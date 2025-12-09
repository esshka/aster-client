# Trades Module - Complete Trade Management

## Overview

The Trades module provides high-level abstractions for managing complete trades consisting of:
- **BBO Entry Order**: Best Bid Offer entry with automatic retry and price chasing
- **Take Profit (TP) Orders**: Up to 5 TP levels with custom quantity allocation
- **Stop Loss (SL) Order**: Protective stop with closePosition

All TP and SL orders are placed **in parallel** for fast execution after entry fill.

## Quick Start

```python
from decimal import Decimal
from aster_client import AsterClient, create_trade
from aster_client.public_client import AsterPublicClient

async def open_trade():
    async with AsterClient.from_env() as client, AsterPublicClient() as public:
        # Get market data
        order_book = await public.get_order_book("ETHUSDT", limit=5)
        symbol_info = await public.get_symbol_info("ETHUSDT")
        
        best_bid = Decimal(str(order_book["bids"][0][0]))
        best_ask = Decimal(str(order_book["asks"][0][0]))
        tick_size = symbol_info.price_filter.tick_size
        
        # Create trade with multiple TPs
        trade = await create_trade(
            client=client,
            symbol="ETHUSDT",
            side="buy",
            quantity=Decimal("0.1"),
            best_bid=best_bid,
            best_ask=best_ask,
            tick_size=tick_size,
            tp_percents=[0.5, 1.0, 1.5],  # 3 TPs at 0.5%, 1%, 1.5%
            sl_percent=0.5,               # SL at -0.5%
        )
        
        print(f"Trade created: {trade.trade_id}")
        print(f"Status: {trade.status.value}")
```

## Take Profit Configurations

The `tp_percents` parameter supports multiple formats for flexible TP configuration:

### Format 1: Single TP (Full Quantity)

```python
tp_percents=1.0  # One TP at +1% with 100% of quantity
```

### Format 2: Multiple TPs (Equal Split)

```python
tp_percents=[0.5, 1.0, 1.5]  # 3 TPs, each gets ~33% of quantity
```

| TP Level | Price | Quantity |
|----------|-------|----------|
| TP1 | +0.5% | 33.3% |
| TP2 | +1.0% | 33.3% |
| TP3 | +1.5% | 33.3% |

### Format 3: Custom Amounts per TP

```python
tp_percents=[[0.5, 0.5], [1.0, 0.5]]  # [price_pct, amount_fraction]
```

| TP Level | Price | Quantity |
|----------|-------|----------|
| TP1 | +0.5% | 50% |
| TP2 | +1.0% | 50% |

### Advanced Custom Allocation

```python
# Take 20% profit early, 30% at mid-range, 50% at final target
tp_percents=[
    [0.3, 0.2],   # TP1: +0.3% with 20% qty
    [0.6, 0.3],   # TP2: +0.6% with 30% qty
    [1.0, 0.5],   # TP3: +1.0% with 50% qty
]
```

> **Note:** Amount fractions must sum to 1.0 (100%). The last TP gets any remainder from rounding.

## API Reference

### `create_trade()`

Create a complete trade with BBO entry and multiple exit orders.

```python
async def create_trade(
    client: AsterClient,
    symbol: str,
    side: str,
    quantity: Decimal,
    best_bid: Decimal,
    best_ask: Decimal,
    tick_size: Decimal,
    tp_percents: Optional[Union[float, list]] = None,
    sl_percent: float = 0.5,
    ticks_distance: int = 0,
    max_retries: int = 2,
    fill_timeout_ms: int = 1000,
    max_chase_percent: float = 0.1,
    position_side: Optional[str] = None,
    vol_size: Optional[Decimal] = None,
) -> Trade
```

#### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `client` | `AsterClient` | Yes | - | Authenticated client instance |
| `symbol` | `str` | Yes | - | Trading symbol (e.g., "ETHUSDT") |
| `side` | `str` | Yes | - | Entry side: "buy" or "sell" |
| `quantity` | `Decimal` | Yes | - | Total order quantity |
| `best_bid` | `Decimal` | Yes | - | Current best bid price |
| `best_ask` | `Decimal` | Yes | - | Current best ask price |
| `tick_size` | `Decimal` | Yes | - | Symbol tick size |
| `tp_percents` | `float` or `list` | No | `None` | TP configuration (see formats above) |
| `sl_percent` | `float` | No | `0.5` | Stop loss percentage |
| `ticks_distance` | `int` | No | `0` | Entry ticks from best bid/ask |
| `max_retries` | `int` | No | `2` | Max BBO entry retries |
| `fill_timeout_ms` | `int` | No | `1000` | Time to wait for fill (ms) |
| `max_chase_percent` | `float` | No | `0.1` | Max price chase (%) |
| `position_side` | `str` | No | `None` | "LONG" or "SHORT" for hedge mode |
| `vol_size` | `Decimal` | No | `None` | Min volume for qty rounding |

#### Returns

`Trade` object containing:
- `trade_id`: Unique trade identifier
- `status`: Current trade status (`TradeStatus` enum)
- `entry_order`: Entry order details (`TradeOrder`)
- `take_profit_orders`: List of TP orders (`list[TradeOrder]`)
- `stop_loss_order`: SL order details (`TradeOrder`)

#### Raises

