"""
Crypto Sentinel AI - Master Bot Controller & Autonomous Loop
Coordinates the Screener, 3-Engines, Arbitration, Risk Engine, and Double Tap OMS.
"""

import threading
import time
from typing import Dict, Any, List, Optional
from crypto_sentinel.config import (
    TOP_50_UNIVERSE, TOP_PRIME_SYMBOLS, MAX_CONCURRENT_POSITIONS, STRATEGY_PROFILES,
    STAGNATION_TIMEOUT_SECONDS, TRUE_FEE_BUFFER_PCT, OPPORTUNITY_SWAP_MIN_SCORE, AUTO_SWAP_ENABLED
)
from crypto_sentinel.models import CryptoAccount, CryptoPosition, ScreenerCandidate, AnalysisOpportunity
from crypto_sentinel.storage import CryptoStorageEngine
from crypto_sentinel.data_feed import CryptoDataFeed
from crypto_sentinel.engines.ict_engine import ICTLiquidityEngine
from crypto_sentinel.engines.momentum_engine import MomentumEngine
from crypto_sentinel.engines.liquidation_engine import LiquidationEngine
from crypto_sentinel.arbitration import SignalArbitrationEngine
from crypto_sentinel.risk_engine import CryptoRiskEngine
from crypto_sentinel.order_manager import CryptoOrderManager

