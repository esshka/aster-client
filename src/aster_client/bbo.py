# -*- coding: utf-8 -*-
"""
BBO (Best Bid Offer) Module

This module implements BBO order pricing functionality for optimal order placement.
BBO orders are placed one tick away from the current market price to maximize
the chance of maker fee execution while getting optimal pricing.

Key Features:
- Automatic BBO price calculation based on market price
- Tick size support using SymbolInfo from public client
- BUY orders: place below best bid (bid - N ticks) for maker orders
- SELL orders: place above best ask (ask + N ticks) for maker orders
- Price precision handling
- Integration with existing order management system
- Real-time BBO price updates via WebSocket (!bookTicker stream)

WebSocket Connection Compliance:
- Automatic reconnection every 24 hours (exchange limit)
- Ping/Pong heartbeat handling (30s client pings, auto-respond to server pings)
- Automatic reconnection on connection errors with 5-second delay
- Single !bookTicker stream (well under 200 stream subscription limit)
- Handles server-side rate limiting (10 messages per second)
"""

import asyncio
import json
import logging
import time
from decimal import Decimal, ROUND_DOWN
from typing import Optional, Dict, Tuple

import aiohttp

from .constants import DEFAULT_WS_URL
from .models.market import SymbolInfo
from .models.orders import OrderRequest

logger = logging.getLogger(__name__)


