import asyncio
from decimal import Decimal, ROUND_DOWN
from aster_client.public_client import AsterPublicClient

def round_step_size(quantity: Decimal, step_size: Decimal) -> Decimal:
    """Rounds a quantity down to the nearest step size."""
    if step_size == 0:
        return quantity
    return (quantity // step_size) * step_size

async def main():
    symbol = "SOLUSDT"
    target_notional = Decimal("20")  # 20 USDT

    print(f"--- Calculating Order Quantity for {symbol} ---")
    print(f"Target Notional: {target_notional} USDT")

    async with AsterPublicClient() as client:
        # 1. Get Symbol Info (for filters)
        print(f"\nFetching symbol info for {symbol}...")
        symbol_info = await client.get_symbol_info(symbol)
        if not symbol_info:
            print(f"Error: Could not fetch symbol info for {symbol}")
            return

        # 2. Get Current Price
        print(f"Fetching current ticker for {symbol}...")
        ticker = await client.get_ticker(symbol)
        if not ticker or "markPrice" not in ticker:
            print(f"Error: Could not fetch ticker for {symbol}")
            return
        
        price = Decimal(str(ticker["markPrice"]))
        print(f"Current Price: {price} USDT")

        # 3. Calculate Raw Quantity
        raw_qty = target_notional / price
        print(f"Raw Quantity ({target_notional} / {price}): {raw_qty}")

        # 4. Apply Filters
        step_size = symbol_info.step_size
        min_qty = symbol_info.min_quantity
        
        # Check if we have more specific filter data (optional, but good practice since we added them)
        if symbol_info.lot_size_filter:
            step_size = symbol_info.lot_size_filter.step_size
            min_qty = symbol_info.lot_size_filter.min_qty
            print("Using LOT_SIZE filter values.")
        else:
            print("Using default symbol info values.")

        print(f"Step Size: {step_size}")
        print(f"Min Quantity: {min_qty}")

        # Adjust for Step Size
        adjusted_qty = round_step_size(raw_qty, step_size)
        print(f"Quantity after step size adjustment: {adjusted_qty}")

        # Adjust for Min Quantity
        if adjusted_qty < min_qty:
            print(f"Warning: Calculated quantity {adjusted_qty} is less than min quantity {min_qty}.")
            adjusted_qty = min_qty
            print(f"Adjusted to min quantity: {adjusted_qty}")

        # Final Check against Min Notional
        final_notional = adjusted_qty * price
        min_notional = symbol_info.min_notional
        if symbol_info.min_notional_filter:
             min_notional = symbol_info.min_notional_filter.notional
        
        print(f"\n--- Final Result ---")
        print(f"Final Quantity: {adjusted_qty}")
        print(f"Final Notional Value: {final_notional} USDT")
        
        if final_notional < min_notional:
             print(f"WARNING: Final notional {final_notional} is less than required min notional {min_notional}!")
        else:
             print("Order is valid.")

if __name__ == "__main__":
    asyncio.run(main())
