"""
ZMQ Trade Listener - Listens for trade commands via ZeroMQ and executes them in parallel.

This module provides the ZMQTradeListener class which subscribes to a ZeroMQ topic,
receives trade configuration messages, and executes trades across multiple accounts
using the AccountPool and trades modules.

Supported message types:
- heartbeat: Connection verification messages from the publisher
- trade: Trade execution commands with account details
"""

import asyncio
import json
import logging
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Dict, Any, Optional, List

import zmq
import zmq.asyncio

from .account_pool import AccountPool, AccountConfig
from .public_client import AsterPublicClient
from .trades import create_trade

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
    
    def __init__(self, zmq_url: str, topic: str = "", log_dir: str = "logs"):
        """
        Initialize the ZMQ listener.
        
        Args:
            zmq_url: URL of the ZMQ publisher
            topic: Topic to subscribe to (empty string for all topics)
            log_dir: Directory to store session log files (default: "logs")
        """
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
        
        # Set up session-specific log file
        self._setup_session_logging()
        
    async def start(self):
        """Start listening for messages."""
        logger.info(f"Connecting to ZMQ publisher at {self.zmq_url}...")
        self.socket.connect(self.zmq_url)
        self.socket.subscribe(self.topic)
        self.running = True
        
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
        
        # Log trade command details
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
            message: Decoded JSON message containing trade details and accounts
        """
        try:
            # Check if this is a heartbeat message
            msg_type = message.get("type", "trade")
            
            if msg_type == "heartbeat":
                # Heartbeat messages are already logged in _log_message_received
                # No further processing needed
                logger.debug("Heartbeat message processed successfully")
                return
            
            # Extract common trade parameters
            symbol = message["symbol"]
            side = message["side"]
            tp_percent = float(message["tp_percent"])
            sl_percent = float(message["sl_percent"])
            ticks_distance = int(message.get("ticks_distance", 1))
            
            accounts_data = message.get("accounts", [])
            if not accounts_data:
                logger.warning("No accounts provided in message")
                return
            
            # Fetch market data from exchange
            logger.info(f"Fetching market data for {symbol}...")
            
            # Get order book for best bid/ask
            # We use a small limit (5) to minimize data transfer while getting top of book
            order_book = await self.public_client.get_order_book(symbol, limit=5)
            if not order_book or "bids" not in order_book or "asks" not in order_book:
                logger.error(f"Failed to fetch order book for {symbol}")
                return
            
            # Extract best bid and ask
            # Bids are sorted desc, Asks are sorted asc
            # Format: [["price", "qty"], ...]
            try:
                best_bid = Decimal(order_book["bids"][0][0])
                best_ask = Decimal(order_book["asks"][0][0])
                logger.info(f"Market data fetched: Bid=${best_bid}, Ask=${best_ask}")
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
            
            logger.info(
                f"Starting trade execution - Symbol: {symbol}, Side: {side}, "
                f"Accounts: {len(accounts_data)}, Bid: {best_bid}, Ask: {best_ask}, "
                f"Tick Size: {tick_size}, TP: {tp_percent}%, SL: {sl_percent}%, "
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

        except KeyError as e:
            logger.error(f"Missing required field in message: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"Error processing message: {type(e).__name__}: {e}", exc_info=True)
