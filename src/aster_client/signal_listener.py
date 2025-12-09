"""
ZMQ Signal Listener - Listens for trading signals via ZeroMQ and executes them.

This module provides the ZMQSignalListener class which handles ENTRY/EXIT/PARTIAL_EXIT
signals from the Python realtime trading pipeline.

Supported message format (Signal):
{
    "type": "signal",
    "action": "ENTRY|EXIT|PARTIAL_EXIT",
    "direction": "LONG|SHORT",
    "symbol": "SOLUSDT",
    "price": 150.50,
    "timestamp": "2025-12-09T01:00:00Z",
    "stop_loss": 148.00,
    "position_size_r": 20.0,
    "exit_pct": 0.5,
    "move_sl_to_be": false
}
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from decimal import Decimal, ROUND_DOWN
from pathlib import Path
from typing import Dict, Any, Optional, List

import yaml
import zmq
import zmq.asyncio

from .account_pool import AccountPool, AccountConfig
from .account_ws import AccountWebSocket
from .public_client import AsterPublicClient
from .bbo import BBOPriceCalculator
from .models.signal_models import SignalMessage, PositionState, PositionSizingConfig
from .models.orders import OrderRequest

logger = logging.getLogger(__name__)


class ZMQSignalListener:
    """
    Listens for trading signals via ZeroMQ and executes them with position tracking.
    
    This listener:
    - Loads accounts from accounts_config.yml
    - Maintains WebSocket connections per account for position tracking
    - Uses R-based position sizing
    - Handles ENTRY/EXIT/PARTIAL_EXIT signals
    """

    def __init__(
        self,
        zmq_url: Optional[str] = None,
        topic: str = "orders",
        config_path: str = "accounts_config.yml",
        log_dir: str = "logs",
    ):
        """
        Initialize the signal listener.
        
        Args:
            zmq_url: ZMQ publisher URL. If None, uses ZMQ_URL env var.
            topic: Topic to subscribe to (default: "orders")
            config_path: Path to accounts config YAML file
            log_dir: Directory for log files
        """
        if zmq_url is None:
            zmq_url = os.environ.get("ZMQ_URL", "tcp://127.0.0.1:5555")
        
        self.zmq_url = zmq_url
        self.topic = topic
        self.config_path = config_path
        self.log_dir = log_dir
        
        # ZMQ setup
        self.ctx = zmq.asyncio.Context()
        self.socket = self.ctx.socket(zmq.SUB)
        self.running = False
        
        # Account management
        self.account_configs: List[AccountConfig] = []
        self.account_websockets: Dict[str, AccountWebSocket] = {}
        self.position_sizing: PositionSizingConfig = PositionSizingConfig()
        
        # Position tracking (aggregated from all account WebSockets)
        # Key: f"{account_id}:{symbol}" -> PositionState
        self.positions: Dict[str, PositionState] = {}
        
        # Market data
        self.public_client = AsterPublicClient(auto_warmup=False)
        self.bbo_calculator = BBOPriceCalculator()
        
        # Session logging
        self.file_handler = None
        self._setup_session_logging()
        
        # Contract size cache
        self.contract_sizes: Dict[str, Decimal] = {}

    def _setup_session_logging(self):
        """Set up session-specific log file."""
        log_path = Path(self.log_dir)
        log_path.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_filename = f"signal_listener_{timestamp}.log"
        log_filepath = log_path / log_filename
        
        self.file_handler = logging.FileHandler(log_filepath, mode='a', encoding='utf-8')
        self.file_handler.setLevel(logging.DEBUG)
        
        formatter = logging.Formatter(
            fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        self.file_handler.setFormatter(formatter)
        logger.addHandler(self.file_handler)
        
        logger.info(f"Session log file created: {log_filepath}")

    def _load_config(self):
        """Load accounts and position sizing from config file."""
        config_path = Path(self.config_path)
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")
        
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        # Load position sizing
        if "position_sizing" in config:
            self.position_sizing = PositionSizingConfig.from_dict(config["position_sizing"])
        
        logger.info(f"💰 Position Sizing: deposit={self.position_sizing.deposit_size} USDT, "
                   f"R={self.position_sizing.r_percentage * 100}% = {self.position_sizing.r_value} USDT")
        
        # Load accounts
        accounts = config.get("accounts", [])
        self.account_configs = []
        
        for acc in accounts:
            account_config = AccountConfig(
                id=acc["id"],
                api_key=acc["api_key"],
                api_secret=acc["api_secret"],
                simulation=acc.get("simulation", False),
                recv_window=acc.get("recv_window", 5000),
            )
            self.account_configs.append(account_config)
        
        logger.info(f"📋 Loaded {len(self.account_configs)} accounts from {config_path}")

    def _on_position_update(self, account_id: str, position: Optional[PositionState]):
        """Callback for WebSocket position updates."""
        if position is None:
            # Position closed - remove from tracking
            for key in list(self.positions.keys()):
                if key.startswith(f"{account_id}:"):
                    del self.positions[key]
        else:
            key = f"{account_id}:{position.symbol}"
            self.positions[key] = position

    async def start(self):
        """Start the signal listener."""
        logger.info(f"🚀 Starting ZMQ Signal Listener...")
        
        # Load configuration
        self._load_config()
        
        if not self.account_configs:
            logger.error("No accounts configured!")
            return
        
        # Connect to ZMQ
        logger.info(f"Connecting to ZMQ publisher at {self.zmq_url}...")
        self.socket.connect(self.zmq_url)
        self.socket.subscribe(self.topic.encode())
        self.running = True
        
        # Start BBO WebSocket
        await self.bbo_calculator.start()
        
        # Warmup symbol cache
        logger.info("Warming up symbol cache...")
        try:
            cached_count = await self.public_client.warmup_cache()
            logger.info(f"Symbol cache warmed up with {cached_count} symbols")
        except Exception as e:
            logger.warning(f"Failed to warmup symbol cache: {e}")
        
        # Start account WebSockets
        for acc_config in self.account_configs:
            ws = AccountWebSocket(
                account_id=acc_config.id,
                api_key=acc_config.api_key,
                api_secret=acc_config.api_secret,
                on_position_update=self._on_position_update,
            )
            await ws.start()
            self.account_websockets[acc_config.id] = ws
        
        logger.info(f"🎧 Listening for signals on topic '{self.topic}'...")
        
        # Main message loop
        while self.running:
            try:
                if self.topic:
                    msg_parts = await self.socket.recv_multipart()
                    payload = msg_parts[1] if len(msg_parts) >= 2 else msg_parts[0]
                else:
                    payload = await self.socket.recv()
                
                try:
                    message = json.loads(payload)
                    logger.info(f"📨 Received message: type={message.get('type', 'signal')}, "
                               f"action={message.get('action', 'N/A')}")
                    
                    asyncio.create_task(self.process_message(message))
                    
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to decode JSON: {e}")
                    
            except asyncio.CancelledError:
                logger.info("Signal listener cancelled")
                break
            except Exception as e:
                logger.error(f"Error in message loop: {e}", exc_info=True)
                await asyncio.sleep(1)

    async def stop(self):
        """Stop the signal listener."""
        self.running = False
        
        # Stop account WebSockets
        for ws in self.account_websockets.values():
            await ws.stop()
        self.account_websockets.clear()
        
        # Stop BBO WebSocket
        await self.bbo_calculator.stop()
        
        # Close public client
        await self.public_client.close()
        
        # Close ZMQ
        self.socket.close()
        self.ctx.term()
        
        # Cleanup logging
        if self.file_handler:
            logger.removeHandler(self.file_handler)
            self.file_handler.close()
        
        logger.info("Signal listener stopped")

    async def process_message(self, message: Dict[str, Any]):
        """Process incoming signal message."""
        try:
            msg_type = message.get("type", "signal")
            
            if msg_type == "heartbeat":
                logger.debug(f"Heartbeat: {message.get('status', 'ok')}")
                return
            
            if msg_type != "signal":
                logger.warning(f"Unknown message type: {msg_type}")
                return
            
            # Parse signal message
            try:
                signal = SignalMessage.from_dict(message)
            except Exception as e:
                logger.error(f"Failed to parse signal message: {e}")
                return
            
            # Validate signal
            if signal.direction not in ("LONG", "SHORT"):
                logger.error(f"Invalid direction: {signal.direction}")
                return
            
            # Route by action
            action = signal.action.upper() if signal.action else "ENTRY"
            
            if action == "ENTRY":
                await self._handle_entry_signal(signal)
            elif action == "EXIT":
                await self._handle_exit_signal(signal)
            elif action == "PARTIAL_EXIT":
                await self._handle_partial_exit_signal(signal)
            else:
                logger.warning(f"Unknown action: {action}")
                
        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)

    async def _get_contract_size(self, symbol: str) -> Decimal:
        """Get contract size for symbol (cached)."""
        if symbol in self.contract_sizes:
            return self.contract_sizes[symbol]
        
        try:
            symbol_info = await self.public_client.get_symbol_info(symbol)
            if symbol_info and symbol_info.lot_size_filter:
                contract_size = symbol_info.lot_size_filter.step_size
                if contract_size:
                    self.contract_sizes[symbol] = contract_size
                    logger.debug(f"Contract size for {symbol}: {contract_size}")
                    return contract_size
        except Exception as e:
            logger.warning(f"Failed to get contract size for {symbol}: {e}")
        
        # Default to 1
        return Decimal("1")

    async def _handle_entry_signal(self, signal: SignalMessage):
        """Handle ENTRY signal - open new position."""
        logger.info(f"\n🚀 ENTRY Signal: {signal.direction} {signal.symbol} @ {signal.price}")
        
        if signal.stop_loss:
            logger.info(f"   Stop Loss: {signal.stop_loss}")
        if signal.position_size_r:
            logger.info(f"   Position Size: {signal.position_size_r}R")
        
        # Check for existing positions
        for acc_config in self.account_configs:
            key = f"{acc_config.id}:{signal.symbol}"
            existing = self.positions.get(key)
            
            if existing:
                if existing.is_read_only:
                    logger.warning(f"[{acc_config.id}] Position is READ-ONLY, skipping")
                    continue
                
                # Check if same direction - skip if already positioned
                if existing.side == signal.direction:
                    logger.info(f"[{acc_config.id}] Already have {signal.direction} position, skipping")
                    continue
                
                # Opposite direction - need to close first
                logger.info(f"[{acc_config.id}] Opposite position exists, will close and flip")
        
        # Get market data
        symbol_info = await self.public_client.get_symbol_info(signal.symbol)
        if not symbol_info:
            logger.error(f"Failed to get symbol info for {signal.symbol}")
            return
        
        tick_size = symbol_info.price_filter.tick_size if symbol_info.price_filter else Decimal("0.01")
        
        # Get BBO
        bbo = self.bbo_calculator.get_bbo(signal.symbol)
        if bbo:
            best_bid, best_ask = bbo
        else:
            order_book = await self.public_client.get_order_book(signal.symbol, limit=5)
            if not order_book or "bids" not in order_book:
                logger.error(f"Failed to get order book for {signal.symbol}")
                return
            best_bid = Decimal(order_book["bids"][0][0])
            best_ask = Decimal(order_book["asks"][0][0])
        
        logger.info(f"   Market: Bid={best_bid}, Ask={best_ask}")
        
        # Calculate position size
        contract_size = await self._get_contract_size(signal.symbol)
        
        quantity = self.position_sizing.calculate_quantity(
            entry_price=signal.price,
            position_size_r=signal.position_size_r or 1.0,
            contract_size=contract_size,
            leverage=20,
        )
        
        if quantity <= 0:
            logger.error("Calculated quantity is 0, skipping")
            return
        
        logger.info(f"   Quantity: {quantity} contracts")
        
        # Execute on all accounts
        async with AccountPool(self.account_configs) as pool:
            tasks = []
            for acc_config in self.account_configs:
                client = pool.get_client(acc_config.id)
                if not client:
                    continue
                
                key = f"{acc_config.id}:{signal.symbol}"
                existing = self.positions.get(key)
                
                # If existing opposite position, close it first
                if existing and existing.side != signal.direction and not existing.is_read_only:
                    close_side = "sell" if existing.side == "LONG" else "buy"
                    close_position_side = existing.side
                    
                    close_request = OrderRequest(
                        symbol=signal.symbol,
                        side=close_side,
                        order_type="market",
                        quantity=existing.quantity,
                        position_side=close_position_side,
                        reduce_only=True,
                    )
                    
                    async def close_and_open(c, acc_id, close_req, open_qty, signal):
                        # Close existing
                        try:
                            await c.place_order(close_req)
                            logger.info(f"[{acc_id}] Closed existing position")
                        except Exception as e:
                            logger.error(f"[{acc_id}] Failed to close position: {e}")
                            return None
                        
                        await asyncio.sleep(0.1)  # Small delay
                        
                        # Open new position
                        side = "buy" if signal.direction == "LONG" else "sell"
                        position_side = signal.direction
                        
                        open_request = OrderRequest(
                            symbol=signal.symbol,
                            side=side,
                            order_type="market",
                            quantity=open_qty,
                            position_side=position_side,
                            stop_price=signal.stop_loss,
                        )
                        
                        try:
                            result = await c.place_order(open_request)
                            logger.info(f"[{acc_id}] Opened {signal.direction} position")
                            return result
                        except Exception as e:
                            logger.error(f"[{acc_id}] Failed to open position: {e}")
                            return None
                    
                    task = close_and_open(client, acc_config.id, close_request, quantity, signal)
                    tasks.append(task)
                else:
                    # Just open new position
                    side = "buy" if signal.direction == "LONG" else "sell"
                    position_side = signal.direction
                    
                    request = OrderRequest(
                        symbol=signal.symbol,
                        side=side,
                        order_type="market",
                        quantity=quantity,
                        position_side=position_side,
                    )
                    
                    async def open_position(c, acc_id, req, sl_price, symbol, direction):
                        try:
                            result = await c.place_order(req)
                            logger.info(f"[{acc_id}] Opened {direction} position: {result.order_id}")
                            
                            # Place SL if provided
                            if sl_price:
                                exit_side = "sell" if direction == "LONG" else "buy"
                                sl_request = OrderRequest(
                                    symbol=symbol,
                                    side=exit_side,
                                    order_type="stop_market",
                                    quantity=Decimal("0"),
                                    stop_price=sl_price,
                                    position_side=direction,
                                    close_position=True,
                                )
                                try:
                                    sl_result = await c.place_order(sl_request)
                                    logger.info(f"[{acc_id}] SL placed: {sl_result.order_id} @ {sl_price}")
                                except Exception as e:
                                    logger.error(f"[{acc_id}] Failed to place SL: {e}")
                            
                            return result
                        except Exception as e:
                            logger.error(f"[{acc_id}] Failed to open position: {e}")
                            return None
                    
                    task = open_position(
                        client, acc_config.id, request,
                        signal.stop_loss, signal.symbol, signal.direction
                    )
                    tasks.append(task)
            
            if tasks:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                success = sum(1 for r in results if r is not None and not isinstance(r, Exception))
                logger.info(f"✅ ENTRY completed: {success}/{len(tasks)} accounts")

    async def _handle_exit_signal(self, signal: SignalMessage):
        """Handle EXIT signal - close all positions for symbol."""
        logger.info(f"\n🛑 EXIT Signal: {signal.direction} {signal.symbol}")
        if signal.reason:
            logger.info(f"   Reason: {signal.reason}")
        
        async with AccountPool(self.account_configs) as pool:
            tasks = []
            
            for acc_config in self.account_configs:
                client = pool.get_client(acc_config.id)
                if not client:
                    continue
                
                key = f"{acc_config.id}:{signal.symbol}"
                position = self.positions.get(key)
                
                if not position:
                    logger.info(f"[{acc_config.id}] No position to close")
                    continue
                
                if position.is_read_only:
                    logger.warning(f"[{acc_config.id}] Position is READ-ONLY, skipping")
                    continue
                
                # Verify direction matches
                if position.side != signal.direction:
                    logger.warning(f"[{acc_config.id}] Position side {position.side} != signal {signal.direction}")
                    continue
                
                # Close position
                close_side = "sell" if position.side == "LONG" else "buy"
                
                async def close_position(c, acc_id, symbol, side, qty, pos_side):
                    try:
                        # Cancel existing orders first
                        await c.cancel_all_open_orders(symbol)
                        logger.debug(f"[{acc_id}] Cancelled existing orders")
                    except Exception as e:
                        logger.warning(f"[{acc_id}] Failed to cancel orders: {e}")
                    
                    request = OrderRequest(
                        symbol=symbol,
                        side=side,
                        order_type="market",
                        quantity=qty,
                        position_side=pos_side,
                        reduce_only=True,
                    )
                    
                    try:
                        result = await c.place_order(request)
                        logger.info(f"[{acc_id}] Position closed: {result.order_id}")
                        return result
                    except Exception as e:
                        logger.error(f"[{acc_id}] Failed to close position: {e}")
                        return None
                
                task = close_position(
                    client, acc_config.id, signal.symbol,
                    close_side, position.quantity, position.side
                )
                tasks.append(task)
            
            if tasks:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                success = sum(1 for r in results if r is not None and not isinstance(r, Exception))
                logger.info(f"✅ EXIT completed: {success}/{len(tasks)} accounts")
            else:
                logger.warning("No positions to close")

    async def _handle_partial_exit_signal(self, signal: SignalMessage):
        """Handle PARTIAL_EXIT signal - partial close with optional SL to BE."""
        logger.info(f"\n✂️ PARTIAL_EXIT Signal: {signal.direction} {signal.symbol}")
        logger.info(f"   Exit: {(signal.exit_pct or 0) * 100}%")
        if signal.move_sl_to_be:
            logger.info(f"   Move SL to BE: True")
        
        async with AccountPool(self.account_configs) as pool:
            tasks = []
            
            for acc_config in self.account_configs:
                client = pool.get_client(acc_config.id)
                if not client:
                    continue
                
                key = f"{acc_config.id}:{signal.symbol}"
                position = self.positions.get(key)
                
                if not position:
                    logger.info(f"[{acc_config.id}] No position for partial exit")
                    continue
                
                if position.is_read_only:
                    logger.warning(f"[{acc_config.id}] Position is READ-ONLY")
                    continue
                
                # Calculate close quantity
                exit_pct = signal.exit_pct or 0.5
                close_qty = (position.quantity * Decimal(str(exit_pct))).quantize(
                    Decimal("1"), rounding=ROUND_DOWN
                )
                
                if close_qty < 1:
                    close_qty = Decimal("1")
                if close_qty > position.quantity:
                    close_qty = position.quantity
                
                logger.info(f"[{acc_config.id}] Closing {close_qty} of {position.quantity}")
                
                close_side = "sell" if position.side == "LONG" else "buy"
                
                async def partial_close(c, acc_id, symbol, side, qty, pos_side, entry_price, move_sl):
                    # Close portion
                    request = OrderRequest(
                        symbol=symbol,
                        side=side,
                        order_type="market",
                        quantity=qty,
                        position_side=pos_side,
                        reduce_only=True,
                    )
                    
                    try:
                        result = await c.place_order(request)
                        logger.info(f"[{acc_id}] Partial close: {result.order_id}")
                    except Exception as e:
                        logger.error(f"[{acc_id}] Failed partial close: {e}")
                        return None
                    
                    # Move SL to BE if requested
                    if move_sl and entry_price:
                        try:
                            # Cancel existing orders
                            await c.cancel_all_open_orders(symbol)
                            
                            # Place new SL at entry
                            exit_side = "sell" if pos_side == "LONG" else "buy"
                            sl_request = OrderRequest(
                                symbol=symbol,
                                side=exit_side,
                                order_type="stop_market",
                                quantity=Decimal("0"),
                                stop_price=entry_price,
                                position_side=pos_side,
                                close_position=True,
                            )
                            sl_result = await c.place_order(sl_request)
                            logger.info(f"[{acc_id}] SL moved to BE: {sl_result.order_id} @ {entry_price}")
                        except Exception as e:
                            logger.error(f"[{acc_id}] Failed to move SL to BE: {e}")
                    
                    return result
                
                task = partial_close(
                    client, acc_config.id, signal.symbol,
                    close_side, close_qty, position.side,
                    position.entry_price, signal.move_sl_to_be
                )
                tasks.append(task)
            
            if tasks:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                success = sum(1 for r in results if r is not None and not isinstance(r, Exception))
                logger.info(f"✅ PARTIAL_EXIT completed: {success}/{len(tasks)} accounts")
