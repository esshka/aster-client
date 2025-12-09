"""
Trades Module - High-level trade management with BBO entry, TP, and SL orders.

This module provides abstractions for managing complete trades consisting of:
- BBO (Best Bid Offer) entry order
- Take Profit (TP) order
- Stop Loss (SL) order

The module handles percent-based TP/SL pricing, automatic placement after entry fill,
and trade lifecycle tracking.

Example usage:
    from aster_client import AsterClient, create_trade
    from aster_client.public_client import AsterPublicClient
    from decimal import Decimal
    
    async with AsterClient.from_env() as client, AsterPublicClient() as public:
        order_book = await public.get_order_book("ETHUSDT", limit=5)
        best_bid = Decimal(str(order_book["bids"][0][0]))
        best_ask = Decimal(str(order_book["asks"][0][0]))
        
        trade = await create_trade(
            client=client,
            symbol="ETHUSDT",
            side="buy",
            quantity=Decimal("0.1"),
            best_bid=best_bid,
            best_ask=best_ask,
            tick_size=Decimal("0.01"),
            tp_percent=1.0,  # 1% profit target
            sl_percent=0.5,  # 0.5% stop loss
        )
        print(f"Trade created: {trade.trade_id}")
"""


import asyncio
import logging
import time
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_DOWN
from enum import Enum
from typing import Optional, TYPE_CHECKING, Union
from datetime import datetime, timezone

if TYPE_CHECKING:
    from .account_client import AsterClient

from .models.orders import OrderRequest, OrderResponse

logger = logging.getLogger(__name__)


class TradeStatus(Enum):
    """Trade lifecycle status enumeration."""
    PENDING = "pending"  # Trade created, no orders placed yet
    ENTRY_PLACED = "entry_placed"  # Entry order placed, waiting for fill
    ENTRY_FILLED = "entry_filled"  # Entry filled, placing TP/SL
    ACTIVE = "active"  # All orders placed, trade is active
    COMPLETED = "completed"  # TP or SL triggered, trade closed
    CANCELLED = "cancelled"  # Trade cancelled before completion
    FAILED = "failed"  # Trade failed due to error


@dataclass
class TradeOrder:
    """Represents a single order within a trade."""
    order_id: Optional[str] = None
    price: Optional[Decimal] = None
    size: Optional[Decimal] = None
    status: Optional[str] = None  # Order status from exchange
    error: Optional[str] = None
    placed_at: Optional[str] = None
    filled_at: Optional[str] = None


