"""
Aster Client - Main orchestration module.

This module provides the main AsterClient class that coordinates
all client functionality while staying under 300 LOC.

The client follows state-first design with clean separation of concerns:
- Data models are immutable structures in models/
- HTTP operations are handled by http_client.py
- Session management is handled by session_manager.py
- API methods are implemented in api_methods.py
- Monitoring and utilities are in dedicated modules
"""

import asyncio
import os
import logging
from decimal import Decimal
from typing import Optional, List
from dotenv import load_dotenv

from .api_methods import APIMethods
from .bbo import BBOPriceCalculator, create_bbo_order
from .constants import (
    DEFAULT_BASE_URL, DEFAULT_TIMEOUT, DEFAULT_RETRY_DELAY,
    DEFAULT_MAX_RETRIES, SUCCESS_STATUS_CODE, ERROR_STATUS_CODE
)
from .http_client import HttpClient
from .models import (
    AccountInfo, Balance, BalanceV2, MarkPrice, OrderRequest, OrderResponse,
    Position, ConnectionConfig, RetryConfig, ClosePositionResult
)
from .monitoring import PerformanceMonitor
from .session_manager import SessionManager

load_dotenv()
logger = logging.getLogger(__name__)


# BBO Retry Exceptions
class BBORetryExhausted(Exception):
    """Raised when BBO order retry limit is exhausted without fill."""
    pass


class BBOPriceChaseExceeded(Exception):
    """Raised when BBO price chase exceeds max allowed deviation."""
    pass


