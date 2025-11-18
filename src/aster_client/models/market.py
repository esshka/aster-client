"""
Market-related models for Aster client.

Immutable data structures for market data and symbol information.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import List, Optional


@dataclass(frozen=True)
class MarkPrice:
    """Mark price data structure."""
    symbol: str
    mark_price: Decimal
    timestamp: int
    funding_rate: Optional[Decimal] = None
    next_funding_time: Optional[int] = None


@dataclass(frozen=True)
class SymbolInfo:
    """Symbol information data structure."""
    symbol: str
    base_asset: str
    quote_asset: str
    status: str
    price_precision: int
    quantity_precision: int
    min_quantity: Decimal
    max_quantity: Decimal
    min_notional: Decimal
    max_notional: Decimal
    tick_size: Decimal
    step_size: Decimal
    contract_type: Optional[str] = None
    delivery_date: Optional[int] = None


@dataclass(frozen=True)
class LeverageBracket:
    """Leverage bracket data structure."""
    symbol: str
    bracket: int
    initial_leverage: Decimal
    notional_cap: Decimal
    notional_floor: Decimal
    max_notional_value: Decimal
    maintenance_margin_rate: Decimal