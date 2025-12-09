"""
Account WebSocket - Per-account WebSocket client for position/order tracking.

This module provides WebSocket connectivity for private user data streams,
handling ACCOUNT_UPDATE and ORDER_TRADE_UPDATE events for real-time
position and order tracking.

Reference: Asterdex User Data Stream API
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, Optional, Callable, Any

import aiohttp

from .auth import ApiCredentials, AsterSigner
from .constants import DEFAULT_BASE_URL
from .models.signal_models import PositionState

logger = logging.getLogger(__name__)


# User Data Stream WebSocket URL
USER_DATA_WS_URL = "wss://fstream.asterdex.com/ws"


@dataclass
class OrderUpdate:
    """Represents an order update from WebSocket."""
    order_id: int
    symbol: str
    side: str
    order_type: str
    status: str
    price: Decimal
    quantity: Decimal
    filled_quantity: Decimal
    average_price: Decimal
    realized_profit: Decimal
    is_maker: bool
    position_side: str


class AccountWebSocket:
    """
    WebSocket client for account position/order updates.
    
    Connects to user data stream and maintains real-time position state.
    Each account needs its own WebSocket connection.
    """

    def __init__(
        self,
        account_id: str,
        api_key: str,
        api_secret: str,
        base_url: str = DEFAULT_BASE_URL,
        on_position_update: Optional[Callable[[str, PositionState], None]] = None,
        on_order_update: Optional[Callable[[str, OrderUpdate], None]] = None,
    ):
        """
        Initialize account WebSocket.
        
        Args:
            account_id: Unique identifier for this account
            api_key: API key for authentication
            api_secret: API secret for authentication
            base_url: REST API base URL for listenKey management
            on_position_update: Callback for position updates
            on_order_update: Callback for order updates
        """
        self.account_id = account_id
        self.credentials = ApiCredentials(api_key=api_key, api_secret=api_secret)
        self.signer = AsterSigner(self.credentials)
        self.base_url = base_url
        
        self.on_position_update = on_position_update
        self.on_order_update = on_order_update
        
        self.running = False
        self.ws_task: Optional[asyncio.Task] = None
        self.keepalive_task: Optional[asyncio.Task] = None
        self.listen_key: Optional[str] = None
        self.session: Optional[aiohttp.ClientSession] = None
        
        # Position cache: symbol -> PositionState
        self.positions: Dict[str, PositionState] = {}
        
        # Track pre-existing positions as read-only
        self._initialized = False

    async def start(self):
        """Start the WebSocket connection."""
        if self.running:
            return
        
        self.running = True
        self.session = aiohttp.ClientSession()
        
        # Create listen key
        self.listen_key = await self._create_listen_key()
        if not self.listen_key:
            logger.error(f"[{self.account_id}] Failed to create listen key")
            self.running = False
            return
        
        logger.info(f"[{self.account_id}] Created listen key: {self.listen_key[:8]}...")
        
        # Start WebSocket loop
        self.ws_task = asyncio.create_task(self._ws_loop())
        
        # Start keepalive task (ping listen key every 30 minutes)
        self.keepalive_task = asyncio.create_task(self._keepalive_loop())
        
        logger.info(f"[{self.account_id}] Account WebSocket started")

    async def stop(self):
        """Stop the WebSocket connection."""
        self.running = False
        
        # Cancel tasks
        if self.keepalive_task:
            self.keepalive_task.cancel()
            try:
                await self.keepalive_task
            except asyncio.CancelledError:
                pass
        
        if self.ws_task:
            self.ws_task.cancel()
            try:
                await self.ws_task
            except asyncio.CancelledError:
                pass
        
        # Close listen key
        if self.listen_key and self.session:
            await self._delete_listen_key()
        
        # Close session
        if self.session:
            await self.session.close()
            self.session = None
        
        logger.info(f"[{self.account_id}] Account WebSocket stopped")

    async def _create_listen_key(self) -> Optional[str]:
        """Create a new listen key via REST API."""
        try:
            url = f"{self.base_url}/fapi/v1/listenKey"
            headers = self.signer.get_auth_headers()
            
            async with self.session.post(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("listenKey")
                else:
                    error = await resp.text()
                    logger.error(f"[{self.account_id}] Failed to create listen key: {error}")
                    return None
        except Exception as e:
            logger.error(f"[{self.account_id}] Error creating listen key: {e}")
            return None

    async def _keepalive_listen_key(self):
        """Keep listen key alive via PUT request."""
        try:
            url = f"{self.base_url}/fapi/v1/listenKey"
            headers = self.signer.get_auth_headers()
            
            async with self.session.put(url, headers=headers) as resp:
                if resp.status == 200:
                    logger.debug(f"[{self.account_id}] Listen key keepalive success")
                else:
                    error = await resp.text()
                    logger.warning(f"[{self.account_id}] Listen key keepalive failed: {error}")
        except Exception as e:
            logger.error(f"[{self.account_id}] Error in listen key keepalive: {e}")

    async def _delete_listen_key(self):
        """Delete listen key via DELETE request."""
        try:
            url = f"{self.base_url}/fapi/v1/listenKey"
            headers = self.signer.get_auth_headers()
            
            async with self.session.delete(url, headers=headers) as resp:
                if resp.status == 200:
                    logger.debug(f"[{self.account_id}] Listen key deleted")
                else:
                    error = await resp.text()
                    logger.warning(f"[{self.account_id}] Failed to delete listen key: {error}")
        except Exception as e:
            logger.error(f"[{self.account_id}] Error deleting listen key: {e}")

    async def _keepalive_loop(self):
        """Periodic keepalive for listen key (every 30 minutes)."""
        while self.running:
            await asyncio.sleep(30 * 60)  # 30 minutes
            if self.running:
                await self._keepalive_listen_key()

    async def _ws_loop(self):
        """Main WebSocket loop."""
        while self.running:
            try:
                ws_url = f"{USER_DATA_WS_URL}/{self.listen_key}"
                
                async with self.session.ws_connect(
                    ws_url,
                    heartbeat=60,
                    timeout=aiohttp.ClientTimeout(total=None, connect=10),
                ) as ws:
                    logger.info(f"[{self.account_id}] Connected to user data stream")
                    
                    async for msg in ws:
                        if not self.running:
                            break
                        
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            try:
                                data = json.loads(msg.data)
                                await self._process_message(data)
                            except Exception as e:
                                logger.error(f"[{self.account_id}] Error processing message: {e}")
                        elif msg.type == aiohttp.WSMsgType.ERROR:
                            logger.error(f"[{self.account_id}] WebSocket error: {ws.exception()}")
                            break
                        elif msg.type == aiohttp.WSMsgType.CLOSE:
                            logger.warning(f"[{self.account_id}] WebSocket closed")
                            break
                            
            except Exception as e:
                logger.error(f"[{self.account_id}] WebSocket connection error: {e}")
            
            if self.running:
                logger.info(f"[{self.account_id}] Reconnecting in 5 seconds...")
                await asyncio.sleep(5)

    async def _process_message(self, data: Dict[str, Any]):
        """Process incoming WebSocket message."""
        event_type = data.get("e")
        
        if event_type == "ACCOUNT_UPDATE":
            await self._handle_account_update(data)
        elif event_type == "ORDER_TRADE_UPDATE":
            await self._handle_order_update(data)
        elif event_type == "listenKeyExpired":
            logger.warning(f"[{self.account_id}] Listen key expired, reconnecting...")
            self.listen_key = await self._create_listen_key()
        else:
            logger.debug(f"[{self.account_id}] Unknown event type: {event_type}")

    async def _handle_account_update(self, data: Dict[str, Any]):
        """
        Handle ACCOUNT_UPDATE event.
        
        Updates position cache based on position data in the event.
        """
        update_data = data.get("a", {})
        positions_data = update_data.get("P", [])
        
        for pos in positions_data:
            symbol = pos.get("s")
            position_amount = Decimal(str(pos.get("pa", "0")))
            entry_price = Decimal(str(pos.get("ep", "0")))
            position_side = pos.get("ps", "BOTH")  # LONG, SHORT, or BOTH
            
            if position_amount == 0:
                # Position closed
                if symbol in self.positions:
                    logger.info(f"[{self.account_id}] Position closed: {symbol}")
                    del self.positions[symbol]
                    if self.on_position_update:
                        # Send None to indicate closed position
                        self.on_position_update(self.account_id, None)
            else:
                # Determine side from amount or position_side field
                if position_side in ("LONG", "SHORT"):
                    side = position_side
                else:
                    side = "LONG" if position_amount > 0 else "SHORT"
                
                # Check if this is a new position (for read-only flag)
                is_read_only = not self._initialized and symbol not in self.positions
                
                position = PositionState(
                    symbol=symbol,
                    account_id=self.account_id,
                    side=side,
                    quantity=abs(position_amount),
                    entry_price=entry_price,
                    is_read_only=is_read_only,
                )
                
                self.positions[symbol] = position
                
                logger.info(
                    f"[{self.account_id}] Position updated: {symbol} {side} "
                    f"{abs(position_amount)} @ {entry_price}"
                    + (" [READ-ONLY]" if is_read_only else "")
                )
                
                if self.on_position_update:
                    self.on_position_update(self.account_id, position)
        
        # After first update, mark as initialized
        if not self._initialized:
            self._initialized = True
            logger.info(f"[{self.account_id}] Position state initialized")

    async def _handle_order_update(self, data: Dict[str, Any]):
        """Handle ORDER_TRADE_UPDATE event."""
        order_data = data.get("o", {})
        
        order_update = OrderUpdate(
            order_id=order_data.get("i", 0),
            symbol=order_data.get("s", ""),
            side=order_data.get("S", ""),
            order_type=order_data.get("o", ""),
            status=order_data.get("X", ""),
            price=Decimal(str(order_data.get("p", "0"))),
            quantity=Decimal(str(order_data.get("q", "0"))),
            filled_quantity=Decimal(str(order_data.get("z", "0"))),
            average_price=Decimal(str(order_data.get("ap", "0"))),
            realized_profit=Decimal(str(order_data.get("rp", "0"))),
            is_maker=order_data.get("m", False),
            position_side=order_data.get("ps", "BOTH"),
        )
        
        logger.info(
            f"[{self.account_id}] Order update: {order_update.symbol} "
            f"{order_update.side} {order_update.status} "
            f"filled={order_update.filled_quantity}/{order_update.quantity}"
        )
        
        if self.on_order_update:
            self.on_order_update(self.account_id, order_update)

    def get_position(self, symbol: str) -> Optional[PositionState]:
        """
        Get current position for a symbol.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            PositionState or None if no position
        """
        return self.positions.get(symbol)

    def has_position(self, symbol: str) -> bool:
        """Check if there's an open position for symbol."""
        return symbol in self.positions

    def get_all_positions(self) -> Dict[str, PositionState]:
        """Get all open positions."""
        return self.positions.copy()

    def clear_position(self, symbol: str):
        """Clear position from local cache (e.g., after manual close)."""
        if symbol in self.positions:
            del self.positions[symbol]

    def mark_position_managed(self, symbol: str):
        """Mark a position as bot-managed (not read-only)."""
        if symbol in self.positions:
            self.positions[symbol].is_read_only = False
