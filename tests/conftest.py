# -*- coding: utf-8 -*-
"""
Shared fixtures and utilities for testing Aster client.
"""

import pytest
import asyncio
from decimal import Decimal
from unittest.mock import Mock, AsyncMock
from typing import Dict, Any, List

from aster_client.public_client import AsterPublicClient
from aster_client.models.market import SymbolInfo


# Mock data fixtures
@pytest.fixture
def ticker_response_data() -> Dict[str, Any]:
    """Mock ticker response data."""
    return {
        "symbol": "BTCUSDT",
        "markPrice": "50000.00",
        "timestamp": 1640995200000,
        "fundingRate": "0.0001",
        "nextFundingTime": 1640995800000
    }


@pytest.fixture
def all_mark_prices_response_data() -> List[Dict[str, Any]]:
    """Mock all mark prices response data."""
    return [
        {
            "symbol": "BTCUSDT",
            "markPrice": "50000.00",
            "timestamp": 1640995200000,
            "fundingRate": "0.0001",
            "nextFundingTime": 1640995800000
        },
        {
            "symbol": "ETHUSDT",
            "markPrice": "4000.00",
            "timestamp": 1640995200000,
            "fundingRate": "0.0002",
            "nextFundingTime": 1640995800000
        }
    ]


@pytest.fixture
def exchange_info_response_data() -> Dict[str, Any]:
    """Mock exchange info response data."""
    return {
        "timezone": "UTC",
        "serverTime": 1640995200000,
        "symbols": [
            {
                "symbol": "BTCUSDT",
                "base_asset": "BTC",
                "quote_asset": "USDT",
                "status": "TRADING",
                "price_precision": 2,
                "quantity_precision": 3,
                "min_quantity": "0.001",
                "max_quantity": "1000",
                "min_notional": "10",
                "max_notional": "1000000",
                "tick_size": "0.01",
                "step_size": "0.001",
                "contract_type": "PERPETUAL",
                "delivery_date": None
            },
            {
                "symbol": "ETHUSDT",
                "base_asset": "ETH",
                "quote_asset": "USDT",
                "status": "TRADING",
                "price_precision": 2,
                "quantity_precision": 2,
                "min_quantity": "0.01",
                "max_quantity": "10000",
                "min_notional": "10",
                "max_notional": "500000",
                "tick_size": "0.01",
                "step_size": "0.01",
                "contract_type": "PERPETUAL",
                "delivery_date": None
            }
        ]
    }


@pytest.fixture
def symbol_info_data() -> Dict[str, Any]:
    """Mock single symbol info data."""
    return {
        "symbol": "BTCUSDT",
        "base_asset": "BTC",
        "quote_asset": "USDT",
        "status": "TRADING",
        "price_precision": 2,
        "quantity_precision": 3,
        "min_quantity": "0.001",
        "max_quantity": "1000",
        "min_notional": "10",
        "max_notional": "1000000",
        "tick_size": "0.01",
        "step_size": "0.001",
        "contract_type": "PERPETUAL",
        "delivery_date": None
    }


@pytest.fixture
def invalid_symbol_info_data() -> Dict[str, Any]:
    """Mock invalid symbol info data with missing fields."""
    return {
        "symbol": "INVALID",
        "base_asset": "INV",
        # Missing quote_asset, status, and other required fields
        "price_precision": "invalid",  # Invalid type
        "quantity_precision": 2,
        "min_quantity": "not_a_number",  # Invalid number
        "max_quantity": "1000",
        "min_notional": "10",
        "max_notional": "1000000",
        "tick_size": "0.01",
        "step_size": "0.001"
    }


@pytest.fixture
def sample_symbol_info() -> SymbolInfo:
    """Sample SymbolInfo object for testing."""
    return SymbolInfo(
        symbol="BTCUSDT",
        base_asset="BTC",
        quote_asset="USDT",
        status="TRADING",
        price_precision=2,
        quantity_precision=3,
        min_quantity=Decimal("0.001"),
        max_quantity=Decimal("1000"),
        min_notional=Decimal("10"),
        max_notional=Decimal("1000000"),
        tick_size=Decimal("0.01"),
        step_size=Decimal("0.001"),
        contract_type="PERPETUAL",
        delivery_date=None
    )


@pytest.fixture
def public_client():
    """Create a fresh AsterPublicClient instance for testing."""
    return AsterPublicClient(base_url="https://test-api.example.com")


@pytest.fixture
def public_client_custom_base_url():
    """Create AsterPublicClient with custom base URL."""
    return AsterPublicClient(base_url="https://custom-api.example.com/v1")


@pytest.fixture
async def closed_public_client():
    """Create a client with closed session for testing error scenarios."""
    client = AsterPublicClient()
    await client.close()
    return client


# Test URLs and symbols
@pytest.fixture
def valid_test_symbol():
    """Valid symbol for testing."""
    return "BTCUSDT"


@pytest.fixture
def invalid_test_symbol():
    """Invalid symbol for testing."""
    return "INVALID_SYMBOL_WITH_TOO_MANY_CHARS_1234567890"


@pytest.fixture
def valid_test_urls():
    """List of valid URLs for testing."""
    return [
        "https://api.example.com",
        "http://localhost.test",
        "https://fapi.asterdex.com",
        "https://test-api.example.com/v1",
        "https://api.example.com/"
    ]


@pytest.fixture
def invalid_test_urls():
    """List of invalid URLs for testing."""
    return [
        "ftp://invalid-protocol.com",
        "not-a-url",
        "://missing-protocol.com",
        "https://",
        "http://",
        "",
        None,
        123,
        "https://invalid-domain-without-tld"
    ]


# Mock response fixtures
@pytest.fixture
def mock_success_response():
    """Mock successful HTTP response."""
    response = Mock()
    response.status = 200
    response.json = AsyncMock(return_value={"status": "success"})
    response.raise_for_status = Mock()
    return response


@pytest.fixture
def mock_error_response():
    """Mock error HTTP response."""
    response = Mock()
    response.status = 400
    response.raise_for_status = Mock(side_effect=Exception("HTTP Error"))
    return response


@pytest.fixture
def mock_timeout_response():
    """Mock timeout error response."""
    import asyncio
    response = Mock()
    response.status = 200
    response.json = AsyncMock(side_effect=asyncio.TimeoutError())
    return response


@pytest.fixture
def mock_connection_error_response():
    """Mock connection error response."""
    import aiohttp
    response = Mock()
    response.status = 200
    response.json = AsyncMock(side_effect=aiohttp.ClientConnectorError(Mock(), Mock()))
    return response


# Async event loop fixture
@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# Utility fixtures
@pytest.fixture
def mock_logger():
    """Mock logger for testing."""
    import logging
    return Mock(spec=logging.Logger)


@pytest.fixture
def mock_client_session():
    """Mock aiohttp ClientSession."""
    import aiohttp
    from unittest.mock import AsyncMock

    session = Mock(spec=aiohttp.ClientSession)
    session.request = AsyncMock()
    session.close = AsyncMock()
    session.closed = False
    return session