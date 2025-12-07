#!/usr/bin/env python3
"""
Example: Parallel Trades Execution with AccountPool

This example demonstrates how to:
1. Load multiple accounts from accounts_config.yml
2. Execute complete trades (entry + TP/SL) across accounts in parallel
3. Handle individual account results and errors
4. Display aggregated results

⚠️  IMPORTANT: This example runs in DEMO MODE by default and will NOT execute real trades.
    To enable real trading, set ENABLE_REAL_TRADING=True (NOT RECOMMENDED for examples)

Prerequisites:
- Create accounts_config.yml in the project root (see accounts_config.example.yml)
- Each account should have sufficient balance for trading
- Install dependencies: poetry install

Usage:
    poetry run python examples/parallel_trades_example.py
"""

import asyncio
import logging
import sys
from decimal import Decimal
from pathlib import Path
from typing import List
import yaml

# Add parent directory to path for local development
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from aster_client import AccountPool, AccountConfig, Trade, create_trade
from aster_client.public_client import AsterPublicClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
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


async def create_trade_for_account(
    account_id: str,
    client,
    symbol: str,
    side: str,
    quantity: Decimal,
    market_price: Decimal,
    tick_size: Decimal,
    tp_percent: float,
    sl_percent: float,
) -> tuple[str, Trade]:
    """Create a trade for a single account."""
    logger.info(f"🔄 [{account_id}] Starting trade creation...")
    
    trade = await create_trade(
        client=client,
        symbol=symbol,
        side=side,
        quantity=quantity,
        market_price=market_price,
        tick_size=tick_size,
        tp_percent=tp_percent,
        sl_percent=sl_percent,
        fill_timeout=30.0,
        poll_interval=2.0,
    )
    
    return account_id, trade


async def simulate_trade_creation(
    account_id: str,
    symbol: str,
    side: str,
    quantity: Decimal,
    market_price: Decimal,
    tp_percent: float,
    sl_percent: float,
) -> tuple[str, dict]:
    """Simulate trade creation without actual API calls (DEMO MODE)."""
    logger.info(f"🔄 [{account_id}] DEMO: Simulating trade creation...")
    
    # Calculate TP and SL prices
    if side == "buy":
        tp_price = market_price * (Decimal("1") + Decimal(str(tp_percent / 100)))
        sl_price = market_price * (Decimal("1") - Decimal(str(sl_percent / 100)))
    else:  # sell
        tp_price = market_price * (Decimal("1") - Decimal(str(tp_percent / 100)))
        sl_price = market_price * (Decimal("1") + Decimal(str(sl_percent / 100)))
    
    # Simulate processing time
    await asyncio.sleep(0.5)
    
    trade_info = {
        "account_id": account_id,
        "symbol": symbol,
        "side": side,
        "quantity": str(quantity),
        "entry_price": str(market_price),
        "tp_price": str(tp_price),
        "sl_price": str(sl_price),
        "status": "simulated",
    }
    
    logger.info(f"✅ [{account_id}] DEMO: Trade simulation complete")
    
    return account_id, trade_info


