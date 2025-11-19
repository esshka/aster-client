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
    from decimal import Decimal
    
    async with AsterClient.from_env() as client:
        trade = await create_trade(
            client=client,
            symbol="ETHUSDT",
            side="buy",
            quantity=Decimal("0.1"),
            market_price=Decimal("3500.0"),
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
from typing import Optional, TYPE_CHECKING
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
        take_profit_order: Take profit order details
        stop_loss_order: Stop loss order details
        status: Current trade status
        tp_percent: Take profit percentage (e.g., 1.0 for 1%)
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
    take_profit_order: TradeOrder = field(default_factory=TradeOrder)
    stop_loss_order: TradeOrder = field(default_factory=TradeOrder)
    status: TradeStatus = TradeStatus.PENDING
    tp_percent: Optional[float] = None
    sl_percent: Optional[float] = None
    created_at: Optional[str] = None
    filled_at: Optional[str] = None
    closed_at: Optional[str] = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert trade to dictionary for serialization."""
        return {
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "side": self.side,
            "status": self.status.value,
            "tp_percent": self.tp_percent,
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
            "take_profit_order": {
                "order_id": self.take_profit_order.order_id,
                "price": str(self.take_profit_order.price) if self.take_profit_order.price else None,
                "size": str(self.take_profit_order.size) if self.take_profit_order.size else None,
                "status": self.take_profit_order.status,
                "error": self.take_profit_order.error,
                "placed_at": self.take_profit_order.placed_at,
            },
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
    tp_percent: float,
    sl_percent: float,
    tick_size: Decimal,
) -> tuple[Decimal, Decimal]:
    """
    Calculate take profit and stop loss prices from entry price and percentage offsets.
    
    Args:
        entry_price: Entry fill price
        side: Order side ("buy" or "sell")
        tp_percent: Take profit percentage (e.g., 1.0 for 1%)
        sl_percent: Stop loss percentage (e.g., 0.5 for 0.5%)
        tick_size: Tick size for price rounding
        
    Returns:
        Tuple of (tp_price, sl_price) rounded to tick size
        
    Raises:
        ValueError: If parameters are invalid or TP/SL don't satisfy constraints
        
    Examples:
        >>> calculate_tp_sl_prices(Decimal("3500"), "buy", 1.0, 0.5, Decimal("0.01"))
        (Decimal("3535.00"), Decimal("3482.50"))
        
        >>> calculate_tp_sl_prices(Decimal("3500"), "sell", 1.0, 0.5, Decimal("0.01"))
        (Decimal("3465.00"), Decimal("3517.50"))
    """
    if entry_price <= 0:
        raise ValueError(f"Entry price must be positive, got {entry_price}")
    if tick_size <= 0:
        raise ValueError(f"Tick size must be positive, got {tick_size}")
    if tp_percent <= 0:
        raise ValueError(f"TP percent must be positive, got {tp_percent}")
    if sl_percent <= 0:
        raise ValueError(f"SL percent must be positive, got {sl_percent}")
    
    side = side.lower()
    if side not in ["buy", "sell"]:
        raise ValueError(f"Side must be 'buy' or 'sell', got '{side}'")
    
    # Calculate raw prices
    tp_multiplier = Decimal(str(1 + tp_percent / 100))
    sl_multiplier = Decimal(str(1 - sl_percent / 100))
    
    if side == "buy":
        # For BUY: TP is above entry, SL is below entry
        tp_price_raw = entry_price * tp_multiplier
        sl_price_raw = entry_price * sl_multiplier
    else:  # sell
        # For SELL: TP is below entry, SL is above entry
        tp_price_raw = entry_price * sl_multiplier
        sl_price_raw = entry_price * tp_multiplier
    
    # Round to tick size
    tp_price = _round_to_tick(tp_price_raw, tick_size)
    sl_price = _round_to_tick(sl_price_raw, tick_size)
    
    # Validate constraints
    if side == "buy":
        if not (sl_price < entry_price < tp_price):
            raise ValueError(
                f"For BUY orders: SL < entry < TP required. "
                f"Got SL={sl_price}, entry={entry_price}, TP={tp_price}"
            )
    else:  # sell
        if not (tp_price < entry_price < sl_price):
            raise ValueError(
                f"For SELL orders: TP < entry < SL required. "
                f"Got TP={tp_price}, entry={entry_price}, SL={sl_price}"
            )
    
    logger.debug(
        f"Calculated TP/SL for {side.upper()} @ {entry_price}: "
        f"TP={tp_price} (+{tp_percent}%), SL={sl_price} (-{sl_percent}%)"
    )
    
    return tp_price, sl_price


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
    market_price: Decimal,
    tick_size: Decimal,
    tp_percent: float,
    sl_percent: float,
    ticks_distance: int = 1,
    fill_timeout: float = 10.0,
    poll_interval: float = 0.5,
    position_side: Optional[str] = None,
) -> Trade:
    """
    Create a complete trade with BBO entry, take profit, and stop loss orders.
    
    Workflow:
        1. Place BBO entry order
        2. Wait for entry fill (default: 10s timeout, polling every 0.5s)
        3. Cancel entry order if not filled within timeout
        4. Calculate TP/SL prices from fill price
        5. Place TP order (LIMIT with reduceOnly=True)
        6. Place SL order (STOP_MARKET with closePosition=True)
    
    Args:
        client: AsterClient instance
        symbol: Trading symbol (e.g., "ETHUSDT")
        side: Order side ("buy" or "sell")
        quantity: Order quantity in base currency
        market_price: Current market price for BBO calculation
        tick_size: Tick size for the symbol
        tp_percent: Take profit percentage (e.g., 1.0 for 1%)
        sl_percent: Stop loss percentage (e.g., 0.5 for 0.5%)
        ticks_distance: Distance in ticks for BBO order (default: 1)
        fill_timeout: Maximum time to wait for entry fill (default: 10s)
        poll_interval: Order status polling interval (default: 0.5s)
        position_side: Position side for hedge mode ("LONG" or "SHORT")
        
    Returns:
        Trade object with all order details
        
    Raises:
        ValueError: If parameters are invalid
        Exception: If order placement fails
    """
    # Generate trade ID
    trade_id = f"trade_{symbol}_{side}_{int(time.time() * 1000)}"
    
    # Create trade object
    trade = Trade(
        trade_id=trade_id,
        symbol=symbol,
        side=side.lower(),
        tp_percent=tp_percent,
        sl_percent=sl_percent,
        created_at=datetime.now(timezone.utc).isoformat(),
        metadata={
            "market_price": str(market_price),
            "tick_size": str(tick_size),
            "ticks_distance": ticks_distance,
        }
    )
    
    try:
        # Step 1: Place BBO entry order
        logger.info(f"📊 Creating trade {trade_id}: {symbol} {side.upper()} {quantity}")
        logger.info(f"   TP: +{tp_percent}%, SL: -{sl_percent}%")
        
        trade.status = TradeStatus.ENTRY_PLACED
        entry_response = await client.place_bbo_order(
            symbol=symbol,
            side=side,
            quantity=quantity,
            market_price=market_price,
            tick_size=tick_size,
            ticks_distance=ticks_distance,
            position_side=position_side,
        )
        
        trade.entry_order.order_id = entry_response.order_id
        trade.entry_order.size = quantity
        trade.entry_order.status = entry_response.status
        trade.entry_order.placed_at = datetime.now(timezone.utc).isoformat()
        
        logger.info(f"✅ Entry order placed: {entry_response.order_id}")
        
        # Step 2: Wait for entry fill
        logger.info(f"⏳ Waiting for entry order to fill (timeout: {fill_timeout}s, polling every {poll_interval}s)...")
        filled_order = await wait_for_order_fill(
            client=client,
            symbol=symbol,
            order_id=entry_response.order_id,
            timeout=fill_timeout,
            poll_interval=poll_interval,
        )
        
        if filled_order is None:
            # Cancel the entry order on the exchange
            logger.warning(f"⚠️ Entry order not filled within {fill_timeout}s, cancelling order...")
            try:
                cancel_response = await client.cancel_order(
                    symbol=symbol,
                    order_id=entry_response.order_id
                )
                logger.info(f"✅ Entry order {entry_response.order_id} cancelled successfully")
                trade.entry_order.status = "CANCELLED"
            except Exception as cancel_error:
                logger.error(f"❌ Failed to cancel entry order {entry_response.order_id}: {cancel_error}")
                trade.entry_order.error = f"Timeout and cancel failed: {cancel_error}"
            
            trade.status = TradeStatus.CANCELLED
            if not trade.entry_order.error:
                trade.entry_order.error = f"Entry order not filled within {fill_timeout}s timeout"
            logger.error(f"❌ Entry order not filled, trade cancelled")
            return trade
        
        # Update entry order with fill details
        trade.status = TradeStatus.ENTRY_FILLED
        trade.entry_order.price = filled_order.average_price
        trade.entry_order.status = filled_order.status
        trade.entry_order.filled_at = datetime.now(timezone.utc).isoformat()
        trade.filled_at = trade.entry_order.filled_at
        
        entry_fill_price = filled_order.average_price or market_price
        logger.info(f"✅ Entry filled at ${entry_fill_price}")
        
        # Step 3: Calculate TP/SL prices
        tp_price, sl_price = calculate_tp_sl_prices(
            entry_price=entry_fill_price,
            side=side,
            tp_percent=tp_percent,
            sl_percent=sl_percent,
            tick_size=tick_size,
        )
        
        logger.info(f"📈 TP: ${tp_price}, SL: ${sl_price}")
        
        # Step 4: Place take profit order (TAKE_PROFIT_MARKET with closePosition=true)
        # For BUY entry (LONG position): SELL order to close with positionSide=LONG
        # For SELL entry (SHORT position): BUY order to close with positionSide=SHORT
        tp_side = "sell" if side.lower() == "buy" else "buy"
        
        # When using closePosition, positionSide must match the position being closed
        # NOT the order side. For a LONG position, we use SELL with positionSide=LONG
        tp_position_side = position_side if position_side else ("LONG" if side.lower() == "buy" else "SHORT")
        
        tp_request = OrderRequest(
            symbol=symbol,
            side=tp_side,
            order_type="take_profit_market",
            quantity=Decimal("0"),  # Required by dataclass but will be ignored by API
            stop_price=tp_price,  # Take profit trigger price
            position_side=tp_position_side,  # Position being closed
            close_position=True,  # Close entire position when TP is hit
        )
        
        try:
            tp_response = await client.place_order(tp_request)
            trade.take_profit_order.order_id = tp_response.order_id
            trade.take_profit_order.price = tp_price
            trade.take_profit_order.size = quantity
            trade.take_profit_order.status = tp_response.status
            trade.take_profit_order.placed_at = datetime.now(timezone.utc).isoformat()
            logger.info(f"✅ Take profit order placed: {tp_response.order_id} @ ${tp_price}")
        except Exception as e:
            logger.error(f"❌ Failed to place TP order: {e}")
            trade.take_profit_order.error = str(e)
        
        # Step 5: Place stop loss order (STOP_MARKET with closePosition=true)
        # For BUY entry (LONG position): SELL order to close with positionSide=LONG
        # For SELL entry (SHORT position): BUY order to close with positionSide=SHORT
        sl_side = "sell" if side.lower() == "buy" else "buy"
        
        # When using closePosition, positionSide must match the position being closed
        sl_position_side = position_side if position_side else ("LONG" if side.lower() == "buy" else "SHORT")
        
        sl_request = OrderRequest(
            symbol=symbol,
            side=sl_side,
            order_type="stop_market",
            quantity=Decimal("0"),  # Required by dataclass but will be ignored by API
            stop_price=sl_price,  # Stop loss trigger price
            position_side=sl_position_side,  # Position being closed
            close_position=True,  # Close entire position when SL is hit
        )
        
        try:
            sl_response = await client.place_order(sl_request)
            trade.stop_loss_order.order_id = sl_response.order_id
            trade.stop_loss_order.price = sl_price
            trade.stop_loss_order.size = quantity
            trade.stop_loss_order.status = sl_response.status
            trade.stop_loss_order.placed_at = datetime.now(timezone.utc).isoformat()
            logger.info(f"✅ Stop loss order placed: {sl_response.order_id} @ ${sl_price}")
        except Exception as e:
            logger.error(f"❌ Failed to place SL order: {e}")
            trade.stop_loss_order.error = str(e)
        
        # Update trade status
        if trade.take_profit_order.order_id and trade.stop_loss_order.order_id:
            trade.status = TradeStatus.ACTIVE
            logger.info(f"🎉 Trade {trade_id} is now ACTIVE")
        elif trade.take_profit_order.order_id or trade.stop_loss_order.order_id:
            trade.status = TradeStatus.ACTIVE  # Partially active
            logger.warning(f"⚠️  Trade {trade_id} partially active (missing TP or SL)")
        else:
            trade.status = TradeStatus.FAILED
            trade.metadata["error"] = "Failed to place TP/SL orders"
            logger.error(f"❌ Trade {trade_id} failed to become active")
        
        return trade
        
    except Exception as e:
        logger.error(f"❌ Trade creation failed: {e}")
        trade.status = TradeStatus.FAILED
        trade.metadata["error"] = str(e)
        return trade
