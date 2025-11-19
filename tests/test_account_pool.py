# -*- coding: utf-8 -*-
"""
Comprehensive tests for AccountPool.
"""

import pytest
import asyncio
from decimal import Decimal
from unittest.mock import Mock, AsyncMock, patch, MagicMock

from aster_client.account_pool import AccountPool, AccountConfig, AccountResult
from aster_client.models import (
    AccountInfo, Balance, Position, OrderRequest, OrderResponse,
    ConnectionConfig, RetryConfig
)


class TestAccountConfig:
    """Test AccountConfig dataclass."""
    
    def test_account_config_creation(self):
        """Test creating AccountConfig."""
        config = AccountConfig(
            id="test_account",
            api_key="test_key_longer_than_20_chars",
            api_secret="test_secret_longer_than_20_chars"
        )
        
        assert config.id == "test_account"
        assert config.api_key == "test_key_longer_than_20_chars"
        assert config.api_secret == "test_secret_longer_than_20_chars"
        assert config.simulation is False
        assert config.recv_window == 5000
    
    def test_account_config_with_optional_params(self):
        """Test AccountConfig with optional parameters."""
        config = AccountConfig(
            id="custom_account",
            api_key="key123key123key123key123",
            api_secret="secret123secret123secret123",
            base_url="https://custom.api.com",
            timeout=30.0,
            simulation=True,
            recv_window=10000
        )
        
        assert config.base_url == "https://custom.api.com"
        assert config.timeout == 30.0
        assert config.simulation is True
        assert config.recv_window == 10000


class TestAccountResult:
    """Test AccountResult dataclass."""
    
    def test_account_result_success(self):
        """Test successful AccountResult."""
        result = AccountResult(
            account_id="acc1",
            success=True,
            result={"data": "test"}
        )
        
        assert result.account_id == "acc1"
        assert result.success is True
        assert result.result == {"data": "test"}
        assert result.error is None
    
    def test_account_result_failure(self):
        """Test failed AccountResult."""
        error = Exception("Test error")
        result = AccountResult(
            account_id="acc2",
            success=False,
            error=error
        )
        
        assert result.account_id == "acc2"
        assert result.success is False
        assert result.result is None
        assert result.error == error


class TestAccountPoolInit:
    """Test AccountPool initialization."""
    
    def test_init_with_valid_accounts(self):
        """Test initialization with valid accounts."""
        accounts = [
            AccountConfig(id="acc1", api_key="key1key1key1key1key1key1", api_secret="sec1sec1sec1sec1sec1sec1"),
            AccountConfig(id="acc2", api_key="key2key2key2key2key2key2", api_secret="sec2sec2sec2sec2sec2sec2"),
        ]
        
        pool = AccountPool(accounts)
        
        assert pool.account_count == 2
        assert not pool._closed
    
    def test_init_with_empty_accounts(self):
        """Test initialization with empty accounts list."""
        with pytest.raises(ValueError, match="Accounts list cannot be empty"):
            AccountPool([])
    
    def test_init_with_duplicate_ids(self):
        """Test initialization with duplicate account IDs."""
        accounts = [
            AccountConfig(id="acc1", api_key="key1key1key1key1key1key1", api_secret="sec1sec1sec1sec1sec1sec1"),
            AccountConfig(id="acc1", api_key="key2key2key2key2key2key2", api_secret="sec2sec2sec2sec2sec2sec2"),
        ]
        
        with pytest.raises(ValueError, match="Duplicate account IDs found"):
            AccountPool(accounts)
    
    def test_init_with_retry_config(self):
        """Test initialization with retry config."""
        accounts = [
            AccountConfig(id="acc1", api_key="key1key1key1key1key1key1", api_secret="sec1sec1sec1sec1sec1sec1"),
        ]
        retry_config = RetryConfig(max_retries=5, retry_delay=2.0)
        
        pool = AccountPool(accounts, retry_config)
        
        assert pool._retry_config == retry_config


class TestAccountPoolClientManagement:
    """Test AccountPool client management."""
    
    @pytest.mark.asyncio
    async def test_initialize_clients(self):
        """Test client initialization."""
        accounts = [
            AccountConfig(id="acc1", api_key="key1key1key1key1key1key1", api_secret="sec1sec1sec1sec1sec1sec1"),
            AccountConfig(id="acc2", api_key="key2key2key2key2key2key2", api_secret="sec2sec2sec2sec2sec2sec2"),
        ]
        
        pool = AccountPool(accounts)
        await pool._initialize_clients()
        
        assert len(pool._clients) == 2
        assert "acc1" in pool._clients
        assert "acc2" in pool._clients
    
    @pytest.mark.asyncio
    async def test_get_client(self):
        """Test getting individual client."""
        accounts = [
            AccountConfig(id="acc1", api_key="key1key1key1key1key1key1", api_secret="sec1sec1sec1sec1sec1sec1"),
        ]
        
        pool = AccountPool(accounts)
        await pool._initialize_clients()
        
        client = pool.get_client("acc1")
        assert client is not None
        
        client = pool.get_client("nonexistent")
        assert client is None


