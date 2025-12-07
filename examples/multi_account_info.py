#!/usr/bin/env python3
"""
Example: Display account information for multiple accounts.

This example demonstrates how to:
1. Load multiple account credentials from a YAML configuration file
2. Fetch balance and open positions for each account in parallel
3. Display only non-empty positions with their P&L details

Prerequisites:
- Create accounts_config.yml in the project root (see accounts_config.example.yml)
- Install dependencies with Poetry: poetry install

Usage:
    poetry run python examples/multi_account_info.py

Configuration File (accounts_config.yml):
    accounts:
      - id: "main_account"
        api_key: "your_api_key_here"
        api_secret: "your_api_secret_here"
      - id: "secondary_account"
        api_key: "another_api_key"
        api_secret: "another_api_secret"
"""

import asyncio
import os
import sys
from decimal import Decimal
from pathlib import Path
from typing import Optional

import yaml

# Add parent directory to path for local development
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from aster_client import AccountPool, AccountConfig
from aster_client.models.account import Position


def format_currency(amount: Decimal, currency: str = "USDT") -> str:
    """Format amount as currency."""
    if amount is None:
        return "N/A"
    return f"{amount:,.4f} {currency}"


def format_percentage(value: Optional[Decimal]) -> str:
    """Format percentage value."""
    if value is None:
        return "N/A"
    return f"{value:+.2f}%"


def print_header(title: str):
    """Print a formatted header."""
    print("\n" + "=" * 80)
    print(f" {title} ".center(80, "="))
    print("=" * 80)


def print_subheader(title: str):
    """Print a formatted subheader."""
    print(f"\n── {title} " + "─" * (75 - len(title)))


def print_positions(positions: list[Position], account_id: str):
    """Print positions for an account, filtering out empty positions."""
    # Filter out positions with zero quantity
    non_empty_positions = [
        p for p in positions 
        if p.quantity != Decimal("0")
    ]
    
    if not non_empty_positions:
        print(f"  No open positions")
        return
    
    print(f"  Open Positions ({len(non_empty_positions)}):")
    print()
    
    # Table header
    print(f"    {'Symbol':<15} {'Side':<8} {'Quantity':<14} {'Entry':<12} "
          f"{'Notional':<15} {'UnPnL':<14} {'PnL %':<10}")
    print("    " + "-" * 90)
    
    # Sort by absolute notional value
    sorted_positions = sorted(
        non_empty_positions,
        key=lambda p: abs(p.market_value or Decimal("0")),
        reverse=True
    )
    
    for pos in sorted_positions:
        symbol = pos.symbol[:14]
        # Determine side from quantity sign (positive = LONG, negative = SHORT)
        if pos.quantity > 0:
            side = "LONG"
        elif pos.quantity < 0:
            side = "SHORT"
        else:
            side = pos.side[:7] if pos.side else "N/A"
        
        quantity = f"{abs(pos.quantity):>12.6f}"
        entry = f"{pos.avg_entry_price:>10.4f}" if pos.avg_entry_price else "N/A"
        notional = f"{abs(pos.market_value):>13,.2f}" if pos.market_value else "N/A"
        unrealized_pl = f"{pos.unrealized_pl:>+12.4f}" if pos.unrealized_pl else "N/A"
        pnl_pct = format_percentage(pos.unrealized_plpc * 100) if pos.unrealized_plpc else "N/A"
        
        print(f"    {symbol:<15} {side:<8} {quantity:<14} {entry:<12} "
              f"{notional:<15} {unrealized_pl:<14} {pnl_pct:<10}")


def load_accounts_config(config_path: str) -> list[AccountConfig]:
    """
    Load account configurations from YAML file.
    
    Args:
        config_path: Path to the YAML configuration file
        
    Returns:
        List of AccountConfig objects
        
    Raises:
        FileNotFoundError: If config file doesn't exist
        ValueError: If config file is invalid
    """
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


async def main():
    """Main function to fetch and display account information for multiple accounts."""
    
    # Configuration
    CONFIG_FILE = "accounts_config.yml"  # Located in project root
    
    # Set larger recv window to handle potential clock skew
    os.environ["ASTER_RECV_WINDOW"] = "10000"
    
    print_header("Multi-Account Information")
    
    try:
        # Load accounts from config file
        project_root = Path(__file__).parent.parent
        config_path = project_root / CONFIG_FILE
        
        print(f"Loading accounts from: {config_path}")
        accounts = load_accounts_config(str(config_path))
        print(f"Found {len(accounts)} account(s) in configuration")
        
        # Create account pool and fetch data
        async with AccountPool(accounts) as pool:
            print("\nFetching account data in parallel...")
            
            # Get balances for all accounts
            balance_results = await pool.get_balances_parallel()
            
            # Get positions for all accounts
            position_results = await pool.get_positions_parallel()
            
            # Display results for each account
            for i, (balance_result, position_result) in enumerate(
                zip(balance_results, position_results)
            ):
                account_id = balance_result.account_id
                
                print_subheader(f"Account: {account_id}")
                
                # Display balance
                if balance_result.success and balance_result.result:
                    balances = balance_result.result
                    # Find USDT balance (most common for futures)
                    usdt_balance = None
                    for bal in balances:
                        if hasattr(bal, 'currency') and bal.currency == 'USDT':
                            usdt_balance = bal
                            break
                        elif hasattr(bal, 'asset') and bal.asset == 'USDT':
                            usdt_balance = bal
                            break
                    
                    if usdt_balance:
                        if hasattr(usdt_balance, 'available_balance'):
                            # V2 balance format
                            print(f"  Balance: {format_currency(usdt_balance.balance)}")
                            print(f"  Available: {format_currency(usdt_balance.available_balance)}")
                            print(f"  Cross Wallet: {format_currency(usdt_balance.cross_wallet_balance)}")
                            print(f"  Unrealized PnL: {format_currency(usdt_balance.cross_un_pnl)}")
                        else:
                            # V1 balance format
                            print(f"  Cash: {format_currency(usdt_balance.cash)}")
                            print(f"  Tradeable: {format_currency(usdt_balance.tradeable)}")
                    else:
                        print(f"  Balances: {len(balances)} asset(s) found")
                        for bal in balances[:3]:  # Show first 3
                            if hasattr(bal, 'available_balance'):
                                print(f"    {bal.asset}: {format_currency(bal.available_balance, bal.asset)}")
                            elif hasattr(bal, 'currency'):
                                print(f"    {bal.currency}: {format_currency(bal.cash, bal.currency)}")
                else:
                    error = balance_result.error if hasattr(balance_result, 'error') else "Unknown error"
                    print(f"  ❌ Failed to fetch balance: {error}")
                
                print()  # Empty line before positions
                
                # Display positions
                if position_result.success and position_result.result is not None:
                    print_positions(position_result.result, account_id)
                else:
                    error = position_result.error if hasattr(position_result, 'error') else "Unknown error"
                    print(f"  ❌ Failed to fetch positions: {error}")
        
        print_header("Summary Complete")
        print(f"✅ Processed {len(accounts)} account(s)")
        
    except FileNotFoundError as e:
        print(f"\n❌ Configuration Error: {e}")
        print("\nTo get started:")
        print("  1. Copy accounts_config.example.yml to accounts_config.yml")
        print("  2. Add your account credentials to accounts_config.yml")
        sys.exit(1)
        
    except ValueError as e:
        print(f"\n❌ Configuration Error: {e}")
        sys.exit(1)
        
    except Exception as e:
        print(f"\n❌ Unexpected Error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
