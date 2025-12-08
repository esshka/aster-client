#!/usr/bin/env python3
"""
Example: Parallel Order Execution with AccountPool

This example demonstrates how to:
1. Load multiple accounts from accounts_config.yml
2. Get account information for all accounts in parallel
3. Place orders across multiple accounts simultaneously (DEMO MODE ONLY)
4. Handle results and errors gracefully
5. Measure performance improvement vs sequential execution

⚠️  IMPORTANT: This example runs in DEMO MODE by default and will NOT place real orders.
    To enable real trading, set ENABLE_REAL_TRADING=True (NOT RECOMMENDED for examples)

Prerequisites:
- Create accounts_config.yml in the project root (see accounts_config.example.yml)
- Install dependencies: poetry install

Usage:
    poetry run python examples/parallel_orders_example.py
"""

import asyncio
import os
import sys
import time
from decimal import Decimal
from pathlib import Path
import yaml
import logging

# Add parent directory to path for local development
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from aster_client import AccountPool, AccountConfig, OrderRequest
from aster_client.public_client import AsterPublicClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ⚠️  SAFETY FLAG - Set to True to enable real trading (NOT RECOMMENDED)
ENABLE_REAL_TRADING = False


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
        if not all(k in acc_data for k in ['id', 'api_key', 'api_secret']):
            raise ValueError(
                f"Invalid account configuration: {acc_data}\n"
                "Each account must have 'id', 'api_key', and 'api_secret'"
            )
        
        accounts.append(AccountConfig(
            id=acc_data['id'],
            api_key=acc_data['api_key'],
            api_secret=acc_data['api_secret'],
            simulation=acc_data.get('simulation', False),
            recv_window=acc_data.get('recv_window', 10000),
        ))
    
    return accounts


async def demonstrate_parallel_account_info(pool: AccountPool):
    """Demonstrate parallel account info retrieval."""
    logger.info("\n" + "=" * 70)
    logger.info("DEMO 1: Parallel Account Info Retrieval")
    logger.info("=" * 70)
    
    start_time = time.time()
    results = await pool.get_accounts_info_parallel()
    duration = time.time() - start_time
    
    logger.info(f"\n✅ Retrieved info for {len(results)} accounts in {duration:.2f}s")
    logger.info(f"   (Average: {duration/len(results):.2f}s per account)\n")
    
    for result in results:
        if result.success:
            info = result.result
            logger.info(f"📊 {result.account_id}:")
            logger.info(f"   Status: {info.status}")
            logger.info(f"   Cash: ${info.cash}")
            logger.info(f"   Buying Power: ${info.buying_power}")
        else:
            logger.error(f"❌ {result.account_id}: {result.error}")


async def demonstrate_parallel_positions(pool: AccountPool):
    """Demonstrate parallel position retrieval."""
    logger.info("\n" + "=" * 70)
    logger.info("DEMO 2: Parallel Position Retrieval")
    logger.info("=" * 70)
    
    results = await pool.get_positions_parallel()
    
    for result in results:
        if result.success:
            positions = result.result
            # Filter out empty positions
            non_empty_positions = [p for p in positions if p.quantity != Decimal("0")]
            logger.info(f"\n📈 {result.account_id}: {len(non_empty_positions)} open position(s)")
            for pos in non_empty_positions:
                logger.info(f"   {pos.symbol}: {pos.quantity} @ ${pos.avg_entry_price}")
        else:
            logger.error(f"❌ {result.account_id}: {result.error}")


