"""
Order-related models for Aster client.

Immutable data structures for order management.
"""

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Optional


class PositionMode(Enum):
    """Position mode enumeration."""
    HEDGED = "hedged"
    NETTED = "netted"


@dataclass(frozen=True)
class OrderRequest:
    """Order request data structure."""
    symbol: str
    side: str  # "buy" or "sell"
    order_type: str  # "limit", "market", etc.
    quantity: Decimal
    price: Optional[Decimal] = None
    time_in_force: Optional[str] = None
    client_order_id: Optional[str] = None


@dataclass(frozen=True)
class OrderResponse:
    """Order response data structure."""
    order_id: str
    client_order_id: Optional[str]
    symbol: str
    side: str
    order_type: str
    quantity: Decimal
    price: Optional[Decimal]
    status: str
    filled_quantity: Decimal
    remaining_quantity: Decimal
    average_price: Optional[Decimal]
    timestamp: int