class TestAccountPoolContextManager:
    """Test AccountPool context manager."""
    
    @pytest.mark.asyncio
    async def test_context_manager_success(self):
        """Test async context manager usage."""
        accounts = [
            AccountConfig(id="acc1", api_key="key1key1key1key1key1key1", api_secret="sec1sec1sec1sec1sec1sec1"),
        ]
        
        pool = AccountPool(accounts)
        
        async with pool as p:
            assert p is pool
            assert len(p._clients) == 1
            assert not p._closed
        
        assert pool._closed
    
    @pytest.mark.asyncio
    async def test_context_manager_with_exception(self):
        """Test context manager with exception."""
        accounts = [
            AccountConfig(id="acc1", api_key="key1key1key1key1key1key1", api_secret="sec1sec1sec1sec1sec1sec1"),
        ]
        
        pool = AccountPool(accounts)
        
        with pytest.raises(ValueError):
            async with pool:
                raise ValueError("Test exception")
        
        assert pool._closed


class TestAccountPoolParallelExecution:
    """Test AccountPool parallel execution methods."""
    
    @pytest.mark.asyncio
    async def test_execute_parallel_success(self):
        """Test successful parallel execution."""
        accounts = [
            AccountConfig(id="acc1", api_key="key1key1key1key1key1key1", api_secret="sec1sec1sec1sec1sec1sec1"),
            AccountConfig(id="acc2", api_key="key2key2key2key2key2key2", api_secret="sec2sec2sec2sec2sec2sec2"),
        ]
        
        async with AccountPool(accounts) as pool:
            # Mock function to execute
            async def mock_func(client):
                return f"result_for_{client._config.api_key[:4]}"
            
            results = await pool.execute_parallel(mock_func)
            
            assert len(results) == 2
            assert all(r.success for r in results)
            assert results[0].account_id == "acc1"
            assert results[1].account_id == "acc2"
    
    @pytest.mark.asyncio
    async def test_execute_parallel_with_errors(self):
        """Test parallel execution with some failures."""
        accounts = [
            AccountConfig(id="acc1", api_key="key1key1key1key1key1key1", api_secret="sec1sec1sec1sec1sec1sec1"),
            AccountConfig(id="acc2", api_key="key2key2key2key2key2key2", api_secret="sec2sec2sec2sec2sec2sec2"),
        ]
        
        async with AccountPool(accounts) as pool:
            # Mock function that fails for acc2
            call_count = 0
            async def mock_func(client):
                nonlocal call_count
                call_count += 1
                if call_count == 2:
                    raise Exception("Test error")
                return "success"
            
            results = await pool.execute_parallel(mock_func)
            
            assert len(results) == 2
            assert results[0].success is True
            assert results[0].result == "success"
            assert results[1].success is False
            assert isinstance(results[1].error, Exception)
    
    @pytest.mark.asyncio
    async def test_execute_parallel_closed_pool(self):
        """Test execution on closed pool."""
        accounts = [
            AccountConfig(id="acc1", api_key="key1key1key1key1key1key1", api_secret="sec1sec1sec1sec1sec1sec1"),
        ]
        
        pool = AccountPool(accounts)
        await pool._initialize_clients()
        await pool.close()
        
        with pytest.raises(RuntimeError, match="AccountPool is closed"):
            async def mock_func(client):
                return "test"
            await pool.execute_parallel(mock_func)


