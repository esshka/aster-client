# -*- coding: utf-8 -*-
"""
Unit tests for BBO (Best Bid Offer) module.

Tests price calculation, validation, and integration with order creation.
"""

import pytest
from decimal import Decimal

from aster_client.bbo import (
    BBOPriceCalculator,
    calculate_bbo_price,
    create_bbo_order,
)
from aster_client.models.market import SymbolInfo, PriceFilter


class TestBBOPriceCalculator:
    """Test suite for BBOPriceCalculator class."""

    @pytest.fixture
    def calculator(self):
        """Create BBOPriceCalculator instance."""
        return BBOPriceCalculator()

    def test_calculate_bbo_price_buy(self, calculator):
        """Test BBO price calculation for BUY orders."""
        symbol = "BTCUSDT"
        side = "buy"
        best_bid = Decimal("50000.0")
        best_ask = Decimal("50000.5")
        tick_size = Decimal("0.1")

        bbo_price = calculator.calculate_bbo_price(
            symbol, side, best_bid, best_ask, tick_size
        )

        # BUY orders should be best_bid + tick_size
        assert bbo_price == Decimal("50000.1")

    def test_calculate_bbo_price_sell(self, calculator):
        """Test BBO price calculation for SELL orders."""
        symbol = "BTCUSDT"
        side = "sell"
        best_bid = Decimal("50000.0")
        best_ask = Decimal("50000.5")
        tick_size = Decimal("0.1")

        bbo_price = calculator.calculate_bbo_price(
            symbol, side, best_bid, best_ask, tick_size
        )

        # SELL orders should be best_ask - tick_size
        assert bbo_price == Decimal("50000.4")

    def test_calculate_bbo_price_different_tick_sizes(self, calculator):
        """Test BBO price calculation with different tick sizes."""
        test_cases = [
            ("BTCUSDT", "buy", Decimal("50000.0"), Decimal("50000.5"), Decimal("0.1"), Decimal("50000.1")),
            ("ETHUSDT", "buy", Decimal("3000.0"), Decimal("3000.5"), Decimal("0.01"), Decimal("3000.01")),
            ("ADAUSDT", "buy", Decimal("0.5000"), Decimal("0.5005"), Decimal("0.0001"), Decimal("0.5001")),
            ("DOTUSDT", "sell", Decimal("9.900"), Decimal("10.000"), Decimal("0.001"), Decimal("9.999")),
        ]

        for symbol, side, best_bid, best_ask, tick_size, expected in test_cases:
            result = calculator.calculate_bbo_price(
                symbol, side, best_bid, best_ask, tick_size
            )
            assert result == expected, f"Failed for {symbol} {side}"

    def test_calculate_bbo_price_with_ticks_distance(self, calculator):
        """Test BBO price calculation with custom ticks distance."""
        # BUY with 2 ticks distance
        result = calculator.calculate_bbo_price(
            "BTCUSDT", "buy", Decimal("50000.0"), Decimal("50000.5"), Decimal("0.1"), ticks_distance=2
        )
        assert result == Decimal("50000.2")  # bid + (0.1 * 2)

        # SELL with 3 ticks distance
        result = calculator.calculate_bbo_price(
            "ETHUSDT", "sell", Decimal("2999.0"), Decimal("3000.0"), Decimal("0.01"), ticks_distance=3
        )
        assert result == Decimal("2999.97")  # ask - (0.01 * 3)

        # BUY with 5 ticks distance
        result = calculator.calculate_bbo_price(
            "ADAUSDT", "buy", Decimal("0.5000"), Decimal("0.5010"), Decimal("0.0001"), ticks_distance=5
        )
        assert result == Decimal("0.5005")  # bid + (0.0001 * 5)

        # SELL with 10 ticks distance
        result = calculator.calculate_bbo_price(
            "DOTUSDT", "sell", Decimal("9.900"), Decimal("10.000"), Decimal("0.001"), ticks_distance=10
        )
        assert result == Decimal("9.990")  # ask - (0.001 * 10)

    def test_price_precision(self, calculator):
        """Test price precision calculation."""
        assert calculator._get_price_precision(Decimal("1")) == 0
        assert calculator._get_price_precision(Decimal("0.1")) == 1
        assert calculator._get_price_precision(Decimal("0.01")) == 2
        assert calculator._get_price_precision(Decimal("0.001")) == 3
        assert calculator._get_price_precision(Decimal("0.0001")) == 4
        assert calculator._get_price_precision(Decimal("0.00001")) == 5
        assert calculator._get_price_precision(Decimal("0.000001")) == 8

    def test_validate_bbo_price(self, calculator):
        """Test BBO price validation."""
        symbol = "BTCUSDT"
        side = "buy"
        best_bid = Decimal("50000.0")
        best_ask = Decimal("50000.5")
        tick_size = Decimal("0.1")

        # Correct BBO price
        bbo_price = Decimal("50000.1")
        assert calculator.validate_bbo_price(
            symbol, side, bbo_price, best_bid, best_ask, tick_size
        )

        # Incorrect BBO price
        wrong_price = Decimal("50000.2")
        assert not calculator.validate_bbo_price(
            symbol, side, wrong_price, best_bid, best_ask, tick_size
        )

    def test_invalid_side(self, calculator):
        """Test error handling for invalid side."""
        with pytest.raises(ValueError, match="Side must be"):
            calculator.calculate_bbo_price(
                "BTCUSDT", "invalid", Decimal("50000"), Decimal("50001"), Decimal("0.1")
            )

    def test_invalid_market_price(self, calculator):
        """Test error handling for invalid market price."""
        with pytest.raises(ValueError, match="Best bid and ask must be greater than 0"):
            calculator.calculate_bbo_price(
                "BTCUSDT", "buy", Decimal("0"), Decimal("50000"), Decimal("0.1")
            )

        with pytest.raises(ValueError, match="Best bid and ask must be greater than 0"):
            calculator.calculate_bbo_price(
                "BTCUSDT", "buy", Decimal("50000"), Decimal("-100"), Decimal("0.1")
            )

    def test_invalid_tick_size(self, calculator):
        """Test error handling for invalid tick size."""
        with pytest.raises(ValueError, match="Tick size must be greater than 0"):
            calculator.calculate_bbo_price(
                "BTCUSDT", "buy", Decimal("50000"), Decimal("50001"), Decimal("0")
            )

    def test_invalid_ticks_distance(self, calculator):
        """Test error handling for invalid ticks distance."""
        with pytest.raises(ValueError, match="Ticks distance must be at least 1"):
            calculator.calculate_bbo_price(
                "BTCUSDT", "buy", Decimal("50000"), Decimal("50001"), Decimal("0.1"), ticks_distance=0
            )

        with pytest.raises(ValueError, match="Ticks distance must be at least 1"):
            calculator.calculate_bbo_price(
                "BTCUSDT", "buy", Decimal("50000"), Decimal("50001"), Decimal("0.1"), ticks_distance=-1
            )

    def test_empty_symbol(self, calculator):
        """Test error handling for empty symbol."""
        with pytest.raises(ValueError, match="Symbol cannot be empty"):
            calculator.calculate_bbo_price(
                "", "buy", Decimal("50000"), Decimal("50001"), Decimal("0.1")
            )

    def test_get_tick_size_from_symbol_info_with_filter(self, calculator):
        """Test tick size extraction from SymbolInfo with price filter."""
        price_filter = PriceFilter(
            min_price=Decimal("0.1"),
            max_price=Decimal("100000"),
            tick_size=Decimal("0.1")
        )

        symbol_info = SymbolInfo(
            symbol="BTCUSDT",
            base_asset="BTC",
            quote_asset="USDT",
            status="TRADING",
            price_precision=1,
            quantity_precision=3,
            min_quantity=Decimal("0.001"),
            max_quantity=Decimal("1000"),
            min_notional=Decimal("10"),
            max_notional=Decimal("1000000"),
            tick_size=Decimal("0.05"),  # Different from filter
            step_size=Decimal("0.001"),
            price_filter=price_filter
        )

        # Should prefer price filter tick size
        tick_size = calculator.get_tick_size_from_symbol_info(symbol_info)
        assert tick_size == Decimal("0.1")

    def test_get_tick_size_from_symbol_info_without_filter(self, calculator):
        """Test tick size extraction from SymbolInfo without price filter."""
        symbol_info = SymbolInfo(
            symbol="ETHUSDT",
            base_asset="ETH",
            quote_asset="USDT",
            status="TRADING",
            price_precision=2,
            quantity_precision=3,
            min_quantity=Decimal("0.001"),
            max_quantity=Decimal("1000"),
            min_notional=Decimal("10"),
            max_notional=Decimal("1000000"),
            tick_size=Decimal("0.01"),
            step_size=Decimal("0.001")
        )

        # Should use direct tick size
        tick_size = calculator.get_tick_size_from_symbol_info(symbol_info)
        assert tick_size == Decimal("0.01")

    def test_get_tick_size_from_symbol_info_error(self, calculator):
        """Test error when tick size is not available."""
        symbol_info = SymbolInfo(
            symbol="INVALID",
            base_asset="INV",
            quote_asset="USDT",
            status="TRADING",
            price_precision=2,
            quantity_precision=3,
            min_quantity=Decimal("0.001"),
            max_quantity=Decimal("1000"),
            min_notional=Decimal("10"),
            max_notional=Decimal("1000000"),
            tick_size=Decimal("0"),  # Invalid tick size
            step_size=Decimal("0.001")
        )

        with pytest.raises(ValueError, match="Tick size not available"):
            calculator.get_tick_size_from_symbol_info(symbol_info)


