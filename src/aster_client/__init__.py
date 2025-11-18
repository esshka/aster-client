"""
Aster Perpetual Trading Client Library

A production-ready Python client for interacting with the Aster perpetual trading platform API.
Enhanced with session management, retry logic, and complete API coverage.
"""

from .account_client import AsterClient
from .public_client import AsterPublicClient as PublicClient
from .auth import ApiCredentials, AsterSigner

__version__ = "2.0.0"
__all__ = [
    "AsterClient",
    "PublicClient",
    "ApiCredentials",
    "AsterSigner",
]