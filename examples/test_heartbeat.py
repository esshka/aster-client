"""
Test script to verify heartbeat message handling in zmq_listener.
"""

import asyncio
import logging
from aster_client.zmq_listener import ZMQTradeListener

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

async def test_heartbeat_processing():
    """Test that heartbeat messages are processed correctly."""
    
    # Create a listener instance
    listener = ZMQTradeListener(zmq_url="tcp://127.0.0.1:5555", log_dir="logs/test")
    
    # Test heartbeat message
    heartbeat_message = {
        "type": "heartbeat",
        "status": "connected",
        "timestamp": "2025-11-20T18:11:20.178966+00:00",
        "message": "TradesExecutor initialized and ready to send signals",
        "accounts_loaded": 2
    }
    
    print("\n" + "="*60)
    print("Testing heartbeat message processing...")
    print("="*60)
    
    # Process the heartbeat message
    await listener.process_message(heartbeat_message)
    
    print("✅ Heartbeat message processed without errors!\n")
    
    # Test trade message (partial - just to see it's detected as trade)
    trade_message = {
        "type": "trade",
        "symbol": "BTCUSDT",
        "side": "buy"
    }
    
    print("="*60)
    print("Testing trade message detection...")
    print("="*60)
    
    try:
        await listener.process_message(trade_message)
    except KeyError as e:
        print(f"✅ Trade message detected (expected error for incomplete message: {e})\n")

if __name__ == "__main__":
    asyncio.run(test_heartbeat_processing())
