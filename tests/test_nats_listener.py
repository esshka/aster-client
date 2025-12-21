"""
Tests for NATS Trade Listener module.
"""
import asyncio
import json
import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from aster_client.nats_listener import NATSTradeListener
from aster_client.trades import Trade, TradeStatus


@pytest.fixture
def sample_trade_message():
    """Sample ZMQ trade message."""
    return {
        "symbol": "BTCUSDT",
        "side": "buy",
        "market_price": "90000.0",
        "tick_size": "0.1",
        "tp_percent": 1.0,
        "sl_percent": 0.5,
        "ticks_distance": 1,
        "accounts": [
            {
                "id": "test_acc_1",
                "api_key": "test_key_1_000000000000000000000000000000000000000",
                "api_secret": "test_secret_1_0000000000000000000000000000000000",
                "quantity": "0.001",
                "simulation": True
            },
            {
                "id": "test_acc_2",
                "api_key": "test_key_2_000000000000000000000000000000000000000",
                "api_secret": "test_secret_2_0000000000000000000000000000000000",
                "quantity": "0.002",
                "simulation": True
            }
        ]
    }


class TestNATSTradeListener:
    """Test suite for NATSTradeListener class."""
    
    def test_initialization(self):
        """Test listener initialization."""
        nats_url = "nats://127.0.0.1:4222"
        subject = "trades"
        
        listener = NATSTradeListener(nats_url=nats_url, subject=subject)
        
        assert listener.nats_url == nats_url
        assert listener.subject == subject
        assert listener.running is False
    
    @pytest.mark.asyncio
    async def test_process_message_extracts_parameters(self, sample_trade_message):
        """Test that process_message correctly extracts trade parameters."""
        listener = NATSTradeListener(nats_url="nats://127.0.0.1:4222")
        
        # Mock public_client methods
        listener.public_client.get_order_book = AsyncMock(return_value={
            "bids": [["90000.0", "1.0"]],
            "asks": [["90001.0", "1.0"]]
        })
        listener.public_client.get_symbol_info = AsyncMock(return_value=MagicMock(
            price_filter=MagicMock(tick_size="0.1")
        ))
        
        # Mock BBO calculator
        listener.bbo_calculator.get_bbo = MagicMock(return_value=(Decimal("90000.0"), Decimal("90001.0")))
        
        # Track accounts that were used
        created_accounts = []
        
        async def mock_get_or_create_client(account_id, api_key, api_secret, simulation=False):
            created_accounts.append(account_id)
            return AsyncMock()
        
        listener._get_or_create_client = mock_get_or_create_client
        
        # Mock create_trade
        with patch('aster_client.nats_listener.create_trade') as mock_create_trade:
            mock_trade = Trade(
                trade_id="test_trade",
                symbol="BTCUSDT",
                side="buy",
                status=TradeStatus.ACTIVE
            )
            mock_create_trade.return_value = mock_trade
            
            # Process message
            await listener.process_message(sample_trade_message)
            
            # Verify clients were created for each account
            assert len(created_accounts) == 2
            assert "test_acc_1" in created_accounts
            assert "test_acc_2" in created_accounts
            
            # Verify create_trade was called for each account
            assert mock_create_trade.call_count == 2
    
    @pytest.mark.asyncio
    async def test_process_message_handles_missing_accounts(self):
        """Test that process_message handles missing accounts gracefully."""
        listener = NATSTradeListener(nats_url="nats://127.0.0.1:4222")
        
        message_no_accounts = {
            "symbol": "BTCUSDT",
            "side": "buy",
            "market_price": "90000.0",
            "tick_size": "0.1",
            "tp_percent": 1.0,
            "sl_percent": 0.5,
        }
        
        # Should not raise exception
        await listener.process_message(message_no_accounts)
    
    @pytest.mark.asyncio
    async def test_process_message_handles_missing_fields(self):
        """Test that process_message handles missing required fields."""
        listener = NATSTradeListener(nats_url="nats://127.0.0.1:4222")
        
        incomplete_message = {
            "symbol": "BTCUSDT",
            # Missing side, market_price, etc.
            "accounts": []
        }
        
        # Should not raise exception, should log error
        await listener.process_message(incomplete_message)
    
    @pytest.mark.asyncio
    async def test_process_message_parallel_execution(self, sample_trade_message):
        """Test that trades are executed in parallel."""
        listener = NATSTradeListener(nats_url="nats://127.0.0.1:4222")
        
        execution_order = []
        
        async def mock_create_trade(*args, **kwargs):
            """Mock create_trade that tracks execution order."""
            client = kwargs.get('client')
            # Simulate some async work
            await asyncio.sleep(0.01)
            execution_order.append(client)
            
            return Trade(
                trade_id=f"trade_{len(execution_order)}",
                symbol="BTCUSDT",
                side="buy",
                status=TradeStatus.ACTIVE
            )
        
        # Mock public_client methods
        listener.public_client.get_order_book = AsyncMock(return_value={
            "bids": [["90000.0", "1.0"]],
            "asks": [["90001.0", "1.0"]]
        })
        listener.public_client.get_symbol_info = AsyncMock(return_value=MagicMock(
            price_filter=MagicMock(tick_size="0.1")
        ))
        
        # Mock BBO calculator
        listener.bbo_calculator.get_bbo = MagicMock(return_value=(Decimal("90000.0"), Decimal("90001.0")))
        
        with patch('aster_client.nats_listener.create_trade', side_effect=mock_create_trade):
            # Mock _get_or_create_client
            async def mock_get_or_create_client(account_id, api_key, api_secret, simulation=False):
                return AsyncMock(id=account_id)
            
            listener._get_or_create_client = mock_get_or_create_client
            
            await listener.process_message(sample_trade_message)
            
            # Verify both trades were executed
            assert len(execution_order) == 2
    
    @pytest.mark.asyncio
    async def test_process_message_handles_trade_failures(self, sample_trade_message):
        """Test that process_message handles individual trade failures."""
        listener = NATSTradeListener(nats_url="nats://127.0.0.1:4222")
        
        # Mock public_client methods
        listener.public_client.get_order_book = AsyncMock(return_value={
            "bids": [["90000.0", "1.0"]],
            "asks": [["90001.0", "1.0"]]
        })
        listener.public_client.get_symbol_info = AsyncMock(return_value=MagicMock(
            price_filter=MagicMock(tick_size="0.1")
        ))
        
        # Mock BBO calculator
        listener.bbo_calculator.get_bbo = MagicMock(return_value=(Decimal("90000.0"), Decimal("90001.0")))
        
        call_count = [0]
        
        async def mock_create_trade(*args, **kwargs):
            """Mock that fails for first call, succeeds for second."""
            call_count[0] += 1
            if call_count[0] == 1:
                raise Exception("Trade failed!")
            
            return Trade(
                trade_id="trade_2",
                symbol="BTCUSDT",
                side="buy",
                status=TradeStatus.ACTIVE
            )
        
        with patch('aster_client.nats_listener.create_trade', side_effect=mock_create_trade):
            # Mock _get_or_create_client
            async def mock_get_or_create_client(account_id, api_key, api_secret, simulation=False):
                return AsyncMock()
            
            listener._get_or_create_client = mock_get_or_create_client
            
            # Should not raise exception
            await listener.process_message(sample_trade_message)
    
    @pytest.mark.asyncio
    async def test_stop_terminates_listener(self):
        """Test that stop() properly terminates the listener."""
        listener = NATSTradeListener(nats_url="nats://127.0.0.1:4222")
        
        # Mock the NATS connection
        listener.nc = MagicMock()
        listener.nc.close = AsyncMock()
        listener.subscription = MagicMock()
        listener.subscription.unsubscribe = AsyncMock()
        listener.running = True
        
        # Mock BBO calculator stop
        listener.bbo_calculator.stop = AsyncMock()
        
        # Mock public_client close
        listener.public_client.close = AsyncMock()
        
        await listener.stop()
        
        assert listener.running is False
        assert listener.subscription.unsubscribe.called
        assert listener.nc.close.called
        assert listener.bbo_calculator.stop.called
    
    @pytest.mark.asyncio
    async def test_process_message_uses_correct_quantities(self, sample_trade_message):
        """Test that each account gets its specified quantity."""
        listener = NATSTradeListener(nats_url="nats://127.0.0.1:4222")
        
        # Mock public_client methods
        listener.public_client.get_order_book = AsyncMock(return_value={
            "bids": [["90000.0", "1.0"]],
            "asks": [["90001.0", "1.0"]]
        })
        listener.public_client.get_symbol_info = AsyncMock(return_value=MagicMock(
            price_filter=MagicMock(tick_size="0.1")
        ))
        
        # Mock BBO calculator
        listener.bbo_calculator.get_bbo = MagicMock(return_value=(Decimal("90000.0"), Decimal("90001.0")))
        
        captured_quantities = []
        
        async def mock_create_trade(*args, **kwargs):
            captured_quantities.append(kwargs['quantity'])
            return Trade(
                trade_id="test",
                symbol="BTCUSDT",
                side="buy",
                status=TradeStatus.ACTIVE
            )
        
        with patch('aster_client.nats_listener.create_trade', side_effect=mock_create_trade):
            # Mock _get_or_create_client
            async def mock_get_or_create_client(account_id, api_key, api_secret, simulation=False):
                return AsyncMock()
            
            listener._get_or_create_client = mock_get_or_create_client
            
            await listener.process_message(sample_trade_message)
            
            # Verify quantities match the message
            assert len(captured_quantities) == 2
            assert captured_quantities[0] == Decimal("0.001")
            assert captured_quantities[1] == Decimal("0.002")
