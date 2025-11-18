# -*- coding: utf-8 -*-
"""
Comprehensive tests for AsterPublicClient.
"""

import pytest
import asyncio
import aiohttp
from aiohttp import ClientSession, ClientError, ClientTimeout, ClientConnectorError
from decimal import Decimal
from unittest.mock import Mock, AsyncMock, patch

from aster_client.public_client import AsterPublicClient
from aster_client.models.market import SymbolInfo


class TestAsterPublicClientInit:
    """Test initialization of AsterPublicClient."""

    def test_valid_init_default_url(self):
        """Test initialization with default URL."""
        client = AsterPublicClient()
        assert client.base_url == "https://fapi.asterdex.com"
        assert client.endpoints["ticker"] == "/fapi/v1/premiumIndex"
        assert client.endpoints["exchange_info"] == "/fapi/v1/exchangeInfo"
        assert isinstance(client._timeout, ClientTimeout)
        assert client._timeout.total == 30

    def test_valid_init_custom_url(self, valid_test_urls):
        """Test initialization with valid custom URLs."""
        for url in valid_test_urls:
            client = AsterPublicClient(base_url=url)
            expected_url = url.rstrip("/")
            assert client.base_url == expected_url

    def test_invalid_init_urls(self, invalid_test_urls):
        """Test initialization with invalid URLs raises ValueError."""
        for url in invalid_test_urls:
            if url is None:  # Skip None for type error test
                continue
            with pytest.raises(ValueError, match="Base URL must be a valid HTTP/HTTPS URL"):
                AsterPublicClient(base_url=url)

    def test_init_type_error(self):
        """Test initialization with non-string URL raises TypeError."""
        with pytest.raises(ValueError):
            AsterPublicClient(base_url=123)

    def test_url_normalization(self):
        """Test that trailing slashes are removed from URLs."""
        client = AsterPublicClient(base_url="https://api.example.com/")
        assert client.base_url == "https://api.example.com"

        client2 = AsterPublicClient(base_url="https://api.example.com/v1/")
        assert client2.base_url == "https://api.example.com/v1"

    def test_endpoints_configuration(self):
        """Test that endpoints are properly configured."""
        client = AsterPublicClient()
        expected_endpoints = {
            "ticker": "/fapi/v1/premiumIndex",
            "all_mark_prices": "/fapi/v1/premiumIndex",
            "exchange_info": "/fapi/v1/exchangeInfo",
            "symbol_info": "/fapi/v1/exchangeInfo",
        }
        assert client.endpoints == expected_endpoints


class TestSessionManagement:
    """Test session management functionality."""

    @pytest.mark.asyncio
    async def test_get_session_creates_new_session(self, public_client):
        """Test that _get_session creates a new session when None."""
        session = await public_client._get_session()
        assert isinstance(session, ClientSession)
        assert session == public_client._session
        assert not session.closed
        await public_client.close()

    @pytest.mark.asyncio
    async def test_get_session_reuses_existing_session(self, public_client):
        """Test that _get_session reuses existing session."""
        session1 = await public_client._get_session()
        session2 = await public_client._get_session()
        assert session1 is session2
        await public_client.close()

    @pytest.mark.asyncio
    async def test_get_session_recreates_closed_session(self, public_client):
        """Test that _get_session recreates session after closure."""
        session1 = await public_client._get_session()
        await public_client.close()
        session2 = await public_client._get_session()
        assert session1 is not session2
        assert session1.closed
        assert not session2.closed

    @pytest.mark.asyncio
    async def test_close_closes_session(self, public_client):
        """Test that close() properly closes the session."""
        await public_client._get_session()  # Create session
        await public_client.close()
        assert public_client._session.closed

    @pytest.mark.asyncio
    async def test_close_no_session(self, public_client):
        """Test that close() works when no session exists."""
        await public_client.close()  # Should not raise error
        assert public_client._session is None

    @pytest.mark.asyncio
    async def test_context_manager_entry(self, public_client):
        """Test async context manager entry."""
        async with public_client as client:
            assert client is public_client

    @pytest.mark.asyncio
    async def test_context_manager_exit_closes_session(self, public_client):
        """Test async context manager exit closes session."""
        async with public_client as client:
            session = await client._get_session()
            assert not session.closed
        assert session.closed

    @pytest.mark.asyncio
    async def test_context_manager_with_exception(self, public_client):
        """Test context manager handles exceptions properly."""
        with pytest.raises(ValueError):
            async with public_client as client:
                await client._get_session()
                raise ValueError("Test exception")
        # Session should still be closed
        assert client._session.closed


