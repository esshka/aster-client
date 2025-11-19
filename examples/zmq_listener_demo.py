import asyncio
import logging
import sys
import os

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), "../src"))

from aster_client.zmq_listener import ZMQTradeListener

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

async def main():
    # Connect to the publisher (sender)
    zmq_url = "tcp://127.0.0.1:5555"
    listener = ZMQTradeListener(zmq_url=zmq_url)
    
    try:
        await listener.start()
    except KeyboardInterrupt:
        await listener.stop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
