#!/usr/bin/env python3
"""
Example: Place BBO (Best Bid Offer) Orders

This example demonstrates how to:
1. Create an authenticated account client using environment variables
2. Get current mark price for a symbol
3. Get symbol information including tick size
4. Calculate BBO prices for buy and sell orders
5. Place a BBO order with automatic price calculation

BBO orders are placed one tick away from best bid/ask to maximize
the chance of maker fee execution while getting optimal pricing:
- BUY orders: best_bid + tick_size
- SELL orders: best_ask - tick_size

Prerequisites:
- Set ASTER_API_KEY and ASTER_API_SECRET environment variables
- Install dependencies with Poetry (recommended): poetry install
- OR install aster-client in development mode: pip install -e .

Usage:
    # Method 1: Using Poetry (recommended)
    poetry run python examples/bbo_order_example.py

    # Method 2: After pip install -e .
    python examples/bbo_order_example.py

Environment Variables:
    ASTER_API_KEY=your_api_key_here
    ASTER_API_SECRET=your_api_secret_here
"""

import asyncio
import os
from dotenv import load_dotenv

load_dotenv()
import logging
from decimal import Decimal

from aster_client import AsterClient
from aster_client.public_client import AsterPublicClient
from aster_client.bbo import calculate_bbo_price

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def main():
    """Main function to demonstrate BBO order placement."""

    # Configuration
    SYMBOL = "BTCUSDT"
    QUANTITY = Decimal("0.001")  # 0.001 BTC
    SIDE = "buy"  # "buy" or "sell"
    TICKS_DISTANCE = 1  # Number of ticks away from market price (default: 1)
    # TICKS_DISTANCE = 2 would place order 2 ticks away from market
    # TICKS_DISTANCE = 5 would place order 5 ticks away from market

    # Safety settings
    SIMULATION_MODE = False  # Set to False for live trading
    USE_ENV_VARS = True      # Use environment variables for credentials

    try:
        # Create public client to get market data
        logger.info("Initializing public client for market data...")
        public_client = AsterPublicClient()

        # Create authenticated client
        if USE_ENV_VARS:
            logger.info("Creating account client from environment variables...")
            client = AsterClient.from_env(simulation=SIMULATION_MODE)
        else:
            logger.error("Please set USE_ENV_VARS=True and configure environment variables")
            return

        async with public_client, client:
            # Step 1: Get order book for best bid/ask
            logger.info(f"Getting order book for {SYMBOL}...")
            order_book = await public_client.get_order_book(SYMBOL, limit=5)
            
            if not order_book or "bids" not in order_book or "asks" not in order_book:
                logger.error(f"Failed to get order book for {SYMBOL}")
                return

            try:
                best_bid = Decimal(order_book["bids"][0][0])
                best_ask = Decimal(order_book["asks"][0][0])
                logger.info(f"📊 Current market: Bid=${best_bid}, Ask=${best_ask}")
            except (IndexError, ValueError) as e:
                logger.error(f"Failed to parse order book: {e}")
                return

            # Step 2: Get symbol info for tick size
            logger.info(f"Getting symbol information for {SYMBOL}...")
            symbol_info = await public_client.get_symbol_info(SYMBOL)
            
            if not symbol_info:
                logger.error(f"Failed to get symbol info for {SYMBOL}")
                return

            # Extract tick size from symbol info
            tick_size = symbol_info.tick_size
            if symbol_info.price_filter:
                tick_size = symbol_info.price_filter.tick_size

            logger.info(f"📏 Tick size for {SYMBOL}: {tick_size}")

            # Step 3: Calculate BBO prices for demonstration
            logger.info("\n" + "=" * 60)
            logger.info("BBO Price Calculations:")
            logger.info("=" * 60)

            buy_bbo_price = calculate_bbo_price(
                SYMBOL, "buy", best_bid, best_ask, tick_size, TICKS_DISTANCE
            )
            sell_bbo_price = calculate_bbo_price(
                SYMBOL, "sell", best_bid, best_ask, tick_size, TICKS_DISTANCE
            )

            price_adjustment = tick_size * TICKS_DISTANCE
            logger.info(
                f"BUY BBO Price:  ${buy_bbo_price} (bid + {TICKS_DISTANCE} tick{'s' if TICKS_DISTANCE > 1 else ''} = +${price_adjustment})"
            )
            logger.info(
                f"SELL BBO Price: ${sell_bbo_price} (ask - {TICKS_DISTANCE} tick{'s' if TICKS_DISTANCE > 1 else ''} = -${price_adjustment})"
            )
            logger.info("=" * 60)

            # Step 4: Get account information
            logger.info("\nRetrieving account information...")
            account_info = await client.get_account_info()
            logger.info(f"Account status: {account_info.status}")
            logger.info(f"Available balance: ${account_info.cash}")
            logger.info(f"Buying power: ${account_info.buying_power}")

            # Step 5: Place BBO order
            distance_info = f" ({TICKS_DISTANCE} tick{'s' if TICKS_DISTANCE > 1 else ''} away)" if TICKS_DISTANCE > 1 else ""
            logger.info(f"\n🎯 Placing BBO {SIDE.upper()} order for {QUANTITY} {SYMBOL}{distance_info}...")
            
            order_result = await client.place_bbo_order(
                symbol=SYMBOL,
                side=SIDE,
                quantity=QUANTITY,
                best_bid=best_bid,
                best_ask=best_ask,
                tick_size=tick_size,
                ticks_distance=TICKS_DISTANCE,
                time_in_force="gtc",
                client_order_id=f"bbo_{SIDE}_{SYMBOL.lower()}",
                position_side="LONG" if SIDE == "buy" else "SHORT"
            )

            logger.info("\n✅ BBO Order placed successfully!")
            logger.info("=" * 60)
            logger.info(f"   Order ID: {order_result.order_id}")
            logger.info(f"   Status: {order_result.status}")
            logger.info(f"   Symbol: {order_result.symbol}")
            logger.info(f"   Side: {order_result.side}")
            logger.info(f"   Type: {order_result.order_type}")
            logger.info(f"   Quantity: {order_result.quantity}")
            logger.info(f"   BBO Price: ${order_result.price}")
            
            if SIDE == "buy":
                logger.info(f"   Best Bid: ${best_bid}")
                price_diff = order_result.price - best_bid
                logger.info(f"   Price Improvement: +${price_diff} (vs Best Bid)")
            else:
                logger.info(f"   Best Ask: ${best_ask}")
                price_diff = best_ask - order_result.price
                logger.info(f"   Price Improvement: +${price_diff} (vs Best Ask)")
            
            logger.info("=" * 60)

            # Step 6: Check order status
            logger.info("\nWaiting 5 seconds before checking order status...")
            await asyncio.sleep(5)

            order_status = await client.get_order(
                symbol=SYMBOL,
                order_id=int(order_result.order_id)
            )

            if order_status:
                logger.info(f"\n📋 Order Status Update:")
                logger.info(f"   Status: {order_status.status}")
                logger.info(f"   Filled: {order_status.filled_quantity}")
                
                if order_status.filled_quantity > 0 and order_status.average_price:
                    logger.info(f"   Average fill price: ${order_status.average_price}")

    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        logger.error("Please check your API credentials and environment variables")

    except Exception as e:
        error_msg = str(e)
        
        # Check for specific error codes
        if "-2019" in error_msg and "Margin is insufficient" in error_msg:
            logger.error(f"❌ Insufficient margin to place order")
            logger.error(f"   💡 Solution: Either reduce QUANTITY, or add more funds")
        elif "-4061" in error_msg:
            logger.error(f"❌ Position side mismatch error: {error_msg}")
            logger.error(f"   Your account may be in Hedge Mode. Check position_side setting.")
        else:
            logger.error(f"Unexpected error: {type(e).__name__}: {e}")
            raise


