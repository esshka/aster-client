"""
API method implementations for Aster client.

Contains all API endpoint implementations organized by functional area.
Follows state-first design with pure functions for data transformation.
"""

import logging
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

from aiohttp import ClientSession

from .http_client import HttpClient
from .models.account import AccountInfo, AccountAsset, Position, Balance
from .models.market import MarkPrice, LeverageBracket
from .models.orders import OrderRequest, OrderResponse, PositionMode
from .utils import (
    clean_response_data,
    convert_timestamp_ms,
    format_with_precision,
    safe_get,
    validate_symbol,
    validate_quantity,
    validate_price,
)

logger = logging.getLogger(__name__)


class APIMethods:
    """Container for all API method implementations."""

    def __init__(self, http_client: HttpClient):
        """Initialize API methods with HTTP client."""
        self._http_client = http_client

    async def get_account_info(self, session: ClientSession) -> AccountInfo:
        """Get account information."""
        response = await self._http_client.request(
            session, "GET", "/account"
        )
        data = clean_response_data(response)

        return AccountInfo(
            account_id=safe_get(data, "account_id", ""),
            account_type=safe_get(data, "account_type", ""),
            status=safe_get(data, "status", ""),
            buying_power=Decimal(str(safe_get(data, "buying_power", 0))),
            day_trading_buying_power=Decimal(str(safe_get(data, "day_trading_buying_power", 0))),
            reg_t_buying_power=Decimal(str(safe_get(data, "reg_t_buying_power", 0))),
            cash=Decimal(str(safe_get(data, "cash", 0))),
            portfolio_value=Decimal(str(safe_get(data, "portfolio_value", 0))),
            equity=Decimal(str(safe_get(data, "equity", 0))),
            last_equity=Decimal(str(safe_get(data, "last_equity", 0))),
            multiplier=safe_get(data, "multiplier", "1"),
            initial_margin=Decimal(str(safe_get(data, "initial_margin", 0))),
            maintenance_margin=Decimal(str(safe_get(data, "maintenance_margin", 0))),
            long_market_value=Decimal(str(safe_get(data, "long_market_value", 0))),
            short_market_value=Decimal(str(safe_get(data, "short_market_value", 0))),
            accrued_fees=Decimal(str(safe_get(data, "accrued_fees", 0))),
            portfolio_equity=Decimal(str(safe_get(data, "portfolio_equity", 0))),
        )

    async def get_positions(self, session: ClientSession) -> List[Position]:
        """Get all open positions."""
        response = await self._http_client.request(
            session, "GET", "/positions"
        )
        data = clean_response_data(response)

        positions = []
        for pos_data in data if isinstance(data, list) else []:
            positions.append(Position(
                asset_id=safe_get(pos_data, "asset_id", ""),
                symbol=safe_get(pos_data, "symbol", ""),
                exchange=safe_get(pos_data, "exchange", ""),
                asset_class=safe_get(pos_data, "asset_class", ""),
                avg_entry_price=Decimal(str(safe_get(pos_data, "avg_entry_price", 0))),
                quantity=Decimal(str(safe_get(pos_data, "quantity", 0))),
                side=safe_get(pos_data, "side", ""),
                market_value=Decimal(str(safe_get(pos_data, "market_value", 0))),
                cost_basis=Decimal(str(safe_get(pos_data, "cost_basis", 0))),
                unrealized_pl=Decimal(str(safe_get(pos_data, "unrealized_pl", 0))),
                unrealized_plpc=Decimal(str(safe_get(pos_data, "unrealized_plpc", 0))),
                current_price=Decimal(str(safe_get(pos_data, "current_price", 0))),
                lastday_price=Decimal(str(safe_get(pos_data, "lastday_price", 0))),
                change_today=Decimal(str(safe_get(pos_data, "change_today", 0))),
            ))

        return positions

    async def get_balances(self, session: ClientSession) -> List[Balance]:
        """Get account balances."""
        response = await self._http_client.request(
            session, "GET", "/balances"
        )
        data = clean_response_data(response)

        balances = []
        for bal_data in data if isinstance(data, list) else []:
            balances.append(Balance(
                asset_id=safe_get(bal_data, "asset_id", ""),
                currency=safe_get(bal_data, "currency", ""),
                cash=Decimal(str(safe_get(bal_data, "cash", 0))),
                tradeable=safe_get(bal_data, "tradeable", False),
                pending_buy=Decimal(str(safe_get(bal_data, "pending_buy", 0))),
                pending_sell=Decimal(str(safe_get(bal_data, "pending_sell", 0))),
            ))

        return balances

    async def place_order(self, session: ClientSession, order: OrderRequest) -> OrderResponse:
        """Place a new order."""
        # Validate order data
        if not validate_symbol(order.symbol):
            raise ValueError(f"Invalid symbol: {order.symbol}")

        if not validate_quantity(order.quantity):
            raise ValueError(f"Invalid quantity: {order.quantity}")

        if order.price is not None and not validate_price(order.price):
            raise ValueError(f"Invalid price: {order.price}")

        # Prepare order data
        order_data = {
            "symbol": order.symbol,
            "side": order.side,
            "type": order.order_type,
            "quantity": str(order.quantity),
        }

        if order.price is not None:
            order_data["price"] = str(order.price)

        if order.time_in_force is not None:
            order_data["time_in_force"] = order.time_in_force

        if order.client_order_id is not None:
            order_data["client_order_id"] = order.client_order_id

        response = await self._http_client.request(
            session, "POST", "/orders", data=order_data
        )
        data = clean_response_data(response)

        return OrderResponse(
            order_id=safe_get(data, "order_id", ""),
            client_order_id=safe_get(data, "client_order_id"),
            symbol=safe_get(data, "symbol", ""),
            side=safe_get(data, "side", ""),
            order_type=safe_get(data, "type", ""),
            quantity=Decimal(str(safe_get(data, "quantity", 0))),
            price=Decimal(str(safe_get(data, "price", 0))) if safe_get(data, "price") else None,
            status=safe_get(data, "status", ""),
            filled_quantity=Decimal(str(safe_get(data, "filled_quantity", 0))),
            remaining_quantity=Decimal(str(safe_get(data, "remaining_quantity", 0))),
            average_price=Decimal(str(safe_get(data, "average_price", 0))) if safe_get(data, "average_price") else None,
            timestamp=convert_timestamp_ms(safe_get(data, "timestamp", 0)),
        )

    async def cancel_order(self, session: ClientSession, order_id: str) -> Dict[str, Any]:
        """Cancel an existing order."""
        if not order_id:
            raise ValueError("Order ID is required")

        response = await self._http_client.request(
            session, "DELETE", f"/orders/{order_id}"
        )
        return clean_response_data(response)

    async def get_order(self, session: ClientSession, order_id: str) -> Optional[OrderResponse]:
        """Get order by ID."""
        if not order_id:
            raise ValueError("Order ID is required")

        try:
            response = await self._http_client.request(
                session, "GET", f"/orders/{order_id}"
            )
            data = clean_response_data(response)

            return OrderResponse(
                order_id=safe_get(data, "order_id", ""),
                client_order_id=safe_get(data, "client_order_id"),
                symbol=safe_get(data, "symbol", ""),
                side=safe_get(data, "side", ""),
                order_type=safe_get(data, "type", ""),
                quantity=Decimal(str(safe_get(data, "quantity", 0))),
                price=Decimal(str(safe_get(data, "price", 0))) if safe_get(data, "price") else None,
                status=safe_get(data, "status", ""),
                filled_quantity=Decimal(str(safe_get(data, "filled_quantity", 0))),
                remaining_quantity=Decimal(str(safe_get(data, "remaining_quantity", 0))),
                average_price=Decimal(str(safe_get(data, "average_price", 0))) if safe_get(data, "average_price") else None,
                timestamp=convert_timestamp_ms(safe_get(data, "timestamp", 0)),
            )
        except (ValueError, TypeError, InvalidOperation) as e:
            logger.error(f"Failed to parse order data: {e}")
            return None
        except KeyError as e:
            logger.error(f"Missing required field in order data: {e}")
            return None

    async def get_orders(self, session: ClientSession, symbol: Optional[str] = None) -> List[OrderResponse]:
        """Get all orders, optionally filtered by symbol."""
        params = {}
        if symbol:
            if not validate_symbol(symbol):
                raise ValueError(f"Invalid symbol: {symbol}")
            params["symbol"] = symbol

        response = await self._http_client.request(
            session, "GET", "/orders", params=params
        )
        data = clean_response_data(response)

        orders = []
        for order_data in data if isinstance(data, list) else []:
            orders.append(OrderResponse(
                order_id=safe_get(order_data, "order_id", ""),
                client_order_id=safe_get(order_data, "client_order_id"),
                symbol=safe_get(order_data, "symbol", ""),
                side=safe_get(order_data, "side", ""),
                order_type=safe_get(order_data, "type", ""),
                quantity=Decimal(str(safe_get(order_data, "quantity", 0))),
                price=Decimal(str(safe_get(order_data, "price", 0))) if safe_get(order_data, "price") else None,
                status=safe_get(order_data, "status", ""),
                filled_quantity=Decimal(str(safe_get(order_data, "filled_quantity", 0))),
                remaining_quantity=Decimal(str(safe_get(order_data, "remaining_quantity", 0))),
                average_price=Decimal(str(safe_get(order_data, "average_price", 0))) if safe_get(order_data, "average_price") else None,
                timestamp=convert_timestamp_ms(safe_get(order_data, "timestamp", 0)),
            ))

        return orders

    
    async def get_mark_price(self, session: ClientSession, symbol: str) -> Optional[MarkPrice]:
        """Get mark price for symbol."""
        if not validate_symbol(symbol):
            raise ValueError(f"Invalid symbol: {symbol}")

        try:
            response = await self._http_client.request(
                session, "GET", f"/market/{symbol}/mark_price"
            )
            data = clean_response_data(response)

            return MarkPrice(
                symbol=safe_get(data, "symbol", ""),
                mark_price=Decimal(str(safe_get(data, "mark_price", 0))),
                timestamp=convert_timestamp_ms(safe_get(data, "timestamp", 0)),
                funding_rate=Decimal(str(safe_get(data, "funding_rate", 0))) if safe_get(data, "funding_rate") else None,
                next_funding_time=convert_timestamp_ms(safe_get(data, "next_funding_time")),
            )
        except (ValueError, TypeError, InvalidOperation) as e:
            logger.error(f"Failed to parse mark price data: {e}")
            return None
        except KeyError as e:
            logger.error(f"Missing required field in mark price data: {e}")
            return None