class AsterClient:
    """
    Main Aster client orchestrator.

    Coordinates all client functionality while maintaining clean
    separation of concerns and keeping implementation minimal.
    """

    def __init__(
        self,
        config: ConnectionConfig,
        retry_config: Optional[RetryConfig] = None,
    ):
        """Initialize Aster client with configuration."""
        self._config = config
        self._session_manager = SessionManager(config)
        self._http_client = HttpClient(config, retry_config)
        self._api_methods = APIMethods(self._http_client)
        self._monitor = PerformanceMonitor()
        self._bbo_calculator = BBOPriceCalculator()
        self._closed = False

    @classmethod
    def from_env(cls, simulation: bool = False) -> "AsterClient":
        """Create client from environment variables."""
        api_key = os.getenv("ASTER_API_KEY", "")
        api_secret = os.getenv("ASTER_API_SECRET", "")

        recv_window = int(os.getenv("ASTER_RECV_WINDOW", "5000"))

        config = ConnectionConfig(
            api_key=api_key,
            api_secret=api_secret,
            simulation=simulation,
            recv_window=recv_window,
        )

        return cls(config)

    # Account methods
    async def get_account_info(self) -> AccountInfo:
        """Get account information."""
        return await self._execute_with_monitoring(
            self._api_methods.get_account_info, "GET", "/account"
        )

    async def get_positions(self) -> list[Position]:
        """Get all open positions."""
        return await self._execute_with_monitoring(
            self._api_methods.get_positions, "GET", "/positions"
        )

    async def get_balances(self) -> list[Balance]:
        """Get account balances."""
        return await self._execute_with_monitoring(
            self._api_methods.get_balances, "GET", "/balances"
        )

    async def get_balances_v2(self, recv_window: Optional[int] = None) -> list[BalanceV2]:
        """Get Futures account balances V2.
        
        Args:
            recv_window: Optional recv window in milliseconds
            
        Returns:
            List of BalanceV2 objects containing detailed balance information
        """
        return await self._execute_with_monitoring(
            self._api_methods.get_balances_v2, "GET", "/fapi/v2/balance", recv_window
        )

    # Order methods
    async def place_order(self, order: OrderRequest) -> OrderResponse:
        """Place a new order."""
        return await self._execute_with_monitoring(
            self._api_methods.place_order, "POST", "/orders", order
        )

    async def place_bbo_order(
        self,
        symbol: str,
        side: str,
        quantity: Decimal,
        best_bid: Decimal,
        best_ask: Decimal,
        tick_size: Decimal,
        ticks_distance: int = 1,
        time_in_force: str = "gtc",
        client_order_id: Optional[str] = None,
        position_side: Optional[str] = None,
    ) -> OrderResponse:
        """
        Place a BBO (Best Bid Offer) order with automatic price calculation.

        BBO orders are placed N ticks AWAY from the spread to ensure maker fees:
        - BUY orders: best_bid - (tick_size * ticks_distance) (below best bid)
        - SELL orders: best_ask + (tick_size * ticks_distance) (above best ask)

        This ensures orders don't cross the spread and execute as maker orders.

        Args:
            symbol: Trading symbol (e.g., "BTCUSDT")
            side: Order side ("buy" or "sell")
            quantity: Order quantity
            best_bid: Current best bid price
            best_ask: Current best ask price
            tick_size: Tick size for the symbol
            ticks_distance: Number of ticks away from best price (default: 1)
            time_in_force: Time in force (default: "gtc")
            client_order_id: Optional client order ID
            position_side: Optional position side for hedge mode

        Returns:
            OrderResponse with order details

        Raises:
            ValueError: If parameters are invalid
        """
        # Calculate BBO price
        bbo_price = self._bbo_calculator.calculate_bbo_price(
            symbol, side, best_bid, best_ask, tick_size, ticks_distance
        )

        # Create order request with BBO price
        order = OrderRequest(
            symbol=symbol,
            side=side.lower(),
            order_type="limit",
            quantity=quantity,
            price=bbo_price,
            time_in_force=time_in_force,
            client_order_id=client_order_id,
            position_side=position_side,
        )

        # Place the order
        return await self.place_order(order)

    async def place_bbo_order_with_retry(
        self,
        symbol: str,
        side: str,
        quantity: Decimal,
        tick_size: Decimal,
        ticks_distance: int = 0,  # At bid1/ask1 (safe with GTX post-only)
        max_retries: int = 2,
        fill_timeout_ms: int = 1000,
        max_chase_percent: float = 0.5,
        time_in_force: str = "GTX",  # Post-only: reject if would cross spread
        client_order_id: Optional[str] = None,
        position_side: Optional[str] = None,
        best_bid: Optional[Decimal] = None,
        best_ask: Optional[Decimal] = None,
        reduce_only: Optional[bool] = None,  # None = don't send, True = reduce only
    ) -> OrderResponse:
        """
        Place a BBO order with automatic retry on unfilled orders.

        This method places a BBO order and automatically retries with updated
        prices if the order doesn't fill within the specified timeout. It will
        stop retrying if the price moves beyond the max chase limit.

        Args:
            symbol: Trading symbol (e.g., "BTCUSDT")
            side: Order side ("buy" or "sell")
            quantity: Order quantity
            tick_size: Tick size for the symbol
            ticks_distance: Number of ticks away from best price (default: 1)
            max_retries: Maximum retry attempts (default: 2)
            fill_timeout_ms: Time to wait for fill before retry in ms (default: 1000)
            max_chase_percent: Maximum price deviation from original (default: 0.5%)
            time_in_force: Time in force (default: "gtc")
            client_order_id: Optional client order ID
            position_side: Optional position side for hedge mode
            best_bid: Optional initial best bid (used if WebSocket cache is empty)
            best_ask: Optional initial best ask (used if WebSocket cache is empty)

        Returns:
            OrderResponse with filled order details

        Raises:
            BBORetryExhausted: If max retries exceeded without fill
            BBOPriceChaseExceeded: If price moved beyond max chase limit
            ValueError: If BBO prices not available
        """
        # Get initial BBO prices from cache or use provided values
        bbo = self._bbo_calculator.get_bbo(symbol)
        if bbo:
            original_best_bid, original_best_ask = bbo
        elif best_bid is not None and best_ask is not None:
            original_best_bid, original_best_ask = best_bid, best_ask
            logger.info(f"Using provided BBO prices for {symbol}: Bid={best_bid}, Ask={best_ask}")
        else:
            raise ValueError(f"BBO prices not available for {symbol}. Ensure WebSocket is connected or provide best_bid/best_ask.")
        
        original_reference = original_best_bid if side.lower() == "buy" else original_best_ask
        
        attempts = 0
        last_order_response = None
        last_bbo_price = None  # Track last order price to avoid unnecessary replacements
        
        while attempts <= max_retries:
            # Get fresh BBO prices for each attempt (prefer cache, fallback to provided)
            bbo = self._bbo_calculator.get_bbo(symbol)
            if bbo:
                current_best_bid, current_best_ask = bbo
            else:
                current_best_bid, current_best_ask = original_best_bid, original_best_ask

            current_reference = current_best_bid if side.lower() == "buy" else current_best_ask
            
            # Check price deviation (except for first attempt)
            if attempts > 0:
                deviation = self._calculate_price_deviation(original_reference, current_reference)
                if deviation > max_chase_percent:
                    logger.warning(
                        f"BBO price chase exceeded: {deviation:.3f}% > {max_chase_percent}% max. "
                        f"Original: {original_reference}, Current: {current_reference}"
                    )
                    raise BBOPriceChaseExceeded(
                        f"Price moved {deviation:.3f}% from original, exceeds {max_chase_percent}% limit"
                    )
            
            # Calculate BBO price
            bbo_price = self._bbo_calculator.calculate_bbo_price(
                symbol, side, current_best_bid, current_best_ask, tick_size, ticks_distance
            )
            
            # Check if we need to place/replace order
            # Only cancel & replace if price changed OR first attempt
            order_placed_this_round = False
            
            if last_order_response is None or bbo_price != last_bbo_price:
                # Cancel existing order if price changed
                if last_order_response is not None and bbo_price != last_bbo_price:
                    logger.info(
                        f"📊 Price changed: {last_bbo_price} → {bbo_price}, replacing order"
                    )
                    try:
                        await self.cancel_order(
                            symbol=symbol,
                            order_id=int(last_order_response.order_id)
                        )
                    except Exception as e:
                        logger.warning(f"Failed to cancel order {last_order_response.order_id}: {e}")
                    
                    # Count price changes as attempts (not waiting loops)
                    attempts += 1
                    if attempts > max_retries:
                        break
                
                logger.info(
                    f"🎯 BBO Order Attempt {attempts + 1}/{max_retries + 1}: "
                    f"{symbol} {side.upper()} @ {bbo_price}"
                )
                
                order = OrderRequest(
                    symbol=symbol,
                    side=side.lower(),
                    order_type="limit",
                    quantity=quantity,
                    price=bbo_price,
                    time_in_force=time_in_force,
                    client_order_id=client_order_id,
                    position_side=position_side,
                    reduce_only=reduce_only,
                )
                
                last_order_response = await self.place_order(order)
                last_bbo_price = bbo_price
                order_placed_this_round = True
            else:
                # Price hasn't changed, keep existing order alive
                logger.debug(f"Price unchanged at {bbo_price}, keeping order alive")
            
            # Wait for fill
            fill_timeout_s = fill_timeout_ms / 1000.0
            await asyncio.sleep(fill_timeout_s)
            
            # Check if filled
            order_status = await self.get_order(
                symbol=symbol,
                order_id=int(last_order_response.order_id)
            )
            
            if order_status and order_status.status in ["FILLED", "COMPLETED"]:
                logger.info(
                    f"✅ BBO Order filled on attempt {attempts + 1}: "
                    f"ID={order_status.order_id}, Price={order_status.average_price}"
                )
                return order_status
        
        # All retries exhausted (only reached if price kept changing)
        logger.error(
            f"❌ BBO Order retry exhausted after {max_retries + 1} attempts. "
            f"Last order: {last_order_response.order_id if last_order_response else 'None'}"
        )
        
        # Cancel the last order if it exists
        if last_order_response:
            try:
                await self.cancel_order(
                    symbol=symbol,
                    order_id=int(last_order_response.order_id)
                )
            except Exception as e:
                logger.warning(f"Failed to cancel final order: {e}")
        
        raise BBORetryExhausted(
            f"BBO order not filled after {max_retries + 1} attempts"
        )

    def _calculate_price_deviation(
        self,
        original_price: Decimal,
        current_price: Decimal,
    ) -> float:
        """Calculate percent deviation between prices."""
        if original_price <= 0:
            return 0.0
        return float(abs(current_price - original_price) / original_price * 100)

    async def cancel_order(
        self,
        symbol: str,
        order_id: Optional[int] = None,
        orig_client_order_id: Optional[str] = None
    ) -> dict:
        """Cancel an existing order."""
        return await self._execute_with_monitoring(
            self._api_methods.cancel_order, 
            "DELETE", 
            f"/orders/{symbol}",
            symbol,
            order_id,
            orig_client_order_id
        )

    async def cancel_all_open_orders(self, symbol: str) -> dict:
        """Cancel all open orders for a symbol."""
        return await self._execute_with_monitoring(
            self._api_methods.cancel_all_open_orders,
            "DELETE",
            f"/orders/{symbol}/all",
            symbol
        )

    async def get_order(
        self,
        symbol: str,
        order_id: Optional[int] = None,
        orig_client_order_id: Optional[str] = None
    ) -> Optional[OrderResponse]:
        """Get order by ID or Client Order ID."""
        return await self._execute_with_monitoring(
            self._api_methods.get_order,
            "GET",
            f"/orders/{symbol}",
            symbol,
            order_id,
            orig_client_order_id
        )

    async def get_orders(self, symbol: Optional[str] = None) -> list[OrderResponse]:
        """Get all orders, optionally filtered by symbol."""
        return await self._execute_with_monitoring(
            self._api_methods.get_orders, "GET", "/orders", symbol
        )

    async def get_mark_price(self, symbol: str) -> Optional[MarkPrice]:
        """Get mark price for symbol."""
        return await self._execute_with_monitoring(
            self._api_methods.get_mark_price, "GET", f"/market/{symbol}/mark_price", symbol
        )

    async def change_position_mode(self, dual_side_position: bool) -> dict:
        """
        Change user's position mode (Hedge Mode or One-way Mode) on every symbol.
        
        Args:
            dual_side_position: True for Hedge Mode, False for One-way Mode
        """
        return await self._execute_with_monitoring(
            self._api_methods.change_position_mode, 
            "POST", 
            "/positionSide/dual", 
            dual_side_position
        )

    async def get_position_mode(self) -> dict:
        """
        Get user's position mode (Hedge Mode or One-way Mode) on every symbol.
        
        Returns:
            Dict containing "dualSidePosition": boolean
        """
        return await self._execute_with_monitoring(
            self._api_methods.get_position_mode, "GET", "/positionSide/dual"
        )

    async def close_position_for_symbol(
        self,
        symbol: str,
        tick_size: Decimal,
        best_bid: Optional[Decimal] = None,
        best_ask: Optional[Decimal] = None,
        ticks_distance: int = 0,
        max_retries: int = 5,  # More retries for close (we want to exit)
        fill_timeout_ms: int = 2000,  # Longer timeout for fills
        max_chase_percent: float = 0.1,
    ) -> ClosePositionResult:
        """
        Close all positions for a symbol with BBO order and cleanup TP/SL orders.
        
        This method:
        1. Gets the current position for the symbol
        2. Cancels all open orders for the symbol (cleanup TP/SL)
        3. Places a BBO order with reduce_only=True to close the position
        
        Args:
            symbol: Trading symbol (e.g., "BTCUSDT")
            tick_size: Tick size for the symbol (for BBO price calculation)
            best_bid: Optional best bid price (uses cache if not provided)
            best_ask: Optional best ask price (uses cache if not provided)
            ticks_distance: Number of ticks away from best price (default: 0 for aggressive)
            max_retries: Maximum retry attempts for BBO order (default: 2)
            fill_timeout_ms: Time to wait for fill before retry (default: 1000)
            max_chase_percent: Maximum price deviation from original (default: 0.1%)
            
        Returns:
            ClosePositionResult with details about the operation
        """
        cancelled_count = 0
        
        try:
            # Step 1: Get current positions
            positions = await self.get_positions()
            
            # Find position for this symbol
            symbol_position = None
            for pos in positions:
                if pos.symbol == symbol and pos.quantity != Decimal("0"):
                    symbol_position = pos
                    break
            
            # Step 2: Cancel all open orders for the symbol (TP/SL cleanup)
            try:
                cancel_result = await self.cancel_all_open_orders(symbol)
                # Try to extract count from result
                if isinstance(cancel_result, dict):
                    cancelled_count = cancel_result.get("count", 1)
                elif isinstance(cancel_result, list):
                    cancelled_count = len(cancel_result)
                else:
                    cancelled_count = 1  # Assume at least 1 if successful
                logger.info(f"🧹 Cancelled {cancelled_count} open orders for {symbol}")
            except Exception as e:
                # No orders to cancel is not an error
                if "no open orders" not in str(e).lower():
                    logger.warning(f"Failed to cancel orders for {symbol}: {e}")
                cancelled_count = 0
            
            # Step 3: Check if there's a position to close
            if symbol_position is None or symbol_position.quantity == Decimal("0"):
                logger.info(f"📭 No position to close for {symbol}")
                return ClosePositionResult(
                    symbol=symbol,
                    cancelled_orders_count=cancelled_count,
                    position_quantity=None,
                    position_side=None,
                    close_order=None,
                    success=True,
                    error=None
                )
            
            # Step 4: Determine close order side (opposite of position side)
            position_qty = abs(symbol_position.quantity)
            position_side = symbol_position.side.upper()  # LONG or SHORT
            
            # Close side is opposite: long -> sell, short -> buy
            close_side = "sell" if position_side == "LONG" else "buy"
            
            logger.info(
                f"📉 Closing {position_side} position for {symbol}: "
                f"{position_qty} @ close side={close_side}"
            )
            
            # Step 5: Place BBO order to close position
            # In Hedge Mode: use position_side param (not reduce_only)
            # The position_side tells the API which position to close
            try:
                close_order = await self.place_bbo_order_with_retry(
                    symbol=symbol,
                    side=close_side,
                    quantity=position_qty,
                    tick_size=tick_size,
                    ticks_distance=ticks_distance,
                    max_retries=max_retries,
                    fill_timeout_ms=fill_timeout_ms,
                    max_chase_percent=max_chase_percent,
                    best_bid=best_bid,
                    best_ask=best_ask,
                    position_side=position_side,  # For Hedge Mode: specify which side to close
                    # Note: Don't send reduce_only in Hedge Mode - API rejects it
                )
                
                logger.info(
                    f"✅ Position closed for {symbol}: "
                    f"Order ID={close_order.order_id}, "
                    f"Avg Price={close_order.average_price}"
                )
                
                return ClosePositionResult(
                    symbol=symbol,
                    cancelled_orders_count=cancelled_count,
                    position_quantity=position_qty,
                    position_side=position_side,
                    close_order=close_order,
                    success=True,
                    error=None
                )
                
            except (BBORetryExhausted, BBOPriceChaseExceeded) as e:
                logger.error(f"❌ Failed to close position for {symbol}: {e}")
                return ClosePositionResult(
                    symbol=symbol,
                    cancelled_orders_count=cancelled_count,
                    position_quantity=position_qty,
                    position_side=position_side,
                    close_order=None,
                    success=False,
                    error=str(e)
                )
                
        except Exception as e:
            logger.error(f"❌ Error closing position for {symbol}: {e}")
            return ClosePositionResult(
                symbol=symbol,
                cancelled_orders_count=cancelled_count,
                position_quantity=None,
                position_side=None,
                close_order=None,
                success=False,
                error=str(e)
            )

    # Monitoring and health
    async def health_check(self) -> bool:
        """Check client health."""
        try:
            await self._session_manager.create_session()
            return await self._session_manager.health_check()
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False

    def get_statistics(self):
        """Get performance statistics."""
        return self._monitor.statistics

    async def close(self) -> None:
        """Close client and cleanup resources."""
        if not self._closed:
            await self._session_manager.close_session()
            self._closed = True
            logger.info("Aster client closed")

    async def _execute_with_monitoring(
        self, api_method, method: str, endpoint: str, *args, **kwargs
    ):
        """Execute API method with performance monitoring."""
        if self._closed:
            raise RuntimeError("Client is closed")

        start_time = asyncio.get_event_loop().time()
        session = await self._session_manager.create_session()

        try:
            result = await api_method(session, *args, **kwargs)
            duration_ms = (asyncio.get_event_loop().time() - start_time) * 1000

            # Record success metrics
            self._monitor.record_request(endpoint, method, SUCCESS_STATUS_CODE, duration_ms)
            return result

        except Exception as e:
            duration_ms = (asyncio.get_event_loop().time() - start_time) * 1000
            status_code = getattr(e, "status_code", ERROR_STATUS_CODE)

            # Record error metrics
            self._monitor.record_request(endpoint, method, status_code, duration_ms)
            raise

    # Context manager support
    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    def __del__(self):
        """Cleanup on deletion."""
        if hasattr(self, '_closed') and not self._closed:
            logger.warning("AsterClient not properly closed - call close() explicitly")


def create_aster_client(
    api_key: str,
    api_secret: str,
    base_url: str = DEFAULT_BASE_URL,
    timeout: float = DEFAULT_TIMEOUT,
    simulation: bool = False,
    recv_window: int = 5000,
    max_retries: int = DEFAULT_MAX_RETRIES,
    retry_delay: float = DEFAULT_RETRY_DELAY,
) -> AsterClient:
    """
    Factory function to create Aster client with common configuration.

    Args:
        api_key: API key for authentication
        api_secret: API secret for authentication
        base_url: Base URL for API endpoints
        timeout: Request timeout in seconds
        simulation: Enable simulation mode
        recv_window: Receive window in milliseconds (default 5000)
        max_retries: Maximum number of retry attempts
        retry_delay: Initial delay between retries in seconds

    Returns:
        Configured AsterClient instance
    """
    config = ConnectionConfig(
        api_key=api_key,
        api_secret=api_secret,
        base_url=base_url,
        timeout=timeout,
        simulation=simulation,
        recv_window=recv_window,
    )

    retry_config = RetryConfig(
        max_retries=max_retries,
        retry_delay=retry_delay,
    )

    return AsterClient(config, retry_config)