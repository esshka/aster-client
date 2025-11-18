# -*- coding: utf-8 -*-
"""
Comprehensive tests for AsterClient (account client).
"""

import pytest
import asyncio
import aiohttp
import unittest
from aiohttp import ClientSession, ClientError, ClientTimeout, ClientConnectorError
from decimal import Decimal
from unittest.mock import Mock, AsyncMock, patch, MagicMock

from aster_client.account_client import AsterClient, create_aster_client
from aster_client.models import (
    AccountInfo, Balance, Position, OrderRequest, OrderResponse,
    ConnectionConfig, RetryConfig, MarkPrice
)


class TestAsterClientInit:
    """Test initialization of AsterClient."""

    def test_valid_init_with_config(self, connection_config, retry_config):
        """Test initialization with valid config."""
        client = AsterClient(connection_config, retry_config)
        assert client._config == connection_config
        assert not client._closed
        assert client._session_manager is not None
        assert client._http_client is not None
        assert client._api_methods is not None
        assert client._monitor is not None

    def test_valid_init_without_retry_config(self, connection_config):
        """Test initialization without retry config."""
        client = AsterClient(connection_config)
        assert client._config == connection_config
        assert not client._closed

    def test_from_env_success(self):
        """Test successful client creation from environment variables."""
        with patch.dict('os.environ', {
            'ASTER_API_KEY': 'test_key',
            'ASTER_API_SECRET': 'test_secret'
        }):
            client = AsterClient.from_env(simulation=True)
            assert client._config.api_key == 'test_key'
            assert client._config.api_secret == 'test_secret'
            assert client._config.simulation is True

    def test_from_env_missing_variables(self):
        """Test from_env with missing environment variables."""
        with patch.dict('os.environ', {}, clear=True):
            client = AsterClient.from_env()
            assert client._config.api_key == ""
            assert client._config.api_secret == ""

    def test_create_aster_client_function(self):
        """Test the factory function create_aster_client."""
        client = create_aster_client(
            api_key="test_key",
            api_secret="test_secret",
            base_url="https://test.api.com",
            timeout=15.0,
            simulation=True,
            max_retries=5,
            retry_delay=2.0
        )

        assert client._config.api_key == "test_key"
        assert client._config.api_secret == "test_secret"
        assert client._config.base_url == "https://test.api.com"
        assert client._config.timeout == 15.0
        assert client._config.simulation is True
        assert client._http_client._retry_config.max_retries == 5
        assert client._http_client._retry_config.retry_delay == 2.0


class TestAccountOperations:
    """Test account-related operations."""

    @pytest.mark.asyncio
    async def test_get_account_info_success(self, account_client, account_info_response_data):
        """Test successful get_account_info call."""
        with patch.object(account_client._session_manager, 'create_session') as mock_session:
            mock_session.return_value = AsyncMock()

            with patch.object(account_client._api_methods, 'get_account_info') as mock_api:
                mock_api.return_value = account_info_response_data

                result = await account_client.get_account_info()

                assert result == account_info_response_data
                mock_session.assert_called_once()
                mock_api.assert_called_once_with(mock_session.return_value)

    @pytest.mark.asyncio
    async def test_get_positions_success(self, account_client, positions_response_data):
        """Test successful get_positions call."""
        with patch.object(account_client._session_manager, 'create_session') as mock_session:
            mock_session.return_value = AsyncMock()

            with patch.object(account_client._api_methods, 'get_positions') as mock_api:
                mock_api.return_value = positions_response_data

                result = await account_client.get_positions()

                assert result == positions_response_data
                mock_session.assert_called_once()
                mock_api.assert_called_once_with(mock_session.return_value)

    @pytest.mark.asyncio
    async def test_get_positions_empty(self, account_client):
        """Test get_positions with no positions."""
        with patch.object(account_client._session_manager, 'create_session') as mock_session:
            mock_session.return_value = AsyncMock()

            with patch.object(account_client._api_methods, 'get_positions') as mock_api:
                mock_api.return_value = []

                result = await account_client.get_positions()

                assert result == []

    @pytest.mark.asyncio
    async def test_get_balances_success(self, account_client, balances_response_data):
        """Test successful get_balances call."""
        with patch.object(account_client._session_manager, 'create_session') as mock_session:
            mock_session.return_value = AsyncMock()

            with patch.object(account_client._api_methods, 'get_balances') as mock_api:
                mock_api.return_value = balances_response_data

                result = await account_client.get_balances()

                assert result == balances_response_data
                mock_session.assert_called_once()
                mock_api.assert_called_once_with(mock_session.return_value)

    @pytest.mark.asyncio
    async def test_get_balances_empty(self, account_client):
        """Test get_balances with no balances."""
        with patch.object(account_client._session_manager, 'create_session') as mock_session:
            mock_session.return_value = AsyncMock()

            with patch.object(account_client._api_methods, 'get_balances') as mock_api:
                mock_api.return_value = []

                result = await account_client.get_balances()

                assert result == []


