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
    base_url: str = "https://api.aster.com"
    timeout: float = 30.0
    simulation: bool = False


@dataclass(frozen=True)
class RetryConfig:
    """Configuration for request retry behavior."""
    max_retries: int = 3
    retry_delay: float = 1.0
    backoff_factor: float = 2.0
    retry_on_status: tuple[int, ...] = (500, 502, 503, 504)