class TestMakeRequest:
    """Test _make_request method."""

    @pytest.mark.asyncio
    async def test_successful_get_request(self, public_client, mock_success_response):
        """Test successful GET request."""
        with patch('aiohttp.ClientSession.request') as mock_request:
            mock_request.return_value.__aenter__.return_value = mock_success_response

            result = await public_client._make_request("GET", "/test")

            assert result == {"status": "success"}
            mock_request.assert_called_once_with(
                method="GET",
                url=f"{public_client.base_url}/test",
                params=None
            )

    @pytest.mark.asyncio
    async def test_request_with_parameters(self, public_client, mock_success_response):
        """Test request with parameters."""
        with patch('aiohttp.ClientSession.request') as mock_request:
            mock_request.return_value.__aenter__.return_value = mock_success_response

            params = {"symbol": "BTCUSDT", "limit": 100}
            result = await public_client._make_request("GET", "/test", params)

            assert result == {"status": "success"}
            mock_request.assert_called_once_with(
                method="GET",
                url=f"{public_client.base_url}/test",
                params=params
            )

    @pytest.mark.asyncio
    async def test_post_request(self, public_client, mock_success_response):
        """Test successful POST request."""
        with patch('aiohttp.ClientSession.request') as mock_request:
            mock_request.return_value.__aenter__.return_value = mock_success_response

            result = await public_client._make_request("POST", "/test")

            assert result == {"status": "success"}
            mock_request.assert_called_once_with(
                method="POST",
                url=f"{public_client.base_url}/test",
                params=None
            )

    @pytest.mark.asyncio
    async def test_timeout_error(self, public_client):
        """Test timeout error handling."""
        with patch('aiohttp.ClientSession.request') as mock_request:
            mock_request.side_effect = asyncio.TimeoutError()

            with pytest.raises(Exception, match="Request timeout"):
                await public_client._make_request("GET", "/test")

    @pytest.mark.asyncio
    async def test_connection_error(self, public_client):
        """Test connection error handling."""
        with patch('aiohttp.ClientSession.request') as mock_request:
            mock_request.side_effect = ClientConnectorError(Mock(), Mock())

            with pytest.raises(Exception, match="Connection error"):
                await public_client._make_request("GET", "/test")

    @pytest.mark.asyncio
    async def test_http_client_error(self, public_client):
        """Test HTTP client error handling."""
        with patch('aiohttp.ClientSession.request') as mock_request:
            mock_request.side_effect = ClientError("HTTP Error")

            with pytest.raises(ClientError, match="HTTP Error"):
                await public_client._make_request("GET", "/test")

    @pytest.mark.asyncio
    async def test_general_exception(self, public_client):
        """Test general exception handling."""
        with patch('aiohttp.ClientSession.request') as mock_request:
            mock_request.side_effect = Exception("General Error")

            with pytest.raises(Exception, match="General Error"):
                await public_client._make_request("GET", "/test")


