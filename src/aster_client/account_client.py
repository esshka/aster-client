"""
Aster Client - Main orchestration module.

This module provides the main AsterClient class that coordinates
all client functionality while staying under 300 LOC.

The client follows state-first design with clean separation of concerns:
- Data models are immutable structures in models/
- HTTP operations are handled by http_client.py
- Session management is handled by session_manager.py
- API methods are implemented in api_methods.py
- Monitoring and utilities are in dedicated modules
"""

import asyncio
import os
import logging
from typing import Optional

from .api_methods import APIMethods
from .constants import (
    DEFAULT_BASE_URL, DEFAULT_TIMEOUT, DEFAULT_RETRY_DELAY,
    DEFAULT_MAX_RETRIES, SUCCESS_STATUS_CODE, ERROR_STATUS_CODE
)
from .http_client import HttpClient
from .models import (
    AccountInfo, Balance, MarkPrice, OrderRequest, OrderResponse,
    Position, ConnectionConfig, RetryConfig
)
from .monitoring import PerformanceMonitor
from .session_manager import SessionManager

logger = logging.getLogger(__name__)


class AsterClient:
    """
    Main Aster client orchestrator.

    Coordinates all client functionality while maintaining clean
    separation of concerns and keeping implementation minimal.
    """

    def __init__(
        self,
        config: ConnectionConfig,
        retry_config: Optional[RetryConfig] = None,
    ):
        """Initialize Aster client with configuration."""
        self._config = config
        self._session_manager = SessionManager(config)
        self._http_client = HttpClient(config, retry_config)
        self._api_methods = APIMethods(self._http_client)
        self._monitor = PerformanceMonitor()
        self._closed = False

    @classmethod
    def from_env(cls, simulation: bool = False) -> "AsterClient":
        """Create client from environment variables."""
        api_key = os.getenv("ASTER_API_KEY", "")
        api_secret = os.getenv("ASTER_API_SECRET", "")

        recv_window = int(os.getenv("ASTER_RECV_WINDOW", "5000"))

        config = ConnectionConfig(
            api_key=api_key,
            api_secret=api_secret,
            simulation=simulation,
            recv_window=recv_window,
        )

        return cls(config)

    # Account methods
    async def get_account_info(self) -> AccountInfo:
        """Get account information."""
        return await self._execute_with_monitoring(
            self._api_methods.get_account_info, "GET", "/account"
        )

    async def get_positions(self) -> list[Position]:
        """Get all open positions."""
        return await self._execute_with_monitoring(
            self._api_methods.get_positions, "GET", "/positions"
        )

    async def get_balances(self) -> list[Balance]:
        """Get account balances."""
        return await self._execute_with_monitoring(
            self._api_methods.get_balances, "GET", "/balances"
        )

    # Order methods
    async def place_order(self, order: OrderRequest) -> OrderResponse:
        """Place a new order."""
        return await self._execute_with_monitoring(
            self._api_methods.place_order, "POST", "/orders", order
        )

    async def cancel_order(self, order_id: str) -> dict:
        """Cancel an existing order."""
        return await self._execute_with_monitoring(
            self._api_methods.cancel_order, "DELETE", f"/orders/{order_id}", order_id
        )

    async def get_order(self, order_id: str) -> Optional[OrderResponse]:
        """Get order by ID."""
        return await self._execute_with_monitoring(
            self._api_methods.get_order, "GET", f"/orders/{order_id}", order_id
        )

    async def get_orders(self, symbol: Optional[str] = None) -> list[OrderResponse]:
        """Get all orders, optionally filtered by symbol."""
        return await self._execute_with_monitoring(
            self._api_methods.get_orders, "GET", "/orders", symbol
        )

    async def get_mark_price(self, symbol: str) -> Optional[MarkPrice]:
        """Get mark price for symbol."""
        return await self._execute_with_monitoring(
            self._api_methods.get_mark_price, "GET", f"/market/{symbol}/mark_price", symbol
        )

    async def change_position_mode(self, dual_side_position: bool) -> dict:
        """
        Change user's position mode (Hedge Mode or One-way Mode) on every symbol.
        
        Args:
            dual_side_position: True for Hedge Mode, False for One-way Mode
        """
        return await self._execute_with_monitoring(
            self._api_methods.change_position_mode, 
            "POST", 
            "/positionSide/dual", 
            dual_side_position
        )

    async def get_position_mode(self) -> dict:
        """
        Get user's position mode (Hedge Mode or One-way Mode) on every symbol.
        
        Returns:
            Dict containing "dualSidePosition": boolean
        """
        return await self._execute_with_monitoring(
            self._api_methods.get_position_mode, "GET", "/positionSide/dual"
        )

    # Monitoring and health
    async def health_check(self) -> bool:
        """Check client health."""
        try:
            await self._session_manager.create_session()
            return await self._session_manager.health_check()
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False

    def get_statistics(self):
        """Get performance statistics."""
        return self._monitor.statistics

    async def close(self) -> None:
        """Close client and cleanup resources."""
        if not self._closed:
            await self._session_manager.close_session()
            self._closed = True
            logger.info("Aster client closed")

    async def _execute_with_monitoring(
        self, api_method, method: str, endpoint: str, *args, **kwargs
    ):
        """Execute API method with performance monitoring."""
        if self._closed:
            raise RuntimeError("Client is closed")

        start_time = asyncio.get_event_loop().time()
        session = await self._session_manager.create_session()

        try:
            result = await api_method(session, *args, **kwargs)
            duration_ms = (asyncio.get_event_loop().time() - start_time) * 1000

            # Record success metrics
            self._monitor.record_request(endpoint, method, SUCCESS_STATUS_CODE, duration_ms)
            return result

        except Exception as e:
            duration_ms = (asyncio.get_event_loop().time() - start_time) * 1000
            status_code = getattr(e, "status_code", ERROR_STATUS_CODE)

            # Record error metrics
            self._monitor.record_request(endpoint, method, status_code, duration_ms)
            raise

    # Context manager support
    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    def __del__(self):
        """Cleanup on deletion."""
        if hasattr(self, '_closed') and not self._closed:
            logger.warning("AsterClient not properly closed - call close() explicitly")


def create_aster_client(
    api_key: str,
    api_secret: str,
    base_url: str = DEFAULT_BASE_URL,
    timeout: float = DEFAULT_TIMEOUT,
    simulation: bool = False,
    recv_window: int = 5000,
    max_retries: int = DEFAULT_MAX_RETRIES,
    retry_delay: float = DEFAULT_RETRY_DELAY,
) -> AsterClient:
    """
    Factory function to create Aster client with common configuration.

    Args:
        api_key: API key for authentication
        api_secret: API secret for authentication
        base_url: Base URL for API endpoints
        timeout: Request timeout in seconds
        simulation: Enable simulation mode
        recv_window: Receive window in milliseconds (default 5000)
        max_retries: Maximum number of retry attempts
        retry_delay: Initial delay between retries in seconds

    Returns:
        Configured AsterClient instance
    """
    config = ConnectionConfig(
        api_key=api_key,
        api_secret=api_secret,
        base_url=base_url,
        timeout=timeout,
        simulation=simulation,
        recv_window=recv_window,
    )

    retry_config = RetryConfig(
        max_retries=max_retries,
        retry_delay=retry_delay,
    )

    return AsterClient(config, retry_config)