"""
Authentication and signing utilities for Aster API
"""

from dataclasses import dataclass
from typing import Dict, Any, Optional
import hashlib
import hmac
import time
from urllib.parse import urlencode


@dataclass
class ApiCredentials:
    """Container for API credentials"""
    api_key: str
    api_secret: str


class AsterSigner:
    """
    Handles request signing for Aster API authentication.

    Uses Binance-style HMAC-SHA256 signing for authenticated requests.
    """

    def __init__(self, credentials: ApiCredentials, recv_window: int = 5000):
        """
        Initialize the signer with API credentials.

        Args:
            credentials: API credentials containing key and secret
            recv_window: Receive window in milliseconds (default: 5000)
        """
        self.credentials = credentials
        self.recv_window = recv_window

    def sign_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Add timestamp and signature to request parameters.

        Args:
            params: Original request parameters

        Returns:
            Dictionary with timestamp and signature added
        """
        if params is None:
            params = {}

        # Create a copy to avoid modifying the original
        signed_params = params.copy()

        # Add timestamp and receive window
        signed_params['timestamp'] = int(time.time() * 1000)
        signed_params['recvWindow'] = self.recv_window

        # Generate signature
        signature = self._generate_signature(signed_params)
        signed_params['signature'] = signature

        return signed_params

    def _generate_signature(self, params: Dict[str, Any]) -> str:
        """
        Generate HMAC-SHA256 signature for the given parameters.

        Args:
            params: Parameters to sign (including timestamp and recvWindow)

        Returns:
            Hex-encoded HMAC-SHA256 signature
        """
        # Sort parameters and create query string
        query_string = urlencode(sorted(params.items()))

        # Generate HMAC-SHA256 signature
        signature = hmac.new(
            self.credentials.api_secret.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

        return signature

    def get_auth_headers(self) -> Dict[str, str]:
        """
        Get authentication headers for API requests.

        Returns:
            Dictionary containing required authentication headers
        """
        return {
            'X-MBX-APIKEY': self.credentials.api_key
        }

    def validate_credentials(self) -> bool:
        """
        Validate that both API key and secret are present.

        Returns:
            True if credentials are valid, False otherwise
        """
        return bool(self.credentials.api_key and self.credentials.api_secret)