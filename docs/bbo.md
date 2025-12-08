# BBO (Best Bid Offer) Order Feature

## Overview

The BBO (Best Bid Offer) order feature automatically calculates optimal limit order prices by placing orders a specified number of ticks away from the current market price. This maximizes the chance of maker fee execution while obtaining favorable pricing.

## What is BBO?

BBO orders are limit orders strategically placed near the market price to:
- **Increase maker fee probability**: Orders at or near the best bid/offer have higher chances of being filled as maker orders
- **Optimize pricing**: Get better execution prices compared to market orders
- **Control slippage**: Limit orders provide price certainty unlike market orders
- **Earn maker rebates**: Many exchanges offer rebates for providing liquidity (maker orders)

## How It Works

### Price Calculation

The BBO price is calculated based on:
- **Best bid/ask**: The current order book top prices
- **Tick size**: The minimum price increment for the symbol
- **Ticks distance**: How many ticks away from best prices (configurable, default: 1)

**Formula (Maker-Side Pricing):**
```
BUY orders:  BBO Price = Best Bid - (Tick Size × Ticks Distance)
SELL orders: BBO Price = Best Ask + (Tick Size × Ticks Distance)
```

> **Why?** Placing BUY orders below the best bid and SELL orders above the best ask
> ensures your order doesn't cross the spread, guaranteeing execution as a maker order
> with lower (or rebate) fees.

### Examples

**Example 1: BTC with 1 tick distance (default)**
```
Best Bid: $92,419.60
Best Ask: $92,419.70
Tick Size: $0.10
Ticks Distance: 1 (default)

BUY BBO Price:  $92,419.60 - ($0.10 × 1) = $92,419.50 (below best bid = maker)
SELL BBO Price: $92,419.70 + ($0.10 × 1) = $92,419.80 (above best ask = maker)
```

**Example 2: BTC with 5 tick distance**
```
Best Bid: $92,419.60
Best Ask: $92,419.70
Tick Size: $0.10
Ticks Distance: 5

BUY BBO Price:  $92,419.60 - ($0.10 × 5) = $92,419.10 (5 ticks below bid)
SELL BBO Price: $92,419.70 + ($0.10 × 5) = $92,420.20 (5 ticks above ask)
```

**Example 3: ETH with custom tick distance**
```
Best Bid: $3,000.00
Best Ask: $3,000.05
Tick Size: $0.01
Ticks Distance: 3

BUY BBO Price:  $3,000.00 - ($0.01 × 3) = $2,999.97 (3 ticks below bid)
SELL BBO Price: $3,000.05 + ($0.01 × 3) = $3,000.08 (3 ticks above ask)
```

## Use Cases

### 1. Market Making
Place orders 1-3 ticks away to capture spread profits while maintaining high fill probability.

```python
# Place bid 2 ticks below market, ask 2 ticks above market
await client.place_bbo_order(
    symbol="BTCUSDT",
    side="buy",
    quantity=Decimal("0.1"),
    market_price=market_price,
    tick_size=tick_size,
    ticks_distance=2
)
```

### 2. Optimal Entry/Exit
Get better prices than market orders without manual price calculation.

```python
# Enter long position at slightly better price than market
await client.place_bbo_order(
    symbol="ETHUSDT",
    side="buy",
    quantity=Decimal("1.0"),
    market_price=current_mark_price,
    tick_size=symbol_info.tick_size,
    ticks_distance=1,
    position_side="LONG"
)
```

### 3. Passive Accumulation
Accumulate positions at favorable prices during ranging markets.

```python
# Place order 5 ticks away for passive accumulation
await client.place_bbo_order(
    symbol="ADAUSDT",
    side="buy",
    quantity=Decimal("1000"),
    market_price=market_price,
    tick_size=tick_size,
    ticks_distance=5  # More patient accumulation
)
```

## API Reference

### `place_bbo_order()`

Place a BBO order with automatic price calculation.

