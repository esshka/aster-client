import asyncio
import logging
import os
from dotenv import load_dotenv
from aster_client.account_client import AsterClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def main():
    # Load environment variables
    load_dotenv()
    
    # Initialize client
    client = AsterClient.from_env()
    
    try:
        # 1. Get current position mode
        logger.info("Getting current position mode...")
        current_mode = await client.get_position_mode()
        logger.info(f"Current position mode: {current_mode}")
        
        is_dual_side = current_mode.get('dualSidePosition', False)
        
        # 2. Toggle position mode
        new_mode_setting = not is_dual_side
        logger.info(f"Toggling position mode to: {'Hedge Mode' if new_mode_setting else 'One-way Mode'}")
        
        response = await client.change_position_mode(new_mode_setting)
        logger.info(f"Change response: {response}")
        
        # 3. Verify change
        updated_mode = await client.get_position_mode()
        logger.info(f"Updated position mode: {updated_mode}")
        
        if updated_mode.get('dualSidePosition') == new_mode_setting:
            logger.info("SUCCESS: Position mode changed successfully")
        else:
            logger.error("FAILURE: Position mode did not change")
            
        # 4. Revert change (cleanup)
        logger.info(f"Reverting position mode to: {'Hedge Mode' if is_dual_side else 'One-way Mode'}")
        await client.change_position_mode(is_dual_side)
        
        final_mode = await client.get_position_mode()
        logger.info(f"Final position mode: {final_mode}")
        
    except Exception as e:
        logger.error(f"An error occurred: {e}")
    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(main())