async def main():
    """Main example function."""
    # Configuration
    CONFIG_FILE = "accounts_config.yml"
    symbol = "ETHUSDT"
    side = "buy"
    usdt_amount = 10.0
    tp_percent = 1.0
    sl_percent = 0.5
    
    logger.info("=" * 70)
    logger.info("PARALLEL TRADES EXAMPLE")
    logger.info("=" * 70)
    logger.info(f"   Symbol: {symbol}")
    logger.info(f"   Side: {side.upper()}")
    logger.info(f"   Amount per account: ${usdt_amount} USDT")
    logger.info(f"   TP: +{tp_percent}%, SL: -{sl_percent}%")
    
    if not ENABLE_REAL_TRADING:
        logger.info("\n💡 DEMO MODE: This example will NOT execute real trades")
        logger.info("   All trade operations are simulated")
        logger.info("   Only market data fetching is real\n")
    else:
        logger.warning("\n⚠️  WARNING: REAL TRADING MODE ENABLED!")
        logger.warning("   This will execute ACTUAL trades on the exchange!")
        logger.warning("   Press Ctrl+C within 5 seconds to cancel...\n")
        await asyncio.sleep(5)
    
    try:
        # Load accounts from config
        project_root = Path(__file__).parent.parent
        config_path = project_root / CONFIG_FILE
        
        logger.info(f"Loading accounts from: {config_path}")
        accounts = load_accounts_from_config(str(config_path))
        logger.info(f"Found {len(accounts)} account(s) in configuration\n")
        
        for acc in accounts:
            logger.info(f"  • {acc.id} (simulation: {acc.simulation})")
        
        # Get market data using public client
        async with AsterPublicClient() as public_client:
            logger.info("\n📊 Fetching market data...")
            ticker = await public_client.get_ticker(symbol)
            if not ticker or not ticker.markPrice:
                logger.error(f"Failed to get ticker for {symbol}")
                return
            
            market_price = Decimal(str(ticker.markPrice))
            logger.info(f"   Current price: ${market_price}")
            
            symbol_info = await public_client.get_symbol_info(symbol)
            if not symbol_info:
                logger.error(f"Failed to get symbol info for {symbol}")
                return
            
            tick_size = symbol_info.tick_size
            logger.info(f"   Tick size: {tick_size}")
            
            # Calculate order quantity
            quantity = Decimal(str(usdt_amount)) / market_price
            steps = int(quantity / symbol_info.step_size)
            quantity = steps * symbol_info.step_size
            
            if quantity < symbol_info.min_order_size:
                quantity = symbol_info.min_order_size
            
            logger.info(f"   Order quantity: {quantity}")
        
        # Create trades in parallel
        logger.info(f"\n🎯 Creating trades across {len(accounts)} account(s) in parallel...")
        
        if ENABLE_REAL_TRADING:
            # Real trading mode - create AccountPool and execute trades
            async with AccountPool(accounts) as pool:
                tasks = []
                for account_config in accounts:
                    client = pool.get_client(account_config.id)
                    if client:
                        task = create_trade_for_account(
                            account_id=account_config.id,
                            client=client,
                            symbol=symbol,
                            side=side,
                            quantity=quantity,
                            market_price=market_price,
                            tick_size=tick_size,
                            tp_percent=tp_percent,
                            sl_percent=sl_percent,
                        )
                        tasks.append(task)
                
                # Execute in parallel with error handling
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Process results
                successful_trades: List[tuple[str, Trade]] = []
                failed_trades: List[tuple[str, Exception]] = []
                
                for result in results:
                    if isinstance(result, Exception):
                        failed_trades.append(("unknown", result))
                    else:
                        account_id, trade = result
                        if trade.status.value in ["active", "entry_filled", "completed"]:
                            successful_trades.append((account_id, trade))
                        else:
                            failed_trades.append((account_id, Exception(f"Trade status: {trade.status.value}")))
                
                # Display summary
                logger.info("\n" + "=" * 60)
                logger.info("📋 PARALLEL TRADES SUMMARY")
                logger.info("=" * 60)
                logger.info(f"Total accounts: {len(accounts)}")
                logger.info(f"Successful trades: {len(successful_trades)}")
                logger.info(f"Failed trades: {len(failed_trades)}")
                
                # Display successful trades
                if successful_trades:
                    logger.info("\n✅ SUCCESSFUL TRADES:")
                    for account_id, trade in successful_trades:
                        logger.info(f"\n[{account_id}]")
                        logger.info(f"  Trade ID: {trade.trade_id}")
                        logger.info(f"  Status: {trade.status.value}")
                        if trade.entry_order.order_id:
                            logger.info(f"  Entry Order: {trade.entry_order.order_id} @ ${trade.entry_order.price}")
                        if trade.take_profit_order.order_id:
                            logger.info(f"  TP Order: {trade.take_profit_order.order_id} @ ${trade.take_profit_order.price}")
                        if trade.stop_loss_order.order_id:
                            logger.info(f"  SL Order: {trade.stop_loss_order.order_id} @ ${trade.stop_loss_order.price}")
                
                # Display failed trades
                if failed_trades:
                    logger.info("\n❌ FAILED TRADES:")
                    for account_id, error in failed_trades:
                        logger.error(f"[{account_id}] {error}")
        else:
            # DEMO MODE - simulate trades without API calls
            tasks = []
            for account_config in accounts:
                task = simulate_trade_creation(
                    account_id=account_config.id,
                    symbol=symbol,
                    side=side,
                    quantity=quantity,
                    market_price=market_price,
                    tp_percent=tp_percent,
                    sl_percent=sl_percent,
                )
                tasks.append(task)
            
            # Execute simulations in parallel
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Display summary
            logger.info("\n" + "=" * 60)
            logger.info("📋 SIMULATED TRADES SUMMARY (DEMO MODE)")
            logger.info("=" * 60)
            logger.info(f"Total accounts: {len(accounts)}")
            logger.info(f"Simulated trades: {len(results)}")
            
            logger.info("\n💡 SIMULATED TRADES:")
            for result in results:
                if not isinstance(result, Exception):
                    account_id, trade_info = result
                    logger.info(f"\n[{account_id}]")
                    logger.info(f"  Symbol: {trade_info['symbol']}")
                    logger.info(f"  Side: {trade_info['side'].upper()}")
                    logger.info(f"  Quantity: {trade_info['quantity']}")
                    logger.info(f"  Entry Price: ${trade_info['entry_price']}")
                    logger.info(f"  TP Price: ${trade_info['tp_price']} (+{tp_percent}%)")
                    logger.info(f"  SL Price: ${trade_info['sl_price']} (-{sl_percent}%)")
                    logger.info(f"  Status: {trade_info['status']}")
                else:
                    logger.error(f"Simulation error: {result}")
            
            logger.info("\n💡 To execute real trades, set ENABLE_REAL_TRADING=True")
        
        logger.info("\n" + "=" * 60)
        
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
        logger.error(f"\n❌ Unexpected Error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
