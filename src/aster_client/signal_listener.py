"""
NATS Signal Listener - Listens for trading signals via NATS and executes them.

Location: src/aster_client/signal_listener.py
Purpose: Receive ENTRY/EXIT/PARTIAL_EXIT signals from run_realtime.py and execute trades
Relevant files: models/signal_models.py, account_pool.py, bbo.py

This module provides the NATSSignalListener class which handles trading signals
from the Python realtime trading pipeline (run_realtime.py).

Symbol format: Accepts both SOL_USDT and SOLUSDT formats (auto-converted to Binance format)

Supported message formats from run_realtime.py:

1. ENTRY - Open new position:
{
    "action": "ENTRY",
    "direction": "LONG" | "SHORT",
    "symbol": "SOL_USDT",
    "price": 100.0,
    "stop_loss": 95.0,
    "take_profit": 110.0,
    "confidence": 0.85,
    "position_size_r": 1.0,
    "signal_type": "BUY" | "SELL",
    "timestamp": "2025-12-14T17:22:47...",
    "multi_tp_enabled": true,
    "tp_levels": [{"price": 105.0, "exit_pct": 0.5, "ratio": 1.0}, ...],
    "move_sl_to_be_after_tp1": false
}

2. EXIT - Close position:
{
    "action": "EXIT",
    "direction": "LONG" | "SHORT",
    "symbol": "SOL_USDT",
    "price": 105.0,
    "reason": "TP" | "SL" | "TimeKill" | "SignalFlip",
    "timestamp": "2025-12-14T17:22:47..."
}

3. PARTIAL_EXIT - Partial profit take:
{
    "action": "PARTIAL_EXIT",
    "direction": "LONG" | "SHORT",
    "symbol": "SOL_USDT",
    "price": 103.0,
    "tp_level": 1,
    "exit_pct": 0.5,
    "remaining_pct": 0.5,
    "move_sl_to_be": true,
    "timestamp": "2025-12-14T17:22:47..."
}

NATS Configuration:
- Default URL: nats://localhost:4222
- Subject: "orders"
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
from nats.aio.client import Client as NATS

from .account_pool import AccountPool, AccountConfig
from .account_ws import AccountWebSocket
from .public_client import AsterPublicClient
from .bbo import BBOPriceCalculator
from .models.signal_models import SignalMessage, PositionState, PositionSizingConfig
from .models.orders import OrderRequest

logger = logging.getLogger(__name__)


class NATSSignalListener:
    """
    Listens for trading signals via NATS and executes them with position tracking.
    
    This listener:
    - Loads accounts from accounts_config.yml
    - Maintains WebSocket connections per account for position tracking
    - Uses R-based position sizing
    - Handles ENTRY/EXIT/PARTIAL_EXIT signals
    """

    def __init__(
        self,
        nats_url: Optional[str] = None,
        subject: str = "orders",
        config_path: str = "accounts_config.yml",
        log_dir: str = "logs",
        allowed_symbols: Optional[List[str]] = None,
    ):
        """
        Initialize the signal listener.
        
        Args:
            nats_url: NATS server URL. If None, uses NATS_URL env var.
            subject: Subject to subscribe to (default: "orders")
            config_path: Path to accounts config YAML file
            log_dir: Directory for log files
            allowed_symbols: List of symbols to accept (empty = all)
        """
        if nats_url is None:
            nats_url = os.environ.get("NATS_URL", "nats://localhost:4222")
        
        self.nats_url = nats_url
        self.subject = subject
        self.config_path = config_path
        self.log_dir = log_dir
        
        # Symbol filter (normalized to uppercase without separators)
        self._allowed_symbols = set(s.upper().replace("_", "").replace("/", "") for s in (allowed_symbols or []))
        
        # NATS setup
        self.nc = NATS()
        self.subscription = None
        self.running = False
        
        # Account management
        self.account_configs: List[AccountConfig] = []
        self.account_websockets: Dict[str, AccountWebSocket] = {}
        self.position_sizing: PositionSizingConfig = PositionSizingConfig()
        
        # Position tracking (aggregated from all account WebSockets)
        # Key: f"{account_id}:{symbol}" -> PositionState
        self.positions: Dict[str, PositionState] = {}
        
        # Order tracking for auto-cancel when position closes
        # Key: f"{account_id}:{symbol}" -> {"sl": order_id, "tp": [order_ids]}
        self.position_orders: Dict[str, Dict[str, Any]] = {}
        
        # Market data
        self.public_client = AsterPublicClient(auto_warmup=False)
        self.bbo_calculator = BBOPriceCalculator()
        
        # Session logging
        self.file_handler = None
        self._setup_session_logging()
        
        # Contract size cache
        self.contract_sizes: Dict[str, Decimal] = {}

    def _normalize_symbol(self, symbol: str) -> str:
        """
        Convert symbol from various formats to Binance format.
        
        Examples:
            SOL_USDT -> SOLUSDT
            SOL/USDT -> SOLUSDT
            SOLUSDT -> SOLUSDT (unchanged)
        """
        if not symbol:
            return symbol
        # Remove underscores and slashes
        normalized = symbol.replace("_", "").replace("/", "").upper()
        return normalized

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
        
        # Load global position sizing (fallback)
        if "position_sizing" in config:
            self.position_sizing = PositionSizingConfig.from_dict(config["position_sizing"])
        
        logger.info(f"💰 Default Position Sizing: deposit={self.position_sizing.deposit_size} USDT, "
                   f"R={self.position_sizing.r_percentage * 100}% = {self.position_sizing.r_value} USDT")
        
        # Load accounts with per-account position sizing
        accounts = config.get("accounts", [])
        self.account_configs = []
        self.account_position_sizing: Dict[str, PositionSizingConfig] = {}
        
        for acc in accounts:
            account_config = AccountConfig(
                id=acc["id"],
                api_key=acc["api_key"],
                api_secret=acc["api_secret"],
                simulation=acc.get("simulation", False),
                recv_window=acc.get("recv_window", 5000),
            )
            self.account_configs.append(account_config)
            
            # Per-account position sizing (optional, falls back to global)
            if "position_sizing" in acc:
                ps = PositionSizingConfig.from_dict(acc["position_sizing"])
                self.account_position_sizing[acc["id"]] = ps
                logger.info(f"   [{acc['id']}] Position Sizing: deposit={ps.deposit_size} USDT, R={ps.r_value} USDT")
        
        logger.info(f"📋 Loaded {len(self.account_configs)} accounts from {config_path}")

    def _on_position_update(self, account_id: str, position: Optional[PositionState]):
        """Callback for WebSocket position updates."""
        if position is None:
            # Old behavior - should not happen anymore, but handle gracefully
            for key in list(self.positions.keys()):
                if key.startswith(f"{account_id}:"):
                    parts = key.split(":", 2)
                    symbol = parts[1] if len(parts) >= 2 else ""
                    del self.positions[key]
                    if key in self.position_orders:
                        asyncio.create_task(self._cancel_position_orders(account_id, symbol, key))
        elif position.quantity == 0:
            # Position closed - cancel related orders
            # Use symbol:side as key for hedge mode
            key = f"{account_id}:{position.symbol}:{position.side}"
            if key in self.positions:
                del self.positions[key]
            if key in self.position_orders:
                logger.info(f"[{account_id}] Position {position.symbol} {position.side} closed, canceling SL/TP orders...")
                asyncio.create_task(self._cancel_position_orders(account_id, position.symbol, key))
        else:
            # Use symbol:side as key for hedge mode
            key = f"{account_id}:{position.symbol}:{position.side}"
            self.positions[key] = position

    async def _cancel_position_orders(self, account_id: str, symbol: str, key: str):
        """Cancel all SL/TP orders for a closed position."""
        orders = self.position_orders.pop(key, {})
        if not orders:
            return
        
        # Get the account client
        acc_config = next((a for a in self.account_configs if a.id == account_id), None)
        if not acc_config:
            return
        
        try:
            async with AccountPool([acc_config]) as pool:
                client = pool.get_client(account_id)
                if not client:
                    return
                
                # Cancel SL order
                sl_order_id = orders.get("sl")
                if sl_order_id:
                    try:
                        await client.cancel_order(symbol=symbol, order_id=sl_order_id)
                        logger.info(f"[{account_id}] Canceled SL order {sl_order_id} (position closed)")
                    except Exception as e:
                        logger.debug(f"[{account_id}] SL order {sl_order_id} cancel failed (may already be filled): {e}")
                
                # Cancel TP orders
                tp_order_ids = orders.get("tp", [])
                for tp_order_id in tp_order_ids:
                    try:
                        await client.cancel_order(symbol=symbol, order_id=tp_order_id)
                        logger.info(f"[{account_id}] Canceled TP order {tp_order_id} (position closed)")
                    except Exception as e:
                        logger.debug(f"[{account_id}] TP order {tp_order_id} cancel failed (may already be filled): {e}")
        except Exception as e:
            logger.error(f"[{account_id}] Error canceling orders for {symbol}: {e}")

    async def start(self):
        """Start the signal listener."""
        logger.info(f"🚀 Starting NATS Signal Listener...")
        
        # Load configuration
        self._load_config()
        
        if not self.account_configs:
            logger.error("No accounts configured!")
            return
        
        # Connect to NATS
        logger.info(f"Connecting to NATS server at {self.nats_url}...")
        await self.nc.connect(self.nats_url)
        self.running = True
        
        # Start BBO WebSocket
        await self.bbo_calculator.start()
        
        # Skip symbol cache warmup - only cache SOLUSDT on-demand
        logger.info("Skipping symbol cache warmup (will cache SOLUSDT on-demand)")

        
        # Start account WebSockets with allowed_symbols for read-only logic
        for acc_config in self.account_configs:
            ws = AccountWebSocket(
                account_id=acc_config.id,
                api_key=acc_config.api_key,
                api_secret=acc_config.api_secret,
                on_position_update=self._on_position_update,
                allowed_symbols=self._allowed_symbols,
            )
            await ws.start()
            self.account_websockets[acc_config.id] = ws
        
        logger.info(f"🎧 Listening for signals on subject '{self.subject}'...")
        
        # Subscribe to NATS subject
        async def message_handler(msg):
            try:
                payload = msg.data.decode()
                message = json.loads(payload)
                logger.info(f"📨 Received message: type={message.get('type', 'signal')}, "
                           f"action={message.get('action', 'N/A')}")
                
                asyncio.create_task(self.process_message(message))
                
            except json.JSONDecodeError as e:
                logger.error(f"Failed to decode JSON: {e}")
            except Exception as e:
                logger.error(f"Error processing message: {e}", exc_info=True)
        
        self.subscription = await self.nc.subscribe(self.subject, cb=message_handler)
        
        # Keep running until stopped
        while self.running:
            await asyncio.sleep(1)

    async def stop(self):
        """Stop the signal listener."""
        self.running = False
        
        # Stop account WebSockets
        for ws in list(self.account_websockets.values()):
            await ws.stop()
        self.account_websockets.clear()
        
        # Stop BBO WebSocket
        await self.bbo_calculator.stop()
        
        # Close public client
        await self.public_client.close()
        
        # Close NATS (gracefully handle if already closed)
        try:
            if self.subscription:
                await self.subscription.unsubscribe()
        except Exception:
            pass  # Already closed
        
        try:
            await self.nc.close()
        except Exception:
            pass  # Already closed
        
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
            
            # Accept both explicit "signal" type and messages with just "action" field
            # (run_realtime.py sends action without type)
            if msg_type != "signal" and "action" not in message:
                logger.warning(f"Unknown message type: {msg_type}")
                return
            
            # Normalize symbol format before parsing (SOL_USDT -> SOLUSDT)
            if "symbol" in message:
                message["symbol"] = self._normalize_symbol(message["symbol"])
                logger.debug(f"Normalized symbol: {message['symbol']}")
            
            # Parse signal message
            try:
                signal = SignalMessage.from_dict(message)
            except Exception as e:
                logger.error(f"Failed to parse signal message: {e}")
                return
            
            # Check symbol filter
            if self._allowed_symbols and signal.symbol not in self._allowed_symbols:
                logger.debug(f"Skipping signal for {signal.symbol} (not in allowed symbols)")
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
                # PARTIAL_EXIT signals are filtered out - we use limit TP orders instead
                logger.debug(f"Ignoring PARTIAL_EXIT signal for {signal.symbol} (handled by limit TP orders)")
                return
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
        """Handle ENTRY signal - open new position with SL and limit TP orders."""
        logger.info(f"\n🚀 ENTRY Signal: {signal.direction} {signal.symbol} @ {signal.price}")
        
        if signal.stop_loss:
            logger.info(f"   Stop Loss: {signal.stop_loss}")
        if signal.position_size_r:
            logger.info(f"   Position Size: {signal.position_size_r}R")
        if signal.tp_levels:
            logger.info(f"   TP Levels: {len(signal.tp_levels)}")
            for i, tp in enumerate(signal.tp_levels, 1):
                logger.info(f"     TP{i}: {tp.price} ({tp.exit_pct*100:.0f}%)")
        
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
        
        # Get contract step size for this symbol
        contract_size = await self._get_contract_size(signal.symbol)
        
        # Execute on all accounts
        async with AccountPool(self.account_configs) as pool:
            tasks = []
            for acc_config in self.account_configs:
                client = pool.get_client(acc_config.id)
                if not client:
                    continue
                
                # Get per-account position sizing or fall back to global
                position_sizing = self.account_position_sizing.get(
                    acc_config.id, self.position_sizing
                )
                
                # Calculate quantity for this account
                quantity = position_sizing.calculate_quantity(
                    entry_price=signal.price,
                    position_size_r=signal.position_size_r or 1.0,
                    contract_size=contract_size,
                    leverage=5,
                )
                
                if quantity <= 0:
                    logger.error(f"[{acc_config.id}] Calculated quantity is 0, skipping")
                    continue
                
                logger.info(f"   [{acc_config.id}] Quantity: {quantity} (deposit={position_sizing.deposit_size})")
                
                # Check for existing opposite position using symbol:side format
                # In hedge mode, we look for the opposite side
                opposite_side = "SHORT" if signal.direction == "LONG" else "LONG"
                key_opposite = f"{acc_config.id}:{signal.symbol}:{opposite_side}"
                existing = self.positions.get(key_opposite)
                
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
                    
                    # Create order tracking dict for the new position (use symbol:side for hedge mode)
                    position_key = f"{acc_config.id}:{signal.symbol}:{signal.direction}"
                    self.position_orders[position_key] = {"sl": None, "tp": []}
                    orders_ref = self.position_orders[position_key]
                    
                    async def close_and_open_with_tp(c, acc_id, close_req, open_qty, signal, step_size, orders_tracker):
                        """Close existing position, then open new with SL and limit TP orders."""
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
                        exit_side = "sell" if signal.direction == "LONG" else "buy"
                        position_side = signal.direction
                        
                        open_request = OrderRequest(
                            symbol=signal.symbol,
                            side=side,
                            order_type="market",
                            quantity=open_qty,
                            position_side=position_side,
                        )
                        
                        try:
                            result = await c.place_order(open_request)
                            logger.info(f"[{acc_id}] Opened {signal.direction} position")
                            
                            # Place SL if provided
                            if signal.stop_loss:
                                sl_request = OrderRequest(
                                    symbol=signal.symbol,
                                    side=exit_side,
                                    order_type="stop_market",
                                    quantity=Decimal("0"),
                                    stop_price=signal.stop_loss,
                                    position_side=position_side,
                                    close_position=True,
                                )
                                try:
                                    sl_result = await c.place_order(sl_request)
                                    orders_tracker["sl"] = sl_result.order_id
                                    logger.info(f"[{acc_id}] SL placed: {sl_result.order_id} @ {signal.stop_loss}")
                                except Exception as e:
                                    logger.error(f"[{acc_id}] Failed to place SL: {e}")
                            
                            # Place limit TP orders for each TP level
                            if signal.tp_levels:
                                remaining_qty = open_qty
                                for i, tp in enumerate(signal.tp_levels, 1):
                                    tp_qty = open_qty * Decimal(str(tp.exit_pct))
                                    tp_qty = (tp_qty / step_size).quantize(Decimal("1"), rounding=ROUND_DOWN) * step_size
                                    if i == len(signal.tp_levels):
                                        tp_qty = remaining_qty
                                    if tp_qty <= 0:
                                        continue
                                    remaining_qty -= tp_qty
                                    
                                    tp_request = OrderRequest(
                                        symbol=signal.symbol,
                                        side=exit_side,
                                        order_type="limit",
                                        quantity=tp_qty,
                                        price=tp.price,
                                        position_side=position_side,
                                        time_in_force="gtc",
                                    )
                                    try:
                                        tp_result = await c.place_order(tp_request)
                                        orders_tracker["tp"].append(tp_result.order_id)
                                        logger.info(f"[{acc_id}] TP{i} placed: {tp_result.order_id} @ {tp.price} ({tp_qty} qty)")
                                    except Exception as e:
                                        logger.error(f"[{acc_id}] Failed to place TP{i}: {e}")
                            
                            return result
                        except Exception as e:
                            logger.error(f"[{acc_id}] Failed to open position: {e}")
                            return None
                    
                    task = close_and_open_with_tp(client, acc_config.id, close_request, quantity, signal, contract_size, orders_ref)
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
                    
                    # Create order tracking dict for this position (use symbol:side for hedge mode)
                    position_key = f"{acc_config.id}:{signal.symbol}:{signal.direction}"
                    self.position_orders[position_key] = {"sl": None, "tp": []}
                    orders_ref = self.position_orders[position_key]
                    
                    async def open_position_with_tp(c, acc_id, req, sl_price, symbol, direction, total_qty, tp_levels, step_size, orders_tracker):
                        """
                        Open position with market order, then place:
                        1. SL order (stop_market, close_position=True)
                        2. Limit TP orders for each TP level
                        Tracks order IDs in orders_tracker for auto-cancel.
                        """
                        try:
                            result = await c.place_order(req)
                            logger.info(f"[{acc_id}] Opened {direction} position: {result.order_id}")
                            
                            exit_side = "sell" if direction == "LONG" else "buy"
                            
                            # Place SL if provided
                            if sl_price:
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
                                    orders_tracker["sl"] = sl_result.order_id
                                    logger.info(f"[{acc_id}] SL placed: {sl_result.order_id} @ {sl_price}")
                                except Exception as e:
                                    logger.error(f"[{acc_id}] Failed to place SL: {e}")
                            
                            # Place limit TP orders for each TP level
                            if tp_levels:
                                remaining_qty = total_qty
                                for i, tp in enumerate(tp_levels, 1):
                                    # Calculate quantity for this TP level using step_size for rounding
                                    tp_qty = total_qty * Decimal(str(tp.exit_pct))
                                    tp_qty = (tp_qty / step_size).quantize(Decimal("1"), rounding=ROUND_DOWN) * step_size
                                    
                                    # For last TP level, use remaining quantity
                                    if i == len(tp_levels):
                                        tp_qty = remaining_qty
                                    
                                    if tp_qty <= 0:
                                        continue
                                    
                                    remaining_qty -= tp_qty
                                    
                                    tp_request = OrderRequest(
                                        symbol=symbol,
                                        side=exit_side,
                                        order_type="limit",
                                        quantity=tp_qty,
                                        price=tp.price,
                                        position_side=direction,
                                        time_in_force="gtc",
                                    )
                                    try:
                                        tp_result = await c.place_order(tp_request)
                                        orders_tracker["tp"].append(tp_result.order_id)
                                        logger.info(f"[{acc_id}] TP{i} placed: {tp_result.order_id} @ {tp.price} ({tp_qty} qty, {tp.exit_pct*100:.0f}%)")
                                    except Exception as e:
                                        logger.error(f"[{acc_id}] Failed to place TP{i} @ {tp.price}: {e}")
                            
                            return result
                        except Exception as e:
                            logger.error(f"[{acc_id}] Failed to open position: {e}")
                            return None
                    
                    task = open_position_with_tp(
                        client, acc_config.id, request,
                        signal.stop_loss, signal.symbol, signal.direction,
                        quantity, signal.tp_levels, contract_size, orders_ref
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
                
                # Use symbol:side key for hedge mode
                key = f"{acc_config.id}:{signal.symbol}:{signal.direction}"
                position = self.positions.get(key)
                
                if not position:
                    logger.info(f"[{acc_config.id}] No position to close for {signal.symbol} {signal.direction}")
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


# Backward-compatible alias
ZMQSignalListener = NATSSignalListener
