#!/usr/bin/env python3
"""
Example: Monitor Active Orders Across Multiple Accounts

This example demonstrates how to use get_orders_parallel() to monitor
active orders across multiple trading accounts in parallel.

Prerequisites:
- Create accounts_config.yml in the project root
- Install dependencies: poetry install

Usage:
    poetry run python examples/check_active_orders.py
"""

import asyncio
import logging
import sys
from pathlib import Path
import yaml

# Add parent directory to path for local development
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from aster_client import AccountPool, AccountConfig

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def load_accounts_from_config(config_path: str) -> list[AccountConfig]:
    """Load account configurations from YAML file."""
    config_file = Path(config_path)
    
    if not config_file.exists():
        raise FileNotFoundError(
            f"Configuration file not found: {config_path}\n"
            f"Please create {config_path} based on accounts_config.example.yml"
        )
    
    with open(config_file, 'r') as f:
        config = yaml.safe_load(f)
    
    if not config or 'accounts' not in config:
        raise ValueError(
            f"Invalid configuration file: {config_path}\n"
            "Expected 'accounts' key with list of account configurations"
        )
    
    accounts = []
    for acc_data in config['accounts']:
        accounts.append(AccountConfig(
            id=acc_data['id'],
            api_key=acc_data['api_key'],
            api_secret=acc_data['api_secret'],
            simulation=acc_data.get('simulation', False),
            recv_window=acc_data.get('recv_window', 10000),
        ))
    
    return accounts


def print_order_details(order):
    """Print formatted order details."""
    status_emoji = {
        "NEW": "🆕",
        "PARTIALLY_FILLED": "⏳",
        "FILLED": "✅",
        "CANCELED": "❌",
        "EXPIRED": "⏰",
    }
    
    emoji = status_emoji.get(order.status, "📋")
    
    print(f"    {emoji} Order #{order.order_id}")
    print(f"       Symbol: {order.symbol}")
    print(f"       Side: {order.side.upper()}")
    print(f"       Type: {order.type}")
    print(f"       Price: ${order.price}" if order.price else f"       Type: MARKET")
    print(f"       Quantity: {order.quantity}")
    print(f"       Filled: {order.executed_qty or 0}")
    print(f"       Status: {order.status}")
    if hasattr(order, 'time'):
        print(f"       Time: {order.time}")
    print()


async def main():
    """Main function to check active orders across all accounts."""
    CONFIG_FILE = "accounts_config.yml"
    
    print("=" * 70)
    print("ACTIVE ORDERS MONITOR - Multi-Account")
    print("=" * 70)
    
    try:
        # Load accounts from config
        project_root = Path(__file__).parent.parent
        config_path = project_root / CONFIG_FILE
        
        logger.info(f"Loading accounts from: {config_path}")
        accounts = load_accounts_from_config(str(config_path))
        logger.info(f"Found {len(accounts)} account(s)\n")
        
        async with AccountPool(accounts) as pool:
            # Get all active orders across all accounts
            print("\n📊 Fetching active orders from all accounts...\n")
            results = await pool.get_orders_parallel()
            
            total_orders = 0
            
            for result in results:
                print(f"\n{'='*70}")
                print(f"Account: {result.account_id}")
                print(f"{'='*70}")
                
                if result.success:
                    orders = result.result
                    total_orders += len(orders)
                    
                    if orders:
                        print(f"Found {len(orders)} active order(s):\n")
                        for order in orders:
                            print_order_details(order)
                    else:
                        print("✅ No active orders\n")
                else:
                    print(f"❌ Error: {result.error}\n")
            
            print(f"\n{'='*70}")
            print(f"SUMMARY")
            print(f"{'='*70}")
            print(f"Total Accounts: {len(accounts)}")
            print(f"Total Active Orders: {total_orders}")
            print(f"{'='*70}\n")
            
            # Example: Get orders for a specific symbol
            specific_symbol = "BTCUSDT"
            print(f"\n📊 Fetching {specific_symbol} orders only...\n")
            btc_results = await pool.get_orders_parallel(symbol=specific_symbol)
            
            btc_order_count = 0
            for result in btc_results:
                if result.success:
                    btc_order_count += len(result.result)
            
            print(f"Found {btc_order_count} {specific_symbol} order(s) across all accounts\n")
    
    except FileNotFoundError as e:
        logger.error(f"\n❌ Configuration Error: {e}")
        logger.error("\nTo get started:")
        logger.error("  1. Copy accounts_config.example.yml to accounts_config.yml")
        logger.error("  2. Add your account credentials to accounts_config.yml")
        sys.exit(1)
    
    except ValueError as e:
        logger.error(f"\n❌ Configuration Error: {e}")
        sys.exit(1)
    
    except Exception as e:
        logger.error(f"\n❌ Unexpected Error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
