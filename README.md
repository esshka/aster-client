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
- `cancel_order(order_id)` - Cancel existing order
- `get_orders(symbol)` - Get all orders for symbol
- `get_order(order_id)` - Get specific order details

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