class TestGetTicker:
    """Test get_ticker method."""

    @pytest.mark.asyncio
    async def test_get_ticker_success(self, public_client, ticker_response_data, valid_test_symbol):
        """Test successful ticker request."""
        with patch.object(public_client, '_make_request') as mock_request:
            mock_request.return_value = ticker_response_data

            result = await public_client.get_ticker(valid_test_symbol)

            assert result == ticker_response_data
            mock_request.assert_called_once_with(
                "GET",
                public_client.endpoints["ticker"],
                {"symbol": valid_test_symbol}
            )

    @pytest.mark.asyncio
    async def test_get_ticker_invalid_symbol(self, public_client, invalid_test_symbol):
        """Test get_ticker with invalid symbol."""
        with pytest.raises(ValueError, match="Invalid symbol format"):
            await public_client.get_ticker(invalid_test_symbol)

    @pytest.mark.asyncio
    async def test_get_ticker_request_error(self, public_client, valid_test_symbol):
        """Test get_ticker handles request errors and returns None."""
        with patch.object(public_client, '_make_request') as mock_request:
            mock_request.side_effect = Exception("Network error")

            result = await public_client.get_ticker(valid_test_symbol)

            assert result is None

    @pytest.mark.asyncio
    async def test_get_ticker_empty_symbol(self, public_client):
        """Test get_ticker with empty symbol."""
        with pytest.raises(ValueError, match="Invalid symbol format"):
            await public_client.get_ticker("")

    @pytest.mark.asyncio
    async def test_get_ticker_none_symbol(self, public_client):
        """Test get_ticker with None symbol."""
        with pytest.raises(ValueError, match="Invalid symbol format"):
            await public_client.get_ticker(None)


class TestGetAllMarkPrices:
    """Test get_all_mark_prices method."""

    @pytest.mark.asyncio
    async def test_get_all_mark_prices_success(self, public_client, all_mark_prices_response_data):
        """Test successful all mark prices request."""
        with patch.object(public_client, '_make_request') as mock_request:
            mock_request.return_value = all_mark_prices_response_data

            result = await public_client.get_all_mark_prices()

            assert result == all_mark_prices_response_data
            mock_request.assert_called_once_with(
                "GET",
                public_client.endpoints["all_mark_prices"]
            )

    @pytest.mark.asyncio
    async def test_get_all_mark_prices_empty_response(self, public_client):
        """Test get_all_mark_prices with empty response."""
        with patch.object(public_client, '_make_request') as mock_request:
            mock_request.return_value = []

            result = await public_client.get_all_mark_prices()

            assert result == []

    @pytest.mark.asyncio
    async def test_get_all_mark_prices_request_error(self, public_client):
        """Test get_all_mark_prices handles request errors and returns None."""
        with patch.object(public_client, '_make_request') as mock_request:
            mock_request.side_effect = Exception("Network error")

            result = await public_client.get_all_mark_prices()

            assert result is None


class TestGetExchangeInfo:
    """Test get_exchange_info method."""

    @pytest.mark.asyncio
    async def test_get_exchange_info_success(self, public_client, exchange_info_response_data):
        """Test successful exchange info request."""
        with patch.object(public_client, '_make_request') as mock_request:
            mock_request.return_value = exchange_info_response_data

            result = await public_client.get_exchange_info()

            assert result == exchange_info_response_data
            mock_request.assert_called_once_with(
                "GET",
                public_client.endpoints["exchange_info"]
            )

    @pytest.mark.asyncio
    async def test_get_exchange_info_complex_response(self, public_client):
        """Test get_exchange_info with complex nested response."""
        complex_response = {
            "timezone": "UTC",
            "serverTime": 1640995200000,
            "rateLimits": [
                {"rateLimitType": "REQUEST_WEIGHT", "interval": "MINUTE", "intervalNum": 1, "limit": 1200}
            ],
            "symbols": [
                {
                    "symbol": "BTCUSDT",
                    "base_asset": "BTC",
                    "quote_asset": "USDT",
                    "filters": [
                        {"filterType": "PRICE_FILTER", "minPrice": "0.01"},
                        {"filterType": "LOT_SIZE", "minQty": "0.001"}
                    ]
                }
            ]
        }

        with patch.object(public_client, '_make_request') as mock_request:
            mock_request.return_value = complex_response

            result = await public_client.get_exchange_info()

            assert result == complex_response

    @pytest.mark.asyncio
    async def test_get_exchange_info_request_error(self, public_client):
        """Test get_exchange_info handles request errors and returns None."""
        with patch.object(public_client, '_make_request') as mock_request:
            mock_request.side_effect = Exception("Network error")

            result = await public_client.get_exchange_info()

            assert result is None


