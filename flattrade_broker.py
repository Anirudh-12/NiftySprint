from typing import List, Dict, Optional, Callable, Any
from broker_interface import BaseBroker
from models import TickData, CandleData, OrderUpdate, PositionData, OptionData
from NorenWebApi import NorenWebApi
import traceback
import logging
import datetime

class FlatTradeBroker(BaseBroker):
    def __init__(self):
        self.api = NorenWebApi()
        self._subscribe_callback: Optional[Callable[[TickData], None]] = None
        self._order_update_callback: Optional[Callable[[OrderUpdate], None]] = None

    def login(self, credentials: Dict[str, Any]) -> bool:
        try:
            # For FlatTrade, credentials usually contain user_id, password, totp_key, appkey
            user_id = credentials.get("user_id")
            password = credentials.get("password")
            totp_key = credentials.get("totp_key", credentials.get("factor2"))
            appkey = credentials.get("appkey", credentials.get("api_key"))
            
            res = self.api.login(user_id, password, totp_key, appkey)
            if res and res.get('stat') == 'Ok':
                return True
            return False
        except Exception as e:
            logging.error(f"FlatTrade login error: {e}")
            return False

    def get_positions(self) -> List[PositionData]:
        raw_positions = self.api.get_positions()
        positions = []
        if raw_positions and isinstance(raw_positions, list):
            for pos in raw_positions:
                try:
                    positions.append(PositionData(
                        symbol=pos.get('tsym', ''),
                        quantity=int(float(pos.get('netqty', pos.get('qty', 0)))),
                        average_price=float(pos.get('netavgprc', pos.get('avgprc', 0.0))),
                        last_price=float(pos.get('lp', 0.0)),
                        realized_pnl=float(pos.get('rpnl', 0.0)),
                        unrealized_pnl=float(pos.get('urmtom', 0.0)),
                        raw_data=pos
                    ))
                except Exception as e:
                    logging.error(f"Error parsing position: {e}")
        return positions

    def get_option_chain(self, exchange: str, symbol: str, strike_price: float, count: int) -> List[OptionData]:
        chain_res = self.api.get_option_chain(
            exchange=exchange,
            tradingsymbol=symbol,
            strikeprice=strike_price,
            count=count
        )
        options = []
        if chain_res and chain_res.get('stat') == 'Ok' and 'values' in chain_res:
            for opt in chain_res['values']:
                try:
                    options.append(OptionData(
                        token=str(opt.get('token', '')),
                        symbol=opt.get('tsym', ''),
                        strike=float(opt.get('strprc', 0)),
                        option_type=opt.get('optt', ''),
                        expiry=opt.get('exd', ''),  # Expiry date string
                        exchange=exchange
                    ))
                except Exception as e:
                    logging.error(f"Error parsing option chain: {e}")
        return options

    def get_historical_data(
        self, exchange: str, token: str, start_time: float, end_time: float, interval: int
    ) -> List[CandleData]:
        res = self.api.get_time_price_series(
            exchange=exchange,
            token=token,
            starttime=start_time,
            endtime=end_time,
            interval=interval
        )
        candles = []
        if res and isinstance(res, list):
            for c in res:
                try:
                    t_str = c.get('time')
                    dt = None
                    try:
                        dt = datetime.datetime.strptime(t_str, "%d-%m-%Y %H:%M:%S")
                    except ValueError:
                        try:
                            dt = datetime.datetime.strptime(t_str, "%d/%m/%Y %H:%M:%S")
                        except ValueError:
                            continue
                    
                    candles.append(CandleData(
                        symbol="", # Not returned in raw
                        token=token,
                        timestamp=int(dt.timestamp()),
                        open=float(c.get('into', 0)),
                        high=float(c.get('inth', 0)),
                        low=float(c.get('intl', 0)),
                        close=float(c.get('intc', 0)),
                        volume=int(c.get('intv', 0)),
                        raw_data=c
                    ))
                except Exception as e:
                    pass
        return candles

    def place_order(
        self,
        symbol: str,
        quantity: int,
        transaction_type: str,
        exchange: str = "NFO",
        order_type: str = "MKT",
        product_type: str = "M",
        price: float = 0.0,
        trigger_price: float = 0.0,
        remarks: str = "",
    ) -> str:
        res = self.api.place_order(
            tradingsymbol=symbol,
            quantity=quantity,
            buy_or_sell=transaction_type,
            exchange=exchange,
            product_type=product_type,
            discloseqty=0,
            price_type=order_type,
            price=price,
            trigger_price=trigger_price,
            remarks=remarks
        )
        if res and 'norenordno' in res:
            return res['norenordno']
        return ""

    def get_order_status(self, order_id: str) -> Optional[OrderUpdate]:
        res = self.api.single_order_history(order_id)
        if res and isinstance(res, list) and len(res) > 0:
            order = res[0]
            price = float(order.get('flprc', order.get('avgprc', 0.0)))
            return OrderUpdate(
                order_id=order_id,
                symbol=order.get('tsym', ''),
                status=order.get('status', 'UNKNOWN'),
                transaction_type=order.get('trantype', ''),
                quantity=int(float(order.get('qty', 0))),
                price=float(order.get('prc', 0.0)),
                average_price=price,
                raw_data=order
            )
        return None

    def get_quotes(self, exchange: str, token: str) -> Optional[TickData]:
        res = self.api.get_quotes(exchange, token)
        if res and 'lp' in res:
            return TickData(
                symbol=res.get('tsym', ''),
                token=token,
                last_price=float(res.get('lp', 0)),
                average_price=float(res.get('ap', 0)),
                volume=int(res.get('v', 0)),
                oi=int(res.get('oi', 0)),
                poi=int(res.get('poi', 0)),
                raw_data=res
            )
        return None

    def _internal_subscribe_callback(self, message: Dict[str, Any]):
        if not self._subscribe_callback: return
        if message.get("t") in ["tf", "tk"]:
            token_str = str(message.get("tk", ""))
            token = token_str.split("|")[-1] if "|" in token_str else token_str
            tick = TickData(
                symbol=message.get('tsym', ''),
                token=token,
                last_price=float(message.get('lp', 0)),
                average_price=float(message.get('ap', 0)),
                volume=int(message.get('v', 0)),
                oi=int(message.get('oi', 0)),
                poi=int(message.get('poi', 0)),
                raw_data=message
            )
            self._subscribe_callback(tick)

    def _internal_order_update_callback(self, message: Dict[str, Any]):
        if not self._order_update_callback: return
        if message.get('t') == 'om':
            order = OrderUpdate(
                order_id=message.get('norenordno', ''),
                symbol=message.get('tsym', ''),
                status=message.get('status', ''),
                transaction_type=message.get('trantype', ''),
                quantity=int(float(message.get('qty', 0))),
                price=float(message.get('prc', 0)),
                average_price=float(message.get('avgprc', 0)),
                raw_data=message
            )
            self._order_update_callback(order)

    def start_websocket(
        self,
        subscribe_callback: Callable[[TickData], None],
        order_update_callback: Callable[[OrderUpdate], None],
        socket_open_callback: Callable[[], None],
    ) -> None:
        self._subscribe_callback = subscribe_callback
        self._order_update_callback = order_update_callback
        self.api.start_websocket(
            subscribe_callback=self._internal_subscribe_callback,
            order_update_callback=self._internal_order_update_callback,
            socket_open_callback=socket_open_callback
        )

    def subscribe_market_data(self, tokens: List[str]) -> None:
        from NorenRestApiPy.NorenApi import FeedType
        self.api.subscribe(tokens, FeedType.TOUCHLINE)
