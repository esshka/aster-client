"""
ZMQ Trade Listener - Listens for trade commands via ZeroMQ and executes them in parallel.

This module provides the ZMQTradeListener class which subscribes to a ZeroMQ topic,
receives trade configuration messages, and executes trades across multiple accounts
using the AccountPool and trades modules.

Supported message types:

1. Heartbeat Message
   Used to verify connection and system status.
   {
       "type": "heartbeat",
       "status": "ready",          # Status string (e.g., "ready", "error")
       "timestamp": "ISO8601",     # Current timestamp
       "message": "...",           # Optional status message
       "accounts_loaded": 10       # Number of loaded accounts
   }

2. Trade Command Message
   Used to execute trades across configured accounts.
   {
       "type": "trade",            # Optional, default is "trade"
       "symbol": "BTCUSDT",        # Trading pair symbol
       "side": "buy",              # "buy" or "sell"
       "tp_percent": 1.5,          # Optional: Take profit percentage (e.g., 1.5%), or null
       "sl_percent": 0.5,          # Stop loss percentage (e.g., 0.5%)
       "ticks_distance": 1,        # Optional (default: 1), BBO offset in ticks
       "accounts": [               # List of accounts to execute on
           {
               "id": "acc_1",          # Account identifier
               "api_key": "...",       # API key
               "api_secret": "...",    # API secret
               "quantity": 0.001,      # Order quantity for this account
               "simulation": false     # Optional (default: false), use testnet/sim
           }
       ]
   }

3. Generic Order Message
   Used to place single orders (Limit, Market, BBO) without TP/SL lifecycle.
   {
       "type": "order",
       "symbol": "BTCUSDT",
       "side": "buy",
       "order_type": "limit",      # "limit", "market", "bbo", etc.
       "price": 50000.0,           # Required for limit orders
       "ticks_distance": 1,        # Required for BBO orders (default: 1)
       "reduce_only": false,       # Optional
       "time_in_force": "gtc",     # Optional
       "position_side": "LONG",    # Optional (for hedge mode)
       "accounts": [               # Same account structure as trade message
           {
               "id": "acc_1",
               "api_key": "...",
               "quantity": 0.001,
               ...
           }
       ]
   }
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Dict, Any, Optional, List

import zmq
import zmq.asyncio

from .account_pool import AccountPool, AccountConfig
from .public_client import AsterPublicClient
from .trades import create_trade
from .bbo import BBOPriceCalculator

logger = logging.getLogger(__name__)


class ZMQTradeListener:
    """
    Listens for trade commands via ZeroMQ and executes them.
    
    Attributes:
        zmq_url: The ZMQ URL to subscribe to (e.g., "tcp://127.0.0.1:5555")
        topic: The topic to subscribe to (default: "")
        ctx: ZMQ context
        socket: ZMQ subscriber socket
    """
    
    def __init__(self, zmq_url: Optional[str] = None, topic: str = "", log_dir: str = "logs"):
        """
        Initialize the ZMQ listener.
        
        Args:
            zmq_url: URL of the ZMQ publisher. If None, uses ZMQ_URL env var or default.
            topic: Topic to subscribe to (empty string for all topics)
            log_dir: Directory to store session log files (default: "logs")
        """
        if zmq_url is None:
            zmq_url = os.environ.get("ZMQ_URL", "tcp://127.0.0.1:5555")
            
        self.zmq_url = zmq_url
        self.topic = topic
        self.ctx = zmq.asyncio.Context()
        self.socket = self.ctx.socket(zmq.SUB)
        self.running = False
        self.log_dir = log_dir
        self.file_handler = None
        
        # Initialize public client for market data (shared instance via singleton)
        # auto_warmup=False because we'll manually control warmup timing in start()
        self.public_client = AsterPublicClient(auto_warmup=False)
        
        # Initialize BBO calculator (singleton)
        self.bbo_calculator = BBOPriceCalculator()
        
        # Set up session-specific log file
        self._setup_session_logging()
        
    async def start(self):
        """Start listening for messages."""
        logger.info(f"Connecting to ZMQ publisher at {self.zmq_url}...")
        self.socket.connect(self.zmq_url)
        self.socket.subscribe(self.topic)
        self.running = True
        
        # Start BBO WebSocket client
        await self.bbo_calculator.start()
        
        # Warmup symbol cache before processing any messages
        logger.info("Warming up symbol cache...")
        try:
            cached_count = await self.public_client.warmup_cache()
            logger.info(f"Symbol cache warmed up with {cached_count} symbols")
        except Exception as e:
            logger.warning(f"Failed to warmup symbol cache: {e}. Will fetch symbols on-demand.")
        
        logger.info(f"Listening for messages on topic '{self.topic}'...")
        
        while self.running:
            try:
                # Receive message
                # We expect multipart message: [topic, payload] if topic is set
                # or just payload if we just recv_json/string depending on sender
                # For simplicity, let's assume the sender sends a JSON string.
                # If using topics, it's usually: socket.send_multipart([topic, json_bytes])
                
                if self.topic:
                    msg_parts = await self.socket.recv_multipart()
                    # msg_parts[0] is topic, msg_parts[1] is payload
                    if len(msg_parts) >= 2:
                        payload = msg_parts[1]
                    else:
                        payload = msg_parts[0] # Fallback
                else:
                    payload = await self.socket.recv()
                
                try:
                    message = json.loads(payload)
                    logger.info(f"Received ZMQ message - Topic: '{self.topic}', Payload size: {len(payload)} bytes")
                    
                    # Log sanitized message details
                    self._log_message_received(message)
                    
                    # Process in background to not block receiving new messages
                    asyncio.create_task(self.process_message(message))
                    
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to decode JSON message: {e}. Payload preview: {payload[:100]}")
                    
            except asyncio.CancelledError:
                logger.info("ZMQ listener cancelled")
                break
            except Exception as e:
                logger.error(f"Error in ZMQ loop: {e}", exc_info=True)
                await asyncio.sleep(1)  # Prevent tight loop on error
                
    async def stop(self):
        """Stop the listener."""
        self.running = False
        self.socket.close()
        self.ctx.term()
        
        # Stop BBO WebSocket client
        await self.bbo_calculator.stop()
        
        # Close public client session
        await self.public_client.close()
        
        logger.info("ZMQ listener stopped")
        
        # Clean up file handler
        if self.file_handler:
            logger.removeHandler(self.file_handler)
            self.file_handler.close()
            self.file_handler = None
    
    def _setup_session_logging(self):
        """
        Set up a session-specific log file for this listener instance.
        Log files are named with timestamp: zmq_listener_YYYYMMDD_HHMMSS.log
        """
        # Create logs directory if it doesn't exist
        log_path = Path(self.log_dir)
        log_path.mkdir(parents=True, exist_ok=True)
        
        # Generate unique log filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_filename = f"zmq_listener_{timestamp}.log"
        log_filepath = log_path / log_filename
        
        # Create file handler with detailed formatting
        self.file_handler = logging.FileHandler(log_filepath, mode='a', encoding='utf-8')
        self.file_handler.setLevel(logging.DEBUG)
        
        # Set up formatter
        formatter = logging.Formatter(
            fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        self.file_handler.setFormatter(formatter)
        
        # Add handler to logger
        logger.addHandler(self.file_handler)
        
        logger.info(f"Session log file created: {log_filepath}")
    
    def _sanitize_account_info(self, account_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sanitize account information for logging by masking sensitive data.
        
        Args:
            account_data: Raw account data from message
            
        Returns:
            Dictionary with masked API key and secret
        """
        sanitized = account_data.copy()
        if "api_key" in sanitized:
            key = sanitized["api_key"]
            sanitized["api_key"] = f"{key[:4]}...{key[-4:]}" if len(key) > 8 else "***"
        if "api_secret" in sanitized:
            sanitized["api_secret"] = "***REDACTED***"
        return sanitized
    
    def _log_message_received(self, message: Dict[str, Any]):
        """
        Log received message with sensitive data sanitized.
        
        Args:
            message: The decoded message
        """
        # Check if this is a heartbeat message
        msg_type = message.get("type", "trade")
        
        if msg_type == "heartbeat":
            # Log heartbeat message details
            logger.info(
                f"Heartbeat received - Status: {message.get('status', 'N/A')}, "
                f"Timestamp: {message.get('timestamp', 'N/A')}, "
                f"Message: {message.get('message', 'N/A')}, "
                f"Accounts Loaded: {message.get('accounts_loaded', 'N/A')}"
            )
            return
        
        # Create sanitized copy for logging
        sanitized = message.copy()
        
        # Sanitize account information
        if "accounts" in sanitized:
            sanitized["accounts"] = [
                self._sanitize_account_info(acc) for acc in sanitized["accounts"]
            ]
        
        elif msg_type == "order":
            # Log order command details
            logger.info(
                f"Order command - Symbol: {message.get('symbol', 'N/A')}, "
                f"Side: {message.get('side', 'N/A')}, "
                f"Type: {message.get('order_type', 'N/A')}, "
                f"Accounts: {len(message.get('accounts', []))}"
            )
        else:
            # Log trade command details (default)
            logger.info(
                f"Trade command - Symbol: {message.get('symbol', 'N/A')}, "
                f"Side: {message.get('side', 'N/A')}, "
                f"Accounts: {len(message.get('accounts', []))}, "
                f"TP: {message.get('tp_percent', 'N/A')}%, "
                f"SL: {message.get('sl_percent', 'N/A')}%, "
                f"Ticks Distance: {message.get('ticks_distance', 1)}"
            )
        
        # Log individual account details (sanitized)
        if "accounts" in message:
            for i, acc in enumerate(message["accounts"], 1):
                sanitized_acc = self._sanitize_account_info(acc)
                logger.debug(
                    f"  Account {i}/{len(message['accounts'])}: "
                    f"ID={sanitized_acc.get('id', 'N/A')}, "
                    f"API Key={sanitized_acc.get('api_key', 'N/A')}, "
                    f"Quantity={acc.get('quantity', 'N/A')}, "
                    f"Simulation={acc.get('simulation', False)}"
                )

    async def process_message(self, message: Dict[str, Any]):
        """
        Process a received trade command message.
        
        Args:
            message: Decoded JSON message containing trade details and accounts.
                     See module docstring for detailed message format specifications.
        """
        try:
            # Check if this is a heartbeat message
            msg_type = message.get("type", "trade")
            
            if msg_type == "heartbeat":
                # Heartbeat messages are already logged in _log_message_received
                # No further processing needed
                logger.debug("Heartbeat message processed successfully")
                return
            
            elif msg_type == "order":
                await self._process_order_message(message)
                return

            else:
                # Default to trade processing for backward compatibility or explicit "trade" type
                await self._process_trade_message(message)

        except KeyError as e:
            logger.error(f"Missing required field in message: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"Error processing message: {type(e).__name__}: {e}", exc_info=True)

    async def _process_order_message(self, message: Dict[str, Any]):
        """
        Process a generic order placement message.
        """
        symbol = message["symbol"]
        side = message["side"]
        order_type = message["order_type"] 
        accounts_data = message.get("accounts", [])
        
        if not accounts_data:
            logger.warning("No accounts provided in order message")
            return

        # Fetch market data for BBO if needed
        best_bid = None
        best_ask = None
        tick_size = Decimal("0") # Initialize default

        if order_type.lower() == "bbo":
             logger.info(f"Fetching market data for BBO order on {symbol}...")
             # ... reused logic or simplified BBO fetching ...
             # We need tick_size for BBO too.
             # Actually, place_bbo_order in account_client needs tick_size.
             # We should fetch symbol info regardless to be safe or if needed.
             pass

        # Fetch tick size if BBO or if we want to validate prices (good practice)
        # For optimization, we only fetch if we really need it. BBO needs it.
        if order_type.lower() == "bbo":
             # Try to get BBO from WebSocket cache first
            bbo = self.bbo_calculator.get_bbo(symbol)
            if bbo:
                best_bid, best_ask = bbo
                logger.info(f"Using real-time BBO for {symbol}: Bid=${best_bid}, Ask=${best_ask}")
            else:
                # Fallback to REST API
                order_book = await self.public_client.get_order_book(symbol, limit=5)
                if order_book and "bids" in order_book and "asks" in order_book:
                    best_bid = Decimal(order_book["bids"][0][0])
                    best_ask = Decimal(order_book["asks"][0][0])
                else:
                    logger.error(f"Failed to fetch order book for {symbol}")
                    return

            symbol_info = await self.public_client.get_symbol_info(symbol)
            if not symbol_info or not symbol_info.price_filter:
                logger.error(f"Failed to fetch symbol info for {symbol}")
                return
            tick_size = symbol_info.price_filter.tick_size

        
        # Prepare execution tasks
        logger.info(
            f"Starting order batch execution - Symbol: {symbol}, Type: {order_type}, "
            f"Side: {side}, Accounts: {len(accounts_data)}"
        )

        account_configs = []
        quantities = {}
        
        for i, acc in enumerate(accounts_data, 1):
            config = AccountConfig(
                id=acc["id"],
                api_key=acc["api_key"],
                api_secret=acc["api_secret"],
                simulation=acc.get("simulation", False)
            )
            account_configs.append(config)
            quantities[acc["id"]] = Decimal(str(acc["quantity"]))

        async with AccountPool(account_configs) as pool:
            tasks = []
            for acc_config in account_configs:
                client = pool.get_client(acc_config.id)
                if not client:
                    continue
                
                qty = quantities[acc_config.id]
                
                if order_type.lower() == "bbo":
                     # Special handling for BBO
                     ticks_distance = int(message.get("ticks_distance", 1))
                     task = client.place_bbo_order(
                         symbol=symbol,
                         side=side,
                         quantity=qty,
                         best_bid=best_bid,
                         best_ask=best_ask,
                         tick_size=tick_size,
                         ticks_distance=ticks_distance,
                         time_in_force=message.get("time_in_force", "gtc"),
                         client_order_id=message.get("client_order_id"),
                         position_side=message.get("position_side")
                     )
                else:
                    # Standard order types (LIMIT, MARKET, etc.)
                    from .models.orders import OrderRequest
                    
                    price = None
                    if "price" in message and message["price"] is not None:
                        price = Decimal(str(message["price"]))
                        
                    stop_price = None
                    if "stop_price" in message and message["stop_price"] is not None:
                         stop_price = Decimal(str(message["stop_price"]))

                    req = OrderRequest(
                        symbol=symbol,
                        side=side,
                        order_type=order_type,
                        quantity=qty,
                        price=price,
                        stop_price=stop_price,
                        time_in_force=message.get("time_in_force"),
                        reduce_only=message.get("reduce_only"),
                        position_side=message.get("position_side"),
                        client_order_id=message.get("client_order_id"),
                    )
                    task = client.place_order(req)
                
                tasks.append(task)

            # Execute
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Log results
            success = 0
            failed = 0
            for i, res in enumerate(results):
                acc_id = account_configs[i].id
                if isinstance(res, Exception):
                    failed += 1
                    logger.error(f"Order failed for {acc_id}: {res}")
                else:
                    success += 1
                    logger.info(f"Order success for {acc_id}: ID={res.order_id}, Status={res.status}")
            
            logger.info(f"Order batch completed: {success} ok, {failed} failed")


    async def _process_trade_message(self, message: Dict[str, Any]):
        """
        Process a standard trade lifecycle message (Entry + TP/SL).
        Target of refactoring from original process_message.
        """
        # Extract common trade parameters
        symbol = message["symbol"]
        side = message["side"]
        
        tp_percent_raw = message.get("tp_percent")
        tp_percent = float(tp_percent_raw) if tp_percent_raw is not None else None
        
        sl_percent = float(message["sl_percent"])
        ticks_distance = int(message.get("ticks_distance", 1))
        
        accounts_data = message.get("accounts", [])
        if not accounts_data:
            logger.warning("No accounts provided in message")
            return
        
        # Fetch market data
        logger.info(f"Fetching market data for {symbol}...")
        
        # Try to get BBO from WebSocket cache first
        bbo = self.bbo_calculator.get_bbo(symbol)
        
        if bbo:
            best_bid, best_ask = bbo
            logger.info(f"Using real-time BBO for {symbol}: Bid=${best_bid}, Ask=${best_ask}")
        else:
            # Fallback to REST API if not in cache (e.g. startup)
            logger.warning(f"BBO not in cache for {symbol}, falling back to REST API")
            order_book = await self.public_client.get_order_book(symbol, limit=5)
            if not order_book or "bids" not in order_book or "asks" not in order_book:
                logger.error(f"Failed to fetch order book for {symbol}")
                return
            
            try:
                best_bid = Decimal(order_book["bids"][0][0])
                best_ask = Decimal(order_book["asks"][0][0])
                logger.info(f"Market data fetched via REST: Bid=${best_bid}, Ask=${best_ask}")
            except (IndexError, ValueError) as e:
                logger.error(f"Failed to parse order book for {symbol}: {e}")
                return
        
        # Get tick size from symbol info (should be cached from warmup)
        symbol_info = await self.public_client.get_symbol_info(symbol)
        if not symbol_info or not symbol_info.price_filter:
            logger.error(f"Failed to fetch symbol info for {symbol}")
            return
        
        tick_size = symbol_info.price_filter.tick_size
        logger.info(f"Tick size fetched: {tick_size}")
        
        tp_desc = f"{tp_percent}%" if tp_percent is not None else "None"
        logger.info(
            f"Starting trade execution - Symbol: {symbol}, Side: {side}, "
            f"Accounts: {len(accounts_data)}, Bid: {best_bid}, Ask: {best_ask}, "
            f"Tick Size: {tick_size}, TP: {tp_desc}, SL: {sl_percent}%, "
            f"Ticks Distance: {ticks_distance}"
        )
        
        # Prepare account configurations
        account_configs = []
        quantities = {}
        
        for i, acc in enumerate(accounts_data, 1):
            config = AccountConfig(
                id=acc["id"],
                api_key=acc["api_key"],
                api_secret=acc["api_secret"],
                simulation=acc.get("simulation", False)
            )
            account_configs.append(config)
            quantities[acc["id"]] = Decimal(str(acc["quantity"]))
            
            # Log account setup (sanitized)
            logger.info(
                f"Account {i}/{len(accounts_data)} configured - "
                f"ID: {acc['id']}, Quantity: {acc['quantity']}, "
                f"Simulation: {acc.get('simulation', False)}"
            )
        
        logger.info(f"Initiating parallel trade execution for {len(account_configs)} accounts...")
        
        # Execute trades in parallel using AccountPool
        async with AccountPool(account_configs) as pool:
            
            tasks = []
            for acc_config in account_configs:
                client = pool.get_client(acc_config.id)
                if not client:
                    logger.warning(f"Client not found for account {acc_config.id}")
                    continue
                    
                qty = quantities[acc_config.id]
                
                logger.debug(
                    f"Creating trade task for account {acc_config.id} - "
                    f"Symbol: {symbol}, Side: {side}, Qty: {qty}"
                )
                
                task = create_trade(
                    client=client,
                    symbol=symbol,
                    side=side,
                    quantity=qty,
                    best_bid=best_bid,
                    best_ask=best_ask,
                    tick_size=tick_size,
                    tp_percent=tp_percent,
                    sl_percent=sl_percent,
                    ticks_distance=ticks_distance
                )
                tasks.append(task)
            
            logger.info(f"Executing {len(tasks)} trade tasks in parallel...")
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Log results
            logger.info("Trade execution completed. Processing results...")
            success_count = 0
            failed_count = 0
            
            for i, res in enumerate(results):
                acc_id = account_configs[i].id
                
                if isinstance(res, Exception):
                    failed_count += 1
                    logger.error(
                        f"Trade FAILED for account {acc_id} - Error: {type(res).__name__}: {res}",
                        exc_info=res
                    )
                else:
                    if res.status.value in ["active", "entry_filled", "entry_placed"]:
                        success_count += 1
                        logger.info(
                            f"Trade SUCCESS for account {acc_id} - "
                            f"Trade ID: {res.trade_id}, Status: {res.status.value}, "
                            f"Entry Order ID: {res.entry_order.order_id if res.entry_order else 'N/A'}"
                        )
                        
                        # Log order details if available
                        if res.entry_order:
                            logger.info(
                                f"  Entry order placed - Account: {acc_id}, "
                                f"Order ID: {res.entry_order.order_id}, "
                                f"Price: {res.entry_order.price}, "
                                f"Size: {res.entry_order.size}"
                            )
                        if res.take_profit_order:
                            logger.info(
                                f"  TP order placed - Account: {acc_id}, "
                                f"Order ID: {res.take_profit_order.order_id}, "
                                f"Price: {res.take_profit_order.price}"
                            )
                        if res.stop_loss_order:
                            logger.info(
                                f"  SL order placed - Account: {acc_id}, "
                                f"Order ID: {res.stop_loss_order.order_id}, "
                                f"Price: {res.stop_loss_order.price}"
                            )
                    else:
                        failed_count += 1
                        logger.warning(
                            f"Trade INCOMPLETE for account {acc_id} - "
                            f"Trade ID: {res.trade_id}, Status: {res.status.value}"
                        )
                        
            logger.info(
                f"Batch execution summary - Symbol: {symbol}, Side: {side}, "
                f"Total: {len(account_configs)}, Success: {success_count}, Failed: {failed_count}"
            )


