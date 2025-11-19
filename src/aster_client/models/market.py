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
class PriceFilter:
    """Price filter rules."""
    min_price: Decimal
    max_price: Decimal
    tick_size: Decimal


@dataclass(frozen=True)
class LotSizeFilter:
    """Lot size filter rules."""
    min_qty: Decimal
    max_qty: Decimal
    step_size: Decimal


@dataclass(frozen=True)
class MarketLotSizeFilter:
    """Market lot size filter rules."""
    min_qty: Decimal
    max_qty: Decimal
    step_size: Decimal


@dataclass(frozen=True)
class MaxNumOrdersFilter:
    """Maximum number of orders filter."""
    limit: int


@dataclass(frozen=True)
class MaxNumAlgoOrdersFilter:
    """Maximum number of algo orders filter."""
    limit: int


@dataclass(frozen=True)
class PercentPriceFilter:
    """Percent price filter rules."""
    multiplier_up: Decimal
    multiplier_down: Decimal
    multiplier_decimal: int


@dataclass(frozen=True)
class MinNotionalFilter:
    """Minimum notional value filter."""
    notional: Decimal


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
    price_filter: Optional[PriceFilter] = None
    lot_size_filter: Optional[LotSizeFilter] = None
    market_lot_size_filter: Optional[MarketLotSizeFilter] = None
    max_num_orders_filter: Optional[MaxNumOrdersFilter] = None
    max_num_algo_orders_filter: Optional[MaxNumAlgoOrdersFilter] = None
    percent_price_filter: Optional[PercentPriceFilter] = None
    min_notional_filter: Optional[MinNotionalFilter] = None


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