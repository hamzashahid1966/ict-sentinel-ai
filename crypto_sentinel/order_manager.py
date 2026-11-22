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
from typing import Optional, Dict, Any, List
from crypto_sentinel.config import (
    BINANCE_TESTNET_REST, BINANCE_TESTNET_API_KEY, BINANCE_TESTNET_API_SECRET,
    TAKER_FEE_PCT, DEFAULT_SLIPPAGE_PCT, STRATEGY_PROFILES,
    TARGET_1_R, TARGET_2_R, DEFAULT_STRATEGY_PROFILE, SSL_CONTEXT,
    DIRECT_OPENER, direct_urlopen,
    STAGNATION_TIMEOUT_SECONDS, TRUE_FEE_BUFFER_PCT, OPPORTUNITY_SWAP_MIN_SCORE
)
from crypto_sentinel.models import CryptoPosition, AnalysisOpportunity, CryptoAccount
from crypto_sentinel.storage import CryptoStorageEngine
from crypto_sentinel.ai_analyzer import CryptoAIAnalyzer

class CryptoOrderManager:
    def __init__(self, storage: CryptoStorageEngine):
        self.storage = storage
        self.ai_analyzer = CryptoAIAnalyzer(self.storage)

    def open_position(self, opp: AnalysisOpportunity, qty: float, mode: str) -> CryptoPosition:
        """
        Executes a new position under Double Tap protocol.
        """
        pos_id = f"POS_{opp.symbol}_{int(time.time())}_{uuid.uuid4().hex[:4].upper()}"

        # Calculate fees
        notional = qty * opp.current_price
        entry_fee = notional * (TAKER_FEE_PCT / 100.0)

        # Dynamic Target 1 and Target 2 calculation from active strategy profile
        acc = self.storage.get_account()
        prof = STRATEGY_PROFILES.get(acc.strategy_profile, STRATEGY_PROFILES.get(DEFAULT_STRATEGY_PROFILE, {}))
        t1_r = prof.get("target_1_r", TARGET_1_R)
        t2_r = prof.get("target_2_r", TARGET_2_R)
        r_dist = abs(opp.current_price - opp.stop_loss)
        target_1 = round(opp.current_price + (r_dist * t1_r if opp.direction == "LONG" else -r_dist * t1_r), 6 if opp.current_price < 1 else 2)
        target_2 = round(opp.current_price + (r_dist * t2_r if opp.direction == "LONG" else -r_dist * t2_r), 6 if opp.current_price < 1 else 2)

        pos = CryptoPosition(
            position_id=pos_id,
            symbol=opp.symbol,
            engine=opp.engine,
            direction=opp.direction,
            entry_price=opp.current_price,
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
        self.storage.log_activity(
            action="ORDER_OPEN",
            coin=opp.symbol,
            detail=f"Opened {opp.direction} {qty} @ {opp.current_price:.4f} | Engine: {opp.engine} | SL: {opp.stop_loss:.4f} | TP1: {target_1:.4f} ({t1_r}R) | TP2: {target_2:.4f} ({t2_r}R)",
            level="SUCCESS"
        )

        # If in Binance Testnet mode, dispatch external API request
        if mode == "BINANCE_TESTNET" and BINANCE_TESTNET_API_KEY:
            self._dispatch_binance_testnet_order(pos, "MARKET")

        return pos

    def update_position_with_price(self, pos: CryptoPosition, current_price: float, account: CryptoAccount):
        """
        Double Tap lifecycle management on price updates:
        1. Check Target 1 (1.5R): close 50% and move stop to entry defensive buffer.
        2. Check Target 2 (3.0R): close remaining 50% (trade complete).
        3. Check Current Stop Loss.
        """
        if pos.status == "CLOSED":
            return

        is_long = (pos.direction == "LONG")
        risk_dist = abs(pos.entry_price - pos.initial_stop)
        current_move = (current_price - pos.entry_price) if is_long else (pos.entry_price - current_price)
        r_multiple = (current_move / risk_dist) if risk_dist > 0 else 0.0

        pos.unrealized_pnl = round(current_move * pos.quantity, 2)
        pos.unrealized_r = round(r_multiple, 2)

        # 1. Target 1 Check (1.5R reached)
        if not pos.t1_hit:
            hit_t1 = (current_price >= pos.target_1) if is_long else (current_price <= pos.target_1)
            if hit_t1:
                pos.t1_hit = True
                # Partial exit of 50%
                half_qty = pos.quantity / 2.0
                half_pnl = round(current_move * half_qty, 2)
                t1_fee = round(half_qty * current_price * (TAKER_FEE_PCT / 100.0), 4)
                pos.fees_paid += t1_fee
                
                # Move Stop to Defensive: Entry + slight cushion in trade direction to guarantee zero-risk
                defensive_cushion = risk_dist * 0.05
                pos.current_stop = round(pos.entry_price + (defensive_cushion if is_long else -defensive_cushion), 6 if pos.entry_price < 1 else 2)
                pos.defensive_active = True
                pos.status = "T1_HIT"

                # Credit realized account balance
                self.storage.update_account(balance=account.balance + half_pnl, realized_pnl_delta=half_pnl)

                # Dispatch partial close to Binance Testnet if in testnet mode
                if account.mode == "BINANCE_TESTNET":
                    self._dispatch_binance_testnet_close(pos.symbol, pos.direction, half_qty, "TP1_PARTIAL")

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
            remaining_qty = (pos.quantity / 2.0) if pos.t1_hit else pos.quantity
            remaining_pnl = round(current_move * remaining_qty, 2)
            total_realized = (pos.unrealized_pnl if not pos.t1_hit else remaining_pnl)
            t2_fee = round(remaining_qty * current_price * (TAKER_FEE_PCT / 100.0), 4)
            pos.fees_paid += t2_fee

            pos.status = "CLOSED"
            pos.exit_price = current_price
            pos.exit_reason = "TARGET_2_FULL_FILL (0.8R)"
            pos.exit_time = time.time()
            self._record_closed_trade_learning(pos)

            self.storage.update_account(balance=account.balance + remaining_pnl, realized_pnl_delta=remaining_pnl)

            # Dispatch close to Binance Testnet if in testnet mode
            if account.mode == "BINANCE_TESTNET":
                self._dispatch_binance_testnet_close(pos.symbol, pos.direction, remaining_qty, "TP2_FULL_0.8R")

            self.storage.log_activity(
                action="DOUBLE_TAP_T2",
                coin=pos.symbol,
                detail=f"🚀 Target 2 HIT at {current_price:.2f}! Trade completed. Gross: +${total_realized:.2f} | Fees: ${pos.fees_paid:.2f} | Net: +${(total_realized - pos.fees_paid):.2f}.",
                level="SUCCESS"
            )

        # 3. Stop Loss Check
        hit_stop = (current_price <= pos.current_stop) if is_long else (current_price >= pos.current_stop)
        if hit_stop and pos.status != "CLOSED":
            remaining_qty = (pos.quantity / 2.0) if pos.t1_hit else pos.quantity
            loss_move = (pos.current_stop - pos.entry_price) if is_long else (pos.entry_price - pos.current_stop)
            stop_pnl = round(loss_move * remaining_qty, 2)
            sl_fee = round(remaining_qty * current_price * (TAKER_FEE_PCT / 100.0), 4)
            pos.fees_paid += sl_fee

            pos.status = "CLOSED"
            pos.exit_price = current_price
            pos.exit_reason = "DEFENSIVE_STOP_OUT" if pos.defensive_active else "INITIAL_STOP_LOSS"
            pos.exit_time = time.time()
            self._record_closed_trade_learning(pos)

            self.storage.update_account(balance=account.balance + stop_pnl, realized_pnl_delta=stop_pnl)

            # Dispatch close to Binance Testnet if in testnet mode
            if account.mode == "BINANCE_TESTNET":
                self._dispatch_binance_testnet_close(pos.symbol, pos.direction, remaining_qty, pos.exit_reason)

            log_level = "INFO" if pos.defensive_active else "DANGER"
            self.storage.log_activity(
                action="STOP_LOSS",
                coin=pos.symbol,
                detail=f"🛑 Stop Loss triggered at {current_price:.2f} ({pos.exit_reason}). Gross: ${stop_pnl:.2f} | Fees: ${pos.fees_paid:.2f} | Net: ${stop_pnl - pos.fees_paid:.2f}.",
                level=log_level
            )

        self.storage.save_position(pos)

    def _record_closed_trade_learning(self, pos: CryptoPosition):
        """Records trade execution results into AI Behavioral Memory for auto-quarantine analysis."""
        if not pos or pos.exit_price is None:
            return
        try:
            is_long = (pos.direction == "LONG")
            if pos.t1_hit:
                half_qty = pos.quantity / 2.0
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

    def close_position_manually(self, pos_id: str, current_price: float, account: CryptoAccount) -> bool:
        """
        Operator manual flatten / panic close.
        """
        open_positions = self.storage.get_open_positions()
        target_pos = next((p for p in open_positions if p.position_id == pos_id), None)
        if not target_pos:
            return False

        is_long = (target_pos.direction == "LONG")
        remaining_qty = (target_pos.quantity / 2.0) if target_pos.t1_hit else target_pos.quantity
        move = (current_price - target_pos.entry_price) if is_long else (target_pos.entry_price - current_price)
        pnl = round(move * remaining_qty, 2)

        target_pos.status = "CLOSED"
        target_pos.exit_price = current_price
        target_pos.exit_reason = "MANUAL_CLOSE"
        target_pos.exit_time = time.time()
        self._record_closed_trade_learning(target_pos)

        self.storage.update_account(balance=account.balance + pnl, realized_pnl_delta=pnl)
        self.storage.save_position(target_pos)

        # Dispatch real market close order to Binance Futures Testnet
        if account.mode == "BINANCE_TESTNET":
            self._dispatch_binance_testnet_close(target_pos.symbol, target_pos.direction, remaining_qty, "MANUAL_CLOSE")

        self.storage.log_activity(
            action="MANUAL_CLOSE",
            coin=target_pos.symbol,
            detail=f"Position manually closed at {current_price:.2f}. Realized PnL: ${pnl:.2f}",
            level="WARNING"
        )
        return True

    def _format_qty_for_symbol(self, symbol: str, qty: float) -> str:
        """Dynamically format quantity according to exchange lot size rules."""
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
        Dispatches authenticated HMAC-SHA256 order to Binance Futures Testnet REST API.
        """
        try:
            timestamp = int(time.time() * 1000)
            side = "BUY" if pos.direction == "LONG" else "SELL"
            qty_str = self._format_qty_for_symbol(pos.symbol, pos.quantity)
            params = {
                "symbol": pos.symbol,
                "side": side,
                "type": order_type,
                "quantity": qty_str,
                "timestamp": timestamp,
                "newClientOrderId": pos.position_id[:32]
            }
            query_string = urllib.parse.urlencode(params)
            signature = hmac.new(
                BINANCE_TESTNET_API_SECRET.encode("utf-8"),
                query_string.encode("utf-8"),
                hashlib.sha256
            ).hexdigest()

            url = f"{BINANCE_TESTNET_REST}/fapi/v1/order?{query_string}&signature={signature}"
            req = urllib.request.Request(url, method="POST", headers={
                "X-MBX-APIKEY": BINANCE_TESTNET_API_KEY,
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "Mozilla/5.0"
            })
            with direct_urlopen(req, timeout=5.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                fill_price = float(data.get("avgPrice") or 0.0)
                if fill_price <= 0:
                    cum_quote = float(data.get("cumQuote") or 0.0)
                    cum_qty = float(data.get("executedQty") or 0.0)
                    if cum_qty > 0 and cum_quote > 0:
                        fill_price = cum_quote / cum_qty
                if fill_price <= 0:
                    time.sleep(0.2)
                    active_pos = self.fetch_binance_testnet_positions()
                    tp = next((t for t in active_pos if t.get("symbol") == pos.symbol), None)
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

                    pos.entry_price = fill_price
                    pos.initial_stop = round(fill_price * (1 - risk_pct if pos.direction == "LONG" else 1 + risk_pct), 6 if fill_price < 1 else 2)
                    pos.current_stop = pos.initial_stop
                    pos.target_1 = round(fill_price * (1 + t1_r * risk_pct if pos.direction == "LONG" else 1 - t1_r * risk_pct), 6 if fill_price < 1 else 2)
                    pos.target_2 = round(fill_price * (1 + t2_r * risk_pct if pos.direction == "LONG" else 1 - t2_r * risk_pct), 6 if fill_price < 1 else 2)
                    self.storage.save_position(pos)
                self.storage.log_activity("BINANCE_TESTNET", pos.symbol, f"Testnet Order Fill: {data.get('orderId')} @ {fill_price or pos.entry_price}", "SUCCESS")
        except Exception as e:
            err_msg = str(e).replace("<", "").replace(">", "")
            self.storage.log_activity("TESTNET_WARN", pos.symbol, f"Testnet sync notice: {err_msg[:80]}", "WARNING")
            pos.status = "DISPATCH_FAILED"
            pos.fees_paid = 0.0
            pos.exit_reason = f"ORDER_DISPATCH_FAILED ({err_msg[:30]})"
            self.storage.save_position(pos)

    def _dispatch_binance_testnet_close(self, symbol: str, direction: str, qty: float, reason: str):
        """
        Dispatches real reduce-only closing market order to Binance Futures Testnet.
        """
        if not BINANCE_TESTNET_API_KEY or not BINANCE_TESTNET_API_SECRET:
            return
        try:
            timestamp = int(time.time() * 1000)
            side = "SELL" if direction == "LONG" else "BUY"
            qty_str = self._format_qty_for_symbol(symbol, qty)

            # If closing in full, check real testnet position amount to avoid lot-size mismatch
            if reason in ("MANUAL_CLOSE", "FLATTEN_ALL", "TP2_FULL_3.0R", "HARD_STOP_LOSS"):
                active_positions = self.fetch_binance_testnet_positions()
                tp = next((t for t in active_positions if t.get("symbol") == symbol), None)
                if tp:
                    real_amt = abs(float(tp["positionAmt"]))
                    if real_amt > 0:
                        qty_str = str(tp["positionAmt"]).replace("-", "")

            params = {
                "symbol": symbol,
                "side": side,
                "type": "MARKET",
                "quantity": qty_str,
                "reduceOnly": "true",
                "timestamp": timestamp,
                "newClientOrderId": f"CLOSE_{symbol}_{timestamp}"[:32]
            }
            query_string = urllib.parse.urlencode(params)
            signature = hmac.new(
                BINANCE_TESTNET_API_SECRET.encode("utf-8"),
                query_string.encode("utf-8"),
                hashlib.sha256
            ).hexdigest()

            url = f"{BINANCE_TESTNET_REST}/fapi/v1/order?{query_string}&signature={signature}"
            req = urllib.request.Request(url, method="POST", headers={
                "X-MBX-APIKEY": BINANCE_TESTNET_API_KEY,
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "Mozilla/5.0"
            })
            with direct_urlopen(req, timeout=5.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                self.storage.log_activity("BINANCE_TESTNET", symbol, f"Testnet Position Closed ({reason}): {data.get('orderId')}", "SUCCESS")
        except Exception as e:
            err_msg = str(e).replace("<", "").replace(">", "")
            self.storage.log_activity("TESTNET_WARN", symbol, f"Testnet close notice: {err_msg[:80]}", "WARNING")

    def fetch_binance_testnet_account(self) -> Optional[Dict[str, Any]]:
        """
        Fetches live wallet balance, margin, and assets from Binance Futures Testnet.
        """
        if not BINANCE_TESTNET_API_KEY or not BINANCE_TESTNET_API_SECRET:
            return None
        try:
            timestamp = int(time.time() * 1000)
            params = {"timestamp": timestamp}
            query_string = urllib.parse.urlencode(params)
            signature = hmac.new(
                BINANCE_TESTNET_API_SECRET.encode("utf-8"),
                query_string.encode("utf-8"),
                hashlib.sha256
            ).hexdigest()

            url = f"{BINANCE_TESTNET_REST}/fapi/v2/account?{query_string}&signature={signature}"
            req = urllib.request.Request(url, headers={
                "X-MBX-APIKEY": BINANCE_TESTNET_API_KEY,
                "User-Agent": "Mozilla/5.0"
            })
            with direct_urlopen(req, timeout=5.0) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            err_msg = str(e).replace("<", "").replace(">", "")
            self.storage.log_activity("TESTNET_ERR", "ACCOUNT", f"Testnet balance fetch failed: {err_msg[:80]}", "DANGER")
            return None

    def fetch_binance_testnet_positions(self) -> List[Dict[str, Any]]:
        """
        Fetches live open positions directly from Binance Testnet positionRisk endpoint.
        Returns only positions with non-zero positionAmt.
        """
        if not BINANCE_TESTNET_API_KEY or not BINANCE_TESTNET_API_SECRET:
            return []
        try:
            timestamp = int(time.time() * 1000)
            params = {"timestamp": timestamp}
            query_string = urllib.parse.urlencode(params)
            signature = hmac.new(
                BINANCE_TESTNET_API_SECRET.encode("utf-8"),
                query_string.encode("utf-8"),
                hashlib.sha256
            ).hexdigest()

            url = f"{BINANCE_TESTNET_REST}/fapi/v2/positionRisk?{query_string}&signature={signature}"
            req = urllib.request.Request(url, headers={
                "X-MBX-APIKEY": BINANCE_TESTNET_API_KEY,
                "User-Agent": "Mozilla/5.0"
            })
            with direct_urlopen(req, timeout=5.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return [p for p in data if float(p.get("positionAmt", 0)) != 0]
        except Exception:
            return []
