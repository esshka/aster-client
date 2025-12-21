"""
Aster Client - Python client for Aster DEX API.

This package provides a simple and efficient client for interacting with
the Aster DEX futures trading API.
"""

from .account_client import (
    AsterClient,
    create_aster_client,
    BBORetryExhausted,
    BBOPriceChaseExceeded,
)
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
    # Signals
    SignalMessage,
    PositionState,
    PositionSizingConfig,
)
from .trades import (
    Trade,
    TradeOrder,
    TradeStatus,
    create_trade,
    calculate_tp_sl_prices,
    wait_for_order_fill,
)
from .nats_listener import NATSTradeListener, ZMQTradeListener
from .signal_listener import NATSSignalListener, ZMQSignalListener
from .account_ws import AccountWebSocket

__all__ = [
    # Main Clients
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
    # NATS Listeners
    "NATSTradeListener",
    "NATSSignalListener",
    # Backward-compatible aliases
    "ZMQTradeListener",
    "ZMQSignalListener",
    # WebSocket
    "AccountWebSocket",
    "SignalMessage",
    "PositionState",
    "PositionSizingConfig",
    # BBO Exceptions
    "BBORetryExhausted",
    "BBOPriceChaseExceeded",
]