class TestOrderOperations:
    """Test order-related operations."""

    @pytest.mark.asyncio
    async def test_place_order_success(self, account_client, sample_order_request, order_response_data):
        """Test successful place_order call."""
        with patch.object(account_client._session_manager, 'create_session') as mock_session:
            mock_session.return_value = AsyncMock()

            with patch.object(account_client._api_methods, 'place_order') as mock_api:
                mock_api.return_value = order_response_data

                result = await account_client.place_order(sample_order_request)

                assert result == order_response_data
                mock_session.assert_called_once()
                mock_api.assert_called_once_with(mock_session.return_value, sample_order_request)

    @pytest.mark.asyncio
    async def test_cancel_order_success(self, account_client):
        """Test successful cancel_order call."""
        order_id = "order_123456"
        cancel_response = {"status": "cancelled", "order_id": order_id}

        with patch.object(account_client._session_manager, 'create_session') as mock_session:
            mock_session.return_value = AsyncMock()

            with patch.object(account_client._api_methods, 'cancel_order') as mock_api:
                mock_api.return_value = cancel_response

                result = await account_client.cancel_order(order_id)

                assert result == cancel_response
                mock_session.assert_called_once()
                mock_api.assert_called_once_with(mock_session.return_value, order_id)

    @pytest.mark.asyncio
    async def test_get_order_success(self, account_client, order_response_data):
        """Test successful get_order call."""
        order_id = "order_123456"

        with patch.object(account_client._session_manager, 'create_session') as mock_session:
            mock_session.return_value = AsyncMock()

            with patch.object(account_client._api_methods, 'get_order') as mock_api:
                mock_api.return_value = order_response_data

                result = await account_client.get_order(order_id)

                assert result == order_response_data
                mock_session.assert_called_once()
                mock_api.assert_called_once_with(mock_session.return_value, order_id)

    @pytest.mark.asyncio
    async def test_get_order_not_found(self, account_client):
        """Test get_order when order is not found."""
        order_id = "nonexistent_order"

        with patch.object(account_client._session_manager, 'create_session') as mock_session:
            mock_session.return_value = AsyncMock()

            with patch.object(account_client._api_methods, 'get_order') as mock_api:
                mock_api.return_value = None

                result = await account_client.get_order(order_id)

                assert result is None

    @pytest.mark.asyncio
    async def test_get_orders_success(self, account_client, order_response_data):
        """Test successful get_orders call."""
        orders_data = [order_response_data]

        with patch.object(account_client._session_manager, 'create_session') as mock_session:
            mock_session.return_value = AsyncMock()

            with patch.object(account_client._api_methods, 'get_orders') as mock_api:
                mock_api.return_value = orders_data

                result = await account_client.get_orders()

                assert result == orders_data
                mock_session.assert_called_once()
                mock_api.assert_called_once_with(mock_session.return_value, None)

    @pytest.mark.asyncio
    async def test_get_orders_with_symbol_filter(self, account_client, order_response_data):
        """Test get_orders with symbol filter."""
        symbol = "BTCUSDT"
        orders_data = [order_response_data]

        with patch.object(account_client._session_manager, 'create_session') as mock_session:
            mock_session.return_value = AsyncMock()

            with patch.object(account_client._api_methods, 'get_orders') as mock_api:
                mock_api.return_value = orders_data

                result = await account_client.get_orders(symbol)

                assert result == orders_data
                mock_session.assert_called_once()
                mock_api.assert_called_once_with(mock_session.return_value, symbol)

    @pytest.mark.asyncio
    async def test_get_orders_empty(self, account_client):
        """Test get_orders with no orders."""
        with patch.object(account_client._session_manager, 'create_session') as mock_session:
            mock_session.return_value = AsyncMock()

            with patch.object(account_client._api_methods, 'get_orders') as mock_api:
                mock_api.return_value = []

                result = await account_client.get_orders()

                assert result == []


