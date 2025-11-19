"""
Simple BTCUSDT Symbol Info Example

This example demonstrates:
- Quick retrieval of BTCUSDT symbol information
- Display of key trading parameters

No API keys required.
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path to import aster_client
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from aster_client.public_client import AsterPublicClient


async def main():
    """Fetch and display BTCUSDT symbol information."""
    print("🔍 Fetching BTCUSDT Symbol Information...\n")
    
    async with AsterPublicClient() as client:
        # Get symbol info (cache is auto-warmed on initialization)
        btc_info = await client.get_symbol_info("BTCUSDT")
        
        if not btc_info:
            print("❌ Failed to fetch BTCUSDT info")
            return
        
        # Display key information
        print("=" * 60)
        print(f"Symbol: {btc_info.symbol}")
        print("=" * 60)
        
        # Price Information
        if btc_info.price_filter:
            print(f"\n💰 PRICE:")
            print(f"   Tick Size:       ${btc_info.price_filter.tick_size}")
            print(f"   Min Price:       ${btc_info.price_filter.min_price}")
            print(f"   Max Price:       ${btc_info.price_filter.max_price}")
        
        # Quantity Information
        if btc_info.lot_size_filter:
            print(f"\n📊 QUANTITY:")
            print(f"   Step Size:       {btc_info.lot_size_filter.step_size} BTC")
            print(f"   Min Quantity:    {btc_info.lot_size_filter.min_qty} BTC")
            print(f"   Max Quantity:    {btc_info.lot_size_filter.max_qty} BTC")
        
        # Min Notional
        if btc_info.min_notional_filter:
            print(f"\n💵 MINIMUM ORDER:")
            print(f"   Min Notional:    ${btc_info.min_notional_filter.notional}")
        
        # Order Limits
        if btc_info.max_num_orders_filter:
            print(f"\n📝 ORDER LIMITS:")
            print(f"   Max Orders:      {btc_info.max_num_orders_filter.limit}")
        
        if btc_info.max_num_algo_orders_filter:
            print(f"   Max Algo Orders: {btc_info.max_num_algo_orders_filter.limit}")
        
        # Status
        print(f"\n✅ STATUS:")
        print(f"   Trading Status:  {btc_info.status}")
        
        print("\n" + "=" * 60)
        print(f"✨ Total symbols cached: {len(client._symbol_info_cache)}")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