class TestConvenienceFunctions:
    """Test suite for convenience functions."""

    def test_calculate_bbo_price_function(self):
        """Test convenience function for BBO price calculation."""
        symbol = "BTCUSDT"
        side = "buy"
        best_bid = Decimal("50000.0")
        best_ask = Decimal("50000.5")
        tick_size = Decimal("0.1")

        bbo_price = calculate_bbo_price(symbol, side, best_bid, best_ask, tick_size)
        assert bbo_price == Decimal("50000.1")

    def test_create_bbo_order(self):
        """Test create_bbo_order convenience function."""
        symbol = "BTCUSDT"
        side = "buy"
        quantity = Decimal("0.001")
        best_bid = Decimal("50000.0")
        best_ask = Decimal("50000.5")
        tick_size = Decimal("0.1")

        order = create_bbo_order(
            symbol=symbol,
            side=side,
            quantity=quantity,
            best_bid=best_bid,
            best_ask=best_ask,
            tick_size=tick_size,
            client_order_id="test123",
            position_side="LONG"
        )

        assert order.symbol == symbol
        assert order.side == "buy"
        assert order.order_type == "limit"
        assert order.quantity == quantity
        assert order.price == Decimal("50000.1")
        assert order.time_in_force == "gtc"
        assert order.client_order_id == "test123"
        assert order.position_side == "LONG"

    def test_create_bbo_order_sell(self):
        """Test create_bbo_order for sell orders."""
        order = create_bbo_order(
            symbol="ETHUSDT",
            side="sell",
            quantity=Decimal("1.0"),
            best_bid=Decimal("2999.0"),
            best_ask=Decimal("3000.0"),
            tick_size=Decimal("0.01")
        )

        assert order.side == "sell"
        assert order.price == Decimal("2999.99")
        assert order.position_side is None

    def test_create_bbo_order_with_ticks_distance(self):
        """Test create_bbo_order with custom ticks distance."""
        # BUY with 3 ticks distance
        order = create_bbo_order(
            symbol="BTCUSDT",
            side="buy",
            quantity=Decimal("0.001"),
            best_bid=Decimal("50000.0"),
            best_ask=Decimal("50000.5"),
            tick_size=Decimal("0.1"),
            ticks_distance=3
        )

        assert order.symbol == "BTCUSDT"
        assert order.side == "buy"
        assert order.price == Decimal("50000.3")  # market + (0.1 * 3)

        # SELL with 5 ticks distance
        order = create_bbo_order(
            symbol="ETHUSDT",
            side="sell",
            quantity=Decimal("1.0"),
            best_bid=Decimal("2999.0"),
            best_ask=Decimal("3000.0"),
            tick_size=Decimal("0.01"),
            ticks_distance=5
        )

        assert order.side == "sell"
        assert order.price == Decimal("2999.95")  # market - (0.01 * 5)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
