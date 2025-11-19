"""
Quick script to check the account's position mode.
"""

import asyncio
from aster_client import AsterClient


async def main():
    async with AsterClient.from_env() as client:
        mode = await client.get_position_mode()
        print(f"Position mode: {mode}")
        
        dual_side = mode.get("dualSidePosition", False)
        if dual_side:
            print("✅ Account is in HEDGE MODE (dual position side)")
            print("   You can have both LONG and SHORT positions simultaneously")
        else:
            print("✅ Account is in ONE-WAY MODE")
            print("   You can only have one position direction at a time")
            print("   positionSide should be 'BOTH' for all orders")


if __name__ == "__main__":
    asyncio.run(main())