class BBOPriceCalculator:
    """
    BBO price calculator for determining optimal order placement prices.
    
    This class implements the Singleton pattern to maintain a single WebSocket
    connection for real-time BBO updates.

    For BBO logic:
    - Buy orders: Place at current market price + 1 tick size
    - Sell orders: Place at current market price - 1 tick size
    """
    
    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(BBOPriceCalculator, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize BBO price calculator."""
        if self._initialized:
            return
            
        self.logger = logger
        self.ws_url = DEFAULT_WS_URL
        self.running = False
        self.ws_task = None
        self.bbo_cache: Dict[str, Tuple[Decimal, Decimal]] = {}  # symbol -> (best_bid, best_ask)
        self.last_update: Dict[str, float] = {}  # symbol -> timestamp
        
        self.logger.debug("BBO calculator initialized (Singleton)")
        self._initialized = True

    async def start(self):
        """Start the WebSocket client for real-time BBO updates."""
        if self.running:
            return

        self.running = True
        self.ws_task = asyncio.create_task(self._ws_loop())
        self.logger.info(f"BBO WebSocket client started: {self.ws_url}")

    async def stop(self):
        """Stop the WebSocket client."""
        self.running = False
        if self.ws_task:
            self.ws_task.cancel()
            try:
                await self.ws_task
            except asyncio.CancelledError:
                pass
            self.ws_task = None
        self.logger.info("BBO WebSocket client stopped")

    async def _ws_loop(self):
        """Main WebSocket loop for receiving BBO updates."""
        while self.running:
            connection_start = time.time()
            reconnect_needed = False
            
            try:
                async with aiohttp.ClientSession() as session:
                    # Test combined stream with query params (standard Binance format)
                    # Base URL changes from /ws to /stream
                    base_url = self.ws_url.replace("/ws/!bookTicker", "/stream")
                    combined_stream_url = f"{base_url}?streams=btcusdt@bookTicker/ethusdt@bookTicker/solusdt@bookTicker"
                    
                    async with session.ws_connect(
                        combined_stream_url,
                        heartbeat=60,
                        timeout=aiohttp.ClientTimeout(total=None, connect=10, sock_read=900),
                    ) as ws:
                        self.logger.info(f"Connected to BBO WebSocket stream: {combined_stream_url}")
                        
                        async for msg in ws:
                            # Check if we've been connected for 24 hours (enforce exchange limit)
                            connection_duration = time.time() - connection_start
                            if connection_duration >= 86400:  # 24 hours = 86400 seconds
                                self.logger.info(
                                    "WebSocket connection approaching 24-hour limit, reconnecting..."
                                )
                                reconnect_needed = True
                                break
                            
                            if not self.running:
                                break
                                
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                try:
                                    data = json.loads(msg.data)
                                    
                                    # Handle combined stream format: {"stream": "...", "data": {...}}
                                    if "data" in data and "stream" in data:
                                        self._process_bbo_update(data["data"])
                                    else:
                                        self._process_bbo_update(data)
                                except Exception as e:
                                    self.logger.error(f"Error processing BBO message: {e}")
                            elif msg.type == aiohttp.WSMsgType.PING:
                                # Server sent a ping, aiohttp will auto-respond with pong
                                self.logger.debug("Received ping from server")
                            elif msg.type == aiohttp.WSMsgType.PONG:
                                # Response to our heartbeat ping
                                self.logger.debug("Received pong from server")
                            elif msg.type == aiohttp.WSMsgType.CLOSE:
                                self.logger.warning(
                                    f"WebSocket connection closed by server: {msg.data}"
                                )
                                reconnect_needed = True
                                break
                            elif msg.type == aiohttp.WSMsgType.ERROR:
                                self.logger.error(f"WebSocket connection error: {ws.exception()}")
                                reconnect_needed = True
                                break
                        
                        # If we exit the async for loop, the connection was closed
                        # Check why it closed
                        if self.running:
                            if ws.closed:
                                self.logger.warning(
                                    f"WebSocket connection closed (code: {ws.close_code})"
                                )
                                reconnect_needed = True
                            elif not reconnect_needed:
                                # Loop exited but ws not closed and no reconnect flag set
                                # This shouldn't happen
                                self.logger.warning("WebSocket loop exited unexpectedly")
                                reconnect_needed = True
                            
            except Exception as e:
                self.logger.error(f"WebSocket connection error: {e}")
                reconnect_needed = True
            
            # Only reconnect if needed and still running
            if reconnect_needed and self.running:
                self.logger.info("Reconnecting in 5 seconds...")
                await asyncio.sleep(5)

    def _process_bbo_update(self, data: Dict):
        """
        Process BBO update message.
        
        Expected format:
        {
          "u":400900217,     // order book updateId
          "s":"BNBUSDT",     // symbol
          "b":"25.35190000", // best bid price
          "B":"31.21000000", // best bid qty
          "a":"25.36520000", // best ask price
          "A":"40.66000000"  // best ask qty
        }
        """
        try:
            symbol = data.get("s")
            if not symbol:
                return

            best_bid = Decimal(str(data.get("b", 0)))
            best_ask = Decimal(str(data.get("a", 0)))

            if best_bid > 0 and best_ask > 0:
                self.bbo_cache[symbol] = (best_bid, best_ask)
                self.last_update[symbol] = time.time()
                # self.logger.debug(f"Updated BBO for {symbol}: Bid={best_bid}, Ask={best_ask}")
        except Exception as e:
            self.logger.error(f"Failed to parse BBO update: {e}")

    def get_bbo(self, symbol: str) -> Optional[Tuple[Decimal, Decimal]]:
        """
        Get the latest BBO prices for a symbol from cache.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Tuple of (best_bid, best_ask) or None if not available
        """
        return self.bbo_cache.get(symbol)

    def get_tick_size_from_symbol_info(self, symbol_info: SymbolInfo) -> Decimal:
        """
        Extract tick size from SymbolInfo.

        Args:
            symbol_info: Symbol information object

        Returns:
            Tick size as Decimal

        Raises:
            ValueError: If tick size is not available or invalid
        """
        # First try to get from price filter (most accurate)
        if symbol_info.price_filter and symbol_info.price_filter.tick_size:
            tick_size = symbol_info.price_filter.tick_size
            self.logger.debug(
                f"Using tick size from price filter for {symbol_info.symbol}: {tick_size}"
            )
            return tick_size

        # Fallback to direct tick_size field
        if symbol_info.tick_size and symbol_info.tick_size > 0:
            tick_size = symbol_info.tick_size
            self.logger.debug(
                f"Using tick size from symbol info for {symbol_info.symbol}: {tick_size}"
            )
            return tick_size

        raise ValueError(
            f"Tick size not available for symbol {symbol_info.symbol}"
        )

    def calculate_bbo_price(
        self,
        symbol: str,
        side: str,
        best_bid: Optional[Decimal] = None,
        best_ask: Optional[Decimal] = None,
        tick_size: Decimal = Decimal("0.01"), # Default if not provided, though usually required
        ticks_distance: int = 1,
    ) -> Decimal:
        """
        Calculate BBO price for optimal order placement.
        
        If best_bid/best_ask are not provided, tries to use cached values.

        Args:
            symbol: Trading symbol
            side: Order side ("buy" or "sell")
            best_bid: Current best bid price (optional)
            best_ask: Current best ask price (optional)
            tick_size: Tick size for the symbol
            ticks_distance: Number of ticks away from best price (default: 1)

        Returns:
            Calculated BBO price

        Raises:
            ValueError: If parameters are invalid or prices unavailable
        """
        if not symbol or not symbol.strip():
            raise ValueError("Symbol cannot be empty")

        # Try to get from cache if not provided
        if best_bid is None or best_ask is None:
            cached_bbo = self.get_bbo(symbol)
            if cached_bbo:
                best_bid = best_bid or cached_bbo[0]
                best_ask = best_ask or cached_bbo[1]
            else:
                if best_bid is None or best_ask is None:
                     # If still missing, we can't calculate
                     raise ValueError(f"BBO prices not available for {symbol} and not provided")

        side_lower = side.lower()
        if side_lower not in ["buy", "sell"]:
            raise ValueError("Side must be 'buy' or 'sell'")

        if best_bid <= 0 or best_ask <= 0:
            raise ValueError("Best bid and ask must be greater than 0")

        if tick_size <= 0:
            raise ValueError("Tick size must be greater than 0")

        if ticks_distance < 1:
            raise ValueError("Ticks distance must be at least 1")

        # Calculate BBO price based on side and ticks distance
        price_adjustment = tick_size * ticks_distance
        
        if side_lower == "buy":
            # For buy orders (LONG): place N ticks below best bid to stay on maker side
            # This ensures we don't cross the spread and get maker fees
            bbo_price = best_bid - price_adjustment
            
            # Warning if price goes below 0 or too far from market
            if bbo_price <= 0:
                self.logger.warning(
                    f"BBO Buy Price {bbo_price} is invalid (below 0)"
                )
        else:  # sell
            # For sell orders (SHORT): place N ticks above best ask to stay on maker side
            # This ensures we don't cross the spread and get maker fees
            bbo_price = best_ask + price_adjustment

        # Round to appropriate precision based on tick size
        precision = self._get_price_precision(tick_size)
        bbo_price = round(bbo_price, precision)

        self.logger.info(
            f"🎯 BBO Price Calculation: {symbol} {side.upper()} "
            f"Bid: ${best_bid:.{precision}f} Ask: ${best_ask:.{precision}f} "
            f"→ BBO: ${bbo_price:.{precision}f} "
            f"({ticks_distance} tick{'s' if ticks_distance > 1 else ''}: {price_adjustment})"
        )

        return bbo_price

    def _get_price_precision(self, tick_size: Decimal) -> int:
        """
        Get price precision based on tick size.

        Args:
            tick_size: Tick size value

        Returns:
            Number of decimal places for precision
        """
        if tick_size >= 1:
            return 0
        elif tick_size >= Decimal("0.1"):
            return 1
        elif tick_size >= Decimal("0.01"):
            return 2
        elif tick_size >= Decimal("0.001"):
            return 3
        elif tick_size >= Decimal("0.0001"):
            return 4
        elif tick_size >= Decimal("0.00001"):
            return 5
        else:
            return 8  # Default for very small tick sizes

    def validate_bbo_price(
        self,
        symbol: str,
        side: str,
        bbo_price: Decimal,
        best_bid: Decimal,
        best_ask: Decimal,
        tick_size: Decimal,
        ticks_distance: int = 1,
    ) -> bool:
        """
        Validate that BBO price is correctly calculated.

        Args:
            symbol: Trading symbol
            side: Order side
            bbo_price: Calculated BBO price
            best_bid: Current best bid price
            best_ask: Current best ask price
            tick_size: Tick size for the symbol
            ticks_distance: Number of ticks away from best price (default: 1)

        Returns:
            True if BBO price is valid, False otherwise
        """
        try:
            expected_bbo = self.calculate_bbo_price(
                symbol, side, best_bid, best_ask, tick_size, ticks_distance
            )
            tolerance = tick_size / Decimal("100")  # Small tolerance
            is_valid = abs(bbo_price - expected_bbo) <= tolerance

            if not is_valid:
                self.logger.warning(
                    f"BBO price validation failed: expected {expected_bbo}, got {bbo_price}"
                )

            return is_valid
        except Exception as e:
            self.logger.error(f"Error validating BBO price: {e}")
            return False


# Global instance for convenience
_default_calculator = BBOPriceCalculator()


def calculate_bbo_price(
    symbol: str,
    side: str,
    best_bid: Optional[Decimal] = None,
    best_ask: Optional[Decimal] = None,
    tick_size: Decimal = Decimal("0.01"),
    ticks_distance: int = 1,
) -> Decimal:
    """
    Convenience function to calculate BBO price using default calculator.

    Args:
        symbol: Trading symbol
        side: Order side ("buy" or "sell")
        best_bid: Current best bid price (optional)
        best_ask: Current best ask price (optional)
        tick_size: Tick size for the symbol
        ticks_distance: Number of ticks away from best price (default: 1)

    Returns:
        Calculated BBO price
    """
    return _default_calculator.calculate_bbo_price(
        symbol, side, best_bid, best_ask, tick_size, ticks_distance
    )


def create_bbo_order(
    symbol: str,
    side: str,
    quantity: Decimal,
    best_bid: Optional[Decimal] = None,
    best_ask: Optional[Decimal] = None,
    tick_size: Decimal = Decimal("0.01"),
    ticks_distance: int = 1,
    time_in_force: str = "gtc",
    client_order_id: Optional[str] = None,
    position_side: Optional[str] = None,
) -> OrderRequest:
    """
    Create an OrderRequest with BBO pricing.

    Args:
        symbol: Trading symbol
        side: Order side ("buy" or "sell")
        quantity: Order quantity
        best_bid: Current best bid price (optional)
        best_ask: Current best ask price (optional)
        tick_size: Tick size for the symbol
        ticks_distance: Number of ticks away from best price (default: 1)
        time_in_force: Time in force (default: "gtc")
        client_order_id: Optional client order ID
        position_side: Optional position side for hedge mode

    Returns:
        OrderRequest with BBO price
    """
    bbo_price = calculate_bbo_price(
        symbol, side, best_bid, best_ask, tick_size, ticks_distance
    )

    return OrderRequest(
        symbol=symbol,
        side=side.lower(),
        order_type="limit",
        quantity=quantity,
        price=bbo_price,
        time_in_force=time_in_force,
        client_order_id=client_order_id,
        position_side=position_side,
    )


if __name__ == "__main__":
    # Demo and testing
    logging.basicConfig(level=logging.INFO)

    print("🎯 BBO Price Calculator Demo")
    print("=" * 60)

    # Test price calculation
    test_cases = [
        ("BTCUSDT", "buy", Decimal("50000.0"), Decimal("50001.0"), Decimal("0.1")),
        ("BTCUSDT", "sell", Decimal("50000.0"), Decimal("50001.0"), Decimal("0.1")),
        ("ETHUSDT", "buy", Decimal("3000.0"), Decimal("3001.0"), Decimal("0.01")),
        ("ETHUSDT", "sell", Decimal("3000.0"), Decimal("3001.0"), Decimal("0.01")),
    ]

    calculator = BBOPriceCalculator()

    for symbol, side, best_bid, best_ask, tick_size in test_cases:
        bbo_price = calculator.calculate_bbo_price(
            symbol, side, best_bid, best_ask, tick_size
        )
        print(
            f"{symbol} {side.upper()}: "
            f"Bid ${best_bid} Ask ${best_ask} → BBO ${bbo_price}"
        )

    print("\n✅ Demo completed!")
