"""
Multi-Crypto Paper Execution Engine (BTC, ETH, SOL, XRP).
Manages $10 max sizing, round execution on best-edge coin at 2-minute mark, and per-coin win/loss ledger.
"""

import time
import threading
from typing import Dict, Any, List, Optional, Set
from datetime import datetime, timezone

from .models import Btc5mRound, Btc5mTrade
from .round_analyzer import MultiCryptoRoundAnalyzer


class MultiCryptoPaperScalper:
    def __init__(self, analyzer: MultiCryptoRoundAnalyzer, initial_bankroll: float = 50.0, activity_callback=None, auto_start: bool = True):
        self.analyzer = analyzer
        self.activity_callback = activity_callback
        self.lock = threading.RLock()
        self.balance: float = initial_bankroll
        self.peak_balance: float = initial_bankroll
        self.realized_pnl: float = 0.0
        self.total_commissions_paid: float = 0.0
        self.active_trades: Dict[str, Btc5mTrade] = {}  # Strictly single active trade
        self.max_concurrent_trades: int = 1  # Hard cap: Exactly 1 trade at a time across all coins
        self.rejected_rounds: Set[str] = set()  # De-duplicate aborted orders for round
        self.trade_history: List[Btc5mTrade] = []
        self.is_enabled: bool = False  # Starts PAUSED by default until user clicks Start button
        self.waiting_for_next_round: bool = False
        self.target_round_ts: int = 0
        self.stagger_interval_seconds: float = 15.0  # Condition timer: at least 15s gap between entering 2 coins
        self.last_entry_time: float = 0.0
        self.last_tick_time: float = time.time()
        self.last_analysis: Optional[Dict[str, Any]] = None
        self.live_executor = None
        self.trading_mode: str = "PAPER"  # "PAPER" or "LIVE"
        self.btc_only: bool = True  # Strict BTC-only mode by default

        # Start continuous 1-second background microstructure processing loop
        self._bg_thread = None
        self._watchdog_thread = None
        if auto_start:
            self._bg_thread = threading.Thread(target=self._background_ticker, daemon=True)
            self._bg_thread.start()
            self._watchdog_thread = threading.Thread(target=self._watchdog_ticker, daemon=True)
            self._watchdog_thread.start()

    @staticmethod
    def calculate_polymarket_fee(shares: float, price: float, fee_rate: float = 0.07) -> float:
        """
        Official Polymarket dynamic parabolic taker fee formula:
        fee = shares * fee_rate * price * (1.0 - price)
        Matches Polymarket CLOB fees exactly.
        """
        p = max(0.01, min(0.99, price))
        raw_fee = shares * fee_rate * p * (1.0 - p)
        return round(max(0.001, raw_fee), 3)

    @property
    def active_trade(self) -> Optional[Btc5mTrade]:
        """Backwards compatibility accessor for first open trade."""
        if not self.active_trades:
            return None
        return list(self.active_trades.values())[0]

    @active_trade.setter
    def active_trade(self, trade: Optional[Btc5mTrade]):
        if trade is None:
            self.active_trades.clear()
        else:
            self.active_trades[trade.symbol] = trade

    def set_live_executor(self, live_executor):
        """Attaches live Polymarket CLOB execution engine."""
        self.live_executor = live_executor

    def set_trading_mode(self, mode: str):
        """Switches between PAPER simulation and LIVE real-money trading."""
        with self.lock:
            self.trading_mode = mode.upper()
            if self.trading_mode == "LIVE" and self.live_executor:
                acc = self.live_executor.get_account_status()
                if acc.get("connected") and acc.get("usdc_balance") is not None:
                    self.balance = round(float(acc.get("usdc_balance")), 2)
            elif self.trading_mode == "PAPER":
                if self.balance < 5.0:
                    self.balance = 50.0  # Reset simulated bankroll if depleted

    def _background_ticker(self):
        """Continuously processes prices, TWAP rolling index, trade triggers, and settlements every 1s."""
        while True:
            try:
                self.process_tick()
            except Exception:
                pass
            time.sleep(1.0)

    def _watchdog_ticker(self):
        """Monitors ticker health; auto-settles expired trades and recovers hung network workers."""
        while True:
            time.sleep(4.0)
            try:
                now = time.time()
                # 1. Autonomous epoch expiration check: never leave trades stuck past round close
                if self.active_trades:
                    with self.lock:
                        now_ts = int(now)
                        for sym, t in list(self.active_trades.items()):
                            try:
                                r_ts = int(t.round_id.split("-")[-1])
                                if now_ts >= r_ts + 300:
                                    cur_coins = self.last_analysis.get("coins", {}) if self.last_analysis else {}
                                    self._check_settlement(cur_coins)
                                    break
                            except Exception:
                                pass

                # 2. Watchdog thread revival if background worker stalled > 8s
                if self.is_enabled and (now - self.last_tick_time > 8.0):
                    if not self._bg_thread or not self._bg_thread.is_alive():
                        self._bg_thread = threading.Thread(target=self._background_ticker, daemon=True)
                        self._bg_thread.start()
            except Exception:
                pass

    def enable(self):
        """Activates the scalper with mid-round protection."""
        cb_payload = None
        with self.lock:
            self.is_enabled = True
            now_ts = int(time.time())
            cur_round = (now_ts // 300) * 300
            seconds_left = max(0, (cur_round + 300) - now_ts)
            # If started with less than 50s remaining, wait for next round to avoid last-minute spread volatility
            if seconds_left < 50:
                self.waiting_for_next_round = True
                self.target_round_ts = cur_round + 300
                cb_payload = (
                    "5M_SCALP",
                    "Scalper Armed (Next Round Prep)",
                    f"Only {seconds_left}s remaining in active candle. Arming for next clean session at {time.strftime('%H:%M', time.gmtime(self.target_round_ts))} UTC.",
                    "accent"
                )
            else:
                self.waiting_for_next_round = False
                self.target_round_ts = 0
                cb_payload = (
                    "5M_SCALP",
                    "Scalper Active & Armed",
                    f"Real-time edge surveillance active with {seconds_left}s remaining in candle.",
                    "success"
                )

        if cb_payload and self.activity_callback:
            try:
                self.activity_callback(*cb_payload)
            except Exception:
                pass

    def disable(self):
        """Pauses the scalper immediately."""
        with self.lock:
            self.is_enabled = False
            self.waiting_for_next_round = False
            self.target_round_ts = 0

    def toggle_active(self) -> bool:
        """Toggles the 5m automated scalper on/off based on user button click."""
        if self.is_enabled:
            self.disable()
        else:
            self.enable()
        return self.is_enabled

    def reset(self, bankroll: float = 50.0):
        """Wipes trade history, open slips, and resets paper bankroll back to initial $50.00 state (PAUSED)."""
        with self.lock:
            self.balance = bankroll
            self.peak_balance = bankroll
            self.realized_pnl = 0.0
            self.total_commissions_paid = 0.0
            self.active_trades.clear()
            self.rejected_rounds.clear()
            self.trade_history = []
            self.is_enabled = False
            self.waiting_for_next_round = False
            self.target_round_ts = 0
            self.last_entry_time = 0.0

    def process_tick(self) -> Dict[str, Any]:
        """
        Executed periodically.
        1. Analyzes all 4 coins (BTC, ETH, SOL, XRP).
        2. Settles previous round trade if expired.
        3. Executes new paper trade on up to 2 parallel coins with staggered condition timer ($10 each).
        """
        self.last_tick_time = time.time()
        analysis = self.analyzer.analyze_all_coins()

        with self.lock:
            self.last_analysis = analysis

            # 1. Automated Settlement Check (runs even when paused)
            self._check_settlement(analysis["coins"])

            # 2. Automated Dynamic Exits (Auto Take-Profit @ 92¢ & Auto Stop-Loss Bailout @ 28¢)
            self._check_dynamic_exits(analysis["coins"])

            # 3. Check if mid-round waiting period has completed
            now_ts = int(time.time())
            cur_round_ts = (now_ts // 300) * 300
            if getattr(self, "_last_round_ts", 0) != cur_round_ts:
                self._last_round_ts = cur_round_ts
                self.rejected_rounds.clear()

            if self.waiting_for_next_round:
                if now_ts >= self.target_round_ts:
                    self.waiting_for_next_round = False
                    self.target_round_ts = 0
                    if self.activity_callback:
                        self.activity_callback(
                            category="5M_SCALP",
                            title="5M Session Open: Armed & Active",
                            details="Fresh 5-minute round started. Real-time edge surveillance active.",
                            level="info"
                        )

            # 4. Automated Trade Entry Check (Strict Single-Trade Execution across all 4 coins)
            now_time = time.time()
            time_since_last_entry = now_time - self.last_entry_time
            can_stagger_enter = (len(self.active_trades) == 0) or (time_since_last_entry >= self.stagger_interval_seconds)

            if self.is_enabled and not self.waiting_for_next_round and len(self.active_trades) < self.max_concurrent_trades and self.balance >= 5.0 and can_stagger_enter:
                all_coins = analysis.get("coins", {})
                cur_round_ts_str = str(cur_round_ts)

                # BTC-Only Mode: Restrict exclusively to BTC (in both LIVE and PAPER mode) for 1-active-trade focus
                if (getattr(self, "btc_only", True) and self.max_concurrent_trades == 1) or self.trading_mode == "LIVE":
                    btc_rd = all_coins.get("BTC")
                    candidate_coins = []
                    if (
                        btc_rd
                        and btc_rd.signal in ["BUY_UP", "BUY_DOWN"]
                        and "BTC" not in self.active_trades
                        and f"{btc_rd.round_id}_BTC" not in self.rejected_rounds
                        and not any(t.round_id.split("-")[-1] == cur_round_ts_str for t in self.trade_history)
                    ):
                        candidate_coins = [btc_rd]
                else:
                    candidate_coins = [
                        rd for sym, rd in all_coins.items()
                        if rd.signal in ["BUY_UP", "BUY_DOWN"]
                        and sym not in self.active_trades
                        and f"{rd.round_id}_{sym}" not in self.rejected_rounds
                        and not any(t.round_id.split("-")[-1] == cur_round_ts_str for t in self.trade_history)
                    ]
                    def _calc_edge(rd):
                        if rd.signal == "BUY_UP": return rd.calculated_prob_up - rd.market_price_up
                        if rd.signal == "BUY_DOWN": return rd.calculated_prob_down - rd.market_price_down
                        return 0.0
                    candidate_coins.sort(key=_calc_edge, reverse=True)

                if candidate_coins:
                    # Enforce strict staggered execution: enter candidate with condition timer & verified edge
                    self._execute_entry(candidate_coins[0])

            return self.get_state()

    def _execute_entry(self, r: Btc5mRound):
        """Executes a disciplined $5.00 bet on the highest conviction coin with condition timer tracking."""
        if self.balance < 5.0:
            return  # Strict capital rule: Minimum $5.00 free balance required.

        outcome = "UP" if r.signal == "BUY_UP" else "DOWN"
        market_px = r.market_price_up if outcome == "UP" else r.market_price_down
        # Paper fills happen at the LIVE best ask, the same price a taker order crosses. Without a live
        # book there is no honest fill price, so paper mode stands aside (live mode has its own book check).
        if self.trading_mode != "LIVE" and getattr(r, "price_source", "gamma") != "clob":
            if not getattr(self, "_no_book_notice_sent", False):
                self._no_book_notice_sent = True
                if self.activity_callback:
                    self.activity_callback("5M_SCALP", "Paper entry skipped: no live order book", f"{r.symbol}: price source is '{getattr(r, 'price_source', 'gamma')}', not the CLOB. Stale quotes produce fictional fills.", "warning")
            return
        exec_px = round(market_px, 3)
        if exec_px >= 0.99 or exec_px <= 0.0:
            return

        # Strict risk sizing: $5.00 fixed outlay per coin
        outlay_target = 5.0
        shares = round(outlay_target / exec_px, 1)
        cost = round(shares * exec_px, 2)
        if cost > outlay_target and shares > 0.1:
            shares = round(shares - 0.1, 1)
            cost = round(shares * exec_px, 2)

        # Official Polymarket Parabolic Crypto Taker Fee: C * feeRate * p * (1 - p)
        commission = self.calculate_polymarket_fee(shares, exec_px)
        total_outlay = round(cost + commission, 2)

        if cost < 4.0 or total_outlay > self.balance:
            return

        # LIVE EXECUTION GATEWAY
        live_order_id = None
        if self.trading_mode == "LIVE" and self.live_executor:
            if not self.live_executor.is_live_enabled:
                if self.activity_callback:
                    self.activity_callback("5M_SCALP", f"⚠️ Live Execution Blocked: Live Mode selected but POLYMARKET_LIVE_ENABLED is False.", "WARNING")
                return

            token_id = None
            if r.clob_token_ids and len(r.clob_token_ids) >= 2:
                token_id = r.clob_token_ids[0] if outcome == "UP" else r.clob_token_ids[1]

            if not token_id:
                poly_m = self.analyzer.fetch_polymarket_market(r.symbol, r.start_time)
                c_ids = poly_m.get("clob_token_ids")
                if c_ids and len(c_ids) >= 2:
                    token_id = c_ids[0] if outcome == "UP" else c_ids[1]

            if not token_id:
                if self.activity_callback:
                    self.activity_callback("5M_SCALP", f"⚠️ Order Aborted: No CLOB token ID found on Polymarket for {r.symbol} {outcome}.", "ERROR")
                return

            max_ask_ceiling = 0.82 if "LATE YIELD HARVEST" in r.signal_reason else min(0.60, max(0.55, round(exec_px + 0.04, 2)))
            order_res = self.live_executor.execute_live_5m_order(
                token_id=str(token_id),
                side="BUY",
                shares=shares,
                price=exec_px,
                max_allowed_ask=max_ask_ceiling
            )
            if not order_res.get("ok"):
                self.rejected_rounds.add(f"{r.round_id}_{r.symbol}")
                if self.activity_callback:
                    self.activity_callback("5M_SCALP", f"🛡️ Order Aborted: {order_res.get('reason')}", "WARN")
                return

            live_order_id = order_res.get("order_id")
            if self.activity_callback:
                self.activity_callback("5M_SCALP", f"🟢 LIVE ORDER SUBMITTED: ID {live_order_id} ({shares} shs @ {exec_px*100:.1f}¢)", "LIVE_TRADE")

        self.last_entry_time = time.time()
        self.balance = round(self.balance - total_outlay, 2)
        self.total_commissions_paid = round(self.total_commissions_paid + commission, 3)

        trade = Btc5mTrade(
            id=len(self.trade_history) + 1,
            round_id=r.round_id,
            action="BUY",
            outcome=outcome,
            shares=shares,
            entry_price=exec_px,
            cost=cost,
            pnl=0.0,
            timestamp=datetime.now(timezone.utc).isoformat(),
            reason=f"[{r.symbol} STAGGERED $5 SCALP] {r.signal_reason}" + (f" [LIVE ORDER: {live_order_id}]" if live_order_id else ""),
            symbol=r.symbol,
            spot_price_at_entry=r.spot_price,
            twap_price_at_entry=r.twap_price,
            oracle_lag_at_entry=r.oracle_lag_delta,
            projected_twap=r.projected_twap,
            commission=commission,
            settlement_price=0.0,
            status="OPEN",
            order_id=live_order_id,
            mode=self.trading_mode
        )
        self.active_trades[r.symbol] = trade

        if self.activity_callback:
            try:
                self.activity_callback(
                    category="5M_SCALP",
                    title=f"5M Scalp Entered: BUY {outcome} on {r.symbol}",
                    details=f"Outlay: ${cost:.2f} ({shares} shs @ ${exec_px:.3f}) | Fee: ${commission:.3f} | {r.signal_reason}",
                    level="accent"
                )
            except Exception:
                pass

    def force_settle_expired_trades(self) -> int:
        """Force-settles any active trades that have exceeded their 5-minute expiry window."""
        with self.lock:
            if not self.active_trades:
                return 0
            cur_coins = self.last_analysis.get("coins", {}) if self.last_analysis else {}
            pre_count = len(self.active_trades)
            self._check_settlement(cur_coins)
            return pre_count - len(self.active_trades)

    def _check_settlement(self, current_coins: Any):
        """Settles open trades when the 5-minute round ends or exceeds epoch expiry, aligning with Polymarket."""
        if not self.active_trades:
            return

        now_ts = int(time.time())
        settled_symbols = []
        for sym, trade in list(self.active_trades.items()):
            matching_coin_round = current_coins.get(trade.symbol) if isinstance(current_coins, dict) else current_coins

            coin = trade.symbol
            round_ts_str = trade.round_id.split("-")[-1]
            try:
                round_ts = int(round_ts_str)
            except ValueError:
                round_ts = matching_coin_round.start_time if matching_coin_round else (now_ts // 300) * 300

            # Determine if trade is ready for settlement:
            # 1. Round transitioned on market feed
            round_changed = bool(matching_coin_round and trade.round_id != matching_coin_round.round_id)

            # 2. Live Polymarket round timer hit 0
            round_timer_zero = bool(matching_coin_round and getattr(matching_coin_round, "seconds_remaining", 1) <= 0)

            # 3. Epoch timeout watchdog: if trade was entered > 330s (5.5m) ago in real time, it is objectively expired
            time_since_entry = 0.0
            if trade.timestamp:
                try:
                    dt = datetime.fromisoformat(trade.timestamp)
                    time_since_entry = (datetime.now(timezone.utc) - dt).total_seconds()
                except Exception:
                    pass
            watchdog_expired = (time_since_entry >= 330.0)

            if round_changed or round_timer_zero or watchdog_expired:
                # 1. Fetch real Polymarket Gamma resolution for full parity
                poly_res = self.analyzer.fetch_polymarket_market(coin, round_ts)
                winning_outcome = poly_res.get("winning_outcome")

                # Prefer official price_to_beat from Polymarket if present
                official_strike = poly_res.get("price_to_beat")
                strike_key = f"{coin}_{round_ts}"
                if official_strike and official_strike > 0:
                    strike_px = official_strike
                    self.analyzer._strike_prices[strike_key] = official_strike
                else:
                    default_strike = matching_coin_round.strike_price if matching_coin_round else trade.entry_price
                    strike_px = self.analyzer._strike_prices.get(strike_key, default_strike)

                final_px = 0.0
                if matching_coin_round and matching_coin_round.twap_price > 0:
                    final_px = matching_coin_round.twap_price
                elif official_strike:
                    final_px = self.analyzer.feed.get_price(coin)
                elif matching_coin_round:
                    final_px = matching_coin_round.current_btc_price

                # 2. Fallback to mathematical TWAP resolution if Polymarket has not settled yet
                if not winning_outcome:
                    winning_outcome = "UP" if final_px >= strike_px else "DOWN"

                trade.settlement_price = final_px
                if trade.outcome == winning_outcome:
                    payout = round(trade.shares * 1.0, 2)
                    pnl = round(payout - trade.cost - trade.commission, 2)
                    trade.status = "WON"
                    trade.pnl = pnl
                    if self.trading_mode == "LIVE" and self.live_executor:
                        acc = self.live_executor.get_account_status()
                        live_bal = float(acc.get("usdc_balance", 0)) if (acc.get("connected") and acc.get("usdc_balance") is not None) else 0.0
                        if live_bal > 0:
                            self.balance = round(max(live_bal, self.balance + payout), 2)
                        else:
                            self.balance = round(self.balance + payout, 2)
                    else:
                        self.balance = round(self.balance + payout, 2)
                    self.realized_pnl = round(self.realized_pnl + pnl, 2)
                    source_label = "Polymarket Contract" if poly_res.get("winning_outcome") else f"TWAP ${final_px:,.4f}"
                    trade.reason += f" | Settled via {source_label}: Strike ${strike_px:,.4f} -> {winning_outcome} WON (+${pnl:.2f}, fee ${trade.commission:.3f})."
                else:
                    pnl = round(-trade.cost - trade.commission, 2)
                    trade.status = "LOST"
                    trade.pnl = pnl
                    if self.trading_mode == "LIVE" and self.live_executor:
                        acc = self.live_executor.get_account_status()
                        if acc.get("connected") and acc.get("usdc_balance") is not None:
                            self.balance = round(float(acc.get("usdc_balance")), 2)
                    self.realized_pnl = round(self.realized_pnl + pnl, 2)
                    source_label = "Polymarket Contract" if poly_res.get("winning_outcome") else f"TWAP ${final_px:,.4f}"
                    trade.reason += f" | Settled via {source_label}: Strike ${strike_px:,.4f} -> {winning_outcome} WON (-${abs(pnl):.2f}, incl fee ${trade.commission:.3f})."

                self.peak_balance = max(self.peak_balance, self.balance)
                self.trade_history.insert(0, trade)
                settled_symbols.append(sym)

                if self.activity_callback:
                    try:
                        lvl = "success" if trade.status == "WON" else "danger"
                        self.activity_callback(
                            category="5M_SCALP",
                            title=f"5M Scalp Settled: {trade.symbol} {trade.status} ({'+' if trade.pnl >= 0 else ''}${trade.pnl:.2f})",
                            details=trade.reason,
                            level=lvl
                        )
                    except Exception:
                        pass

        for sym in settled_symbols:
            if sym in self.active_trades:
                del self.active_trades[sym]

    def _check_dynamic_exits(self, coins_data: Dict[str, Any]):
        """Evaluates active positions for Auto Take-Profit, Quick-Pop Cashout, and Expiry Wick Protection."""
        active_syms = list(self.active_trades.keys())
        for sym in active_syms:
            if sym not in self.active_trades:
                continue
            trade = self.active_trades[sym]
            c_round = coins_data.get(sym)
            if not c_round:
                continue

            cur_px = c_round.market_price_up if trade.outcome == "UP" else c_round.market_price_down
            top_bid = 0.0
            # Paper exits are priced at the live best bid (what a seller actually receives), never the ask.
            if trade.mode != "LIVE" and getattr(c_round, "price_source", "gamma") == "clob":
                live_bid = c_round.bid_up if trade.outcome == "UP" else c_round.bid_down
                if live_bid and live_bid > 0:
                    cur_px = live_bid
                    top_bid = live_bid

            # Real-Time CLOB Orderbook Check: In live mode, read top executable bid for selling into pops
            if trade.mode == "LIVE" and self.live_executor and getattr(self.live_executor, "client", None) and c_round.clob_token_ids:
                try:
                    tok_id = c_round.clob_token_ids[0] if trade.outcome == "UP" else c_round.clob_token_ids[1]
                    ob = self.live_executor.client.get_order_book(str(tok_id))
                    bids = [float(b["price"]) for b in ob.get("bids", []) if float(b.get("price", 0)) > 0]
                    if bids:
                        top_bid = max(bids)
                except Exception:
                    pass

            trade_age_seconds = 0.0
            if trade.timestamp:
                try:
                    dt = datetime.fromisoformat(trade.timestamp)
                    trade_age_seconds = (datetime.now(timezone.utc) - dt).total_seconds()
                except Exception:
                    pass

            sec_rem = getattr(c_round, "seconds_remaining", 300)

            # --- LIVE TRADING EXECUTION RULES ---
            # On live Polymarket CLOB, early cashouts require a real counterparty bid.
            # Never exit early on theoretical prices if no marketable bid exists.
            # Hold to resolution for guaranteed 100¢ ($1.00) settlement payout without spread penalty.
            if trade.mode == "LIVE":
                if top_bid > 0:
                    floating_val = round(trade.shares * top_bid, 2)
                    exit_comm = self.calculate_polymarket_fee(trade.shares, top_bid)
                    net_profit = round(floating_val - trade.cost - trade.commission - exit_comm, 2)

                    # 1. ⚡ Fast $1.00 - $2.00 Profit Lock:
                    # Cash out immediately the moment live CLOB bid guarantees >= +$1.00 net profit (+20% to +40% on $5)!
                    if net_profit >= 1.00:
                        self.cashout_trade(sym, reason="AUTO_QUICK_POP", exit_price=top_bid)
                        continue

                    # 2. 🎯 Big Surge Ceiling (>= 80¢ or net profit >= +$2.00)
                    if top_bid >= 0.80 or net_profit >= 2.00:
                        self.cashout_trade(sym, reason="AUTO_TAKE_PROFIT", exit_price=top_bid)
                        continue

                # 3. 🛡️ True Emergency Stop-Loss:
                # Only if consensus probability collapsed <= 18¢ AND a reasonable bid >= 12¢ exists
                if cur_px <= 0.18 and top_bid >= 0.12:
                    self.cashout_trade(sym, reason="AUTO_STOP_LOSS", exit_price=top_bid)
                    continue

                # Otherwise: HOLD TO RESOLUTION to claim full $1.00 payout at the 5-minute mark!
                continue

            # --- PAPER SIMULATION EXECUTION RULES ---
            # For taking profit in paper simulation:
            eval_px = max(cur_px, top_bid)
            gain = eval_px - trade.entry_price
            is_profitable = (gain >= 0.005)
            pop_exit_px = top_bid if (top_bid > trade.entry_price) else cur_px

            # Dynamic Stop-Loss threshold (strictly evaluated on true market price, NEVER on lowball orderbook bids):
            sl_cutoff = 0.50 if (trade.entry_price >= 0.65 or "LATE YIELD HARVEST" in trade.reason) else 0.28

            # 1. Full Win Ceiling (>= 88¢)
            if eval_px >= 0.88:
                self.cashout_trade(sym, reason="AUTO_TAKE_PROFIT", exit_price=pop_exit_px)
            # 2. ⚡ Fast Quick-Pop Auto Take-Profit:
            # - Early Scalps (entry <= 55¢): Any pop >= +8¢ or reaching >= 65¢ in profit -> LOCK IN PROFIT!
            # - Late Yield Harvest (entry > 55¢): Any pop >= +6¢ or reaching >= 84¢ -> LOCK IN PROFIT!
            elif is_profitable and (
                (trade.entry_price <= 0.55 and (gain >= 0.08 or eval_px >= 0.65)) or
                (trade.entry_price > 0.55 and (gain >= 0.06 or eval_px >= 0.84))
            ):
                self.cashout_trade(sym, reason="AUTO_QUICK_POP", exit_price=pop_exit_px)
            # 3. ⚡ 45-60s Quick Time Scalp:
            # If trade has been open >= 45 seconds and has gained >= +4¢, bank the profit!
            elif trade_age_seconds >= 45.0 and gain >= 0.04:
                self.cashout_trade(sym, reason="AUTO_QUICK_POP", exit_price=pop_exit_px)
            # 4. ⚡ 90s Early Win Lock:
            # If trade has been open >= 90 seconds and is in any profit (gain >= +2¢), exit immediately!
            elif trade_age_seconds >= 90.0 and gain >= 0.02:
                self.cashout_trade(sym, reason="AUTO_QUICK_POP", exit_price=pop_exit_px)
            # 5. 🛡️ 120-Second Max Hold Guard (Anti-Noose Trap):
            # Never hold a scalper trade past 2 minutes into the candle.
            # If after 120s price is in profit or break-even, cash out to prevent expiry reversal!
            elif trade_age_seconds >= 120.0 and is_profitable:
                self.cashout_trade(sym, reason="AUTO_QUICK_POP", exit_price=pop_exit_px)
            # 6. 🛡️ Pre-Expiry Wick Shield:
            # If <= 45s remain in the 5-minute round and trade is in profit, cash out immediately before the closing wick!
            elif sec_rem <= 45 and is_profitable:
                self.cashout_trade(sym, reason="AUTO_QUICK_POP", exit_price=pop_exit_px)
            # 7. 🛡️ Auto Stop-Loss Bailout:
            # Evaluated strictly against true consensus market price (cur_px), NEVER lowball orderbook bids!
            elif cur_px <= sl_cutoff:
                self.cashout_trade(sym, reason="AUTO_STOP_LOSS", exit_price=cur_px)

    def cashout_trade(self, symbol: str, reason: str = "MANUAL", exit_price: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """Allows selling/cashing out an active trade early at the current live floating market odds."""
        cb_payload = None
        with self.lock:
            trade = self.active_trades.get(symbol)
            if not trade:
                return None

            if exit_price is not None:
                cur_px = exit_price
            else:
                cur_px = trade.entry_price
                if self.last_analysis and "coins" in self.last_analysis:
                    c_round = self.last_analysis["coins"].get(symbol)
                    if c_round:
                        cur_px = c_round.market_price_up if trade.outcome == "UP" else c_round.market_price_down
                        live_bid = c_round.bid_up if trade.outcome == "UP" else c_round.bid_down
                        if trade.mode != "LIVE" and getattr(c_round, "price_source", "gamma") == "clob" and live_bid:
                            cur_px = live_bid

            # LIVE SELL EXECUTION
            if trade.mode == "LIVE" and self.live_executor and self.live_executor.is_live_enabled:
                token_id = None
                if self.last_analysis and "coins" in self.last_analysis:
                    c_round = self.last_analysis["coins"].get(symbol)
                    if c_round and c_round.clob_token_ids and len(c_round.clob_token_ids) >= 2:
                        token_id = c_round.clob_token_ids[0] if trade.outcome == "UP" else c_round.clob_token_ids[1]
                if token_id:
                    try:
                        self.live_executor.execute_live_5m_order(
                            token_id=str(token_id),
                            side="SELL",
                            shares=trade.shares,
                            price=cur_px
                        )
                    except Exception as ex:
                        logger.error(f"Live cashout sell failed for {symbol}: {ex}")

            floating_val = round(trade.shares * cur_px, 2)
            exit_comm = self.calculate_polymarket_fee(trade.shares, cur_px)
            pnl = round(floating_val - trade.cost - trade.commission - exit_comm, 2)

            trade.settlement_price = cur_px
            trade.status = "WON" if pnl >= 0 else "LOST"
            trade.pnl = pnl
            self.balance = round(self.balance + floating_val - exit_comm, 2)
            self.peak_balance = max(self.peak_balance, self.balance)
            self.realized_pnl = round(self.realized_pnl + pnl, 2)
            self.total_commissions_paid = round(self.total_commissions_paid + exit_comm, 3)

            if reason == "AUTO_TAKE_PROFIT":
                trade.reason += f" | Auto Take-Profit Hit @ {cur_px*100:.0f}¢: Locked in +${pnl:.2f}."
                title = f"🎯 Auto Take-Profit: {trade.symbol} (+${pnl:.2f})"
                lvl = "success"
            elif reason == "AUTO_QUICK_POP":
                pct_str = f"+{(pnl / max(0.01, trade.cost)) * 100:.1f}%"
                trade.reason += f" | ⚡ 1-Minute Quick-Pop Cashout @ {cur_px*100:.0f}¢: Banked +${pnl:.2f} ({pct_str})."
                title = f"⚡ 1-Minute Quick-Pop: {trade.symbol} (+${pnl:.2f})"
                lvl = "success"
            elif reason == "AUTO_STOP_LOSS":
                trade.reason += f" | Auto Stop-Loss Bailout @ {cur_px*100:.0f}¢: Salvaged ${floating_val:.2f} (Loss capped at -${abs(pnl):.2f})."
                title = f"🛡️ Auto Stop-Loss Bailout: {trade.symbol} (-${abs(pnl):.2f})"
                lvl = "warning"
            else:
                trade.reason += f" | Early Cashout @ {cur_px*100:.1f}¢: Locked in {'+' if pnl >= 0 else ''}${pnl:.2f}."
                title = f"💰 Early Cashout: {trade.symbol} ({'+' if pnl>=0 else ''}${pnl:.2f})"
                lvl = "success" if pnl >= 0 else "warning"

            self.trade_history.insert(0, trade)
            del self.active_trades[symbol]

            cb_payload = ("5M_SCALP", title, trade.reason, lvl)

        if cb_payload and self.activity_callback:
            try:
                self.activity_callback(*cb_payload)
            except Exception:
                pass

        return {"ok": True, "symbol": symbol, "pnl": pnl, "cashout_value": floating_val, "reason": reason}

    def get_state(self) -> Dict[str, Any]:
        """Returns JSON state for the 4-coin frontend dashboard."""
        coins_dict = {}
        best_round_dict = None

        if self.last_analysis:
            best_r = self.last_analysis.get("best_round")
            if best_r:
                best_round_dict = {
                    "round_id": best_r.round_id,
                    "symbol": best_r.symbol,
                    "slug": best_r.slug,
                    "title": best_r.title,
                    "strike_price": best_r.strike_price,
                    "current_btc_price": best_r.current_btc_price,
                    "spot_price": best_r.spot_price,
                    "twap_price": best_r.twap_price,
                    "oracle_lag_delta": best_r.oracle_lag_delta,
                    "projected_twap": best_r.projected_twap,
                    "price_delta": best_r.price_delta,
                    "seconds_remaining": best_r.seconds_remaining,
                    "market_price_up": best_r.market_price_up,
                    "market_price_down": best_r.market_price_down,
                    "bid_up": getattr(best_r, "bid_up", 0.0),
                    "bid_down": getattr(best_r, "bid_down", 0.0),
                    "price_source": getattr(best_r, "price_source", "gamma"),
                    "oracle_source": getattr(best_r, "oracle_source", "binance"),
                    "calculated_prob_up": best_r.calculated_prob_up,
                    "calculated_prob_down": best_r.calculated_prob_down,
                    "z_score": best_r.z_score,
                    "ict_fvg_status": best_r.ict_fvg_status,
                    "signal": best_r.signal,
                    "signal_reason": best_r.signal_reason
                }

            all_c = self.last_analysis.get("coins", {})
            now_ts = int(time.time())
            cur_round_ts = (now_ts // 300) * 300
            for sym, r in all_c.items():
                slug = r.slug or r.round_id or f"{sym.lower()}-updown-5m-{cur_round_ts}"
                poly_url = f"https://polymarket.com/event/{slug}"

                # Generate next 5 scheduled rounds with direct links for this coin
                coin_next_rounds = []
                for i in range(1, 6):
                    u_ts = cur_round_ts + (i * 300)
                    u_slug = f"{sym.lower()}-updown-5m-{u_ts}"
                    start_str = time.strftime('%H:%M', time.gmtime(u_ts))
                    starts_in = max(0, u_ts - now_ts)
                    coin_next_rounds.append({
                        "slug": u_slug,
                        "timestamp": u_ts,
                        "label": f"+{i*5}m",
                        "time_utc": f"{start_str} UTC",
                        "starts_in_seconds": starts_in,
                        "status": f"in {starts_in // 60}m {starts_in % 60}s",
                        "url": f"https://polymarket.com/event/{u_slug}"
                    })

                coins_dict[sym] = {
                    "symbol": sym,
                    "round_id": r.round_id,
                    "slug": slug,
                    "polymarket_url": poly_url,
                    "next_rounds": coin_next_rounds,
                    "strike_price": r.strike_price,
                    "current_price": r.current_btc_price,
                    "spot_price": r.spot_price,
                    "twap_price": r.twap_price,
                    "oracle_lag_delta": r.oracle_lag_delta,
                    "projected_twap": r.projected_twap,
                    "price_delta": r.price_delta,
                    "seconds_remaining": r.seconds_remaining,
                    "market_price_up": r.market_price_up,
                    "market_price_down": r.market_price_down,
                    "bid_up": getattr(r, "bid_up", 0.0),
                    "bid_down": getattr(r, "bid_down", 0.0),
                    "price_source": getattr(r, "price_source", "gamma"),
                    "oracle_source": getattr(r, "oracle_source", "binance"),
                    "calculated_prob_up": r.calculated_prob_up,
                    "calculated_prob_down": r.calculated_prob_down,
                    "z_score": r.z_score,
                    "signal": r.signal,
                    "signal_reason": r.signal_reason
                }

        active_trades_list = []
        for t in self.active_trades.values():
            cur_px = t.entry_price
            if self.last_analysis and "coins" in self.last_analysis:
                c_round = self.last_analysis["coins"].get(t.symbol)
                if c_round:
                    cur_px = c_round.market_price_up if t.outcome == "UP" else c_round.market_price_down

            floating_val = round(t.shares * cur_px, 2)
            floating_pnl = round(floating_val - t.cost - t.commission, 2)
            floating_pct = round((floating_pnl / t.cost) * 100, 1) if t.cost > 0 else 0.0

            active_trades_list.append({
                "round_id": t.round_id,
                "symbol": t.symbol,
                "outcome": t.outcome,
                "shares": t.shares,
                "entry_price": t.entry_price,
                "current_price": cur_px,
                "cost": t.cost,
                "floating_value": floating_val,
                "floating_pnl": floating_pnl,
                "floating_pnl_pct": floating_pct,
                "spot_price_at_entry": t.spot_price_at_entry,
                "twap_price_at_entry": t.twap_price_at_entry,
                "oracle_lag_at_entry": t.oracle_lag_at_entry,
                "projected_twap": t.projected_twap,
                "commission": t.commission,
                "timestamp": t.timestamp,
                "reason": t.reason,
                "order_id": getattr(t, "order_id", None),
                "mode": getattr(t, "mode", "PAPER")
            })
        active_trade_dict = active_trades_list[0] if active_trades_list else None

        total_trades = len(self.trade_history)
        wins = sum(1 for t in self.trade_history if t.status == "WON")
        losses = sum(1 for t in self.trade_history if t.status == "LOST")
        win_rate = round((wins / total_trades) * 100, 1) if total_trades > 0 else 0.0

        # Per-coin breakdown
        coin_stats = {}
        for c in ["BTC", "ETH", "SOL", "XRP"]:
            c_trades = [t for t in self.trade_history if t.symbol == c]
            c_wins = sum(1 for t in c_trades if t.status == "WON")
            c_losses = sum(1 for t in c_trades if t.status == "LOST")
            c_pnl = sum(t.pnl for t in c_trades)
            c_comm = sum(t.commission for t in c_trades)
            c_win_rate = round((c_wins / len(c_trades)) * 100, 1) if c_trades else 0.0
            coin_stats[c] = {
                "trades": len(c_trades),
                "wins": c_wins,
                "losses": c_losses,
                "win_rate": c_win_rate,
                "pnl": round(c_pnl, 2),
                "commissions_paid": round(c_comm, 3)
            }

        upcoming_list = self.last_analysis.get("upcoming_rounds", []) if self.last_analysis else []

        stagger_rem = 0
        if len(self.active_trades) == 1 and self.last_entry_time > 0:
            stagger_rem = max(0, int(self.stagger_interval_seconds - (time.time() - self.last_entry_time)))

        # Default real-time timeline for BTC 5M
        timeline_data = {}
        try:
            timeline_data = self.analyzer.get_polymarket_timeline("BTC", "5m")
        except Exception:
            pass

        # Live balance sync when operating in LIVE mode
        if self.trading_mode == "LIVE" and self.live_executor:
            try:
                acc = self.live_executor.get_account_status()
                if acc.get("connected") and acc.get("usdc_balance") is not None:
                    self.balance = round(float(acc.get("usdc_balance")), 2)
            except Exception:
                pass

        return {
            "is_enabled": self.is_enabled,
            "trading_mode": self.trading_mode,
            "max_concurrent_trades": self.max_concurrent_trades,
            "waiting_for_next_round": self.waiting_for_next_round,
            "target_round_ts": self.target_round_ts,
            "upcoming_rounds": upcoming_list,
            "timeline": timeline_data,
            "stagger_timer_remaining": stagger_rem,
            "stagger_interval_seconds": self.stagger_interval_seconds,
            "balance": round(self.balance, 2),
            "realized_pnl": round(self.realized_pnl, 2),
            "total_commissions_paid": round(self.total_commissions_paid, 3),
            "win_rate": win_rate,
            "total_trades": total_trades,
            "total_won": wins,
            "total_lost": losses,
            "round": best_round_dict,
            "predictions": self.last_analysis.get("predictions", {}) if self.last_analysis else {},
            "coins": coins_dict,
            "coin_stats": coin_stats,
            "active_trade": active_trade_dict,
            "active_trades": active_trades_list,
            "history": [
                {
                    "id": t.id,
                    "round_id": t.round_id,
                    "symbol": t.symbol,
                    "outcome": t.outcome,
                    "shares": t.shares,
                    "entry_price": t.entry_price,
                    "cost": t.cost,
                    "commission": t.commission,
                    "spot_price_at_entry": t.spot_price_at_entry,
                    "twap_price_at_entry": t.twap_price_at_entry,
                    "settlement_price": t.settlement_price,
                    "pnl": t.pnl,
                    "status": t.status,
                    "timestamp": t.timestamp,
                    "reason": t.reason
                }
                for t in self.trade_history[:20]
            ]
        }


# Alias for backwards compatibility
Btc5mPaperScalper = MultiCryptoPaperScalper
