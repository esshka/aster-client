# -*- coding: utf-8 -*-
"""
Unit tests for BBO order retry logic.

Tests the place_bbo_order_with_retry method and related functionality.
"""

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from aster_client.account_client import (
    AsterClient,
    BBORetryExhausted,
    BBOPriceChaseExceeded,
)
from aster_client.models.orders import OrderResponse


@pytest.fixture
def mock_order_response():
    """Create a mock OrderResponse."""
    return OrderResponse(
        order_id="12345",
        client_order_id=None,
        symbol="BTCUSDT",
        side="buy",
        order_type="limit",
        quantity=Decimal("0.001"),
        price=Decimal("49999.9"),
        status="NEW",
        filled_quantity=Decimal("0"),
        remaining_quantity=Decimal("0.001"),
        average_price=None,
        timestamp=1234567890
    )


@pytest.fixture
def mock_filled_order_response():
    """Create a mock filled OrderResponse."""
    return OrderResponse(
        order_id="12345",
        client_order_id=None,
        symbol="BTCUSDT",
        side="buy",
        order_type="limit",
        quantity=Decimal("0.001"),
        price=Decimal("49999.9"),
        status="FILLED",
        filled_quantity=Decimal("0.001"),
        remaining_quantity=Decimal("0"),
        average_price=Decimal("49999.9"),
        timestamp=1234567890
    )


