# aster-client

Production-ready Python client for the [Aster](https://docs.asterdex.com/) perpetual trading platform with async/await support.

![Python](https://img.shields.io/badge/python-3.11+-blue.svg)
[![Poetry](https://img.shields.io/endpoint?url=https://python-poetry.org/badge/v0.json)](https://python-poetry.org/)

## Features

- **Full API Coverage**: Complete access to Aster trading and market data endpoints
- **Async/Await**: Built for high-performance asynchronous operations
- **Reliable**: Automatic retry logic, proper error handling, and resource cleanup
- **Secure**: Built-in authentication and request signing
- **Dual Client Design**: Separate clients for authenticated trading and public market data

## Installation

```bash
poetry add aster-client
# or
pip install aster-client
```

## Quick Start

### Public Market Data (No Authentication)

```python
import asyncio
from aster_client import PublicClient

async def get_market_data():
    async with PublicClient() as client:
        exchange_info = await client.get_exchange_info()
        mark_prices = await client.get_all_mark_prices()
        print(f"Exchange Timezone: {exchange_info.get('timezone')}")
        print(f"Number of symbols: {len(exchange_info.get('symbols', []))}")

asyncio.run(get_market_data())
```

### Authenticated Trading

```python
import asyncio
from aster_client import AsterClient
from aster_client.models.orders import OrderRequest

async def trading_example():
    # Initialize from environment variables (ASTER_API_KEY, ASTER_API_SECRET)
    client = AsterClient.from_env()
    
    async with client:
        account = await client.get_account_info()
        print(f"Balance: {account.equity} USD")
        
        # Create order request
        order_req = OrderRequest(
            symbol="BTC-PERP",
            side="BUY",
            order_type="LIMIT",
            quantity=0.001,
            price=45000.0,
            position_side="LONG" # Required for Hedge Mode
        )
        
        # Place order
        order = await client.place_order(order_req)
        print(f"Order placed: {order.order_id}")

asyncio.run(trading_example())
```

## API Reference

### PublicClient
- `get_exchange_info()` - Exchange information (returns dict)
- `get_symbol_info(symbol)` - Information for specific symbol
- `get_all_mark_prices()` - Current mark prices for all symbols
- `get_ticker(symbol)` - Ticker data for specific symbol

### AsterClient
**Account:**
- `get_account_info()` - Account details and balances
- `get_balances()` - All account balances
- `get_positions()` - Open positions

**Orders:**
- `place_order(order: OrderRequest)` - Place new order
- `place_bbo_order(symbol, side, quantity, ...)` - Place BBO (Best Bid Offer) order
- `cancel_order(order_id)` - Cancel existing order
- `get_orders(symbol)` - Get all orders for symbol
- `get_order(order_id)` - Get specific order details

## Advanced Features

### Automated Trades with BBO Entry, Take Profit, and Stop Loss

The trades module provides a high-level abstraction for managing complete trades with automatic BBO entry, take profit, and stop loss orders.

```python
import asyncio
from decimal import Decimal
from aster_client import AsterClient, create_trade

async def create_automated_trade():
    async with AsterClient.from_env() as client:
        # Create a complete trade with TP and SL
        trade = await create_trade(
            client=client,
            symbol="ETHUSDT",
            side="buy",  # or "sell"
            quantity=Decimal("0.1"),
            market_price=Decimal("3000.0"),
            tick_size=Decimal("0.01"),
            tp_percent=1.0,  # 1% take profit
            sl_percent=0.5,  # 0.5% stop loss
            fill_timeout=10.0,  # Wait 10s for entry fill (default)
            poll_interval=0.5,  # Check every 0.5s (default)
        )
        
        if trade.status == "active":
            print(f"✅ Trade active!")
            print(f"Entry: {trade.entry_order.price}")
            print(f"TP: {trade.take_profit_order.price}")
            print(f"SL: {trade.stop_loss_order.price}")
        else:
            print(f"❌ Trade failed: {trade.metadata.get('error')}")

asyncio.run(create_automated_trade())
```

**Features:**
- **BBO Entry**: Automatically places limit order 1 tick from market price for better fills
- **Smart Timeout**: Waits up to 10 seconds (configurable) for entry fill, polls every 0.5s
- **Auto-Cancellation**: Cancels entry order if not filled within timeout
- **Position Closing**: TP and SL orders use `closePosition=true` to properly close positions
- **Hedge Mode Support**: Works seamlessly in both One-way and Hedge mode
- **Calculated Prices**: TP/SL prices automatically calculated from entry fill price

**Trade Workflow:**
1. Places BBO entry order (limit order 1 tick from market)
2. Polls order status every 0.5s (waits up to 10s by default)
3. If timeout, cancels entry order and returns failed trade
4. Once filled, calculates TP/SL prices from actual fill price
5. Places TAKE_PROFIT_MARKET order with `closePosition=true`
6. Places STOP_MARKET order with `closePosition=true`
7. Returns complete trade object with all order details

## Development

```bash
# Setup
poetry install

# Run tests
poetry run pytest

# Format code
poetry run black src/ tests/
```

## License

MIT License - see [LICENSE](LICENSE) file.