class TestAccountPoolAccountInfoMethods:
    """Test AccountPool account info methods."""
    
    @pytest.mark.asyncio
    async def test_get_accounts_info_parallel(self):
        """Test parallel account info retrieval."""
        accounts = [
            AccountConfig(id="acc1", api_key="key1key1key1key1key1key1", api_secret="sec1sec1sec1sec1sec1sec1"),
            AccountConfig(id="acc2", api_key="key2key2key2key2key2key2", api_secret="sec2sec2sec2sec2sec2sec2"),
        ]
        
        mock_info = Mock(spec=AccountInfo)
        
        async with AccountPool(accounts) as pool:
            # Mock get_account_info for all clients
            for client in pool._clients.values():
                client.get_account_info = AsyncMock(return_value=mock_info)
            
            results = await pool.get_accounts_info_parallel()
            
            assert len(results) == 2
            assert all(r.success for r in results)
            assert all(r.result == mock_info for r in results)
    
    @pytest.mark.asyncio
    async def test_get_positions_parallel(self):
        """Test parallel positions retrieval."""
        accounts = [
            AccountConfig(id="acc1", api_key="key1key1key1key1key1key1", api_secret="sec1sec1sec1sec1sec1sec1"),
        ]
        
        mock_positions = [Mock(spec=Position)]
        
        async with AccountPool(accounts) as pool:
            for client in pool._clients.values():
                client.get_positions = AsyncMock(return_value=mock_positions)
            
            results = await pool.get_positions_parallel()
            
            assert len(results) == 1
            assert results[0].success
            assert results[0].result == mock_positions
    
    @pytest.mark.asyncio
    async def test_get_balances_parallel(self):
        """Test parallel balances retrieval."""
        accounts = [
            AccountConfig(id="acc1", api_key="key1key1key1key1key1key1", api_secret="sec1sec1sec1sec1sec1sec1"),
        ]
        
        mock_balances = [Mock(spec=Balance)]
        
        async with AccountPool(accounts) as pool:
            for client in pool._clients.values():
                client.get_balances = AsyncMock(return_value=mock_balances)
            
            results = await pool.get_balances_parallel()
            
            assert len(results) == 1
            assert results[0].success
            assert results[0].result == mock_balances


class TestAccountPoolOrderMethods:
    """Test AccountPool order methods."""
    
    @pytest.mark.asyncio
    async def test_place_orders_parallel_single_order(self):
        """Test placing same order across all accounts."""
        accounts = [
            AccountConfig(id="acc1", api_key="key1key1key1key1key1key1", api_secret="sec1sec1sec1sec1sec1sec1"),
            AccountConfig(id="acc2", api_key="key2key2key2key2key2key2", api_secret="sec2sec2sec2sec2sec2sec2"),
        ]
        
        order = OrderRequest(
            symbol="BTCUSDT",
            side="buy",
            order_type="limit",
            quantity=Decimal("0.001"),
            price=Decimal("45000")
        )
        
        mock_response = Mock(spec=OrderResponse)
        
        async with AccountPool(accounts) as pool:
            for client in pool._clients.values():
                client.place_order = AsyncMock(return_value=mock_response)
            
            results = await pool.place_orders_parallel(order)
            
            assert len(results) == 2
            assert all(r.success for r in results)
            assert all(r.result == mock_response for r in results)
    
    @pytest.mark.asyncio
    async def test_place_orders_parallel_multiple_orders(self):
        """Test placing different orders for each account."""
        accounts = [
            AccountConfig(id="acc1", api_key="key1key1key1key1key1key1", api_secret="sec1sec1sec1sec1sec1sec1"),
            AccountConfig(id="acc2", api_key="key2key2key2key2key2key2", api_secret="sec2sec2sec2sec2sec2sec2"),
        ]
        
        orders = [
            OrderRequest(
                symbol="BTCUSDT",
                side="buy",
                order_type="limit",
                quantity=Decimal("0.001"),
                price=Decimal("45000")
            ),
            OrderRequest(
                symbol="ETHUSDT",
                side="sell",
                order_type="limit",
                quantity=Decimal("0.01"),
                price=Decimal("3000")
            ),
        ]
        
        mock_response = Mock(spec=OrderResponse)
        
        async with AccountPool(accounts) as pool:
            for client in pool._clients.values():
                client.place_order = AsyncMock(return_value=mock_response)
            
            results = await pool.place_orders_parallel(orders)
            
            assert len(results) == 2
            assert all(r.success for r in results)
    
    @pytest.mark.asyncio
    async def test_place_orders_parallel_invalid_count(self):
        """Test placing orders with mismatched count."""
        accounts = [
            AccountConfig(id="acc1", api_key="key1key1key1key1key1key1", api_secret="sec1sec1sec1sec1sec1sec1"),
        ]
        
        orders = [
            Mock(spec=OrderRequest),
            Mock(spec=OrderRequest),  # Too many orders
        ]
        
        async with AccountPool(accounts) as pool:
            with pytest.raises(ValueError, match="must match account count"):
                await pool.place_orders_parallel(orders)
    
    @pytest.mark.asyncio
    async def test_place_bbo_orders_parallel(self):
        """Test placing BBO orders in parallel."""
        accounts = [
            AccountConfig(id="acc1", api_key="key1key1key1key1key1key1", api_secret="sec1sec1sec1sec1sec1sec1"),
            AccountConfig(id="acc2", api_key="key2key2key2key2key2key2", api_secret="sec2sec2sec2sec2sec2sec2"),
        ]
        
        mock_response = Mock(spec=OrderResponse)
        
        async with AccountPool(accounts) as pool:
            for client in pool._clients.values():
                client.place_bbo_order = AsyncMock(return_value=mock_response)
            
            results = await pool.place_bbo_orders_parallel(
                symbol="BTCUSDT",
                side="buy",
                quantity=Decimal("0.001"),
                market_price=Decimal("45000"),
                tick_size=Decimal("0.1"),
                ticks_distance=2
            )
            
            assert len(results) == 2
            assert all(r.success for r in results)
    
    @pytest.mark.asyncio
    async def test_place_bbo_orders_parallel_with_quantities(self):
        """Test placing BBO orders with different quantities."""
        accounts = [
            AccountConfig(id="acc1", api_key="key1key1key1key1key1key1", api_secret="sec1sec1sec1sec1sec1sec1"),
            AccountConfig(id="acc2", api_key="key2key2key2key2key2key2", api_secret="sec2sec2sec2sec2sec2sec2"),
        ]
        
        quantities = [Decimal("0.001"), Decimal("0.002")]
        mock_response = Mock(spec=OrderResponse)
        
        async with AccountPool(accounts) as pool:
            for client in pool._clients.values():
                client.place_bbo_order = AsyncMock(return_value=mock_response)
            
            results = await pool.place_bbo_orders_parallel(
                symbol="BTCUSDT",
                side="buy",
                quantity=quantities,
                market_price=Decimal("45000"),
                tick_size=Decimal("0.1")
            )
            
            assert len(results) == 2
    
    @pytest.mark.asyncio
    async def test_cancel_orders_parallel(self):
        """Test canceling orders in parallel."""
        accounts = [
            AccountConfig(id="acc1", api_key="key1key1key1key1key1key1", api_secret="sec1sec1sec1sec1sec1sec1"),
            AccountConfig(id="acc2", api_key="key2key2key2key2key2key2", api_secret="sec2sec2sec2sec2sec2sec2"),
        ]
        
        order_ids = [123, 456]
        
        async with AccountPool(accounts) as pool:
            for client in pool._clients.values():
                client.cancel_order = AsyncMock(return_value={"status": "cancelled"})
            
            results = await pool.cancel_orders_parallel(
                symbol="BTCUSDT",
                order_ids=order_ids
            )
            
            assert len(results) == 2
            assert all(r.success for r in results)