**Method Signature:**
```python
async def place_bbo_order(
    symbol: str,
    side: str,
    quantity: Decimal,
    market_price: Decimal,
    tick_size: Decimal,
    ticks_distance: int = 1,
    time_in_force: str = "gtc",
    client_order_id: Optional[str] = None,
    position_side: Optional[str] = None,
) -> OrderResponse
```

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `symbol` | `str` | Yes | - | Trading symbol (e.g., "BTCUSDT") |
| `side` | `str` | Yes | - | Order side: "buy" or "sell" |
| `quantity` | `Decimal` | Yes | - | Order quantity |
| `market_price` | `Decimal` | Yes | - | Current market price for reference |
| `tick_size` | `Decimal` | Yes | - | Tick size for the symbol |
| `ticks_distance` | `int` | No | `1` | Number of ticks away from market price |
| `time_in_force` | `str` | No | `"gtc"` | Time in force: "gtc", "ioc", "fok" |
| `client_order_id` | `str` | No | `None` | Custom client order ID |
| `position_side` | `str` | No | `None` | Position side for hedge mode: "LONG" or "SHORT" |

**Returns:**
- `OrderResponse`: Order details including order ID, status, and executed price

**Raises:**
- `ValueError`: If parameters are invalid (e.g., ticks_distance < 1, invalid side)

**Example:**
```python
from decimal import Decimal
from aster_client import AsterClient
from aster_client.public_client import AsterPublicClient

async def place_bbo_buy_order():
    # Get market data
    async with AsterPublicClient() as public_client:
        ticker = await public_client.get_ticker("BTCUSDT")
        symbol_info = await public_client.get_symbol_info("BTCUSDT")
        
        market_price = Decimal(str(ticker["markPrice"]))
        tick_size = symbol_info.price_filter.tick_size
    
    # Place BBO order
    async with AsterClient.from_env() as client:
        order = await client.place_bbo_order(
            symbol="BTCUSDT",
            side="buy",
            quantity=Decimal("0.001"),
            market_price=market_price,
            tick_size=tick_size,
            ticks_distance=2,  # 2 ticks away
            position_side="LONG"
        )
        
        print(f"Order placed at ${order.price}")
        print(f"Market price was ${market_price}")
```

### `calculate_bbo_price()`

Calculate BBO price without placing an order.

**Function Signature:**
```python
def calculate_bbo_price(
    symbol: str,
    side: str,
    market_price: Decimal,
    tick_size: Decimal,
    ticks_distance: int = 1,
) -> Decimal
```

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `symbol` | `str` | Yes | - | Trading symbol |
| `side` | `str` | Yes | - | Order side: "buy" or "sell" |
| `market_price` | `Decimal` | Yes | - | Current market price |
| `tick_size` | `Decimal` | Yes | - | Tick size for the symbol |
| `ticks_distance` | `int` | No | `1` | Number of ticks away from market price |

**Returns:**
- `Decimal`: Calculated BBO price

**Example:**
```python
from decimal import Decimal
from aster_client.bbo import calculate_bbo_price

# Calculate buy price 3 ticks above market
buy_price = calculate_bbo_price(
    symbol="BTCUSDT",
    side="buy",
    market_price=Decimal("50000.0"),
    tick_size=Decimal("0.1"),
    ticks_distance=3
)
# Result: 50000.3

# Calculate sell price 1 tick below market
sell_price = calculate_bbo_price(
    symbol="ETHUSDT",
    side="sell",
    market_price=Decimal("3000.0"),
    tick_size=Decimal("0.01"),
    ticks_distance=1
)
# Result: 2999.99
```

### `create_bbo_order()`

Create an `OrderRequest` with BBO pricing (without placing it).

**Function Signature:**
```python
def create_bbo_order(
    symbol: str,
    side: str,
    quantity: Decimal,
    market_price: Decimal,
    tick_size: Decimal,
    ticks_distance: int = 1,
    time_in_force: str = "gtc",
    client_order_id: Optional[str] = None,
    position_side: Optional[str] = None,
) -> OrderRequest
```

**Returns:**
- `OrderRequest`: Order request object with calculated BBO price

**Example:**
```python
from decimal import Decimal
from aster_client.bbo import create_bbo_order

# Create order request
order_request = create_bbo_order(
    symbol="BTCUSDT",
    side="buy",
    quantity=Decimal("0.001"),
    market_price=Decimal("50000.0"),
    tick_size=Decimal("0.1"),
    ticks_distance=2
)

# Inspect before placing
print(f"Order will be placed at: ${order_request.price}")

# Place the order
async with AsterClient.from_env() as client:
    response = await client.place_order(order_request)
```

