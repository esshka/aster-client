#!/usr/bin/env python3
"""
Example: Fetch and display comprehensive account information.

This example demonstrates how to:
1. Create an authenticated account client using environment variables
2. Fetch complete account overview (status, buying power, equity)
3. Retrieve and display all open positions with P&L details
4. Show account balances by currency
5. Display recent orders and performance statistics

Prerequisites:
- Set ASTER_API_KEY and ASTER_API_SECRET environment variables
- Install dependencies with Poetry (recommended): poetry install
- OR install aster-client in development mode: pip install -e .

Usage:
    # Method 1: Using Poetry (recommended)
    poetry run python examples/account_info.py

    # Method 2: After pip install -e .
    python examples/account_info.py

Environment Variables:
    ASTER_API_KEY=your_api_key_here
    ASTER_API_SECRET=your_api_secret_here
"""

import asyncio
import os
from dotenv import load_dotenv

load_dotenv()
import logging
from typing import Optional

from aster_client import AsterClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def format_currency(amount: float, currency: str = "USD") -> str:
    """Format amount as currency."""
    if amount is None:
        return "N/A"
    return f"{amount:,.2f} {currency}"


def format_percentage(value: Optional[float]) -> str:
    """Format percentage value."""
    if value is None:
        return "N/A"
    return f"{value:+.2f}%"


def print_section_header(title: str):
    """Print a formatted section header."""
    print("\n" + "=" * 70)
    print(f" {title.upper()} ".center(70, "="))
    print("=" * 70)


def print_account_summary(account_info):
    """Print formatted account summary."""
    print_section_header("Account Overview")

    # Basic account info
    print(f"Account ID:      {account_info.account_id}")
    print(f"Account Type:    {account_info.account_type}")
    print(f"Status:          {account_info.status}")
    print()

    # Financial metrics
    print("Portfolio Summary:")
    print(f"  Portfolio Value:    {format_currency(account_info.portfolio_value)}")
    print(f"  Equity:             {format_currency(account_info.equity)}")
    print(f"  Last Equity:        {format_currency(account_info.last_equity)}")
    print(f"  Cash:               {format_currency(account_info.cash)}")
    print()

    # Buying power
    print("Buying Power:")
    print(f"  Buying Power:       {format_currency(account_info.buying_power)}")
    print(f"  Day Trading BP:     {format_currency(account_info.day_trading_buying_power)}")
    print(f"  Reg T Buying Power: {format_currency(account_info.reg_t_buying_power)}")
    print(f"  Multiplier:         {account_info.multiplier}x")
    print()

    # Margin information
    print("Margin Information:")
    print(f"  Initial Margin:     {format_currency(account_info.initial_margin)}")
    print(f"  Maintenance Margin: {format_currency(account_info.maintenance_margin)}")
    print(f"  Long Market Value:  {format_currency(account_info.long_market_value)}")
    print(f"  Short Market Value: {format_currency(account_info.short_market_value)}")
    print()

    # Fees
    print(f"Accrued Fees:    {format_currency(account_info.accrued_fees)}")


def print_positions(positions):
    """Print formatted positions table."""
    print_section_header(f"Open Positions ({len(positions)} total)")

    if not positions:
        print("No open positions found.")
        return

    # Table header
    print(f"{'Symbol':<12} {'Side':<6} {'Quantity':<12} {'Avg Price':<12} "
          f"{'Current':<12} {'Market Value':<15} {'P&L':<12} {'P&L %':<8}")
    print("-" * 90)

    # Sort positions by market value (absolute)
    sorted_positions = sorted(positions,
                            key=lambda p: abs(p.market_value or 0),
                            reverse=True)

    for position in sorted_positions:
        symbol = position.symbol[:11]  # Truncate if too long
        side = position.side[:5]
        quantity = f"{position.quantity:>8.6f}"
        avg_price = f"{position.avg_entry_price:>8.2f}" if position.avg_entry_price else "N/A"
        current_price = f"{position.current_price:>8.2f}" if position.current_price else "N/A"
        market_value = f"{position.market_value:>13,.2f}" if position.market_value else "N/A"
        unrealized_pl = f"{position.unrealized_pl:>10,.2f}" if position.unrealized_pl else "N/A"
        unrealized_plpc = format_percentage(position.unrealized_plpc)

        print(f"{symbol:<12} {side:<6} {quantity:<12} {avg_price:<12} "
              f"{current_price:<12} {market_value:<15} {unrealized_pl:<12} {unrealized_plpc:<8}")


