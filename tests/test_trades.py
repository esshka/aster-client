"""
Unit tests for the trades module.

Tests cover:
- TP/SL price calculation
- Price rounding to tick size
- Trade creation workflow
- Error handling
- Order fill waiting
"""

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from aster_client.trades import (
    Trade,
    TradeOrder,
    TradeStatus,
    calculate_tp_sl_prices,
    _round_to_tick,
    wait_for_order_fill,
    create_trade,
)
from aster_client.models.orders import OrderResponse


class TestTPSLCalculation:
    """Test TP/SL price calculation logic."""
    
    def test_buy_tp_sl_calculation(self):
        """Test TP/SL calculation for BUY orders."""
        entry_price = Decimal("3500.00")
        tp_percent = 1.0  # 1%
        sl_percent = 0.5  # 0.5%
        tick_size = Decimal("0.01")
        
        tp_price, sl_price = calculate_tp_sl_prices(
            entry_price, "buy", tp_percent, sl_percent, tick_size
        )
        
        # For BUY: TP above entry, SL below entry
        assert tp_price > entry_price
        assert sl_price < entry_price
        assert tp_price == Decimal("3535.00")  # 3500 * 1.01
        assert sl_price == Decimal("3482.50")  # 3500 * 0.995
    
    def test_sell_tp_sl_calculation(self):
        """Test TP/SL calculation for SELL orders."""
        entry_price = Decimal("3500.00")
        tp_percent = 1.0
        sl_percent = 0.5
        tick_size = Decimal("0.01")
        
        tp_price, sl_price = calculate_tp_sl_prices(
            entry_price, "sell", tp_percent, sl_percent, tick_size
        )
        
        # For SELL: TP below entry, SL above entry
        assert tp_price < entry_price
        assert sl_price > entry_price
        assert tp_price == Decimal("3482.50")  # 3500 * 0.995
        assert sl_price == Decimal("3535.00")  # 3500 * 1.01
    
    def test_tp_sl_with_different_tick_size(self):
        """Test TP/SL calculation with different tick sizes."""
        entry_price = Decimal("50000.00")
        tp_percent = 2.0
        sl_percent = 1.0
        tick_size = Decimal("0.10")
        
        tp_price, sl_price = calculate_tp_sl_prices(
            entry_price, "buy", tp_percent, sl_percent, tick_size
        )
        
        # Verify prices are rounded to tick size
        assert (tp_price % tick_size) == 0
        assert (sl_price % tick_size) == 0
        assert tp_price == Decimal("51000.00")  # 50000 * 1.02
        assert sl_price == Decimal("49500.00")  # 50000 * 0.99
    
    def test_invalid_side(self):
        """Test that invalid side raises ValueError."""
        with pytest.raises(ValueError, match="Side must be"):
            calculate_tp_sl_prices(
                Decimal("3500"), "invalid", 1.0, 0.5, Decimal("0.01")
            )
    
    def test_negative_entry_price(self):
        """Test that negative entry price raises ValueError."""
        with pytest.raises(ValueError, match="Entry price must be positive"):
            calculate_tp_sl_prices(
                Decimal("-3500"), "buy", 1.0, 0.5, Decimal("0.01")
            )
    
    def test_negative_tp_percent(self):
        """Test that negative TP percent raises ValueError."""
        with pytest.raises(ValueError, match="TP percent must be positive"):
            calculate_tp_sl_prices(
                Decimal("3500"), "buy", -1.0, 0.5, Decimal("0.01")
            )
    
    def test_negative_sl_percent(self):
        """Test that negative SL percent raises ValueError."""
        with pytest.raises(ValueError, match="SL percent must be positive"):
            calculate_tp_sl_prices(
                Decimal("3500"), "buy", 1.0, -0.5, Decimal("0.01")
            )


class TestPriceRounding:
    """Test price rounding to tick size."""
    
    def test_round_to_tick_basic(self):
        """Test basic price rounding."""
        price = Decimal("3500.567")
        tick_size = Decimal("0.01")
        
        rounded = _round_to_tick(price, tick_size)
        
        assert rounded == Decimal("3500.56")
    
    def test_round_to_tick_larger_tick(self):
        """Test rounding with larger tick size."""
        price = Decimal("50123.45")
        tick_size = Decimal("0.10")
        
        rounded = _round_to_tick(price, tick_size)
        
        assert rounded == Decimal("50123.40")
    
    def test_round_to_tick_exact_match(self):
        """Test rounding when price already matches tick size."""
        price = Decimal("3500.00")
        tick_size = Decimal("0.01")
        
        rounded = _round_to_tick(price, tick_size)
        
        assert rounded == price


