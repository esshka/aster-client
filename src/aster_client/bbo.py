# -*- coding: utf-8 -*-
"""
BBO (Best Bid Offer) Module

This module implements BBO order pricing functionality for optimal order placement.
BBO orders are placed one tick away from the current market price to maximize
the chance of maker fee execution while getting optimal pricing.

Key Features:
- Automatic BBO price calculation based on market price
- Tick size support using SymbolInfo from public client
- BUY orders: market price + 1 tick size
- SELL orders: market price - 1 tick size
- Price precision handling
- Integration with existing order management system
"""

import logging
from decimal import Decimal, ROUND_DOWN
from typing import Optional

from .models.market import SymbolInfo
from .models.orders import OrderRequest

logger = logging.getLogger(__name__)


class BBOPriceCalculator:
    """
    BBO price calculator for determining optimal order placement prices.

    For BBO logic:
    - Buy orders: Place at current market price + 1 tick size
    - Sell orders: Place at current market price - 1 tick size
    """

    def __init__(self):
        """Initialize BBO price calculator."""
        self.logger = logger
        self.logger.debug("BBO calculator initialized")

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
        market_price: Decimal,
        tick_size: Decimal,
        ticks_distance: int = 1,
    ) -> Decimal:
        """
        Calculate BBO price for optimal order placement.

        Args:
            symbol: Trading symbol
            side: Order side ("buy" or "sell")
            market_price: Current market price
            tick_size: Tick size for the symbol
            ticks_distance: Number of ticks away from market price (default: 1)

        Returns:
            Calculated BBO price

        Raises:
            ValueError: If parameters are invalid
        """
        if not symbol or not symbol.strip():
            raise ValueError("Symbol cannot be empty")

        side_lower = side.lower()
        if side_lower not in ["buy", "sell"]:
            raise ValueError("Side must be 'buy' or 'sell'")

        if market_price <= 0:
            raise ValueError("Market price must be greater than 0")

        if tick_size <= 0:
            raise ValueError("Tick size must be greater than 0")

        if ticks_distance < 1:
            raise ValueError("Ticks distance must be at least 1")

        # Calculate BBO price based on side and ticks distance
        price_adjustment = tick_size * ticks_distance
        
        if side_lower == "buy":
            # For buy orders: place N ticks above market price
            bbo_price = market_price + price_adjustment
        else:  # sell
            # For sell orders: place N ticks below market price
            bbo_price = market_price - price_adjustment

        # Round to appropriate precision based on tick size
        precision = self._get_price_precision(tick_size)
        bbo_price = round(bbo_price, precision)

        self.logger.info(
            f"🎯 BBO Price Calculation: {symbol} {side.upper()} "
            f"Market: ${market_price:.{precision}f} → BBO: ${bbo_price:.{precision}f} "
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
        market_price: Decimal,
        tick_size: Decimal,
        ticks_distance: int = 1,
    ) -> bool:
        """
        Validate that BBO price is correctly calculated.

        Args:
            symbol: Trading symbol
            side: Order side
            bbo_price: Calculated BBO price
            market_price: Current market price
            tick_size: Tick size for the symbol
            ticks_distance: Number of ticks away from market price (default: 1)

        Returns:
            True if BBO price is valid, False otherwise
        """
        try:
            expected_bbo = self.calculate_bbo_price(
                symbol, side, market_price, tick_size, ticks_distance
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
    market_price: Decimal,
    tick_size: Decimal,
    ticks_distance: int = 1,
) -> Decimal:
    """
    Convenience function to calculate BBO price using default calculator.

    Args:
        symbol: Trading symbol
        side: Order side ("buy" or "sell")
        market_price: Current market price
        tick_size: Tick size for the symbol
        ticks_distance: Number of ticks away from market price (default: 1)

    Returns:
        Calculated BBO price
    """
    return _default_calculator.calculate_bbo_price(
        symbol, side, market_price, tick_size, ticks_distance
    )


def create_bbo_order(
    symbol: str,
    side: str,
    quantity: Decimal,
    market_price: Decimal,
    tick_size: Decimal,
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
        market_price: Current market price
        tick_size: Tick size for the symbol
        ticks_distance: Number of ticks away from market price (default: 1)
        time_in_force: Time in force (default: "gtc")
        client_order_id: Optional client order ID
        position_side: Optional position side for hedge mode

    Returns:
        OrderRequest with BBO price
    """
    bbo_price = calculate_bbo_price(symbol, side, market_price, tick_size, ticks_distance)

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
        ("BTCUSDT", "buy", Decimal("50000.0"), Decimal("0.1")),
        ("BTCUSDT", "sell", Decimal("50000.0"), Decimal("0.1")),
        ("ETHUSDT", "buy", Decimal("3000.0"), Decimal("0.01")),
        ("ETHUSDT", "sell", Decimal("3000.0"), Decimal("0.01")),
        ("ADAUSDT", "buy", Decimal("0.5000"), Decimal("0.0001")),
        ("ADAUSDT", "sell", Decimal("0.5000"), Decimal("0.0001")),
    ]

    calculator = BBOPriceCalculator()

    for symbol, side, market_price, tick_size in test_cases:
        bbo_price = calculator.calculate_bbo_price(
            symbol, side, market_price, tick_size
        )
        print(
            f"{symbol} {side.upper()}: "
            f"Market ${market_price} → BBO ${bbo_price}"
        )

    print("\n✅ Demo completed!")
