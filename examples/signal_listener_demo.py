"""
Signal Listener Demo - Demonstrates the ZMQ Signal Listener.

This script connects to a ZMQ publisher and listens for ENTRY/EXIT/PARTIAL_EXIT
signals, executing them across all accounts configured in accounts_config.yml.

Usage:
    python examples/signal_listener_demo.py
    
    # With custom ZMQ URL:
    ZMQ_URL=tcp://192.168.1.100:5555 python examples/signal_listener_demo.py

Requirements:
    - accounts_config.yml in the project root with account credentials
    - ZMQ publisher sending signals on the "orders" topic
"""

import asyncio
import logging
import signal
import sys
from pathlib import Path

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from aster_client import ZMQSignalListener


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


async def main():
    """Main entry point."""
    logger.info("=" * 60)
    logger.info("🚀 ZMQ Signal Listener Demo")
    logger.info("=" * 60)
    
    # Create listener
    listener = ZMQSignalListener(
        topic="orders",
        config_path="accounts_config.yml",
    )
    
    # Handle shutdown gracefully
    loop = asyncio.get_event_loop()
    
    def shutdown_handler():
        logger.info("\n⚠️ Shutdown signal received...")
        asyncio.create_task(listener.stop())
    
    # Register signal handlers
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, shutdown_handler)
    
    try:
        await listener.start()
    except Exception as e:
        logger.error(f"Error in listener: {e}")
    finally:
        await listener.stop()
    
    logger.info("👋 Signal listener stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
