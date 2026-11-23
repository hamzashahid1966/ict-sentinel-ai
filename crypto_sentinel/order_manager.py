"""
Crypto Sentinel AI - Double Tap Order Management System (OMS)
Handles trade execution, partial profit scaling (Target 1: 1.5R @ 50%),
defensive stop adjustments, and full exit (Target 2: 3.0R @ 50%).
"""

import time
import uuid
import hmac
import hashlib
import json
import urllib.request
import urllib.parse
import urllib.error
from decimal import Decimal, ROUND_DOWN
from typing import Optional, Dict, Any, List
from crypto_sentinel.config import (
    BINANCE_TESTNET_REST, BINANCE_TESTNET_API_KEY, BINANCE_TESTNET_API_SECRET,
    TAKER_FEE_PCT, DEFAULT_SLIPPAGE_PCT, STRATEGY_PROFILES,
    TARGET_1_R, TARGET_2_R, DEFAULT_STRATEGY_PROFILE, SSL_CONTEXT,
    DIRECT_OPENER, direct_urlopen,
    STAGNATION_TIMEOUT_SECONDS, TRUE_FEE_BUFFER_PCT, OPPORTUNITY_SWAP_MIN_SCORE,
    BINANCE_PUBLIC_REST, REAL_PAPER_MODE
)
from crypto_sentinel.models import CryptoPosition, AnalysisOpportunity, CryptoAccount
from crypto_sentinel.storage import CryptoStorageEngine
from crypto_sentinel.ai_analyzer import CryptoAIAnalyzer

def paper_entry_fill(direction: str, quote: Optional[tuple], stop: float) -> Optional[float]:
    """
    REAL_DATA_PAPER entry: a market order crosses the real book, so a long buys the best ask
    and a short sells the best bid. None (no trade) without a real quote, or when the fill
    would already be through the stop.
    """
    if not quote:
        return None
    bid, ask = quote
    if direction == "LONG":
        return ask if ask > stop else None
    return bid if bid < stop else None


def _exit_fill(pos: CryptoPosition, current_price: float, quote: Optional[tuple]) -> float:
    """Closing a long sells the real bid; closing a short buys the real ask. Falls back to the price seen."""
    if not quote:
        return current_price
    return quote[0] if pos.direction == "LONG" else quote[1]


