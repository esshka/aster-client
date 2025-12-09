"""
AccountPool - Multi-account parallel execution module.

This module provides the AccountPool class for managing multiple Aster trading
accounts and executing requests in parallel using asyncio.gather().

Example usage:
    from aster_client import AccountPool, AccountConfig
    
    accounts = [
        AccountConfig(id="account1", api_key="key1", api_secret="secret1"),
        AccountConfig(id="account2", api_key="key2", api_secret="secret2"),
    ]
    
    async with AccountPool(accounts) as pool:
        # Get account info for all accounts in parallel
        results = await pool.get_accounts_info_parallel()
        
        # Place orders across all accounts simultaneously
        order = OrderRequest(symbol="BTCUSDT", side="buy", ...)
        order_results = await pool.place_orders_parallel(order)
"""

import asyncio
import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import List, Optional, Callable, Any, TypeVar, Generic

from .account_client import AsterClient
from .models import (
    ConnectionConfig, RetryConfig, OrderRequest, OrderResponse,
    AccountInfo, Position, Balance, BalanceV2, ClosePositionResult
)

logger = logging.getLogger(__name__)

T = TypeVar('T')


@dataclass(frozen=True)
class AccountConfig:
    """
    Configuration for a single account in the pool.
    
    Attributes:
        id: Unique identifier for this account
        api_key: API key for authentication
        api_secret: API secret for authentication
        base_url: Optional custom base URL for this account
        timeout: Optional custom timeout in seconds
        simulation: Enable simulation mode (default: False)
        recv_window: Receive window in milliseconds (default: 5000)
    """
    id: str
    api_key: str
    api_secret: str
    base_url: Optional[str] = None
    timeout: Optional[float] = None
    simulation: bool = False
    recv_window: int = 5000


@dataclass(frozen=True)
class AccountResult(Generic[T]):
    """
    Wrapper for individual account execution results.
    
    Attributes:
        account_id: ID of the account this result belongs to
        success: Whether the operation succeeded
        result: The result data if successful
        error: The exception if failed
    """
    account_id: str
    success: bool
    result: Optional[T] = None
    error: Optional[Exception] = None


