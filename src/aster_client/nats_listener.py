"""
NATS Trade Listener - Listens for trade commands via NATS and executes them in parallel.

Location: src/aster_client/nats_listener.py
Purpose: Process trade commands from NATS and execute on multiple accounts
Relevant files: account_client.py, account_pool.py, bbo.py, trades.py

This module provides the NATSTradeListener class which subscribes to a NATS subject,
receives trade configuration messages, and executes trades across multiple accounts.
Accounts are loaded from a YAML config file at startup.

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
       "ticks_distance": 0         # Optional (default: 0), BBO offset in ticks
   }

3. Generic Order Message
   Used to place single orders (Limit, Market, BBO) without TP/SL lifecycle.
   {
       "type": "order",
       "symbol": "BTCUSDT",
       "side": "buy",
       "order_type": "limit",      # "limit", "market", "bbo", etc.
       "price": 50000.0,           # Required for limit orders
       "ticks_distance": 0,        # Required for BBO orders (default: 0)
       "reduce_only": false,       # Optional
       "time_in_force": "gtc",     # Optional
       "position_side": "LONG"     # Optional (for hedge mode)
   }

4. Close Position Message
   Used to close all positions for a symbol with BBO order and cleanup TP/SL orders.
   {
       "type": "close_position",
       "symbol": "BTCUSDT",
       "ticks_distance": 0         # Optional (default: 0 for aggressive close)
   }
"""

import asyncio
import hashlib
import json
import logging
import os
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

from nats.aio.client import Client as NATS

from .account_client import AsterClient
from .account_pool import AccountPool, AccountConfig
from .models import ConnectionConfig
from .public_client import AsterPublicClient
from .trades import create_trade
from .bbo import BBOPriceCalculator

logger = logging.getLogger(__name__)