class TestBBORetryLogic:
    """Test suite for BBO order retry logic."""

    @pytest.mark.asyncio
    async def test_fills_immediately(self, mock_order_response, mock_filled_order_response):
        """Test BBO order that fills on first attempt."""
        with patch.object(AsterClient, '__init__', lambda x, *args, **kwargs: None):
            client = AsterClient.__new__(AsterClient)
            client._bbo_calculator = MagicMock()
            client._bbo_calculator.get_bbo.return_value = (
                Decimal("50000.0"),  # best_bid
                Decimal("50001.0"),  # best_ask
            )
            client._bbo_calculator.calculate_bbo_price.return_value = Decimal("49999.9")
            
            client.place_order = AsyncMock(return_value=mock_order_response)
            client.get_order = AsyncMock(return_value=mock_filled_order_response)
            client.cancel_order = AsyncMock()
            
            result = await client.place_bbo_order_with_retry(
                symbol="BTCUSDT",
                side="buy",
                quantity=Decimal("0.001"),
                tick_size=Decimal("0.1"),
                fill_timeout_ms=10,  # Short timeout for test
            )
            
            assert result.status == "FILLED"
            assert result.order_id == "12345"
            # Should not have cancelled anything
            client.cancel_order.assert_not_called()

    @pytest.mark.asyncio
    async def test_fills_on_retry(self, mock_order_response, mock_filled_order_response):
        """Test BBO order that fills on second attempt."""
        with patch.object(AsterClient, '__init__', lambda x, *args, **kwargs: None):
            client = AsterClient.__new__(AsterClient)
            client._bbo_calculator = MagicMock()
            client._bbo_calculator.get_bbo.return_value = (
                Decimal("50000.0"),
                Decimal("50001.0"),
            )
            client._bbo_calculator.calculate_bbo_price.return_value = Decimal("49999.9")
            
            unfilled_response = OrderResponse(
                order_id="12345",
                client_order_id=None,
                symbol="BTCUSDT",
                side="buy",
                order_type="limit",
                quantity=Decimal("0.001"),
                price=Decimal("49999.9"),
                status="NEW",  # Not filled
                filled_quantity=Decimal("0"),
                remaining_quantity=Decimal("0.001"),
                average_price=None,
                timestamp=1234567890
            )
            
            # First attempt: not filled, second attempt: filled
            client.place_order = AsyncMock(return_value=mock_order_response)
            client.get_order = AsyncMock(side_effect=[unfilled_response, mock_filled_order_response])
            client.cancel_order = AsyncMock()
            
            result = await client.place_bbo_order_with_retry(
                symbol="BTCUSDT",
                side="buy",
                quantity=Decimal("0.001"),
                tick_size=Decimal("0.1"),
                max_retries=2,
                fill_timeout_ms=10,
            )
            
            assert result.status == "FILLED"
            # Should have cancelled the first order
            assert client.cancel_order.call_count == 1

    @pytest.mark.asyncio
    async def test_max_retries_exhausted(self, mock_order_response):
        """Test BBORetryExhausted when all retries fail."""
        with patch.object(AsterClient, '__init__', lambda x, *args, **kwargs: None):
            client = AsterClient.__new__(AsterClient)
            client._bbo_calculator = MagicMock()
            client._bbo_calculator.get_bbo.return_value = (
                Decimal("50000.0"),
                Decimal("50001.0"),
            )
            client._bbo_calculator.calculate_bbo_price.return_value = Decimal("49999.9")
            
            unfilled_response = OrderResponse(
                order_id="12345",
                client_order_id=None,
                symbol="BTCUSDT",
                side="buy",
                order_type="limit",
                quantity=Decimal("0.001"),
                price=Decimal("49999.9"),
                status="NEW",
                filled_quantity=Decimal("0"),
                remaining_quantity=Decimal("0.001"),
                average_price=None,
                timestamp=1234567890
            )
            
            # Never fills
            client.place_order = AsyncMock(return_value=mock_order_response)
            client.get_order = AsyncMock(return_value=unfilled_response)
            client.cancel_order = AsyncMock()
            
            with pytest.raises(BBORetryExhausted) as exc_info:
                await client.place_bbo_order_with_retry(
                    symbol="BTCUSDT",
                    side="buy",
                    quantity=Decimal("0.001"),
                    tick_size=Decimal("0.1"),
                    max_retries=2,
                    fill_timeout_ms=10,
                )
            
            assert "not filled after 3 attempts" in str(exc_info.value)
            # Should have cancelled 3 orders (2 retries + 1 final)
            assert client.cancel_order.call_count == 3

    @pytest.mark.asyncio
    async def test_price_chase_exceeded(self, mock_order_response):
        """Test BBOPriceChaseExceeded when price moves too far."""
        with patch.object(AsterClient, '__init__', lambda x, *args, **kwargs: None):
            client = AsterClient.__new__(AsterClient)
            client._bbo_calculator = MagicMock()
            
            # get_bbo is called:
            # 1. At start to get original reference
            # 2. In loop iteration 0 (first attempt)
            # 3. In loop iteration 1 (second attempt - price moved)
            client._bbo_calculator.get_bbo.side_effect = [
                (Decimal("50000.0"), Decimal("50001.0")),  # Original (at start)
                (Decimal("50000.0"), Decimal("50001.0")),  # Loop attempt 0
                (Decimal("50500.0"), Decimal("50501.0")),  # Loop attempt 1 - 1% move (exceeds 0.5%)
            ]
            client._bbo_calculator.calculate_bbo_price.return_value = Decimal("49999.9")
            
            unfilled_response = OrderResponse(
                order_id="12345",
                client_order_id=None,
                symbol="BTCUSDT",
                side="buy",
                order_type="limit",
                quantity=Decimal("0.001"),
                price=Decimal("49999.9"),
                status="NEW",
                filled_quantity=Decimal("0"),
                remaining_quantity=Decimal("0.001"),
                average_price=None,
                timestamp=1234567890
            )
            
            client.place_order = AsyncMock(return_value=mock_order_response)
            client.get_order = AsyncMock(return_value=unfilled_response)
            client.cancel_order = AsyncMock()
            
            with pytest.raises(BBOPriceChaseExceeded) as exc_info:
                await client.place_bbo_order_with_retry(
                    symbol="BTCUSDT",
                    side="buy",
                    quantity=Decimal("0.001"),
                    tick_size=Decimal("0.1"),
                    max_retries=2,
                    max_chase_percent=0.5,  # 0.5% max
                    fill_timeout_ms=10,
                )
            
            assert "exceeds" in str(exc_info.value)
            # Should have placed one order, then detected chase on retry attempt
            assert client.place_order.call_count == 1
            # Should have cancelled the first order before detecting chase
            assert client.cancel_order.call_count == 1


    @pytest.mark.asyncio
    async def test_no_bbo_prices_available(self):
        """Test ValueError when BBO prices not in cache."""
        with patch.object(AsterClient, '__init__', lambda x, *args, **kwargs: None):
            client = AsterClient.__new__(AsterClient)
            client._bbo_calculator = MagicMock()
            client._bbo_calculator.get_bbo.return_value = None  # No BBO data
            
            with pytest.raises(ValueError) as exc_info:
                await client.place_bbo_order_with_retry(
                    symbol="XYZUSDT",
                    side="buy",
                    quantity=Decimal("0.001"),
                    tick_size=Decimal("0.1"),
                )
            
            assert "not available" in str(exc_info.value)


class TestPriceDeviationCalculation:
    """Test the price deviation calculation helper."""

    def test_calculate_price_deviation_increase(self):
        """Test deviation calculation for price increase."""
        with patch.object(AsterClient, '__init__', lambda x, *args, **kwargs: None):
            client = AsterClient.__new__(AsterClient)
            
            # 1% increase
            deviation = client._calculate_price_deviation(
                Decimal("100.0"),
                Decimal("101.0")
            )
            assert abs(deviation - 1.0) < 0.001

    def test_calculate_price_deviation_decrease(self):
        """Test deviation calculation for price decrease."""
        with patch.object(AsterClient, '__init__', lambda x, *args, **kwargs: None):
            client = AsterClient.__new__(AsterClient)
            
            # 2% decrease
            deviation = client._calculate_price_deviation(
                Decimal("100.0"),
                Decimal("98.0")
            )
            assert abs(deviation - 2.0) < 0.001

    def test_calculate_price_deviation_zero_original(self):
        """Test deviation calculation with zero original price."""
        with patch.object(AsterClient, '__init__', lambda x, *args, **kwargs: None):
            client = AsterClient.__new__(AsterClient)
            
            deviation = client._calculate_price_deviation(
                Decimal("0"),
                Decimal("100.0")
            )
            assert deviation == 0.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
