#!/usr/bin/env python3
"""
Example: Create account client and place BUY order for BTCUSDT
with limit price.

This example demonstrates how to:
1. Create an authenticated account client using environment variables
2. Place a BUY limit order for BTCUSDT at $80,000
3. Handle responses and errors properly

Prerequisites:
- Set ASTER_API_KEY and ASTER_API_SECRET environment variables
- Install dependencies with Poetry (recommended): poetry install
- OR install aster-client in development mode: pip install -e .

Usage:
    # Method 1: Using Poetry (recommended)
    poetry run python examples/btc_buy_limit_order.py

    # Method 2: After pip install -e .
    python examples/btc_buy_limit_order.py

Environment Variables:
    ASTER_API_KEY=your_api_key_here
    ASTER_API_SECRET=your_api_secret_here
"""

import asyncio
import os
import logging
from decimal import Decimal

from aster_client import AsterClient
from aster_client.models.orders import OrderRequest

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def main():
    """Main function to demonstrate account client creation and
    BUY order placement."""

    # Configuration
    SYMBOL = "BTCUSDT"
    PRICE = Decimal("80000.00")  # Limit price: $80,000
    QUANTITY = Decimal("0.001")   # Quantity: 0.001 BTC

    # Safety settings
    SIMULATION_MODE = True  # Set to False for live trading
    USE_ENV_VARS = True     # Use environment variables for credentials

    try:
        # Method 1: Create client using env variables
        if USE_ENV_VARS:
            logger.info("Creating account client from environment variables...")
            client = AsterClient.from_env(simulation=SIMULATION_MODE)
        else:
            # Method 2: Create client with explicit credentials
            api_key = os.getenv("ASTER_API_KEY", "your_api_key_here")
            api_secret = os.getenv("ASTER_API_SECRET", "your_api_secret_here")
            client = AsterClient.create_aster_client(
                api_key=api_key,
                api_secret=api_secret,
                simulation=SIMULATION_MODE
            )

        msg = f"Client created successfully (simulation mode: {SIMULATION_MODE})"
        logger.info(msg)

        # Use context manager for automatic resource cleanup
        async with client:
            # Step 1: Get account information
            logger.info("Retrieving account information...")
            account_info = await client.get_account_info()
            logger.info(f"Account status: {account_info.status}")
            logger.info(f"Available balance: ${account_info.cash}")
            logger.info(f"Buying power: ${account_info.buying_power}")

            # Step 2: Check current positions
            logger.info("Retrieving current positions...")
            positions = await client.get_positions()
            logger.info(f"Current open positions: {len(positions)}")

            for position in positions:
                if position.symbol == SYMBOL:
                    pos_msg = (f"Current {SYMBOL} position: "
                        f"{position.quantity} @ ${position.avg_entry_price}")
                    logger.info(pos_msg)

            # Step 3: Create BUY limit order
            order_msg = (f"Creating BUY limit order for {QUANTITY} "
                        f"{SYMBOL} at ${PRICE}...")
            logger.info(order_msg)

            buy_order = OrderRequest(
                symbol=SYMBOL,
                side="buy",  # "buy" or "sell"
                order_type="limit",  # "limit", "market", etc.
                quantity=QUANTITY,
                price=PRICE,
                time_in_force="gtc",  # Good Till Cancelled
                client_order_id=f"btc_buy_example_{SYMBOL.lower()}"
            )

            # Step 4: Place the order
            logger.info("Placing BUY order...")
            order_result = await client.place_order(buy_order)

            logger.info("✅ Order placed successfully!")
            logger.info(f"   Order ID: {order_result.order_id}")
            logger.info(f"   Status: {order_result.status}")
            logger.info(f"   Symbol: {order_result.symbol}")
            logger.info(f"   Side: {order_result.side}")
            logger.info(f"   Type: {order_result.order_type}")
            logger.info(f"   Quantity: {order_result.quantity}")
            logger.info(f"   Price: ${order_result.price}")
            logger.info(f"   Filled: {order_result.filled_quantity}")

            # Step 5: Check order status after placement
            logger.info("Checking order status...")
            order_status = await client.get_order(order_result.order_id)

            logger.info("Order status update:")
            if order_status is not None:
                logger.info(f"   Status: {order_status.status}")
                logger.info(f"   Filled: {order_status.filled_quantity}")
                if (order_status.filled_quantity > 0
                        and order_status.average_price is not None):
                    price_msg = (f"   Average fill price: "
                           f"${order_status.average_price}")
                    logger.info(price_msg)

            # Step 6: Monitor order briefly (optional)
            logger.info("Monitoring order for 10 seconds...")
            await asyncio.sleep(10)

            final_status = await client.get_order(order_result.order_id)
            if final_status is not None:
                logger.info(f"Final order status: {final_status.status}")

                if final_status.status == "filled":
                    avg_msg = (f"🎉 Order fully filled! "
                            f"Average price: ${final_status.average_price}")
                    logger.info(avg_msg)
                elif final_status.status == "partially_filled":
                    filled_msg = (f"⚡ Order partially filled: "
                               f"{final_status.filled_quantity} / {final_status.quantity}")
                    logger.info(filled_msg)
                else:
                    logger.info("⏳ Order still open or pending")
            else:
                logger.error("Failed to get final order status")

    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        logger.error("Please check your API credentials and environment variables")

    except Exception as e:
        logger.error(f"Unexpected error: {type(e).__name__}: {e}")
        raise


def print_environment_setup():
    """Print instructions for setting up environment variables."""
    print("=" * 70)
    print("ENVIRONMENT VARIABLES SETUP")
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
        logger.warning("For testing, you can modify USE_ENV_VARS=False in the script.")

    # Run the main async function
    asyncio.run(main())
