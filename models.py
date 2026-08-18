from dataclasses import dataclass
from typing import Optional, Dict, Any, List
from datetime import datetime

@dataclass
class TickData:
    symbol: str
    token: str
    last_price: float
    average_price: float = 0.0
    volume: int = 0
    oi: int = 0
    poi: int = 0
    timestamp: Optional[datetime] = None
    raw_data: Optional[Dict[str, Any]] = None

@dataclass
class CandleData:
    symbol: str
    token: str
    timestamp: int  # unix timestamp in seconds for the open time
    open: float
    high: float
    low: float
    close: float
    volume: int
    raw_data: Optional[Dict[str, Any]] = None

@dataclass
class OrderUpdate:
    order_id: str
    symbol: str
    status: str  # e.g., 'FILLED', 'REJECTED', 'OPEN'
    transaction_type: str  # 'Buy' or 'Sell'
    quantity: int
    price: float
    average_price: float
    raw_data: Optional[Dict[str, Any]] = None

@dataclass
class PositionData:
    symbol: str
    quantity: int  # Net quantity (positive for long, negative for short)
    average_price: float
    last_price: float
    realized_pnl: float
    unrealized_pnl: float
    raw_data: Optional[Dict[str, Any]] = None

@dataclass
class OptionData:
    token: str
    symbol: str
    strike: float
    option_type: str  # 'CE' or 'PE'
    expiry: str
    exchange: str = "NFO"
