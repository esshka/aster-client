"""
ZMQ Trade Listener - Listens for trade commands via ZeroMQ and executes them in parallel.

This module provides the ZMQTradeListener class which subscribes to a ZeroMQ topic,
receives trade configuration messages, and executes trades across multiple accounts
using the AccountPool and trades modules.
"""

import asyncio
import json
import logging
from decimal import Decimal
from typing import Dict, Any, Optional, List

import zmq
import zmq.asyncio

from .account_pool import AccountPool, AccountConfig
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
    
    def __init__(self, zmq_url: str, topic: str = ""):
        """
        Initialize the ZMQ listener.
        
        Args:
            zmq_url: URL of the ZMQ publisher
            topic: Topic to subscribe to (empty string for all topics)
        """
        self.zmq_url = zmq_url
        self.topic = topic
        self.ctx = zmq.asyncio.Context()
        self.socket = self.ctx.socket(zmq.SUB)
        self.running = False
        
    async def start(self):
        """Start listening for messages."""
        logger.info(f"Connecting to ZMQ publisher at {self.zmq_url}...")
        self.socket.connect(self.zmq_url)
        self.socket.subscribe(self.topic)
        self.running = True
        
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
                    logger.info(f"Received trade command for {message.get('symbol', 'unknown')}")
                    
                    # Process in background to not block receiving new messages
                    asyncio.create_task(self.process_message(message))
                    
                except json.JSONDecodeError:
                    logger.error(f"Failed to decode JSON message: {payload}")
                    
            except asyncio.CancelledError:
                logger.info("ZMQ listener cancelled")
                break
            except Exception as e:
                logger.error(f"Error in ZMQ loop: {e}")
                await asyncio.sleep(1)  # Prevent tight loop on error
                
    async def stop(self):
        """Stop the listener."""
        self.running = False
        self.socket.close()
        self.ctx.term()
        logger.info("ZMQ listener stopped")

    async def process_message(self, message: Dict[str, Any]):
        """
        Process a received trade command message.
        
        Args:
            message: Decoded JSON message containing trade details and accounts
        """
        try:
            # Extract common trade parameters
            symbol = message["symbol"]
            side = message["side"]
            market_price = Decimal(str(message["market_price"]))
            tick_size = Decimal(str(message["tick_size"]))
            tp_percent = float(message["tp_percent"])
            sl_percent = float(message["sl_percent"])
            ticks_distance = int(message.get("ticks_distance", 1))
            
            accounts_data = message.get("accounts", [])
            if not accounts_data:
                logger.warning("No accounts provided in message")
                return
                
            logger.info(f"Processing trade for {len(accounts_data)} accounts on {symbol}")
            
            # Prepare account configurations
            account_configs = []
            quantities = {}
            
            for acc in accounts_data:
                config = AccountConfig(
                    id=acc["id"],
                    api_key=acc["api_key"],
                    api_secret=acc["api_secret"],
                    simulation=acc.get("simulation", False)
                )
                account_configs.append(config)
                quantities[acc["id"]] = Decimal(str(acc["quantity"]))
            
            # Execute trades in parallel using AccountPool
            async with AccountPool(account_configs) as pool:
                
                tasks = []
                for acc_config in account_configs:
                    client = pool.get_client(acc_config.id)
                    if not client:
                        continue
                        
                    qty = quantities[acc_config.id]
                    
                    task = create_trade(
                        client=client,
                        symbol=symbol,
                        side=side,
                        quantity=qty,
                        market_price=market_price,
                        tick_size=tick_size,
                        tp_percent=tp_percent,
                        sl_percent=sl_percent,
                        ticks_distance=ticks_distance
                    )
                    tasks.append(task)
                
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Log results
                success_count = 0
                for i, res in enumerate(results):
                    acc_id = account_configs[i].id
                    if isinstance(res, Exception):
                        logger.error(f"Trade failed for {acc_id}: {res}")
                    else:
                        if res.status.value in ["active", "entry_filled", "entry_placed"]:
                            success_count += 1
                            logger.info(f"Trade initiated for {acc_id}: {res.trade_id}")
                        else:
                            logger.warning(f"Trade for {acc_id} ended with status: {res.status}")
                            
                logger.info(f"Batch execution completed. Success: {success_count}/{len(account_configs)}")

        except KeyError as e:
            logger.error(f"Missing required field in message: {e}")
        except Exception as e:
            logger.error(f"Error processing message: {e}")
