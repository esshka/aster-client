"""
Configuration models for Aster client.

Immutable configuration structures following state-first design.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ConnectionConfig:
    """Configuration for Aster client connection."""
    api_key: str
    api_secret: str
    base_url: str = "https://fapi.asterdex.com"
    timeout: float = 30.0
    simulation: bool = False
    recv_window: int = 5000

    def __post_init__(self):
        """Validate configuration after initialization."""
        self._validate_api_key()
        self._validate_api_secret()

    def _validate_api_key(self):
        """Validate API key format."""
        if not self.api_key:
            raise ValueError("API key cannot be empty")

        # Basic validation - API keys are typically 32-64 characters
        if len(self.api_key) < 20:
            raise ValueError(
                f"API key appears to be too short (expected 20+ characters, got {len(self.api_key)})"
            )

        if len(self.api_key) > 128:
            raise ValueError(
                f"API key appears to be too long (expected max 128 characters, got {len(self.api_key)})"
            )

    def _validate_api_secret(self):
        """Validate API secret format."""
        if not self.api_secret:
            raise ValueError("API secret cannot be empty")

        # Basic validation - API secrets are typically 32-64 characters
        if len(self.api_secret) < 20:
            raise ValueError(
                f"API secret appears to be too short (expected 20+ characters, got {len(self.api_secret)})"
            )

        if len(self.api_secret) > 128:
            raise ValueError(
                f"API secret appears to be too long (expected max 128 characters, got {len(self.api_secret)})"
            )


@dataclass(frozen=True)
class RetryConfig:
    """Configuration for request retry behavior."""
    max_retries: int = 3
    retry_delay: float = 1.0
    backoff_factor: float = 2.0
    retry_on_status: tuple[int, ...] = (500, 502, 503, 504)