# AccountPool - Multi-Account Management

## Overview

The **AccountPool** module provides a powerful abstraction for managing multiple trading accounts simultaneously. It enables parallel execution of operations across all accounts using `asyncio.gather()`, making it ideal for managing portfolio-wide actions efficiently.

## Key Features

- **Parallel Execution**: Execute operations across all accounts simultaneously
- **Error Isolation**: Individual account failures don't affect other accounts
- **Flexible Configuration**: Support for per-account customization
- **Built-in Methods**: Pre-built methods for common operations
- **Custom Operations**: Execute any async function across all accounts

## Quick Start

```python
from aster_client import AccountPool, AccountConfig

# Define accounts
accounts = [
    AccountConfig(
        id="account1",
        api_key="your_api_key_1",
        api_secret="your_api_secret_1"
    ),
    AccountConfig(
        id="account2",
        api_key="your_api_key_2",
        api_secret="your_api_secret_2"
    ),
]

# Use the pool
async with AccountPool(accounts) as pool:
    # Get positions from all accounts
    results = await pool.get_positions_parallel()
    
    for result in results:
        if result.success:
            print(f"{result.account_id}: {len(result.result)} positions")
        else:
            print(f"{result.account_id} failed: {result.error}")
```

## Configuration

### AccountConfig

Configuration for a single account in the pool.

```python
@dataclass
class AccountConfig:
    id: str                           # Unique identifier
    api_key: str                      # API key
    api_secret: str                   # API secret
    base_url: Optional[str] = None    # Custom API URL
    timeout: Optional[float] = None   # Request timeout
    simulation: bool = False          # Simulation mode
    recv_window: int = 5000           # Receive window (ms)
```

### Loading from YAML

```python
import yaml
from pathlib import Path

def load_accounts_from_config(config_path: str) -> list[AccountConfig]:
    """Load account configurations from YAML file."""
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    return [
        AccountConfig(
            id=acc['id'],
            api_key=acc['api_key'],
            api_secret=acc['api_secret'],
            simulation=acc.get('simulation', False),
        )
        for acc in config['accounts']
    ]

# Usage
accounts = load_accounts_from_config('accounts_config.yml')
```

**Example `accounts_config.yml`:**

```yaml
accounts:
  - id: main_account
    api_key: "your_main_api_key"
    api_secret: "your_main_api_secret"
    simulation: false
    recv_window: 10000
  
  - id: test_account
    api_key: "your_test_api_key"
    api_secret: "your_test_api_secret"
    simulation: true
```

## Built-in Methods

### Account Information

#### `get_accounts_info_parallel()`

Get account information for all accounts.

```python
async with AccountPool(accounts) as pool:
    results = await pool.get_accounts_info_parallel()
    
    for result in results:
        if result.success:
            info = result.result
            print(f"{result.account_id}:")
            print(f"  Cash: ${info.cash}")
            print(f"  Buying Power: ${info.buying_power}")
```

### Positions

#### `get_positions_parallel()`

Get open positions for all accounts.

```python
async with AccountPool(accounts) as pool:
    results = await pool.get_positions_parallel()
    
    for result in results:
        if result.success:
            positions = result.result
            # Filter non-empty positions
            active = [p for p in positions if p.quantity != Decimal("0")]
            print(f"{result.account_id}: {len(active)} active positions")
```

### Balances

#### `get_balances_parallel()`

Get balance information for all accounts.

```python
async with AccountPool(accounts) as pool:
    results = await pool.get_balances_parallel()
    
    for result in results:
        if result.success:
            balances = result.result
            print(f"{result.account_id}: {len(balances)} assets")
```

### Orders

#### `get_orders_parallel(symbol=None)`

Get active orders for all accounts, optionally filtered by symbol.

```python
async with AccountPool(accounts) as pool:
    # Get all active orders
    results = await pool.get_orders_parallel()
    
    for result in results:
        if result.success:
            orders = result.result
            print(f"{result.account_id}: {len(orders)} active orders")
    
    # Get only BTCUSDT orders
    btc_results = await pool.get_orders_parallel(symbol="BTCUSDT")
    
    for result in btc_results:
        if result.success:
            orders = result.result
            for order in orders:
                print(f"  {order.side} {order.quantity} @ ${order.price}")
```

**Parameters:**
- `symbol` (Optional[str]): Filter orders by symbol (e.g., "BTCUSDT")

**Returns:**
- `List[AccountResult[List[OrderResponse]]]`: Results for each account

