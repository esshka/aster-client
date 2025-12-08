import pytest
import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from aster_client.bbo import BBOPriceCalculator

@pytest.mark.asyncio
async def test_bbo_singleton():
    """Test that BBOPriceCalculator is a singleton."""
    calc1 = BBOPriceCalculator()
    calc2 = BBOPriceCalculator()
    assert calc1 is calc2
    assert calc1.bbo_cache is calc2.bbo_cache

@pytest.mark.asyncio
async def test_bbo_update_processing():
    """Test processing of BBO update messages."""
    calc = BBOPriceCalculator()
    
    # Mock data
    data = {
        "u": 12345,
        "s": "BTCUSDT",
        "b": "50000.00",
        "B": "1.5",
        "a": "50001.00",
        "A": "2.0"
    }
    
    calc._process_bbo_update(data)
    
    assert "BTCUSDT" in calc.bbo_cache
    bid, ask = calc.get_bbo("BTCUSDT")
    assert bid == Decimal("50000.00")
    assert ask == Decimal("50001.00")

@pytest.mark.asyncio
async def test_calculate_bbo_price_with_cache():
    """Test price calculation using cached values."""
    calc = BBOPriceCalculator()
    calc.bbo_cache["ETHUSDT"] = (Decimal("3000.00"), Decimal("3001.00"))
    
    # Buy order: Bid - 1 tick (place below best bid)
    price = calc.calculate_bbo_price(
        symbol="ETHUSDT",
        side="buy",
        tick_size=Decimal("0.01")
    )
    assert price == Decimal("2999.99")
    
    # Sell order: Ask + 1 tick (place above best ask)
    price = calc.calculate_bbo_price(
        symbol="ETHUSDT",
        side="sell",
        tick_size=Decimal("0.01")
    )
    assert price == Decimal("3001.01")

@pytest.mark.asyncio
async def test_calculate_bbo_price_missing_cache():
    """Test that calculation fails if data is missing and not provided."""
    calc = BBOPriceCalculator()
    # Ensure cache is empty for this symbol
    if "SOLUSDT" in calc.bbo_cache:
        del calc.bbo_cache["SOLUSDT"]
        
    with pytest.raises(ValueError, match="BBO prices not available"):
        calc.calculate_bbo_price(
            symbol="SOLUSDT",
            side="buy",
            tick_size=Decimal("0.01")
        )