def print_balances(balances):
    """Print formatted balances by currency."""
    print_section_header("Account Balances")

    if not balances:
        print("No balances found.")
        return

    # Group by currency
    currency_totals = {}
    for balance in balances:
        currency = balance.currency
        if currency not in currency_totals:
            currency_totals[currency] = {
                'cash': 0,
                'tradeable': 0,
                'pending_buy': 0,
                'pending_sell': 0
            }

        currency_totals[currency]['cash'] += balance.cash or 0
        currency_totals[currency]['tradeable'] += balance.tradeable or 0
        currency_totals[currency]['pending_buy'] += balance.pending_buy or 0
        currency_totals[currency]['pending_sell'] += balance.pending_sell or 0

    # Print balances by currency
    for currency, totals in currency_totals.items():
        print(f"{currency} Balances:")
        print(f"  Available Cash:    {format_currency(totals['cash'], currency)}")
        print(f"  Tradeable:         {format_currency(totals['tradeable'], currency)}")
        print(f"  Pending Buys:      {format_currency(totals['pending_buy'], currency)}")
        print(f"  Pending Sells:     {format_currency(totals['pending_sell'], currency)}")
        print()


def print_orders(orders):
    """Print recent orders summary."""
    print_section_header(f"Recent Orders ({len(orders)} total)")

    if not orders:
        print("No orders found.")
        return

    # Show last 10 orders, most recent first
    recent_orders = sorted(orders,
                          key=lambda o: o.timestamp or 0,
                          reverse=True)[:10]

    print(f"{'Order ID':<20} {'Symbol':<12} {'Side':<6} {'Type':<8} "
          f"{'Quantity':<10} {'Price':<10} {'Status':<12} {'Created':<20}")
    print("-" * 100)

    for order in recent_orders:
        order_id = (order.order_id or "")[:18]
        symbol = (order.symbol or "")[:10]
        side = (order.side or "")[:4]
        order_type = (order.order_type or "")[:6]
        quantity = f"{order.quantity:>8.6f}" if order.quantity else "N/A"
        price = f"{order.price:>8.2f}" if order.price else "MARKET"
        status = (order.status or "")[:10]
        created = str(order.timestamp)[:19] if order.timestamp else "N/A"

        print(f"{order_id:<20} {symbol:<12} {side:<6} {order_type:<8} "
              f"{quantity:<10} {price:<10} {status:<12} {created:<20}")


async def main():
    """Main function to fetch and display comprehensive account information."""

    # Safety settings
    SIMULATION_MODE = False  # Set to False for live trading (required for authentication)
    USE_ENV_VARS = True     # Use environment variables for credentials
    SHOW_RECENT_ORDERS = True  # Include recent orders in output

    # Set larger recv window to handle potential clock skew
    os.environ["ASTER_RECV_WINDOW"] = "10000"

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

        logger.info(f"Client created successfully (simulation mode: {SIMULATION_MODE})")

        # Use context manager for automatic resource cleanup
        async with client:
            logger.info("Fetching account information...")

            # Step 1: Get account overview
            account_info = await client.get_account_info()
            print_account_summary(account_info)

            # Step 2: Get positions
            logger.info("Fetching open positions...")
            positions = await client.get_positions()
            print_positions(positions)

            # Step 3: Get balances
            logger.info("Fetching account balances...")
            balances = await client.get_balances()
            print_balances(balances)

            # Step 4: Get recent orders (optional)
            if SHOW_RECENT_ORDERS:
                logger.info("Fetching recent orders...")
                orders = await client.get_orders()
                print_orders(orders)

            # Step 5: Get client statistics
            logger.info("Fetching account statistics...")
            try:
                stats = await client.get_statistics()
                if stats:
                    print_section_header("Account Statistics")
                    # Note: Print based on actual statistics model structure
                    logger.info(f"Statistics received: {type(stats)}")
            except Exception as e:
                logger.warning(f"Could not fetch statistics: {e}")

            print_section_header("Summary Complete")
            logger.info("✅ Account information fetched successfully!")

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