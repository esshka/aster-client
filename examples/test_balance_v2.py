#!/usr/bin/env python3
"""
Test script for Futures Account Balance V2 endpoint.

This script demonstrates how to use the new get_balances_v2 method.
"""

import asyncio
import os
from dotenv import load_dotenv

from aster_client.account_client import AsterClient


async def main():
    """Test the get_balances_v2 method."""
    # Load environment variables
    load_dotenv()
    
    # Set larger recv window to handle potential clock skew
    os.environ["ASTER_RECV_WINDOW"] = "10000"
    
    # Create client (simulation=False required for authenticated endpoints)
    client = AsterClient.from_env(simulation=False)
    
    try:
        print("=" * 80)
        print("Futures Account Balance V2 Test")
        print("=" * 80)
        print()
        
        # Get balances using V2 endpoint
        balances = await client.get_balances_v2()
        
        print(f"Found {len(balances)} balance(s):")
        print()
        
        for balance in balances:
            print(f"Account Alias: {balance.account_alias}")
            print(f"Asset: {balance.asset}")
            print(f"Balance: {balance.balance}")
            print(f"Cross Wallet Balance: {balance.cross_wallet_balance}")
            print(f"Cross UnPnl: {balance.cross_un_pnl}")
            print(f"Available Balance: {balance.available_balance}")
            print(f"Max Withdraw Amount: {balance.max_withdraw_amount}")
            print(f"Margin Available: {balance.margin_available}")
            print(f"Update Time: {balance.update_time}")
            print("-" * 80)
        
        # Test with custom recv_window
        print("\nTesting with custom recv_window (10000ms):")
        balances_custom = await client.get_balances_v2(recv_window=10000)
        print(f"Found {len(balances_custom)} balance(s) with custom recv_window")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
