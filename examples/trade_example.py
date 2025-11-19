"""
Trade Example - Single trade with BBO entry, TP, and SL orders.

This example demonstrates how to:
1. Create a client from environment variables
2. Fetch market data (current price and symbol info)
3. Create a complete trade with percent-based TP/SL
4. Display trade results and order IDs

Prerequisites:
- Set ASTER_API_KEY and ASTER_API_SECRET in .env file
- Ensure account has sufficient balance and trading is enabled
"""

import asyncio
import logging
from decimal import Decimal

from aster_client import AsterClient, create_trade
from aster_client.public_client import AsterPublicClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


async def main():
    """Main example function."""
    # Configuration
    symbol = "ETHUSDT"
    side = "buy"  # "buy" or "sell"
    usdt_amount = 10.0  # Amount in USDT to trade
    tp_percent = 1.0  # 1% take profit
    sl_percent = 0.5  # 0.5% stop loss
    ticks_distance = 1  # BBO distance in ticks
    
    logger.info(f"🚀 Trade Example: {symbol} {side.upper()}")
    logger.info(f"   Amount: ${usdt_amount} USDT")
    logger.info(f"   TP: +{tp_percent}%, SL: -{sl_percent}%")
    
    # Create clients
    async with AsterClient.from_env() as client, AsterPublicClient() as public_client:
        # Step 1: Get current market price
        logger.info("\n📊 Fetching market data...")
        ticker = await public_client.get_ticker(symbol)
        if not ticker or not ticker.markPrice:
            logger.error(f"Failed to get ticker for {symbol}")
            return
        
        market_price = Decimal(str(ticker.markPrice))
        logger.info(f"   Current price: ${market_price}")
        
        # Step 2: Get symbol information for tick size
        symbol_info = await public_client.get_symbol_info(symbol)
        if not symbol_info:
            logger.error(f"Failed to get symbol info for {symbol}")
            return
        
        tick_size = symbol_info.tick_size
        logger.info(f"   Tick size: {tick_size}")
        
        # Step 3: Calculate order quantity from USDT amount
        quantity = Decimal(str(usdt_amount)) / market_price
        
        # Round to step size
        steps = int(quantity / symbol_info.step_size)
        quantity = steps * symbol_info.step_size
        
        # Ensure minimum order size
        if quantity < symbol_info.min_order_size:
            quantity = symbol_info.min_order_size
        
        logger.info(f"   Order quantity: {quantity} (min: {symbol_info.min_order_size})")
        
        # Step 4: Create the trade
        logger.info("\n🎯 Creating trade...")
        trade = await create_trade(
            client=client,
            symbol=symbol,
            side=side,
            quantity=quantity,
            market_price=market_price,
            tick_size=tick_size,
            tp_percent=tp_percent,
            sl_percent=sl_percent,
            ticks_distance=ticks_distance,
            fill_timeout=30.0,  # 30 seconds timeout for testing
            poll_interval=2.0,
        )
        
        # Step 5: Display results
        logger.info("\n" + "=" * 60)
        logger.info("📋 TRADE RESULTS")
        logger.info("=" * 60)
        logger.info(f"Trade ID: {trade.trade_id}")
        logger.info(f"Symbol: {trade.symbol}")
        logger.info(f"Side: {trade.side.upper()}")
        logger.info(f"Status: {trade.status.value}")
        logger.info(f"Created: {trade.created_at}")
        
        if trade.entry_order.order_id:
            logger.info(f"\n📥 ENTRY ORDER:")
            logger.info(f"   Order ID: {trade.entry_order.order_id}")
            logger.info(f"   Price: ${trade.entry_order.price}")
            logger.info(f"   Size: {trade.entry_order.size}")
            logger.info(f"   Status: {trade.entry_order.status}")
            if trade.entry_order.filled_at:
                logger.info(f"   Filled At: {trade.entry_order.filled_at}")
        
        if trade.take_profit_order.order_id:
            logger.info(f"\n📈 TAKE PROFIT ORDER:")
            logger.info(f"   Order ID: {trade.take_profit_order.order_id}")
            logger.info(f"   Price: ${trade.take_profit_order.price}")
            logger.info(f"   Size: {trade.take_profit_order.size}")
            logger.info(f"   Status: {trade.take_profit_order.status}")
        elif trade.take_profit_order.error:
            logger.error(f"\n❌ TAKE PROFIT ORDER FAILED:")
            logger.error(f"   Error: {trade.take_profit_order.error}")
        
        if trade.stop_loss_order.order_id:
            logger.info(f"\n📉 STOP LOSS ORDER:")
            logger.info(f"   Order ID: {trade.stop_loss_order.order_id}")
            logger.info(f"   Price: ${trade.stop_loss_order.price}")
            logger.info(f"   Size: {trade.stop_loss_order.size}")
            logger.info(f"   Status: {trade.stop_loss_order.status}")
        elif trade.stop_loss_order.error:
            logger.error(f"\n❌ STOP LOSS ORDER FAILED:")
            logger.error(f"   Error: {trade.stop_loss_order.error}")
        
        logger.info("\n" + "=" * 60)
        
        # Show trade as dict
        logger.info("\n📄 Trade as JSON:")
        import json
        print(json.dumps(trade.to_dict(), indent=2))


if __name__ == "__main__":
    asyncio.run(main())
