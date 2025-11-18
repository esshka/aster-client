"""
Account-related models for Aster client.

Immutable data structures for account and position information.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import List, Optional


@dataclass(frozen=True)
class AccountInfo:
    """Account information data structure."""
    account_id: str
    account_type: str
    status: str
    buying_power: Decimal
    day_trading_buying_power: Decimal
    reg_t_buying_power: Decimal
    cash: Decimal
    portfolio_value: Decimal
    equity: Decimal
    last_equity: Decimal
    multiplier: str
    initial_margin: Decimal
    maintenance_margin: Decimal
    long_market_value: Decimal
    short_market_value: Decimal
    accrued_fees: Decimal
    portfolio_equity: Decimal


@dataclass(frozen=True)
class AccountAsset:
    """Account asset data structure."""
    asset_id: str
    exchange: str
    symbol: str
    asset_currency: str
    quantity: Decimal
    avg_entry_price: Decimal
    side: str
    market_value: Decimal
    cost_basis: Decimal
    unrealized_pl: Decimal
    unrealized_plpc: Decimal
    current_price: Decimal
    lastday_price: Decimal
    change_today: Decimal


@dataclass(frozen=True)
class Position:
    """Position data structure."""
    asset_id: str
    symbol: str
    exchange: str
    asset_class: str
    avg_entry_price: Decimal
    quantity: Decimal
    side: str
    market_value: Decimal
    cost_basis: Decimal
    unrealized_pl: Decimal
    unrealized_plpc: Decimal
    current_price: Decimal
    lastday_price: Decimal
    change_today: Decimal


@dataclass(frozen=True)
class Balance:
    """Balance data structure."""
    asset_id: str
    currency: str
    cash: Decimal
    tradeable: bool
    pending_buy: Decimal
    pending_sell: Decimal