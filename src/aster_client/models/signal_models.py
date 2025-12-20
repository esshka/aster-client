"""
Signal Models - Data structures for ZMQ signal processing.

This module provides dataclasses for handling ENTRY/EXIT/PARTIAL_EXIT signals
from the Python realtime trading pipeline.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional, List


@dataclass
class TPLevel:
    """Take profit level configuration."""
    price: Decimal
    exit_pct: float
    ratio: float = 1.0


@dataclass
class SignalMessage:
    """
    ZMQ Signal message from realtime trading pipeline.
    
    Attributes:
        action: Signal action (ENTRY, EXIT, PARTIAL_EXIT)
        direction: Trading direction (LONG, SHORT)
        symbol: Trading pair symbol (e.g., "SOLUSDT")
        price: Current market price
        timestamp: ISO 8601 timestamp
        confidence: Optional model confidence score (0.0 - 1.0)
        stop_loss: Optional stop loss price
        take_profit: Optional take profit price
        reason: Optional reason for signal (e.g., "ML Signal", "TimeKill")
        position_size_r: Position size in R units
        exit_pct: Percentage of position to exit (for PARTIAL_EXIT)
        remaining_pct: Remaining position percentage after exit
        move_sl_to_be: Whether to move SL to break-even after partial exit
        multi_tp_enabled: Whether multiple TP levels are enabled
        tp_levels: List of TP level configurations
    """
    action: str  # ENTRY, EXIT, PARTIAL_EXIT
    direction: str  # LONG, SHORT
    symbol: str
    price: Decimal
    timestamp: str
    confidence: Optional[float] = None
    stop_loss: Optional[Decimal] = None
    take_profit: Optional[Decimal] = None
    reason: Optional[str] = None
    position_size_r: Optional[float] = None
    exit_pct: Optional[float] = None
    remaining_pct: Optional[float] = None
    move_sl_to_be: bool = False
    multi_tp_enabled: bool = False
    tp_levels: Optional[List[TPLevel]] = None

    @classmethod
    def from_dict(cls, data: dict) -> "SignalMessage":
        """Create SignalMessage from dictionary."""
        tp_levels = None
        if data.get("tp_levels"):
            tp_levels = [
                TPLevel(
                    price=Decimal(str(tp["price"])),
                    exit_pct=float(tp["exit_pct"]),
                    ratio=float(tp.get("ratio", 1.0))
                )
                for tp in data["tp_levels"]
            ]
        
        return cls(
            action=data.get("action", "ENTRY"),
            direction=data["direction"],
            symbol=data["symbol"],
            price=Decimal(str(data["price"])),
            timestamp=data["timestamp"],
            confidence=data.get("confidence"),
            stop_loss=Decimal(str(data["stop_loss"])) if data.get("stop_loss") else None,
            take_profit=Decimal(str(data["take_profit"])) if data.get("take_profit") else None,
            reason=data.get("reason"),
            position_size_r=data.get("position_size_r"),
            exit_pct=data.get("exit_pct"),
            remaining_pct=data.get("remaining_pct"),
            move_sl_to_be=data.get("move_sl_to_be", False),
            multi_tp_enabled=data.get("multi_tp_enabled", False),
            tp_levels=tp_levels,
        )


@dataclass
class PositionState:
    """
    Tracks position state for a symbol/account.
    
    Attributes:
        symbol: Trading pair symbol
        account_id: Account identifier
        side: Position side (LONG, SHORT)
        quantity: Current position quantity
        entry_price: Average entry price
        is_read_only: If True, position was pre-existing and should not be managed
    """
    symbol: str
    account_id: str
    side: str  # LONG, SHORT
    quantity: Decimal
    entry_price: Decimal
    is_read_only: bool = False

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "symbol": self.symbol,
            "account_id": self.account_id,
            "side": self.side,
            "quantity": str(self.quantity),
            "entry_price": str(self.entry_price),
            "is_read_only": self.is_read_only,
        }


@dataclass
class PositionSizingConfig:
    """
    Configuration for R-based position sizing.
    
    R = deposit_size * r_percentage
    
    Example with defaults:
        R = 140 USDT * 0.01 = 1.4 USDT per R
        position_size_r = 20 means target notional = 28 USDT
    """
    deposit_size: Decimal = field(default_factory=lambda: Decimal("140"))
    r_percentage: Decimal = field(default_factory=lambda: Decimal("0.01"))  # 1% = 1R
    
    @property
    def r_value(self) -> Decimal:
        """Calculate R value in USDT."""
        return self.deposit_size * self.r_percentage
    
    def calculate_quantity(
        self,
        entry_price: Decimal,
        position_size_r: float,
        contract_size: Decimal = Decimal("1"),
        leverage: int = 20,
    ) -> Decimal:
        """
        Calculate position quantity based on R units.
        
        Args:
            entry_price: Entry price for the position
            position_size_r: Position size in R units
            contract_size: Contract size (e.g., 0.1 for some tokens)
            leverage: Leverage to use
            
        Returns:
            Number of contracts/units to trade
        """
        # Target Notional = position_size_r * R value
        target_notional = Decimal(str(position_size_r)) * self.r_value
        
        # Contract Value = entry_price * contract_size
        contract_value = entry_price * contract_size
        
        # Contracts = Target Notional / Contract Value
        contracts = target_notional / contract_value
        
        # Safety: Cap at max buying power (deposit * leverage * 0.95)
        max_notional = self.deposit_size * Decimal(str(leverage)) * Decimal("0.95")
        max_contracts = max_notional / contract_value
        
        if contracts > max_contracts:
            contracts = max_contracts
        
        # Round down to whole number (most exchanges use integer contracts)
        return contracts.quantize(Decimal("1"), rounding="ROUND_DOWN")
    
    @classmethod
    def from_dict(cls, data: dict) -> "PositionSizingConfig":
        """Create from dictionary (e.g., from YAML config)."""
        return cls(
            deposit_size=Decimal(str(data.get("deposit_size", 140))),
            r_percentage=Decimal(str(data.get("r_percentage", 0.01))),
        )