class TestMarketDataOperations:
    """Test market data operations."""

    @pytest.mark.asyncio
    async def test_get_mark_price_success(self, account_client, mark_price_response_data):
        """Test successful get_mark_price call."""
        symbol = "BTCUSDT"

        with patch.object(account_client._session_manager, 'create_session') as mock_session:
            mock_session.return_value = AsyncMock()

            with patch.object(account_client._api_methods, 'get_mark_price') as mock_api:
                mock_api.return_value = mark_price_response_data

                result = await account_client.get_mark_price(symbol)

                assert result == mark_price_response_data
                mock_session.assert_called_once()
                mock_api.assert_called_once_with(mock_session.return_value, symbol)

    @pytest.mark.asyncio
    async def test_get_mark_price_not_found(self, account_client):
        """Test get_mark_price when symbol is not found."""
        symbol = "INVALID"

        with patch.object(account_client._session_manager, 'create_session') as mock_session:
            mock_session.return_value = AsyncMock()

            with patch.object(account_client._api_methods, 'get_mark_price') as mock_api:
                mock_api.return_value = None

                result = await account_client.get_mark_price(symbol)

                assert result is None


class TestHealthAndMonitoring:
    """Test health check and monitoring functionality."""

    @pytest.mark.asyncio
    async def test_health_check_success(self, account_client):
        """Test successful health check."""
        with patch.object(account_client._session_manager, 'create_session') as mock_session:
            mock_session.return_value = AsyncMock()

            with patch.object(account_client._session_manager, 'health_check') as mock_health:
                mock_health.return_value = True

                result = await account_client.health_check()

                assert result is True
                mock_session.assert_called_once()
                mock_health.assert_called_once()

    @pytest.mark.asyncio
    async def test_health_check_failure(self, account_client):
        """Test health check failure."""
        with patch.object(account_client._session_manager, 'create_session') as mock_session:
            mock_session.return_value = AsyncMock()

            with patch.object(account_client._session_manager, 'health_check') as mock_health:
                mock_health.return_value = False

                result = await account_client.health_check()

                assert result is False

    @pytest.mark.asyncio
    async def test_health_check_exception(self, account_client):
        """Test health check with exception."""
        with patch.object(account_client._session_manager, 'create_session') as mock_session:
            mock_session.side_effect = Exception("Connection error")

            result = await account_client.health_check()

            assert result is False

    def test_get_statistics(self, account_client):
        """Test getting performance statistics."""
        # Mock the statistics property directly
        account_client._monitor._statistics = Mock()
        account_client._monitor._statistics.total_requests = 10
        account_client._monitor._statistics.failed_requests = 1

        stats = account_client.get_statistics()
        assert stats.total_requests == 10
        assert stats.failed_requests == 1


class TestLifecycleManagement:
    """Test client lifecycle management."""

    @pytest.mark.asyncio
    async def test_close_success(self, account_client):
        """Test successful client closure."""
        with patch.object(account_client._session_manager, 'close_session') as mock_close:
            await account_client.close()

            assert account_client._closed is True
            mock_close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_already_closed(self, account_client):
        """Test closing already closed client."""
        account_client._closed = True

        with patch.object(account_client._session_manager, 'close_session') as mock_close:
            await account_client.close()

            mock_close.assert_not_called()

    @pytest.mark.asyncio
    async def test_context_manager_success(self, account_client):
        """Test async context manager usage."""
        with patch.object(account_client, 'close') as mock_close:
            async with account_client as client:
                assert client is account_client
                assert not account_client._closed

            mock_close.assert_called_once()

    @pytest.mark.asyncio
    async def test_context_manager_with_exception(self, account_client):
        """Test context manager with exception."""
        with patch.object(account_client, 'close') as mock_close:
            with pytest.raises(ValueError):
                async with account_client as client:
                    raise ValueError("Test exception")

            mock_close.assert_called_once()

    def test_del_warning(self, connection_config):
        """Test __del__ warning when client not properly closed."""
        import logging
        from unittest.mock import patch

        with patch('aster_client.account_client.logger') as mock_logger:
            client = AsterClient(connection_config)
            # Manually trigger __del__ by removing references
            client.__del__()

            mock_logger.warning.assert_called_once_with(
                "AsterClient not properly closed - call close() explicitly"
            )