class TestWaitForOrderFill:
    """Test order fill waiting logic."""
    
    @pytest.mark.asyncio
    async def test_order_fills_successfully(self):
        """Test successful order fill."""
        # Mock client
        mock_client = AsyncMock()
        filled_order = OrderResponse(
            order_id="12345",
            client_order_id=None,
            symbol="ETHUSDT",
            side="buy",
            order_type="limit",
            quantity=Decimal("0.1"),
            price=Decimal("3500"),
            status="FILLED",
            filled_quantity=Decimal("0.1"),
            remaining_quantity=Decimal("0"),
            average_price=Decimal("3500.50"),
            timestamp=1234567890,
        )
        mock_client.get_order.return_value = filled_order
        
        # Wait for fill
        result = await wait_for_order_fill(
            client=mock_client,
            symbol="ETHUSDT",
            order_id="12345",
            timeout=10.0,
            poll_interval=0.1,
        )
        
        assert result is not None
        assert result.status == "FILLED"
        assert result.average_price == Decimal("3500.50")
    
    @pytest.mark.asyncio
    async def test_order_cancelled(self):
        """Test order cancel detection."""
        mock_client = AsyncMock()
        cancelled_order = OrderResponse(
            order_id="12345",
            client_order_id=None,
            symbol="ETHUSDT",
            side="buy",
            order_type="limit",
            quantity=Decimal("0.1"),
            price=Decimal("3500"),
            status="CANCELED",
            filled_quantity=Decimal("0"),
            remaining_quantity=Decimal("0.1"),
            average_price=None,
            timestamp=1234567890,
        )
        mock_client.get_order.return_value = cancelled_order
        
        result = await wait_for_order_fill(
            client=mock_client,
            symbol="ETHUSDT",
            order_id="12345",
            timeout=10.0,
            poll_interval=0.1,
        )
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_order_timeout(self):
        """Test timeout when order doesn't fill."""
        mock_client = AsyncMock()
        pending_order = OrderResponse(
            order_id="12345",
            client_order_id=None,
            symbol="ETHUSDT",
            side="buy",
            order_type="limit",
            quantity=Decimal("0.1"),
            price=Decimal("3500"),
            status="PENDING",
            filled_quantity=Decimal("0"),
            remaining_quantity=Decimal("0.1"),
            average_price=None,
            timestamp=1234567890,
        )
        mock_client.get_order.return_value = pending_order
        
        result = await wait_for_order_fill(
            client=mock_client,
            symbol="ETHUSDT",
            order_id="12345",
            timeout=0.5,  # Short timeout
            poll_interval=0.1,
        )
        
        assert result is None