class CryptoBotController:
    def __init__(self):
        self.storage = CryptoStorageEngine()
        self.data_feed = CryptoDataFeed()
        self.engine_a = ICTLiquidityEngine()
        self.engine_b = MomentumEngine()
        self.engine_c = LiquidationEngine()
        self.arbitrator = SignalArbitrationEngine()
        self.risk_engine = CryptoRiskEngine()
        self.order_mgr = CryptoOrderManager(self.storage)

        self.running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self.current_status = "IDLE (WAITING TO START)"
        self.active_regime = "BALANCED_MARKET"
        self.last_scan_time = 0.0
        self.last_trade_opened_at = 0.0

    def start(self):
        if self.running:
            return
        self.running = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        self.storage.log_activity("SYSTEM", "CORE", "Crypto Sentinel Autonomous Engine Started.", "SUCCESS")

    def stop(self):
        if not self.running:
            return
        self.running = False
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=3.0)
        self.current_status = "STOPPED"
        self.storage.log_activity("SYSTEM", "CORE", "Crypto Sentinel Autonomous Engine Stopped.", "WARNING")

    def _loop(self):
        while not self._stop_event.is_set():
            try:
                self.run_cycle()
            except Exception as e:
                self.storage.log_activity("ERROR", "CORE", f"Cycle exception: {str(e)[:80]}", "DANGER")
            # Wait 5 seconds between ticks / sub-cycles
            self._stop_event.wait(5.0)

    def run_cycle(self):
        account = self.storage.get_account()

        # Step 1: Manage active open positions with live prices
        if account.mode == "BINANCE_TESTNET":
            testnet_positions = self.order_mgr.fetch_binance_testnet_positions()
            open_positions = self.storage.get_open_positions()
            seen_symbols = set()
            for pos in open_positions:
                if pos.symbol in seen_symbols:
                    pos.status = "CLOSED"
                    pos.exit_time = time.time()
                    pos.exit_reason = "DUPLICATE_CLEANUP"
                    self.storage.save_position(pos)
                    continue

                tp = next((t for t in testnet_positions if t.get("symbol") == pos.symbol), None)
                if tp:
                    seen_symbols.add(pos.symbol)
                    amt = float(tp["positionAmt"])
                    pos.direction = "LONG" if amt > 0 else "SHORT"
                    pos.quantity = abs(amt)
                    pos.entry_price = float(tp["entryPrice"])
                    mark = float(tp["markPrice"])
                    pos.current_price = mark
                    pos.unrealized_pnl = round(float(tp["unRealizedProfit"]), 2)

                    acc_prof = STRATEGY_PROFILES.get(account.strategy_profile, STRATEGY_PROFILES.get("FAST_SCALPER", {}))
                    t1_r = acc_prof.get("target_1_r", 0.30)
                    t2_r = acc_prof.get("target_2_r", 0.60)

                    # Guard against stop loss on the wrong side or corrupted scale (only when defensive stop is not yet active)
                    dist_pct = abs(pos.current_stop - pos.entry_price) / pos.entry_price if pos.entry_price > 0 else 1.0
                    is_stop_wrong = ((pos.current_stop >= pos.entry_price) if pos.direction == "LONG" else (pos.current_stop <= pos.entry_price)) if not pos.defensive_active else False
                    if dist_pct > 0.08 or is_stop_wrong:
                        risk_pct = 0.015
                        pos.initial_stop = round(pos.entry_price * (1 - risk_pct if pos.direction == "LONG" else 1 + risk_pct), 6 if pos.entry_price < 1 else 2)
                        pos.current_stop = pos.initial_stop
                        pos.target_1 = round(pos.entry_price * (1 + t1_r * risk_pct if pos.direction == "LONG" else 1 - t1_r * risk_pct), 6 if pos.entry_price < 1 else 2)
                        pos.target_2 = round(pos.entry_price * (1 + t2_r * risk_pct if pos.direction == "LONG" else 1 - t2_r * risk_pct), 6 if pos.entry_price < 1 else 2)
                        self.storage.save_position(pos)
                    elif not pos.t1_hit:
                        # Ensure targets match active profile
                        r_dist = abs(pos.entry_price - pos.initial_stop)
                        if r_dist > 0:
                            expected_t1 = round(pos.entry_price + (r_dist * t1_r if pos.direction == "LONG" else -r_dist * t1_r), 6 if pos.entry_price < 1 else 2)
                            expected_t2 = round(pos.entry_price + (r_dist * t2_r if pos.direction == "LONG" else -r_dist * t2_r), 6 if pos.entry_price < 1 else 2)
                            if pos.target_1 != expected_t1 or pos.target_2 != expected_t2:
                                pos.target_1 = expected_t1
                                pos.target_2 = expected_t2
                                self.storage.save_position(pos)

                    self.order_mgr.update_position_with_price(pos, mark, account)
                else:
                    age = time.time() - (pos.entry_time or time.time())
                    # If position was dispatched within 10 seconds, give it grace time to populate on exchange
                    if age < 10.0 and getattr(pos, 'status', '') == 'OPEN':
                        synced_open.append(pos)
                        continue

                    if getattr(pos, 'status', '') == 'DISPATCH_FAILED':
                        continue

                    pos.status = "CLOSED"
                    pos.exit_time = time.time()
                    pos.exit_reason = "EXCHANGE_CLOSE"
                    pos.exit_price = pos.current_price or pos.entry_price
                    self.order_mgr._record_closed_trade_learning(pos)
                    self.storage.save_position(pos)
        else:
            open_positions = self.storage.get_open_positions()
            acc_prof = STRATEGY_PROFILES.get(account.strategy_profile, STRATEGY_PROFILES.get("FAST_SCALPER", {}))
            t1_r = acc_prof.get("target_1_r", 0.30)
            t2_r = acc_prof.get("target_2_r", 0.60)
            for pos in open_positions:
                price = self.data_feed.get_current_price(pos.symbol)
                pos.current_price = price
                if not pos.t1_hit:
                    r_dist = abs(pos.entry_price - pos.initial_stop)
                    if r_dist > 0:
                        pos.target_1 = round(pos.entry_price + (r_dist * t1_r if pos.direction == "LONG" else -r_dist * t1_r), 6 if pos.entry_price < 1 else 2)
                        pos.target_2 = round(pos.entry_price + (r_dist * t2_r if pos.direction == "LONG" else -r_dist * t2_r), 6 if pos.entry_price < 1 else 2)
                        self.storage.save_position(pos)
                self.order_mgr.update_position_with_price(pos, price, account)

        # Step 2: Run Curated Top 12 Prime Screener every 30 seconds or if empty
        now = time.time()
        candidates = self.storage.get_screener_candidates()
        if not candidates or (now - self.last_scan_time > 30.0):
            self.current_status = "SCREENING TOP 12 PRIME UNIVERSE (INSTITUTIONAL LIQUIDITY)"
            candidates = self.data_feed.scan_top_50(prime_only=True)
            self.storage.save_screener_candidates(candidates)
            self.last_scan_time = now

            top_picks = [c for c in candidates if c.is_active_focus and c.symbol in TOP_PRIME_SYMBOLS]
            if not top_picks:
                top_picks = [c for c in candidates if c.symbol in TOP_PRIME_SYMBOLS]
            pick_symbols = ", ".join([c.symbol for c in top_picks[:3]])
            self.storage.log_activity("SCREENER", "TOP_PRIME", f"Top 12 Prime Universe screened. Focused: {pick_symbols}", "INFO")

        # Step 3: Analyze top candidate coins across Engines A, B, and C with H1 -> M15 -> M5 Confluence
        # Focus strictly on Curated Top 12 Prime Universe for entry generation
        top_focus = [c for c in candidates if c.symbol in TOP_PRIME_SYMBOLS]
        if not top_focus:
            top_focus = candidates[:12]
        detected_opportunities: List[AnalysisOpportunity] = []
        symbol_candles: Dict[str, Any] = {}

        for cand in top_focus:
            self.current_status = f"ANALYZING REAL KLINES ON {cand.symbol}"
            m5_candles = self.data_feed.fetch_candles(cand.symbol, timeframe="5m", limit=30)
            m15_candles = self.data_feed.fetch_candles(cand.symbol, timeframe="15m", limit=30)
            h1_candles = self.data_feed.fetch_candles(cand.symbol, timeframe="1h", limit=50)
            symbol_candles[cand.symbol] = (m5_candles, m15_candles, h1_candles)

            # Classify regime
            self.active_regime = self.arbitrator.classify_regime(cand.change_24h, cand.volatility_pct)

            # Evaluate Engine A (ICT Liquidity) with M5, M15, H1
            opp_a = self.engine_a.evaluate(cand.symbol, m5_candles, h1_candles, m15_candles)
            if opp_a:
                detected_opportunities.append(opp_a)
                self.storage.save_analysis(opp_a)

            # Evaluate Engine B (Momentum IMP) with M5, M15, H1
            opp_b = self.engine_b.evaluate(cand.symbol, m5_candles, h1_candles, m15_candles)
            if opp_b:
                detected_opportunities.append(opp_b)
                self.storage.save_analysis(opp_b)

            # Evaluate Engine C (Liquidation Reversal) with M5, M15
            opp_c = self.engine_c.evaluate(cand.symbol, m5_candles, m15_candles)
            if opp_c:
                detected_opportunities.append(opp_c)
                self.storage.save_analysis(opp_c)

        # Step 4 & 5: Signal Arbitration & Execution for up to 5 concurrent positions
        distinct_symbols = set(o.symbol for o in detected_opportunities)
        candidate_opps = []
        for sym in distinct_symbols:
            sym_opps = [o for o in detected_opportunities if o.symbol == sym]
            best_for_sym = self.arbitrator.arbitrate(sym_opps, self.active_regime)
            if best_for_sym:
                candidate_opps.append(best_for_sym)

        candidate_opps.sort(key=lambda o: o.confidence_score, reverse=True)

        current_open = self.storage.get_open_positions()
        trades_opened = 0
        btc_trend = self.data_feed.get_btc_trend()

        for opp in candidate_opps:
            if len(current_open) >= MAX_CONCURRENT_POSITIONS:
                # Option A: Check for Stagnant Opportunity Swap if A+ Setup exists
                if AUTO_SWAP_ENABLED and opp.confidence_score >= (OPPORTUNITY_SWAP_MIN_SCORE / 100.0):
                    eligible_swap_pos = None
                    for pos in current_open:
                        if pos.symbol == opp.symbol or pos.t1_hit:
                            continue
                        trade_age = time.time() - (pos.entry_time or time.time())
                        if trade_age >= STAGNATION_TIMEOUT_SECONDS:
                            is_long = (pos.direction == "LONG")
                            cur_px = pos.current_price or self.data_feed.get_current_price(pos.symbol)
                            fee_cover_px = pos.entry_price * (1 + TRUE_FEE_BUFFER_PCT if is_long else 1 - TRUE_FEE_BUFFER_PCT)
                            # Strictly enforce: NO LOSS AFTER FEES
                            is_fee_covered = (cur_px >= fee_cover_px) if is_long else (cur_px <= fee_cover_px)
                            if is_fee_covered:
                                eligible_swap_pos = pos
                                break

                    if eligible_swap_pos:
                        mins_held = int((time.time() - eligible_swap_pos.entry_time) // 60)
                        swap_px = eligible_swap_pos.current_price or self.data_feed.get_current_price(eligible_swap_pos.symbol)
                        is_l = (eligible_swap_pos.direction == "LONG")
                        pnl = round(((swap_px - eligible_swap_pos.entry_price) if is_l else (eligible_swap_pos.entry_price - swap_px)) * eligible_swap_pos.quantity, 2)

                        # Gracefully close the stagnant trade
                        eligible_swap_pos.status = "CLOSED"
                        eligible_swap_pos.exit_price = swap_px
                        eligible_swap_pos.exit_reason = "STAGNANT_SWAP_FEE_PAID"
                        eligible_swap_pos.exit_time = time.time()
                        self.order_mgr._record_closed_trade_learning(eligible_swap_pos)
                        self.storage.save_position(eligible_swap_pos)
                        self.storage.update_account(balance=account.balance + pnl, realized_pnl_delta=pnl)

                        if account.mode == "BINANCE_TESTNET":
                            self.order_mgr._dispatch_binance_testnet_close(
                                eligible_swap_pos.symbol, eligible_swap_pos.direction, eligible_swap_pos.quantity, "STAGNANT_SWAP_FEE_PAID"
                            )

                        self.storage.log_activity(
                            action="OPPORTUNITY_SWAP",
                            coin=eligible_swap_pos.symbol,
                            detail=f"⚡ Swapped stagnant {eligible_swap_pos.symbol} (Held {mins_held}m, +${pnl:.2f} net after fees) for A+ setup {opp.symbol} ({int(opp.confidence_score*100)}% Conviction).",
                            level="SUCCESS"
                        )
                        current_open = [p for p in current_open if p.position_id != eligible_swap_pos.position_id]
                    else:
                        break
                else:
                    break
            cand_info = next((c for c in candidates if c.symbol == opp.symbol), None)
            sector = cand_info.sector if cand_info else "MAJOR"

            latest_open_ts = max([p.entry_time for p in current_open if p.entry_time] or [0.0])
            effective_last_ts = max(self.last_trade_opened_at, latest_open_ts)

            is_quar, quar_rem, quar_reason = self.storage.is_coin_quarantined(opp.symbol)

            approved, qty, risk_reason = self.risk_engine.approve_trade(
                account=account,
                opportunity=opp,
                open_positions=current_open,
                sector=sector,
                btc_trend=btc_trend,
                last_trade_time=effective_last_ts,
                is_quarantined=is_quar,
                quarantine_reason=quar_reason
            )

            if approved:
                # Calibrate targets to selected profile
                prof_key = getattr(account, "strategy_profile", "MODERATE_GROWTH") or "MODERATE_GROWTH"
                prof_data = STRATEGY_PROFILES.get(prof_key, STRATEGY_PROFILES["MODERATE_GROWTH"])
                t1_r = prof_data.get("target_1_r", 1.5)
                t2_r = prof_data.get("target_2_r", 3.0)
                r_dist = abs(opp.current_price - opp.stop_loss)
                if r_dist > 0:
                    opp.target_1 = round(opp.current_price + (r_dist * t1_r if opp.direction == "LONG" else -r_dist * t1_r), 6 if opp.current_price < 1 else 2)
                    opp.target_2 = round(opp.current_price + (r_dist * t2_r if opp.direction == "LONG" else -r_dist * t2_r), 6 if opp.current_price < 1 else 2)

                self.current_status = f"TAKING TRADE: {opp.direction} {opp.symbol} ({opp.engine})"
                new_pos = self.order_mgr.open_position(opp, qty, account.mode)
                self.last_trade_opened_at = time.time()
                current_open.append(new_pos)
                trades_opened += 1

                # Archive entry snapshot with multi-timeframe candles for dataset training
                candles_tuple = symbol_candles.get(opp.symbol)
                m5_c = candles_tuple[0] if candles_tuple else None
                m15_c = candles_tuple[1] if candles_tuple else None
                h1_c = candles_tuple[2] if candles_tuple else None
                self.storage.save_trade_snapshot(
                    position_id=new_pos.position_id,
                    symbol=new_pos.symbol,
                    engine=new_pos.engine,
                    direction=new_pos.direction,
                    entry_price=new_pos.entry_price,
                    m5_candles=m5_c,
                    m15_candles=m15_c,
                    h1_candles=h1_c,
                    btc_trend=btc_trend,
                    volatility_pct=getattr(cand_info, 'volatility_pct', 0.0) if cand_info else 0.0
                )
            else:
                self.storage.log_activity("RISK_GATE", opp.symbol, risk_reason, "WARNING")

        if trades_opened > 0:
            self.current_status = f"ACTIVE TRADING: {len(current_open)}/{MAX_CONCURRENT_POSITIONS} POSITIONS OPEN"
        elif current_open:
            self.current_status = f"MANAGING {len(current_open)}/{MAX_CONCURRENT_POSITIONS} POSITIONS · REGIME: {self.active_regime}"
        else:
            self.current_status = f"MONITORING MARKETS · REGIME: {self.active_regime}"

    def force_scan(self):
        self.last_scan_time = 0.0
        self.run_cycle()

    def flatten_all(self):
        account = self.storage.get_account()
        open_positions = self.storage.get_open_positions()
        for pos in open_positions:
            price = self.data_feed.get_current_price(pos.symbol)
            self.order_mgr.close_position_manually(pos.position_id, price, account)

        if account.mode == "BINANCE_TESTNET":
            testnet_positions = self.order_mgr.fetch_binance_testnet_positions()
            for tp in testnet_positions:
                amt = float(tp["positionAmt"])
                if abs(amt) > 0:
                    dir_str = "LONG" if amt > 0 else "SHORT"
                    self.order_mgr._dispatch_binance_testnet_close(tp["symbol"], dir_str, abs(amt), "FLATTEN_ALL")

        self.storage.log_activity("PANIC", "ALL", "Operator triggered FLATTEN ALL. All crypto positions closed.", "DANGER")

    def set_strategy_profile(self, profile: str):
        if profile in STRATEGY_PROFILES:
            self.storage.set_strategy_profile(profile)
            p_info = STRATEGY_PROFILES[profile]
            t1_r = p_info.get("target_1_r", 0.30)
            t2_r = p_info.get("target_2_r", 0.60)
            open_pos = self.storage.get_open_positions()
            for p in open_pos:
                if not p.t1_hit:
                    r_dist = abs(p.entry_price - p.initial_stop)
                    if r_dist > 0:
                        p.target_1 = round(p.entry_price + (r_dist * t1_r if p.direction == "LONG" else -r_dist * t1_r), 6 if p.entry_price < 1 else 2)
                        p.target_2 = round(p.entry_price + (r_dist * t2_r if p.direction == "LONG" else -r_dist * t2_r), 6 if p.entry_price < 1 else 2)
                        self.storage.save_position(p)
            self.storage.log_activity("PROFILE", "CONFIG", f"Switched strategy profile to {p_info['name']} ({p_info['risk_per_trade_pct']}% risk, TP1={t1_r}R, TP2={t2_r}R).", "INFO")

    def reset(self):
        live_acc = self.order_mgr.fetch_binance_testnet_account()
        wallet_bal = float(live_acc.get("totalWalletBalance")) if (live_acc and live_acc.get("totalWalletBalance")) else None
        self.storage.reset_system(new_balance=wallet_bal)
        bal_str = f"${wallet_bal:.2f}" if wallet_bal else "$1,000 baseline"
        self.storage.log_activity("RESET", "CORE", f"Crypto Sentinel state completely reset. Baseline calibrated to {bal_str}.", "WARNING")

    def get_dashboard_state(self) -> Dict[str, Any]:
        account = self.storage.get_account()
        testnet_info = None
        open_positions = self.storage.get_open_positions()

        if account.mode == "BINANCE_TESTNET":
            live_acc = self.order_mgr.fetch_binance_testnet_account()
            if live_acc:
                total_wallet = float(live_acc.get("totalWalletBalance", account.balance))
                unrealized = float(live_acc.get("totalUnrealizedProfit", 0.0))
                avail = float(live_acc.get("availableBalance", total_wallet))
                self.storage.sync_testnet_account(total_wallet, avail)
                account = self.storage.get_account()
                testnet_info = {
                    "total_wallet_balance": round(total_wallet, 2),
                    "total_unrealized_pnl": round(unrealized, 2),
                    "available_balance": round(avail, 2)
                }

            # Direct sync with Binance Testnet positions to eliminate any lag or mismatch
            testnet_positions = self.order_mgr.fetch_binance_testnet_positions()
            synced_open = []
            seen_symbols = set()

            for pos in open_positions:
                if pos.symbol in seen_symbols:
                    pos.status = "CLOSED"
                    pos.exit_time = time.time()
                    pos.exit_reason = "DUPLICATE_CLEANUP"
                    self.storage.save_position(pos)
                    continue

                tp = next((t for t in testnet_positions if t.get("symbol") == pos.symbol), None)
                if tp:
                    seen_symbols.add(pos.symbol)
                    amt = float(tp["positionAmt"])
                    pos.direction = "LONG" if amt > 0 else "SHORT"
                    pos.quantity = abs(amt)
                    pos.entry_price = float(tp["entryPrice"])
                    pos.unrealized_pnl = round(float(tp["unRealizedProfit"]), 2)
                    mark = float(tp["markPrice"])
                    pos.current_price = mark

                    acc_prof = STRATEGY_PROFILES.get(account.strategy_profile, STRATEGY_PROFILES.get("FAST_SCALPER", {}))
                    t1_r = acc_prof.get("target_1_r", 0.30)
                    t2_r = acc_prof.get("target_2_r", 0.60)

                    # Recalibrate stops/targets if mismatched or inherited from synthetic price scale (only when defensive stop is not yet active)
                    dist_pct = abs(pos.current_stop - pos.entry_price) / pos.entry_price if pos.entry_price > 0 else 1.0
                    is_stop_wrong = ((pos.current_stop >= pos.entry_price) if pos.direction == "LONG" else (pos.current_stop <= pos.entry_price)) if not pos.defensive_active else False
                    if dist_pct > 0.08 or is_stop_wrong:
                        risk_pct = 0.015
                        pos.initial_stop = round(pos.entry_price * (1 - risk_pct if pos.direction == "LONG" else 1 + risk_pct), 6 if pos.entry_price < 1 else 2)
                        pos.current_stop = pos.initial_stop
                        pos.target_1 = round(pos.entry_price * (1 + t1_r * risk_pct if pos.direction == "LONG" else 1 - t1_r * risk_pct), 6 if pos.entry_price < 1 else 2)
                        pos.target_2 = round(pos.entry_price * (1 + t2_r * risk_pct if pos.direction == "LONG" else 1 - t2_r * risk_pct), 6 if pos.entry_price < 1 else 2)
                        self.storage.save_position(pos)
                    elif not pos.t1_hit:
                        r_dist = abs(pos.entry_price - pos.initial_stop)
                        if r_dist > 0:
                            pos.target_1 = round(pos.entry_price + (r_dist * t1_r if pos.direction == "LONG" else -r_dist * t1_r), 6 if pos.entry_price < 1 else 2)
                            pos.target_2 = round(pos.entry_price + (r_dist * t2_r if pos.direction == "LONG" else -r_dist * t2_r), 6 if pos.entry_price < 1 else 2)
                            self.storage.save_position(pos)

                    risk_dist = abs(pos.entry_price - pos.initial_stop)
                    move = (mark - pos.entry_price) if pos.direction == "LONG" else (pos.entry_price - mark)
                    pos.unrealized_r = round(move / risk_dist, 2) if risk_dist > 0 else 0.0
                    synced_open.append(pos)
                else:
                    age = time.time() - (pos.entry_time or time.time())
                    # If position was dispatched within 10 seconds, give it grace time to populate on exchange
                    if age < 10.0 and getattr(pos, 'status', '') == 'OPEN':
                        synced_open.append(pos)
                        continue

                    if getattr(pos, 'status', '') == 'DISPATCH_FAILED':
                        continue

                    pos.status = "CLOSED"
                    pos.exit_time = time.time()
                    pos.exit_reason = "EXCHANGE_CLOSE"
                    pos.exit_price = pos.current_price or pos.entry_price
                    self.order_mgr._record_closed_trade_learning(pos)
                    self.storage.save_position(pos)

            for tp in testnet_positions:
                if not any(p.symbol == tp["symbol"] for p in synced_open):
                    amt = float(tp["positionAmt"])
                    entry_p = float(tp["entryPrice"])
                    mark_p = float(tp["markPrice"])
                    pnl = round(float(tp["unRealizedProfit"]), 2)
                    direction = "LONG" if amt > 0 else "SHORT"
                    pos_id = f"POS_{tp['symbol']}_{int(time.time())}"
                    
                    acc_prof = STRATEGY_PROFILES.get(account.strategy_profile, STRATEGY_PROFILES.get("FAST_SCALPER", {}))
                    t1_r = acc_prof.get("target_1_r", 0.30)
                    t2_r = acc_prof.get("target_2_r", 0.60)
                    risk_pct = 0.015
                    stop_l = round(entry_p * (1 - risk_pct if direction == "LONG" else 1 + risk_pct), 6 if entry_p < 1 else 2)
                    risk_d = abs(entry_p - stop_l)
                    tp1 = round(entry_p + (risk_d * t1_r if direction == "LONG" else -risk_d * t1_r), 6 if entry_p < 1 else 2)
                    tp2 = round(entry_p + (risk_d * t2_r if direction == "LONG" else -risk_d * t2_r), 6 if entry_p < 1 else 2)
                    new_synced = CryptoPosition(
                        position_id=pos_id,
                        symbol=tp["symbol"],
                        engine="BINANCE_EXCHANGE",
                        direction=direction,
                        entry_price=entry_p,
                        quantity=abs(amt),
                        initial_stop=stop_l,
                        current_stop=stop_l,
                        target_1=tp1,
                        target_2=tp2,
                        current_price=mark_p,
                        unrealized_pnl=pnl,
                        unrealized_r=0.0,
                        status="OPEN"
                    )
                    self.storage.save_position(new_synced)
                    synced_open.append(new_synced)

            open_positions = synced_open

        closed_trades = self.storage.get_closed_positions(limit=15)
        screener = self.storage.get_screener_candidates()
        analyses = self.storage.get_latest_analyses(limit=6)
        logs = self.storage.get_activity_logs(limit=12)

        # Ensure current status accurately reflects real-time open positions
        if self.running:
            if len(open_positions) == 0:
                self.current_status = f"SCANNING UNIVERSE · 0/{MAX_CONCURRENT_POSITIONS} POSITIONS OPEN · REGIME: {self.active_regime}"
            else:
                self.current_status = f"MANAGING {len(open_positions)}/{MAX_CONCURRENT_POSITIONS} POSITIONS · REGIME: {self.active_regime}"

        return {
            "running": self.running,
            "status": self.current_status,
            "regime": self.active_regime,
            "account": account.to_dict(),
            "strategy_profiles": STRATEGY_PROFILES,
            "selected_profile": getattr(account, "strategy_profile", "MODERATE_GROWTH") or "MODERATE_GROWTH",
            "testnet_info": testnet_info,
            "open_positions": [p.to_dict() for p in open_positions],
            "closed_trades": [t.to_dict() for t in closed_trades],
            "coin_intelligence": self.storage.get_coin_intelligence(),
            "trade_snapshots": self.storage.get_trade_snapshots(limit=10),
            "screener_candidates": [c.to_dict() for c in screener],
            "latest_analyses": [a.to_dict() for a in analyses],
            "activity_logs": [l.to_dict() for l in logs]
        }

# Global Singleton Instance for API access
CRYPTO_BOT = CryptoBotController()