class TestExecuteWithMonitoring:
    """Test the _execute_with_monitoring method."""

    @pytest.mark.asyncio
    async def test_execute_with_monitoring_success(self, account_client):
        """Test successful execution with monitoring."""
        mock_api_method = AsyncMock(return_value="success")

        with patch.object(account_client._session_manager, 'create_session') as mock_session:
            mock_session.return_value = AsyncMock()

            with patch.object(account_client._monitor, 'record_request') as mock_record:
                result = await account_client._execute_with_monitoring(
                    mock_api_method, "GET", "/test"
                )

                assert result == "success"
                mock_session.assert_called_once()
                mock_api_method.assert_called_once_with(mock_session.return_value)
                mock_record.assert_called_once_with("/test", "GET", 200, unittest.mock.ANY)

    @pytest.mark.asyncio
    async def test_execute_with_monitoring_with_args(self, account_client):
        """Test execution with monitoring and arguments."""
        mock_api_method = AsyncMock(return_value="success")
        test_arg = "test_arg"

        with patch.object(account_client._session_manager, 'create_session') as mock_session:
            mock_session.return_value = AsyncMock()

            with patch.object(account_client._monitor, 'record_request') as mock_record:
                result = await account_client._execute_with_monitoring(
                    mock_api_method, "POST", "/orders", test_arg
                )

                assert result == "success"
                mock_api_method.assert_called_once_with(mock_session.return_value, test_arg)

    @pytest.mark.asyncio
    async def test_execute_with_monitoring_closed_client(self, account_client):
        """Test execution when client is closed."""
        account_client._closed = True

        with pytest.raises(RuntimeError, match="Client is closed"):
            await account_client._execute_with_monitoring(
                AsyncMock(), "GET", "/test"
            )

    @pytest.mark.asyncio
    async def test_execute_with_monitoring_api_error(self, account_client):
        """Test execution with API error."""
        mock_api_method = AsyncMock(side_effect=Exception("API Error"))

        with patch.object(account_client._session_manager, 'create_session') as mock_session:
            mock_session.return_value = AsyncMock()

            with patch.object(account_client._monitor, 'record_request') as mock_record:
                with pytest.raises(Exception, match="API Error"):
                    await account_client._execute_with_monitoring(
                        mock_api_method, "GET", "/test"
                    )

                # Should record error metrics
                assert mock_record.call_count == 1
                call_args = mock_record.call_args[0]
                assert call_args[0] == "/test"  # endpoint
                assert call_args[1] == "GET"    # method
                assert call_args[2] == 500      # status_code (ERROR_STATUS_CODE)


class TestErrorHandling:
    """Test error handling scenarios."""

    @pytest.mark.asyncio
    async def test_api_method_exception(self, account_client):
        """Test handling of API method exceptions."""
        with patch.object(account_client._session_manager, 'create_session') as mock_session:
            mock_session.return_value = AsyncMock()

            with patch.object(account_client._api_methods, 'get_account_info') as mock_api:
                mock_api.side_effect = Exception("API Error")

                with pytest.raises(Exception, match="API Error"):
                    await account_client.get_account_info()

    @pytest.mark.asyncio
    async def test_session_creation_error(self, account_client):
        """Test handling of session creation errors."""
        with patch.object(account_client._session_manager, 'create_session') as mock_session:
            mock_session.side_effect = Exception("Session creation failed")

            with pytest.raises(Exception, match="Session creation failed"):
                await account_client.get_account_info()

    @pytest.mark.asyncio
    async def test_timeout_error(self, account_client):
        """Test handling of timeout errors."""
        with patch.object(account_client._session_manager, 'create_session') as mock_session:
            mock_session.return_value = AsyncMock()

            with patch.object(account_client._api_methods, 'get_account_info') as mock_api:
                mock_api.side_effect = asyncio.TimeoutError()

                with pytest.raises(asyncio.TimeoutError):
                    await account_client.get_account_info()


