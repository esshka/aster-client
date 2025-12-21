#!/usr/bin/env python
"""
Run NATS Listener - Entry point script for the NATS Trade Listener.

Location: run_listener.py
Purpose: Entry point for running the NATS signal listener
Relevant files: src/aster_client/zmq_listener.py, config.yml

Usage:
    poetry run python run_listener.py
    poetry run python run_listener.py --nats_url nats://localhost:4222
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
    nats_config = config.get("nats", {})
    logging_config = config.get("logging", {})
    trading_config = config.get("trading", {})
    
    parser = argparse.ArgumentParser(description="Run NATS Trade Listener")
    parser.add_argument("--nats_url", default=nats_config.get("url", "nats://localhost:4222"))
    parser.add_argument("--subject", default=nats_config.get("subject", "orders"))
    parser.add_argument("--log_dir", default=logging_config.get("log_dir", "logs"))
    parser.add_argument("--log_level", default=logging_config.get("level", "INFO"))
    parser.add_argument("--symbol", default=trading_config.get("default_symbol", "SOLUSDT"))
    args = parser.parse_args()
    
    # Configure logging
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    # Load accounts
    accounts = load_accounts()
    
    # Import after parsing args to avoid the warning
    from aster_client.zmq_listener import NATSTradeListener
    from aster_client.bbo import BBOPriceCalculator
    
    # Initialize BBO with configured symbol
    BBOPriceCalculator(default_symbol=args.symbol)
    
    async def run():
        listener = NATSTradeListener(
            nats_url=args.nats_url,
            subject=args.subject,
            log_dir=args.log_dir,
            accounts=accounts
        )
        
        print(f"🚀 Starting NATS Listener on {args.nats_url} (subject: '{args.subject}')")
        print(f"📋 Loaded {len(accounts)} accounts from config")
        print(f"📊 BBO WebSocket symbol: {args.symbol}")
        
        try:
            await listener.start()
        except KeyboardInterrupt:
            print("\n⏹️  Shutting down...")
        finally:
            await listener.stop()
    
    asyncio.run(run())


if __name__ == "__main__":
    main()

