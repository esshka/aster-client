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
            session, "GET", "/fapi/v4/account"
        )
        data = clean_response_data(response)

        return AccountInfo(
            account_id=safe_get(data, "account_id", ""),
            account_type=safe_get(data, "account_type", ""),
            status=safe_get(data, "status", ""),
            buying_power=Decimal(str(safe_get(data, "availableBalance", 0))),
            day_trading_buying_power=Decimal(str(safe_get(data, "day_trading_buying_power", 0))),
            reg_t_buying_power=Decimal(str(safe_get(data, "reg_t_buying_power", 0))),
            cash=Decimal(str(safe_get(data, "totalWalletBalance", 0))),
            portfolio_value=Decimal(str(safe_get(data, "totalMarginBalance", 0))),
            equity=Decimal(str(safe_get(data, "totalMarginBalance", 0))),
            last_equity=Decimal(str(safe_get(data, "last_equity", 0))),
            multiplier=safe_get(data, "multiplier", "1"),
            initial_margin=Decimal(str(safe_get(data, "totalInitialMargin", 0))),
            maintenance_margin=Decimal(str(safe_get(data, "totalMaintMargin", 0))),
            long_market_value=Decimal(str(safe_get(data, "long_market_value", 0))),
            short_market_value=Decimal(str(safe_get(data, "short_market_value", 0))),
            accrued_fees=Decimal(str(safe_get(data, "accrued_fees", 0))),
            portfolio_equity=Decimal(str(safe_get(data, "totalMarginBalance", 0))),
        )

    async def get_positions(self, session: ClientSession) -> List[Position]:
        """Get all open positions."""
        response = await self._http_client.request(
            session, "GET", "/fapi/v4/account"
        )
        data = clean_response_data(response)
        positions_data = safe_get(data, "positions", [])

        positions = []
        for pos_data in positions_data:
            # Calculate PnL % if possible
            unrealized_pl = Decimal(str(safe_get(pos_data, "unrealizedProfit", 0)))
            initial_margin = Decimal(str(safe_get(pos_data, "positionInitialMargin", 0)))
            unrealized_plpc = Decimal("0")
            if initial_margin > 0:
                unrealized_plpc = (unrealized_pl / initial_margin) * 100

            positions.append(Position(
                asset_id=safe_get(pos_data, "symbol", ""),
                symbol=safe_get(pos_data, "symbol", ""),
                exchange="Aster",
                asset_class="UsdtFutures",
                avg_entry_price=Decimal(str(safe_get(pos_data, "entryPrice", 0))),
                quantity=Decimal(str(safe_get(pos_data, "positionAmt", 0))),
                side=safe_get(pos_data, "positionSide", ""),
                market_value=Decimal(str(safe_get(pos_data, "notional", 0))),
                cost_basis=initial_margin,
                unrealized_pl=unrealized_pl,
                unrealized_plpc=unrealized_plpc,
                current_price=Decimal("0"), # Not available in account info
                lastday_price=Decimal("0"),
                change_today=Decimal("0"),
            ))

        return positions

    async def get_balances(self, session: ClientSession) -> List[Balance]:
        """Get account balances."""
        response = await self._http_client.request(
            session, "GET", "/fapi/v4/account"
        )
        data = clean_response_data(response)
        assets_data = safe_get(data, "assets", [])

        balances = []
        for bal_data in assets_data:
            balances.append(Balance(
                asset_id=safe_get(bal_data, "asset", ""),
                currency=safe_get(bal_data, "asset", ""),
                cash=Decimal(str(safe_get(bal_data, "walletBalance", 0))),
                tradeable=safe_get(bal_data, "marginAvailable", False),
                pending_buy=Decimal("0"),
                pending_sell=Decimal("0"),
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
            session, "POST", "/fapi/v1/orders", data=order_data
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
            timestamp=convert_timestamp_ms(safe_get(data, "timestamp", 0)) or 0,
        )

    async def cancel_order(self, session: ClientSession, order_id: str) -> Dict[str, Any]:
        """Cancel an existing order."""
        if not order_id:
            raise ValueError("Order ID is required")

        response = await self._http_client.request(
            session, "DELETE", f"/fapi/v1/orders/{order_id}"
        )
        return clean_response_data(response)

    async def get_order(self, session: ClientSession, order_id: str) -> Optional[OrderResponse]:
        """Get order by ID."""
        if not order_id:
            raise ValueError("Order ID is required")

        try:
            response = await self._http_client.request(
                session, "GET", f"/fapi/v1/orders/{order_id}"
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
                timestamp=convert_timestamp_ms(safe_get(data, "timestamp", 0)) or 0,
            )
        except (ValueError, TypeError, InvalidOperation) as e:
            logger.error(f"Failed to parse order data: {e}")
            return None
        except KeyError as e:
            logger.error(f"Missing required field in order data: {e}")
            return None

    async def get_orders(self, session: ClientSession, symbol: Optional[str] = None) -> List[OrderResponse]:
        """Get all open orders, optionally filtered by symbol."""
        params = {}
        if symbol:
            if not validate_symbol(symbol):
                raise ValueError(f"Invalid symbol: {symbol}")
            params["symbol"] = symbol

        response = await self._http_client.request(
            session, "GET", "/fapi/v1/openOrders", params=params
        )
        data = clean_response_data(response)

        orders = []
        for order_data in data if isinstance(data, list) else []:
            # Calculate remaining quantity
            orig_qty = Decimal(str(safe_get(order_data, "origQty", 0)))
            executed_qty = Decimal(str(safe_get(order_data, "executedQty", 0)))
            remaining_qty = orig_qty - executed_qty

            orders.append(OrderResponse(
                order_id=str(safe_get(order_data, "orderId", "")),
                client_order_id=safe_get(order_data, "clientOrderId"),
                symbol=safe_get(order_data, "symbol", ""),
                side=safe_get(order_data, "side", ""),
                order_type=safe_get(order_data, "type", ""),
                quantity=orig_qty,
                price=Decimal(str(safe_get(order_data, "price", 0))) if safe_get(order_data, "price") else None,
                status=safe_get(order_data, "status", ""),
                filled_quantity=executed_qty,
                remaining_quantity=remaining_qty,
                average_price=Decimal(str(safe_get(order_data, "avgPrice", 0))) if safe_get(order_data, "avgPrice") else None,
                timestamp=convert_timestamp_ms(safe_get(order_data, "time", 0)) or 0,
            ))

        return orders

    
    async def get_mark_price(self, session: ClientSession, symbol: str) -> Optional[MarkPrice]:
        """Get mark price for symbol."""
        if not validate_symbol(symbol):
            raise ValueError(f"Invalid symbol: {symbol}")

        try:
            response = await self._http_client.request(
                session, "GET", f"/fapi/v1/premiumIndex"
            )
            data = clean_response_data(response)

            return MarkPrice(
                symbol=safe_get(data, "symbol", ""),
                mark_price=Decimal(str(safe_get(data, "mark_price", 0))),
                timestamp=convert_timestamp_ms(safe_get(data, "timestamp", 0)) or 0,
                funding_rate=Decimal(str(safe_get(data, "funding_rate", 0))) if safe_get(data, "funding_rate") else None,
                next_funding_time=convert_timestamp_ms(safe_get(data, "next_funding_time")),
            )
        except (ValueError, TypeError, InvalidOperation) as e:
            logger.error(f"Failed to parse mark price data: {e}")
            return None
        except KeyError as e:
            logger.error(f"Missing required field in mark price data: {e}")
            return None