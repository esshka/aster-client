import asyncio
import logging
from decimal import Decimal
from aster_client.bbo import BBOPriceCalculator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("BBODemo")

async def main():
    logger.info("Starting BBO WebSocket Demo")
    
    # Get the singleton instance
    calculator = BBOPriceCalculator()
    
    # Start the WebSocket connection
    await calculator.start()
    
    try:
        logger.info("Waiting for WebSocket connection and initial data...")
        await asyncio.sleep(5)  # Give it some time to connect and fill cache
        
        symbol = "BTCUSDT"
        
        logger.info(f"Monitoring BBO for: {symbol}")
        
        # Monitor for 10 seconds
        for i in range(10):
            print("\n" + "="*60)
            print(f"Update #{i+1}")
            print(f"{'Best Bid':>12} | {'Best Ask':>12} | {'BBO Buy Price':>15}")
            print("-" * 60)
            
            bbo = calculator.get_bbo(symbol)
            if bbo:
                best_bid, best_ask = bbo
                tick_size = Decimal("0.1")  # BTCUSDT tick size
                
                try:
                    buy_price = calculator.calculate_bbo_price(
                        symbol, "buy", best_bid, best_ask, tick_size
                    )
                    print(f"{best_bid:>12} | {best_ask:>12} | {buy_price:>15}")
                except ValueError as e:
                    print(f"Error: {e}")
            else:
                print("Waiting for data...")
            
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("Demo interrupted")
    except Exception as e:
        logger.error(f"An error occurred: {e}")
    finally:
        logger.info("Stopping BBO WebSocket...")
        await calculator.stop()
        logger.info("Done")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
