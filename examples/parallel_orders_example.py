#!/usr/bin/env python3
"""
Example: Parallel Order Execution with AccountPool

This example demonstrates how to:
1. Create an AccountPool with multiple accounts
2. Get account information for all accounts in parallel
3. Place orders across multiple accounts simultaneously
4. Handle results and errors gracefully
5. Measure performance improvement vs sequential execution

Prerequisites:
- Set environment variables for multiple accounts:
  ACCOUNT_1_API_KEY, ACCOUNT_1_API_SECRET
  ACCOUNT_2_API_KEY, ACCOUNT_2_API_SECRET
  etc.
- Install dependencies: poetry install

Usage:
    poetry run python examples/parallel_orders_example.py
"""

import asyncio
import os
import time
from decimal import Decimal
from dotenv import load_dotenv
import logging

load_dotenv()

from aster_client import AccountPool, AccountConfig, OrderRequest
from aster_client.public_client import AsterPublicClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_accounts_from_env() -> list[AccountConfig]:
    """Load account configurations from environment variables."""
    accounts = []
    i = 1
    
    while True:
        api_key = os.getenv(f"ACCOUNT_{i}_API_KEY")
        api_secret = os.getenv(f"ACCOUNT_{i}_API_SECRET")
        
        if not api_key or not api_secret:
            break
        
        accounts.append(
            AccountConfig(
                id=f"account_{i}",
                api_key=api_key,
                api_secret=api_secret,
                simulation=os.getenv(f"ACCOUNT_{i}_SIMULATION", "false").lower() == "true"
            )
        )
        i += 1
    
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
            logger.info(f"   Balance: ${info.cash}")
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
            logger.info(f"\n📈 {result.account_id}: {len(positions)} position(s)")
            for pos in positions:
                logger.info(f"   {pos.symbol}: {pos.position_amount} @ ${pos.entry_price}")
        else:
            logger.error(f"❌ {result.account_id}: {result.error}")


async def demonstrate_parallel_order_placement(pool: AccountPool):
    """Demonstrate parallel order placement."""
    logger.info("\n" + "=" * 70)
    logger.info("DEMO 3: Parallel Order Placement")
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
    
    logger.info(f"\n🎯 Placing {SIDE.upper()} orders for {QUANTITY} {SYMBOL} @ ${PRICE}")
    logger.info(f"   Executing across {pool.account_count} accounts in parallel...\n")
    
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


async def demonstrate_parallel_bbo_orders(pool: AccountPool):
    """Demonstrate parallel BBO order placement."""
    logger.info("\n" + "=" * 70)
    logger.info("DEMO 4: Parallel BBO Order Placement")
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
    
    logger.info(f"\n🎯 Placing BBO {SIDE.upper()} orders:")
    logger.info(f"   Symbol: {SYMBOL}")
    logger.info(f"   Quantity: {QUANTITY}")
    logger.info(f"   Market Price: ${market_price}")
    logger.info(f"   Tick Size: {tick_size}")
    logger.info(f"   Ticks Distance: {TICKS_DISTANCE}\n")
    
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
        
        return {
            "status": account_info.status,
            "balance": str(account_info.cash),
            "position_count": len(positions),
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
            logger.info(f"   Positions: {data['position_count']}")
            logger.info(f"   Assets: {data['balance_count']}")
        else:
            logger.error(f"❌ {result.account_id}: {result.error}")


async def main():
    """Main function to run all demonstrations."""
    
    # Load accounts from environment
    accounts = load_accounts_from_env()
    
    if not accounts:
        logger.error("No accounts found in environment variables!")
        logger.error("Please set ACCOUNT_1_API_KEY, ACCOUNT_1_API_SECRET, etc.")
        print_setup_instructions()
        return
    
    logger.info("=" * 70)
    logger.info("PARALLEL ORDER EXECUTION DEMO")
    logger.info("=" * 70)
    logger.info(f"Loaded {len(accounts)} account(s) from environment\n")
    
    for acc in accounts:
        logger.info(f"  • {acc.id} (simulation: {acc.simulation})")
    
    try:
        # Create AccountPool
        async with AccountPool(accounts) as pool:
            logger.info(f"\n✅ AccountPool initialized with {pool.account_count} accounts\n")
            
            # Run demonstrations
            await demonstrate_parallel_account_info(pool)
            await demonstrate_parallel_positions(pool)
            
            # Uncomment to test actual order placement:
            # WARNING: This will place real orders if not in simulation mode!
            # await demonstrate_parallel_order_placement(pool)
            # await demonstrate_parallel_bbo_orders(pool)
            
            await demonstrate_custom_parallel_execution(pool)
            
    except Exception as e:
        logger.error(f"Error: {type(e).__name__}: {e}")
        raise


def print_setup_instructions():
    """Print setup instructions for environment variables."""
    print("\n" + "=" * 70)
    print("SETUP INSTRUCTIONS")
    print("=" * 70)
    print("Set environment variables for your accounts:\n")
    print("# Account 1")
    print("export ACCOUNT_1_API_KEY=your_api_key_here")
    print("export ACCOUNT_1_API_SECRET=your_api_secret_here")
    print("export ACCOUNT_1_SIMULATION=true  # Optional, default: false\n")
    print("# Account 2")
    print("export ACCOUNT_2_API_KEY=your_api_key_here")
    print("export ACCOUNT_2_API_SECRET=your_api_secret_here\n")
    print("# Account 3, 4, etc...")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