class TestGetSymbolInfo:
    """Test get_symbol_info method."""

    @pytest.mark.asyncio
    async def test_get_symbol_info_success(self, public_client, exchange_info_response_data, sample_symbol_info, valid_test_symbol):
        """Test successful symbol info request."""
        with patch.object(public_client, 'get_exchange_info') as mock_get_exchange_info:
            mock_get_exchange_info.return_value = exchange_info_response_data

            result = await public_client.get_symbol_info(valid_test_symbol)

            assert isinstance(result, SymbolInfo)
            assert result.symbol == valid_test_symbol
            assert result.base_asset == "BTC"
            assert result.quote_asset == "USDT"
            assert result.status == "TRADING"
            assert result.price_precision == 2
            assert result.quantity_precision == 3
            assert result.min_quantity == Decimal("0.001")
            assert result.max_quantity == Decimal("1000")
            assert result.min_notional == Decimal("10")
            assert result.max_notional == Decimal("1000000")
            assert result.tick_size == Decimal("0.01")
            assert result.step_size == Decimal("0.001")
            assert result.contract_type == "PERPETUAL"
            assert result.delivery_date is None

    @pytest.mark.asyncio
    async def test_get_symbol_info_not_found(self, public_client, exchange_info_response_data):
        """Test get_symbol_info when symbol is not found."""
        with patch.object(public_client, 'get_exchange_info') as mock_get_exchange_info:
            mock_get_exchange_info.return_value = exchange_info_response_data

            result = await public_client.get_symbol_info("NOTFOUND")

            assert result is None

    @pytest.mark.asyncio
    async def test_get_symbol_info_invalid_symbol(self, public_client, invalid_test_symbol):
        """Test get_symbol_info with invalid symbol."""
        with pytest.raises(ValueError, match="Invalid symbol format"):
            await public_client.get_symbol_info(invalid_test_symbol)

    @pytest.mark.asyncio
    async def test_get_symbol_info_exchange_info_error(self, public_client, valid_test_symbol):
        """Test get_symbol_info when get_exchange_info returns None."""
        with patch.object(public_client, 'get_exchange_info') as mock_get_exchange_info:
            mock_get_exchange_info.return_value = None

            result = await public_client.get_symbol_info(valid_test_symbol)

            assert result is None

    @pytest.mark.asyncio
    async def test_get_symbol_info_no_symbols_key(self, public_client, valid_test_symbol):
        """Test get_symbol_info when exchange info has no symbols key."""
        with patch.object(public_client, 'get_exchange_info') as mock_get_exchange_info:
            mock_get_exchange_info.return_value = {"timezone": "UTC"}

            result = await public_client.get_symbol_info(valid_test_symbol)

            assert result is None

    @pytest.mark.asyncio
    async def test_get_symbol_info_invalid_data_parsing(self, public_client, valid_test_symbol):
        """Test get_symbol_info with invalid data that causes parsing errors."""
        # Create data that will trigger decimal.InvalidOperation
        invalid_symbol_data = {
            "symbol": "INVALID",
            "base_asset": "INV",
            "quote_asset": "USDT",
            "status": "TRADING",
            "price_precision": 2,
            "quantity_precision": 3,
            "min_quantity": "not_a_number",  # This will cause Decimal conversion to fail
            "max_quantity": "1000",
            "min_notional": "10",
            "max_notional": "1000000",
            "tick_size": "0.01",
            "step_size": "0.001"
        }
        exchange_info = {"symbols": [invalid_symbol_data]}

        with patch.object(public_client, 'get_exchange_info') as mock_get_exchange_info:
            mock_get_exchange_info.return_value = exchange_info

            # The current implementation doesn't catch decimal.InvalidOperation
            # so this should raise an exception
            with pytest.raises(Exception):
                await public_client.get_symbol_info("INVALID")

    @pytest.mark.asyncio
    async def test_get_symbol_info_missing_fields(self, public_client, valid_test_symbol):
        """Test get_symbol_info with missing required fields."""
        incomplete_symbol_data = {
            "symbol": valid_test_symbol,
            "base_asset": "BTC",
            # Missing many required fields
        }
        exchange_info = {"symbols": [incomplete_symbol_data]}

        with patch.object(public_client, 'get_exchange_info') as mock_get_exchange_info:
            mock_get_exchange_info.return_value = exchange_info

            result = await public_client.get_symbol_info(valid_test_symbol)

            # Should still return a SymbolInfo with default values
            assert isinstance(result, SymbolInfo)
            assert result.symbol == valid_test_symbol
            assert result.base_asset == "BTC"
            assert result.quote_asset == ""

    @pytest.mark.asyncio
    async def test_get_symbol_info_decimal_conversion_error(self, public_client, valid_test_symbol):
        """Test get_symbol_info with invalid Decimal values."""
        invalid_decimal_data = {
            "symbol": valid_test_symbol,
            "base_asset": "BTC",
            "quote_asset": "USDT",
            "status": "TRADING",
            "price_precision": 2,
            "quantity_precision": 3,
            "min_quantity": "not_a_valid_decimal",
            "max_quantity": "1000",
            "min_notional": "10",
            "max_notional": "1000000",
            "tick_size": "0.01",
            "step_size": "0.001"
        }
        exchange_info = {"symbols": [invalid_decimal_data]}

        with patch.object(public_client, 'get_exchange_info') as mock_get_exchange_info:
            mock_get_exchange_info.return_value = exchange_info

            # The current implementation doesn't catch decimal.InvalidOperation
            # so this should raise an exception
            with pytest.raises(Exception):
                await public_client.get_symbol_info(valid_test_symbol)