- `ValueError`: Invalid parameters (e.g., >5 TPs, amounts don't sum to 1.0)
- `Exception`: Order placement failures

### `calculate_tp_sl_prices()`

Calculate TP and SL prices from entry price and percentages.

```python
def calculate_tp_sl_prices(
    entry_price: Decimal,
    side: str,
    tp_percents: Optional[list],
    sl_percent: float,
    tick_size: Decimal,
) -> tuple[list[Decimal], Decimal]
```

#### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `entry_price` | `Decimal` | Entry fill price |
| `side` | `str` | "buy" or "sell" |
| `tp_percents` | `list` | List of TP percentages |
| `sl_percent` | `float` | SL percentage |
| `tick_size` | `Decimal` | Price tick size |

#### Returns

Tuple of `(tp_prices_list, sl_price)`:
- `tp_prices_list`: List of calculated TP prices
- `sl_price`: Calculated SL price

#### Examples

```python
from decimal import Decimal
from aster_client.trades import calculate_tp_sl_prices

# BUY trade: TPs above entry, SL below entry
tp_prices, sl_price = calculate_tp_sl_prices(
    entry_price=Decimal("3500"),
    side="buy",
    tp_percents=[1.0, 2.0],
    sl_percent=0.5,
    tick_size=Decimal("0.01"),
)
# tp_prices = [Decimal("3535.00"), Decimal("3570.00")]
# sl_price = Decimal("3482.50")

# SELL trade: TPs below entry, SL above entry
tp_prices, sl_price = calculate_tp_sl_prices(
    entry_price=Decimal("3500"),
    side="sell",
    tp_percents=[1.0],
    sl_percent=0.5,
    tick_size=Decimal("0.01"),
)
# tp_prices = [Decimal("3465.00")]
# sl_price = Decimal("3517.50")
```

## Trade Object

### TradeStatus Enum

```python
class TradeStatus(Enum):
    PENDING = "pending"           # Created, no orders placed
    ENTRY_PLACED = "entry_placed" # Entry order placed, waiting fill
    ENTRY_FILLED = "entry_filled" # Entry filled, placing TP/SL
    ACTIVE = "active"             # All orders placed, trade running
    COMPLETED = "completed"       # TP or SL triggered
    CANCELLED = "cancelled"       # Cancelled before completion
    FAILED = "failed"             # Error occurred
```

### TradeOrder Dataclass

```python
@dataclass
class TradeOrder:
    order_id: Optional[str] = None
    price: Optional[Decimal] = None
    size: Optional[Decimal] = None
    status: Optional[str] = None
    error: Optional[str] = None
    placed_at: Optional[str] = None
    filled_at: Optional[str] = None
```

### Trade Dataclass

```python
@dataclass
class Trade:
    trade_id: str
    symbol: str
    side: str
    entry_order: TradeOrder
    take_profit_orders: list[TradeOrder]  # Up to 5
    stop_loss_order: TradeOrder
    status: TradeStatus
    tp_percents: Optional[list]
    sl_percent: Optional[float]
    created_at: Optional[str]
    filled_at: Optional[str]
    closed_at: Optional[str]
    metadata: dict
```

### Serialization

```python
# Convert trade to dictionary
trade_dict = trade.to_dict()

# Example output
{
    "trade_id": "trade_ETHUSDT_buy_1702080000000",
    "symbol": "ETHUSDT",
    "side": "buy",
    "status": "active",
    "tp_percents": [0.5, 1.0],
    "sl_percent": 0.5,
    "entry_order": {
        "order_id": "123456",
        "price": "3500.00",
        "size": "0.1",
        "status": "FILLED",
        ...
    },
    "take_profit_orders": [
        {"order_id": "123457", "price": "3517.50", "size": "0.05", ...},
        {"order_id": "123458", "price": "3535.00", "size": "0.05", ...},
    ],
    "stop_loss_order": {
        "order_id": "123459",
        "price": "3482.50",
        ...
    },
    ...
}
```

## Workflow

### 1. Entry Phase

1. Place BBO entry order with automatic retry
2. Chase price if needed (up to `max_chase_percent`)
3. Wait for fill (up to `fill_timeout_ms` per attempt)
4. If fill fails after `max_retries`, trade is CANCELLED

### 2. Exit Orders Phase (Parallel)

After entry fills, all exit orders are placed **simultaneously**:

```
┌─────────────────────────────────────────────────┐
│              asyncio.gather()                   │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌───────┐ │
│  │  TP[1]  │ │  TP[2]  │ │  TP[3]  │ │  SL   │ │
│  └─────────┘ └─────────┘ └─────────┘ └───────┘ │
└─────────────────────────────────────────────────┘
```

- **TP Orders**: LIMIT orders with GTX (post-only maker)
- **SL Order**: STOP_MARKET with closePosition=True

### 3. Trade Active

Trade is marked ACTIVE when:
- At least one TP order placed successfully (if TPs were requested)
- SL order placed successfully

## Examples

### Basic Long Trade

```python
trade = await create_trade(
    client=client,
    symbol="BTCUSDT",
    side="buy",
    quantity=Decimal("0.01"),
    best_bid=best_bid,
    best_ask=best_ask,
    tick_size=Decimal("0.1"),
    tp_percents=1.0,    # Single TP at +1%
    sl_percent=0.5,     # SL at -0.5%
)
```

### Short Trade with Multiple TPs

```python
trade = await create_trade(
    client=client,
    symbol="ETHUSDT",
    side="sell",
    quantity=Decimal("1.0"),
    best_bid=best_bid,
    best_ask=best_ask,
    tick_size=Decimal("0.01"),
    tp_percents=[0.3, 0.6, 1.0],  # 3 TPs, equal split
    sl_percent=0.5,
    position_side="SHORT",
)
```

### Scalping with Custom TP Allocation

```python
# Take most profit early, leave small runner
trade = await create_trade(
    client=client,
    symbol="SOLUSDT",
    side="buy",
    quantity=Decimal("10"),
    best_bid=best_bid,
    best_ask=best_ask,
    tick_size=Decimal("0.001"),
    tp_percents=[
        [0.3, 0.5],   # 50% at +0.3%
        [0.5, 0.3],   # 30% at +0.5%
        [1.0, 0.2],   # 20% at +1.0%
    ],
    sl_percent=0.3,
    vol_size=Decimal("0.1"),  # Round quantities
)
```

### Aggressive Entry with Full TP Config

```python
trade = await create_trade(
    client=client,
    symbol="BTCUSDT",
    side="buy",
    quantity=Decimal("0.05"),
    best_bid=best_bid,
    best_ask=best_ask,
    tick_size=tick_size,
    tp_percents=[
        [0.2, 0.2],   # TP1: +0.2% with 20%
        [0.4, 0.2],   # TP2: +0.4% with 20%
        [0.6, 0.2],   # TP3: +0.6% with 20%
        [0.8, 0.2],   # TP4: +0.8% with 20%
        [1.0, 0.2],   # TP5: +1.0% with 20%
    ],
    sl_percent=0.5,
    ticks_distance=0,         # Entry at best bid/ask
    max_retries=5,            # More retries
    fill_timeout_ms=500,      # Faster retry
    max_chase_percent=0.2,    # Chase up to 0.2%
)
```

### Trade Without TP (SL Only)

```python
trade = await create_trade(
    client=client,
    symbol="ETHUSDT",
    side="buy",
    quantity=Decimal("0.5"),
    best_bid=best_bid,
    best_ask=best_ask,
    tick_size=tick_size,
    tp_percents=None,  # No TPs
    sl_percent=1.0,    # SL only at -1%
)
```

## Error Handling

```python
from aster_client import create_trade
from aster_client.trades import TradeStatus

trade = await create_trade(...)

# Check trade status
if trade.status == TradeStatus.CANCELLED:
    print(f"Entry failed: {trade.entry_order.error}")
    
elif trade.status == TradeStatus.ACTIVE:
    # Check for partial failures
    failed_tps = [tp for tp in trade.take_profit_orders if tp.error]
    if failed_tps:
        print(f"Warning: {len(failed_tps)} TP orders failed")
    
    if trade.stop_loss_order.error:
        print(f"Warning: SL order failed: {trade.stop_loss_order.error}")
        
elif trade.status == TradeStatus.FAILED:
    print(f"Trade failed: {trade.metadata.get('error')}")
```

## Best Practices

### 1. Always Provide Fresh Market Data

```python
# Get fresh order book before each trade
order_book = await public.get_order_book(symbol, limit=5)
best_bid = Decimal(str(order_book["bids"][0][0]))
best_ask = Decimal(str(order_book["asks"][0][0]))
```

### 2. Get Symbol Info for Tick/Vol Size

```python
symbol_info = await public.get_symbol_info(symbol)
tick_size = symbol_info.price_filter.tick_size
vol_size = symbol_info.lot_size_filter.step_size
```

### 3. Validate TP Amounts Sum to 1.0

```python
# This will raise ValueError
tp_percents=[[0.5, 0.3], [1.0, 0.5]]  # Sums to 0.8, not 1.0

# Correct
tp_percents=[[0.5, 0.5], [1.0, 0.5]]  # Sums to 1.0 ✓
```

### 4. Use vol_size for Clean Quantities

```python
# Prevents tiny remainder quantities
trade = await create_trade(
    ...
    vol_size=symbol_info.lot_size_filter.step_size,
)
```

### 5. Handle Partial Failures

```python
# Trade can be ACTIVE even if some TPs failed
if trade.status == TradeStatus.ACTIVE:
    successful_tps = len([tp for tp in trade.take_profit_orders if tp.order_id])
    total_tps = len(trade.take_profit_orders)
    print(f"Trade active with {successful_tps}/{total_tps} TPs")
```

## Logging

The trades module logs key events:

```
📊 Creating trade trade_ETHUSDT_buy_1702080000000: ETHUSDT BUY 0.1
   TPs: ['+0.5%', '+1.0%'], SL: -0.5%
   BBO: ticks_distance=0, max_retries=2, timeout=1000ms, chase=0.1%
✅ Entry order filled: 123456 @ 3500.00
📈 TPs: [Decimal('3517.50'), Decimal('3535.00')], SL: $3482.50
   TP quantities: ['0.05', '0.05']
   Placing 3 orders in parallel...
✅ TP[1] order placed: 123457 @ $3517.50 (0.05)
✅ TP[2] order placed: 123458 @ $3535.00 (0.05)
✅ Stop loss order placed: 123459 @ $3482.50
🎉 Trade trade_ETHUSDT_buy_1702080000000 is now ACTIVE
```

## See Also

- [BBO Orders Documentation](./bbo.md)
- [Example Scripts](../examples/)
