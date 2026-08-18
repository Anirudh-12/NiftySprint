from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Callable, Any, Union
from models import TickData, CandleData, OrderUpdate, PositionData, OptionData

class BaseBroker(ABC):
    """
    Abstract base class for all broker implementations.
    Any new broker (e.g., Zerodha, AngelOne) should inherit from this class.
    """

    @abstractmethod
    def login(self, credentials: Dict[str, Any]) -> bool:
        """Authenticate with the broker's API."""
        pass

    @abstractmethod
    def get_positions(self) -> List[PositionData]:
        """Fetch all open positions and return as standardized PositionData."""
        pass

    @abstractmethod
    def get_option_chain(self, exchange: str, symbol: str, strike_price: float, count: int) -> List[OptionData]:
        """Fetch option chain and return standardized OptionData."""
        pass

    @abstractmethod
    def get_historical_data(
        self, exchange: str, token: str, start_time: float, end_time: float, interval: int
    ) -> List[CandleData]:
        """Fetch historical candle data (1-minute, etc.) and return standard CandleData."""
        pass

    @abstractmethod
    def place_order(
        self,
        symbol: str,
        quantity: int,
        transaction_type: str,  # 'Buy' or 'Sell'
        exchange: str = "NFO",
        order_type: str = "MKT",
        product_type: str = "M",
        price: float = 0.0,
        trigger_price: float = 0.0,
        remarks: str = "",
    ) -> str:
        """
        Place an order and return the order ID.
        """
        pass

    @abstractmethod
    def get_order_status(self, order_id: str) -> Optional[OrderUpdate]:
        """Fetch status of a single order."""
        pass

    @abstractmethod
    def get_quotes(self, exchange: str, token: str) -> Optional[TickData]:
        """Get snapshot quote (LTP) for a token."""
        pass

    @abstractmethod
    def start_websocket(
        self,
        subscribe_callback: Callable[[TickData], None],
        order_update_callback: Callable[[OrderUpdate], None],
        socket_open_callback: Callable[[], None],
    ) -> None:
        """Start the broker's websocket connection and set up normalized callbacks."""
        pass

    @abstractmethod
    def subscribe_market_data(self, tokens: List[str]) -> None:
        """Subscribe to live tick data for a list of tokens (format e.g., 'NSE|26000' or depends on broker)."""
        pass

class BaseInstrumentHelper(ABC):
    """Abstract base class for broker-specific instrument data retrieval."""
    
    @abstractmethod
    def get_step_size(self, symbol: str) -> float:
        pass

    @abstractmethod
    def get_expirys_dict(self, symbols: List[str]) -> Dict[str, List[str]]:
        pass

    @abstractmethod
    def ce_strike_to_token(self, symbol: str, expiry: str) -> Dict[float, str]:
        pass

    @abstractmethod
    def pe_strike_to_token(self, symbol: str, expiry: str) -> Dict[float, str]:
        pass

    @abstractmethod
    def ce_strike_to_symbol(self, symbol: str, expiry: str) -> Dict[float, str]:
        pass

    @abstractmethod
    def pe_strike_to_symbol(self, symbol: str, expiry: str) -> Dict[float, str]:
        pass

    @abstractmethod
    def get_option_strikes(self, symbol: str, expiry: str, atm_strike: int, count: int) -> List[Dict[str, str]]:
        pass

    @abstractmethod
    def get_lot_size(self, symbol: str) -> int:
        pass
        
    @abstractmethod
    def get_nifty_fut_token(self) -> str:
        pass
        
    @abstractmethod
    def get_token_symbol_dict(self, selected_expiry: str) -> Dict[str, str]:
        pass