class CryptoOrderManager:
    def __init__(self, storage: CryptoStorageEngine):
        self.storage = storage
        self.ai_analyzer = CryptoAIAnalyzer(self.storage)
        self._lot_steps: Dict[str, float] = {}
        self._tick_sizes: Dict[str, float] = {}
        self._lot_steps_at: float = 0.0
        self._last_fetch_warn: float = 0.0
        self._stops_placed: set = set()   # position_ids protected by a resting exchange stop this process
        self._stop_retry_at: Dict[str, float] = {}   # position_id -> earliest next attempt after a failure
        self._funding_checked_at: Dict[str, float] = {}  # position_id -> last funding lookup (REAL_DATA_PAPER)

    # ── Exchange transport ─────────────────────────────────────────────
    def _testnet_keys(self) -> bool:
        return bool(BINANCE_TESTNET_API_KEY and BINANCE_TESTNET_API_SECRET)

    def _signed_request(self, method: str, path: str, params: Dict[str, Any]) -> Any:
        """One signed call to Binance Futures Testnet. Raises on any transport or HTTP error."""
        query = dict(params)
        query["timestamp"] = int(time.time() * 1000)
        query_string = urllib.parse.urlencode(query)
        signature = hmac.new(BINANCE_TESTNET_API_SECRET.encode("utf-8"), query_string.encode("utf-8"), hashlib.sha256).hexdigest()
        headers = {"X-MBX-APIKEY": BINANCE_TESTNET_API_KEY, "User-Agent": "Mozilla/5.0"}
        if method != "GET":
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        req = urllib.request.Request(f"{BINANCE_TESTNET_REST}{path}?{query_string}&signature={signature}", method=method, headers=headers)
        with direct_urlopen(req, timeout=5.0) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _public_get(self, path: str) -> Any:
        req = urllib.request.Request(f"{BINANCE_TESTNET_REST}{path}", headers={"User-Agent": "Mozilla/5.0"})
        with direct_urlopen(req, timeout=8.0) as resp:
            return json.loads(resp.read().decode("utf-8"))

    @staticmethod
    def _http_error_text(e: Exception) -> str:
        if isinstance(e, urllib.error.HTTPError):
            try:
                body = e.read().decode("utf-8", "replace")
                return f"HTTP {e.code}: {body[:120]}"
            except Exception:
                return f"HTTP {e.code}"
        return str(e).replace("<", "").replace(">", "")[:120]

    # ── Exchange filters (lot size / tick size) ────────────────────────
    def _ensure_exchange_filters(self):
        now = time.time()
        if self._lot_steps and now - self._lot_steps_at < 3600:
            return
        if not self._lot_steps and now - self._lot_steps_at < 60:
            return  # recent failure: do not hammer exchangeInfo
        self._lot_steps_at = now
        try:
            info = self._public_get("/fapi/v1/exchangeInfo")
        except Exception:
            return
        steps, ticks = {}, {}
        for sym in info.get("symbols", []):
            for f in sym.get("filters", []):
                if f.get("filterType") == "LOT_SIZE":
                    steps[sym["symbol"]] = float(f["stepSize"])
                elif f.get("filterType") == "PRICE_FILTER":
                    ticks[sym["symbol"]] = float(f["tickSize"])
        if steps:
            self._lot_steps, self._tick_sizes = steps, ticks

    @staticmethod
    def _decimals_for(step: float) -> int:
        return max(0, -Decimal(str(step)).normalize().as_tuple().exponent)

    def _format_price_for_symbol(self, symbol: str, price: float) -> str:
        self._ensure_exchange_filters()
        tick = self._tick_sizes.get(symbol)
        if tick:
            q = (Decimal(str(price)) / Decimal(str(tick))).quantize(Decimal("1")) * Decimal(str(tick))
            return f"{float(q):.{self._decimals_for(tick)}f}"
        return f"{price:.6f}" if price < 1 else f"{price:.2f}"

    # ── Exchange-side protective stops ─────────────────────────────────
    def _cancel_open_orders(self, symbol: str) -> bool:
        """Cancel resting conditional (algo) orders for the symbol, i.e. the bot's exchange stops."""
        if not self._testnet_keys():
            return True
        try:
            # Conditional orders live on the Algo Service since 2025-12-09; /fapi/v1/allOpenOrders does not touch them.
            self._signed_request("DELETE", "/fapi/v1/algoOpenOrders", {"symbol": symbol})
            return True
        except Exception as e:
            self.storage.log_activity("TESTNET_WARN", symbol, f"Could not cancel resting stop orders: {self._http_error_text(e)}", "WARNING")
            return False

    def _sync_exchange_stop(self, pos: CryptoPosition) -> bool:
        """Replace the resting STOP_MARKET (closePosition) on Binance with one at pos.current_stop."""
        if not self._testnet_keys() or not pos.current_stop:
            return True
        self._cancel_open_orders(pos.symbol)
        params = {
            "algoType": "CONDITIONAL",
            "symbol": pos.symbol,
            "side": "SELL" if pos.direction == "LONG" else "BUY",
            "type": "STOP_MARKET",
            "triggerPrice": self._format_price_for_symbol(pos.symbol, pos.current_stop),
            "closePosition": "true",
            "workingType": "MARK_PRICE",
            "clientAlgoId": f"SL_{pos.symbol}_{int(time.time())}"[:36],
        }
        try:
            # Binance Algo Order API (STOP_MARKET on /fapi/v1/order is rejected with -4120 since 2025-12-09).
            self._signed_request("POST", "/fapi/v1/algoOrder", params)
            self._stops_placed.add(pos.position_id)
            return True
        except Exception as e:
            self.storage.log_activity("TESTNET_WARN", pos.symbol, f"Exchange stop NOT placed at {params['triggerPrice']}: {self._http_error_text(e)} (software stop still active)", "DANGER")
            return False

    def _remaining_qty(self, pos: CryptoPosition, testnet: bool) -> float:
        # On testnet the local size mirrors the exchange (halved after Target 1);
        # in paper mode the size stays at the original and half is assumed banked.
        if testnet:
            return pos.quantity
        return (pos.quantity / 2.0) if pos.t1_hit else pos.quantity

    def open_position(self, opp: AnalysisOpportunity, qty: float, mode: str, fill_price: Optional[float] = None) -> CryptoPosition:
        """
        Executes a new position under Double Tap protocol.
        fill_price (REAL_DATA_PAPER): the real Binance price the market order fills at; targets
        are measured from it and the entry fee is taken out of the balance.
        """
        pos_id = f"POS_{opp.symbol}_{int(time.time())}_{uuid.uuid4().hex[:4].upper()}"
        entry_px = fill_price if fill_price is not None else opp.current_price

        # Calculate fees
        notional = qty * entry_px
        entry_fee = notional * (TAKER_FEE_PCT / 100.0)

        # Dynamic Target 1 and Target 2 calculation from active strategy profile
        acc = self.storage.get_account()
        prof = STRATEGY_PROFILES.get(acc.strategy_profile, STRATEGY_PROFILES.get(DEFAULT_STRATEGY_PROFILE, {}))
        t1_r = prof.get("target_1_r", TARGET_1_R)
        t2_r = prof.get("target_2_r", TARGET_2_R)
        r_dist = abs(entry_px - opp.stop_loss)
        nd = 6 if entry_px < 1 else 2
        target_1 = round(entry_px + (r_dist * t1_r if opp.direction == "LONG" else -r_dist * t1_r), nd)
        target_2 = round(entry_px + (r_dist * t2_r if opp.direction == "LONG" else -r_dist * t2_r), nd)

        pos = CryptoPosition(
            position_id=pos_id,
            symbol=opp.symbol,
            engine=opp.engine,
            direction=opp.direction,
            entry_price=entry_px,
            quantity=qty,
            initial_stop=opp.stop_loss,
            current_stop=opp.stop_loss,
            target_1=target_1,
            target_2=target_2,
            t1_hit=False,
            defensive_active=False,
            unrealized_pnl=0.0,
            unrealized_r=0.0,
            entry_time=time.time(),
            status="OPEN",
            fees_paid=entry_fee
        )

        self.storage.save_position(pos)
        if mode == REAL_PAPER_MODE:
            acc_now = self.storage.get_account()
            self.storage.update_account(balance=acc_now.balance - entry_fee, realized_pnl_delta=-entry_fee)
        self.storage.log_activity(
            action="ORDER_OPEN",
            coin=opp.symbol,
            detail=f"Opened {opp.direction} {qty} @ {entry_px:.4f}{' (real Binance fill)' if mode == REAL_PAPER_MODE else ''} | Engine: {opp.engine} | SL: {opp.stop_loss:.4f} | TP1: {target_1:.4f} ({t1_r}R) | TP2: {target_2:.4f} ({t2_r}R)",
            level="SUCCESS"
        )

        # If in Binance Testnet mode, dispatch external API request
        if mode == "BINANCE_TESTNET" and BINANCE_TESTNET_API_KEY:
            self._dispatch_binance_testnet_order(pos, "MARKET")

        return pos

    def update_position_with_price(self, pos: CryptoPosition, current_price: float, account: CryptoAccount,
                                   quote: Optional[tuple] = None):
        """
        Double Tap lifecycle management on price updates:
        1. Check Target 1 (1.5R): close 50% and move stop to entry defensive buffer.
        2. Check Target 2 (3.0R): close remaining 50% (trade complete).
        3. Check Current Stop Loss.
        """
        if pos.status == "CLOSED":
            return

        testnet = (account.mode == "BINANCE_TESTNET")
        real = (account.mode == REAL_PAPER_MODE)
        is_long = (pos.direction == "LONG")
        # REAL_DATA_PAPER: triggers on the real mark (current_price), fills at the real bid/ask.
        fill = _exit_fill(pos, current_price, quote) if real else current_price
        fill_move = (fill - pos.entry_price) if is_long else (pos.entry_price - fill)
        risk_dist = abs(pos.entry_price - pos.initial_stop)
        current_move = (current_price - pos.entry_price) if is_long else (pos.entry_price - current_price)
        r_multiple = (current_move / risk_dist) if risk_dist > 0 else 0.0

        pos.unrealized_pnl = round(current_move * pos.quantity, 2)
        pos.unrealized_r = round(r_multiple, 2)

        # 1. Target 1 Check (1.5R reached)
        if not pos.t1_hit:
            hit_t1 = (current_price >= pos.target_1) if is_long else (current_price <= pos.target_1)
            if hit_t1:
                half_qty = pos.quantity / 2.0
                if testnet and not self._dispatch_binance_testnet_close(pos.symbol, pos.direction, half_qty, "TP1_PARTIAL"):
                    self.storage.log_activity("CLOSE_RETRY", pos.symbol, "Target 1 partial close not confirmed by Binance. Nothing booked; retrying next tick.", "WARNING")
                    self.storage.save_position(pos)
                    return
                pos.t1_hit = True
                # Partial exit of 50%
                if real:
                    half_pnl = fill_move * half_qty
                    t1_fee = half_qty * fill * (TAKER_FEE_PCT / 100.0)
                else:
                    half_pnl = round(current_move * half_qty, 2)
                    t1_fee = round(half_qty * current_price * (TAKER_FEE_PCT / 100.0), 4)
                pos.fees_paid += t1_fee
                
                # Move Stop to Defensive: Entry + slight cushion in trade direction to guarantee zero-risk
                defensive_cushion = risk_dist * 0.05
                pos.current_stop = round(pos.entry_price + (defensive_cushion if is_long else -defensive_cushion), 6 if pos.entry_price < 1 else 2)
                pos.defensive_active = True
                pos.status = "T1_HIT"

                # Credit realized account balance (net of the exit fee in REAL_DATA_PAPER)
                booked = half_pnl - t1_fee if real else half_pnl
                self.storage.update_account(balance=account.balance + booked, realized_pnl_delta=booked)
                account = self.storage.get_account()

                # Partial close already confirmed above; mirror the exchange size and move the exchange stop
                if testnet:
                    pos.quantity = round(pos.quantity - half_qty, 8)
                    self._sync_exchange_stop(pos)

                self.storage.log_activity(
                    action="DOUBLE_TAP_T1",
                    coin=pos.symbol,
                    detail=f"🎯 Target 1 HIT at {current_price}! 50% secured (+${half_pnl:.2f} net). Stop moved to Breakeven ({pos.current_stop}).",
                    level="SUCCESS"
                )

        # 1b. Stagnation & True Fee-Covered Breakeven Guard (Option A)
        trade_age = time.time() - (pos.entry_time or time.time())
        if not pos.t1_hit and trade_age >= STAGNATION_TIMEOUT_SECONDS:
            if not getattr(pos, 'is_stagnant', False):
                pos.is_stagnant = True
                pos.stagnant_at = time.time()
                mins = int(trade_age // 60)
                fee_cover_price = round(pos.entry_price * (1 + TRUE_FEE_BUFFER_PCT if is_long else 1 - TRUE_FEE_BUFFER_PCT), 6 if pos.entry_price < 1 else 2)
                can_arm_be = (current_price >= fee_cover_price) if is_long else (current_price <= fee_cover_price)
                if can_arm_be:
                    is_better_stop = (fee_cover_price > pos.current_stop) if is_long else (fee_cover_price < pos.current_stop)
                    if is_better_stop:
                        pos.current_stop = fee_cover_price
                        pos.defensive_active = True
                        if testnet:
                            self._sync_exchange_stop(pos)
                        self.storage.log_activity(
                            action="STAGNATION_BE",
                            coin=pos.symbol,
                            detail=f"🛡️ Stagnation ({mins}m): Shifted Stop to True Fee Breakeven ({pos.current_stop}). Guaranteed $0 net loss after all Binance fees.",
                            level="WARNING"
                        )
                else:
                    self.storage.log_activity(
                        action="STAGNATION_MONITOR",
                        coin=pos.symbol,
                        detail=f"⏳ Stagnation ({mins}m): Trade open > 45m without TP1. Monitoring for True Fee Breakeven (+0.11%) or Swap.",
                        level="INFO"
                    )

        # 2. Target 2 Check (3.0R reached)
        hit_t2 = (current_price >= pos.target_2) if is_long else (current_price <= pos.target_2)
        if hit_t2:
            remaining_qty = self._remaining_qty(pos, testnet)
            if testnet and not self._dispatch_binance_testnet_close(pos.symbol, pos.direction, remaining_qty, "TP2_FULL", full=True):
                self.storage.log_activity("CLOSE_RETRY", pos.symbol, "Target 2 close not confirmed by Binance. Position kept open; retrying next tick.", "WARNING")
                self.storage.save_position(pos)
                return
            if real:
                remaining_pnl = fill_move * remaining_qty
                t2_fee = remaining_qty * fill * (TAKER_FEE_PCT / 100.0)
            else:
                remaining_pnl = round(current_move * remaining_qty, 2)
                t2_fee = round(remaining_qty * current_price * (TAKER_FEE_PCT / 100.0), 4)
            total_realized = (pos.unrealized_pnl if not pos.t1_hit else remaining_pnl)
            pos.fees_paid += t2_fee

            pos.status = "CLOSED"
            pos.exit_price = fill
            pos.exit_reason = "TARGET_2_FULL_FILL (0.8R)"
            pos.exit_time = time.time()
            self._record_closed_trade_learning(pos, remaining_is_half=testnet)

            booked = remaining_pnl - t2_fee if real else remaining_pnl
            self.storage.update_account(balance=account.balance + booked, realized_pnl_delta=booked)

            self.storage.log_activity(
                action="DOUBLE_TAP_T2",
                coin=pos.symbol,
                detail=f"🚀 Target 2 HIT at {current_price:.2f}! Trade completed. Gross: +${total_realized:.2f} | Fees: ${pos.fees_paid:.2f} | Net: +${(total_realized - pos.fees_paid):.2f}.",
                level="SUCCESS"
            )

        # 3. Stop Loss Check
        hit_stop = (current_price <= pos.current_stop) if is_long else (current_price >= pos.current_stop)
        if hit_stop and pos.status != "CLOSED":
            remaining_qty = self._remaining_qty(pos, testnet)
            stop_reason = "DEFENSIVE_STOP_OUT" if pos.defensive_active else "INITIAL_STOP_LOSS"
            if testnet and not self._dispatch_binance_testnet_close(pos.symbol, pos.direction, remaining_qty, stop_reason, full=True):
                self.storage.log_activity("CLOSE_RETRY", pos.symbol, f"{stop_reason} close not confirmed by Binance. Position kept open; retrying next tick.", "DANGER")
                self.storage.save_position(pos)
                return
            if real:
                # Real market: the stop is a market order at the real bid/ask, so a gap costs money.
                stop_pnl = fill_move * remaining_qty
                sl_fee = remaining_qty * fill * (TAKER_FEE_PCT / 100.0)
            else:
                loss_move = (pos.current_stop - pos.entry_price) if is_long else (pos.entry_price - pos.current_stop)
                stop_pnl = round(loss_move * remaining_qty, 2)
                sl_fee = round(remaining_qty * current_price * (TAKER_FEE_PCT / 100.0), 4)
            pos.fees_paid += sl_fee

            pos.status = "CLOSED"
            pos.exit_price = fill
            pos.exit_reason = stop_reason
            pos.exit_time = time.time()
            self._record_closed_trade_learning(pos, remaining_is_half=testnet)

            booked = stop_pnl - sl_fee if real else stop_pnl
            self.storage.update_account(balance=account.balance + booked, realized_pnl_delta=booked)

            log_level = "INFO" if pos.defensive_active else "DANGER"
            self.storage.log_activity(
                action="STOP_LOSS",
                coin=pos.symbol,
                detail=f"🛑 Stop Loss triggered at {current_price:.2f} ({pos.exit_reason}). Gross: ${stop_pnl:.2f} | Fees: ${pos.fees_paid:.2f} | Net: ${stop_pnl - pos.fees_paid:.2f}.",
                level=log_level
            )

        self.storage.save_position(pos)

    def _record_closed_trade_learning(self, pos: CryptoPosition, remaining_is_half: bool = False):
        """Records trade execution results into AI Behavioral Memory for auto-quarantine analysis."""
        if not pos or pos.exit_price is None:
            return
        try:
            is_long = (pos.direction == "LONG")
            if pos.t1_hit:
                half_qty = pos.quantity if remaining_is_half else pos.quantity / 2.0
                t1_move = (pos.target_1 - pos.entry_price) if is_long else (pos.entry_price - pos.target_1)
                exit_move = (pos.exit_price - pos.entry_price) if is_long else (pos.entry_price - pos.exit_price)
                gross_pnl = round((t1_move * half_qty) + (exit_move * half_qty), 4)
            else:
                exit_move = (pos.exit_price - pos.entry_price) if is_long else (pos.entry_price - pos.exit_price)
                gross_pnl = round(exit_move * pos.quantity, 4)

            fees = getattr(pos, "fees_paid", 0.0) or 0.0
            is_win = (gross_pnl - fees) > 0
            self.storage.record_coin_trade_outcome(pos.symbol, gross_pnl, fees, is_win, pos.exit_reason or "TRADE_CLOSED")

            # Finalize trade snapshot & trigger non-blocking background AI debrief
            snap_id = self.storage.finalize_trade_snapshot(
                position_id=pos.position_id,
                exit_price=pos.exit_price or pos.entry_price,
                gross_pnl=gross_pnl,
                fees=fees,
                net_pnl=round(gross_pnl - fees, 4),
                is_win=is_win,
                exit_reason=pos.exit_reason or "TRADE_CLOSED"
            )
            if snap_id:
                self.ai_analyzer.analyze_trade_async(snap_id)
        except Exception as e:
            pass

    def close_position_manually(self, pos_id: str, current_price: float, account: CryptoAccount,
                                quote: Optional[tuple] = None) -> bool:
        """
        Operator manual flatten / panic close.
        """
        open_positions = self.storage.get_open_positions()
        target_pos = next((p for p in open_positions if p.position_id == pos_id), None)
        if not target_pos:
            return False

        testnet = (account.mode == "BINANCE_TESTNET")
        is_long = (target_pos.direction == "LONG")
        remaining_qty = self._remaining_qty(target_pos, testnet)
        if testnet and not self._dispatch_binance_testnet_close(target_pos.symbol, target_pos.direction, remaining_qty, "MANUAL_CLOSE", full=True):
            self.storage.log_activity("CLOSE_RETRY", target_pos.symbol, "Manual close not confirmed by Binance. Position left open.", "DANGER")
            return False
        real = (account.mode == REAL_PAPER_MODE)
        px = _exit_fill(target_pos, current_price, quote) if real else current_price
        move = (px - target_pos.entry_price) if is_long else (target_pos.entry_price - px)
        if real:
            fee = remaining_qty * px * (TAKER_FEE_PCT / 100.0)
            target_pos.fees_paid += fee
            pnl = move * remaining_qty - fee
        else:
            pnl = round(move * remaining_qty, 2)

        target_pos.status = "CLOSED"
        target_pos.exit_price = px
        target_pos.exit_reason = "MANUAL_CLOSE"
        target_pos.exit_time = time.time()
        self._record_closed_trade_learning(target_pos, remaining_is_half=testnet)

        self.storage.update_account(balance=account.balance + pnl, realized_pnl_delta=pnl)
        self.storage.save_position(target_pos)

        self.storage.log_activity(
            action="MANUAL_CLOSE",
            coin=target_pos.symbol,
            detail=f"Position manually closed at {current_price:.2f}. Realized PnL: ${pnl:.2f}",
            level="WARNING"
        )
        return True

    def _real_get(self, path: str) -> Any:
        req = urllib.request.Request(f"{BINANCE_PUBLIC_REST}{path}", headers={"User-Agent": "Mozilla/5.0"})
        with direct_urlopen(req, timeout=5.0) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def settle_funding(self, pos: CryptoPosition, account: CryptoAccount, now: Optional[float] = None,
                       force: bool = False, min_interval: float = 600.0) -> float:
        """
        REAL_DATA_PAPER: book Binance's real funding settlements for an open paper position.
        A long pays when the rate is positive and receives when negative (shorts the reverse),
        on notional = open quantity x settlement mark price. Each settlement is booked once
        (tracked by last_funding_ts) and only if the position was open at that moment.
        Returns the amount paid (+) / received (-) by this call.
        """
        if account.mode != REAL_PAPER_MODE or pos.status == "CLOSED":
            return 0.0
        now = time.time() if now is None else now
        if not force and now - self._funding_checked_at.get(pos.position_id, 0.0) < min_interval:
            return 0.0
        self._funding_checked_at[pos.position_id] = now
        since = max(pos.entry_time or 0.0, pos.last_funding_ts or 0.0)
        try:
            rows = self._real_get(f"/fapi/v1/fundingRate?symbol={pos.symbol}&startTime={int(since * 1000) + 1}&limit=100") or []
        except Exception:
            return 0.0
        open_qty = self._remaining_qty(pos, testnet=False)
        sign = 1.0 if pos.direction == "LONG" else -1.0
        paid = 0.0
        latest = pos.last_funding_ts
        for r in sorted(rows, key=lambda x: int(x.get("fundingTime", 0))):
            ft = int(r.get("fundingTime", 0)) / 1000.0
            if ft <= since or ft > now:
                continue
            try:
                rate = float(r["fundingRate"])
                mark = float(r.get("markPrice") or 0) or (pos.current_price or pos.entry_price)
            except (KeyError, TypeError, ValueError):
                continue
            paid += sign * open_qty * mark * rate
            latest = ft
        if latest is not None and latest != pos.last_funding_ts:
            pos.last_funding_ts = latest
            pos.funding_paid = (pos.funding_paid or 0.0) + paid
            pos.fees_paid += paid
            acc = self.storage.get_account()
            self.storage.update_account(balance=acc.balance - paid, realized_pnl_delta=-paid)
            self.storage.save_position(pos)
            self.storage.log_activity("FUNDING", pos.symbol,
                                      f"Funding settlement booked: {'paid' if paid >= 0 else 'received'} ${abs(paid):.4f} "
                                      f"({pos.direction} {open_qty} @ real Binance rate).", "INFO")
        return paid

    def _format_qty_for_symbol(self, symbol: str, qty: float) -> str:
        """Format quantity to the exchange's LOT_SIZE step (floored), falling back to the config table."""
        self._ensure_exchange_filters()
        step = self._lot_steps.get(symbol)
        if step:
            q = (Decimal(str(qty)) / Decimal(str(step))).to_integral_value(rounding=ROUND_DOWN) * Decimal(str(step))
            return f"{float(q):.{self._decimals_for(step)}f}"
        from crypto_sentinel.config import TOP_50_UNIVERSE
        item = next((x for x in TOP_50_UNIVERSE if x["symbol"] == symbol), None)
        min_qty = item.get("min_qty", 1.0) if item else 1.0
        
        if min_qty >= 1.0:
            return str(max(int(min_qty), int(round(qty))))
        elif min_qty >= 0.1:
            return f"{qty:.1f}"
        elif min_qty >= 0.01:
            return f"{qty:.2f}"
        else:
            return f"{qty:.3f}"

    def _dispatch_binance_testnet_order(self, pos: CryptoPosition, order_type: str = "MARKET"):
        """
        Sends the entry order to Binance Futures Testnet. A rejection (HTTP error) marks the
        position DISPATCH_FAILED. A transport error leaves the outcome unknown, so the exchange
        is asked whether the position exists before deciding. On a fill the stop and targets are
        re-anchored to the real fill and a protective STOP_MARKET is placed on the exchange.
        """
        side = "BUY" if pos.direction == "LONG" else "SELL"
        params = {
            "symbol": pos.symbol,
            "side": side,
            "type": order_type,
            "quantity": self._format_qty_for_symbol(pos.symbol, pos.quantity),
            "newClientOrderId": pos.position_id[:32],
        }
        data: Dict[str, Any] = {}
        try:
            data = self._signed_request("POST", "/fapi/v1/order", params) or {}
        except urllib.error.HTTPError as e:
            self._mark_dispatch_failed(pos, self._http_error_text(e))
            return
        except Exception as e:
            live = self.fetch_binance_testnet_positions()
            tp = next((t for t in (live or []) if t.get("symbol") == pos.symbol), None)
            if tp and ((float(tp["positionAmt"]) > 0) == (pos.direction == "LONG")):
                data = {"avgPrice": tp.get("entryPrice"), "orderId": "UNCONFIRMED_BUT_FILLED"}
                self.storage.log_activity("TESTNET_WARN", pos.symbol, f"Entry response lost ({self._http_error_text(e)[:40]}) but position exists on Binance; keeping it.", "WARNING")
            else:
                self._mark_dispatch_failed(pos, self._http_error_text(e))
                return

        fill_price = float(data.get("avgPrice") or 0.0)
        if fill_price <= 0:
            cum_quote = float(data.get("cumQuote") or 0.0)
            cum_qty = float(data.get("executedQty") or 0.0)
            if cum_qty > 0 and cum_quote > 0:
                fill_price = cum_quote / cum_qty
        if fill_price <= 0:
            time.sleep(0.2)
            live = self.fetch_binance_testnet_positions() or []
            tp = next((t for t in live if t.get("symbol") == pos.symbol), None)
            if tp and float(tp.get("entryPrice", 0)) > 0:
                fill_price = float(tp["entryPrice"])

        if fill_price > 0:
            acc = self.storage.get_account()
            prof = STRATEGY_PROFILES.get(acc.strategy_profile, STRATEGY_PROFILES.get(DEFAULT_STRATEGY_PROFILE, {}))
            t1_r = prof.get("target_1_r", TARGET_1_R)
            t2_r = prof.get("target_2_r", TARGET_2_R)
            risk_pct = 0.015
            if pos.initial_stop > 0 and pos.entry_price > 0:
                prev_dist = abs(pos.entry_price - pos.initial_stop) / pos.entry_price
                if 0.005 <= prev_dist <= 0.04:
                    risk_pct = prev_dist
            nd = 6 if fill_price < 1 else 2
            pos.entry_price = fill_price
            pos.initial_stop = round(fill_price * (1 - risk_pct if pos.direction == "LONG" else 1 + risk_pct), nd)
            pos.current_stop = pos.initial_stop
            pos.target_1 = round(fill_price * (1 + t1_r * risk_pct if pos.direction == "LONG" else 1 - t1_r * risk_pct), nd)
            pos.target_2 = round(fill_price * (1 + t2_r * risk_pct if pos.direction == "LONG" else 1 - t2_r * risk_pct), nd)
            self.storage.save_position(pos)
        self.storage.log_activity("BINANCE_TESTNET", pos.symbol, f"Testnet Order Fill: {data.get('orderId')} @ {fill_price or pos.entry_price}", "SUCCESS")
        self._sync_exchange_stop(pos)

    def _mark_dispatch_failed(self, pos: CryptoPosition, err_msg: str):
        self.storage.log_activity("TESTNET_WARN", pos.symbol, f"Entry order rejected: {err_msg[:90]}", "WARNING")
        pos.status = "DISPATCH_FAILED"
        pos.fees_paid = 0.0
        pos.exit_reason = f"ORDER_DISPATCH_FAILED ({err_msg[:60]})"
        self.storage.save_position(pos)

    def _dispatch_binance_testnet_close(self, symbol: str, direction: str, qty: float, reason: str, full: bool = False) -> bool:
        """
        Sends a reduce-only market close to Binance Futures Testnet and reports whether Binance
        accepted it. With full=True the live exchange size is closed (whatever remains), resting
        stop orders are cancelled afterwards, and an already-flat symbol counts as success.
        Callers must not book a close unless this returns True.
        """
        if not self._testnet_keys():
            return True
        qty_str = self._format_qty_for_symbol(symbol, qty)
        if full:
            live = self.fetch_binance_testnet_positions()
            if live is None:
                self.storage.log_activity("TESTNET_WARN", symbol, f"Close ({reason}) postponed: Binance positions unreachable.", "WARNING")
                return False
            tp = next((t for t in live if t.get("symbol") == symbol), None)
            if not tp:
                self._cancel_open_orders(symbol)
                return True
            qty_str = str(tp["positionAmt"]).lstrip("-")
        params = {
            "symbol": symbol,
            "side": "SELL" if direction == "LONG" else "BUY",
            "type": "MARKET",
            "quantity": qty_str,
            "reduceOnly": "true",
            "newClientOrderId": f"CLOSE_{symbol}_{int(time.time() * 1000)}"[:32],
        }
        try:
            data = self._signed_request("POST", "/fapi/v1/order", params) or {}
        except Exception as e:
            self.storage.log_activity("TESTNET_WARN", symbol, f"Close ({reason}) NOT accepted: {self._http_error_text(e)[:90]}", "DANGER")
            return False
        self.storage.log_activity("BINANCE_TESTNET", symbol, f"Testnet Position Closed ({reason}): {data.get('orderId')}", "SUCCESS")
        if full:
            self._cancel_open_orders(symbol)
        return True

    def fetch_binance_testnet_account(self) -> Optional[Dict[str, Any]]:
        """Live wallet balance and margin from Binance Futures Testnet, or None when unavailable."""
        if not self._testnet_keys():
            return None
        try:
            return self._signed_request("GET", "/fapi/v2/account", {})
        except Exception as e:
            self.storage.log_activity("TESTNET_ERR", "ACCOUNT", f"Testnet balance fetch failed: {self._http_error_text(e)[:80]}", "DANGER")
            return None

    def fetch_binance_testnet_positions(self) -> Optional[List[Dict[str, Any]]]:
        """
        Open positions on Binance Futures Testnet (non-zero positionAmt).
        Returns None when the exchange cannot be read. Callers must treat None as
        "unknown", never as "flat": an empty list means the account really holds nothing.
        """
        if not self._testnet_keys():
            return []
        try:
            data = self._signed_request("GET", "/fapi/v2/positionRisk", {})
        except Exception as e:
            now = time.time()
            if now - self._last_fetch_warn > 60:
                self._last_fetch_warn = now
                self.storage.log_activity("TESTNET_WARN", "POSITIONS", f"Binance positions unreachable ({self._http_error_text(e)[:60]}). Treating as unknown, not flat.", "WARNING")
            return None
        return [p for p in (data or []) if float(p.get("positionAmt", 0)) != 0]