### Order Placement

#### `place_orders_parallel(orders)`

Place orders across all accounts.

```python
from aster_client.models import OrderRequest
from decimal import Decimal

# Same order for all accounts
order = OrderRequest(
    symbol="BTCUSDT",
    side="buy",
    order_type="limit",
    quantity=Decimal("0.001"),
    price=Decimal("45000")
)

async with AccountPool(accounts) as pool:
    results = await pool.place_orders_parallel(order)
    
    for result in results:
        if result.success:
            print(f"{result.account_id}: Order placed - {result.result.order_id}")

# Different orders per account
orders = [
    OrderRequest(symbol="BTCUSDT", side="buy", ...),
    OrderRequest(symbol="ETHUSDT", side="buy", ...),
]

results = await pool.place_orders_parallel(orders)
```

#### `place_bbo_orders_parallel(...)`

Place BBO (Best Bid/Offer) orders across all accounts.

```python
async with AccountPool(accounts) as pool:
    results = await pool.place_bbo_orders_parallel(
        symbol="BTCUSDT",
        side="buy",
        quantity=Decimal("0.001"),  # Same for all
        market_price=Decimal("45000"),
        tick_size=Decimal("0.1"),
        ticks_distance=2  # 2 ticks from market
    )
```

**Different quantities per account:**

```python
quantities = [Decimal("0.001"), Decimal("0.002")]

results = await pool.place_bbo_orders_parallel(
    symbol="BTCUSDT",
    side="buy",
    quantity=quantities,  # List of quantities
    market_price=Decimal("45000"),
    tick_size=Decimal("0.1")
)
```

### Order Cancellation

#### `cancel_orders_parallel(symbol, order_ids=None, client_order_ids=None)`

Cancel orders across all accounts.

```python
# Cancel specific orders
order_ids = [123456, 789012]

async with AccountPool(accounts) as pool:
    results = await pool.cancel_orders_parallel(
        symbol="BTCUSDT",
        order_ids=order_ids
    )
```

## Custom Parallel Execution

### `execute_parallel(func)`

Execute any custom async function across all accounts.

```python
async def get_account_summary(client):
    """Custom function to get account summary."""
    info = await client.get_account_info()
    positions = await client.get_positions()
    orders = await client.get_orders()
    
    return {
        "balance": info.cash,
        "positions": len([p for p in positions if p.quantity != 0]),
        "active_orders": len(orders)
    }

async with AccountPool(accounts) as pool:
    results = await pool.execute_parallel(get_account_summary)
    
    for result in results:
        if result.success:
            data = result.result
            print(f"{result.account_id}:")
            print(f"  Balance: ${data['balance']}")
            print(f"  Positions: {data['positions']}")
            print(f"  Orders: {data['active_orders']}")
```

## AccountResult Object

Each parallel operation returns a list of `AccountResult` objects.

```python
@dataclass
class AccountResult[T]:
    account_id: str           # Account identifier
    success: bool             # Operation success status
    result: Optional[T]       # Result data (if successful)
    error: Optional[Exception]  # Exception (if failed)
```

### Handling Results

```python
results = await pool.get_positions_parallel()

# Filter successful results
successful = [r for r in results if r.success]
failed = [r for r in results if not r.success]

print(f"Successful: {len(successful)}")
print(f"Failed: {len(failed)}")

# Process errors
for result in failed:
    print(f"{result.account_id} error: {result.error}")
```

## Advanced Usage

### Portfolio-Wide Position Monitoring

```python
async def monitor_portfolio(pool: AccountPool):
    """Monitor all positions across accounts."""
    results = await pool.get_positions_parallel()
    
    total_positions = 0
    total_value = Decimal("0")
    
    for result in results:
        if result.success:
            positions = result.result
            active = [p for p in positions if p.quantity != Decimal("0")]
            
            total_positions += len(active)
            
            for pos in active:
                total_value += abs(pos.market_value or Decimal("0"))
                
                print(f"{result.account_id} - {pos.symbol}:")
                print(f"  Size: {pos.quantity}")
                print(f"  Value: ${pos.market_value}")
                print(f"  PnL: ${pos.unrealized_pl} ({pos.unrealized_plpc:.2%})")
    
    print(f"\nTotal Positions: {total_positions}")
    print(f"Total Value: ${total_value:,.2f}")

# Usage
async with AccountPool(accounts) as pool:
    await monitor_portfolio(pool)
```

### Coordinated Trade Execution