class TestTradeCreation:
    """Test complete trade creation workflow."""
    
    @pytest.mark.asyncio
    async def test_successful_trade_creation(self):
        """Test successful trade creation with all orders placed."""
        # Mock client
        mock_client = AsyncMock()
        
        # Mock BBO order placement
        entry_response = OrderResponse(
            order_id="entry123",
            client_order_id=None,
            symbol="ETHUSDT",
            side="buy",
            order_type="limit",
            quantity=Decimal("0.1"),
            price=Decimal("3500.50"),
            status="NEW",
            filled_quantity=Decimal("0"),
            remaining_quantity=Decimal("0.1"),
            average_price=None,
            timestamp=1234567890,
        )
        mock_client.place_bbo_order.return_value = entry_response
        
        # Mock filled order for wait
        filled_entry = OrderResponse(
            order_id="entry123",
            client_order_id=None,
            symbol="ETHUSDT",
            side="buy",
            order_type="limit",
            quantity=Decimal("0.1"),
            price=Decimal("3500.50"),
            status="FILLED",
            filled_quantity=Decimal("0.1"),
            remaining_quantity=Decimal("0"),
            average_price=Decimal("3501.00"),
            timestamp=1234567890,
        )
        mock_client.get_order.return_value = filled_entry
        
        # Mock TP/SL placements
        tp_response = OrderResponse(
            order_id="tp123",
            client_order_id=None,
            symbol="ETHUSDT",
            side="sell",
            order_type="limit",
            quantity=Decimal("0.1"),
            price=Decimal("3536.01"),
            status="NEW",
            filled_quantity=Decimal("0"),
            remaining_quantity=Decimal("0.1"),
            average_price=None,
            timestamp=1234567890,
        )
        
        sl_response = OrderResponse(
            order_id="sl123",
            client_order_id=None,
            symbol="ETHUSDT",
            side="sell",
            order_type="stop_market",
            quantity=Decimal("0.1"),
            price=Decimal("3483.50"),
            status="NEW",
            filled_quantity=Decimal("0"),
            remaining_quantity=Decimal("0.1"),
            average_price=None,
            timestamp=1234567890,
        )
        
        mock_client.place_order.side_effect = [tp_response, sl_response]
        
        # Create trade
        trade = await create_trade(
            client=mock_client,
            symbol="ETHUSDT",
            side="buy",
            quantity=Decimal("0.1"),
            market_price=Decimal("3500.00"),
            tick_size=Decimal("0.01"),
            tp_percent=1.0,
            sl_percent=0.5,
            fill_timeout=10.0,
            poll_interval=0.1,
        )
        
        # Verify trade structure
        assert trade.status == TradeStatus.ACTIVE
        assert trade.symbol == "ETHUSDT"
        assert trade.side == "buy"
        assert trade.entry_order.order_id == "entry123"
        assert trade.take_profit_order.order_id == "tp123"
        assert trade.stop_loss_order.order_id == "sl123"
    
    @pytest.mark.asyncio
    async def test_trade_creation_entry_timeout(self):
        """Test trade creation when entry order times out."""
        mock_client = AsyncMock()
        
        # Mock BBO order placement
        entry_response = OrderResponse(
            order_id="entry123",
            client_order_id=None,
            symbol="ETHUSDT",
            side="buy",
            order_type="limit",
            quantity=Decimal("0.1"),
            price=Decimal("3500.50"),
            status="NEW",
            filled_quantity=Decimal("0"),
            remaining_quantity=Decimal("0.1"),
            average_price=None,
            timestamp=1234567890,
        )
        mock_client.place_bbo_order.return_value = entry_response
        
        # Mock pending order (never fills)
        pending_order = OrderResponse(
            order_id="entry123",
            client_order_id=None,
            symbol="ETHUSDT",
            side="buy",
            order_type="limit",
            quantity=Decimal("0.1"),
            price=Decimal("3500.50"),
            status="PENDING",
            filled_quantity=Decimal("0"),
            remaining_quantity=Decimal("0.1"),
            average_price=None,
            timestamp=1234567890,
        )
        mock_client.get_order.return_value = pending_order
        
        # Create trade with short timeout
        trade = await create_trade(
            client=mock_client,
            symbol="ETHUSDT",
            side="buy",
            quantity=Decimal("0.1"),
            market_price=Decimal("3500.00"),
            tick_size=Decimal("0.01"),
            tp_percent=1.0,
            sl_percent=0.5,
            fill_timeout=0.5,
            poll_interval=0.1,
        )
        
        # Verify trade is cancelled
        assert trade.status == TradeStatus.CANCELLED
        assert trade.entry_order.error is not None


class TestTradeDataStructures:
    """Test trade data structures and serialization."""
    
    def test_trade_to_dict(self):
        """Test trade serialization to dict."""
        trade = Trade(
            trade_id="test123",
            symbol="ETHUSDT",
            side="buy",
            tp_percent=1.0,
            sl_percent=0.5,
        )
        
        trade.entry_order.order_id = "entry123"
        trade.entry_order.price = Decimal("3500.00")
        trade.entry_order.size = Decimal("0.1")
        
        data = trade.to_dict()
        
        assert data["trade_id"] == "test123"
        assert data["symbol"] == "ETHUSDT"
        assert data["side"] == "buy"
        assert data["entry_order"]["order_id"] == "entry123"
        assert data["entry_order"]["price"] == "3500.00"
    
    def test_trade_status_enum(self):
        """Test trade status enumeration."""
        assert TradeStatus.PENDING.value == "pending"
        assert TradeStatus.ACTIVE.value == "active"
        assert TradeStatus.COMPLETED.value == "completed"
        assert TradeStatus.CANCELLED.value == "cancelled"
        assert TradeStatus.FAILED.value == "failed"
