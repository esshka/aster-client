#!/usr/bin/env python
"""
Run NATS Signal Listener - Entry point script for the NATS Signal Listener.

Location: run_listener.py
Purpose: Entry point for running the NATS signal listener
Relevant files: src/aster_client/signal_listener.py, config.yml

Usage:
    poetry run python run_listener.py
    poetry run python run_listener.py --nats_url nats://localhost:4222
"""

import asyncio
import argparse
import logging
import signal
import sys
from pathlib import Path

import yaml


def load_config():
    """Load configuration from config.yml"""
    config_path = Path(__file__).parent / "config.yml"
    if config_path.exists():
        with open(config_path) as f:
            return yaml.safe_load(f)
    return {}


def main():
    config = load_config()
    nats_config = config.get("nats", {})
    logging_config = config.get("logging", {})
    trading_config = config.get("trading", {})
    
    parser = argparse.ArgumentParser(description="Run NATS Signal Listener")
    parser.add_argument("--nats_url", default=nats_config.get("url", "nats://localhost:4222"))
    parser.add_argument("--subject", default=nats_config.get("subject", "orders"))
    parser.add_argument("--log_dir", default=logging_config.get("log_dir", "logs"))
    parser.add_argument("--log_level", default=logging_config.get("level", "INFO"))
    parser.add_argument("--symbol", default=trading_config.get("default_symbol", "BTCUSDT"))
    args = parser.parse_args()
    
    # Configure logging
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    # Import after parsing args
    from aster_client.signal_listener import NATSSignalListener
    from aster_client.bbo import BBOPriceCalculator
    
    # Initialize BBO with configured symbol
    BBOPriceCalculator(default_symbol=args.symbol)
    
    async def run():
        listener = NATSSignalListener(
            nats_url=args.nats_url,
            subject=args.subject,
            config_path="accounts_config.yml",
            log_dir=args.log_dir,
        )
        
        print(f"🚀 Starting NATS Signal Listener on {args.nats_url} (subject: '{args.subject}')")
        print(f"📊 BBO WebSocket symbol: {args.symbol}")
        
        # Handle shutdown gracefully
        loop = asyncio.get_event_loop()
        
        def shutdown_handler():
            print("\n⏹️  Shutting down...")
            asyncio.create_task(listener.stop())
        
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, shutdown_handler)
        
        try:
            await listener.start()
        except Exception as e:
            logging.error(f"Error in listener: {e}")
        finally:
            await listener.stop()
    
    asyncio.run(run())


if __name__ == "__main__":
    main()
