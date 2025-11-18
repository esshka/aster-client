"""
Utility functions for Aster client.

Helper functions and utilities following functional programming principles.
"""

from decimal import Decimal, ROUND_DOWN
from typing import Any, Dict, List, Optional, Union


def format_with_precision(value: Union[Decimal, float, str], precision: int) -> Decimal:
    """Format a numeric value with specified precision."""
    decimal_value = Decimal(str(value))
    quantizer = Decimal(f"1e-{precision}")
    return decimal_value.quantize(quantizer, rounding=ROUND_DOWN)


def validate_symbol(symbol: str) -> bool:
    """Validate symbol format."""
    if not symbol or not isinstance(symbol, str):
        return False

    # Basic validation - adjust according to Aster's symbol requirements
    return len(symbol) >= 1 and len(symbol) <= 20 and symbol.replace("-", "").replace("_", "").isalnum()


def validate_quantity(quantity: Union[Decimal, float, str]) -> bool:
    """Validate quantity is positive."""
    try:
        decimal_quantity = Decimal(str(quantity))
        return decimal_quantity > 0
    except (ValueError, TypeError):
        return False


def validate_price(price: Union[Decimal, float, str]) -> bool:
    """Validate price is positive."""
    try:
        decimal_price = Decimal(str(price))
        return decimal_price > 0
    except (ValueError, TypeError):
        return False


def sanitize_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """Remove None values and empty strings from dictionary."""
    return {
        key: value for key, value in data.items()
        if value is not None and value != ""
    }


def deep_merge_dicts(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Deep merge two dictionaries."""
    result = base.copy()

    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge_dicts(result[key], value)
        else:
            result[key] = value

    return result


def chunk_list(items: List[Any], chunk_size: int) -> List[List[Any]]:
    """Split a list into chunks of specified size."""
    if chunk_size <= 0:
        raise ValueError("Chunk size must be positive")

    return [items[i:i + chunk_size] for i in range(0, len(items), chunk_size)]


def safe_get(data: Dict[str, Any], path: str, default: Any = None) -> Any:
    """Safely get nested dictionary values using dot notation."""
    keys = path.split(".")
    current = data

    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return default

    return current


def convert_timestamp_ms(timestamp: Union[int, float, None]) -> Optional[int]:
    """Convert timestamp to milliseconds if needed."""
    if timestamp is None:
        return None
    if timestamp > 1e10:  # Already in milliseconds
        return int(timestamp)
    else:  # Convert from seconds to milliseconds
        return int(float(timestamp) * 1000)


def validate_url(url: str) -> bool:
    """Validate URL format."""
    if not url or not isinstance(url, str):
        return False
    return url.startswith(("http://", "https://")) and "." in url


def order_side_to_string(side: Union[str, int]) -> str:
    """Convert order side to standardized string."""
    if isinstance(side, str):
        return side.lower()
    elif isinstance(side, int):
        return "buy" if side == 1 else "sell"
    else:
        raise ValueError(f"Invalid order side: {side}")


def order_type_to_string(order_type: Union[str, int]) -> str:
    """Convert order type to standardized string."""
    if isinstance(order_type, str):
        return order_type.lower()
    elif isinstance(order_type, int):
        type_mapping = {1: "limit", 2: "market", 3: "stop", 4: "stop_limit"}
        if order_type in type_mapping:
            return type_mapping[order_type]
        else:
            raise ValueError(f"Invalid order type: {order_type}")
    else:
        raise ValueError(f"Invalid order type: {order_type}")


def clean_response_data(data: Any) -> Any:
    """Recursively clean API response data."""
    if isinstance(data, dict):
        return {k: clean_response_data(v) for k, v in data.items() if v is not None}
    elif isinstance(data, list):
        return [clean_response_data(item) for item in data]
    elif isinstance(data, (int, float, str, bool)):
        return data
    else:
        return str(data)