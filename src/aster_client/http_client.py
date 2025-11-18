"""
HTTP client for Aster API.

Handles request execution, retry logic, authentication, and response processing.
Follows pure core/impure edges principle with clean separation of concerns.
"""

import asyncio
import hashlib
import hmac
import json
import time
from typing import Any, Dict, Optional, Union
from urllib.parse import urlencode

import aiohttp
from aiohttp import ClientResponse, ClientSession

from .models.config import ConnectionConfig, RetryConfig


class HttpClient:
    """HTTP client specialized for Aster API interactions."""

    def __init__(
        self,
        config: ConnectionConfig,
        retry_config: Optional[RetryConfig] = None,
    ):
        """Initialize HTTP client with configuration."""
        self._config = config
        self._retry_config = retry_config or RetryConfig()

    async def request(
        self,
        session: ClientSession,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Execute HTTP request with retry logic and authentication."""
        url = f"{self._config.base_url}{endpoint}"

        # Prepare request data
        request_headers = self._prepare_headers(headers)
        request_params = params or {}
        request_data = data or {}

        # Add authentication if not simulation mode
        if not self._config.simulation:
            self._add_authentication(
                method, endpoint, request_params, request_data, request_headers
            )

        # Execute with retry logic
        return await self._execute_with_retry(
            session, method, url, request_params, request_data, request_headers
        )

    def _prepare_headers(self, custom_headers: Optional[Dict[str, str]]) -> Dict[str, str]:
        """Prepare request headers."""
        headers = {}
        if custom_headers:
            headers.update(custom_headers)
        return headers

    def _add_authentication(
        self,
        method: str,
        endpoint: str,
        params: Dict[str, Any],
        data: Dict[str, Any],
        headers: Dict[str, str],
    ) -> None:
        """Add authentication headers to request."""
        timestamp = str(int(time.time() * 1000))

        # Prepare signature payload
        payload: Dict[str, Any] = {
            "timestamp": timestamp,
            "method": method.upper(),
            "endpoint": endpoint,
        }

        if params:
            payload["params"] = dict(sorted(params.items()))
        if data:
            payload["data"] = dict(sorted(data.items()))

        # Generate signature
        message = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        signature = hmac.new(
            self._config.api_secret.encode(),
            message.encode(),
            hashlib.sha256,
        ).hexdigest()

        # Add auth headers
        headers["X-Api-Key"] = self._config.api_key
        headers["X-Timestamp"] = timestamp
        headers["X-Signature"] = signature

    async def _execute_with_retry(
        self,
        session: ClientSession,
        method: str,
        url: str,
        params: Dict[str, Any],
        data: Dict[str, Any],
        headers: Dict[str, str],
    ) -> Dict[str, Any]:
        """Execute request with retry logic."""
        last_exception = None

        for attempt in range(self._retry_config.max_retries + 1):
            try:
                async with session.request(
                    method=method,
                    url=url,
                    params=params if params else None,
                    json=data if data else None,
                    headers=headers,
                ) as response:
                    response_data = await self._process_response(response)

                    # Check if response indicates success
                    if response.status < 400:
                        return response_data

                    # Don't retry on client errors (4xx)
                    if 400 <= response.status < 500:
                        raise HttpClientClientError(
                            f"Client error {response.status}: {response_data}",
                            status_code=response.status,
                            response_data=response_data,
                        )

                    # Retry on server errors
                    if response.status in self._retry_config.retry_on_status:
                        raise HttpServerError(
                            f"Server error {response.status}: {response_data}",
                            status_code=response.status,
                            response_data=response_data,
                        )

                    # Other status codes - treat as client error
                    raise HttpClientClientError(
                        f"HTTP {response.status}: {response_data}",
                        status_code=response.status,
                        response_data=response_data,
                    )

            except (HttpServerError, HttpClientClientError, aiohttp.ClientError) as e:
                last_exception = e

                # Don't retry on the last attempt
                if attempt == self._retry_config.max_retries:
                    break

                # Calculate delay with exponential backoff
                delay = self._retry_config.retry_delay * (
                    self._retry_config.backoff_factor ** attempt
                )
                await asyncio.sleep(delay)

        # All retries exhausted
        raise last_exception or HttpClientError("Request failed after all retries")

    async def _process_response(self, response: ClientResponse) -> Dict[str, Any]:
        """Process HTTP response and return data."""
        response_text = await response.text()

        if not response_text:
            return {"status": response.status, "data": None}

        try:
            return json.loads(response_text)
        except json.JSONDecodeError as e:
            raise HttpClientError(
                f"Invalid JSON response: {response_text[:200]}",
                status_code=response.status,
            ) from e


class HttpClientError(Exception):
    """Base exception for HTTP client errors."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        response_data: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.response_data = response_data


class HttpServerError(HttpClientError):
    """Exception for server errors (5xx)."""
    pass


class HttpClientClientError(HttpClientError):
    """Exception for client errors (4xx)."""
    pass