## Configuration Options

### Ticks Distance

The `ticks_distance` parameter controls how aggressively or passively your order is placed:

| Distance | Strategy | Fill Probability | Price Quality |
|----------|----------|------------------|---------------|
| 1 tick | **Aggressive** | Very High | Good |
| 2-3 ticks | **Balanced** | High | Better |
| 4-5 ticks | **Moderate** | Medium | Much Better |
| 6-10 ticks | **Passive** | Lower | Best |
| 11+ ticks | **Very Passive** | Low | Excellent |

**Choosing the right distance:**

- **High volatility markets**: Use 1-2 ticks for faster fills
- **Low volatility markets**: Use 3-5 ticks for better prices
- **Accumulation strategies**: Use 5-10 ticks for patient entry
- **Market making**: Use 1-3 ticks for both sides

### Time in Force

- **GTC (Good Till Cancelled)**: Order stays until filled or manually cancelled (default)
- **IOC (Immediate or Cancel)**: Fill immediately or cancel
- **FOK (Fill or Kill)**: Fill entire order immediately or cancel

### Position Side (Hedge Mode)

If your account is in hedge mode, specify the position side:
- **"LONG"**: For long positions
- **"SHORT"**: For short positions
- **"BOTH"**: For one-way mode (default if not specified)

## Best Practices

### 1. Always Get Fresh Market Data

```python
# ✅ Good: Get current market price
ticker = await public_client.get_ticker(symbol)
market_price = Decimal(str(ticker["markPrice"]))

# ❌ Bad: Use stale or hardcoded prices
market_price = Decimal("50000.0")  # Don't do this!
```

### 2. Get Tick Size from Symbol Info

```python
# ✅ Good: Get actual tick size for the symbol
symbol_info = await public_client.get_symbol_info(symbol)
tick_size = symbol_info.price_filter.tick_size

# ❌ Bad: Assume or hardcode tick size
tick_size = Decimal("0.1")  # May be wrong for some symbols!
```

### 3. Validate Sufficient Balance

```python
# ✅ Good: Check balance before placing order
account_info = await client.get_account_info()
if account_info.buying_power < estimated_cost:
    logger.error("Insufficient buying power")
    return

order = await client.place_bbo_order(...)
```

### 4. Use Appropriate Ticks Distance

```python
# ✅ Good: Adjust based on market conditions
if volatility > threshold:
    ticks_distance = 1  # Aggressive for volatile markets
else:
    ticks_distance = 3  # More passive for stable markets

# ❌ Bad: Always use the same distance
ticks_distance = 5  # Might miss fills in volatile markets
```

### 5. Handle Errors Gracefully

```python
try:
    order = await client.place_bbo_order(...)
    logger.info(f"Order placed: {order.order_id}")
except ValueError as e:
    logger.error(f"Invalid parameters: {e}")
except Exception as e:
    if "-2019" in str(e):
        logger.error("Insufficient margin")
    elif "-4061" in str(e):
        logger.error("Position side mismatch")
    else:
        logger.error(f"Unexpected error: {e}")
```

### 6. Monitor Order Fill Status

```python
# Place order
order = await client.place_bbo_order(...)

# Monitor fill status
await asyncio.sleep(5)  # Wait before checking

status = await client.get_order(
    symbol=order.symbol,
    order_id=int(order.order_id)
)

if status.status == "filled":
    logger.info(f"Order filled at ${status.average_price}")
elif status.status == "partially_filled":
    logger.info(f"Partially filled: {status.filled_quantity}/{status.quantity}")
else:
    logger.info("Order still open")
```

## Complete Example

Here's a complete example demonstrating the BBO feature:

```python
#!/usr/bin/env python3
import asyncio
from decimal import Decimal
from aster_client import AsterClient
from aster_client.public_client import AsterPublicClient
from aster_client.bbo import calculate_bbo_price

async def main():
    symbol = "BTCUSDT"
    side = "buy"
    quantity = Decimal("0.001")
    ticks_distance = 2
    
    # Step 1: Get market data
    async with AsterPublicClient() as public_client:
        # Get current price
        ticker = await public_client.get_ticker(symbol)
        market_price = Decimal(str(ticker["markPrice"]))
        print(f"Market price: ${market_price}")
        
        # Get symbol info for tick size
        symbol_info = await public_client.get_symbol_info(symbol)
        tick_size = symbol_info.price_filter.tick_size
        print(f"Tick size: ${tick_size}")
    
    # Step 2: Calculate BBO prices
    buy_price = calculate_bbo_price(
        symbol, "buy", market_price, tick_size, ticks_distance
    )
    sell_price = calculate_bbo_price(
        symbol, "sell", market_price, tick_size, ticks_distance
    )
    
    print(f"\nBBO Prices ({ticks_distance} ticks away):")
    print(f"  BUY:  ${buy_price}")
    print(f"  SELL: ${sell_price}")
    
    # Step 3: Check account balance
    async with AsterClient.from_env() as client:
        account_info = await client.get_account_info()
        print(f"\nAccount balance: ${account_info.cash}")
        print(f"Buying power: ${account_info.buying_power}")
        
        # Step 4: Place BBO order
        try:
            order = await client.place_bbo_order(
                symbol=symbol,
                side=side,
                quantity=quantity,
                market_price=market_price,
                tick_size=tick_size,
                ticks_distance=ticks_distance,
                position_side="LONG"
            )
            
            print(f"\n✅ Order placed successfully!")
            print(f"  Order ID: {order.order_id}")
            print(f"  BBO Price: ${order.price}")
            print(f"  Status: {order.status}")
            
            # Step 5: Monitor order
            await asyncio.sleep(5)
            status = await client.get_order(
                symbol=symbol,
                order_id=int(order.order_id)
            )
            print(f"\nOrder status: {status.status}")
            if status.filled_quantity > 0:
                print(f"Filled: {status.filled_quantity}")
                
        except Exception as e:
            print(f"❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
```

## FAQ

### Q: What's the difference between BBO and market orders?

**Market orders:**
- Execute immediately at current market price
- May experience slippage
- Always pay taker fees
- Less favorable pricing

**BBO orders:**
- Execute when price reaches your limit (if at all)
- No slippage beyond your limit price
- High chance of maker fees/rebates
- Better pricing control

### Q: When should I use different ticks distances?

- **1 tick**: When fill probability is more important than price
- **2-3 ticks**: Balanced approach for most trading
- **5+ ticks**: When accumulating positions or price quality matters most

### Q: Will my BBO order always get filled?

No. BBO orders are limit orders, so they only fill if the market price reaches (or crosses) your order price. If the market moves away, your order remains open until:
- The market returns to your price
- You manually cancel it
- It expires (if using IOC/FOK)

### Q: Can I update the ticks distance after placing an order?

No. To change the distance, you must:
1. Cancel the existing order
2. Calculate new BBO price with different ticks distance
3. Place a new order

### Q: What happens if I set ticks_distance = 0?

The system will raise a `ValueError` because ticks_distance must be at least 1.

### Q: How do I know what tick size to use?

Always get the tick size from `SymbolInfo`:

```python
symbol_info = await public_client.get_symbol_info("BTCUSDT")
tick_size = symbol_info.price_filter.tick_size
```

Don't hardcode tick sizes as they may change or vary by symbol.

## Troubleshooting

### Error: "Tick size must be greater than 0"

**Cause:** Invalid tick size provided

**Solution:**
```python
# Get tick size from symbol info
symbol_info = await public_client.get_symbol_info(symbol)
tick_size = symbol_info.price_filter.tick_size
```

### Error: "Ticks distance must be at least 1"

**Cause:** `ticks_distance` is 0 or negative

**Solution:**
```python
# Use at least 1
ticks_distance = max(1, your_calculated_distance)
```

### Error: "Insufficient margin"

**Cause:** Not enough buying power for the order

**Solution:**
```python
# Check balance first
account_info = await client.get_account_info()
max_quantity = account_info.buying_power / market_price
quantity = min(desired_quantity, max_quantity)
```

### Order not filling

**Cause:** Market moved away from your BBO price

**Solution:**
- Reduce `ticks_distance` for faster fills
- Monitor market conditions
- Consider canceling and replacing with updated BBO price

## See Also

- [Order Management Documentation](./orders.md)
- [Account Management Documentation](./account.md)
- [Symbol Information Documentation](./symbols.md)
- [Example Scripts](../examples/)