class AccountPool:
    """
    Manages multiple Aster accounts and executes operations in parallel.
    
    The AccountPool creates and manages individual AsterClient instances for
    each account, providing methods to execute operations across all accounts
    simultaneously using asyncio.gather().
    
    Example:
        accounts = [
            AccountConfig(id="acc1", api_key="key1", api_secret="secret1"),
            AccountConfig(id="acc2", api_key="key2", api_secret="secret2"),
        ]
        
        async with AccountPool(accounts) as pool:
            results = await pool.get_accounts_info_parallel()
            for result in results:
                if result.success:
                    print(f"{result.account_id}: {result.result}")
                else:
                    print(f"{result.account_id} failed: {result.error}")
    """
    
    def __init__(
        self,
        accounts: List[AccountConfig],
        retry_config: Optional[RetryConfig] = None,
    ):
        """
        Initialize AccountPool with multiple accounts.
        
        Args:
            accounts: List of AccountConfig objects
            retry_config: Optional shared retry configuration for all accounts
            
        Raises:
            ValueError: If accounts list is empty or contains duplicate IDs
        """
        if not accounts:
            raise ValueError("Accounts list cannot be empty")
        
        # Check for duplicate account IDs
        account_ids = [acc.id for acc in accounts]
        if len(account_ids) != len(set(account_ids)):
            raise ValueError("Duplicate account IDs found")
        
        self._accounts = accounts
        self._retry_config = retry_config
        self._clients: dict[str, AsterClient] = {}
        self._closed = False
        
        logger.info(f"AccountPool initialized with {len(accounts)} accounts")
    
    @property
    def account_count(self) -> int:
        """Get the number of accounts in the pool."""
        return len(self._accounts)
    
    def get_client(self, account_id: str) -> Optional[AsterClient]:
        """
        Get the AsterClient for a specific account.
        
        Args:
            account_id: ID of the account
            
        Returns:
            AsterClient instance or None if not found
        """
        return self._clients.get(account_id)
    
    async def _initialize_clients(self) -> None:
        """Initialize AsterClient instances for all accounts."""
        for account_config in self._accounts:
            # Prepare connection config parameters
            conn_params = {
                'api_key': account_config.api_key,
                'api_secret': account_config.api_secret,
                'simulation': account_config.simulation,
                'recv_window': account_config.recv_window,
            }
            
            # Only include base_url if explicitly set to avoid overriding the default
            if account_config.base_url is not None:
                conn_params['base_url'] = account_config.base_url
            
            # Only include timeout if explicitly set
            if account_config.timeout is not None:
                conn_params['timeout'] = account_config.timeout
            
            conn_config = ConnectionConfig(**conn_params)
            
            client = AsterClient(conn_config, self._retry_config)
            self._clients[account_config.id] = client
            
        logger.info(f"Initialized {len(self._clients)} client instances")
    
    async def execute_parallel(
        self,
        func: Callable[[AsterClient], Any],
        return_exceptions: bool = True,
    ) -> List[AccountResult[Any]]:
        """
        Execute a function across all accounts in parallel.
        
        Args:
            func: Async function that takes an AsterClient and returns a result
            return_exceptions: If True, capture exceptions instead of raising
            
        Returns:
            List of AccountResult objects, one per account
            
        Example:
            async def get_balance(client):
                return await client.get_balances()
            
            results = await pool.execute_parallel(get_balance)
        """
        if self._closed:
            raise RuntimeError("AccountPool is closed")
        
        # Create tasks for each account
        tasks = []
        account_ids = []
        
        for account_config in self._accounts:
            client = self._clients[account_config.id]
            tasks.append(func(client))
            account_ids.append(account_config.id)
        
        # Execute in parallel
        results = await asyncio.gather(*tasks, return_exceptions=return_exceptions)
        
        # Wrap results in AccountResult objects
        account_results = []
        for account_id, result in zip(account_ids, results):
            if isinstance(result, Exception):
                account_results.append(
                    AccountResult(
                        account_id=account_id,
                        success=False,
                        error=result
                    )
                )
                logger.error(f"Account {account_id} failed: {result}")
            else:
                account_results.append(
                    AccountResult(
                        account_id=account_id,
                        success=True,
                        result=result
                    )
                )
        
        return account_results
    
    async def get_accounts_info_parallel(self) -> List[AccountResult[AccountInfo]]:
        """
        Get account information for all accounts in parallel.
        
        Returns:
            List of AccountResult objects containing AccountInfo
        """
        async def get_info(client: AsterClient) -> AccountInfo:
            return await client.get_account_info()
        
        return await self.execute_parallel(get_info)
    
    async def get_positions_parallel(self) -> List[AccountResult[List[Position]]]:
        """
        Get positions for all accounts in parallel.
        
        Returns:
            List of AccountResult objects containing position lists
        """
        async def get_positions(client: AsterClient) -> List[Position]:
            return await client.get_positions()
        
        return await self.execute_parallel(get_positions)
    
    async def get_balances_parallel(self) -> List[AccountResult[List[Balance]]]:
        """
        Get balances for all accounts in parallel.
        
        Returns:
            List of AccountResult objects containing balance lists
        """
        async def get_balances(client: AsterClient) -> List[Balance]:
            return await client.get_balances()
        
        return await self.execute_parallel(get_balances)
    
    async def get_orders_parallel(
        self,
        symbol: Optional[str] = None
    ) -> List[AccountResult[List[OrderResponse]]]:
        """
        Get active orders for all accounts in parallel.
        
        Args:
            symbol: Optional symbol to filter orders (e.g., "BTCUSDT").
                   If None, returns all orders for each account.
        
        Returns:
            List of AccountResult objects containing OrderResponse lists
            
        Example:
            # Get all orders across all accounts
            results = await pool.get_orders_parallel()
            
            # Get only BTCUSDT orders
            results = await pool.get_orders_parallel(symbol="BTCUSDT")
            
            for result in results:
                if result.success:
                    print(f"{result.account_id}: {len(result.result)} orders")
        """
        async def get_orders(client: AsterClient) -> List[OrderResponse]:
            return await client.get_orders(symbol=symbol)
        
        return await self.execute_parallel(get_orders)
    
    async def place_orders_parallel(
        self,
        orders: OrderRequest | List[OrderRequest],
    ) -> List[AccountResult[OrderResponse]]:
        """
        Place orders across all accounts in parallel.
        
        Args:
            orders: Single OrderRequest (same for all accounts) or list of
                   OrderRequest objects (one per account)
            
        Returns:
            List of AccountResult objects containing OrderResponse
            
        Raises:
            ValueError: If orders list length doesn't match account count
        """
        # Handle single order for all accounts
        if isinstance(orders, OrderRequest):
            order_list = [orders] * len(self._accounts)
        else:
            if len(orders) != len(self._accounts):
                raise ValueError(
                    f"Orders list length ({len(orders)}) must match "
                    f"account count ({len(self._accounts)})"
                )
            order_list = orders
        
        # Create order placement tasks
        tasks = []
        account_ids = []
        
        for account_config, order in zip(self._accounts, order_list):
            client = self._clients[account_config.id]
            tasks.append(client.place_order(order))
            account_ids.append(account_config.id)
        
        # Execute in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Wrap results
        account_results = []
        for account_id, result in zip(account_ids, results):
            if isinstance(result, Exception):
                account_results.append(
                    AccountResult(
                        account_id=account_id,
                        success=False,
                        error=result
                    )
                )
                logger.error(f"Order placement failed for {account_id}: {result}")
            else:
                account_results.append(
                    AccountResult(
                        account_id=account_id,
                        success=True,
                        result=result
                    )
                )
                logger.info(f"Order placed successfully for {account_id}")
        
        return account_results
    
    async def place_bbo_orders_parallel(
        self,
        symbol: str,
        side: str,
        quantity: Decimal | List[Decimal],
        market_price: Decimal,
        tick_size: Decimal,
        ticks_distance: int = 1,
        time_in_force: str = "gtc",
        client_order_ids: Optional[List[str]] = None,
        position_side: Optional[str] = None,
    ) -> List[AccountResult[OrderResponse]]:
        """
        Place BBO orders across all accounts in parallel.
        
        Args:
            symbol: Trading symbol
            side: Order side ("buy" or "sell")
            quantity: Single quantity (same for all) or list of quantities
            market_price: Current market price
            tick_size: Tick size for the symbol
            ticks_distance: Number of ticks away from market price
            time_in_force: Time in force (default: "gtc")
            client_order_ids: Optional list of client order IDs (one per account)
            position_side: Optional position side for hedge mode
            
        Returns:
            List of AccountResult objects containing OrderResponse
        """
        # Handle single quantity for all accounts
        if isinstance(quantity, Decimal):
            quantities = [quantity] * len(self._accounts)
        else:
            if len(quantity) != len(self._accounts):
                raise ValueError(
                    f"Quantities list length ({len(quantity)}) must match "
                    f"account count ({len(self._accounts)})"
                )
            quantities = quantity
        
        # Handle client order IDs
        if client_order_ids and len(client_order_ids) != len(self._accounts):
            raise ValueError(
                f"Client order IDs list length must match account count"
            )
        
        # Create BBO order tasks
        tasks = []
        account_ids = []
        
        for i, account_config in enumerate(self._accounts):
            client = self._clients[account_config.id]
            client_order_id = client_order_ids[i] if client_order_ids else None
            
            tasks.append(
                client.place_bbo_order(
                    symbol=symbol,
                    side=side,
                    quantity=quantities[i],
                    market_price=market_price,
                    tick_size=tick_size,
                    ticks_distance=ticks_distance,
                    time_in_force=time_in_force,
                    client_order_id=client_order_id,
                    position_side=position_side,
                )
            )
            account_ids.append(account_config.id)
        
        # Execute in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Wrap results
        account_results = []
        for account_id, result in zip(account_ids, results):
            if isinstance(result, Exception):
                account_results.append(
                    AccountResult(
                        account_id=account_id,
                        success=False,
                        error=result
                    )
                )
                logger.error(f"BBO order failed for {account_id}: {result}")
            else:
                account_results.append(
                    AccountResult(
                        account_id=account_id,
                        success=True,
                        result=result
                    )
                )
                logger.info(f"BBO order placed for {account_id}")
        
        return account_results
    
    async def cancel_orders_parallel(
        self,
        symbol: str,
        order_ids: Optional[List[Optional[int]]] = None,
        client_order_ids: Optional[List[Optional[str]]] = None,
    ) -> List[AccountResult[dict]]:
        """
        Cancel orders across all accounts in parallel.
        
        Args:
            symbol: Trading symbol
            order_ids: Optional list of order IDs (one per account, can be None)
            client_order_ids: Optional list of client order IDs
            
        Returns:
            List of AccountResult objects containing cancellation responses
        """
        # Validate list lengths
        if order_ids and len(order_ids) != len(self._accounts):
            raise ValueError("Order IDs list length must match account count")
        if client_order_ids and len(client_order_ids) != len(self._accounts):
            raise ValueError("Client order IDs list length must match account count")
        
        # Create cancellation tasks
        tasks = []
        account_ids = []
        
        for i, account_config in enumerate(self._accounts):
            client = self._clients[account_config.id]
            order_id = order_ids[i] if order_ids else None
            client_order_id = client_order_ids[i] if client_order_ids else None
            
            tasks.append(
                client.cancel_order(
                    symbol=symbol,
                    order_id=order_id,
                    orig_client_order_id=client_order_id
                )
            )
            account_ids.append(account_config.id)
        
        # Execute in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Wrap results
        account_results = []
        for account_id, result in zip(account_ids, results):
            if isinstance(result, Exception):
                account_results.append(
                    AccountResult(
                        account_id=account_id,
                        success=False,
                        error=result
                    )
                )
                logger.error(f"Order cancellation failed for {account_id}: {result}")
            else:
                account_results.append(
                    AccountResult(
                        account_id=account_id,
                        success=True,
                        result=result
                    )
                )
        
        return account_results
    
    async def close_positions_for_symbol_parallel(
        self,
        symbol: str,
        tick_size: Decimal,
        best_bid: Optional[Decimal] = None,
        best_ask: Optional[Decimal] = None,
        ticks_distance: int = 0,
        max_retries: int = 2,
        fill_timeout_ms: int = 1000,
        max_chase_percent: float = 0.1,
    ) -> List[AccountResult[ClosePositionResult]]:
        """
        Close positions for a symbol across all accounts in parallel.
        
        This method executes close_position_for_symbol on each account simultaneously,
        cancelling all open orders (TP/SL) and closing positions with BBO orders.
        
        Args:
            symbol: Trading symbol (e.g., "BTCUSDT")
            tick_size: Tick size for the symbol (for BBO price calculation)
            best_bid: Optional best bid price (uses cache if not provided)
            best_ask: Optional best ask price (uses cache if not provided)
            ticks_distance: Number of ticks away from best price (default: 0)
            max_retries: Maximum retry attempts for BBO order (default: 2)
            fill_timeout_ms: Time to wait for fill before retry (default: 1000)
            max_chase_percent: Maximum price deviation from original (default: 0.1%)
            
        Returns:
            List of AccountResult objects containing ClosePositionResult for each account
        """
        if self._closed:
            raise RuntimeError("AccountPool is closed")
        
        # Create close position tasks for each account
        tasks = []
        account_ids = []
        
        for account_config in self._accounts:
            client = self._clients[account_config.id]
            tasks.append(
                client.close_position_for_symbol(
                    symbol=symbol,
                    tick_size=tick_size,
                    best_bid=best_bid,
                    best_ask=best_ask,
                    ticks_distance=ticks_distance,
                    max_retries=max_retries,
                    fill_timeout_ms=fill_timeout_ms,
                    max_chase_percent=max_chase_percent,
                )
            )
            account_ids.append(account_config.id)
        
        # Execute in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Wrap results
        account_results = []
        for account_id, result in zip(account_ids, results):
            if isinstance(result, Exception):
                account_results.append(
                    AccountResult(
                        account_id=account_id,
                        success=False,
                        error=result
                    )
                )
                logger.error(f"Close position failed for {account_id}: {result}")
            else:
                account_results.append(
                    AccountResult(
                        account_id=account_id,
                        success=result.success,
                        result=result,
                        error=Exception(result.error) if result.error else None
                    )
                )
                if result.success:
                    if result.close_order:
                        logger.info(
                            f"Position closed for {account_id}: "
                            f"Qty={result.position_quantity}, "
                            f"Cancelled={result.cancelled_orders_count} orders"
                        )
                    else:
                        logger.info(
                            f"No position to close for {account_id}, "
                            f"cancelled {result.cancelled_orders_count} orders"
                        )
                else:
                    logger.error(f"Close position failed for {account_id}: {result.error}")
        
        return account_results
    
    async def close(self) -> None:
        """Close all client connections and cleanup resources."""
        if not self._closed:
            close_tasks = [
                client.close() for client in self._clients.values()
            ]
            await asyncio.gather(*close_tasks, return_exceptions=True)
            self._closed = True
            logger.info("AccountPool closed")
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self._initialize_clients()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