async def demonstrate_parallel_order_placement(pool: AccountPool):
    """Demonstrate parallel order placement (DEMO MODE - shows what WOULD happen)."""
    logger.info("\n" + "=" * 70)
    logger.info("DEMO 3: Parallel Order Placement (SIMULATION)")
    logger.info("=" * 70)
    
    # Configuration
    SYMBOL = "BTCUSDT"
    QUANTITY = Decimal("0.001")
    SIDE = "buy"
    PRICE = Decimal("45000.00")  # Example limit price
    
    # Create order request (same for all accounts)
    order = OrderRequest(
        symbol=SYMBOL,
        side=SIDE,
        order_type="limit",
        quantity=QUANTITY,
        price=PRICE,
        time_in_force="gtc",
    )
    
    logger.info(f"\n🎯 DEMO: Would place {SIDE.upper()} orders for {QUANTITY} {SYMBOL} @ ${PRICE}")
    logger.info(f"   Across {pool.account_count} accounts in parallel")
    
    if ENABLE_REAL_TRADING:
        logger.warning("\n⚠️  REAL TRADING ENABLED - Placing actual orders!")
        start_time = time.time()
        results = await pool.place_orders_parallel(order)
        duration = time.time() - start_time
        
        logger.info(f"✅ Order placement completed in {duration:.2f}s")
        logger.info(f"   (Average: {duration/len(results):.2f}s per account)\n")
        
        # Process results
        success_count = 0
        failure_count = 0
        
        for result in results:
            if result.success:
                success_count += 1
                order_response = result.result
                logger.info(f"✅ {result.account_id}:")
                logger.info(f"   Order ID: {order_response.order_id}")
                logger.info(f"   Status: {order_response.status}")
                logger.info(f"   Price: ${order_response.price}")
            else:
                failure_count += 1
                logger.error(f"❌ {result.account_id}: {result.error}")
        
        logger.info(f"\n📊 Summary: {success_count} succeeded, {failure_count} failed")
    else:
        logger.info("\n💡 DEMO MODE: No actual orders placed")
        logger.info("   To enable real trading, set ENABLE_REAL_TRADING=True")
        logger.info(f"\n   Order details that WOULD be placed:")
        logger.info(f"   - Symbol: {order.symbol}")
        logger.info(f"   - Side: {order.side}")
        logger.info(f"   - Type: {order.order_type}")
        logger.info(f"   - Quantity: {order.quantity}")
        logger.info(f"   - Price: ${order.price}")
        logger.info(f"   - Time in Force: {order.time_in_force}")


async def demonstrate_parallel_bbo_orders(pool: AccountPool):
    """Demonstrate parallel BBO order placement (DEMO MODE)."""
    logger.info("\n" + "=" * 70)
    logger.info("DEMO 4: Parallel BBO Order Placement (SIMULATION)")
    logger.info("=" * 70)
    
    SYMBOL = "BTCUSDT"
    QUANTITY = Decimal("0.001")
    SIDE = "buy"
    TICKS_DISTANCE = 2
    
    # Get current market price
    async with AsterPublicClient() as public_client:
        ticker = await public_client.get_ticker(SYMBOL)
        symbol_info = await public_client.get_symbol_info(SYMBOL)
        
        if not ticker or not symbol_info:
            logger.error("Failed to get market data")
            return
        
        market_price = Decimal(str(ticker.get("markPrice", 0)))
        tick_size = symbol_info.tick_size
        if symbol_info.price_filter:
            tick_size = symbol_info.price_filter.tick_size
    
    logger.info(f"\n🎯 DEMO: Would place BBO {SIDE.upper()} orders:")
    logger.info(f"   Symbol: {SYMBOL}")
    logger.info(f"   Quantity: {QUANTITY}")
    logger.info(f"   Market Price: ${market_price}")
    logger.info(f"   Tick Size: {tick_size}")
    logger.info(f"   Ticks Distance: {TICKS_DISTANCE}")
    
    if ENABLE_REAL_TRADING:
        logger.warning("\n⚠️  REAL TRADING ENABLED - Placing actual BBO orders!")
        start_time = time.time()
        results = await pool.place_bbo_orders_parallel(
            symbol=SYMBOL,
            side=SIDE,
            quantity=QUANTITY,
            market_price=market_price,
            tick_size=tick_size,
            ticks_distance=TICKS_DISTANCE,
            time_in_force="gtc",
        )
        duration = time.time() - start_time
        
        logger.info(f"✅ BBO orders placed in {duration:.2f}s\n")
        
        for result in results:
            if result.success:
                order_response = result.result
                logger.info(f"✅ {result.account_id}:")
                logger.info(f"   Order ID: {order_response.order_id}")
                logger.info(f"   BBO Price: ${order_response.price}")
            else:
                logger.error(f"❌ {result.account_id}: {result.error}")
    else:
        logger.info("\n💡 DEMO MODE: No actual orders placed")
        logger.info("   To enable real trading, set ENABLE_REAL_TRADING=True")


