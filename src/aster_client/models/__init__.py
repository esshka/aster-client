"""
Data models for Aster client.

This package contains all data structures used throughout the Aster client,
following the state-first principle with immutable data structures.
"""

from .config import ConnectionConfig, RetryConfig
from .orders import OrderRequest, OrderResponse, PositionMode, ClosePositionResult
from .account import AccountInfo, AccountAsset, Position, Balance, BalanceV2
from .market import MarkPrice, SymbolInfo, LeverageBracket

__all__ = [
    # Configuration
    "ConnectionConfig",
    "RetryConfig",
    # Orders
    "OrderRequest",
    "OrderResponse",
    "PositionMode",
    "ClosePositionResult",
    # Account
    "AccountInfo",
    "AccountAsset",
    "Position",
    "Balance",
    "BalanceV2",
    # Market
    "MarkPrice",
    "SymbolInfo",
    "LeverageBracket",
]