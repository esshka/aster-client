"""
Symbol Info Example - Demonstrates cache warmup and symbol information retrieval.

This example demonstrates how to:
1. Use the AsterPublicClient with cache warmup
2. Fetch and display comprehensive symbol information for BTCUSDT
3. Access various filters and trading parameters
4. Compare performance with and without cache warmup

Prerequisites:
- No API keys required (public endpoint only)
- Internet connection to access the Aster exchange API
"""

import asyncio
import logging
import time
import sys
from pathlib import Path

# Add parent directory to path to import aster_client
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from aster_client.public_client import AsterPublicClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def display_symbol_info(symbol_info):
    """Display comprehensive symbol information in a formatted way."""
    print("\n" + "=" * 70)
    print(f"📊 SYMBOL INFORMATION: {symbol_info.symbol}")
    print("=" * 70)
    
    # Basic Information
    print(f"\n🔸 BASIC INFO:")
    print(f"   Symbol:              {symbol_info.symbol}")
    print(f"   Base Asset:          {symbol_info.base_asset}")
    print(f"   Quote Asset:         {symbol_info.quote_asset}")
    print(f"   Status:              {symbol_info.status}")
    print(f"   Contract Type:       {symbol_info.contract_type or 'N/A'}")
    
    # Precision
    print(f"\n🔸 PRECISION:")
    print(f"   Price Precision:     {symbol_info.price_precision}")
    print(f"   Quantity Precision:  {symbol_info.quantity_precision}")
    
    # Price Filter
    if symbol_info.price_filter:
        print(f"\n🔸 PRICE FILTER:")
        print(f"   Min Price:           {symbol_info.price_filter.min_price}")
        print(f"   Max Price:           {symbol_info.price_filter.max_price}")
        print(f"   Tick Size:           {symbol_info.price_filter.tick_size}")
    
    # Lot Size Filter
    if symbol_info.lot_size_filter:
        print(f"\n🔸 LOT SIZE FILTER:")
        print(f"   Min Quantity:        {symbol_info.lot_size_filter.min_qty}")
        print(f"   Max Quantity:        {symbol_info.lot_size_filter.max_qty}")
        print(f"   Step Size:           {symbol_info.lot_size_filter.step_size}")
    
    # Market Lot Size Filter
    if symbol_info.market_lot_size_filter:
        print(f"\n🔸 MARKET LOT SIZE FILTER:")
        print(f"   Min Quantity:        {symbol_info.market_lot_size_filter.min_qty}")
        print(f"   Max Quantity:        {symbol_info.market_lot_size_filter.max_qty}")
        print(f"   Step Size:           {symbol_info.market_lot_size_filter.step_size}")
    
    # Min Notional Filter
    if symbol_info.min_notional_filter:
        print(f"\n🔸 MIN NOTIONAL FILTER:")
        print(f"   Notional:            {symbol_info.min_notional_filter.notional}")
    
    # Percent Price Filter
    if symbol_info.percent_price_filter:
        print(f"\n🔸 PERCENT PRICE FILTER:")
        print(f"   Multiplier Up:       {symbol_info.percent_price_filter.multiplier_up}")
        print(f"   Multiplier Down:     {symbol_info.percent_price_filter.multiplier_down}")
        print(f"   Multiplier Decimal:  {symbol_info.percent_price_filter.multiplier_decimal}")
    
    # Max Orders Filters
    if symbol_info.max_num_orders_filter:
        print(f"\n🔸 MAX NUM ORDERS FILTER:")
        print(f"   Limit:               {symbol_info.max_num_orders_filter.limit}")
    
    if symbol_info.max_num_algo_orders_filter:
        print(f"\n🔸 MAX NUM ALGO ORDERS FILTER:")
        print(f"   Limit:               {symbol_info.max_num_algo_orders_filter.limit}")
    
    # Legacy fields (for backward compatibility)
    print(f"\n🔸 LEGACY FIELDS:")
    print(f"   Min Quantity:        {symbol_info.min_quantity}")
    print(f"   Max Quantity:        {symbol_info.max_quantity}")
    print(f"   Min Notional:        {symbol_info.min_notional}")
    print(f"   Max Notional:        {symbol_info.max_notional}")
    print(f"   Tick Size:           {symbol_info.tick_size}")
    print(f"   Step Size:           {symbol_info.step_size}")
    
    print("\n" + "=" * 70)


