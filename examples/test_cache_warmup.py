"""
Test script to verify symbol cache warmup in ZMQ listener.
"""

import asyncio
import logging
from aster_client.zmq_listener import ZMQTradeListener

# Configure logging to see cache warmup messages
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

async def test_cache_warmup():
    """Test that cache is warmed up on listener start."""
    
    print("\n" + "="*60)
    print("Testing Symbol Cache Warmup")
    print("="*60 + "\n")
    
    # Create listener
    listener = ZMQTradeListener(zmq_url="tcp://127.0.0.1:5555", log_dir="logs/test")
    
    print("Created ZMQ listener instance")
    print(f"Public client instance: {listener.public_client}")
    print(f"Cache size before warmup: {len(listener.public_client._symbol_info_cache)}")
    
    print("\nStarting listener (this should trigger cache warmup)...")
    
    # Start in background task so we can monitor it
    start_task = asyncio.create_task(listener.start())
    
    # Give it a few seconds to warm up and start listening
    await asyncio.sleep(5)
    
    print(f"\nCache size after warmup: {len(listener.public_client._symbol_info_cache)}")
    
    if len(listener.public_client._symbol_info_cache) > 0:
        print(f"✅ SUCCESS: Cache warmed up with {len(listener.public_client._symbol_info_cache)} symbols")
        print("\nSample symbols in cache:")
        for i, symbol in enumerate(list(listener.public_client._symbol_info_cache.keys())[:5]):
            print(f"  {i+1}. {symbol}")
    else:
        print("❌ FAILED: Cache is empty after warmup")
    
    # Stop the listener
    print("\nStopping listener...")
    await listener.stop()
    
    # Cancel the start task
    start_task.cancel()
    try:
        await start_task
    except asyncio.CancelledError:
        pass
    
    print("\n" + "="*60)
    print("Test completed")
    print("="*60 + "\n")

if __name__ == "__main__":
    asyncio.run(test_cache_warmup())