class TestAccountPoolEdgeCases:
    """Test edge cases and error conditions."""
    
    @pytest.mark.asyncio
    async def test_all_operations_fail(self):
        """Test when all operations fail."""
        accounts = [
            AccountConfig(id="acc1", api_key="key1key1key1key1key1key1", api_secret="sec1sec1sec1sec1sec1sec1"),
            AccountConfig(id="acc2", api_key="key2key2key2key2key2key2", api_secret="sec2sec2sec2sec2sec2sec2"),
        ]
        
        async with AccountPool(accounts) as pool:
            for client in pool._clients.values():
                client.get_account_info = AsyncMock(side_effect=Exception("API Error"))
            
            results = await pool.get_accounts_info_parallel()
            
            assert len(results) == 2
            assert all(not r.success for r in results)
            assert all(isinstance(r.error, Exception) for r in results)
    
    @pytest.mark.asyncio
    async def test_mixed_success_failure(self):
        """Test mixed success and failure results."""
        accounts = [
            AccountConfig(id="acc1", api_key="key1key1key1key1key1key1", api_secret="sec1sec1sec1sec1sec1sec1"),
            AccountConfig(id="acc2", api_key="key2key2key2key2key2key2", api_secret="sec2sec2sec2sec2sec2sec2"),
            AccountConfig(id="acc3", api_key="key3key3key3key3key3key3", api_secret="sec3sec3sec3sec3sec3sec3"),
        ]
        
        async with AccountPool(accounts) as pool:
            clients_list = list(pool._clients.values())
            clients_list[0].get_account_info = AsyncMock(return_value=Mock(spec=AccountInfo))
            clients_list[1].get_account_info = AsyncMock(side_effect=Exception("Error"))
            clients_list[2].get_account_info = AsyncMock(return_value=Mock(spec=AccountInfo))
            
            results = await pool.get_accounts_info_parallel()
            
            assert len(results) == 3
            assert results[0].success is True
            assert results[1].success is False
            assert results[2].success is True
