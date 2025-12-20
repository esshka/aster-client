#!/usr/bin/env python
"""
Run ZMQ Listener - Entry point script for the ZMQ Trade Listener.

Usage:
    poetry run python run_listener.py
    poetry run python run_listener.py --zmq_url tcp://127.0.0.1:5557
"""

import asyncio
import argparse
import logging
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


def load_accounts():
    """Load accounts from accounts_config.yml"""
    accounts_path = Path(__file__).parent / "accounts_config.yml"
    if accounts_path.exists():
        with open(accounts_path) as f:
            data = yaml.safe_load(f)
            return data.get("accounts", []) if data else []
    return []


def main():
    config = load_config()
    zmq_config = config.get("zmq", {})
    logging_config = config.get("logging", {})
    
    parser = argparse.ArgumentParser(description="Run ZMQ Trade Listener")
    parser.add_argument("--zmq_url", default=zmq_config.get("url", "tcp://127.0.0.1:5556"))
    parser.add_argument("--topic", default=zmq_config.get("topic", "orders"))
    parser.add_argument("--log_dir", default=logging_config.get("log_dir", "logs"))
    parser.add_argument("--log_level", default=logging_config.get("level", "INFO"))
    args = parser.parse_args()
    
    # Configure logging
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    # Load accounts
    accounts = load_accounts()
    
    # Import after parsing args to avoid the warning
    from aster_client.zmq_listener import ZMQTradeListener
    
    async def run():
        listener = ZMQTradeListener(
            zmq_url=args.zmq_url,
            topic=args.topic,
            log_dir=args.log_dir,
            accounts=accounts
        )
        
        print(f"🚀 Starting ZMQ Listener on {args.zmq_url} (topic: '{args.topic}')")
        print(f"📋 Loaded {len(accounts)} accounts from config")
        
        try:
            await listener.start()
        except KeyboardInterrupt:
            print("\n⏹️  Shutting down...")
        finally:
            await listener.stop()
    
    asyncio.run(run())


if __name__ == "__main__":
    main()