async def demonstrate_custom_parallel_execution(pool: AccountPool):
    """Demonstrate custom parallel execution with execute_parallel."""
    logger.info("\n" + "=" * 70)
    logger.info("DEMO 5: Custom Parallel Execution")
    logger.info("=" * 70)
    
    # Define custom async function
    async def get_custom_data(client):
        """Get multiple data points in one function."""
        account_info = await client.get_account_info()
        positions = await client.get_positions()
        balances = await client.get_balances()
        
        # Filter non-empty positions
        non_empty_positions = [p for p in positions if p.quantity != Decimal("0")]
        
        return {
            "status": account_info.status,
            "balance": str(account_info.cash),
            "position_count": len(non_empty_positions),
            "balance_count": len(balances),
        }
    
    logger.info("\n📊 Executing custom data retrieval function...\n")
    
    results = await pool.execute_parallel(get_custom_data)
    
    for result in results:
        if result.success:
            data = result.result
            logger.info(f"✅ {result.account_id}:")
            logger.info(f"   Status: {data['status']}")
            logger.info(f"   Balance: ${data['balance']}")
            logger.info(f"   Open Positions: {data['position_count']}")
            logger.info(f"   Assets: {data['balance_count']}")
        else:
            logger.error(f"❌ {result.account_id}: {result.error}")


async def main():
    """Main function to run all demonstrations."""
    
    # Configuration
    CONFIG_FILE = "accounts_config.yml"
    
    logger.info("=" * 70)
    logger.info("PARALLEL ORDER EXECUTION DEMO")
    logger.info("=" * 70)
    
    if not ENABLE_REAL_TRADING:
        logger.info("\n💡 DEMO MODE: This example will NOT place real orders")
        logger.info("   All order placement demos are simulated")
        logger.info("   Only read-only operations (account info, positions) are executed\n")
    else:
        logger.warning("\n⚠️  WARNING: REAL TRADING MODE ENABLED!")
        logger.warning("   This will place ACTUAL orders on the exchange!")
        logger.warning("   Press Ctrl+C within 5 seconds to cancel...\n")
        await asyncio.sleep(5)
    
    try:
        # Load accounts from config file
        project_root = Path(__file__).parent.parent
        config_path = project_root / CONFIG_FILE
        
        logger.info(f"Loading accounts from: {config_path}")
        accounts = load_accounts_from_config(str(config_path))
        logger.info(f"Loaded {len(accounts)} account(s) from configuration\n")
        
        for acc in accounts:
            logger.info(f"  • {acc.id} (simulation: {acc.simulation})")
        
        # Create AccountPool
        async with AccountPool(accounts) as pool:
            logger.info(f"\n✅ AccountPool initialized with {pool.account_count} accounts\n")
            
            # Run demonstrations
            await demonstrate_parallel_account_info(pool)
            await demonstrate_parallel_positions(pool)
            
            # Order placement demos (DEMO MODE by default)
            await demonstrate_parallel_order_placement(pool)
            await demonstrate_parallel_bbo_orders(pool)
            
            await demonstrate_custom_parallel_execution(pool)
            
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
        logger.error(f"Error: {type(e).__name__}: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
