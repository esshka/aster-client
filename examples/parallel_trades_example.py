"""
Parallel Trades Example - Execute trades across multiple accounts in parallel.

This example demonstrates how to:
1. Set up an AccountPool with multiple accounts
2. Execute trades in parallel using asyncio.gather()
3. Handle individual account results and errors
4. Display aggregated results

Prerequisites:
- Multiple accounts configured (see AccountPool documentation)
- Each account has sufficient balance and trading enabled
"""

import asyncio
import logging
from decimal import Decimal
from typing import List

from aster_client import AccountPool, AccountConfig, Trade, create_trade
from aster_client.public_client import AsterPublicClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


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


async def main():
    """Main example function."""
    # Configuration
    symbol = "ETHUSDT"
    side = "buy"
    usdt_amount = 10.0
    tp_percent = 1.0
    sl_percent = 0.5
    
    logger.info(f"🚀 Parallel Trades Example")
    logger.info(f"   Symbol: {symbol}")
    logger.info(f"   Side: {side.upper()}")
    logger.info(f"   Amount per account: ${usdt_amount} USDT")
    logger.info(f"   TP: +{tp_percent}%, SL: -{sl_percent}%")
    
    # Set up accounts - Replace with your actual account configurations
    # For this example, we'll assume you have accounts configured in environment
    import os
    
    accounts = []
    
    # Example: Load two accounts from environment variables
    # Account 1
    if os.getenv("ASTER_API_KEY_1") and os.getenv("ASTER_API_SECRET_1"):
        accounts.append(AccountConfig(
            id="account_1",
            api_key=os.getenv("ASTER_API_KEY_1"),
            api_secret=os.getenv("ASTER_API_SECRET_1"),
        ))
    
    # Account 2
    if os.getenv("ASTER_API_KEY_2") and os.getenv("ASTER_API_SECRET_2"):
        accounts.append(AccountConfig(
            id="account_2",
            api_key=os.getenv("ASTER_API_KEY_2"),
            api_secret=os.getenv("ASTER_API_SECRET_2"),
        ))
    
    # If no accounts configured, use default account twice (for testing)
    if not accounts:
        logger.warning("No separate accounts configured, using default account")
        api_key = os.getenv("ASTER_API_KEY", "")
        api_secret = os.getenv("ASTER_API_SECRET", "")
        accounts = [
            AccountConfig(id="account_1", api_key=api_key, api_secret=api_secret),
        ]
    
    logger.info(f"\n📊 Setting up {len(accounts)} account(s)...")
    
    # Create account pool
    pool = AccountPool(accounts=accounts)
    
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
    
    logger.info("\n" + "=" * 60)
    
    # Cleanup
    await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