class TestIntegration:
    """Integration tests for AsterClient."""

    @pytest.mark.asyncio
    async def test_full_workflow(self, account_client, sample_order_request, order_response_data):
        """Test full workflow with multiple operations."""
        with patch.object(account_client._session_manager, 'create_session') as mock_session:
            mock_session.return_value = AsyncMock()

            with patch.object(account_client._api_methods, 'get_account_info') as mock_account:
                with patch.object(account_client._api_methods, 'place_order') as mock_order:
                    with patch.object(account_client._api_methods, 'get_orders') as mock_get_orders:

                        mock_account.return_value = {"account_id": "test"}
                        mock_order.return_value = order_response_data
                        mock_get_orders.return_value = [order_response_data]

                        # Execute workflow
                        account_info = await account_client.get_account_info()
                        order_response = await account_client.place_order(sample_order_request)
                        orders = await account_client.get_orders()

                        assert account_info == {"account_id": "test"}
                        assert order_response == order_response_data
                        assert orders == [order_response_data]

                        # Verify session was created for each call
                        assert mock_session.call_count == 3

    @pytest.mark.asyncio
    async def test_concurrent_requests(self, account_client):
        """Test handling concurrent requests."""
        with patch.object(account_client._session_manager, 'create_session') as mock_session:
            mock_session.return_value = AsyncMock()

            with patch.object(account_client._api_methods, 'get_account_info') as mock_account:
                mock_account.return_value = {"account_id": "test"}

                # Create multiple concurrent requests
                tasks = [
                    account_client.get_account_info()
                    for _ in range(5)
                ]

                results = await asyncio.gather(*tasks)

                # All should succeed
                assert all(result == {"account_id": "test"} for result in results)
                # Should make 5 calls
                assert mock_account.call_count == 5

    @pytest.mark.asyncio
    async def test_performance_monitoring_integration(self, account_client):
        """Test performance monitoring integration."""
        with patch.object(account_client._session_manager, 'create_session') as mock_session:
            mock_session.return_value = AsyncMock()

            with patch.object(account_client._api_methods, 'get_account_info') as mock_api:
                mock_api.return_value = {"account_id": "test"}

                with patch.object(account_client._monitor, 'record_request') as mock_record:
                    await account_client.get_account_info()

                    # Verify monitoring was called
                    mock_record.assert_called_once()
                    call_args = mock_record.call_args[0]
                    assert call_args[0] == "/account"  # endpoint
                    assert call_args[1] == "GET"      # method
                    assert call_args[2] == 200        # success status
                    assert isinstance(call_args[3], (int, float))  # duration_ms


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_empty_api_responses(self, account_client):
        """Test handling of empty API responses."""
        with patch.object(account_client._session_manager, 'create_session') as mock_session:
            mock_session.return_value = AsyncMock()

            with patch.object(account_client._api_methods, 'get_positions') as mock_positions:
                with patch.object(account_client._api_methods, 'get_balances') as mock_balances:
                    with patch.object(account_client._api_methods, 'get_orders') as mock_orders:

                        mock_positions.return_value = []
                        mock_balances.return_value = []
                        mock_orders.return_value = []

                        positions = await account_client.get_positions()
                        balances = await account_client.get_balances()
                        orders = await account_client.get_orders()

                        assert positions == []
                        assert balances == []
                        assert orders == []

    @pytest.mark.asyncio
    async def test_malformed_api_response(self, account_client):
        """Test handling of malformed API responses."""
        with patch.object(account_client._session_manager, 'create_session') as mock_session:
            mock_session.return_value = AsyncMock()

            with patch.object(account_client._api_methods, 'get_account_info') as mock_api:
                # Return response that's missing expected fields
                mock_api.return_value = {"incomplete": "data"}

                result = await account_client.get_account_info()
                assert result == {"incomplete": "data"}

    @pytest.mark.asyncio
    async def test_invalid_symbols(self, account_client):
        """Test handling of invalid symbols."""
        invalid_symbols = ["", "INVALID", "toolong" * 20]

        with patch.object(account_client._session_manager, 'create_session') as mock_session:
            mock_session.return_value = AsyncMock()

            with patch.object(account_client._api_methods, 'get_mark_price') as mock_api:
                mock_api.return_value = None

                for symbol in invalid_symbols:
                    result = await account_client.get_mark_price(symbol)
                    assert result is None

    @pytest.mark.asyncio
    async def test_very_large_decimal_values(self, account_client):
        """Test handling of very large decimal values."""
        with patch.object(account_client._session_manager, 'create_session') as mock_session:
            mock_session.return_value = AsyncMock()

            with patch.object(account_client._api_methods, 'get_balances') as mock_api:
                # Use very large decimal values
                large_balances = [
                    {
                        "asset_id": "test",
                        "currency": "TEST",
                        "cash": "999999999999999999.99",
                        "tradeable": True,
                        "pending_buy": "0.00",
                        "pending_sell": "0.00"
                    }
                ]
                mock_api.return_value = large_balances

                result = await account_client.get_balances()
                assert result == large_balances

    @pytest.mark.asyncio
    async def test_unicode_handling(self, account_client):
        """Test handling of unicode characters in responses."""
        with patch.object(account_client._session_manager, 'create_session') as mock_session:
            mock_session.return_value = AsyncMock()

            with patch.object(account_client._api_methods, 'get_account_info') as mock_api:
                unicode_response = {
                    "account_id": "测试账户",
                    "account_type": "margin",
                    "status": "活跃",
                    "buying_power": "100000.00"
                }
                mock_api.return_value = unicode_response

                result = await account_client.get_account_info()
                assert result == unicode_response