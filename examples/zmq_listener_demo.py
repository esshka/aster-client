import asyncio
import logging
from dotenv import load_dotenv
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
    load_dotenv()
    zmq_url = os.getenv("ZMQ_URL", "tcp://127.0.0.1:5556")
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
