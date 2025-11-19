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

from .constants import DEFAULT_RECV_WINDOW
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

        # Set content type for POST/PUT requests (form-urlencoded)
        if method.upper() in ["POST", "PUT"] and request_data:
            request_headers["Content-Type"] = "application/x-www-form-urlencoded"

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
        """Add Binance-style authentication to request."""
        timestamp = str(int(time.time() * 1000))

        # Prepare parameters for signature
        if method.upper() == "GET":
            # For GET requests, signature goes in query params
            auth_params = params.copy()
            auth_params["timestamp"] = timestamp
            auth_params["recvWindow"] = self._config.recv_window

            # Create signature from query string
            query_string = urlencode(sorted(auth_params.items()))
            signature = hmac.new(
                self._config.api_secret.encode(),
                query_string.encode(),
                hashlib.sha256,
            ).hexdigest()

            # Add signature to params
            params["timestamp"] = timestamp
            params["recvWindow"] = self._config.recv_window
            params["signature"] = signature
        else:
            # For POST/PUT requests, signature goes in request body
            auth_data = data.copy()
            auth_data["timestamp"] = timestamp
            auth_data["recvWindow"] = self._config.recv_window

            # Create signature from request body
            query_string = urlencode(sorted(auth_data.items()))
            signature = hmac.new(
                self._config.api_secret.encode(),
                query_string.encode(),
                hashlib.sha256,
            ).hexdigest()

            # Add signature to data
            data["timestamp"] = timestamp
            data["recvWindow"] = self._config.recv_window
            data["signature"] = signature

        # Add API key header (Binance-style)
        headers["X-MBX-APIKEY"] = self._config.api_key

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
                # Prepare request kwargs
                request_kwargs = {
                    "method": method,
                    "url": url,
                    "headers": headers,
                }

                # Add parameters and data appropriately
                if params:
                    # Ensure signature is last if present
                    params_list = list(params.items())
                    if "signature" in params:
                        sig = params["signature"]
                        # Sort everything except signature
                        params_list = sorted([(k, v) for k, v in params.items() if k != "signature"])
                        params_list.append(("signature", sig))
                    else:
                        params_list = sorted(params_list)
                    request_kwargs["params"] = params_list

                if data:
                    if method.upper() in ["POST", "PUT"]:
                        # Use form-encoded data for POST/PUT
                        # Ensure signature is last if present
                        data_list = list(data.items())
                        if "signature" in data:
                            sig = data["signature"]
                            # Sort everything except signature
                            data_list = sorted([(k, v) for k, v in data.items() if k != "signature"])
                            data_list.append(("signature", sig))
                        else:
                            data_list = sorted(data_list)
                        
                        request_kwargs["data"] = urlencode(data_list)
                    else:
                        # Use JSON for other methods if needed
                        request_kwargs["json"] = data

                async with session.request(**request_kwargs) as response:
                    response_data = await self._process_response(response)

                    # Check if response indicates success
                    if response.status < 400:
                        return response_data

                    # Don't retry on client errors (4xx)
                    if 400 <= response.status < 500:
                        # Provide better error messages for common authentication issues
                        if response.status == 401:
                            if isinstance(response_data, dict):
                                code = response_data.get("code", 0)
                                msg = response_data.get("msg", "Unknown authentication error")

                                if code == -2014 and "API-key format invalid" in msg:
                                    raise HttpClientClientError(
                                        f"Authentication failed: API key format is invalid. "
                                        f"Please check your ASTER_API_KEY environment variable. "
                                        f"Server error: {msg}",
                                        status_code=response.status,
                                        response_data=response_data,
                                    )
                                elif code == -2015 and "Invalid API-key" in msg:
                                    raise HttpClientClientError(
                                        f"Authentication failed: Invalid API key or IP restrictions. "
                                        f"Please check your ASTER_API_KEY and any IP whitelist settings. "
                                        f"Server error: {msg}",
                                        status_code=response.status,
                                        response_data=response_data,
                                    )
                                elif code == -1022 and "Signature for this request is not valid" in msg:
                                    raise HttpClientClientError(
                                        f"Authentication failed: Invalid signature. "
                                        f"Please check your ASTER_API_SECRET environment variable. "
                                        f"Server error: {msg}",
                                        status_code=response.status,
                                        response_data=response_data,
                                    )

                            raise HttpClientClientError(
                                f"Authentication failed: Please check your API credentials. "
                                f"Server response: {response_data}",
                                status_code=response.status,
                                response_data=response_data,
                            )

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

            except (HttpServerError, aiohttp.ClientError) as e:
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
                f"Invalid JSON response (Status {response.status}): {response_text[:200]}",
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