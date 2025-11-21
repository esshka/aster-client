"""
Order Book Depth Example

This example demonstrates:
- Fetching order book depth data for a symbol
- Different depth limits (5, 10, 20, 50, 100, 500, 1000)
- Displaying best bid/ask prices and quantities
- Analyzing spread and liquidity

No API keys required.
"""

import asyncio
import sys
from pathlib import Path
from decimal import Decimal

# Add parent directory to path to import aster_client
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from aster_client.public_client import AsterPublicClient


def format_order_book_level(price: str, quantity: str) -> str:
    """Format a single order book level for display."""
    return f"   Price: ${Decimal(price):>12,.2f}  |  Quantity: {Decimal(quantity):>10,.4f}"


async def display_order_book(symbol: str, limit: int = 5):
    """Fetch and display order book for a symbol."""
    print(f"\n📊 Fetching Order Book for {symbol} (limit={limit})...\n")
    
    async with AsterPublicClient() as client:
        order_book = await client.get_order_book(symbol, limit=limit)
        
        if not order_book:
            print(f"❌ Failed to fetch order book for {symbol}")
            return
        
        bids = order_book.get("bids", [])
        asks = order_book.get("asks", [])
        
        if not bids or not asks:
            print("⚠️  Order book is empty")
            return
        
        # Get best bid and ask
        best_bid_price = Decimal(bids[0][0])
        best_bid_qty = Decimal(bids[0][1])
        best_ask_price = Decimal(asks[0][0])
        best_ask_qty = Decimal(asks[0][1])
        
        # Calculate spread
        spread = best_ask_price - best_bid_price
        spread_pct = (spread / best_bid_price) * 100
        
        # Calculate mid price
        mid_price = (best_bid_price + best_ask_price) / 2
        
        print("=" * 70)
        print(f"📈 {symbol} Order Book")
        print("=" * 70)
        
        # Market overview
        print("\n💡 MARKET OVERVIEW:")
        print(f"   Mid Price:     ${mid_price:,.2f}")
        print(f"   Spread:        ${spread:,.2f} ({spread_pct:.4f}%)")
        print(f"   Last Update:   {order_book.get('lastUpdateId', 'N/A')}")
        
        # Display asks (from highest to lowest, so reverse)
        print(f"\n🔴 TOP {min(limit, len(asks))} ASKS (Sell Orders):")
        print("   " + "-" * 60)
        for ask in reversed(asks[:limit]):
            print(format_order_book_level(ask[0], ask[1]))
        
        # Display best bid/ask highlight
        print("\n   " + "=" * 60)
        print(f"   💰 Best Ask: ${best_ask_price:>12,.2f}  |  {best_ask_qty:>10,.4f}")
        print(f"   💵 Best Bid: ${best_bid_price:>12,.2f}  |  {best_bid_qty:>10,.4f}")
        print("   " + "=" * 60)
        
        # Display bids
        print(f"\n🟢 TOP {min(limit, len(bids))} BIDS (Buy Orders):")
        print("   " + "-" * 60)
        for bid in bids[:limit]:
            print(format_order_book_level(bid[0], bid[1]))
        
        # Calculate total liquidity at each side
        total_bid_qty = sum(Decimal(bid[1]) for bid in bids)
        total_ask_qty = sum(Decimal(ask[1]) for ask in asks)
        total_bid_value = sum(Decimal(bid[0]) * Decimal(bid[1]) for bid in bids)
        total_ask_value = sum(Decimal(ask[0]) * Decimal(ask[1]) for ask in asks)
        
        print(f"\n📊 LIQUIDITY SUMMARY:")
        print(f"   Total Bid Quantity:  {total_bid_qty:,.4f} (${total_bid_value:,.2f})")
        print(f"   Total Ask Quantity:  {total_ask_qty:,.4f} (${total_ask_value:,.2f})")
        
        print("\n" + "=" * 70)


async def compare_depths(symbol: str):
    """Compare different depth limits to show the impact on API weight."""
    print("\n🔬 Comparing Different Depth Limits\n")
    print("=" * 70)
    print("Limit | API Weight | Use Case")
    print("-" * 70)
    print("5     | 2          | Quick price check, minimal data")
    print("10    | 2          | Basic market overview")
    print("20    | 2          | Standard trading view")
    print("50    | 2          | Detailed market depth")
    print("100   | 5          | Deep liquidity analysis")
    print("500   | 10         | Full order book analysis")
    print("1000  | 20         | Complete market microstructure")
    print("=" * 70)
    
    # Demonstrate with different limits
    for limit in [5, 20, 100]:
        await display_order_book(symbol, limit=limit)
        await asyncio.sleep(0.5)  # Small delay between requests


async def main():
    """Main example function."""
    symbol = "BTCUSDT"
    
    print("\n" + "=" * 70)
    print("📚 ORDER BOOK DEPTH EXAMPLE")
    print("=" * 70)
    
    # Example 1: Basic order book with default limit
    await display_order_book(symbol)
    
    # Example 2: Order book with custom limit
    await display_order_book(symbol, limit=20)
    
    # Example 3: Compare different depths
    # Uncomment to see comparison (makes multiple API calls)
    # await compare_depths(symbol)
    
    print("\n✅ Example completed!\n")


if __name__ == "__main__":
    asyncio.run(main())
