# -*- coding: utf-8 -*-
"""
Aster Public Market Data Client

This module provides a lightweight client for accessing public market data
from the Aster perpetual trading platform without requiring authentication.
"""

import asyncio
import logging
import aiohttp
from aiohttp import ClientSession, ClientError, ClientTimeout
from typing import Dict, Any, Optional
from decimal import Decimal

from .models.market import (
    SymbolInfo,
    PriceFilter,
    LotSizeFilter,
    MarketLotSizeFilter,
    MaxNumOrdersFilter,
    MaxNumAlgoOrdersFilter,
    PercentPriceFilter,
    MinNotionalFilter,
)
from .utils import validate_symbol, validate_url


logger = logging.getLogger(__name__)


class AsterPublicClient:
    """
    A lightweight client for accessing public market data from Aster exchange
    without requiring authentication.
    """

    def __init__(self, base_url: str = "https://fapi.asterdex.com"):
        """
        Initialize the public Aster client.

        Args:
            base_url: Base URL for the API
        """
        if not validate_url(base_url):
            raise ValueError("Base URL must be a valid HTTP/HTTPS URL")

        self.base_url = base_url.rstrip("/")

        # API endpoint paths for public data
        self.endpoints = {
            "ticker": "/fapi/v1/premiumIndex",
            "all_mark_prices": "/fapi/v1/premiumIndex",
            "exchange_info": "/fapi/v1/exchangeInfo",
            "symbol_info": "/fapi/v1/exchangeInfo",
        }

        # Initialize session (will be created lazily when needed)
        self._session = None
        self._timeout = ClientTimeout(total=30)

        logger.info("AsterPublicClient initialized for public market data access")

    async def _get_session(self) -> ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = ClientSession(timeout=self._timeout)
        return self._session

    async def close(self):
        """Close the aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Make HTTP request to the API.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            params: Request parameters

        Returns:
            Response data as dictionary
        """
        url = f"{self.base_url}{endpoint}"
        session = await self._get_session()

        try:
            async with session.request(
                method=method,
                url=url,
                params=params,
            ) as response:
                response.raise_for_status()
                return await response.json()
        except asyncio.TimeoutError:
            logger.error("Request timeout")
            raise Exception("Request timeout")
        except aiohttp.ClientConnectorError:
            logger.error("Connection error")
            raise Exception("Connection error")
        except ClientError as e:
            logger.error(f"Request failed: {e}")
            raise
        except Exception as e:
            logger.error(f"Request failed: {e}")
            raise

    async def get_ticker(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get mark price ticker for a specific symbol.

        Args:
            symbol: Trading symbol (e.g., 'BTCUSDT')

        Returns:
            Ticker data with mark price information
        """
        if not validate_symbol(symbol):
            raise ValueError(f"Invalid symbol format: {symbol}")

        params = {"symbol": symbol}
        endpoint = self.endpoints["ticker"]

        try:
            response = await self._make_request("GET", endpoint, params)
            return response
        except Exception as e:
            logger.error(f"Failed to get ticker for {symbol}: {e}")
            return None

    async def get_all_mark_prices(self) -> Optional[list]:
        """
        Get mark prices for all symbols.

        Returns:
            List of mark price data for all symbols
        """
        endpoint = self.endpoints["all_mark_prices"]

        try:
            response = await self._make_request("GET", endpoint)
            return response
        except Exception as e:
            logger.error(f"Failed to get all mark prices: {e}")
            return None

    async def get_exchange_info(self) -> Optional[Dict[str, Any]]:
        """
        Get exchange information including symbol specifications.

        Returns:
            Exchange information dictionary
        """
        endpoint = self.endpoints["exchange_info"]

        try:
            response = await self._make_request("GET", endpoint)
            return response
        except Exception as e:
            logger.error(f"Failed to get exchange info: {e}")
            return None

    async def get_symbol_info(self, symbol: str) -> Optional[SymbolInfo]:
        """
        Get information for a specific symbol.

        Args:
            symbol: Trading symbol

        Returns:
            Symbol information object
        """
        if not validate_symbol(symbol):
            raise ValueError(f"Invalid symbol format: {symbol}")

        exchange_info = await self.get_exchange_info()
        if not exchange_info or "symbols" not in exchange_info:
            return None

        for symbol_data in exchange_info["symbols"]:
            if symbol_data["symbol"] == symbol:
                try:
                    # Parse filters
                    price_filter = None
                    lot_size_filter = None
                    market_lot_size_filter = None
                    max_num_orders_filter = None
                    max_num_algo_orders_filter = None
                    percent_price_filter = None
                    min_notional_filter = None

                    for filter_data in symbol_data.get("filters", []):
                        filter_type = filter_data.get("filterType")
                        if filter_type == "PRICE_FILTER":
                            price_filter = PriceFilter(
                                min_price=Decimal(str(filter_data.get("minPrice", 0))),
                                max_price=Decimal(str(filter_data.get("maxPrice", 0))),
                                tick_size=Decimal(str(filter_data.get("tickSize", 0))),
                            )
                        elif filter_type == "LOT_SIZE":
                            lot_size_filter = LotSizeFilter(
                                min_qty=Decimal(str(filter_data.get("minQty", 0))),
                                max_qty=Decimal(str(filter_data.get("maxQty", 0))),
                                step_size=Decimal(str(filter_data.get("stepSize", 0))),
                            )
                        elif filter_type == "MARKET_LOT_SIZE":
                            market_lot_size_filter = MarketLotSizeFilter(
                                min_qty=Decimal(str(filter_data.get("minQty", 0))),
                                max_qty=Decimal(str(filter_data.get("maxQty", 0))),
                                step_size=Decimal(str(filter_data.get("stepSize", 0))),
                            )
                        elif filter_type == "MAX_NUM_ORDERS":
                            max_num_orders_filter = MaxNumOrdersFilter(
                                limit=int(filter_data.get("limit", 0))
                            )
                        elif filter_type == "MAX_NUM_ALGO_ORDERS":
                            max_num_algo_orders_filter = MaxNumAlgoOrdersFilter(
                                limit=int(filter_data.get("limit", 0))
                            )
                        elif filter_type == "PERCENT_PRICE":
                            percent_price_filter = PercentPriceFilter(
                                multiplier_up=Decimal(str(filter_data.get("multiplierUp", 0))),
                                multiplier_down=Decimal(str(filter_data.get("multiplierDown", 0))),
                                multiplier_decimal=int(filter_data.get("multiplierDecimal", 0)),
                            )
                        elif filter_type == "MIN_NOTIONAL":
                            min_notional_filter = MinNotionalFilter(
                                notional=Decimal(str(filter_data.get("notional", 0)))
                            )

                    return SymbolInfo(
                        symbol=symbol_data.get("symbol", ""),
                        base_asset=symbol_data.get("base_asset", ""),
                        quote_asset=symbol_data.get("quote_asset", ""),
                        status=symbol_data.get("status", ""),
                        price_precision=symbol_data.get("price_precision", 0),
                        quantity_precision=symbol_data.get("quantity_precision", 0),
                        min_quantity=Decimal(str(symbol_data.get("min_quantity", 0))),
                        max_quantity=Decimal(str(symbol_data.get("max_quantity", 0))),
                        min_notional=Decimal(str(symbol_data.get("min_notional", 0))),
                        max_notional=Decimal(str(symbol_data.get("max_notional", 0))),
                        tick_size=Decimal(str(symbol_data.get("tick_size", 0))),
                        step_size=Decimal(str(symbol_data.get("step_size", 0))),
                        contract_type=symbol_data.get("contract_type"),
                        delivery_date=symbol_data.get("delivery_date"),
                        price_filter=price_filter,
                        lot_size_filter=lot_size_filter,
                        market_lot_size_filter=market_lot_size_filter,
                        max_num_orders_filter=max_num_orders_filter,
                        max_num_algo_orders_filter=max_num_algo_orders_filter,
                        percent_price_filter=percent_price_filter,
                        min_notional_filter=min_notional_filter,
                    )
                except (ValueError, TypeError) as e:
                    logger.error(f"Failed to parse symbol info data: {e}")
                    return None

        return None
    

if __name__ == "__main__":
    # Example usage
    async def main():
        symbol = "BTCUSDT"
        async with AsterPublicClient() as client:
            ticker = await client.get_ticker(symbol)
            print(ticker)
            mark_prices = await client.get_all_mark_prices()
            print(mark_prices)
            symbol_info = await client.get_symbol_info(symbol)
            print(symbol_info)

    asyncio.run(main())    