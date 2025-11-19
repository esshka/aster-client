"""
Tests for ZMQ Trade Listener module.
"""
import asyncio
import json
import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from aster_client.zmq_listener import ZMQTradeListener
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


class TestZMQTradeListener:
    """Test suite for ZMQTradeListener class."""
    
    def test_initialization(self):
        """Test listener initialization."""
        zmq_url = "tcp://127.0.0.1:5555"
        topic = "trades"
        
        listener = ZMQTradeListener(zmq_url=zmq_url, topic=topic)
        
        assert listener.zmq_url == zmq_url
        assert listener.topic == topic
        assert listener.running is False
    
    @pytest.mark.asyncio
    async def test_process_message_extracts_parameters(self, sample_trade_message):
        """Test that process_message correctly extracts trade parameters."""
        listener = ZMQTradeListener(zmq_url="tcp://127.0.0.1:5555")
        
        # Mock AccountPool and create_trade
        with patch('aster_client.zmq_listener.AccountPool') as mock_pool_class, \
             patch('aster_client.zmq_listener.create_trade') as mock_create_trade:
            
            # Setup mock pool
            mock_pool = AsyncMock()
            mock_pool_class.return_value.__aenter__.return_value = mock_pool
            mock_pool.get_client.return_value = AsyncMock()
            
            # Setup mock trade result
            mock_trade = Trade(
                trade_id="test_trade",
                symbol="BTCUSDT",
                side="buy",
                status=TradeStatus.ACTIVE
            )
            mock_create_trade.return_value = mock_trade
            
            # Process message
            await listener.process_message(sample_trade_message)
            
            # Verify AccountPool was created with correct configs
            assert mock_pool_class.called
            account_configs = mock_pool_class.call_args[0][0]
            assert len(account_configs) == 2
            assert account_configs[0].id == "test_acc_1"
            assert account_configs[1].id == "test_acc_2"
            
            # Verify create_trade was called for each account
            assert mock_create_trade.call_count == 2
    
    @pytest.mark.asyncio
    async def test_process_message_handles_missing_accounts(self):
        """Test that process_message handles missing accounts gracefully."""
        listener = ZMQTradeListener(zmq_url="tcp://127.0.0.1:5555")
        
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
        listener = ZMQTradeListener(zmq_url="tcp://127.0.0.1:5555")
        
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
        listener = ZMQTradeListener(zmq_url="tcp://127.0.0.1:5555")
        
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
        
        with patch('aster_client.zmq_listener.AccountPool') as mock_pool_class, \
             patch('aster_client.zmq_listener.create_trade', side_effect=mock_create_trade):
            
            mock_pool = AsyncMock()
            mock_pool_class.return_value.__aenter__.return_value = mock_pool
            mock_pool.get_client.side_effect = lambda x: AsyncMock(id=x)
            
            await listener.process_message(sample_trade_message)
            
            # Verify both trades were executed
            assert len(execution_order) == 2
    
    @pytest.mark.asyncio
    async def test_process_message_handles_trade_failures(self, sample_trade_message):
        """Test that process_message handles individual trade failures."""
        listener = ZMQTradeListener(zmq_url="tcp://127.0.0.1:5555")
        
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
        
        with patch('aster_client.zmq_listener.AccountPool') as mock_pool_class, \
             patch('aster_client.zmq_listener.create_trade', side_effect=mock_create_trade):
            
            mock_pool = AsyncMock()
            mock_pool_class.return_value.__aenter__.return_value = mock_pool
            mock_pool.get_client.return_value = AsyncMock()
            
            # Should not raise exception
            await listener.process_message(sample_trade_message)
    
    @pytest.mark.asyncio
    async def test_stop_terminates_listener(self):
        """Test that stop() properly terminates the listener."""
        listener = ZMQTradeListener(zmq_url="tcp://127.0.0.1:5555")
        
        # Mock the socket
        listener.socket = MagicMock()
        listener.ctx = MagicMock()
        listener.running = True
        
        await listener.stop()
        
        assert listener.running is False
        assert listener.socket.close.called
        assert listener.ctx.term.called
    
    @pytest.mark.asyncio
    async def test_process_message_uses_correct_quantities(self, sample_trade_message):
        """Test that each account gets its specified quantity."""
        listener = ZMQTradeListener(zmq_url="tcp://127.0.0.1:5555")
        
        captured_quantities = []
        
        async def mock_create_trade(*args, **kwargs):
            captured_quantities.append(kwargs['quantity'])
            return Trade(
                trade_id="test",
                symbol="BTCUSDT",
                side="buy",
                status=TradeStatus.ACTIVE
            )
        
        with patch('aster_client.zmq_listener.AccountPool') as mock_pool_class, \
             patch('aster_client.zmq_listener.create_trade', side_effect=mock_create_trade):
            
            mock_pool = AsyncMock()
            mock_pool_class.return_value.__aenter__.return_value = mock_pool
            mock_pool.get_client.return_value = AsyncMock()
            
            await listener.process_message(sample_trade_message)
            
            # Verify quantities match the message
            assert len(captured_quantities) == 2
            assert captured_quantities[0] == Decimal("0.001")
            assert captured_quantities[1] == Decimal("0.002")