def print_environment_setup():
    """Print instructions for setting up environment variables."""
    print("=" * 70)
    print("BBO ORDER EXAMPLE - ENVIRONMENT SETUP")
    print("=" * 70)
    print("Before running this example, set the following environment variables:")
    print()
    print("# Export in your terminal (Linux/Mac):")
    print("export ASTER_API_KEY=your_actual_api_key_here")
    print("export ASTER_API_SECRET=your_actual_api_secret_here")
    print()
    print("# Or set in PowerShell (Windows):")
    print("$env:ASTER_API_KEY='your_actual_api_key_here'")
    print("$env:ASTER_API_SECRET='your_actual_api_secret_here'")
    print()
    print("# Or create a .env file:")
    print("ASTER_API_KEY=your_actual_api_key_here")
    print("ASTER_API_SECRET=your_actual_api_secret_here")
    print()
    print("⚠️  WARNING: Never commit your API keys to version control!")
    print("=" * 70)
    print()


if __name__ == "__main__":
    # Print environment setup instructions
    print_environment_setup()

    # Check if environment variables are set
    if not os.getenv("ASTER_API_KEY") or not os.getenv("ASTER_API_SECRET"):
        logger.warning("⚠️  Environment variables ASTER_API_KEY and/or "
                    "ASTER_API_SECRET not set!")
        logger.warning("See setup instructions above.")

    # Run the main async function
    asyncio.run(main())