```python
async def execute_coordinated_trades(
    pool: AccountPool,
    symbol: str,
    side: str,
    total_usdt: Decimal,
    price: Decimal
):
    """Execute trades across all accounts with proportional sizing."""
    
    # Get account balances
    balance_results = await pool.get_accounts_info_parallel()
    
    # Calculate proportional quantities
    total_buying_power = sum(
        r.result.buying_power for r in balance_results if r.success
    )
    
    quantities = []
    for result in balance_results:
        if result.success:
            proportion = result.result.buying_power / total_buying_power
            account_qty = (total_usdt * proportion) / price
            quantities.append(account_qty)
    
    # Place orders
    order_results = await pool.place_bbo_orders_parallel(
        symbol=symbol,
        side=side,
        quantity=quantities,
        market_price=price,
        tick_size=Decimal("0.1")
    )
    
    # Report results
    for result in order_results:
        if result.success:
            print(f"{result.account_id}: Order placed")
        else:
            print(f"{result.account_id}: Failed - {result.error}")
```

### Active Order Management

```python
async def cancel_old_orders(pool: AccountPool, symbol: str):
    """Cancel all orders older than 5 minutes for a symbol."""
    import time
    
    # Get all orders
    results = await pool.get_orders_parallel(symbol=symbol)
    
    order_ids_per_account = []
    
    for result in results:
        if result.success:
            old_orders = [
                order.order_id
                for order in result.result
                if (time.time() * 1000 - order.time) > 300000  # 5 min
            ]
            order_ids_per_account.append(
                old_orders[0] if old_orders else None
            )
    
    # Cancel old orders
    if any(order_ids_per_account):
        cancel_results = await pool.cancel_orders_parallel(
            symbol=symbol,
            order_ids=order_ids_per_account
        )
        
        cancelled = sum(1 for r in cancel_results if r.success)
        print(f"Cancelled {cancelled} old orders")
```

## Error Handling

```python
async with AccountPool(accounts) as pool:
    try:
        results = await pool.get_positions_parallel()
        
        # Check for any failures
        failures = [r for r in results if not r.success]
        
        if failures:
            print(f"⚠️  {len(failures)} account(s) failed:")
            for failure in failures:
                print(f"  {failure.account_id}: {failure.error}")
        
        # Process successful results
        for result in results:
            if result.success:
                # Process result
                pass
    
    except Exception as e:
        print(f"Pool operation failed: {e}")
```

## Best Practices

### 1. **Use Context Manager**

Always use `async with` to ensure proper cleanup:

```python
# ✅ Good
async with AccountPool(accounts) as pool:
    results = await pool.get_positions_parallel()

# ❌ Bad
pool = AccountPool(accounts)
results = await pool.get_positions_parallel()
# Resources not cleaned up!
```

### 2. **Handle Individual Failures**

Always check `success` on each result:

```python
for result in results:
    if result.success:
        # Process result
        data = result.result
    else:
        # Log error
        logger.error(f"{result.account_id}: {result.error}")
```

### 3. **Use Symbol Filters**

When monitoring specific symbols, use the symbol filter to reduce API calls:

```python
# ✅ Good - Filter on server side
results = await pool.get_orders_parallel(symbol="BTCUSDT")

# ❌ Less efficient - Get all, filter locally
results = await pool.get_orders_parallel()
btc_orders = [
    order for r in results if r.success
    for order in r.result if order.symbol == "BTCUSDT"
]
```

### 4. **Aggregate Data Safely**

Handle missing data when aggregating:

```python
total = Decimal("0")
for result in results:
    if result.success:
        positions = result.result
        for pos in positions:
            if pos.market_value:  # Check for None
                total += abs(pos.market_value)
```

### 5. **Logging and Monitoring**

Set up proper logging for multi-account operations:

```python
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

# AccountPool will log operations automatically
async with AccountPool(accounts) as pool:
    # Logged: "AccountPool initialized with N accounts"
    results = await pool.get_positions_parallel()
    # Logged: Individual successes/failures
```

## Examples

See the `examples/` directory for complete working examples:

- **`parallel_trades_example.py`** - Execute trades across multiple accounts
- **`parallel_orders_example.py`** - Parallel order management
- **`check_active_orders.py`** - Monitor active orders across accounts
- **`multi_account_info.py`** - Display account information

## See Also

- [Trades Module Documentation](./trades.md)
- [BBO Orders Documentation](./bbo.md)
- [API Models](../src/aster_client/models/)