class NATSTradeListener:
    """
    Listens for trade commands via NATS and executes them.
    
    Attributes:
        nats_url: The NATS URL to connect to (e.g., "nats://localhost:4222")
        subject: The subject to subscribe to (default: "orders")
        nc: NATS client
    """
    
    def __init__(
        self, 
        nats_url: Optional[str] = None, 
        subject: str = "orders", 
        log_dir: str = "logs",
        accounts: Optional[List[Dict[str, Any]]] = None,
        allowed_symbols: Optional[List[str]] = None,
    ):
        """
        Initialize the NATS listener.
        
        Args:
            nats_url: URL of the NATS server. If None, uses NATS_URL env var or default.
            subject: Subject to subscribe to
            log_dir: Directory to store session log files (default: "logs")
            accounts: List of account dicts with id, api_key, api_secret, quantity, simulation.
                      If provided, these accounts are used for all trade messages.
            allowed_symbols: List of symbols to process. If empty/None, all symbols are accepted.
        """
        if nats_url is None:
            nats_url = os.environ.get("NATS_URL", "nats://localhost:4222")
            
        self.nats_url = nats_url
        self.subject = subject
        self.nc = NATS()
        self.subscription = None
        self.running = False
        self.log_dir = log_dir
        self.file_handler = None
        
        # Symbol filter - only process these symbols (empty = all)
        self._allowed_symbols = set(s.upper() for s in (allowed_symbols or []))
        
        # Accounts loaded from config (used if not specified in message)
        self._config_accounts = accounts or []
        
        # Initialize public client for market data (shared instance via singleton)
        # auto_warmup=False because we'll manually control warmup timing in start()
        self.public_client = AsterPublicClient(auto_warmup=False)
        
        # Initialize BBO calculator (singleton)
        self.bbo_calculator = BBOPriceCalculator()
        
        # Persistent client cache: key = (account_id, credentials_hash)
        # Clients are reused across messages for low-latency execution
        self._clients: Dict[str, AsterClient] = {}
        self._clients_lock = asyncio.Lock()
        
        # Cache statistics for monitoring
        self._cache_hits = 0
        self._cache_misses = 0
        
        # Set up session-specific log file
        self._setup_session_logging()
        
        if self._config_accounts:
            logger.info(f"Loaded {len(self._config_accounts)} accounts from config")
        
        if self._allowed_symbols:
            logger.info(f"Symbol filter active: {', '.join(sorted(self._allowed_symbols))}")
        
    async def start(self):
        """Start listening for messages."""
        logger.info(f"Connecting to NATS server at {self.nats_url}...")
        await self.nc.connect(self.nats_url)
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
        
        logger.info(f"Listening for messages on subject '{self.subject}'...")
        
        # Define message handler
        async def message_handler(msg):
            try:
                payload = msg.data.decode()
                message = json.loads(payload)
                logger.info(f"Received NATS message - Subject: '{self.subject}', Payload size: {len(payload)} bytes")
                
                # Log sanitized message details
                self._log_message_received(message)
                
                # Process in background to not block receiving new messages
                asyncio.create_task(self.process_message(message))
                
            except json.JSONDecodeError as e:
                logger.error(f"Failed to decode JSON message: {e}. Payload preview: {payload[:100]}")
            except Exception as e:
                logger.error(f"Error processing NATS message: {e}", exc_info=True)
        
        # Subscribe to NATS subject
        self.subscription = await self.nc.subscribe(self.subject, cb=message_handler)
        
        # Keep running until stopped
        while self.running:
            await asyncio.sleep(1)
                
    async def stop(self):
        """Stop the listener."""
        self.running = False
        
        # Close NATS connection
        if self.subscription:
            await self.subscription.unsubscribe()
        await self.nc.close()
        
        # Stop BBO WebSocket client
        await self.bbo_calculator.stop()
        
        # Close public client session
        await self.public_client.close()
        
        # Close all cached account clients
        await self._cleanup_clients()
        
        logger.info("NATS listener stopped")
        
        # Clean up file handler
        if self.file_handler:
            logger.removeHandler(self.file_handler)
            self.file_handler.close()
            self.file_handler = None
    
    async def _cleanup_clients(self):
        """Close all cached account clients and release resources."""
        async with self._clients_lock:
            close_tasks = [client.close() for client in self._clients.values()]
            if close_tasks:
                await asyncio.gather(*close_tasks, return_exceptions=True)
                logger.info(f"Closed {len(self._clients)} cached account clients")
            self._clients.clear()
    
    def _get_client_cache_key(self, account_id: str, api_key: str, api_secret: str) -> str:
        """
        Generate a cache key for account client lookup.
        
        Uses account_id + hash of credentials to detect credential changes.
        """
        # Hash credentials to detect changes without storing them in the key
        cred_hash = hashlib.sha256(f"{api_key}:{api_secret}".encode()).hexdigest()[:16]
        return f"{account_id}:{cred_hash}"
    
    async def _get_or_create_client(
        self, 
        account_id: str, 
        api_key: str, 
        api_secret: str, 
        simulation: bool = False
    ) -> AsterClient:
        """
        Get an existing client or create a new one with pre-warmed session.
        
        Clients are cached by (account_id, credentials_hash) to:
        1. Reuse TCP connections for low-latency requests
        2. Detect credential changes and create new clients if needed
        
        Args:
            account_id: Unique account identifier
            api_key: API key for authentication
            api_secret: API secret for authentication  
            simulation: Enable simulation/testnet mode
            
        Returns:
            AsterClient instance with warmed session
        """
        cache_key = self._get_client_cache_key(account_id, api_key, api_secret)
        
        async with self._clients_lock:
            # Return cached client if exists
            if cache_key in self._clients:
                self._cache_hits += 1
                return self._clients[cache_key]
            
            # Cache miss - create new client
            self._cache_misses += 1
            
            config = ConnectionConfig(
                api_key=api_key,
                api_secret=api_secret,
                simulation=simulation,
            )
            client = AsterClient(config)
            
            # Pre-warm the session (creates aiohttp.ClientSession)
            await client._session_manager.create_session()
            
            # Cache the client
            self._clients[cache_key] = client
            logger.info(f"Created and cached client for account {account_id} (cache size: {len(self._clients)})")
            
            return client
    
    @property
    def cache_size(self) -> int:
        """Get the current number of cached clients."""
        return len(self._clients)
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics for monitoring.
        
        Returns:
            Dictionary with cache_size, hits, misses, and hit_rate
        """
        total = self._cache_hits + self._cache_misses
        hit_rate = (self._cache_hits / total * 100) if total > 0 else 0.0
        
        return {
            "cache_size": len(self._clients),
            "hits": self._cache_hits,
            "misses": self._cache_misses,
            "total_requests": total,
            "hit_rate_percent": round(hit_rate, 2),
        }
    
    async def prewarm_accounts(self, accounts: List[Dict[str, Any]]) -> int:
        """
        Pre-warm account clients before any messages arrive.
        
        Call this at startup with known accounts to eliminate first-message latency.
        Sessions will be created and cached for all accounts.
        
        Args:
            accounts: List of account dicts with id, api_key, api_secret, simulation (optional)
                      Same format as accounts in ZMQ messages.
        
        Returns:
            Number of accounts successfully warmed
        
        Example:
            accounts = [
                {"id": "acc1", "api_key": "key1", "api_secret": "secret1"},
                {"id": "acc2", "api_key": "key2", "api_secret": "secret2", "simulation": True},
            ]
            warmed = await listener.prewarm_accounts(accounts)
            logger.info(f"Pre-warmed {warmed} accounts")
        """
        warmed = 0
        for acc in accounts:
            try:
                await self._get_or_create_client(
                    account_id=acc["id"],
                    api_key=acc["api_key"],
                    api_secret=acc["api_secret"],
                    simulation=acc.get("simulation", False)
                )
                warmed += 1
                logger.debug(f"Pre-warmed account {acc['id']}")
            except Exception as e:
                logger.error(f"Failed to pre-warm account {acc['id']}: {e}")
        
        logger.info(f"Pre-warmed {warmed}/{len(accounts)} accounts (cache size: {self.cache_size})")
        return warmed
    
    def _setup_session_logging(self):
        """
        Set up a session-specific log file for this listener instance.
        Log files are named with timestamp: nats_listener_YYYYMMDD_HHMMSS.log
        """
        # Create logs directory if it doesn't exist
        log_path = Path(self.log_dir)
        log_path.mkdir(parents=True, exist_ok=True)
        
        # Generate unique log filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_filename = f"nats_listener_{timestamp}.log"
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
                f"Ticks Distance: {message.get('ticks_distance', 0)}"
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
            
            # Check symbol filter (skip heartbeats which have no symbol)
            symbol = message.get("symbol", "").upper().replace("_", "").replace("/", "")
            if self._allowed_symbols and symbol not in self._allowed_symbols:
                logger.debug(f"Skipping message for {symbol} (not in allowed symbols)")
                return
            
            if msg_type == "order":
                await self._process_order_message(message)
                return
            
            elif msg_type == "close_position":
                await self._process_close_position_message(message)
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
        
        # Fall back to config accounts if none in message
        if not accounts_data:
            accounts_data = self._config_accounts
        
        if not accounts_data:
            logger.warning("No accounts provided in order message and no accounts loaded from config")
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

        # Get or create cached clients for each account (sessions pre-warmed)
        tasks = []
        account_ids = []
        
        for acc in accounts_data:
            client = await self._get_or_create_client(
                account_id=acc["id"],
                api_key=acc["api_key"],
                api_secret=acc["api_secret"],
                simulation=acc.get("simulation", False)
            )
            
            qty = Decimal(str(acc["quantity"]))
            
            if order_type.lower() == "bbo":
                # Special handling for BBO
                ticks_distance = int(message.get("ticks_distance", 0))
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
            account_ids.append(acc["id"])

        # Execute all orders in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Log results
        success = 0
        failed = 0
        for i, res in enumerate(results):
            acc_id = account_ids[i]
            if isinstance(res, Exception):
                failed += 1
                logger.error(f"Order failed for {acc_id}: {res}")
            else:
                success += 1
                logger.info(f"Order success for {acc_id}: ID={res.order_id}, Status={res.status}")
        
        logger.info(f"Order batch completed: {success} ok, {failed} failed")

    async def _process_close_position_message(self, message: Dict[str, Any]):
        """
        Process a close position message.
        
        Closes all positions for a symbol with BBO order and cleans up TP/SL orders.
        """
        symbol = message["symbol"]
        ticks_distance = int(message.get("ticks_distance", 0))
        accounts_data = message.get("accounts", [])
        
        # Fall back to config accounts if none in message
        if not accounts_data:
            accounts_data = self._config_accounts
        
        if not accounts_data:
            logger.warning("No accounts provided in close_position message and no accounts loaded from config")
            return
        
        logger.info(
            f"🔄 Processing close_position message - Symbol: {symbol}, "
            f"Accounts: {len(accounts_data)}, Ticks Distance: {ticks_distance}"
        )
        
        # Fetch market data
        # Get tick size from symbol info
        symbol_info = await self.public_client.get_symbol_info(symbol)
        if not symbol_info or not symbol_info.price_filter:
            logger.error(f"Failed to fetch symbol info for {symbol}")
            return
        
        tick_size = symbol_info.price_filter.tick_size
        
        # Get BBO prices
        best_bid = None
        best_ask = None
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
                logger.info(f"Using REST BBO for {symbol}: Bid=${best_bid}, Ask=${best_ask}")
            else:
                logger.error(f"Failed to fetch order book for {symbol}")
                return
        
        # Get or create cached clients for each account (sessions pre-warmed)
        tasks = []
        account_ids = []
        
        for acc in accounts_data:
            client = await self._get_or_create_client(
                account_id=acc["id"],
                api_key=acc["api_key"],
                api_secret=acc["api_secret"],
                simulation=acc.get("simulation", False)
            )
            
            task = client.close_position_for_symbol(
                symbol=symbol,
                tick_size=tick_size,
                best_bid=best_bid,
                best_ask=best_ask,
                ticks_distance=ticks_distance,
            )
            tasks.append(task)
            account_ids.append(acc["id"])
        
        # Execute close positions in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Log summary
        success_count = 0
        failed_count = 0
        total_cancelled = 0
        total_closed = 0
        
        for i, res in enumerate(results):
            acc_id = account_ids[i]
            if isinstance(res, Exception):
                failed_count += 1
                logger.error(f"Close position failed for {acc_id}: {res}")
            elif res.success:
                success_count += 1
                total_cancelled += res.cancelled_orders_count
                if res.close_order:
                    total_closed += 1
                    logger.info(
                        f"Position closed for {acc_id}: "
                        f"Qty={res.position_quantity}, "
                        f"Cancelled={res.cancelled_orders_count} orders"
                    )
                else:
                    logger.info(
                        f"No position to close for {acc_id}, "
                        f"cancelled {res.cancelled_orders_count} orders"
                    )
            else:
                failed_count += 1
                logger.error(f"Close position failed for {acc_id}: {res.error}")
        
        logger.info(
            f"✅ Close position batch completed - Symbol: {symbol}, "
            f"Accounts: {len(results)}, Success: {success_count}, Failed: {failed_count}, "
            f"Positions Closed: {total_closed}, Orders Cancelled: {total_cancelled}"
        )

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
        ticks_distance = int(message.get("ticks_distance", 0))  # At bid1/ask1 (safe with GTX)
        
        accounts_data = message.get("accounts", [])
        
        # Fall back to config accounts if none in message
        if not accounts_data:
            accounts_data = self._config_accounts
        
        if not accounts_data:
            logger.warning("No accounts provided in message and no accounts loaded from config")
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
        
        # Get default quantity from message (applies to all accounts if not per-account)
        default_quantity = message.get("quantity")
        
        # Get or create cached clients for each account (sessions pre-warmed)
        tasks = []
        account_ids = []
        
        for i, acc in enumerate(accounts_data, 1):
            # Get quantity: message > account config > error
            qty_raw = acc.get("quantity") or default_quantity
            if not qty_raw:
                logger.error(f"No quantity specified for account {acc['id']} - skipping")
                continue
            
            qty = Decimal(str(qty_raw))
            
            # Log account setup (sanitized)
            logger.info(
                f"Account {i}/{len(accounts_data)} configured - "
                f"ID: {acc['id']}, Quantity: {qty}, "
                f"Simulation: {acc.get('simulation', False)}"
            )
            
            client = await self._get_or_create_client(
                account_id=acc["id"],
                api_key=acc["api_key"],
                api_secret=acc["api_secret"],
                simulation=acc.get("simulation", False)
            )
            
            logger.debug(
                f"Creating trade task for account {acc['id']} - "
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
                tp_percents=[tp_percent] if tp_percent is not None else [],
                sl_percent=sl_percent,
                ticks_distance=ticks_distance
            )
            tasks.append(task)
            account_ids.append(acc["id"])
        
        logger.info(f"Executing {len(tasks)} trade tasks in parallel...")
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Log results
        logger.info("Trade execution completed. Processing results...")
        success_count = 0
        failed_count = 0
        
        for i, res in enumerate(results):
            acc_id = account_ids[i]
            
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
                    if res.take_profit_orders:
                        for tp_order in res.take_profit_orders:
                            logger.info(
                                f"  TP order placed - Account: {acc_id}, "
                                f"Order ID: {tp_order.order_id}, "
                                f"Price: {tp_order.price}"
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
            f"Total: {len(account_ids)}, Success: {success_count}, Failed: {failed_count}"
        )


# Backward-compatible alias
ZMQTradeListener = NATSTradeListener