async def example_with_auto_warmup():
    """
    Example 1: Using auto_warmup (default behavior)
    
    When using the client as a context manager with auto_warmup=True (default),
    all symbol information is preloaded on initialization.
    """
    logger.info("🚀 Example 1: Auto Warmup (Default Behavior)")
    logger.info("=" * 70)
    
    start_time = time.time()
    
    async with AsterPublicClient() as client:
        warmup_time = time.time() - start_time
        cached_count = len(client._symbol_info_cache)
        logger.info(f"✅ Cache warmed up with {cached_count} symbols in {warmup_time:.2f}s")
        
        # Fetch BTCUSDT info (should be instant from cache)
        fetch_start = time.time()
        btc_info = await client.get_symbol_info("BTCUSDT")
        fetch_time = time.time() - fetch_start
        
        if btc_info:
            logger.info(f"⚡ Fetched BTCUSDT info from cache in {fetch_time*1000:.2f}ms")
            display_symbol_info(btc_info)
        else:
            logger.error("Failed to get BTCUSDT info")


async def example_without_auto_warmup():
    """
    Example 2: Without auto_warmup
    
    When auto_warmup is disabled, symbol info is fetched on-demand.
    """
    logger.info("\n\n🚀 Example 2: No Auto Warmup (On-Demand Fetching)")
    logger.info("=" * 70)
    
    async with AsterPublicClient(auto_warmup=False) as client:
        cached_count = len(client._symbol_info_cache)
        logger.info(f"Cache size: {cached_count} symbols (empty)")
        
        # First fetch (will hit the API)
        logger.info("\n📡 First fetch (will hit API)...")
        fetch_start = time.time()
        btc_info = await client.get_symbol_info("BTCUSDT")
        fetch_time = time.time() - fetch_start
        
        if btc_info:
            logger.info(f"⏱️  Fetched BTCUSDT info from API in {fetch_time*1000:.2f}ms")
        
        # Second fetch (should be from cache)
        logger.info("\n📡 Second fetch (should be from cache)...")
        fetch_start = time.time()
        btc_info = await client.get_symbol_info("BTCUSDT")
        fetch_time = time.time() - fetch_start
        
        if btc_info:
            logger.info(f"⚡ Fetched BTCUSDT info from cache in {fetch_time*1000:.2f}ms")


async def example_manual_warmup():
    """
    Example 3: Manual cache warmup
    
    You can manually control when to warmup the cache.
    """
    logger.info("\n\n🚀 Example 3: Manual Cache Warmup")
    logger.info("=" * 70)
    
    async with AsterPublicClient(auto_warmup=False) as client:
        logger.info("Client initialized without auto warmup")
        
        # Manually warmup when you're ready
        logger.info("🔄 Manually warming up cache...")
        warmup_start = time.time()
        cached_count = await client.warmup_cache()
        warmup_time = time.time() - warmup_start
        
        logger.info(f"✅ Manually warmed up {cached_count} symbols in {warmup_time:.2f}s")
        
        # Now fetch is instant
        fetch_start = time.time()
        btc_info = await client.get_symbol_info("BTCUSDT")
        fetch_time = time.time() - fetch_start
        
        if btc_info:
            logger.info(f"⚡ Fetched BTCUSDT info from cache in {fetch_time*1000:.2f}ms")


async def main():
    """Run all examples."""
    logger.info("\n" + "🔷" * 35)
    logger.info("       SYMBOL INFO & CACHE WARMUP EXAMPLES")
    logger.info("🔷" * 35 + "\n")
    
    # Run all examples
    await example_with_auto_warmup()
    await example_without_auto_warmup()
    await example_manual_warmup()
    
    logger.info("\n\n✨ All examples completed successfully!")


if __name__ == "__main__":
    asyncio.run(main())