@dataclass
class Trade:
    """
    Complete trade structure with entry, TP, and SL orders.
    
    Attributes:
        trade_id: Unique identifier for this trade
        symbol: Trading symbol (e.g., "ETHUSDT")
        side: Order side ("buy" or "sell")
        entry_order: BBO entry order details
        take_profit_orders: List of take profit order details (up to 5)
        stop_loss_order: Stop loss order details
        status: Current trade status
        tp_percents: List of take profit percentages (e.g., [1.0, 2.0] for 1% and 2%)
        sl_percent: Stop loss percentage (e.g., 0.5 for 0.5%)
        created_at: ISO timestamp when trade was created
        filled_at: ISO timestamp when entry was filled
        closed_at: ISO timestamp when trade was closed
        metadata: Additional metadata for the trade
    """
    trade_id: str
    symbol: str
    side: str
    entry_order: TradeOrder = field(default_factory=TradeOrder)
    take_profit_orders: list = field(default_factory=list)  # List of TradeOrder
    stop_loss_order: TradeOrder = field(default_factory=TradeOrder)
    status: TradeStatus = TradeStatus.PENDING
    tp_percents: Optional[list] = None  # List of float percentages
    sl_percent: Optional[float] = None
    created_at: Optional[str] = None
    filled_at: Optional[str] = None
    closed_at: Optional[str] = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert trade to dictionary for serialization."""
        tp_orders_list = []
        for tp_order in self.take_profit_orders:
            tp_orders_list.append({
                "order_id": tp_order.order_id,
                "price": str(tp_order.price) if tp_order.price else None,
                "size": str(tp_order.size) if tp_order.size else None,
                "status": tp_order.status,
                "error": tp_order.error,
                "placed_at": tp_order.placed_at,
            })
        
        return {
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "side": self.side,
            "status": self.status.value,
            "tp_percents": self.tp_percents,
            "sl_percent": self.sl_percent,
            "created_at": self.created_at,
            "filled_at": self.filled_at,
            "closed_at": self.closed_at,
            "entry_order": {
                "order_id": self.entry_order.order_id,
                "price": str(self.entry_order.price) if self.entry_order.price else None,
                "size": str(self.entry_order.size) if self.entry_order.size else None,
                "status": self.entry_order.status,
                "error": self.entry_order.error,
                "placed_at": self.entry_order.placed_at,
                "filled_at": self.entry_order.filled_at,
            },
            "take_profit_orders": tp_orders_list,
            "stop_loss_order": {
                "order_id": self.stop_loss_order.order_id,
                "price": str(self.stop_loss_order.price) if self.stop_loss_order.price else None,
                "size": str(self.stop_loss_order.size) if self.stop_loss_order.size else None,
                "status": self.stop_loss_order.status,
                "error": self.stop_loss_order.error,
                "placed_at": self.stop_loss_order.placed_at,
            },
            "metadata": self.metadata,
        }


def calculate_tp_sl_prices(
    entry_price: Decimal,
    side: str,
    tp_percents: Optional[list],
    sl_percent: float,
    tick_size: Decimal,
) -> tuple[list, Decimal]:
    """
    Calculate take profit and stop loss prices from entry price and percentage offsets.
    
    Args:
        entry_price: Entry fill price
        side: Order side ("buy" or "sell")
        tp_percents: List of take profit percentages (e.g., [1.0, 2.0] for 1% and 2%), or None/empty for no TPs
        sl_percent: Stop loss percentage (e.g., 0.5 for 0.5%)
        tick_size: Tick size for price rounding
        
    Returns:
        Tuple of (tp_prices_list, sl_price) rounded to tick size. tp_prices_list can be empty.
        
    Raises:
        ValueError: If parameters are invalid or TP/SL don't satisfy constraints
        
    Examples:
        >>> calculate_tp_sl_prices(Decimal("3500"), "buy", [1.0, 2.0], 0.5, Decimal("0.01"))
        ([Decimal("3535.00"), Decimal("3570.00")], Decimal("3482.50"))
        
        >>> calculate_tp_sl_prices(Decimal("3500"), "sell", [1.0], 0.5, Decimal("0.01"))
        ([Decimal("3465.00")], Decimal("3517.50"))
    """
    if entry_price <= 0:
        raise ValueError(f"Entry price must be positive, got {entry_price}")
    if tick_size <= 0:
        raise ValueError(f"Tick size must be positive, got {tick_size}")
    if sl_percent <= 0:
        raise ValueError(f"SL percent must be positive, got {sl_percent}")
    
    # Normalize tp_percents to a list
    if tp_percents is None:
        tp_percents = []
    elif not isinstance(tp_percents, list):
        tp_percents = [tp_percents]
    
    # Validate TP percents
    if len(tp_percents) > 5:
        raise ValueError(f"Maximum 5 TP levels allowed, got {len(tp_percents)}")
    for i, tp_pct in enumerate(tp_percents):
        if tp_pct <= 0:
            raise ValueError(f"TP percent at index {i} must be positive, got {tp_pct}")
    
    side = side.lower()
    if side not in ["buy", "sell"]:
        raise ValueError(f"Side must be 'buy' or 'sell', got '{side}'")
    
    tp_prices = []
    
    if side == "buy":
        # For BUY: TP is above entry, SL is below entry
        for tp_percent in tp_percents:
            tp_multiplier = Decimal(str(1 + tp_percent / 100))
            tp_price_raw = entry_price * tp_multiplier
            tp_price = _round_to_tick(tp_price_raw, tick_size)
            tp_prices.append(tp_price)
            
        sl_multiplier = Decimal(str(1 - sl_percent / 100))
        sl_price_raw = entry_price * sl_multiplier
        sl_price = _round_to_tick(sl_price_raw, tick_size)
    else:  # sell
        # For SELL: TP is below entry, SL is above entry
        for tp_percent in tp_percents:
            tp_sell_mult = Decimal(str(1 - tp_percent / 100))
            tp_price_raw = entry_price * tp_sell_mult
            tp_price = _round_to_tick(tp_price_raw, tick_size)
            tp_prices.append(tp_price)
            
        sl_sell_mult = Decimal(str(1 + sl_percent / 100))
        sl_price_raw = entry_price * sl_sell_mult
        sl_price = _round_to_tick(sl_price_raw, tick_size)
    
    # Validate constraints
    if side == "buy":
        for i, tp_price in enumerate(tp_prices):
            if not (sl_price < entry_price < tp_price):
                raise ValueError(
                    f"For BUY orders: SL < entry < TP required. "
                    f"Got SL={sl_price}, entry={entry_price}, TP[{i}]={tp_price}"
                )
    else:  # sell
        for i, tp_price in enumerate(tp_prices):
            if not (tp_price < entry_price < sl_price):
                raise ValueError(
                    f"For SELL orders: TP < entry < SL required. "
                    f"Got TP[{i}]={tp_price}, entry={entry_price}, SL={sl_price}"
                )
    
    tp_str = f"TPs={tp_prices}" if tp_prices else "TPs=[]"
    logger.debug(
        f"Calculated TP/SL for {side.upper()} @ {entry_price}: "
        f"{tp_str}, SL={sl_price} (-{sl_percent}%)"
    )
    
    return tp_prices, sl_price


def _round_to_tick(price: Decimal, tick_size: Decimal) -> Decimal:
    """Round price to the nearest tick size."""
    # Calculate number of ticks
    ticks = (price / tick_size).quantize(Decimal("1"), rounding=ROUND_DOWN)
    rounded_price = ticks * tick_size
    
    # Maintain precision based on tick size
    precision = abs(tick_size.as_tuple().exponent)
    return rounded_price.quantize(Decimal(10) ** -precision)


async def wait_for_order_fill(
    client: "AsterClient",
    symbol: str,
    order_id: str,
    timeout: float = 60.0,
    poll_interval: float = 2.0,
) -> Optional[OrderResponse]:
    """
    Poll order status until filled or timeout.
    
    Args:
        client: AsterClient instance
        symbol: Trading symbol
        order_id: Order ID to monitor (string or int)
        timeout: Maximum time to wait in seconds (default: 60)
        poll_interval: Polling interval in seconds (default: 2)
        
    Returns:
        OrderResponse if order is filled, None if timeout or cancelled
        
    Raises:
        Exception: If order query fails
    """
    start_time = time.time()
    elapsed = 0.0
    
    logger.info(f"⏳ Waiting for order {order_id} to fill (timeout: {timeout}s)")
    
    while elapsed < timeout:
        try:
            # Query order status - convert order_id to int if it's a string
            try:
                order_id_int = int(order_id) if isinstance(order_id, str) else order_id
            except ValueError:
                # If order_id is a non-numeric string, just pass it as is
                order_id_int = order_id
                
            order = await client.get_order(symbol=symbol, order_id=order_id_int)
            
            if order is None:
                logger.warning(f"Order {order_id} not found")
                await asyncio.sleep(poll_interval)
                elapsed = time.time() - start_time
                continue
            
            # Check if filled
            if order.status in ["FILLED", "COMPLETED"]:
                logger.info(f"✅ Order {order_id} filled at ${order.average_price}")
                return order
            
            # Check if cancelled or rejected
            if order.status in ["CANCELED", "CANCELLED", "REJECTED", "EXPIRED"]:
                logger.warning(f"❌ Order {order_id} {order.status}")
                return None
            
            # Still pending, wait and retry
            logger.debug(f"Order {order_id} status: {order.status}, waiting...")
            await asyncio.sleep(poll_interval)
            elapsed = time.time() - start_time
            
        except Exception as e:
            logger.error(f"Error querying order {order_id}: {e}")
            raise
    
    logger.error(f"⏰ Timeout waiting for order {order_id} after {timeout}s")
    return None


async def create_trade(
    client: "AsterClient",
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
) -> Trade:
    """
    Create a complete trade with BBO entry, take profit(s), and stop loss orders.
    
    Workflow:
        1. Place BBO entry order with automatic retry
        2. Wait for entry fill with automatic price updates
        3. Calculate TP/SL prices from fill price
        4. Place TP order(s) (LIMIT with reduceOnly=True) - quantity split equally among TPs
        5. Place SL order (STOP_MARKET with closePosition=True)
    
    Args:
        client: AsterClient instance
        symbol: Trading symbol (e.g., "ETHUSDT")
        side: Order side ("buy" or "sell")
        quantity: Order quantity in base currency
        best_bid: Current best bid price
        best_ask: Current best ask price
        tick_size: Tick size for the symbol
        tp_percents: Take profit configuration(s). Supports multiple formats:
                    - Single float: 1.0 (TP at +1%, full quantity)
                    - List of floats: [0.5, 1.0, 1.5] (3 TPs, equal quantity split)
                    - List of [price_pct, amount_frac]: [[0.5, 0.5], [1.0, 0.5]] 
                      (TP1 at +0.5% with 50% qty, TP2 at +1.0% with 50% qty)
        sl_percent: Stop loss percentage (e.g., 0.5 for 0.5%)
        ticks_distance: Distance in ticks for BBO order (default: 0 = at best bid/ask)
        max_retries: Maximum retry attempts for BBO order (default: 2)
        fill_timeout_ms: Time to wait for fill before retry in ms (default: 1000)
        max_chase_percent: Maximum price deviation from original (default: 0.1%)
        position_side: Position side for hedge mode ("LONG" or "SHORT")
        vol_size: Minimum volume size for the symbol (used for quantity rounding)
        
    Returns:
        Trade object with all order details
        
    Raises:
        ValueError: If parameters are invalid (e.g., more than 5 TPs)
        Exception: If order placement fails
    """
    # Normalize tp_percents to list of (price_pct, amount_frac) tuples
    # Supports:
    #   - None -> []
    #   - 1.0 -> [(1.0, 1.0)]
    #   - [0.5, 1.0] -> [(0.5, 0.5), (1.0, 0.5)]  (equal split)
    #   - [[0.5, 0.3], [1.0, 0.7]] -> [(0.5, 0.3), (1.0, 0.7)]  (custom amounts)
    tp_configs: list[tuple[float, float]] = []
    
    if tp_percents is None:
        pass  # Empty list
    elif isinstance(tp_percents, (int, float)):
        # Single TP with full quantity
        tp_configs = [(float(tp_percents), 1.0)]
    elif isinstance(tp_percents, list) and len(tp_percents) > 0:
        # Check if it's a list of [price, amount] pairs or just prices
        first_item = tp_percents[0]
        if isinstance(first_item, (list, tuple)) and len(first_item) == 2:
            # Format: [[price_pct, amount_frac], ...]
            tp_configs = [(float(p[0]), float(p[1])) for p in tp_percents]
        else:
            # Format: [price_pct, ...] - equal split
            num_tps = len(tp_percents)
            equal_frac = 1.0 / num_tps
            tp_configs = [(float(p), equal_frac) for p in tp_percents]
    
    # Validate TP count
    if len(tp_configs) > 5:
        raise ValueError(f"Maximum 5 TP levels allowed, got {len(tp_configs)}")
    
    # Validate amount fractions sum to ~1.0 (with tolerance for floating point)
    if tp_configs:
        total_frac = sum(frac for _, frac in tp_configs)
        if abs(total_frac - 1.0) > 0.01:
            raise ValueError(f"TP amount fractions must sum to 1.0, got {total_frac}")
    
    # Extract just the percentages for Trade object and calculate_tp_sl_prices
    tp_percents_list = [pct for pct, _ in tp_configs]
    
    # Generate trade ID
    trade_id = f"trade_{symbol}_{side}_{int(time.time() * 1000)}"
    
    # Create trade object
    trade = Trade(
        trade_id=trade_id,
        symbol=symbol,
        side=side.lower(),
        tp_percents=tp_percents_list if tp_percents_list else None,
        sl_percent=sl_percent,
        created_at=datetime.now(timezone.utc).isoformat(),
        metadata={
            "best_bid": str(best_bid),
            "best_ask": str(best_ask),
            "tick_size": str(tick_size),
            "ticks_distance": ticks_distance,
            "max_retries": max_retries,
            "fill_timeout_ms": fill_timeout_ms,
            "max_chase_percent": max_chase_percent,
        }
    )
    
    try:
        # Step 1: Place BBO entry order with retry
        if tp_percents_list:
            tp_desc = f"TPs: {[f'+{p}%' for p in tp_percents_list]}"
        else:
            tp_desc = "TPs: None"
        logger.info(f"📊 Creating trade {trade_id}: {symbol} {side.upper()} {quantity}")
        logger.info(f"   {tp_desc}, SL: -{sl_percent}%")
        logger.info(f"   BBO: ticks_distance={ticks_distance}, max_retries={max_retries}, timeout={fill_timeout_ms}ms, chase={max_chase_percent}%")
        
        trade.status = TradeStatus.ENTRY_PLACED
        
        try:
            # Use BBO order with automatic retry
            filled_order = await client.place_bbo_order_with_retry(
                symbol=symbol,
                side=side,
                quantity=quantity,
                tick_size=tick_size,
                ticks_distance=ticks_distance,
                max_retries=max_retries,
                fill_timeout_ms=fill_timeout_ms,
                max_chase_percent=max_chase_percent,
                position_side=position_side,
                best_bid=best_bid,
                best_ask=best_ask,
            )

            
            trade.entry_order.order_id = filled_order.order_id
            trade.entry_order.size = quantity
            trade.entry_order.status = filled_order.status
            trade.entry_order.price = filled_order.average_price
            trade.entry_order.placed_at = datetime.now(timezone.utc).isoformat()
            trade.entry_order.filled_at = trade.entry_order.placed_at
            
            logger.info(f"✅ Entry order filled: {filled_order.order_id} @ {filled_order.average_price}")
            
        except Exception as bbo_error:
            # BBO order failed (retry exhausted or chase exceeded)
            trade.status = TradeStatus.CANCELLED
            trade.entry_order.error = str(bbo_error)
            logger.error(f"❌ Entry order failed: {bbo_error}")
            return trade

        # Entry order filled successfully
        trade.status = TradeStatus.ENTRY_FILLED
        trade.filled_at = trade.entry_order.filled_at
        
        # Use best bid/ask as fallback if fill price is missing
        fallback_price = best_bid if side.lower() == "buy" else best_ask
        entry_fill_price = filled_order.average_price or trade.entry_order.price or fallback_price

        
        # Step 3: Calculate TP/SL prices
        tp_prices, sl_price = calculate_tp_sl_prices(
            entry_price=entry_fill_price,
            side=side,
            tp_percents=tp_percents_list,
            sl_percent=sl_percent,
            tick_size=tick_size,
        )
        
        logger.info(f"📈 TPs: {tp_prices}, SL: ${sl_price}")
        
        # Step 4 & 5: Place all TP orders and SL order in parallel
        # For BUY entry (LONG position): SELL order to close with positionSide=LONG
        # For SELL entry (SHORT position): BUY order to close with positionSide=SHORT
        exit_side = "sell" if side.lower() == "buy" else "buy"
        exit_position_side = position_side if position_side else ("LONG" if side.lower() == "buy" else "SHORT")
        
        # Prepare all order requests
        order_tasks = []
        tp_quantities = []
        
        # Prepare TP orders
        if tp_prices:
            num_tps = len(tp_prices)
            
            # Calculate quantities based on tp_configs amount fractions
            for i, (_, amount_frac) in enumerate(tp_configs):
                tp_qty = quantity * Decimal(str(amount_frac))
                
                # Round quantity if vol_size is provided
                if vol_size:
                    tp_qty = (tp_qty / vol_size).quantize(
                        Decimal("1"), rounding=ROUND_DOWN
                    ) * vol_size
                
                tp_quantities.append(tp_qty)
            
            # Adjust last TP to use remainder (handle rounding)
            placed_qty = sum(tp_quantities[:-1]) if len(tp_quantities) > 1 else Decimal("0")
            tp_quantities[-1] = quantity - placed_qty
            
            logger.info(f"   TP quantities: {[str(q) for q in tp_quantities]}")
            
            
            # Create TP order tasks
            for i, (tp_price, tp_quantity) in enumerate(zip(tp_prices, tp_quantities)):
                tp_request = OrderRequest(
                    symbol=symbol,
                    side=exit_side,
                    order_type="limit",
                    quantity=tp_quantity,
                    price=tp_price,
                    time_in_force="GTX",
                    position_side=exit_position_side,
                )
                order_tasks.append(("TP", i, tp_price, tp_quantity, client.place_order(tp_request)))
        else:
            logger.info("ℹ️ No TP percents provided, skipping TP orders.")
        
        # Prepare SL order
        sl_request = OrderRequest(
            symbol=symbol,
            side=exit_side,
            order_type="stop_market",
            quantity=Decimal("0"),
            stop_price=sl_price,
            position_side=exit_position_side,
            close_position=True,
        )
        order_tasks.append(("SL", 0, sl_price, quantity, client.place_order(sl_request)))
        
        # Execute all orders in parallel
        logger.info(f"   Placing {len(order_tasks)} orders in parallel...")
        
        async def execute_order(order_type, index, price, qty, coro):
            """Execute a single order and return result."""
            try:
                response = await coro
                return (order_type, index, price, qty, response, None)
            except Exception as e:
                return (order_type, index, price, qty, None, e)
        
        results = await asyncio.gather(
            *[execute_order(ot, idx, p, q, coro) for ot, idx, p, q, coro in order_tasks]
        )
        
        # Process results
        placed_at = datetime.now(timezone.utc).isoformat()
        for order_type, index, price, qty, response, error in results:
            if order_type == "TP":
                tp_order = TradeOrder()
                if response:
                    tp_order.order_id = response.order_id
                    tp_order.price = price
                    tp_order.size = qty
                    tp_order.status = response.status
                    tp_order.placed_at = placed_at
                    logger.info(f"✅ TP[{index+1}] order placed: {response.order_id} @ ${price} ({qty})")
                else:
                    tp_order.price = price
                    tp_order.size = qty
                    tp_order.error = str(error)
                    logger.error(f"❌ Failed to place TP[{index+1}] order: {error}")
                trade.take_profit_orders.append(tp_order)
            else:  # SL
                if response:
                    trade.stop_loss_order.order_id = response.order_id
                    trade.stop_loss_order.price = price
                    trade.stop_loss_order.size = qty
                    trade.stop_loss_order.status = response.status
                    trade.stop_loss_order.placed_at = placed_at
                    logger.info(f"✅ Stop loss order placed: {response.order_id} @ ${price}")
                else:
                    trade.stop_loss_order.price = price
                    trade.stop_loss_order.error = str(error)
                    logger.error(f"❌ Failed to place SL order: {error}")
        
        # Update trade status
        # TP is OK if no TPs were requested, or at least one TP was placed successfully
        if not tp_percents_list:
            tp_ok = True
        else:
            tp_ok = any(tp.order_id is not None for tp in trade.take_profit_orders)
        sl_ok = (trade.stop_loss_order.order_id is not None)
        
        # Check for partial TP failures
        tp_failures = sum(1 for tp in trade.take_profit_orders if tp.error is not None)
        total_tps = len(trade.take_profit_orders)

        if tp_ok and sl_ok:
            trade.status = TradeStatus.ACTIVE
            if tp_failures > 0:
                logger.warning(f"🎉 Trade {trade_id} is now ACTIVE ({total_tps - tp_failures}/{total_tps} TPs placed)")
            else:
                logger.info(f"🎉 Trade {trade_id} is now ACTIVE")
        elif not sl_ok: 
            # SL is required
            trade.status = TradeStatus.ACTIVE  # Partially active (only TP placed or neither if TP missing too)
            logger.warning(f"⚠️  Trade {trade_id} partially active (missing SL)")
        elif not tp_ok:
            # TP was requested but all failed
            trade.status = TradeStatus.ACTIVE
            logger.warning(f"⚠️  Trade {trade_id} partially active (all TPs failed)")
        else:
            trade.status = TradeStatus.FAILED
            trade.metadata["error"] = "Failed to place required orders"
            logger.error(f"❌ Trade {trade_id} failed to become active")
        
        return trade
        
    except Exception as e:
        logger.error(f"❌ Trade creation failed: {e}")
        trade.status = TradeStatus.FAILED
        trade.metadata["error"] = str(e)
        return trade
