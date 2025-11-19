"""
Aster Client - Python client for Aster DEX API.

This package provides a simple and efficient client for interacting with
the Aster DEX futures trading API.
"""

from .account_client import AsterClient, create_aster_client
from .account_pool import AccountPool, AccountConfig, AccountResult
from .public_client import AsterPublicClient
from .models import (
    # Configuration
    ConnectionConfig,
    RetryConfig,
    # Orders
    OrderRequest,
    OrderResponse,
    PositionMode,
    # Account
    AccountInfo,
    Position,
    Balance,
)
from .trades import (
    Trade,
    TradeOrder,
    TradeStatus,
    create_trade,
    calculate_tp_sl_prices,
    wait_for_order_fill,
)

__all__ = [
    "AsterClient",
    "create_aster_client",
    "AccountPool",
    "AccountConfig",
    "AccountResult",
    "AsterPublicClient",
    "ConnectionConfig",
    "RetryConfig",
    "OrderRequest",
    "OrderResponse",
    "PositionMode",
    "AccountInfo",
    "Position",
    "Balance",
    "Trade",
    "TradeOrder",
    "TradeStatus",
    "create_trade",
    "calculate_tp_sl_prices",
    "wait_for_order_fill",
]