# Aster Client Examples

This directory contains practical examples demonstrating how to use the aster-client library for cryptocurrency trading.

## Setup

Before running any examples, you need to:

### 1. Install Dependencies

#### Option 1: Using Poetry (Recommended)
```bash
# Install dependencies
poetry install

# Run examples
poetry run python examples/btc_buy_limit_order.py
```

#### Option 2: Install in Development Mode
```bash
# Install the package in development mode
pip install -e .

# Run examples
python examples/btc_buy_limit_order.py
```

### 2. Set Up API Credentials

You need to set environment variables for your API credentials:

#### Required Environment Variables
- `ASTER_API_KEY`: Your API key for accessing the exchange
- `ASTER_API_SECRET`: Your API secret for request signing

#### Setup Methods

**Option 1: Export in Terminal (Linux/Mac)**
```bash
export ASTER_API_KEY=your_actual_api_key_here
export ASTER_API_SECRET=your_actual_api_secret_here
```

**Option 2: Set in PowerShell (Windows)**
```powershell
$env:ASTER_API_KEY='your_actual_api_key_here'
$env:ASTER_API_SECRET='your_actual_api_secret_here'
```

**Option 3: Create .env File**
```env
ASTER_API_KEY=your_actual_api_key_here
ASTER_API_SECRET=your_actual_api_secret_here
```

⚠️ **Security Warning**: Never commit your API keys to version control!

## Examples

### [btc_buy_limit_order.py](./btc_buy_limit_order.py)
Demonstrates how to:
- Create an authenticated account client using environment variables
- Place a BUY limit order for BTCUSDT at $80,000
- Handle order placement and monitoring

**Key Features:**
- Environment variable configuration
- Proper error handling and logging
- Async/await patterns with context managers
- Account information retrieval
- Order status monitoring
- Simulation mode for testing

**Usage:**
```bash
# Make sure environment variables are set
poetry run python examples/btc_buy_limit_order.py
# OR after pip install -e .
python examples/btc_buy_limit_order.py
```

## Best Practices

### 1. Always Use Decimal for Financial Values
```python
from decimal import Decimal

price = Decimal("80000.00")  # ✅ Correct
quantity = Decimal("0.001")  # ✅ Correct
# price = 80000.00          # ❌ Incorrect - uses float
```

### 2. Use Context Managers for Resource Management
```python
async with client:
    # Your trading operations here
    pass
# Client automatically closed
```

### 3. Start with Simulation Mode
```python
client = AsterClient.from_env(simulation=True)  # Safe for testing
# client = AsterClient.from_env(simulation=False)  # Live trading
```

### 4. Proper Error Handling
```python
try:
    order_result = await client.place_order(order)
    logger.info(f"Order placed: {order_result.order_id}")
except Exception as e:
    logger.error(f"Order failed: {e}")
```

### 5. Monitor Order Status
```python
# Check order after placement
order_status = await client.get_order(order_result.order_id)
if order_status.status == "filled":
    print("Order completely filled")
```

## Common Patterns

### Client Creation Methods

```python
# Method 1: From environment variables (recommended)
client = AsterClient.from_env(simulation=True)

# Method 2: Using factory function
client = AsterClient.create_aster_client(
    api_key="your_key",
    api_secret="your_secret",
    simulation=True
)

# Method 3: With custom configuration
from aster_client.models.config import ConnectionConfig
config = ConnectionConfig(
    api_key="your_key",
    api_secret="your_secret",
    simulation=True,
    timeout=30.0
)
client = AsterClient(config)
```

### Order Creation
```python
from aster_client.models.orders import OrderRequest, OrderSide, OrderType, TimeInForce

order = OrderRequest(
    symbol="BTCUSDT",
    side=OrderSide.BUY,
    order_type=OrderType.LIMIT,
    quantity=Decimal("0.001"),
    price=Decimal("80000.00"),
    time_in_force=TimeInForce.GTC,
    client_order_id="my_custom_order_id"
)
```

## Getting Help

- Check the [main README](../README.md) for installation instructions
- Review the test files for additional usage patterns
- Consult the API documentation for complete method references

## Safety Notes

- Always test with `simulation=True` first
- Never commit API credentials to version control
- Use appropriate position sizing
- Monitor your orders after placement
- Keep your API keys secure and rotate them regularly