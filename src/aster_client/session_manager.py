"""
Session management for Aster client.

Handles connection lifecycle, session creation, and resource cleanup
following the pure core/impure edges principle.
"""

import aiohttp
from typing import Optional
from contextlib import asynccontextmanager

from .models.config import ConnectionConfig


class SessionManager:
    """Manages HTTP session lifecycle for Aster client."""

    def __init__(self, config: ConnectionConfig):
        """Initialize session manager with configuration."""
        self._config = config
        self._session: Optional[aiohttp.ClientSession] = None

    async def create_session(self) -> aiohttp.ClientSession:
        """Create and configure HTTP session."""
        if self._session is not None and not self._session.closed:
            return self._session

        connector = aiohttp.TCPConnector(
            limit=100,
            limit_per_host=20,
            ttl_dns_cache=300,
            use_dns_cache=True,
        )

        timeout = aiohttp.ClientTimeout(total=self._config.timeout)

        headers = {
            "User-Agent": "aster-client/1.0",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

        self._session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers=headers,
        )

        return self._session

    async def close_session(self) -> None:
        """Close HTTP session and cleanup resources."""
        if self._session and not self._session.closed:
            await self._session.close()
        self._session = None

    @property
    def session(self) -> Optional[aiohttp.ClientSession]:
        """Get current session without creating one."""
        return self._session

    @asynccontextmanager
    async def managed_session(self):
        """Context manager for automatic session lifecycle management."""
        session = await self.create_session()
        try:
            yield session
        finally:
            await self.close_session()

    async def health_check(self) -> bool:
        """Perform basic health check on session."""
        if not self._session or self._session.closed:
            return False

        try:
            # Simple ping to health endpoint
            async with self._session.get(
                f"{self._config.base_url}/health",
                timeout=aiohttp.ClientTimeout(total=5.0)
            ) as response:
                return response.status == 200
        except (aiohttp.ClientError, aiohttp.ServerTimeoutError, ConnectionError):
            return False
        except Exception:
            return False