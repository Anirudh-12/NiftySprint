import threading
from threading import Lock
from datetime import datetime, time as dtime
from collections import deque
import os
import asyncio

def log_debug(msg):
    try:
        with open("exe_debug_log.txt", "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n")
    except Exception:
        pass

class NiftyOneMinStrategy:
    def __init__(self, api, option_handler, instrument_helper, position_manager, bridge, notify_func=None):
        log_debug("NiftyOneMinStrategy initialized!")
        self.api = api
        self.option_handler = option_handler
        self.instrument_helper = instrument_helper
        self.position_manager = position_manager
        self.bridge = bridge
        self.notify_func = notify_func
        self.lock = Lock()

        # --- Config (set via configure) ---
        self.trig_min = 25
        self.trig_max = 45
        self.break_buffer = 2.0
        self.trail_points = 12.0
        self.t1_pct = 0.5
        self.t2_pct = 1.0
        self.t3_mult = 2
        self.pm_limit = 100
        self.initial_qty = 25
        self.t1_qty = 25
        self.start_time_str = "09:17"
        self.stop_time_str = "10:45"
        self.t2_qty = 0
        self.strike_ce = 0
        self.strike_pe = 0
        self.direction = None
        self.direction_filter = "BOTH"  # BOTH | LONG | SHORT

        # --- State ---
        self.state = "IDLE"
        self.is_running = False
        self.premarket_ok = True  # Kept True for UI compatibility; OI filter handles gating

        # --- Day tracking ---
        self.prev_day_close = 0.0
        self.day_high = 0.0
        self.day_low = float('inf')
        self.day_initialized = False

        # --- Futures candles ---
        self.futures_candles = []
        self.running_fut_candle = None
        self.last_fut_candle_ts = 0

        # --- Option candles (keyed by timestamp) ---
        self.option_candles = {"CE": {}, "PE": {}}
        self.running_opt_candle = {"CE": None, "PE": None}
        self.last_opt_candle_ts = {"CE": 0, "PE": 0}
        self.opt_ltp = 0.0
        self.index_ltp = 0.0

        # --- Reference Candle State ---
        self.reference_candle_fut = None
        self.reference_candle_ce = None
        self.reference_candle_pe = None
        self.ref_candle_ts = 0
        self.trigger_candle = None

        # --- Filters State (OI and price filters removed) ---

        # --- Direction Disable & Crossing State ---
        self.ce_disabled = False
        self.pe_disabled = False
        self.ce_scan_active = False
        self.pe_scan_active = False
        self.prev_opt_ltp = {"CE": 0.0, "PE": 0.0}

        # --- Trade / Position tracking ---
        self.entry_price_opt = 0.0
        self.opt_candle_size = 0.0
        self.option_high_since_entry = 0.0
        self.t1_target = 0.0
        self.t2_target = 0.0
        self.t3_target = 0.0
        self.current_sl = 0.0
        self.trailing_sl = 0.0
        self.t1_hit = False
        self.t2_hit = False
        self.remaining_qty = 0

        # --- Option subscription ---
        self.active_opt_strike = 0
        self.active_opt_type = "CE"
        self.active_trade_candles = {}
        self.running_active_trade_candle = None
        self.last_active_trade_candle_ts = 0

        # --- Asyncio event loop for non-blocking candle replacement ---
        self._asyncio_loop = asyncio.new_event_loop()
        self._asyncio_thread = threading.Thread(
            target=self._run_asyncio_loop,
            name="StrategyAsyncioLoop",
            daemon=True
        )
        self._asyncio_thread.start()

    def _run_asyncio_loop(self):
        asyncio.set_event_loop(self._asyncio_loop)
        self._asyncio_loop.run_forever()

    def _parse_time(self, time_str):
        try:
            parts = time_str.split(":")
            if len(parts) == 2:
                return dtime(int(parts[0]), int(parts[1]))
        except Exception:
            pass
        return None

    def _notify_user_message(self, message, title="Nifty Strategy"):
        if self.bridge:
            try:
                self.bridge.notify("showNotification", {"title": title, "message": message})
            except Exception:
                pass

    # =========================================================================
    # CONFIGURE & START/STOP
    # =========================================================================

    def configure(self, initial_qty, t1_qty, t2_qty, strike_ce, strike_pe,
                  trig_min, trig_max, break_buffer, t1_pct, t2_pct, t3_mult,
                  direction_filter="BOTH", pm_limit=100, start_time="09:17", stop_time="10:45", trail_points=12.0):
        self.initial_qty = int(initial_qty)
        self.t1_qty = int(t1_qty)
        self.t2_qty = int(t2_qty)
        self.start_time_str = str(start_time)
        self.stop_time_str = str(stop_time)
        self.trail_points = float(trail_points)

        new_strike_ce = int(strike_ce) if strike_ce else 0
        self.strike_ce = new_strike_ce

        new_strike_pe = int(strike_pe) if strike_pe else 0
        self.strike_pe = new_strike_pe
        self.direction_filter = str(direction_filter).upper() if direction_filter else "BOTH"
        self.trig_min = int(trig_min)
        self.trig_max = int(trig_max)
        self.break_buffer = float(break_buffer)
        self.t1_pct = float(t1_pct)
        self.t2_pct = float(t2_pct)
        self.t3_mult = int(t3_mult)
        self.pm_limit = int(pm_limit)

        if self.is_running:
            strike_changed = False
            if new_strike_ce > 0 and new_strike_ce != getattr(self, '_last_configured_strike_ce', 0):
                with self.lock:
                    self.option_candles["CE"].clear()
                    self.running_opt_candle["CE"] = None
                    self.last_opt_candle_ts["CE"] = 0
                self._fetch_historical_option_candles("CE", new_strike_ce)
                strike_changed = True
            if new_strike_pe > 0 and new_strike_pe != getattr(self, '_last_configured_strike_pe', 0):
                with self.lock:
                    self.option_candles["PE"].clear()
                    self.running_opt_candle["PE"] = None
                    self.last_opt_candle_ts["PE"] = 0
                self._fetch_historical_option_candles("PE", new_strike_pe)
                strike_changed = True
            if strike_changed:
                self._notify()

        self._last_configured_strike_ce = new_strike_ce
        self._last_configured_strike_pe = new_strike_pe

        if self.state in ("IN_TRADE", "TRAILING"):
            ep = self.entry_price_opt
            cs = self.opt_candle_size if self.opt_candle_size > 0 else ep * 0.1
            self.t1_target = ep + cs * self.t1_pct
            self.t2_target = ep + cs * self.t2_pct
            self.t3_target = ep + cs * self.t3_mult

    def start(self):
        should_notify_idle = False
        msg = ""
        with self.lock:
            if self.is_running:
                return
            self.is_running = True

            self.reference_candle_fut = None
            self.reference_candle_ce = None
            self.reference_candle_pe = None
            self.ref_candle_ts = 0
            self.trigger_candle = None

            self.ce_disabled = False
            self.pe_disabled = False
            self.ce_scan_active = False
            self.pe_scan_active = False
            self.prev_opt_ltp = {"CE": 0.0, "PE": 0.0}

            self.futures_candles = []
            self.running_fut_candle = None
            self.last_fut_candle_ts = 0
            self.day_initialized = False
            self.prev_day_close = 0.0
            self.day_high = 0.0
            self.day_low = float('inf')

            now_time = datetime.now().time()
            start_t = self._parse_time(self.start_time_str) or dtime(9, 17)
            stop_t = self._parse_time(self.stop_time_str) or dtime(10, 45)

            if now_time < start_t:
                self.state = "WAITING_TIME"
                print(f"[TIME] Current time {now_time.strftime('%H:%M:%S')} is before start time {self.start_time_str}. Waiting...")
            elif now_time >= stop_t:
                self.state = "IDLE"
                self.is_running = False
                msg = f"Cannot start strategy: Current time is after the stop time {self.stop_time_str}."
                print(f"[TIME] {msg}")
                should_notify_idle = True
            else:
                self.state = "SCANNING"

            if not should_notify_idle:
                self._fetch_prev_close()
                self._fetch_and_replay_historical_candles()
                self.option_handler.register_strategy_callback(self._on_tick)

        if should_notify_idle:
            self._notify_user_message(msg)
            self._notify()
        else:
            self._notify()

    def stop(self):
        with self.lock:
            self.is_running = False
            self._panic_exit_internal()
            self.state = "IDLE"
            self._reset_trade_state()
            self.ce_disabled = False
            self.pe_disabled = False
            self.ce_scan_active = False
            self.pe_scan_active = False
            self.reference_candle_fut = None
            self.reference_candle_ce = None
            self.reference_candle_pe = None
            self.ref_candle_ts = 0
        try:
            self.option_handler.unregister_strategy_callback(self._on_tick)
        except Exception:
            pass
        self._notify()

    def panic_exit(self):
        with self.lock:
            self._panic_exit_internal()
            self.state = "IDLE"
            self._reset_trade_state()
            self.ce_disabled = False
            self.pe_disabled = False
            self.ce_scan_active = False
            self.pe_scan_active = False
        self._notify()

    def force_entry(self, direction):
        with self.lock:
            tc = self.reference_candle_fut or self.trigger_candle
            if tc is None and self.futures_candles:
                tc = self.futures_candles[-1]
            self._enter_trade(direction, tc or {}, force=True)

    # =========================================================================
    # TICK HANDLER
    # =========================================================================

    def _on_tick(self, index_ltp, index_ltt=None, index_ap=0.0):
        if not self.is_running or not index_ltp:
            return
        try:
            now = datetime.now()
            ltp = float(index_ltp)
            self.index_ltp = ltp

            self._update_day_range(ltp)
            self._update_fut_candle(ltp, now)

            if self._check_time_limits_on_tick(now):
                return

            try:
                if self.strike_ce > 0:
                    ce_ltp = self.option_handler.get_option_ltp(self.strike_ce, "CE")
                    if ce_ltp > 0:
                        self._update_opt_candle(ce_ltp, now, "CE")
                if self.strike_pe > 0:
                    pe_ltp = self.option_handler.get_option_ltp(self.strike_pe, "PE")
                    if pe_ltp > 0:
                        self._update_opt_candle(pe_ltp, now, "PE")

                if self.state in ("IN_TRADE", "TRAILING"):
                    trade_ltp = self.option_handler.get_option_ltp(self.active_opt_strike, self.active_opt_type)
                    if trade_ltp > 0:
                        self._update_active_trade_candle(trade_ltp, now)
                        if trade_ltp > self.option_high_since_entry:
                            self.option_high_since_entry = trade_ltp
                    self.opt_ltp = trade_ltp
                else:
                    self.opt_ltp = self.option_handler.get_option_ltp(self.active_opt_strike, self.active_opt_type)
            except Exception:
                pass

            if self.state not in ("IDLE", "WAITING_TIME"):
                self._check_breakout(ltp, now)
                self._check_trade(ltp, now)

            # Record previous LTPs for crossing detection
            if self.strike_ce > 0:
                c_ltp = self.option_handler.get_option_ltp(self.strike_ce, "CE")
                if c_ltp > 0:
                    self.prev_opt_ltp["CE"] = c_ltp
            if self.strike_pe > 0:
                p_ltp = self.option_handler.get_option_ltp(self.strike_pe, "PE")
                if p_ltp > 0:
                    self.prev_opt_ltp["PE"] = p_ltp

            self._notify()
        except Exception:
            pass

    def _check_time_limits_on_tick(self, now):
        start_t = self._parse_time(self.start_time_str) or dtime(9, 17)
        stop_t = self._parse_time(self.stop_time_str) or dtime(10, 45)
        now_time = now.time()

        if now_time < start_t:
            if self.state != "WAITING_TIME":
                print(f"[TIME] Current time {now_time.strftime('%H:%M:%S')} is before start time {self.start_time_str}. Waiting...")
                self.state = "WAITING_TIME"
                self._notify()
            return True

        if self.state == "WAITING_TIME" and now_time >= start_t and now_time < stop_t:
            print(f"[TIME] Start time {self.start_time_str} reached. Transitioning to SCANNING.")
            self.state = "SCANNING"
            self._notify()
            msg = f"Nifty Strategy started scanning at {now_time.strftime('%H:%M:%S')} (Start time: {self.start_time_str})."
            self._notify_user_message(msg)

        if now_time >= stop_t:
            has_position = self.remaining_qty > 0 and self.state in ("IN_TRADE", "TRAILING")
            if not has_position:
                print(f"[TIME] Stop time {self.stop_time_str} reached. Stopping strategy.")
                self.stop()
                msg = f"Nifty Strategy stopped at {now_time.strftime('%H:%M:%S')} as stop time {self.stop_time_str} was reached and no active positions exist."
                self._notify_user_message(msg)
                return True
        return False

    # =========================================================================
    # DIRECTION GATING (OI and price filters removed)
    # =========================================================================

    def _is_direction_allowed(self, direction):
        """Direction is allowed unless manually disabled or blocked by direction_filter."""
        if direction == "CE" and self.ce_disabled:
            return False
        if direction == "PE" and self.pe_disabled:
            return False

        if self.direction_filter == "LONG" and direction != "CE":
            return False
        if self.direction_filter == "SHORT" and direction != "PE":
            return False

        return True

    # =========================================================================
    # DAY RANGE & HISTORICAL REPLAY
    # =========================================================================

    def _fetch_prev_close(self):
        try:
            nifty_token = self.option_handler.index_tokens.get("NIFTY", {}).get("token")
            exchange = self.option_handler.index_tokens.get("NIFTY", {}).get("exchange", "NFO")
            if not nifty_token:
                return
            quotes = self.api.get_quotes(exchange, nifty_token)
            if quotes:
                prev_close = quotes.get('c') or quotes.get('pc') or quotes.get('lp', 0)
                self.prev_day_close = float(prev_close or 0)
                current_lp = float(quotes.get('lp', 0) or 0)
                if current_lp > 0 and self.index_ltp == 0.0:
                    self.index_ltp = current_lp
                day_high = float(quotes.get('h', 0) or 0)
                day_low = float(quotes.get('l', 0) or 0)
                if day_high > 0 and day_low > 0:
                    self.day_high = day_high
                    self.day_low = day_low
                    self.day_initialized = True
        except Exception:
            pass

    def _fetch_and_replay_historical_candles(self):
        try:
            nifty_token = self.option_handler.index_tokens.get("NIFTY", {}).get("token")
            exchange = self.option_handler.index_tokens.get("NIFTY", {}).get("exchange", "NFO")
            if not nifty_token:
                return

            now = datetime.now()
            start_dt = now.replace(hour=9, minute=15, second=0, microsecond=0)
            snapped_minute = now.minute
            current_block_ts = int(now.replace(minute=snapped_minute, second=0, microsecond=0).timestamp())

            candles = self.api.get_historical_data(
                exchange=exchange,
                token=nifty_token,
                start_time=start_dt.timestamp(),
                end_time=now.timestamp(),
                interval=1
            )
            if not candles:
                return

            candles_sorted = sorted(candles, key=lambda x: x.timestamp)
            for c in candles_sorted:
                c_ts = c.timestamp
                if c_ts >= current_block_ts:
                    continue

                hi = c.high
                lo = c.low
                cl = c.close

                candle_obj = {
                    "time": c_ts,
                    "open": c.open,
                    "high": hi,
                    "low": lo,
                    "close": cl,
                    "size": hi - lo,
                }
                self.futures_candles.append(candle_obj)
                self._on_candle_close(candle_obj, "futures")

            if self.strike_ce > 0:
                self._fetch_historical_option_candles("CE", self.strike_ce)
            if self.strike_pe > 0:
                self._fetch_historical_option_candles("PE", self.strike_pe)

        except Exception as e:
            log_debug(f"[API_DEBUG] Exception in _fetch_and_replay_historical_candles: {e}")

    def _fetch_historical_option_candles(self, opt_type, strike):
        if strike <= 0:
            return
        token_info = self.option_handler._get_option_token("NIFTY", opt_type, strike)
        if not token_info:
            return
        exchange = token_info.get("exchange", "NFO")
        token = token_info.get("token")
        if not token:
            return

        def fetch_task():
            import time
            time.sleep(0.5)
            try:
                now = datetime.now()
                start_dt = now.replace(hour=9, minute=15, second=0, microsecond=0)
                snapped_minute = now.minute
                current_block_ts = int(now.replace(minute=snapped_minute, second=0, microsecond=0).timestamp())

                candles = self.api.get_historical_data(
                    exchange=exchange,
                    token=token,
                    start_time=start_dt.timestamp(),
                    end_time=now.timestamp(),
                    interval=1
                )
                if not candles:
                    return

                candles_sorted = sorted(candles, key=lambda x: x.timestamp)
                valid_candles = []
                for c in candles_sorted:
                    c_ts = c.timestamp
                    if c_ts >= current_block_ts:
                        continue

                    hi = c.high
                    lo = c.low
                    cl = c.close

                    valid_candles.append((c_ts, {
                        "time": c_ts,
                        "open": c.open,
                        "high": hi,
                        "low": lo,
                        "close": cl,
                        "size": hi - lo,
                    }))

                new_candles = dict(valid_candles)

                with self.lock:
                    current_strike = self.strike_ce if opt_type == "CE" else self.strike_pe
                    if strike != current_strike:
                        return
                    self.option_candles[opt_type].clear()
                    self.option_candles[opt_type].update(new_candles)
                self._notify()
            except Exception as e:
                log_debug(f"Error fetching historical options candles for {opt_type} {strike}: {e}")

        try:
            threading.Thread(target=fetch_task, daemon=True).start()
        except Exception as e:
            log_debug(f"[API_DEBUG] Thread creation failed: {e}")

    def _update_day_range(self, ltp):
        if not self.day_initialized:
            self.day_high = ltp
            self.day_low = ltp
            self.day_initialized = True
        if self.day_initialized:
            if ltp > self.day_high:
                self.day_high = ltp
            if ltp < self.day_low:
                self.day_low = ltp

    # =========================================================================
    # CANDLE BUILDERS
    # =========================================================================

    def _async_replace_candle(self, exchange, token, target_ts, candle_dict, label="futures"):
        if not token or not exchange:
            return
        try:
            asyncio.run_coroutine_threadsafe(
                self._async_replace_candle_coro(exchange, token, target_ts, candle_dict, label),
                self._asyncio_loop
            )
        except Exception as e:
            log_debug(f"[ASYNC_REPLACE] Failed to schedule async candle replace: {e}")

    async def _async_replace_candle_coro(self, exchange, token, target_ts, candle_dict, label="futures"):
        max_retries = 8
        ts_str = datetime.fromtimestamp(target_ts).strftime('%H:%M:%S')
        for attempt in range(max_retries):
            await asyncio.sleep(0.2)
            try:
                now = datetime.now()
                candles = await asyncio.to_thread(
                    self.api.get_historical_data,
                    exchange=exchange,
                    token=token,
                    start_time=target_ts,
                    end_time=now.timestamp(),
                    interval=1
                )
                if not candles:
                    continue
                found = False
                for c in candles:
                    c_ts = c.timestamp
                    if c_ts == target_ts:
                        hi = c.high
                        lo = c.low
                        cl = c.close
                        op = c.open
                        with self.lock:
                            candle_dict["open"] = op
                            candle_dict["high"] = hi
                            candle_dict["low"] = lo
                            candle_dict["close"] = cl
                            candle_dict["size"] = hi - lo
                            if label == "CE Option":
                                self.option_candles["CE"][target_ts] = candle_dict
                            elif label == "PE Option":
                                self.option_candles["PE"][target_ts] = candle_dict
                        msg = f"[ASYNC_REPLACE] SUCCESS: Replaced {label} candle ({ts_str}) -> O:{op}, H:{hi}, L:{lo}, C:{cl} (Attempt {attempt+1})"
                        print(msg)
                        log_debug(msg)
                        self._notify()
                        found = True
                        break
                if found:
                    return
            except Exception as e:
                if attempt == max_retries - 1:
                    err_msg = f"[ASYNC_REPLACE] FAIL: Error replacing {label} candle ({ts_str}): {e}"
                    print(err_msg)
                    log_debug(err_msg)
        fail_msg = f"[ASYNC_REPLACE] FAIL: Could not replace {label} candle ({ts_str}) - candle not found after {max_retries} attempts."
        print(fail_msg)
        log_debug(fail_msg)

    def _snap_1min(self, dt):
        return int(dt.replace(second=0, microsecond=0).timestamp())

    def _update_fut_candle(self, ltp, now):
        ts = self._snap_1min(now)
        if self.running_fut_candle is None:
            self.running_fut_candle = {"time": ts, "open": ltp, "high": ltp, "low": ltp, "close": ltp, "vol": 0}
            self.last_fut_candle_ts = ts
        elif ts > self.last_fut_candle_ts:
            completed = dict(self.running_fut_candle)
            completed["size"] = completed["high"] - completed["low"]
            self.futures_candles.append(completed)

            nifty_token = self.option_handler.index_tokens.get("NIFTY", {}).get("token")
            exchange = self.option_handler.index_tokens.get("NIFTY", {}).get("exchange", "NFO")
            if nifty_token and exchange:
                self._async_replace_candle(exchange, nifty_token, self.last_fut_candle_ts, completed, label="futures")

            self.running_fut_candle = {"time": ts, "open": ltp, "high": ltp, "low": ltp, "close": ltp, "vol": 0}
            self.last_fut_candle_ts = ts
            self._on_candle_close(completed, "futures")
        else:
            c = self.running_fut_candle
            c["high"] = max(c["high"], ltp)
            c["low"] = min(c["low"], ltp)
            c["close"] = ltp

    def _update_opt_candle(self, ltp, now, opt_type):
        if ltp <= 0:
            return
        ts = self._snap_1min(now)
        if self.running_opt_candle[opt_type] is None:
            self.running_opt_candle[opt_type] = {"time": ts, "open": ltp, "high": ltp, "low": ltp, "close": ltp}
            self.last_opt_candle_ts[opt_type] = ts
        elif ts > self.last_opt_candle_ts[opt_type]:
            completed = dict(self.running_opt_candle[opt_type])
            completed["size"] = completed["high"] - completed["low"]
            self.option_candles[opt_type][self.last_opt_candle_ts[opt_type]] = completed
            strike = self.strike_ce if opt_type == "CE" else self.strike_pe
            if strike > 0:
                token_info = self.option_handler._get_option_token("NIFTY", opt_type, strike)
                if token_info:
                    self._async_replace_candle(
                        token_info.get("exchange", "NFO"),
                        token_info.get("token"),
                        self.last_opt_candle_ts[opt_type],
                        completed,
                        label=f"{opt_type} Option"
                    )
            self._on_candle_close(completed, opt_type)
            self.running_opt_candle[opt_type] = {"time": ts, "open": ltp, "high": ltp, "low": ltp, "close": ltp}
            self.last_opt_candle_ts[opt_type] = ts
        else:
            c = self.running_opt_candle[opt_type]
            c["high"] = max(c["high"], ltp)
            c["low"] = min(c["low"], ltp)
            c["close"] = ltp

    def _update_active_trade_candle(self, ltp, now):
        ts = self._snap_1min(now)
        if self.running_active_trade_candle is None:
            self.running_active_trade_candle = {"time": ts, "open": ltp, "high": ltp, "low": ltp, "close": ltp}
            self.last_active_trade_candle_ts = ts
        elif ts > self.last_active_trade_candle_ts:
            completed = dict(self.running_active_trade_candle)
            completed["size"] = completed["high"] - completed["low"]
            self.active_trade_candles[self.last_active_trade_candle_ts] = completed
            if self.active_opt_strike > 0 and self.active_opt_type:
                token_info = self.option_handler._get_option_token("NIFTY", self.active_opt_type, self.active_opt_strike)
                if token_info:
                    self._async_replace_candle(token_info.get("exchange", "NFO"), token_info.get("token"), self.last_active_trade_candle_ts, completed, label=f"{self.active_opt_type} Option")
            self.running_active_trade_candle = {"time": ts, "open": ltp, "high": ltp, "low": ltp, "close": ltp}
            self.last_active_trade_candle_ts = ts
        else:
            c = self.running_active_trade_candle
            c["high"] = max(c["high"], ltp)
            c["low"] = min(c["low"], ltp)
            c["close"] = ltp

    # =========================================================================
    # CANDLE CLOSE & REFERENCE CANDLE ASSIGNMENT
    # =========================================================================

    def _on_candle_close(self, candle, candle_type):
        if candle_type == "futures":
            try:
                ts_str = datetime.fromtimestamp(candle["time"]).strftime('%H:%M:%S')
                print(f"\n[SCAN] --- Future Candle Closed @ {ts_str} ---")
                print(f"[SCAN] O:{candle['open']} H:{candle['high']} L:{candle['low']} C:{candle['close']} Size:{candle.get('size', 0):.2f}")
            except Exception:
                pass

            self._check_and_set_reference_candle(candle)
        elif candle_type in ("CE", "PE"):
            if self.state in ("IN_TRADE", "TRAILING"):
                return
            ref_opt = self._get_option_reference_candle(candle_type)
            if ref_opt and ref_opt.get("high"):
                ref_high = ref_opt["high"]
                if candle["close"] < ref_high:
                    if candle_type == "CE" and self.ce_disabled:
                        print(f"[RE-ACTIVATE] CE candle closed at {candle['close']} < Ref High {ref_high}. Re-activating CE setup.")
                        self.ce_disabled = False
                        self.ce_scan_active = False
                    elif candle_type == "PE" and self.pe_disabled:
                        print(f"[RE-ACTIVATE] PE candle closed at {candle['close']} < Ref High {ref_high}. Re-activating PE setup.")
                        self.pe_disabled = False
                        self.pe_scan_active = False

    def _check_and_set_reference_candle(self, fut_candle):
        """Sets the start-time candle as the reference candle when it closes."""
        if self.reference_candle_fut is not None:
            return

        try:
            c_time = datetime.fromtimestamp(fut_candle["time"]).time()
            start_t = self._parse_time(self.start_time_str) or dtime(9, 17)
            if c_time == start_t:
                self.reference_candle_fut = fut_candle
                self.ref_candle_ts = fut_candle["time"]
                print(f"[REFERENCE] Start time candle ({self.start_time_str}) set as REFERENCE candle!")
                print(f"[REFERENCE] Futures High: {fut_candle['high']}, Low: {fut_candle['low']}")
                self._notify()
        except Exception:
            pass

    def _get_option_reference_candle(self, opt_type):
        """Returns the option candle coincident with the start-time reference candle."""
        if not self.ref_candle_ts:
            return None

        opt_history = self.option_candles.get(opt_type, {})
        c = opt_history.get(self.ref_candle_ts)
        if not c and self.running_opt_candle.get(opt_type):
            rc = self.running_opt_candle[opt_type]
            if rc.get("time") == self.ref_candle_ts:
                c = rc
        return c

    # =========================================================================
    # BREAKOUT DETECTION (CROSSING & OPPOSITE IN-TRADE CHECK)
    # =========================================================================

    def _check_breakout(self, ltp, now):
        if self.state not in ("SCANNING", "IN_TRADE", "TRAILING"):
            return

        start_t = self._parse_time(self.start_time_str) or dtime(9, 17)
        stop_t = self._parse_time(self.stop_time_str) or dtime(10, 45)
        if now.time() < start_t or now.time() >= stop_t:
            return

        if self.reference_candle_fut is None:
            return

        in_trade = self.state in ("IN_TRADE", "TRAILING")

        # Check LONG (Buy CE)
        if self._is_direction_allowed("CE"):
            if not (in_trade and self.direction == "CE"):
                ref_ce = self._get_option_reference_candle("CE")
                if ref_ce and ref_ce.get("high", 0) > 0:
                    ce_ltp = self.option_handler.get_option_ltp(self.strike_ce, "CE")
                    ref_high = ref_ce["high"]
                    threshold = ref_high + self.break_buffer

                    if not getattr(self, "ce_scan_active", False):
                        if ce_ltp > threshold:
                            print(f"[FILTER] CE setup already triggered! Discarding setup. CE LTP {ce_ltp:.2f} > Ref High {ref_high:.2f} + {self.break_buffer}")
                            self.ce_disabled = True
                            return
                        else:
                            self.ce_scan_active = True

                    prev_ltp = self.prev_opt_ltp.get("CE", 0.0)
                    if ce_ltp > threshold and prev_ltp <= threshold:
                        print(f"[ENTRY] LONG CE option crossover breakout! CE LTP {ce_ltp:.2f} > Ref High {ref_high:.2f} + {self.break_buffer} (Prev: {prev_ltp:.2f})")
                        if in_trade:
                            print("[ENTRY] Opposite direction CE breakout while in PE trade! Flipping position.")
                            self._exit_all("FLIP_TO_NEW_SETUP")
                        self.active_opt_strike = self.strike_ce
                        self.active_opt_type = "CE"
                        self.opt_ltp = ce_ltp
                        self._enter_trade("CE", self.reference_candle_fut)
                        return

        # Check SHORT (Buy PE)
        if self._is_direction_allowed("PE"):
            if not (in_trade and self.direction == "PE"):
                ref_pe = self._get_option_reference_candle("PE")
                if ref_pe and ref_pe.get("high", 0) > 0:
                    pe_ltp = self.option_handler.get_option_ltp(self.strike_pe, "PE")
                    ref_high = ref_pe["high"]
                    threshold = ref_high + self.break_buffer

                    if not getattr(self, "pe_scan_active", False):
                        if pe_ltp > threshold:
                            print(f"[FILTER] PE setup already triggered! Discarding setup. PE LTP {pe_ltp:.2f} > Ref High {ref_high:.2f} + {self.break_buffer}")
                            self.pe_disabled = True
                            return
                        else:
                            self.pe_scan_active = True

                    prev_ltp = self.prev_opt_ltp.get("PE", 0.0)
                    if pe_ltp > threshold and prev_ltp <= threshold:
                        print(f"[ENTRY] SHORT PE option crossover breakout! PE LTP {pe_ltp:.2f} > Ref High {ref_high:.2f} + {self.break_buffer} (Prev: {prev_ltp:.2f})")
                        if in_trade:
                            print("[ENTRY] Opposite direction PE breakout while in CE trade! Flipping position.")
                            self._exit_all("FLIP_TO_NEW_SETUP")
                        self.active_opt_strike = self.strike_pe
                        self.active_opt_type = "PE"
                        self.opt_ltp = pe_ltp
                        self._enter_trade("PE", self.reference_candle_fut)
                        return

    # =========================================================================
    # ENTRY
    # =========================================================================

    def _enter_trade(self, opt_type, trigger_candle, force=False):
        # Taking a trade re-enables both directions for opposite trade scanning
        self.ce_disabled = False
        self.pe_disabled = False
        self.ce_scan_active = False
        self.pe_scan_active = False

        ref_opt = self._get_option_reference_candle(opt_type)
        if ref_opt and (ref_opt.get("high", 0) - ref_opt.get("low", 0)) > 0:
            self.opt_candle_size = ref_opt["high"] - ref_opt["low"]
        else:
            fut_size = trigger_candle.get("high", 0) - trigger_candle.get("low", 0)
            self.opt_candle_size = fut_size

        strike = self.strike_ce if opt_type == "CE" else self.strike_pe
        self.entry_price_opt = self.option_handler.get_option_ltp(strike, opt_type)
        if self.entry_price_opt <= 0:
            return

        ep = self.entry_price_opt
        cs = self.opt_candle_size if self.opt_candle_size > 0 else ep * 0.1

        self.option_high_since_entry = ep
        # Fixed SL before T1 = entry - candle_size (no trail before target)
        self.current_sl = ep - cs
        self.trailing_sl = ep - cs

        self.t1_target = ep + cs * self.t1_pct
        self.t2_target = ep + cs * self.t2_pct
        self.t3_target = ep + cs * self.t3_mult

        self.t1_hit = False
        self.t2_hit = False
        self.remaining_qty = self.initial_qty
        self.direction = opt_type

        self.active_trade_candles = dict(self.option_candles[opt_type])
        self.running_active_trade_candle = dict(self.running_opt_candle[opt_type]) if self.running_opt_candle[opt_type] else None
        self.last_active_trade_candle_ts = self.last_opt_candle_ts[opt_type]

        self.state = "IN_TRADE"
        self.trigger_candle = trigger_candle
        self._notify()

        symbol = self.option_handler.get_option_symbol(strike, opt_type)
        if symbol:
            try:
                print(f"[ENTRY] Placing BUY order for {self.initial_qty} qty of {symbol} at Market.")
                self.position_manager.place_order(
                    tradingsymbol=symbol, quantity=self.initial_qty,
                    buy_or_sell='B', exchange="NFO", product_type='M', price_type='MKT'
                )
            except Exception as e:
                print(f"[ERROR] Failed to place entry order: {e}")

    # =========================================================================
    # IN-TRADE MANAGEMENT
    # =========================================================================

    def _check_trade(self, ltp, now):
        if self.state not in ("IN_TRADE", "TRAILING"):
            return
        opt_ltp = self.opt_ltp
        if opt_ltp <= 0:
            return

        # Fixed SL before T1. After T1 hits, trail by trail_points from max option price
        if not self.t1_hit:
            proposed_sl = self.entry_price_opt - self.opt_candle_size
        else:
            proposed_sl = self.option_high_since_entry - self.trail_points

        if proposed_sl != self.current_sl:
            self.current_sl = proposed_sl
            self.trailing_sl = proposed_sl
            self._notify()

        if not self.t1_hit:
            if opt_ltp >= self.t1_target:
                self._exit_partial(self.t1_qty, "T1")
                self.t1_hit = True
                self.current_sl = max(self.current_sl, self.option_high_since_entry - self.trail_points)
                if self.remaining_qty <= 0:
                    exited_dir = self.direction
                    self._reset_trade_state()
                    self.state = "SCANNING"
                    if exited_dir == "CE":
                        self.ce_disabled = True
                    elif exited_dir == "PE":
                        self.pe_disabled = True
                    print(f"[EXIT] Zero quantity remaining after T1 exit. Disabling {exited_dir} until opposite trade is taken.")
                self._notify()
                return

        if self.t1_hit and not self.t2_hit:
            if opt_ltp >= self.t2_target:
                self._exit_partial(self.t2_qty, "T2")
                self.t2_hit = True
                self.state = "TRAILING"
                self.trailing_sl = max(self.current_sl, self.option_high_since_entry - self.trail_points)
                self.current_sl = self.trailing_sl
                if self.remaining_qty <= 0:
                    exited_dir = self.direction
                    self._reset_trade_state()
                    self.state = "SCANNING"
                    if exited_dir == "CE":
                        self.ce_disabled = True
                    elif exited_dir == "PE":
                        self.pe_disabled = True
                    print(f"[EXIT] Zero quantity remaining after T2 exit. Disabling {exited_dir} until opposite trade is taken.")
                self._notify()
                return

        if self.state == "TRAILING":
            if self.t3_target > self.t2_target and opt_ltp >= self.t3_target:
                self._exit_all("T3")
                return

        if opt_ltp <= self.current_sl:
            self._exit_all("SL")

    # =========================================================================
    # EXITS
    # =========================================================================

    def _exit_partial(self, qty, reason):
        if qty <= 0 or self.remaining_qty <= 0:
            return
        qty = min(qty, self.remaining_qty)
        print(f"[EXIT] Executing {reason} exit for {qty} qty at market.")
        opt_type = self.active_opt_type
        strike = self.active_opt_strike
        symbol = self.option_handler.get_option_symbol(strike, opt_type)
        if symbol:
            try:
                self.position_manager.place_order(
                    tradingsymbol=symbol, quantity=qty,
                    buy_or_sell='S', exchange="NFO", product_type='M', price_type='MKT')
            except Exception:
                pass
        self.remaining_qty -= qty

    def _exit_all(self, reason):
        print(f"[EXIT] Executing ALL remaining qty ({self.remaining_qty}) for reason: {reason}")
        exited_dir = self.direction
        self._exit_partial(self.remaining_qty, reason)
        self._reset_trade_state()
        self.state = "SCANNING"

        if reason != "FLIP_TO_NEW_SETUP" and exited_dir:
            if exited_dir == "CE":
                self.ce_disabled = True
            elif exited_dir == "PE":
                self.pe_disabled = True
            print(f"[FILTER] Direction {exited_dir} disabled after {reason} exit until opposite direction trade is taken.")

        self._notify()

    def _panic_exit_internal(self):
        if self.remaining_qty > 0 and self.state in ("IN_TRADE", "TRAILING"):
            self._exit_partial(self.remaining_qty, "PANIC")
        self._reset_trade_state()
        self.ce_disabled = False
        self.pe_disabled = False
        self.ce_scan_active = False
        self.pe_scan_active = False

    def _reset_trade_state(self):
        self.entry_price_opt = 0.0
        self.opt_candle_size = 0.0
        self.option_high_since_entry = 0.0
        self.t1_target = 0.0
        self.t2_target = 0.0
        self.t3_target = 0.0
        self.current_sl = 0.0
        self.trailing_sl = 0.0
        self.t1_hit = False
        self.t2_hit = False
        self.remaining_qty = 0

    # =========================================================================
    # NOTIFICATION
    # =========================================================================

    def _notify(self):
        try:
            is_long = self._is_direction_allowed("CE") if self.reference_candle_fut else False
            is_short = self._is_direction_allowed("PE") if self.reference_candle_fut else False

            if is_long and is_short:
                setup_signal = "L/S"
            elif is_long:
                setup_signal = "LONG"
            elif is_short:
                setup_signal = "SHORT"
            else:
                setup_signal = None

            tc = self.reference_candle_fut or self.trigger_candle
            tc_ts = ""
            if tc:
                try:
                    tc_ts = datetime.fromtimestamp(tc.get("time", 0)).strftime("%H:%M")
                except Exception:
                    tc_ts = ""

            def get_opt_candle_dict(opt_type):
                c = self._get_option_reference_candle(opt_type)
                if c:
                    try:
                        ts_str = datetime.fromtimestamp(c.get("time", 0)).strftime("%H:%M")
                    except Exception:
                        ts_str = ""
                    return {
                        "open_time": ts_str,
                        "high": c.get("high", 0),
                        "low": c.get("low", 0),
                    }
                return {}

            ce_candle_data = get_opt_candle_dict("CE")
            pe_candle_data = get_opt_candle_dict("PE")

            display_move = 0
            display_range = 0
            if self.prev_day_close > 0:
                app_high, app_low = self.day_high, self.day_low
                if app_high is not None and app_low is not None and app_high > 0:
                    display_move = max(abs(app_high - self.prev_day_close), abs(app_low - self.prev_day_close))
                    display_range = app_high - app_low

            data = {
                "state": self.state,
                "setup_signal": setup_signal,
                "trigger_candle": {
                    "open_time": tc_ts,
                    "high": tc.get("high", 0) if tc else 0,
                    "low": tc.get("low", 0) if tc else 0,
                    "size": round((tc.get("high", 0) - tc.get("low", 0)), 2) if tc else 0
                } if tc else {},
                "ce_candle": ce_candle_data,
                "pe_candle": pe_candle_data,
                "entry_price_opt": self.entry_price_opt,
                "current_sl": self.current_sl,
                "t1_target": self.t1_target,
                "t1_hit": self.t1_hit,
                "t2_target": self.t2_target,
                "t2_hit": self.t2_hit,
                "t3_target": self.t3_target,
                "trailing_sl": self.trailing_sl,
                "remaining_qty": self.remaining_qty,
                "premarket_ok": self.premarket_ok,
                "prev_close": self.prev_day_close,
                "day_range": round(display_range, 2),
                "premarket_move": round(display_move, 2),
                "opt_ltp": self.opt_ltp,
                "opt_candle_size": round(self.opt_candle_size, 2),
                "ce_disabled": self.ce_disabled,
                "pe_disabled": self.pe_disabled,
            }
            if self.bridge:
                self.bridge.notify("updateNiftyState", data)
        except Exception:
            pass

    def get_state_dict(self):
        self._notify()
        return {
            "state": self.state,
            "premarket_ok": self.premarket_ok,
            "prev_close": self.prev_day_close,
            "remaining_qty": self.remaining_qty,
        }
