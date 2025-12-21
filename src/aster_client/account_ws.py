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
        allowed_symbols: Optional[set] = None,
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
            allowed_symbols: Set of symbols that are bot-managed (not read-only)
        """
        self.account_id = account_id
        self.credentials = ApiCredentials(api_key=api_key, api_secret=api_secret)
        self.signer = AsterSigner(self.credentials)
        self.base_url = base_url
        
        self.on_position_update = on_position_update
        self.on_order_update = on_order_update
        
        # Symbols that are bot-managed (positions for these are NOT read-only)
        self._allowed_symbols = allowed_symbols or set()
        
        self.running = False
        self.ws_task: Optional[asyncio.Task] = None
        self.keepalive_task: Optional[asyncio.Task] = None
        self.listen_key: Optional[str] = None
        self.session: Optional[aiohttp.ClientSession] = None
        
        # Position cache: symbol:side -> PositionState
        self.positions: Dict[str, PositionState] = {}
        
        # Track pre-existing positions as read-only
        self._initialized = False

    async def start(self):
        """Start the WebSocket connection."""
        if self.running:
            return
        
        self.running = True
        self.session = aiohttp.ClientSession()
        
        # Fetch existing positions via REST API before WebSocket starts
        await self._fetch_initial_positions()
        
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
    
    async def _fetch_initial_positions(self):
        """Fetch existing positions via REST API to populate cache."""
        try:
            import hashlib
            import hmac
            from urllib.parse import urlencode
            
            url = f"{self.base_url}/fapi/v2/positionRisk"
            
            # Generate signature the same way as http_client.py
            timestamp = str(int(time.time() * 1000))
            auth_params = {
                "timestamp": timestamp,
                "recvWindow": self.signer.recv_window,
            }
            
            # Create signature from sorted query string
            query_string = urlencode(sorted(auth_params.items()))
            signature = hmac.new(
                self.credentials.api_secret.encode(),
                query_string.encode(),
                hashlib.sha256,
            ).hexdigest()
            
            # Build params list with signature last (order matters!)
            params_list = sorted(auth_params.items())
            params_list.append(("signature", signature))
            
            headers = self.signer.get_auth_headers()
            
            async with self.session.get(url, params=params_list, headers=headers) as resp:
                if resp.status == 200:
                    positions = await resp.json()
                    for pos in positions:
                        symbol = pos.get("symbol")
                        position_amt = Decimal(str(pos.get("positionAmt", "0")))
                        entry_price = Decimal(str(pos.get("entryPrice", "0")))
                        position_side = pos.get("positionSide", "BOTH")
                        
                        if position_amt == 0:
                            continue  # No position
                        
                        # Determine side
                        if position_side in ("LONG", "SHORT"):
                            side = position_side
                        else:
                            side = "LONG" if position_amt > 0 else "SHORT"
                        
                        # Position key for hedge mode
                        position_key = f"{symbol}:{side}" if position_side in ("LONG", "SHORT") else symbol
                        
                        # Check if allowed symbol (not read-only)
                        is_read_only = symbol not in self._allowed_symbols
                        
                        position = PositionState(
                            symbol=symbol,
                            account_id=self.account_id,
                            side=side,
                            quantity=abs(position_amt),
                            entry_price=entry_price,
                            is_read_only=is_read_only,
                        )
                        
                        self.positions[position_key] = position
                        
                        logger.info(
                            f"[{self.account_id}] Initial position: {symbol} {side} "
                            f"{abs(position_amt)} @ {entry_price}"
                            + (" [READ-ONLY]" if is_read_only else "")
                        )
                        
                        # Notify listener
                        if self.on_position_update:
                            self.on_position_update(self.account_id, position)
                    
                    if not self.positions:
                        logger.info(f"[{self.account_id}] No open positions")
                    
                    # Mark as initialized after fetching
                    self._initialized = True
                else:
                    error = await resp.text()
                    logger.error(f"[{self.account_id}] Failed to fetch positions: {error}")
        except Exception as e:
            logger.error(f"[{self.account_id}] Error fetching initial positions: {e}")
        
        # Fetch open orders for allowed symbols
        await self._fetch_initial_orders()
    
    async def _fetch_initial_orders(self):
        """Fetch open orders via REST API and log them."""
        try:
            import hashlib
            import hmac
            from urllib.parse import urlencode
            
            # Fetch orders for each allowed symbol
            for symbol in self._allowed_symbols:
                url = f"{self.base_url}/fapi/v1/allOrders"
                
                # Generate signature
                timestamp = str(int(time.time() * 1000))
                auth_params = {
                    "symbol": symbol,
                    "timestamp": timestamp,
                    "recvWindow": self.signer.recv_window,
                    "limit": 100,
                }
                
                query_string = urlencode(sorted(auth_params.items()))
                signature = hmac.new(
                    self.credentials.api_secret.encode(),
                    query_string.encode(),
                    hashlib.sha256,
                ).hexdigest()
                
                params_list = sorted(auth_params.items())
                params_list.append(("signature", signature))
                
                headers = self.signer.get_auth_headers()
                
                async with self.session.get(url, params=params_list, headers=headers) as resp:
                    if resp.status == 200:
                        orders = await resp.json()
                        # Filter for active orders only (NEW status)
                        active_orders = [o for o in orders if o.get("status") == "NEW"]
                        
                        if active_orders:
                            logger.info(f"[{self.account_id}] Open orders for {symbol}:")
                            for order in active_orders:
                                order_type = order.get("type", "UNKNOWN")
                                side = order.get("side", "")
                                price = order.get("price") or order.get("stopPrice", "0")
                                qty = order.get("origQty", "0")
                                position_side = order.get("positionSide", "BOTH")
                                order_id = order.get("orderId")
                                
                                logger.info(
                                    f"  [{order_id}] {order_type} {side} {qty} @ {price} "
                                    f"(positionSide={position_side})"
                                )
                        else:
                            logger.info(f"[{self.account_id}] No open orders for {symbol}")
                    else:
                        error = await resp.text()
                        logger.error(f"[{self.account_id}] Failed to fetch orders for {symbol}: {error}")
        except Exception as e:
            logger.error(f"[{self.account_id}] Error fetching initial orders: {e}")

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
            
            # Use symbol:side as key for hedge mode to avoid cross-interference
            position_key = f"{symbol}:{position_side}" if position_side in ("LONG", "SHORT") else symbol
            
            if position_amount == 0:
                # Position closed - only if we're tracking this specific side
                if position_key in self.positions:
                    closed_position = self.positions[position_key]
                    logger.info(f"[{self.account_id}] Position closed: {symbol} {position_side}")
                    del self.positions[position_key]
                    if self.on_position_update:
                        # Send closed position (with quantity=0) to include symbol info
                        closed_position.quantity = Decimal("0")
                        self.on_position_update(self.account_id, closed_position)
            else:
                # Determine side from position_side field or amount
                if position_side in ("LONG", "SHORT"):
                    side = position_side
                else:
                    side = "LONG" if position_amount > 0 else "SHORT"
                
                # Positions for allowed_symbols are bot-managed (not read-only)
                # Positions for other symbols (pre-existing or manually opened) are read-only
                if symbol in self._allowed_symbols:
                    is_read_only = False  # Bot can manage this symbol
                else:
                    is_read_only = not self._initialized and position_key not in self.positions
                
                position = PositionState(
                    symbol=symbol,
                    account_id=self.account_id,
                    side=side,
                    quantity=abs(position_amount),
                    entry_price=entry_price,
                    is_read_only=is_read_only,
                )
                
                self.positions[position_key] = position
                
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

    def get_position(self, symbol: str, side: Optional[str] = None) -> Optional[PositionState]:
        """
        Get current position for a symbol.
        
        Args:
            symbol: Trading symbol
            side: Position side (LONG/SHORT) for hedge mode, None for one-way mode
            
        Returns:
            PositionState or None if no position
        """
        if side:
            key = f"{symbol}:{side}"
            return self.positions.get(key)
        # Try both formats
        return self.positions.get(symbol) or self.positions.get(f"{symbol}:LONG") or self.positions.get(f"{symbol}:SHORT")

    def has_position(self, symbol: str, side: Optional[str] = None) -> bool:
        """Check if there's an open position for symbol."""
        if side:
            return f"{symbol}:{side}" in self.positions
        return symbol in self.positions or f"{symbol}:LONG" in self.positions or f"{symbol}:SHORT" in self.positions

    def get_all_positions(self) -> Dict[str, PositionState]:
        """Get all open positions."""
        return self.positions.copy()

    def clear_position(self, symbol: str, side: Optional[str] = None):
        """Clear position from local cache (e.g., after manual close)."""
        if side:
            key = f"{symbol}:{side}"
            if key in self.positions:
                del self.positions[key]
        else:
            # Clear all matching
            for key in list(self.positions.keys()):
                if key == symbol or key.startswith(f"{symbol}:"):
                    del self.positions[key]

    def mark_position_managed(self, symbol: str, side: Optional[str] = None):
        """Mark a position as bot-managed (not read-only)."""
        if side:
            key = f"{symbol}:{side}"
            if key in self.positions:
                self.positions[key].is_read_only = False
        else:
            for key in self.positions:
                if key == symbol or key.startswith(f"{symbol}:"):
                    self.positions[key].is_read_only = False