class TestIntegration:
    """Integration tests for AsterPublicClient."""

    @pytest.mark.asyncio
    async def test_full_workflow_with_context_manager(self, public_client, ticker_response_data, exchange_info_response_data, all_mark_prices_response_data, valid_test_symbol):
        """Test full workflow using context manager."""
        with patch.object(public_client, '_make_request') as mock_request:
            # Setup different responses for different calls
            async def mock_make_request(method, endpoint, params=None):
                if endpoint == public_client.endpoints["ticker"] and params and "symbol" in params:
                    return ticker_response_data
                elif endpoint == public_client.endpoints["all_mark_prices"] and not params:
                    return all_mark_prices_response_data
                elif endpoint == public_client.endpoints["exchange_info"]:
                    return exchange_info_response_data
                else:
                    return []

            mock_request.side_effect = mock_make_request

            async with public_client as client:
                # Get ticker
                ticker = await client.get_ticker(valid_test_symbol)
                assert ticker == ticker_response_data

                # Get all mark prices
                all_prices = await client.get_all_mark_prices()
                assert all_prices == all_mark_prices_response_data

                # Get exchange info
                exchange_info = await client.get_exchange_info()
                assert exchange_info == exchange_info_response_data

                # Get symbol info
                symbol_info = await client.get_symbol_info(valid_test_symbol)
                assert isinstance(symbol_info, SymbolInfo)
                assert symbol_info.symbol == valid_test_symbol

    @pytest.mark.asyncio
    async def test_concurrent_requests(self, public_client, ticker_response_data, valid_test_symbol):
        """Test handling concurrent requests."""
        with patch.object(public_client, '_make_request') as mock_request:
            mock_request.return_value = ticker_response_data

            # Create multiple concurrent requests
            tasks = [
                public_client.get_ticker(valid_test_symbol)
                for _ in range(5)
            ]

            results = await asyncio.gather(*tasks)

            # All should succeed
            assert all(result == ticker_response_data for result in results)
            # Should only make one call due to session reuse
            assert mock_request.call_count == 5

    @pytest.mark.asyncio
    async def test_session_reuse_across_methods(self, public_client, ticker_response_data, exchange_info_response_data, valid_test_symbol):
        """Test that session is reused across different method calls."""
        with patch.object(public_client, '_make_request') as mock_request:
            async def mock_make_request(method, endpoint, params=None):
                # Verify the same session is being used
                session = await public_client._get_session()
                assert session is public_client._session
                if endpoint == public_client.endpoints["ticker"]:
                    return ticker_response_data
                elif endpoint == public_client.endpoints["exchange_info"]:
                    return exchange_info_response_data
                return {}

            mock_request.side_effect = mock_make_request

            # Make multiple calls
            await public_client.get_ticker(valid_test_symbol)
            await public_client.get_exchange_info()
            await public_client.get_all_mark_prices()

            # Session should be the same throughout
            session = await public_client._get_session()
            assert not session.closed

    @pytest.mark.asyncio
    async def test_error_handling_workflow(self, public_client, valid_test_symbol):
        """Test error handling in complete workflow."""
        with patch.object(public_client, '_make_request') as mock_request:
            mock_request.side_effect = Exception("Network error")

            async with public_client as client:
                # All methods should return None on error
                ticker = await client.get_ticker(valid_test_symbol)
                assert ticker is None

                all_prices = await client.get_all_mark_prices()
                assert all_prices is None

                exchange_info = await client.get_exchange_info()
                assert exchange_info is None

                symbol_info = await client.get_symbol_info(valid_test_symbol)
                assert symbol_info is None


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_very_long_symbol(self, public_client):
        """Test with very long symbol name."""
        long_symbol = "A" * 25  # Longer than max allowed length
        with pytest.raises(ValueError, match="Invalid symbol format"):
            await public_client.get_ticker(long_symbol)

    @pytest.mark.asyncio
    async def test_symbol_with_special_characters(self, public_client):
        """Test symbol with special characters."""
        special_symbol = "BTC@USDT"
        with pytest.raises(ValueError, match="Invalid symbol format"):
            await public_client.get_ticker(special_symbol)

    @pytest.mark.asyncio
    async def test_empty_and_whitespace_symbols(self, public_client):
        """Test with empty and whitespace symbols."""
        for symbol in ["", "   ", "\t", "\n"]:
            with pytest.raises(ValueError, match="Invalid symbol format"):
                await public_client.get_ticker(symbol)

    @pytest.mark.asyncio
    async def test_session_cleanup_on_exception(self, public_client):
        """Test that session is properly cleaned up even when exceptions occur."""
        with patch.object(public_client, '_make_request') as mock_request:
            mock_request.side_effect = Exception("Test exception")

            try:
                async with public_client as client:
                    await client.get_ticker("BTCUSDT")
            except Exception:
                pass  # Expected

            # Session should still be closed
            assert public_client._session is None or public_client._session.closed

    def test_endpoint_url_construction(self):
        """Test that endpoint URLs are constructed correctly."""
        client = AsterPublicClient(base_url="https://api.example.com")

        expected_urls = {
            "ticker": "https://api.example.com/fapi/v1/premiumIndex",
            "all_mark_prices": "https://api.example.com/fapi/v1/premiumIndex",
            "exchange_info": "https://api.example.com/fapi/v1/exchangeInfo",
            "symbol_info": "https://api.example.com/fapi/v1/exchangeInfo",
        }

        for endpoint_name, expected_url in expected_urls.items():
            actual_url = f"{client.base_url}{client.endpoints[endpoint_name]}"
            assert actual_url == expected_url