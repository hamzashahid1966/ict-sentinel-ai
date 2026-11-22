"""
ICT Sentinel AI — Real-Time Streaming Command Center with Live Activity Radar
Dual-column institutional dashboard:
- Left Column: KPIs, Live Equity Curve, Active Positions, Market Feeds, Trade Journal.
- Right Column: Live Bot Activity Radar, Real-Time Event Stream, Risk Circuit Breakers.
"""

import os
import json
import queue
import threading
import datetime
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from typing import Dict, Any, List, Optional, Set

from .config import ASSET_SPECS, INITIAL_CAPITAL, NY_TZ, LON_TZ, MAX_BAR_AGE_MINUTES, AUTO_TRADING_ENABLED
from .storage import StorageEngine
from .data_feed import DataFeedEngine
from .ipda_engine import IPDAEngine
from .ai_advisor import AIAdvisor
from .order_manager import OrderManager
from .memory_engine import MemoryEngine
from .models import Candle
from polymarket_sentinel.controller import POLY_BOT
from crypto_sentinel.controller import CRYPTO_BOT


class BotController:
    """Thread-safe singleton owning the trading engine, activity stream, and SSE broadcast hub."""

    def __init__(self):
        self.storage = StorageEngine()
        self.advisor = AIAdvisor()
        self.memory_engine = MemoryEngine(self.storage, self.advisor)
        self.order_mgr = OrderManager(self.storage, self.advisor, memory_engine=self.memory_engine)
        self.ipda = IPDAEngine()
        self.data_feed = DataFeedEngine(mode="live")

        self.is_running = False
        self.is_demo_running = False
        self.worker_thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        self.last_cycle_time: Optional[str] = None
        self.current_prices: Dict[str, float] = {a: 0.0 for a in ASSET_SPECS}
        self.last_checked_session: Optional[str] = None
        self._stale_assets: Set[str] = set()
        self.auto_trading_enabled: bool = AUTO_TRADING_ENABLED
        self._disabled_notice_sent: bool = False
        self.lock = threading.Lock()

        # Real-time Activity Event Buffer (stores latest 50 live micro-events)
        self.activity_events: List[Dict[str, Any]] = []
        self._add_activity("SYSTEM", "Engine Initialized", "All 52-Lecture IPDA modules & Double Tap OMS loaded.", "ready")

        # SSE Subscriber Queues
        self.subscribers: Set[queue.Queue] = set()
        self.sub_lock = threading.Lock()

    # ── Activity Event Logging ────────────────────────────────────────
    def _add_activity(self, category: str, title: str, details: str, level: str = "info"):
        now_str = datetime.datetime.now(datetime.timezone.utc).strftime("%H:%M:%S UTC")
        event = {
            "time": now_str,
            "category": category,
            "title": title,
            "details": details,
            "level": level
        }
        self.activity_events.insert(0, event)
        if len(self.activity_events) > 50:
            self.activity_events.pop()

    # ── SSE Broker Hub ────────────────────────────────────────────────
    def subscribe(self) -> queue.Queue:
        q = queue.Queue(maxsize=100)
        with self.sub_lock:
            self.subscribers.add(q)
        return q

    def unsubscribe(self, q: queue.Queue):
        with self.sub_lock:
            self.subscribers.discard(q)

    def broadcast_state(self):
        """Pushes current full state snapshot to all connected streaming clients."""
        state = self.get_full_state()
        data = f"data: {json.dumps(state)}\n\n"
        with self.sub_lock:
            dead_queues = []
            for q in self.subscribers:
                try:
                    q.put_nowait(data)
                except queue.Full:
                    dead_queues.append(q)
            for dq in dead_queues:
                self.subscribers.discard(dq)

    # ── Engine Lifecycle ──────────────────────────────────────────────
    def start(self):
        with self.lock:
            if self.is_running:
                return
            self.is_running = True
            self.stop_event.clear()
            self._add_activity("ENGINE", "Live Engine Started", "Subscribed to CME & Forex live feeds. 15s scan loop active.", "success")
            self.worker_thread = threading.Thread(target=self._run_loop, daemon=True)
            self.worker_thread.start()
        self.broadcast_state()

    def stop(self):
        with self.lock:
            if not self.is_running:
                return
            self.is_running = False
            self.stop_event.set()
            self._add_activity("ENGINE", "Engine Paused", "Scanning paused. All open positions & stop brackets preserved.", "warning")
        self.broadcast_state()

    def _run_loop(self):
        while not self.stop_event.is_set():
            try:
                self._execute_cycle()
            except Exception as e:
                print(f"[!] Worker cycle error: {e}")
                self._add_activity("ERROR", "Execution Cycle Error", str(e), "danger")
            self.stop_event.wait(30)

    def _execute_cycle(self):
        self.last_cycle_time = datetime.datetime.now(
            datetime.timezone.utc
        ).strftime("%Y-%m-%d %H:%M:%S UTC")

        state_changed = False
        now_et = datetime.datetime.now(NY_TZ)
        current_session = self.ipda.get_current_session(now_et.time())

        # Inter-session transition detection & automated debrief generation
        if self.last_checked_session and current_session != self.last_checked_session:
            prev_session = self.last_checked_session
            sample_asset = 'EURUSD' if prev_session == 'LONDON' else 'NASDAQ'
            c_list = self.data_feed.candle_cache.get(sample_asset, [])
            rec_trades = self.storage.get_trade_history(limit=20)
            s_trades = [t for t in rec_trades if t.session == prev_session]
            d_str = now_et.strftime('%Y-%m-%d')
            debrief = self.ipda.generate_session_debrief(prev_session, c_list, s_trades, d_str)
            self.storage.record_session_debrief(debrief)
            debrief_log = self.advisor.explain_session_debrief(debrief)
            self.storage.log_ai_thought(debrief_log)
            self._add_activity("SESSION", f"Session Closed: {prev_session}", f"Bias for next session: {debrief.cross_session_bias}", "warning")
            state_changed = True

        self.last_checked_session = current_session
        assets_synced = 0
        for asset in ASSET_SPECS:
            if self.stop_event.is_set():
                break
            candles = self.data_feed.fetch_recent_bars(asset, interval="5m", limit=180)
            if not candles:
                continue
            assets_synced += 1
            current_bar = candles[-1]
            if self.current_prices[asset] != current_bar.close:
                self.current_prices[asset] = current_bar.close
                state_changed = True

            # 1. Update positions (Bank 1.5R Center Mass or Trail Stops)
            closed_trades = self.order_mgr.update_positions_with_bar(asset, current_bar)
            if closed_trades:
                state_changed = True
                for tr in closed_trades:
                    lvl = "success" if tr.dollar_pnl > 0 else "danger"
                    self._add_activity("TRADE", f"Position Closed [{tr.outcome}]", f"{tr.asset} {tr.direction} exit @ {tr.exit_price:.2f} (Net: ${tr.dollar_pnl:+.2f})", lvl)

            # 2. Check for new signals (never on a stale tape, never while the kill switch is off)
            if not self.auto_trading_enabled:
                if not self._disabled_notice_sent:
                    self._disabled_notice_sent = True
                    self._add_activity("RISK", "Auto-Trading DISABLED", "ICT live entries are switched off (ICT_AUTO_TRADING_ENABLED is not true). Open positions are still managed; diagnostics and demo replay still run. See docs/GOLD_LONDON_MODEL_VALIDATION.md.", "warning")
                    state_changed = True
                continue
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            if not self.ipda.bars_are_fresh(candles, now_utc):
                if asset not in self._stale_assets:
                    self._stale_assets.add(asset)
                    age_min = int((now_utc - current_bar.timestamp.astimezone(datetime.timezone.utc)).total_seconds() // 60)
                    self._add_activity("DATA", f"Stale Tape: {asset}", f"Latest bar is {age_min} min old (limit {MAX_BAR_AGE_MINUTES}). Entries suspended until the feed catches up.", "warning")
                continue
            self._stale_assets.discard(asset)
            signal = self.ipda.evaluate_market(asset, candles, memory_engine=self.memory_engine, now_utc=now_utc)
            if signal:
                opened = self.order_mgr.open_position_from_signal(signal, current_bar.timestamp_et)
                if opened:
                    state_changed = True
                    self._add_activity("ORDER", f"New Order [{signal.direction}]", f"{signal.asset} @ {signal.entry_price:.2f} | Stop: {signal.stop_loss:.2f} | Target: {signal.target_head_shot:.2f}", "accent")

        if assets_synced > 0:
            self._add_activity("DATA", "Market Tape Synchronized", f"Updated 5m bars for {assets_synced} assets. Micro-structure valid.", "info")
            state_changed = True

        if state_changed:
            self.broadcast_state()

    # ── Accelerated Simulation ───────────────────────────────────────
    def run_demo(self):
        if self.is_demo_running:
            return
        threading.Thread(target=self._exec_demo, daemon=True).start()

    def _exec_demo(self):
        self.is_demo_running = True
        # A replay must not append to the permanent learning ledger.
        prev_persist = self.memory_engine.persist_knowledge
        self.memory_engine.persist_knowledge = False
        self._add_activity("SIMULATION", "Accelerated Simulation Started", "Replaying 1,500 historical bars across CME & Forex feeds...", "accent")
        self.broadcast_state()
        try:
            trades_created = 0
            for asset in ASSET_SPECS:
                self._add_activity("LIVE_FEED", f"Connecting CME / Forex Feed: {asset}", "Pulling latest continuous live exchange bars over network...", "info")
                self.broadcast_state()
                candles = self.data_feed.fetch_live_simulation_bars(asset, limit=1500)
                if not candles:
                    continue
                latest_c = candles[-1]
                self._add_activity("LIVE_FEED", f"Synced {len(candles)} Live Bars: {asset}", f"Live quote: {latest_c.close:.2f} (Bar Timestamp: {latest_c.timestamp_et.strftime('%m/%d %H:%M EST')})", "success")
                self.broadcast_state()

                rolling: List[Candle] = []
                for c in candles:
                    rolling.append(c)
                    if len(rolling) > 60:
                        rolling.pop(0)
                    if len(rolling) >= 20:
                        closed = self.order_mgr.update_positions_with_bar(asset, c)
                        if closed:
                            for tr in closed:
                                trades_created += 1
                                lvl = "success" if tr.dollar_pnl > 0 else "danger"
                                self._add_activity("TRADE", f"Simulation Trade: {tr.asset}", f"{tr.direction} exit @ {tr.exit_price:.2f} (Net: ${tr.dollar_pnl:+.2f})", lvl)
                        sig = self.ipda.evaluate_market(asset, rolling, memory_engine=self.memory_engine)
                        if sig:
                            opened = self.order_mgr.open_position_from_signal(sig, c.timestamp_et)
                            if opened:
                                self._add_activity("ORDER", f"Signal Executed: {sig.asset}", f"{sig.direction} @ {sig.entry_price:.2f} | 50% CE: {sig.pd_array.consequent_encroachment:.2f}", "accent")
            self._add_activity("SIMULATION", "Live Simulation Completed", f"Processed live market stream. Strategy tested on real bars.", "success")
        finally:
            self.memory_engine.persist_knowledge = prev_persist
            self.is_demo_running = False
            self.broadcast_state()

    # ── Manual Position Controls ─────────────────────────────────────
    def flatten_all(self):
        with self.lock:
            closed = self.order_mgr.flatten_all_positions(self.current_prices)
            self._add_activity("EMERGENCY", "Flattened All Positions", f"Manually liquidated {len(closed)} open position(s) at market.", "danger")
        self.broadcast_state()

    def close_single(self, pos_id: str):
        with self.lock:
            positions = [p for p in self.storage.load_open_positions() if p.position_id == pos_id]
            if positions:
                px = self.current_prices.get(positions[0].asset, positions[0].entry_price)
                self.order_mgr.close_single_position(pos_id, px, reason="Dashboard Action")
                self._add_activity("TRADE", f"Manual Close #{pos_id}", f"Liquidated {positions[0].asset} contract at {px:.2f}.", "warning")
        self.broadcast_state()

    def reset_account(self):
        with self.lock:
            self.storage.reset_account(INITIAL_CAPITAL)
            self._add_activity("SYSTEM", "Account Reset", f"Balance reset to ${INITIAL_CAPITAL:.2f}. All records cleared.", "warning")
        self.broadcast_state()

    # ── State Representation ─────────────────────────────────────────
    @staticmethod
    def calculate_session_schedule(now_et: datetime.datetime) -> Dict[str, Any]:
        schedule = [
            ('LONDON', datetime.time(2, 0), datetime.time(4, 30), 'London Killzone'),
            ('LONDON_CORE', datetime.time(4, 30), datetime.time(7, 0), 'London Core (Gold Active)'),
            ('NEW_YORK_AM', datetime.time(8, 0), datetime.time(10, 30), 'New York AM Killzone'),
            ('ASIAN_MACRO', datetime.time(18, 50), datetime.time(20, 15), 'Asian Macro / CME Open'),
        ]
        weekday = now_et.weekday()
        t = now_et.time()

        # Check active session
        for name, start_t, end_t, label in schedule:
            if weekday == 4 and name == 'ASIAN_MACRO':
                continue
            if weekday == 5:
                continue
            if weekday == 6 and name in ('LONDON', 'NEW_YORK_AM'):
                continue
            if start_t <= t <= end_t:
                close_dt = now_et.replace(hour=end_t.hour, minute=end_t.minute, second=0, microsecond=0)
                sec_left = int((close_dt - now_et).total_seconds())
                return {
                    'active': True,
                    'session': name,
                    'label': label,
                    'status': 'ACTIVE',
                    'target_desc': f'{label} closes in',
                    'target_time': close_dt.isoformat(),
                    'seconds_left': max(0, sec_left),
                    'est_time': now_et.strftime('%H:%M:%S EST'),
                }

        # Find next session
        candidates = []
        for day_offset in range(4):
            cand_date = now_et.date() + datetime.timedelta(days=day_offset)
            cand_weekday = cand_date.weekday()
            for name, start_t, end_t, label in schedule:
                if cand_weekday == 4 and name == 'ASIAN_MACRO':
                    continue
                if cand_weekday == 5:
                    continue
                if cand_weekday == 6 and name in ('LONDON', 'NEW_YORK_AM'):
                    continue
                cand_dt = datetime.datetime.combine(cand_date, start_t, tzinfo=now_et.tzinfo)
                if cand_dt > now_et:
                    candidates.append((cand_dt, name, label))

        if candidates:
            candidates.sort(key=lambda x: x[0])
            next_dt, name, label = candidates[0]
            sec_left = int((next_dt - now_et).total_seconds())
            return {
                'active': False,
                'session': 'OFF-SESSION',
                'next_session': name,
                'label': label,
                'status': 'OFF_SESSION',
                'target_desc': f'{label} opens in',
                'target_time': next_dt.isoformat(),
                'seconds_left': max(0, sec_left),
                'est_time': now_et.strftime('%H:%M:%S EST'),
            }
        return {
            'active': False,
            'session': 'OFF-SESSION',
            'next_session': 'MARKET_HALT',
            'label': 'Weekend Close',
            'status': 'OFF_SESSION',
            'target_desc': 'Market opens Sunday 18:50 EST',
            'target_time': '',
            'seconds_left': 0,
            'est_time': now_et.strftime('%H:%M:%S EST'),
        }

    def get_full_state(self) -> Dict[str, Any]:
        acct = self.storage.get_account_state()
        open_pos = self.storage.load_open_positions()
        trades = self.storage.get_trade_history(limit=50)
        logs = self.storage.get_recent_ai_logs(limit=25)
        weights = self.memory_engine.get_all_weights()
        reflections = self.memory_engine.get_recent_reflections(limit=5)

        now_et = datetime.datetime.now(NY_TZ)
        session_info = self.calculate_session_schedule(now_et)
        session = session_info["session"]

        wins = [t for t in trades if t.dollar_pnl > 0]
        losses_list = [t for t in trades if t.dollar_pnl < 0]
        total = len(trades)
        wr = (len(wins) / total * 100) if total else 0
        gp = sum(t.dollar_pnl for t in wins)
        gl = abs(sum(t.dollar_pnl for t in losses_list))
        pf = (gp / gl) if gl > 0 else (999 if gp > 0 else 0)

        eq = [{"t": "Start", "b": INITIAL_CAPITAL}]
        bal = INITIAL_CAPITAL
        for t in reversed(trades):
            bal += t.dollar_pnl
            eq.append({"t": t.exit_time, "b": round(bal, 2)})

        assets = []
        for a, s in ASSET_SPECS.items():
            px = self.current_prices.get(a, 0.0)
            cache_candles = self.data_feed.candle_cache.get(a, [])
            last_bar_time = cache_candles[-1].timestamp_et.strftime('%m/%d %H:%M EST') if cache_candles else "Syncing..."
            assets.append({
                "a": a, "sym": s["symbol"], "dn": s["display_name"],
                "px": px, "ip": any(p.asset == a for p in open_pos),
                "last_bar_time": last_bar_time,
                "source": "LIVE CME / INTERBANK"
            })

        pos = []
        for p in open_pos:
            px = self.current_prices.get(p.asset, p.entry_price)
            spec = ASSET_SPECS[p.asset]
            pts = (px - p.entry_price) if p.direction == "LONG" else (p.entry_price - px)
            unr = (pts * spec["point_value"]) if px > 0 else 0
            pos.append({
                "id": p.position_id, "a": p.asset, "d": p.direction,
                "ep": p.entry_price, "ts": p.active_trailing_stop,
                "cm": p.target_center_mass, "hs": p.target_head_shot,
                "cmf": p.center_mass_filled, "rp": p.realized_pnl,
                "unr": round(unr, 2), "st": p.status,
                "ce": p.defending_fvg_ce, "targ": p.target_liquidity_pool,
                "inv": p.invalidation_reason, "orig": p.session_origin
            })

        tds = []
        for t in trades:
            tds.append({
                "id": t.trade_id, "a": t.asset, "ss": t.session,
                "d": t.direction, "et": t.entry_time, "ep": t.entry_price,
                "xt": t.exit_time, "xp": t.exit_price,
                "pnl": t.dollar_pnl, "out": t.outcome, "ai": t.ai_reasoning,
                "tp1": t.target_tp1_price, "tp2": t.target_tp2_price,
                "inv": t.invalidation_reason, "targ": t.target_liquidity_pool
            })

        lg = []
        for l in logs:
            lg.append({
                "ts": l.timestamp, "a": l.asset, "cat": l.category,
                "msg": l.message, "rsn": l.reasoning,
            })

        # Calculate Consecutive Losses across all sessions
        cons_losses = max([w.get("consecutive_losses", 0) for w in weights], default=0)

        # Multi-Asset AI Market Diagnostics & Decision Matrix
        diagnostics = []
        for a in ASSET_SPECS:
            c_list = self.data_feed.candle_cache.get(a, [])
            diag = self.ipda.diagnose_market(a, c_list, memory_engine=self.memory_engine)
            diagnostics.append(diag)

        # Micro-state string
        current_dd = self.storage.get_daily_drawdown(datetime.datetime.now(NY_TZ).date().isoformat())
        locked_for_day = current_dd >= 50.0
        if locked_for_day:
            micro_state = f"Daily Risk Budget Exceeded (${current_dd:.2f} / $50.00) — Circuit Breaker Locked (Capital Protected)"
        elif not self.is_running:
            micro_state = "Engine Idle (Click 'Start Engine' to activate live tape scanning)"
        elif len(open_pos) > 0:
            micro_state = f"Managing {len(open_pos)} active Double Tap position(s) with Defensive Shields"
        elif session == "OFF-SESSION":
            next_name = session_info.get("label", "Next Session")
            micro_state = f"Engine Armed & Monitoring Tape — Standing by for {next_name}"
        else:
            micro_state = f"Actively scanning 5m bars in {session} for sweeps & body MSS"

        meta_reflections = self.memory_engine.get_latest_meta_reflections(limit=5)
        if not meta_reflections:
            meta_reflections = [self.memory_engine.synthesize_weekly_meta_reflection()]

        from .config import INSTITUTIONAL_GOALS

        return {
            "running": self.is_running,
            "auto_trading_enabled": self.auto_trading_enabled,
            "demo": self.is_demo_running,
            "session": session,
            "session_info": session_info,
            "micro_state": micro_state,
            "cycle": self.last_cycle_time,
            "acct": {
                "bal": round(acct.balance, 2),
                "peak": round(acct.peak_balance, 2),
                "pnl": round(acct.realized_pnl, 2),
                "mdd": round(acct.max_drawdown_dollars, 2),
                "mddp": round(acct.max_drawdown_pct, 1),
                "wr": round(wr, 1), "pf": round(pf, 2),
                "sharpe": meta_reflections[0]['realized_sharpe'] if meta_reflections else 0.0,
                "tt": total, "w": len(wins), "l": len(losses_list),
            },
            "goals": INSTITUTIONAL_GOALS,
            "meta_reflections": meta_reflections,
            "eq": eq, "assets": assets, "pos": pos,
            "trades": tds, "logs": lg,
            "diagnostics": diagnostics,
            "debriefs": self.storage.get_latest_session_debriefs(limit=5),
            "mem": weights, "ref": reflections,
            "activity": self.activity_events,
            "risk_guards": {
                "consecutive_losses": cons_losses,
                "max_consecutive_allowed": 2,
                "daily_risk_budget": 50.00,
                "drawdown_current": round(current_dd, 2),
                "locked_for_day": locked_for_day
            }
        }


BOT = BotController()


# ── Full Real-Time Browser Command Center with Live Activity Radar ──
HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ICT Sentinel AI — Institutional Command Center</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root{
  --bg:#06080E;--card:#0C101A;--card-inner:#121826;--bdr:#1A2234;--bdr-hover:#2A3752;
  --tx:#F8FAFC;--tx2:#94A3B8;--tx3:#64748B;
  --ac:#6366F1;--acg:rgba(99,102,241,.25);
  --gr:#10B981;--grg:rgba(16,185,129,.2);--grb:rgba(16,185,129,.1);
  --rd:#F43F5E;--rdb:rgba(244,63,94,.1);
  --am:#F59E0B;--amb:rgba(245,158,11,.1);
}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--tx);font-family:'Plus Jakarta Sans',system-ui,sans-serif;min-height:100vh}

/* Header */
header{background:rgba(12,16,26,.94);backdrop-filter:blur(18px);border-bottom:1px solid var(--bdr);padding:12px 24px;display:flex;justify-content:space-between;align-items:center;position:sticky;top:0;z-index:99}
.hl{display:flex;align-items:center;gap:14px}
.icon{background:linear-gradient(135deg,#6366F1,#8B5CF6);width:38px;height:38px;border-radius:10px;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:18px;color:#fff;box-shadow:0 0 18px var(--acg)}
.brand{font-size:16px;font-weight:700;letter-spacing:-.02em}
.sub{font-size:11px;color:var(--tx2);font-family:'JetBrains Mono',monospace}
.hr{display:flex;align-items:center;gap:8px}
.pill{display:flex;align-items:center;gap:7px;background:#151C2C;border:1px solid var(--bdr);padding:5px 12px;border-radius:20px;font-size:11px;font-family:'JetBrains Mono',monospace;color:#CBD5E1}
.stream-pill{display:flex;align-items:center;gap:6px;background:rgba(16,185,129,.08);border:1px solid rgba(16,185,129,.25);padding:5px 11px;border-radius:20px;font-size:10.5px;font-family:'JetBrains Mono',monospace;color:var(--gr)}
.stream-pill.disconnected{background:var(--rdb);border-color:rgba(244,63,94,.3);color:var(--rd)}
.dot{width:8px;height:8px;border-radius:50%;background:var(--gr);box-shadow:0 0 10px var(--gr);animation:p 1.8s infinite}
.dot.off{background:var(--am);box-shadow:0 0 10px var(--am);animation:none}
@keyframes p{0%{opacity:.3;transform:scale(.9)}50%{opacity:1;transform:scale(1.15)}100%{opacity:.3;transform:scale(.9)}}

/* Running Session Clocks & Countdown */
.session-badge-wrap{display:flex;align-items:center;gap:6px}
.timer-pill{display:inline-flex;align-items:center;gap:6px;background:#101726;border:1px solid #1E293B;padding:5px 12px;border-radius:20px;font-size:11px;font-family:'JetBrains Mono',monospace;color:#94A3B8;transition:all .2s ease}
.timer-pill.active{background:rgba(16,185,129,.08);border-color:rgba(16,185,129,.3);color:var(--gr)}
.timer-pill.off{background:rgba(245,158,11,.08);border-color:rgba(245,158,11,.25);color:#FBBF24}
.timer-pill .t-icon{font-size:11px}
.timer-pill .t-lbl{font-weight:600}
.timer-pill .t-val{font-weight:700;color:#F8FAFC;letter-spacing:.02em;font-variant-numeric:tabular-nums}
.timer-pill.active .t-val{color:#34D399}
.timer-pill.off .t-val{color:#FDE68A}

/* Clock Box in Right Sidebar */
.clock-box{padding:12px 14px;background:#090D15;border-bottom:1px solid var(--bdr);display:flex;flex-direction:column;gap:8px}
.clock-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.clock-item{background:#0D131F;border:1px solid var(--bdr);border-radius:6px;padding:6px 8px;display:flex;flex-direction:column;gap:2px}
.clock-lbl{font-size:9.5px;font-weight:600;color:var(--tx3);text-transform:uppercase;letter-spacing:.04em}
.clock-val{font-size:11.5px;font-weight:700;font-family:'JetBrains Mono',monospace;color:#E2E8F0;font-variant-numeric:tabular-nums}
.clock-status-bar{background:#0D131F;border:1px solid rgba(245,158,11,.2);border-radius:6px;padding:7px 10px;display:flex;align-items:center;gap:7px;font-size:11px;font-family:'JetBrains Mono',monospace;color:#FBBF24}
.clock-status-bar.active{border-color:rgba(16,185,129,.3);color:var(--gr)}

.btn{padding:7px 14px;border-radius:8px;font-size:12px;font-weight:600;cursor:pointer;border:none;transition:all .15s;display:inline-flex;align-items:center;gap:5px}
.btn:hover{transform:translateY(-1px)}
.btn-go{background:var(--gr);color:#042F22;box-shadow:0 4px 12px var(--grg)}
.btn-stop{background:var(--am);color:#451A03}
.btn-demo{background:#1B2234;color:#E2E8F0;border:1px solid #2D3A54}
.btn-demo:hover{background:#26324A}
.btn-x{background:var(--rdb);color:var(--rd);border:1px solid rgba(244,63,94,.3)}
.btn-x:hover{background:rgba(244,63,94,.2)}
.btn-g{background:transparent;color:var(--tx2);border:1px solid var(--bdr)}
.btn-g:hover{background:rgba(255,255,255,.05);color:var(--tx)}

/* Main Workspace Layout: Dual-Column */
main{padding:18px 24px;max-width:1680px;margin:0 auto;display:grid;grid-template-columns:1fr 340px;gap:20px;align-items:start}
@media(max-width:1280px){main{grid-template-columns:1fr}}

.left-col{display:flex;flex-direction:column;gap:18px;min-width:0}
.right-sidebar{display:flex;flex-direction:column;gap:18px;position:sticky;top:74px}

/* KPIs */
.krow{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:14px}
.kc{background:var(--card);border:1px solid var(--bdr);border-radius:12px;padding:16px 18px;display:flex;flex-direction:column;gap:6px}
.kc.a{border-top:2px solid var(--ac)}.kc.p{border-top:2px solid var(--gr)}
.kl{font-size:10.5px;font-weight:600;color:var(--tx2);text-transform:uppercase;letter-spacing:.06em}
.kv{font-size:24px;font-weight:800;letter-spacing:-.02em;font-family:'JetBrains Mono',monospace}
.ks{font-size:11.5px;color:var(--tx2);display:flex;justify-content:space-between}
.g{color:var(--gr)}.r{color:var(--rd)}

/* Panels */
.pn{background:var(--card);border:1px solid var(--bdr);border-radius:12px;overflow:hidden}
.ph{padding:12px 18px;border-bottom:1px solid var(--bdr);display:flex;justify-content:space-between;align-items:center;background:rgba(255,255,255,.01)}
.pt{font-size:13px;font-weight:700;display:flex;align-items:center;gap:7px}

/* Tables */
.tw{overflow-x:auto}
table{width:100%;border-collapse:collapse;text-align:left}
th{background:#090D15;padding:10px 14px;color:var(--tx2);font-weight:600;font-size:10.5px;text-transform:uppercase;letter-spacing:.05em;border-bottom:1px solid var(--bdr)}
td{padding:11px 14px;border-bottom:1px solid var(--bdr);font-family:'JetBrains Mono',monospace;font-size:11.5px}
tr:last-child td{border-bottom:none}
tr:hover td{background:rgba(255,255,255,.015)}

/* Badges */
.b{display:inline-flex;align-items:center;padding:2px 7px;border-radius:5px;font-size:10px;font-weight:600}
.b-l{background:var(--grb);color:var(--gr);border:1px solid rgba(16,185,129,.3)}
.b-s{background:var(--rdb);color:var(--rd);border:1px solid rgba(244,63,94,.3)}
.b-w{background:var(--grb);color:var(--gr);border:1px solid rgba(16,185,129,.3)}
.b-x{background:var(--rdb);color:var(--rd);border:1px solid rgba(244,63,94,.3)}
.b-d{background:var(--amb);color:var(--am);border:1px solid rgba(245,158,11,.3)}
.b-p{background:rgba(99,102,241,.15);color:#818CF8;border:1px solid rgba(99,102,241,.3)}

/* Market Cards Grid */
.mg{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px;padding:14px}
.mc{background:#090D15;border:1px solid var(--bdr);border-radius:10px;padding:12px;display:flex;flex-direction:column;gap:4px}
.mc.ip{border-color:var(--ac);background:rgba(99,102,241,.04)}
.mh{display:flex;justify-content:space-between;align-items:center}
.mn{font-weight:700;font-size:12px}
.ms{color:var(--tx2);font-size:10px;font-family:'JetBrains Mono',monospace}
.mp{font-size:17px;font-weight:800;font-family:'JetBrains Mono',monospace;color:#F1F5F9}

/* Equity Chart */
.cc{padding:14px 18px 18px;height:160px;width:100%}
svg.es{width:100%;height:100%;overflow:visible}
.cl{fill:none;stroke:var(--gr);stroke-width:2.5;stroke-linecap:round;stroke-linejoin:round;filter:drop-shadow(0 0 5px var(--grg))}
.ca{fill:url(#eg)}
.cd{fill:var(--gr);stroke:#0C101A;stroke-width:2}

/* Progress bar */
.pbb{background:#1B2234;height:5px;border-radius:3px;overflow:hidden;width:80px;display:inline-block;vertical-align:middle;margin-right:6px}
.pbf{height:100%;background:var(--gr);border-radius:3px}

/* Diagnostic Radar Cards */
.diag-card{background:#090D15;border:1px solid var(--bdr);border-radius:10px;padding:14px;display:flex;flex-direction:column;gap:10px}
.diag-top{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px}
.diag-asset{font-size:14px;font-weight:800;letter-spacing:.02em;margin-right:8px}
.diag-px{font-size:13px;font-family:'JetBrains Mono',monospace;color:var(--tx2);margin-right:8px}
.diag-score-wrap{display:flex;align-items:center;font-size:11px}
.diag-score-lbl{color:var(--tx3);margin-right:4px}
.diag-levels{display:flex;flex-wrap:wrap;gap:12px;font-size:11px;font-family:'JetBrains Mono',monospace;color:#CBD5E1;background:#0D1322;padding:6px 10px;border-radius:6px;border:1px solid #1A2438}
.diag-checklist{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:6px;font-size:10.5px;font-family:'JetBrains Mono',monospace}
.chk-item{background:rgba(255,255,255,.02);border:1px solid var(--bdr);border-radius:4px;padding:4px 8px;display:flex;justify-content:space-between;gap:6px}
.chk-k{color:var(--tx3)}
.chk-v.g{color:var(--gr);font-weight:600}
.chk-v.y{color:var(--am);font-weight:600}
.chk-v.r{color:var(--rd);font-weight:600}
.diag-decision-box{background:#0D1424;border-left:3px solid var(--ac);padding:8px 12px;border-radius:0 6px 6px 0;display:flex;flex-direction:column;gap:4px}
.diag-dec-title{font-size:11px;color:var(--ac);font-family:'JetBrains Mono',monospace}
.diag-thesis{font-size:11.5px;color:#CBD5E1;line-height:1.4}

/* ── Live Activity Radar (Sidebar) ── */
.radar-card{background:var(--card);border:1px solid var(--bdr);border-radius:12px;overflow:hidden}
.radar-header{padding:14px 16px;border-bottom:1px solid var(--bdr);display:flex;justify-content:space-between;align-items:center;background:rgba(99,102,241,.03)}
.radar-title{font-size:12.5px;font-weight:700;display:flex;align-items:center;gap:6px}

/* Micro-state Pulse Box */
.micro-box{padding:12px 14px;background:#090D15;border-bottom:1px solid var(--bdr);display:flex;flex-direction:column;gap:6px}
.micro-lbl{font-size:10px;font-weight:600;color:var(--tx3);text-transform:uppercase;letter-spacing:.05em}
.micro-text{font-size:11.5px;color:#CBD5E1;font-weight:500;line-height:1.4;display:flex;align-items:flex-start;gap:7px}

/* Activity Stream List */
.activity-stream{max-height:380px;overflow-y:auto;display:flex;flex-direction:column;padding:8px}
.act-item{padding:9px 11px;border-radius:8px;background:transparent;border-left:2px solid transparent;display:flex;flex-direction:column;gap:2px;transition:background .15s}
.act-item:hover{background:rgba(255,255,255,.02)}
.act-item.ready{border-left-color:var(--tx3)}
.act-item.info{border-left-color:#38BDF8}
.act-item.accent{border-left-color:var(--ac)}
.act-item.success{border-left-color:var(--gr);background:rgba(16,185,129,.03)}
.act-item.warning{border-left-color:var(--am);background:rgba(245,158,11,.03)}
.act-item.danger{border-left-color:var(--rd);background:rgba(244,63,94,.03)}
.act-top{display:flex;justify-content:space-between;align-items:center}
.act-tag{font-size:9.5px;font-weight:700;text-transform:uppercase;font-family:'JetBrains Mono',monospace;padding:1px 5px;border-radius:4px}
.act-time{font-size:9.5px;color:var(--tx3);font-family:'JetBrains Mono',monospace}
.act-title{font-size:11.5px;font-weight:600;color:#E2E8F0;margin-top:2px}
.act-desc{font-size:10.5px;color:var(--tx2);font-family:'JetBrains Mono',monospace;line-height:1.35;word-break:break-word}

/* Risk Gauges Box */
.risk-box{padding:14px 16px;background:#090D15;border-top:1px solid var(--bdr);display:flex;flex-direction:column;gap:12px}
.gauge-item{display:flex;flex-direction:column;gap:4px}
.gauge-header{display:flex;justify-content:space-between;font-size:10.5px}
.gauge-lbl{color:var(--tx2);font-weight:500}
.gauge-val{font-weight:700;font-family:'JetBrains Mono',monospace}
.gauge-bar{height:5px;border-radius:3px;background:#1A2234;overflow:hidden}
.gauge-fill{height:100%;border-radius:3px;background:var(--gr)}

.empty{padding:28px 14px;text-align:center;color:var(--tx3);font-size:11.5px}
.si{background:#151C2C;border:1px solid var(--bdr);color:#fff;padding:4px 10px;border-radius:6px;font-size:11px;font-family:'JetBrains Mono',monospace;outline:none}
.si:focus{border-color:var(--ac)}

/* Main Dual-App Navigation Tabs */
.top-nav{background:#090D15;border-bottom:1px solid var(--bdr);padding:0 24px;display:flex;gap:4px;position:sticky;top:63px;z-index:90;backdrop-filter:blur(12px)}
.nav-tab{background:transparent;border:none;border-bottom:2px solid transparent;color:var(--tx2);padding:12px 20px;font-size:12.5px;font-weight:700;font-family:'Plus Jakarta Sans',sans-serif;cursor:pointer;display:inline-flex;align-items:center;gap:8px;transition:all .15s}
.nav-tab:hover{color:var(--tx);background:rgba(255,255,255,.02)}
.nav-tab.active{color:#fff;border-bottom-color:var(--ac);background:rgba(99,102,241,.06)}
.tab-badge{font-size:9.5px;padding:2px 7px;border-radius:10px;font-family:'JetBrains Mono',monospace;font-weight:700}

/* Polymarket Design System Components */
.poly-gig-banner{background:linear-gradient(90deg,rgba(99,102,241,.12),rgba(16,185,129,.06));border:1px solid rgba(99,102,241,.3);border-radius:12px;padding:14px 18px;display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}
.poly-gig-left{display:flex;align-items:center;gap:12px}
.poly-pulse-dot{width:10px;height:10px;border-radius:50%;background:#10B981;box-shadow:0 0 12px #10B981;animation:p 1.5s infinite}
.poly-chips-row{display:flex;gap:8px;overflow-x:auto;padding:2px 0;align-items:center}
.poly-chip{background:#0E1424;border:1px solid var(--bdr);color:var(--tx2);padding:6px 14px;border-radius:20px;font-size:11px;font-weight:600;cursor:pointer;transition:all .15s;white-space:nowrap;user-select:none}
.poly-chip:hover{color:#fff;border-color:var(--ac)}
.poly-chip.active{background:rgba(99,102,241,.2);border-color:var(--ac);color:#fff}

/* Polymarket Cards Grid */
.pm-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:14px}
.pm-card{background:#0C101A;border:1px solid var(--bdr);border-radius:14px;padding:16px;display:flex;flex-direction:column;gap:12px;transition:all .2s ease;position:relative}
.pm-card:hover{border-color:var(--bdr-hover);transform:translateY(-2px);box-shadow:0 12px 28px rgba(0,0,0,.5)}
.pm-card-top{display:flex;justify-content:space-between;align-items:flex-start;gap:10px}
.pm-card-title{font-size:14px;font-weight:700;line-height:1.35;color:#F8FAFC}
.pm-outcomes-wrap{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.pm-btn{background:#111726;border:1px solid var(--bdr);border-radius:8px;padding:8px 12px;display:flex;justify-content:space-between;align-items:center;cursor:pointer;transition:all .15s}
.pm-btn:hover{background:#182034}
.pm-btn.yes{border-left:3px solid #38BDF8}
.pm-btn.no{border-left:3px solid #94A3B8}
.pm-prob-bar{height:6px;border-radius:3px;background:#1E293B;overflow:hidden;display:flex}
.pm-bar-yes{height:100%;background:#38BDF8;transition:width .3s}
.pm-bar-no{height:100%;background:#64748B;transition:width .3s}

/* Polymarket Fast-Expiry Timeline Ribbon Styles */
.poly-tf-btn{background:#0E1424;border:1px solid rgba(255,255,255,.1);color:var(--tx2);padding:5px 12px;border-radius:6px;font-size:11px;font-weight:700;cursor:pointer;transition:all .15s}
.poly-tf-btn:hover{color:#fff;border-color:#38BDF8}
.poly-tf-btn.active{background:rgba(56,189,248,.18);border-color:#38BDF8;color:#38BDF8;box-shadow:0 0 10px rgba(56,189,248,.2)}

.poly-coin-tab-btn{background:#0E1424;border:1px solid rgba(255,255,255,.1);color:var(--tx2);padding:5px 12px;border-radius:6px;font-size:11.5px;font-weight:700;cursor:pointer;transition:all .15s;display:inline-flex;align-items:center;gap:5px}
.poly-coin-tab-btn:hover{color:#fff;border-color:var(--ac)}
.poly-coin-tab-btn.active{background:rgba(99,102,241,.2);border-color:var(--ac);color:#fff}

.poly-ribbon-bar{display:flex;align-items:center;gap:8px;overflow-x:auto;padding:8px 4px;scrollbar-width:thin}
.poly-pill-past-btn{background:#111726;border:1px solid rgba(255,255,255,.12);color:var(--tx2);padding:5px 10px;border-radius:20px;font-size:11px;font-weight:700;cursor:pointer;display:inline-flex;align-items:center;gap:4px;white-space:nowrap}
.poly-pill-past-btn:hover{background:#182034;color:#fff}
.poly-pill-outcome{min-width:24px;height:24px;padding:0 6px;border-radius:12px;display:inline-flex;align-items:center;justify-content:center;font-size:10px;font-weight:900;text-decoration:none;cursor:pointer;transition:transform .15s}
.poly-pill-outcome:hover{transform:scale(1.08)}
.poly-pill-outcome.up{background:rgba(16,185,129,.18);border:1.5px solid #10B981;color:#10B981}
.poly-pill-outcome.down{background:rgba(239,68,68,.18);border:1.5px solid #EF4444;color:#EF4444}
.poly-pill-active{background:linear-gradient(135deg,rgba(56,189,248,.25),rgba(15,23,42,.9));border:1.5px solid #38BDF8;color:#fff;padding:6px 14px;border-radius:20px;font-size:11.5px;font-weight:800;display:inline-flex;align-items:center;gap:6px;box-shadow:0 0 14px rgba(56,189,248,.3);white-space:nowrap;cursor:pointer}
.poly-pill-upcoming{background:#0F172A;border:1px solid rgba(255,255,255,.1);color:var(--tx2);padding:5px 12px;border-radius:20px;font-size:11px;font-weight:600;display:inline-flex;align-items:center;gap:4px;white-space:nowrap;cursor:pointer;transition:all .15s}
.poly-pill-upcoming:hover{background:#1E293B;color:#fff;border-color:rgba(255,255,255,.25)}

.pm-ai-box{background:#080C14;border:1px solid rgba(99,102,241,.25);border-radius:8px;padding:10px;display:flex;flex-direction:column;gap:6px}
.pm-thesis{font-size:11px;color:#CBD5E1;line-height:1.4;background:rgba(255,255,255,.015);padding:6px 8px;border-radius:6px;border-left:2px solid var(--ac)}

/* News & Verified Evidence Feed Grid */
.news-feed-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:12px}
.news-item-card{background:#090D15;border:1px solid var(--bdr);border-radius:10px;padding:12px 14px;display:flex;flex-direction:column;gap:6px;transition:border .15s}
.news-item-card:hover{border-color:var(--ac)}
.news-top{display:flex;justify-content:space-between;align-items:center;gap:6px}
.news-headline{font-size:12px;font-weight:700;color:#F1F5F9;line-height:1.35}
.news-summary{font-size:11px;color:var(--tx2);line-height:1.4}
.sentiment-pill{display:inline-flex;align-items:center;gap:4px;padding:2px 7px;border-radius:5px;font-size:9.5px;font-weight:700;font-family:'JetBrains Mono',monospace}
.sentiment-pill.bullish{background:rgba(16,185,129,.12);color:var(--gr);border:1px solid rgba(16,185,129,.3)}
.sentiment-pill.bearish{background:rgba(244,63,94,.12);color:var(--rd);border:1px solid rgba(244,63,94,.3)}
.sentiment-pill.neutral{background:rgba(148,163,184,.12);color:#94A3B8;border:1px solid rgba(148,163,184,.3)}
</style>
</head>
<body>

<header>
  <div class="hl">
    <div class="icon">⚡</div>
    <div>
      <div class="brand">SENTINEL AI PLATFORM</div>
      <div class="sub">Institutional Command Center · ICT Forex &amp; Polymarket Prediction Intelligence</div>
    </div>
  </div>
  <div class="hr">
    <div id="streamPill" class="stream-pill">● LIVE STREAM (ACTIVE)</div>
    <div class="session-badge-wrap">
      <div class="pill"><div id="dot" class="dot"></div><span id="sess">CONNECTING...</span></div>
      <div id="sessionTimerBadge" class="timer-pill off" title="Running Session Countdown">
        <span class="t-icon">⏱</span>
        <span id="timerLabel" class="t-lbl">Next:</span>
        <span id="timerCountdown" class="t-val">--:--:--</span>
      </div>
    </div>
    <button id="engBtn" class="btn btn-go" onclick="toggle()">▶ Start Engine</button>
    <button id="demBtn" class="btn btn-demo" onclick="demo()">⚡ Run Simulation</button>
    <button class="btn btn-x" onclick="flatten()">⚠ Flatten All</button>
    <button class="btn btn-g" onclick="reset()">🔄 Reset</button>
  </div>
</header>

<!-- Main Top Navigation Tabs -->
<nav class="top-nav">
  <button id="tabBtnIct" class="nav-tab active" onclick="switchMainTab('ict')">
    <span style="font-size:14px">⚡</span> ICT Forex Sentinel
    <span class="tab-badge" style="background:rgba(16,185,129,.15);color:var(--gr)">CME &amp; FX LIVE</span>
  </button>
  <button id="tabBtnPoly" class="nav-tab" onclick="switchMainTab('poly')">
    <span style="font-size:14px">🔮</span> Polymarket Sentinel
    <span class="tab-badge" style="background:rgba(99,102,241,.2);color:#A5B4FC">PREDICTION INTELLIGENCE</span>
  </button>
  <button id="tabBtnCrypto" class="nav-tab" onclick="switchMainTab('crypto')">
    <span style="font-size:14px">🪙</span> Crypto Sentinel AI
    <span class="tab-badge" style="background:rgba(245,158,11,.2);color:#FBBF24">BINANCE &amp; 3-ENGINE</span>
  </button>
</nav>

<div id="view-ict">

<main>
  <!-- LEFT COLUMN (Core Charts, Positions, Feeds, Trades) -->
  <div class="left-col">
    <!-- KPIs -->
    <div class="krow">
      <div class="kc a">
        <div class="kl">Account Balance</div>
        <div class="kv" id="kBal">$500.00</div>
        <div class="ks"><span>Start: $500.00</span><span>Peak: <b id="kPk" class="g">$500.00</b></span></div>
      </div>
      <div class="kc p">
        <div class="kl">Realized Net PnL</div>
        <div class="kv g" id="kPnl">+$0.00</div>
        <div class="ks"><span>Win Rate: <b id="kWr" class="g">0%</b></span><span>PF: <b id="kPf">0</b></span><span>Sharpe: <b id="kSharpe" style="color:var(--cy)">0.00</b></span></div>
      </div>
      <div class="kc">
        <div class="kl">Trade Ledger</div>
        <div class="kv" id="kTt">0</div>
        <div class="ks"><span>Wins: <b id="kW" class="g">0</b></span><span>Losses: <b id="kL" class="r">0</b></span></div>
      </div>
      <div class="kc">
        <div class="kl">Risk & Institutional Goals</div>
        <div class="kv" id="kDD">$0.00</div>
        <div class="ks"><span>Max DD: <b id="kDDp">0%</b></span><span>Goal Sharpe: <b class="g">1.50</b></span></div>
      </div>
    </div>

    <!-- Real-Time Equity Curve -->
    <div class="pn">
      <div class="ph"><div class="pt">📈 Real-Time Account Equity Progression</div><span class="b b-p">Live SSE</span></div>
      <div class="cc" id="chC">
        <svg class="es" id="svg">
          <defs><linearGradient id="eg" x1="0%" y1="0%" x2="0%" y2="100%"><stop offset="0%" stop-color="var(--gr)" stop-opacity=".35"/><stop offset="100%" stop-color="var(--gr)" stop-opacity="0"/></linearGradient></defs>
          <path id="cA" class="ca" d=""/><path id="cL" class="cl" d=""/><g id="cD"></g>
        </svg>
      </div>
    </div>

    <!-- Active Positions -->
    <div class="pn">
      <div class="ph"><div class="pt">🎯 Active Open Positions (Double Tap Architecture)</div><span class="b b-p" id="pCt">0</span></div>
      <div class="tw">
        <table><thead><tr>
          <th>ID</th><th>Asset</th><th>Dir</th><th>Entry</th><th>Stop</th><th>50% CE Defense</th><th>CM 1.5R</th><th>HS 3.0R</th><th>Unreal PnL</th><th>Status</th><th>Action</th>
        </tr></thead><tbody id="pTb">
          <tr><td colspan="11" class="empty">No open positions. Real-time tape monitoring active...</td></tr>
        </tbody></table>
      </div>
    </div>

    <!-- Market Feeds -->
    <div class="pn">
      <div class="ph"><div class="pt">📡 Institutional Market Feeds</div><span class="sub" id="cyc">Streaming live...</span></div>
      <div class="mg" id="mG"></div>
    </div>

    <!-- AI Market Diagnostics & Decision Radar -->
    <div class="pn">
      <div class="ph">
        <div class="pt">🧭 AI Market Diagnostics & Decision Radar</div>
        <span class="b b-p">Continuous Live Surveillance</span>
      </div>
      <div id="diagList" style="display:flex;flex-direction:column;gap:12px;padding:14px">
        <div class="empty">Evaluating market structure across CME & Forex feeds...</div>
      </div>
    </div>

    <!-- Self-Learning Bayesian Intelligence -->
    <div class="pn">
      <div class="ph"><div class="pt">🧠 Self-Learning Bayesian Intelligence</div><span class="b b-p">Active</span></div>
      <div class="tw">
        <table><thead><tr><th>Regime</th><th>Record</th><th>BQS</th><th>Status</th></tr></thead>
        <tbody id="mTb"><tr><td colspan="4" class="empty">Accumulating episodes...</td></tr></tbody></table>
      </div>
      <div style="padding:12px 16px;border-top:1px solid var(--bdr);background:#090D15">
        <div class="kl" style="margin-bottom:4px">Latest AI Post-Mortem Reflection</div>
        <div id="ref" style="color:#CBD5E1;font-size:11px;font-family:'JetBrains Mono',monospace">Awaiting first reflection...</div>
      </div>
    </div>

    <!-- Cross-Session Transition Debriefs -->
    <div class="pn">
      <div class="ph">
        <div class="pt">🔄 Cross-Session Transition Debriefs & Macro Synthesis</div>
        <span class="b b-p">Inter-Session Order Flow</span>
      </div>
      <div id="debriefList" style="display:flex;flex-direction:column;gap:10px;padding:14px">
        <div class="empty">Awaiting session close to compile cross-session debrief...</div>
      </div>
    </div>

    <!-- Scientific Method & Institutional Meta-Reflections -->
    <div class="pn">
      <div class="ph">
        <div class="pt">🔬 Institutional Meta-Reflections & Scientific Method Journal</div>
        <span class="b b-p">Single-Variable Optimization</span>
      </div>
      <div id="metaReflectionList" style="display:flex;flex-direction:column;gap:10px;padding:14px">
        <div class="empty">Synthesizing institutional multi-session batch metrics...</div>
      </div>
    </div>

    <!-- Full Trade Journal -->
    <div class="pn">
      <div class="ph">
        <div class="pt">📖 Historical Trade Journal</div>
        <input class="si" id="tSr" placeholder="Search asset..." oninput="filt()">
      </div>
      <div class="tw" style="max-height:360px;overflow-y:auto">
        <table><thead><tr>
          <th>Exit Time</th><th>Asset</th><th>Session</th><th>Dir</th><th>Entry ➔ Exit</th><th>Net PnL</th><th>Outcome</th><th>AI Thesis</th>
        </tr></thead><tbody id="tTb">
          <tr><td colspan="8" class="empty">No closed trades yet.</td></tr>
        </tbody></table>
      </div>
    </div>
  </div>

  <!-- RIGHT SIDEBAR (Live Bot Activity & System Radar) -->
  <div class="right-sidebar">
    <div class="radar-card">
      <div class="radar-header">
        <div class="radar-title"><span>📡</span> LIVE BOT ACTIVITY RADAR</div>
        <span class="stream-pill" style="padding:2px 7px;font-size:9.5px;">RUN TIME</span>
      </div>

      <!-- Algorithmic Clocks & Running Session Countdown -->
      <div class="clock-box">
        <div class="clock-grid">
          <div class="clock-item">
            <span class="clock-lbl">NY / EST (IPDA REF)</span>
            <span class="clock-val" id="clockEst">--:--:-- EST</span>
          </div>
          <div class="clock-item">
            <span class="clock-lbl">LOCAL SYSTEM TIME</span>
            <span class="clock-val" id="clockLocal">--:--:--</span>
          </div>
        </div>
        <div class="clock-status-bar" id="sessionTimeline">
          <span>⏳</span>
          <span id="sessionCountdownText" style="flex:1">Calculating next open...</span>
        </div>
      </div>

      <!-- Active Micro-State Pulse Box -->
      <div class="micro-box">
        <div class="micro-lbl">Current Pipeline State</div>
        <div class="micro-text">
          <span style="color:var(--gr)">●</span>
          <span id="microState">Engine Idle</span>
        </div>
      </div>

      <!-- Live Activity Stream List -->
      <div class="activity-stream" id="activityList">
        <div class="empty">Listening for bot actions...</div>
      </div>

      <!-- Risk & Circuit Breaker Health Gauges -->
      <div class="risk-box">
        <div class="micro-lbl" style="margin-bottom:2px">Risk & Safety Safeguards</div>
        
        <!-- Gauge 1: Consecutive Loss Shield -->
        <div class="gauge-item">
          <div class="gauge-header">
            <span class="gauge-lbl">Consecutive Loss Shield</span>
            <span class="gauge-val" id="lossShieldVal">0 / 2 Losses</span>
          </div>
          <div class="gauge-bar"><div class="gauge-fill" id="lossShieldBar" style="width:0%;"></div></div>
        </div>

        <!-- Gauge 2: Drawdown Risk Budget -->
        <div class="gauge-item">
          <div class="gauge-header">
            <span class="gauge-lbl">Drawdown Budget</span>
            <span class="gauge-val" id="ddBudgetVal">$0.00 / $50.00</span>
          </div>
          <div class="gauge-bar"><div class="gauge-fill" id="ddBudgetBar" style="width:0%;"></div></div>
        </div>

        <!-- Gauge 3: Killzone Gate -->
        <div class="gauge-item" style="margin-top:2px;">
          <div class="gauge-header">
            <span class="gauge-lbl">10:00 AM NY Gate</span>
            <span class="gauge-val g" id="gateVal">CLEAR (UNRESTRICTED)</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</main>
</div>

<!-- ===================================================================== -->
<!-- POLYMARKET SENTINEL COMMAND CENTER WORKSPACE                         -->
<!-- ===================================================================== -->
<div id="view-poly" style="display:none">
<main style="max-width:1720px">
  <!-- LEFT COLUMN (BTC 5M Scalper Terminal) -->
  <div class="left-col">
    <!-- BTC 5-MINUTE QUANTITATIVE SCALPER TERMINAL -->
    <div class="pn" style="border:1px solid rgba(245,158,11,.3);background:linear-gradient(180deg,rgba(245,158,11,.04),rgba(15,23,42,.7))">
      <div class="ph" style="background:rgba(245,158,11,.08);display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px">
        <div style="display:flex;align-items:center;gap:10px">
          <div class="pt">
            <span style="font-size:16px">⚡</span> BTC 5-Minute Quantitative Scalper
            <span class="tab-badge" style="background:rgba(245,158,11,.15);color:#FBBF24;margin-left:6px" id="poly5mStatusBadge">BTC ONLY · 1¢-2¢ TIGHT CLOB SPREAD</span>
          </div>
          <button id="btn5mToggle" class="btn btn-demo" style="padding:4px 10px;font-size:10px" onclick="polyToggle5mScalper()">
            🟢 Scalper Active
          </button>
          <button class="btn btn-demo" style="padding:4px 9px;font-size:10px;background:rgba(255,255,255,.07);border:1px solid rgba(255,255,255,.15)" onclick="polyForceSettle()" title="Force-settle any expired rounds directly against Polymarket contracts">
            ⚡ Sync / Settle
          </button>
          </button>
          <!-- Mode Switcher Pill -->
          <div style="display:inline-flex;align-items:center;background:rgba(0,0,0,.6);border:1px solid rgba(255,255,255,.15);border-radius:6px;padding:2px;gap:2px">
            <button id="btnPolyModePaper" onclick="setPolyTradingMode(false)" style="padding:3px 9px;font-size:10px;font-weight:700;border-radius:4px;background:rgba(99,102,241,.3);color:#A5B4FC;border:none;cursor:pointer">
              📝 Paper ($50)
            </button>
            <button id="btnPolyModeLive" onclick="setPolyTradingMode(true)" style="padding:3px 9px;font-size:10px;font-weight:700;border-radius:4px;background:transparent;color:var(--tx3);border:none;cursor:pointer">
              🔴 Live Trading
            </button>
          </div>
          <!-- API Keys & Live Wallet Config Modal Button -->
          <button class="btn" style="padding:4px 10px;font-size:10px;font-weight:700;background:rgba(245,158,11,.15);border:1px solid rgba(245,158,11,.35);color:#FBBF24;cursor:pointer;display:inline-flex;align-items:center;gap:4px" onclick="openPolyKeyModal()" title="Configure Polymarket Private Key, Funder / Proxy Address & Test Live Connection">
            ⚙️ API Keys &amp; Wallet
          </button>
          <span id="polyLiveAccountBadge" class="tab-badge" style="background:rgba(255,255,255,.06);color:var(--tx3);font-size:10px">📝 Paper Simulation Mode</span>
        </div>
        <div style="display:flex;align-items:center;gap:12px;font-size:11px;font-family:'JetBrains Mono',monospace;flex-wrap:wrap">
          <span style="color:var(--tx2)">Scalper Bankroll: <b id="poly5mBal" style="color:var(--tx1)">$50.00</b></span>
          <span style="color:var(--tx2)">P&amp;L: <b id="poly5mPnl" style="color:var(--gr)">+$0.00</b></span>
          <span style="color:var(--tx2)">Win Rate: <b id="poly5mWinRate" style="color:#A5B4FC">0.0%</b></span>
          <span style="color:var(--tx2)">Fees Paid: <b id="poly5mFees" style="color:#FBBF24">$0.000</b></span>
          <span style="color:var(--tx2)">Record: <b id="poly5mRecord" style="color:#38BDF8">0W - 0L</b></span>
        </div>
      </div>
      <div style="padding:16px">
        <!-- Interactive Polymarket Timeframe & Coin Navigator Bar -->
        <div style="display:flex;justify-content:space-between;align-items:center;background:rgba(0,0,0,.45);border:1px solid rgba(255,255,255,.09);border-radius:10px;padding:8px 12px;margin-bottom:12px;flex-wrap:wrap;gap:10px">
          <!-- Asset Selector -->
          <div style="display:flex;align-items:center;gap:6px">
            <span style="font-size:10.5px;color:var(--tx3);font-weight:700;text-transform:uppercase;margin-right:2px">Asset:</span>
            <button class="poly-coin-tab-btn active" id="polyCoinTab_BTC" style="background:rgba(245,158,11,.2);border-color:#F59E0B;color:#FBBF24;font-weight:800;pointer-events:none">🟠 BTC Only (Deep CLOB Liquidity · 1¢-2¢ Spread)</button>
          </div>
          <!-- Timeframe Selector -->
          <div style="display:flex;align-items:center;gap:6px">
            <span style="font-size:10.5px;color:var(--tx3);font-weight:700;text-transform:uppercase;margin-right:2px">Timeframe:</span>
            <button class="poly-tf-btn active" id="polyTfBtn_5m" onclick="selectPolyTimelineTf('5m')">⚡ 5M (Scalp)</button>
            <button class="poly-tf-btn" id="polyTfBtn_15m" onclick="selectPolyTimelineTf('15m')">⏱️ 15M (Intra-Hour)</button>
            <button class="poly-tf-btn" id="polyTfBtn_1h" onclick="selectPolyTimelineTf('1h')">⏳ 1H (Session)</button>
          </div>
        </div>

        <!-- Live Round Header with Dual Countdowns (Exact Polymarket Design) -->
        <div style="display:flex;justify-content:space-between;align-items:center;background:linear-gradient(180deg,rgba(0,0,0,.4),rgba(15,23,42,.6));border:1px solid rgba(255,255,255,.08);border-radius:10px;padding:12px 16px;margin-bottom:12px;flex-wrap:wrap;gap:12px">
          <!-- Title & Time Window -->
          <div style="display:flex;align-items:center;gap:12px">
            <span id="polyTimelineCoinIcon" style="font-size:26px">🟠</span>
            <div>
              <div style="font-size:14px;font-weight:800;color:#fff;display:flex;align-items:center;gap:6px">
                <span id="polyTimelineTitle">BTC Up or Down 5m</span>
                <span id="polyTimelineActiveBadge" class="tab-badge" style="background:rgba(56,189,248,.15);color:#38BDF8;font-size:9px">LIVE CONTRACT</span>
              </div>
              <div style="font-size:11px;color:var(--tx2);margin-top:2px" id="polyTimelineWindow">Loading Polymarket schedule...</div>
            </div>
          </div>

          <!-- Price to Beat & Spot -->
          <div style="display:flex;align-items:center;gap:16px;background:rgba(0,0,0,.3);border:1px solid rgba(255,255,255,.06);border-radius:8px;padding:6px 14px">
            <div>
              <div style="font-size:9.5px;color:var(--tx3);text-transform:uppercase;font-weight:700">Price To Beat (Strike)</div>
              <div style="font-size:13.5px;font-weight:800;color:var(--tx1);font-family:'JetBrains Mono',monospace" id="polyTimelinePtb">--</div>
            </div>
            <div style="border-left:1px solid rgba(255,255,255,.1);padding-left:12px">
              <div style="font-size:9.5px;color:var(--tx3);text-transform:uppercase;font-weight:700">Current Spot</div>
              <div style="font-size:13.5px;font-weight:800;color:#FBBF24;font-family:'JetBrains Mono',monospace" id="polyTimelineSpot">--</div>
            </div>
          </div>

          <!-- Dual Timers: Candle Closes In + Polymarket Series Expiry -->
          <div style="display:flex;align-items:center;gap:16px">
            <div style="text-align:right">
              <div style="font-size:9.5px;color:var(--tx3);text-transform:uppercase;font-weight:700">Candle Closes In</div>
              <div style="font-size:20px;font-weight:900;color:#38BDF8;font-family:'JetBrains Mono',monospace" id="poly5mTimer">00:00</div>
            </div>
            <div style="border-left:1px solid rgba(255,255,255,.1);padding-left:12px;text-align:right">
              <div style="font-size:9.5px;color:#F87171;text-transform:uppercase;font-weight:700;display:flex;align-items:center;gap:4px;justify-content:flex-end">
                <span>⚡ Series Expiry</span>
              </div>
              <div style="font-size:18px;font-weight:900;color:#F43F5E;font-family:'JetBrains Mono',monospace" id="polySessionTimer">00:00:00</div>
            </div>
          </div>
        </div>

        <!-- Polymarket Horizon Pill Ribbon (Past Pills | Active Round | Upcoming Pills) -->
        <div style="background:rgba(0,0,0,.35);border:1px solid rgba(255,255,255,.07);border-radius:10px;padding:8px 12px;margin-bottom:12px">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
            <span style="font-size:10.5px;font-weight:800;color:var(--tx3);text-transform:uppercase;letter-spacing:.05em">
              🌐 Polymarket Live Exchange Horizon Ribbon:
            </span>
            <span style="font-size:10px;color:var(--tx3);font-family:'JetBrains Mono',monospace">Direct contract integration</span>
          </div>
          <div class="poly-ribbon-bar" id="polyTimelineRibbon">
            <!-- Dynamically populated past, active, and upcoming pills -->
            <span style="font-size:11px;color:var(--tx3)">Connecting to Polymarket Gamma API...</span>
          </div>
        </div>

        <!-- Active Round Contract Action & Multi-Coin Surveillance Bar -->
        <div style="background:rgba(255,255,255,.02);border:1px solid rgba(255,255,255,.06);border-radius:8px;padding:10px 12px;margin-bottom:12px;display:flex;flex-direction:column;gap:8px">
          <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px">
            <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
              <span style="font-size:10px;color:var(--tx3);text-transform:uppercase;font-weight:700">Focused Contract:</span>
              <span style="font-size:11px;font-weight:700;color:#A5B4FC;font-family:'JetBrains Mono',monospace" id="poly5mRoundId">Loading round...</span>
              <span id="poly5mOrderbookBadge" class="tab-badge" style="background:rgba(16,185,129,.15);color:var(--gr);font-size:9.5px">🟢 Accepting Orders</span>
            </div>
            <div style="display:flex;align-items:center;gap:12px">
              <div style="font-size:11px;font-weight:700;color:#FBBF24" id="poly5mWindowDesc">Maturity Window (3:30 - 0:45 left) · Auto TP @ 92¢ · Auto SL Bailout @ 28¢</div>
              <a id="polyTimelineDirectLink" href="https://polymarket.com" target="_blank" rel="noopener noreferrer" style="font-size:10.5px;color:#38BDF8;text-decoration:none;font-weight:700;background:rgba(56,189,248,.12);border:1px solid rgba(56,189,248,.3);padding:3px 10px;border-radius:6px;display:inline-flex;align-items:center;gap:4px;transition:all .15s">
                <span>🔗 Verify on Polymarket.com</span> <span>↗</span>
              </a>
            </div>
          </div>

        </div>

        <!-- Polymarket Upcoming Rounds Timeline Cards -->
        <div style="background:rgba(255,255,255,.02);border:1px solid rgba(255,255,255,.07);border-radius:8px;padding:10px 12px;margin-bottom:14px">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
            <span style="font-size:11px;font-weight:800;color:var(--tx2);text-transform:uppercase;letter-spacing:.05em" id="polyUpcomingHeaderLabel">
              🗓️ Polymarket API Schedule · Next Upcoming Rounds (24/7 Aligned):
            </span>
            <span style="font-size:10px;color:var(--tx3);font-family:'JetBrains Mono',monospace">Real-time Polymarket UTC epochs</span>
          </div>
          <div id="poly5mUpcomingGrid" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px">
            <!-- Dynamically populated upcoming rounds -->
          </div>
        </div>

        <!-- BTC Live Microstructure Surveillance & Orderbook Matrix -->
        <div style="font-size:11px;font-weight:800;color:var(--tx3);text-transform:uppercase;letter-spacing:.05em;margin-bottom:8px">
          📊 BTC Microstructure Surveillance &amp; Orderbook Terminal:
        </div>
        <div id="poly5mCoinsGrid" style="display:grid;grid-template-columns:1fr;gap:12px;margin-bottom:14px">
          <!-- Dynamically populated BTC card -->
        </div>

        <!-- Best Selected Setup Callout Banner -->
        <div id="poly5mBestBanner" style="background:rgba(99,102,241,.07);border:1px solid rgba(99,102,241,.2);border-radius:8px;padding:10px 14px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;margin-bottom:14px">
          <div style="display:flex;align-items:center;gap:8px">
            <span style="font-size:11px;font-weight:800;color:#A5B4FC">🎯 BTC TARGET SETUP:</span>
            <span id="poly5mSignalBadge" class="b b-p">ABSTAIN</span>
            <span id="poly5mPatternBadge" style="font-size:10.5px;color:#A5B4FC;background:rgba(255,255,255,.05);padding:3px 7px;border-radius:4px">NEUTRAL SWEEP</span>
          </div>
          <div style="font-size:11.5px;color:var(--tx1);flex:1;text-align:right" id="poly5mReason">Scanning BTC 1m/2m order flow for clean displacement...</div>
        </div>

        <!-- Next 5M Session Predictive Radar Widget -->
        <div style="background:var(--bg2);border:1px solid rgba(99,102,241,.25);border-radius:8px;padding:12px;margin-bottom:12px">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;flex-wrap:wrap;gap:8px">
            <div style="display:flex;align-items:center;gap:8px">
              <span style="font-size:14px">🔮</span>
              <span style="font-size:12px;font-weight:800;letter-spacing:0.04em;color:#A5B4FC;text-transform:uppercase">Next 5M Session Predictive Radar (BTC)</span>
              <span class="tab-badge" style="background:rgba(99,102,241,.2);color:#C4B5FD;font-size:9.5px">AI Chart &amp; Momentum Forecast</span>
            </div>
            <div style="font-size:10.5px;color:var(--tx3);font-family:'JetBrains Mono',monospace" id="polyPredCountdown">Next Round Starting in --:--</div>
          </div>
          <div id="poly5mPredictionsGrid" style="display:grid;grid-template-columns:1fr;gap:10px">
            <div style="font-size:11.5px;color:var(--tx3);padding:8px">Evaluating candlestick anatomy &amp; momentum...</div>
          </div>
        </div>

        <!-- 5M Scalper Active Trade & Recent Settlements -->
        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:12px">
          <!-- Active 5M Bet Slip -->
          <div style="background:var(--bg2);border:1px solid var(--bdr);border-radius:8px;padding:12px">
            <div style="font-size:11px;font-weight:700;color:var(--tx3);margin-bottom:8px;text-transform:uppercase">Active 5M Bet Slip ($5 Max Risk · BTC Focus)</div>
            <div id="poly5mActiveSlip" style="font-size:12px;color:var(--tx2)">No active position for this 5-minute round.</div>
          </div>

          <!-- Recent 5M Round Settlements -->
          <div style="background:var(--bg2);border:1px solid var(--bdr);border-radius:8px;padding:12px">
            <div style="font-size:11px;font-weight:700;color:var(--tx3);margin-bottom:8px;text-transform:uppercase">Recent 5M Scalp History (BTC Only)</div>
            <div id="poly5mHistoryList" style="max-height:120px;overflow-y:auto;display:flex;flex-direction:column;gap:6px">
              <div style="font-size:11.5px;color:var(--tx3)">No completed 5M scalps yet.</div>
            </div>
          </div>
        </div>
      </div>
    </div>

  </div>

  <!-- RIGHT SIDEBAR (Live Scalper Order & Settlement Stream) -->
  <div class="right-sidebar">
    <div class="radar-card">
      <div class="radar-header" style="background:transparent">
        <div class="radar-title"><span>📡</span> LIVE SCALPER ORDER &amp; EVENT STREAM</div>
        <span class="stream-pill" style="padding:2px 7px;font-size:9.5px;" id="polyGatewayPill">ACTIVE</span>
      </div>
      <div class="activity-stream" id="polyActivityList" style="max-height:680px">
        <div class="empty">Listening for BTC 5M live scalper orders and settlements...</div>
      </div>
    </div>
  </div>
</main>

<!-- Deep Dive Dossier Modal -->
<div id="polyModal" style="display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(4,6,12,.85);backdrop-filter:blur(8px);z-index:999;align-items:center;justify-content:center;">
  <div style="background:#0C101A;border:1px solid var(--bdr);border-radius:14px;width:90%;max-width:880px;max-height:85vh;overflow-y:auto;padding:24px;display:flex;flex-direction:column;gap:18px;box-shadow:0 20px 40px rgba(0,0,0,.6)">
    <div style="display:flex;justify-content:space-between;align-items:flex-start;border-bottom:1px solid var(--bdr);padding-bottom:14px">
      <div>
        <div class="kl" id="modalCategory" style="margin-bottom:4px">CATEGORY</div>
        <div style="font-size:16px;font-weight:700;color:#F8FAFC" id="modalQuestion">Question</div>
        <div style="font-size:11px;color:var(--tx2);margin-top:4px" id="modalResolution">Resolution Source: Polymarket Oracle</div>
      </div>
      <button class="btn btn-x" onclick="closeDeepDive()">✕ Close</button>
    </div>

    <!-- Probability Evolution Timeline -->
    <div class="pn">
      <div class="ph"><div class="pt">📈 Probability Revision History (Event Memory)</div></div>
      <div id="modalTimelineList" style="display:flex;flex-direction:column;gap:8px;padding:14px;max-height:240px;overflow-y:auto">
        <div class="empty">No prior forecast revisions recorded.</div>
      </div>
    </div>

    <!-- Verified Evidence Dossier -->
    <div class="pn">
      <div class="ph"><div class="pt">📑 Verified Evidence &amp; Intelligence Citations</div></div>
      <div id="modalEvidenceList" style="display:flex;flex-direction:column;gap:8px;padding:14px;max-height:240px;overflow-y:auto">
        <div class="empty">No external evidence linked yet.</div>
      </div>
    </div>
  </div>
</div>
</div>

<!-- ===================================================================== -->
<!-- POLYMARKET LIVE API KEYS & WALLET CREDENTIALS MODAL                   -->
<!-- ===================================================================== -->
<div id="polyKeyModal" style="display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(4,6,12,.88);backdrop-filter:blur(8px);z-index:1000;align-items:center;justify-content:center;">
  <div style="background:#0C101A;border:1px solid rgba(245,158,11,.4);border-radius:14px;width:90%;max-width:680px;max-height:88vh;overflow-y:auto;padding:24px;display:flex;flex-direction:column;gap:18px;box-shadow:0 24px 50px rgba(0,0,0,.75)">
    <!-- Header -->
    <div style="display:flex;justify-content:space-between;align-items:flex-start;border-bottom:1px solid var(--bdr);padding-bottom:14px">
      <div>
        <div style="font-size:11px;font-weight:700;color:#FBBF24;text-transform:uppercase;letter-spacing:.5px;margin-bottom:3px">POLYMARKET CLOB PROTOCOL</div>
        <div style="font-size:17px;font-weight:800;color:#F8FAFC">⚙️ Live API Keys &amp; Trading Wallet Setup</div>
        <div style="font-size:12px;color:var(--tx2);margin-top:4px">Connect your Polygon wallet to enable real on-chain orders via gasless CLOB.</div>
      </div>
      <button class="btn btn-x" onclick="closePolyKeyModal()">✕ Close</button>
    </div>

    <!-- Instructions / Guide Box -->
    <div style="background:rgba(245,158,11,.06);border:1px solid rgba(245,158,11,.2);border-radius:8px;padding:12px 14px;font-size:11.5px;color:#E2E8F0;line-height:1.5">
      <div style="font-weight:700;color:#FBBF24;margin-bottom:4px">💡 Where to find your credentials:</div>
      <ul style="margin:0;padding-left:18px;display:flex;flex-direction:column;gap:4px">
        <li><b>MetaMask / Web3 Wallet:</b> Export private key from Account Details. Leave <i>Funder Address</i> blank and select <i>Signature Type 0 (EOA)</i>.</li>
        <li><b>Polymarket Email / Google Login:</b> Go to Polymarket.com &rarr; Settings &rarr; Export Private Key. Your USDC sits in a Gnosis Safe proxy, so copy your <b>Deposit Address</b> into <i>Funder Address</i> and select <i>Signature Type 2</i>.</li>
      </ul>
    </div>

    <!-- Credential Inputs Form -->
    <div style="display:flex;flex-direction:column;gap:14px">
      <!-- Private Key -->
      <div>
        <label style="display:block;font-size:11.5px;font-weight:700;color:var(--tx1);margin-bottom:5px">
          🔑 Polygon Private Key (0x...) <span style="color:#EF4444">*</span>
        </label>
        <div style="display:flex;gap:6px">
          <input type="password" id="polyModalPrivateKey" placeholder="0xabc123... (stored securely in local .env only)" style="flex:1;background:#060911;border:1px solid var(--bdr);border-radius:6px;padding:8px 12px;font-size:12px;font-family:'JetBrains Mono',monospace;color:#F8FAFC;outline:none" />
          <button type="button" class="btn btn-demo" style="padding:8px 12px;font-size:11px" onclick="togglePolyKeyVisibility()">👁️ Show/Hide</button>
        </div>
      </div>

      <!-- Funder / Proxy Address -->
      <div>
        <label style="display:block;font-size:11.5px;font-weight:700;color:var(--tx1);margin-bottom:5px">
          🏦 Funder / Proxy Address (Optional for Email/Magic Logins)
        </label>
        <input type="text" id="polyModalFunderAddress" placeholder="0x... (Polymarket Gnosis Safe address where your USDC.e resides)" style="width:100%;box-sizing:border-box;background:#060911;border:1px solid var(--bdr);border-radius:6px;padding:8px 12px;font-size:12px;font-family:'JetBrains Mono',monospace;color:#F8FAFC;outline:none" />
      </div>

      <!-- Signature Type -->
      <div>
        <label style="display:block;font-size:11.5px;font-weight:700;color:var(--tx1);margin-bottom:5px">
          ✍️ CLOB Signature Type
        </label>
        <select id="polyModalSigType" style="width:100%;box-sizing:border-box;background:#060911;border:1px solid var(--bdr);border-radius:6px;padding:8px 12px;font-size:12px;color:#F8FAFC;outline:none;cursor:pointer">
          <option value="0">0 — Standard EOA (MetaMask / Raw Private Key)</option>
          <option value="1">1 — Polymarket Proxy (Magic Link Email login without Safe)</option>
          <option value="2">2 — Gnosis Safe Proxy (Standard Polymarket Smart Contract Wallet)</option>
        </select>
      </div>

      <!-- Live Order Safety Cap Notice -->
      <div style="background:rgba(99,102,241,.08);border:1px solid rgba(99,102,241,.25);border-radius:8px;padding:10px 14px;font-size:11px;color:#C7D2FE">
        🛡️ <b>Built-in Capital Preservation:</b> Live orders are automatically restricted to <b>max $5.00 USDC.e</b> per contract round. Automatic Take-Profit at <b>92¢</b> and Stop-Loss bailout at <b>28¢</b> protect your collateral 24/7.
      </div>

      <!-- Status / Test Output Banner -->
      <div id="polyModalTestResult" style="display:none;padding:12px;border-radius:8px;font-size:12px;font-family:'JetBrains Mono',monospace"></div>
    </div>

    <!-- Action Buttons -->
    <div style="display:flex;justify-content:space-between;align-items:center;border-top:1px solid var(--bdr);padding-top:16px;flex-wrap:wrap;gap:10px">
      <button class="btn btn-demo" id="btnTestPolyCreds" onclick="testPolyCredentials()" style="padding:9px 16px;font-size:12px;font-weight:700;background:rgba(56,189,248,.15);border:1px solid #38BDF8;color:#38BDF8">
        🧪 Test Live Connection
      </button>
      <div style="display:flex;gap:10px">
        <button class="btn btn-x" onclick="closePolyKeyModal()" style="padding:9px 16px;font-size:12px">Cancel</button>
        <button class="btn btn-go" id="btnSavePolyCreds" onclick="savePolyCredentials()" style="padding:9px 18px;font-size:12px;font-weight:800">
          💾 Save &amp; Apply Credentials
        </button>
      </div>
    </div>
  </div>
</div>

<!-- ===================================================================== -->
<!-- POLYMARKET LIVE TRADING CONFIRMATION SAFETY MODAL                     -->
<!-- ===================================================================== -->
<div id="polyLiveConfirmModal" style="display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(4,6,12,.88);backdrop-filter:blur(8px);z-index:1000;align-items:center;justify-content:center;">
  <div style="background:#0C101A;border:1px solid rgba(239,68,68,.5);border-radius:14px;width:90%;max-width:540px;padding:24px;display:flex;flex-direction:column;gap:16px;box-shadow:0 24px 50px rgba(239,68,68,.2)">
    <div style="display:flex;align-items:center;gap:10px;border-bottom:1px solid rgba(239,68,68,.3);padding-bottom:12px">
      <span style="font-size:24px">⚠️</span>
      <div>
        <div style="font-size:16px;font-weight:800;color:#F87171">Arm Live Real-Money Trading?</div>
        <div style="font-size:11.5px;color:var(--tx2)">Real gasless orders will be placed on Polymarket using on-chain USDC.e collateral.</div>
      </div>
    </div>

    <div style="background:rgba(0,0,0,.4);border:1px solid rgba(255,255,255,.08);border-radius:8px;padding:12px 14px;font-size:12px;display:flex;flex-direction:column;gap:6px">
      <div style="display:flex;justify-content:space-between">
        <span style="color:var(--tx3)">Spendable USDC.e:</span>
        <b id="polyConfirmLiveBalance" style="color:#10B981;font-family:'JetBrains Mono',monospace">$0.00</b>
      </div>
      <div style="display:flex;justify-content:space-between">
        <span style="color:var(--tx3)">Max Outlay Per Trade:</span>
        <b style="color:#FBBF24;font-family:'JetBrains Mono',monospace">$5.00 (Safe Entry)</b>
      </div>
      <div style="display:flex;justify-content:space-between">
        <span style="color:var(--tx3)">Contracts Monitored:</span>
        <b style="color:#38BDF8">BTC, ETH, SOL, XRP (5m Expiries)</b>
      </div>
      <div style="display:flex;justify-content:space-between">
        <span style="color:var(--tx3)">Risk Management:</span>
        <span style="color:#A5B4FC">Auto TP @ 92¢ · Auto SL @ 28¢</span>
      </div>
    </div>

    <div style="font-size:11px;color:var(--tx2);line-height:1.5">
      The scalper will only trigger if an algorithmic edge &gt; 12% is verified with low-latency Binance order-flow leading the Polymarket TWAP oracle.
    </div>

    <div style="display:flex;justify-content:flex-end;gap:10px;border-top:1px solid var(--bdr);padding-top:14px">
      <button class="btn btn-x" onclick="closePolyLiveConfirmModal(false)" style="padding:9px 16px;font-size:12px">🛑 Cancel / Stay in Paper</button>
      <button class="btn btn-go" onclick="closePolyLiveConfirmModal(true)" style="padding:9px 18px;font-size:12px;font-weight:800;background:linear-gradient(135deg,#DC2626,#EF4444);border-color:#EF4444">
        🟢 Confirm &amp; Arm Live Scalper
      </button>
    </div>
  </div>
</div>

<!-- ===================================================================== -->
<!-- CRYPTO SENTINEL AI COMMAND CENTER WORKSPACE                           -->
<!-- ===================================================================== -->
<div id="view-crypto" style="display:none">
<main style="max-width:1720px">
  <div class="left-col" style="flex:1">
    <!-- Top Action & Status Banner -->
    <div style="background:linear-gradient(90deg,rgba(245,158,11,.12),rgba(99,102,241,.06));border:1px solid rgba(245,158,11,.3);border-radius:12px;padding:14px 18px;display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap">
      <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap">
        <div id="cryptoPulseDot" style="width:10px;height:10px;border-radius:50%;background:#10B981;box-shadow:0 0 12px #10B981;animation:p 1.5s infinite"></div>
        <div>
          <div style="display:flex;align-items:center;gap:8px">
            <b style="font-size:14px;color:#F8FAFC">CRYPTO SENTINEL AI</b>
            <span id="cryptoStatusPill" class="b b-p">● ENGINE READY</span>
            <span id="cryptoRegimeBadge" class="b" style="background:rgba(245,158,11,.2);color:#FBBF24;border:1px solid rgba(245,158,11,.4)">REGIME: DETECTING...</span>
            <span id="cryptoModeBadge" class="b b-d">SIMULATED PAPER</span>
          </div>
          <div id="cryptoBotDoing" style="font-size:12px;color:#94A3B8;margin-top:4px;font-family:'JetBrains Mono',monospace">
            🤖 <b>CURRENT ACTIVITY:</b> <span id="cryptoCurrentTask">Initializing market scanner...</span>
          </div>
        </div>
      </div>

      <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
        <select id="cryptoModeSelect" onchange="cryptoChangeMode(this.value)" style="background:#0F172A;border:1px solid var(--bdr);color:#F8FAFC;padding:6px 10px;border-radius:6px;font-size:11px;font-weight:600;outline:none">
          <option value="SIMULATED_PAPER">Simulated Paper Mode</option>
          <option value="BINANCE_TESTNET">Binance Testnet API</option>
        </select>
        <select id="cryptoProfileSelect" onchange="cryptoChangeProfile(this.value)" style="background:#0F172A;border:1px solid #38BDF8;color:#38BDF8;padding:6px 10px;border-radius:6px;font-size:11px;font-weight:700;outline:none;cursor:pointer">
          <option value="FAST_SCALPER">⚡ Fast Scalper Mode (0.4R / 0.8R Sweet-Spot)</option>
          <option value="OPTIMAL_GROWTH">⭐ Optimal Growth (1.0R / 2.0R Balanced)</option>
          <option value="ULTRA_SAFE">🛡️ Ultra-Safe Prop Firm (0.25% Risk · 1.0R/2.0R)</option>
          <option value="AGGRESSIVE_GROWTH">🚀 Aggressive Growth (2.00% Risk · 1.0R/2.0R)</option>
        </select>
        <button id="cryptoToggleBtn" class="btn btn-go" onclick="cryptoToggle()">▶ Start Engine</button>
        <button class="btn btn-demo" onclick="cryptoScan()">🔍 Scan Universe</button>
        <button class="btn btn-x" onclick="cryptoFlatten()">⚠ Flatten All</button>
        <button class="btn btn-g" onclick="cryptoReset()">🔄 Reset</button>
      </div>
    </div>

    <!-- Strategy Profile Live Details & Parameter Columns Banner -->
    <div id="cryptoProfileBanner" style="background:#090D15;border:1px solid var(--bdr);border-left:4px solid #38BDF8;border-radius:8px;padding:12px 16px;margin-top:12px;font-family:'Inter',sans-serif">
      <!-- Populated dynamically by JS -->
    </div>

    <!-- Stats Bar -->
    <div class="krow" style="margin-top:12px">
      <div class="kc a">
        <div class="kl">Crypto Account Equity</div>
        <div class="kv" id="cBal">$1,000.00</div>
        <div class="ks"><span>Peak: <b id="cPk" class="g">$1,000.00</b></span><span>Base: <b>$1,000.00</b></span></div>
      </div>
      <div class="kc p">
        <div style="display:flex;justify-content:space-between;align-items:center">
          <div class="kl">Realized Net PnL</div>
          <span style="font-size:9.5px;color:var(--tx3);font-family:'JetBrains Mono',monospace" id="cPnlSubBreakdown">Net After Fees</span>
        </div>
        <div class="kv g" id="cPnl">+$0.00</div>
        <div class="ks">
          <span>Gross: <b id="cGrossPnl" class="g">+$0.00</b></span>
          <span>Fees: <b id="cTotalFees" class="r">-$0.00</b></span>
          <span>WR: <b id="cWr" class="g">0%</b></span>
          <span>Trades: <b id="cTrades">0</b></span>
        </div>
      </div>
      <div class="kc d">
        <div class="kl">Daily Risk &amp; Drawdown Lock</div>
        <div class="kv" id="cDd">0.00%</div>
        <div class="ks"><span style="color:var(--am)" id="cMaxLock">Max Lock: 3.00%</span><span id="cLockStatus" class="g">SAFE / ACTIVE</span></div>
      </div>
      <div class="kc m">
        <div class="kl">Double Tap Protocol</div>
        <div class="kv" style="color:var(--cy)" id="cDtHeader">1.5R ➔ 3.0R</div>
        <div class="ks"><span id="cDtSub1">TP1: 50% Exit</span><span id="cDtSub2">Defensive SL at BE</span></div>
      </div>
    </div>

    <!-- Active Trades (What is Taken, SL, TP1, TP2) -->
    <div class="pn" style="margin-top:14px">
      <div class="ph">
        <div class="pt">🎯 Active Taken Trades (Double Tap OMS: SL, TP1, TP2)</div>
        <span id="cryptoPosCount" class="b b-p">0 OPEN</span>
      </div>
      <div id="cryptoPositionsGrid" style="padding:14px;display:flex;flex-direction:column;gap:10px">
        <div class="empty">No active trades open. Bot is continuously scanning the universe for high-probability setups.</div>
      </div>
    </div>

    <!-- Opportunity Analysis Card (Is there an opportunity right now?) -->
    <div class="pn" style="margin-top:14px">
      <div class="ph">
        <div class="pt">⚡ Analyzing Opportunities (Engine A: ICT | Engine B: Momentum | Engine C: Liquidation)</div>
        <span class="b b-d">LIVE TELEMETRY</span>
      </div>
      <div id="cryptoAnalysisList" style="padding:14px;display:flex;flex-direction:column;gap:10px">
        <div class="empty">Analyzing market structure across Top 12 Prime coins...</div>
      </div>
    </div>

    <!-- Which Coins Picked and Why Picked (Top 12 Prime Screener & Active Focus) -->
    <div class="pn" style="margin-top:14px">
      <div class="ph">
        <div class="pt">🪙 Which Coins Picked &amp; Why (Top 12 Prime Screener)</div>
        <div style="display:flex;gap:8px;align-items:center">
          <input type="text" id="cryptoSearch" placeholder="Filter coin (e.g. PEPE, BTC)..." oninput="cryptoFilterTable()" style="background:#090D15;border:1px solid var(--bdr);color:#fff;padding:4px 8px;border-radius:6px;font-size:11px">
        </div>
      </div>

      <!-- High Conviction Active Focus Cards -->
      <div style="padding:14px;background:#090D15;border-bottom:1px solid var(--bdr)">
        <div style="font-size:11px;font-weight:700;color:var(--tx2);text-transform:uppercase;letter-spacing:.05em;margin-bottom:8px">🔥 Top High-Conviction Coins Selected for Active Execution:</div>
        <div id="cryptoFocusCards" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:10px">
          <!-- Populated by JS -->
        </div>
      </div>

      <!-- Screener Table -->
      <div class="tw" style="max-height:360px;overflow-y:auto">
        <table>
          <thead>
            <tr>
              <th>Coin</th>
              <th>Sector</th>
              <th>Price</th>
              <th>24h Change</th>
              <th>24h Volume</th>
              <th>Score</th>
              <th>Why Picked / Market State</th>
            </tr>
          </thead>
          <tbody id="cryptoScreenerTb">
            <tr><td colspan="7" class="empty">Scanning universe...</td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Recent Closed Trades History -->
    <div class="pn" style="margin-top:14px">
      <div class="ph"><div class="pt">📜 Recent Closed Crypto Trades</div></div>
      <div class="tw">
        <table>
          <thead>
            <tr>
              <th>Time</th>
              <th>Coin</th>
              <th>Engine</th>
              <th>Side</th>
              <th>Entry ➔ Exit</th>
              <th>Gross PnL</th>
              <th>Fee</th>
              <th>Net Take-Home</th>
              <th>R-Multiple</th>
              <th>Exit Reason</th>
            </tr>
          </thead>
          <tbody id="cryptoTradesTb">
            <tr><td colspan="10" class="empty">No closed trades yet.</td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- AI Asset Intelligence & Behavioral Memory -->
    <div class="pn" style="margin-top:14px">
      <div class="ph" style="display:flex;justify-content:space-between;align-items:center">
        <div class="pt">🧠 AI Asset Intelligence &amp; Behavioral Memory</div>
        <div style="display:flex;align-items:center;gap:8px">
          <a href="/api/crypto/export-dataset" target="_blank" style="text-decoration:none;font-size:10px;padding:3px 8px;background:#1E293B;border:1px solid var(--bdr);color:#94A3B8;border-radius:4px;font-family:'JetBrains Mono',monospace">📥 Export AI Dataset (JSON)</a>
          <div style="font-size:10px;color:var(--t3);font-family:'JetBrains Mono',monospace">Top 12 Prime Universe · Auto-Quarantine (24h Cooldown)</div>
        </div>
      </div>
      <div class="tw">
        <table>
          <thead>
            <tr>
              <th>Status</th>
              <th>Asset</th>
              <th>Win Rate</th>
              <th>Trades (W/L)</th>
              <th>Gross PnL</th>
              <th>Binance Fees</th>
              <th>Net Take-Home</th>
              <th>AI Behavioral Debrief &amp; Lesson Learned</th>
            </tr>
          </thead>
          <tbody id="cryptoIntelligenceTb">
            <tr><td colspan="8" class="empty">Loading asset intelligence...</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>

  <!-- RIGHT COLUMN: Bot Thinking & Live Activity Feed -->
  <div class="right-col" style="width:360px;min-width:320px">
    <div class="pn" style="position:sticky;top:115px">
      <div class="ph">
        <div class="pt">🤖 Bot Activity &amp; Decision Stream</div>
        <span class="b b-p" style="font-size:9px">REAL-TIME</span>
      </div>
      <div id="cryptoActivityList" style="padding:12px;display:flex;flex-direction:column;gap:8px;max-height:750px;overflow-y:auto;font-family:'JetBrains Mono',monospace;font-size:11px">
        <div class="empty">Awaiting activity logs...</div>
      </div>
    </div>
  </div>
</main>
</div>

<script>
let R=false,AT=[],currentSessionInfo=null;
let polyCurrentCoin = 'BTC';
let polyCurrentTf = '5m';
let polyTimelineCache = {};
const $=id=>document.getElementById(id);
const fx=(a,v)=>a.includes('USD')?v.toFixed(4):v.toFixed(2);
const escHtml=s=>!s?'':String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');

// ── Running Institutional Clock & Session Countdown ──────────────────
function tickRunningClock() {
  const now = new Date();

  // 1. Local System Clock
  const locStr = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
  const clkLoc = $('clockLocal');
  if (clkLoc) clkLoc.innerText = locStr;

  // 2. NY / Eastern Time (IPDA Standard Reference Clock)
  try {
    const nyStr = now.toLocaleTimeString('en-US', { timeZone: 'America/New_York', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
    const clkEst = $('clockEst');
    if (clkEst) clkEst.innerText = nyStr + ' EST';
  } catch(e) {}

  // 3. Running Countdown to Open or Close
  if (currentSessionInfo && currentSessionInfo.target_time) {
    const targetMs = new Date(currentSessionInfo.target_time).getTime();
    const diffSec = Math.max(0, Math.floor((targetMs - now.getTime()) / 1000));

    const hrs = Math.floor(diffSec / 3600);
    const mins = Math.floor((diffSec % 3600) / 60);
    const secs = diffSec % 60;
    const timeFormatted = `${String(hrs).padStart(2, '0')}h ${String(mins).padStart(2, '0')}m ${String(secs).padStart(2, '0')}s`;

    const timerBadge = $('sessionTimerBadge');
    const timerLabel = $('timerLabel');
    const timerCountdown = $('timerCountdown');
    const timeline = $('sessionTimeline');
    const countText = $('sessionCountdownText');

    if (currentSessionInfo.active) {
      if (timerBadge) timerBadge.className = 'timer-pill active';
      if (timerLabel) timerLabel.innerText = 'Closes in:';
      if (timerCountdown) timerCountdown.innerText = timeFormatted;
      if (timeline) timeline.className = 'clock-status-bar active';
      if (countText) countText.innerText = `🟢 ${currentSessionInfo.label} closes in ${timeFormatted}`;
    } else {
      if (timerBadge) timerBadge.className = 'timer-pill off';
      const shortName = currentSessionInfo.next_session === 'ASIAN_MACRO' ? 'Asian Macro' :
                       (currentSessionInfo.next_session === 'LONDON' ? 'London' :
                       (currentSessionInfo.next_session === 'NEW_YORK_AM' ? 'New York AM' : (currentSessionInfo.label || 'Next Session')));
      if (timerLabel) timerLabel.innerText = `${shortName} in:`;
      if (timerCountdown) timerCountdown.innerText = timeFormatted;
      if (timeline) timeline.className = 'clock-status-bar';
      if (countText) countText.innerText = `⏳ ${currentSessionInfo.label} opens in ${timeFormatted}`;
    }

    if (diffSec === 0 && currentSessionInfo._armed) {
      currentSessionInfo._armed = false;
      fetch('/api/state').then(r => r.json()).then(U).catch(()=>{});
    }
  }

  // 3. Polymarket Fast-Expiry Candle Real-Time Continuous Clock (Exact 1s tick synchronized with Polymarket UTC epochs)
  const nowSec = Math.floor(now.getTime() / 1000);
  const tfSeconds = (typeof polyCurrentTf !== 'undefined' && polyCurrentTf === '1h') ? 3600 : ((typeof polyCurrentTf !== 'undefined' && polyCurrentTf === '15m') ? 900 : 300);
  const currentTfEnd = Math.floor(nowSec / tfSeconds) * tfSeconds + tfSeconds;
  const remSec = Math.max(0, currentTfEnd - nowSec);
  const pmM = Math.floor(remSec / 60);
  const pmS = remSec % 60;
  const timerStr = (pmM < 10 ? '0' : '') + pmM + ':' + (pmS < 10 ? '0' : '') + pmS;
  const polyTimerEl = $('poly5mTimer');
  if (polyTimerEl) {
    polyTimerEl.innerText = timerStr;
    polyTimerEl.style.color = remSec <= 30 ? '#F43F5E' : (remSec <= 150 && remSec >= 60 ? '#FBBF24' : '#38BDF8');
  }
  const pillTimer = $('polyPillActiveTimer');
  if (pillTimer) {
    pillTimer.innerText = timerStr;
  }

  // 4. Polymarket Daily Market Series Expiry Timer (Exact Parity with Polymarket Screenshot: 07 : 43 : 26 HRS MINS SECS)
  const sessionEndSec = Math.floor(nowSec / 86400) * 86400 + 86400;
  const sRem = Math.max(0, sessionEndSec - nowSec);
  const sH = String(Math.floor(sRem / 3600)).padStart(2, '0');
  const sM = String(Math.floor((sRem % 3600) / 60)).padStart(2, '0');
  const sS = String(sRem % 60).padStart(2, '0');
  const sessTimerEl = $('polySessionTimer');
  if (sessTimerEl) {
    sessTimerEl.innerText = `${sH}:${sM}:${sS}`;
  }

  // Auto-refresh timeline when round changes
  if (remSec === 0 && typeof fetchPolyTimeline === 'function') {
    fetchPolyTimeline(polyCurrentCoin, polyCurrentTf);
  }
}
setInterval(tickRunningClock, 1000);
tickRunningClock();

// ── Native SSE Real-Time Stream (No Polling) ─────────────────────────
let evtSource = null;

function connectStream() {
  if (evtSource) evtSource.close();
  
  evtSource = new EventSource('/api/stream');
  
  evtSource.onopen = () => {
    $('streamPill').className = 'stream-pill';
    $('streamPill').innerText = '● LIVE STREAM (ACTIVE)';
  };

  evtSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      U(data);
    } catch(err) {
      console.error("Stream parse error:", err);
    }
  };

  evtSource.onerror = () => {
    $('streamPill').className = 'stream-pill disconnected';
    $('streamPill').innerText = '○ RECONNECTING...';
    setTimeout(connectStream, 3000);
  };
}

function U(d){
  R=d.running;
  $('dot').className=R?'dot':'dot off';
  $('sess').innerText=d.session;
  $('microState').innerText=d.micro_state || (R ? 'Actively monitoring market tape' : 'Engine Idle');

  if (d.session_info) {
    currentSessionInfo = d.session_info;
    currentSessionInfo._armed = true;
    tickRunningClock();
  }

  const eb=$('engBtn');
  if(R){eb.className='btn btn-stop';eb.innerHTML='⏹ Stop Engine'}
  else{eb.className='btn btn-go';eb.innerHTML='▶ Start Engine'}
  
  const db=$('demBtn');
  if(d.demo){db.disabled=true;db.innerHTML='⏳ Running...'}
  else{db.disabled=false;db.innerHTML='⚡ Run Simulation'}

  // KPIs
  const a=d.acct;
  $('kBal').innerText='$'+a.bal.toFixed(2);
  $('kPk').innerText='$'+a.peak.toFixed(2);
  const pe=$('kPnl');
  pe.innerText=(a.pnl>=0?'+':'')+' $'+a.pnl.toFixed(2);
  pe.className=a.pnl>=0?'kv g':'kv r';
  $('kWr').innerText=a.wr.toFixed(1)+'%';
  $('kPf').innerText=a.pf>=900?'MAX':a.pf.toFixed(2);
  const shEl=$('kSharpe');
  if(shEl){shEl.innerText=(a.sharpe!==undefined&&a.sharpe!==null)?a.sharpe.toFixed(2):'0.00'}
  $('kTt').innerText=a.tt;
  $('kW').innerText=a.w;$('kL').innerText=a.l;
  $('kDD').innerText='$'+a.mdd.toFixed(2);
  $('kDDp').innerText=a.mddp.toFixed(1)+'%';
  $('kOp').innerText=d.pos.length+' Brackets';
  $('cyc').innerText=d.cycle?'Last: '+d.cycle.split(' ')[1]:'Streaming live...';

  // Equity
  EC(d.eq);

  // Positions
  $('pCt').innerText=d.pos.length+' Open';
  const pt=$('pTb');
  if(!d.pos.length){pt.innerHTML='<tr><td colspan="11" class="empty">No open positions. Real-time tape monitoring active...</td></tr>'}
  else{pt.innerHTML=d.pos.map(p=>`<tr>
    <td>#${p.id}</td><td><b>${p.a}</b></td>
    <td><span class="b ${p.d==='LONG'?'b-l':'b-s'}">${p.d}</span></td>
    <td>${fx(p.a,p.ep)}</td><td class="r">${fx(p.a,p.ts)}</td>
    <td><span style="color:var(--am);font-weight:600">${p.ce ? fx(p.a, p.ce) : '-'}</span><br><span style="font-size:9px;color:var(--tx3)">Early Scratch</span></td>
    <td class="g">${fx(p.a,p.cm)}<br><span style="font-size:9px;color:var(--tx3)">50% Scale</span></td>
    <td class="g">${fx(p.a,p.hs)}<br><span style="font-size:9px;color:var(--tx3)">Runner</span></td>
    <td class="${p.unr>=0?'g':'r'}">${p.unr>=0?'+':''}$${p.unr.toFixed(2)}</td>
    <td><span class="b ${p.st==='PARTIAL'?'b-d':'b-p'}">${p.st}</span></td>
    <td><button class="btn btn-x" style="padding:2px 6px;font-size:9px" onclick="cpos('${p.id}')">Close</button></td>
  </tr>`).join('')}

  // Markets
  $('mG').innerHTML=d.assets.map(a=>`<div class="mc ${a.ip?'ip':''}">
    <div class="mh">
      <span class="mn">${a.dn.split('(')[0]}</span>
      <span class="b ${a.ip?'b-d':'b-p'}">${a.ip?'TRADING':'LIVE FEED'}</span>
    </div>
    <div class="ms">${a.a} · ${a.sym}</div>
    <div class="mp">${a.px>0?fx(a.a,a.px):'Streaming...'}</div>
    <div style="font-size:10px;color:var(--tx3);display:flex;justify-content:space-between;margin-top:3px;font-family:'JetBrains Mono',monospace;">
      <span>● ${a.source}</span>
      <span>${a.last_bar_time}</span>
    </div>
  </div>`).join('');

  // AI Market Diagnostics & Decision Matrix
  const dg=$('diagList');
  if(dg && d.diagnostics && d.diagnostics.length){
    dg.innerHTML=d.diagnostics.map(x=>{
      const chkHtml = Object.entries(x.checklist).map(([k,v])=>{
        let cls = 'chk-v';
        if(v.includes('CLEAR')||v.includes('VALID')||v.includes('PASS')||v.includes('CONFIRMED')||v.includes('SWEPT')||v.includes('RESPECTED')) cls += ' g';
        else if(v.includes('STANDBY')||v.includes('WAITING')||v.includes('PENDING')||v.includes('COMPRESSED')) cls += ' y';
        else cls += ' r';
        return `<div class="chk-item"><span class="chk-k">${k}</span><span class="${cls}">${v}</span></div>`;
      }).join('');

      const scCol = x.score>=75?'var(--gr)':(x.score>=40?'var(--am)':'#94A3B8');

      return `<div class="diag-card">
        <div class="diag-top">
          <div style="display:flex;align-items:center;gap:8px">
            <span class="diag-asset">${x.asset}</span>
            <span class="diag-px">${fx(x.asset, x.current_price)}</span>
            <span class="b ${x.badge}">${x.status_label}</span>
          </div>
          <div class="diag-score-wrap">
            <span class="diag-score-lbl">Confluence Readiness:</span>
            <div class="pbb" style="width:70px;margin:0 6px"><div class="pbf" style="width:${x.score}%;background:${scCol}"></div></div>
            <b style="font-family:'JetBrains Mono',monospace;color:${scCol}">${x.score}/100</b>
          </div>
        </div>
        <div class="diag-levels">
          <span><b>Ref High:</b> ${fx(x.asset, x.ref_high)}</span>
          <span><b>Ref Low:</b> ${fx(x.asset, x.ref_low)}</span>
          <span><b>Range:</b> ${x.ref_range.toFixed(2)} pts (Min: ${x.min_range_needed})</span>
          <span><b>Zone:</b> ${x.quadrant}</span>
        </div>
        <div class="diag-checklist">${chkHtml}</div>
        <div class="diag-decision-box">
          <div class="diag-dec-title"><b>AI Executive Decision:</b> <span style="color:#F1F5F9">${x.decision}</span></div>
          <div class="diag-thesis">${x.thesis}</div>
        </div>
      </div>`;
    }).join('');
  }

  // Memory
  const mt=$('mTb');
  if(!d.mem.length){mt.innerHTML='<tr><td colspan="4" class="empty">Accumulating episodes...</td></tr>'}
  else{mt.innerHTML=d.mem.map(w=>{
    const pct=Math.round(w.quality_score*100);
    let bc='b-p';if(w.status==='QUARANTINED')bc='b-q';else if(w.status==='OBSERVATION')bc='b-d';
    return`<tr><td><b>${w.key_pair}</b></td><td>${w.wins}W / ${w.losses}L</td>
    <td><div class="pbb"><div class="pbf" style="width:${pct}%"></div></div>${pct}%</td>
    <td><span class="b ${bc}">${w.status}</span></td></tr>`}).join('')}

  const rf=$('ref');
  if(d.ref&&d.ref.length){const r=d.ref[0];rf.innerHTML=`<b>[${r.asset}::${r.session}] ${r.reflection_type}:</b> ${r.lesson}`}

  // Cross-Session Transition Debriefs
  const dbList=$('debriefList');
  if(dbList){
    if(!d.debriefs || !d.debriefs.length){
      dbList.innerHTML='<div class="empty">Awaiting session close to compile cross-session debrief...</div>';
    }else{
      dbList.innerHTML=d.debriefs.map(b=>`
        <div style="background:var(--s2);border:1px solid var(--bdr);border-radius:6px;padding:12px">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
            <div style="display:flex;gap:8px;align-items:center">
              <b style="color:#F1F5F9;font-family:'JetBrains Mono',monospace">${b.session_name} DEBRIEF</b>
              <span class="b b-d">${b.date}</span>
              <span class="b ${b.net_dollar_pnl>=0?'b-p':'b-q'}">${b.net_dollar_pnl>=0?'+':''}$${b.net_dollar_pnl.toFixed(2)} (${b.trades_taken} trades)</span>
            </div>
            <span class="b b-p" style="font-size:10px">${b.asian_sweep_type}</span>
          </div>
          <div style="font-size:11px;color:var(--tx2);margin-bottom:6px">
            <b>Session Range:</b> Low ${b.session_low.toFixed(2)} ──► High ${b.session_high.toFixed(2)} | 
            <b>Next Bias:</b> <span style="color:var(--am);font-weight:600">${b.cross_session_bias}</span>
          </div>
          <div style="font-size:11px;color:#94A3B8;line-height:1.5;background:#090D15;padding:8px;border-radius:4px;border:1px solid rgba(255,255,255,.03)">
            ${b.ai_debrief_summary}
          </div>
        </div>
      `).join('');
    }
  }

  // ── Render Meta-Reflections & Scientific Method Journal ──
  const metaList = $('metaReflectionList');
  if (metaList) {
    if (!d.meta_reflections || !d.meta_reflections.length) {
      metaList.innerHTML = '<div class="empty">Synthesizing institutional multi-session batch metrics...</div>';
    } else {
      metaList.innerHTML = d.meta_reflections.map(m => `
        <div style="background:var(--s2);border:1px solid var(--bdr);border-radius:6px;padding:12px;display:flex;flex-direction:column;gap:6px">
          <div style="display:flex;justify-content:space-between;align-items:center">
            <div style="display:flex;gap:8px;align-items:center">
              <b style="color:#F1F5F9;font-family:'JetBrains Mono',monospace">${m.window_name}</b>
              <span class="b b-p">${m.timestamp}</span>
              <span class="b ${m.status === 'CONFIRMED' ? 'b-p' : (m.status === 'TESTING' ? 'b-d' : 'b-q')}">${m.status}</span>
            </div>
            <div style="font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--tx2)">
              Sharpe: <b style="color:var(--cy)">${m.realized_sharpe.toFixed(2)}</b> (Goal: 1.50) | PF: <b style="color:var(--gr)">${m.profit_factor.toFixed(2)}</b> (Goal: 2.00)
            </div>
          </div>
          <div style="font-size:11px;color:var(--tx2);line-height:1.4">
            <b style="color:var(--am)">Single Variable Isolated:</b> <span style="color:#F1F5F9;font-weight:600">${m.variable_tested}</span>
          </div>
          <div style="font-size:11px;color:#94A3B8;background:#090D15;padding:8px;border-radius:4px;border:1px solid rgba(255,255,255,.03);line-height:1.4">
            <b>Scientific Hypothesis & Target:</b> ${m.hypothesis}
          </div>
        </div>
      `).join('');
    }
  }

  // ── Render Live Activity Stream (Right Sidebar) ──
  const actList=$('activityList');
  if(d.activity&&d.activity.length){
    actList.innerHTML=d.activity.map(act=>`
      <div class="act-item ${act.level}">
        <div class="act-top">
          <span class="act-tag" style="background:rgba(255,255,255,.05);color:var(--tx2);">${act.category}</span>
          <span class="act-time">${act.time}</span>
        </div>
        <div class="act-title">${act.title}</div>
        <div class="act-desc">${act.details}</div>
      </div>
    `).join('');
  }

  // ── Render Risk & Safety Gauges ──
  if(d.risk_guards){
    const rg=d.risk_guards;
    $('lossShieldVal').innerText=`${rg.consecutive_losses} / ${rg.max_consecutive_allowed} Losses`;
    const lossPct=Math.min(100,(rg.consecutive_losses/rg.max_consecutive_allowed)*100);
    const lossBar=$('lossShieldBar');
    lossBar.style.width=`${lossPct}%`;
    lossBar.style.background=rg.consecutive_losses>=2?'var(--rd)':'var(--gr)';

    if(rg.locked_for_day){
      $('ddBudgetVal').innerHTML=`<span style="color:var(--rd);font-weight:700">LOCKED ($${rg.drawdown_current.toFixed(2)} / $${rg.daily_risk_budget.toFixed(2)})</span>`;
    }else{
      $('ddBudgetVal').innerText=`$${rg.drawdown_current.toFixed(2)} / $${rg.daily_risk_budget.toFixed(2)}`;
    }
    const ddPct=Math.min(100,(rg.drawdown_current/rg.daily_risk_budget)*100);
    const ddBar=$('ddBudgetBar');
    ddBar.style.width=`${ddPct}%`;
    ddBar.style.background=rg.locked_for_day?'var(--rd)':(ddPct>70?'var(--rd)':(ddPct>40?'var(--am)':'var(--gr)'));
  }

  AT=d.trades;filt();
}

function EC(pts){
  if(!pts||pts.length<2)return;
  const s=$('svg'),w=s.clientWidth||800,h=s.clientHeight||160,pd=16;
  const bs=pts.map(p=>p.b),mn=Math.min(...bs)*.998,mx=Math.max(...bs)*1.002,rn=(mx-mn)||1;
  const cs=pts.map((p,i)=>({
    x:pd+(i/(pts.length-1))*(w-pd*2),
    y:h-pd-((p.b-mn)/rn)*(h-pd*2),b:p.b,t:p.t
  }));
  const ld=cs.reduce((a,c,i)=>a+`${i?'L':'M'}${c.x.toFixed(1)} ${c.y.toFixed(1)} `,'');
  $('cL').setAttribute('d',ld);
  $('cA').setAttribute('d',ld+`L${cs[cs.length-1].x.toFixed(1)} ${h} L${cs[0].x.toFixed(1)} ${h} Z`);
  $('cD').innerHTML=cs.map(c=>`<circle class="cd" cx="${c.x.toFixed(1)}" cy="${c.y.toFixed(1)}" r="3.5"><title>${c.t}: $${c.b.toFixed(2)}</title></circle>`).join('');
}

function filt(){
  const q=($('tSr').value||'').toUpperCase();
  const f=AT.filter(t=>t.a.includes(q)||t.out.includes(q)||t.ss.includes(q));
  const tb=$('tTb');
  if(!f.length){tb.innerHTML='<tr><td colspan="8" class="empty">No matching trades.</td></tr>';return}
  tb.innerHTML=f.map(t=>{
    let bc='b-w';
    if(t.out==='DEFENSIVE_STOP') bc='b-d';
    else if(t.out==='EARLY_SCRATCH') bc='b-d';
    else if(t.out==='SESSION_EXPIRATION') bc='b-p';
    else if(t.out==='LOSS') bc='b-x';
    const pc=t.pnl>=0?'g':'r',sg=t.pnl>=0?'+':'';
    const targets = (t.tp1 && t.tp2) ? `<span style="font-size:9px;color:var(--tx3)">TP1: ${fx(t.a,t.tp1)} | TP2: ${fx(t.a,t.tp2)}</span>` : '';
    const inv = t.inv ? `<br><span style="font-size:9px;color:var(--am)">Trigger: ${t.inv}</span>` : '';
    return`<tr>
      <td>${t.xt}</td><td><b>${t.a}</b></td><td>${t.ss}</td>
      <td><span class="b ${t.d==='LONG'?'b-l':'b-s'}">${t.d}</span></td>
      <td>${fx(t.a,t.ep)} ➔ ${fx(t.a,t.xp)}<br>${targets}</td>
      <td class="${pc}"><b>${sg}$${t.pnl.toFixed(2)}</b></td>
      <td><span class="b ${bc}">${t.out}</span>${inv}</td>
      <td style="color:var(--tx2);font-size:10.5px;max-width:240px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${t.ai}">${t.ai}</td>
    </tr>`}).join('');
}

async function toggle(){await fetch(R?'/api/bot/stop':'/api/bot/start',{method:'POST'});}
async function demo(){await fetch('/api/bot/demo',{method:'POST'});}
async function flatten(){if(confirm('Flatten ALL open positions at market price?')){await fetch('/api/bot/flatten',{method:'POST'});}}
async function cpos(id){if(confirm('Close position #'+id+'?')){await fetch('/api/bot/close',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id})});}}
async function reset(){if(confirm('Reset account to $500 and clear all history?')){await fetch('/api/bot/reset',{method:'POST'});}}

// ── Polymarket Client Intelligence & Navigation ──────────────────────
let currentMainTab = 'ict';
let polyInterval = null;
let allPolyMarkets = [];
let allPolyEvidence = [];
let polyRunning = false;
let currentPolyCategory = 'ALL';
let currentPolyView = 'cards';

function setPolyCategory(cat, el) {
  currentPolyCategory = cat;
  const chips = document.querySelectorAll('.poly-chip');
  chips.forEach(c => c.classList.remove('active'));
  if (el) el.classList.add('active');
  filterPolyMarkets();
}

function setPolyView(mode) {
  currentPolyView = mode;
  const cardsWrap = $('polyCardsWrap');
  const tableWrap = $('polyTableWrap');
  const btnCards = $('viewBtnCards');
  const btnTable = $('viewBtnTable');
  if (mode === 'cards') {
    cardsWrap.style.display = 'grid';
    tableWrap.style.display = 'none';
    if (btnCards) btnCards.className = 'btn btn-demo';
    if (btnTable) btnTable.className = 'btn btn-g';
  } else {
    cardsWrap.style.display = 'none';
    tableWrap.style.display = 'block';
    if (btnCards) btnCards.className = 'btn btn-g';
    if (btnTable) btnTable.className = 'btn btn-demo';
  }
}

async function polyToggleAuto() {
  await fetch(polyRunning ? '/api/polymarket/stop' : '/api/polymarket/start', { method: 'POST' });
  setTimeout(loadPolymarketState, 300);
}

function switchMainTab(tab) {
  currentMainTab = tab;
  const tabIct = $('tabBtnIct');
  const tabPoly = $('tabBtnPoly');
  const tabCrypto = $('tabBtnCrypto');
  const viewIct = $('view-ict');
  const viewPoly = $('view-poly');
  const viewCrypto = $('view-crypto');

  tabIct.classList.remove('active');
  tabPoly.classList.remove('active');
  if (tabCrypto) tabCrypto.classList.remove('active');

  viewIct.style.display = 'none';
  viewPoly.style.display = 'none';
  if (viewCrypto) viewCrypto.style.display = 'none';

  if (polyInterval) { clearInterval(polyInterval); polyInterval = null; }
  if (cryptoInterval) { clearInterval(cryptoInterval); cryptoInterval = null; }

  if (tab === 'ict') {
    tabIct.classList.add('active');
    viewIct.style.display = 'block';
  } else if (tab === 'poly') {
    tabPoly.classList.add('active');
    viewPoly.style.display = 'block';
    loadPolymarketState();
    if (!polyInterval) { polyInterval = setInterval(loadPolymarketState, 1000); }
  } else if (tab === 'crypto') {
    if (tabCrypto) tabCrypto.classList.add('active');
    if (viewCrypto) viewCrypto.style.display = 'block';
    loadCryptoState();
    if (!cryptoInterval) { cryptoInterval = setInterval(loadCryptoState, 2500); }
  }
}

// ── Crypto Sentinel Client Intelligence & Rendering ────────────────────
let cryptoInterval = null;
let allCryptoScreener = [];
let cryptoRunning = false;

async function loadCryptoState() {
  try {
    const res = await fetch('/api/crypto/state');
    const d = await res.json();
    renderCrypto(d);
  } catch (e) {}
}

function renderCrypto(d) {
  if (!d) return;
  cryptoRunning = d.running;
  allCryptoScreener = d.screener_candidates || [];

  // 1. Status & Header
  const btn = $('cryptoToggleBtn');
  if (btn) {
    btn.className = d.running ? 'btn btn-x' : 'btn btn-go';
    btn.innerText = d.running ? '⏸ Pause Engine' : '▶ Start Engine';
  }
  const pill = $('cryptoStatusPill');
  if (pill) {
    pill.innerText = d.running ? '● ENGINE ACTIVE' : '○ ENGINE STOPPED';
    pill.className = d.running ? 'b b-p' : 'b b-q';
  }
  const dot = $('cryptoPulseDot');
  if (dot) dot.style.background = d.running ? '#10B981' : '#F43F5E';

  const reg = $('cryptoRegimeBadge');
  if (reg) {
    reg.innerText = 'REGIME: ' + (d.regime || 'BALANCED');
  }

  const task = $('cryptoCurrentTask');
  if (task) task.innerText = d.status || 'Scanning markets...';

  const modeBadge = $('cryptoModeBadge');
  if (modeBadge) modeBadge.innerText = (d.account && d.account.mode) ? d.account.mode.replace('_', ' ') : 'SIMULATED PAPER';
  const modeSelect = $('cryptoModeSelect');
  if (modeSelect && d.account && d.account.mode && document.activeElement !== modeSelect) {
    modeSelect.value = d.account.mode;
  }

  const profSelect = $('cryptoProfileSelect');
  const selProf = d.selected_profile || (d.account && d.account.strategy_profile) || 'MODERATE_GROWTH';
  if (profSelect && document.activeElement !== profSelect) {
    profSelect.value = selProf;
  }

  // Strategy Profile Live Banner Details
  const profBanner = $('cryptoProfileBanner');
  if (profBanner && d.strategy_profiles) {
    const pInfo = d.strategy_profiles[selProf] || d.strategy_profiles['MODERATE_GROWTH'];
    const accBal = (d.account && d.account.balance) ? d.account.balance : 3800;
    let riskCalc = (accBal * (pInfo.risk_per_trade_pct / 100));
    if (pInfo.max_dollar_risk && riskCalc > pInfo.max_dollar_risk) riskCalc = pInfo.max_dollar_risk;
    const riskDollar = riskCalc.toFixed(2);
    const tp1Profit = (riskCalc * pInfo.target_1_r * 0.5).toFixed(2);
    const tp2Profit = (riskCalc * pInfo.target_2_r * 0.5).toFixed(2);
    const totalMaxProfit = (riskCalc * pInfo.target_1_r * 0.5 + riskCalc * pInfo.target_2_r * 0.5).toFixed(2);

    profBanner.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;margin-bottom:8px">
        <div style="display:flex;align-items:center;gap:10px">
          <span style="font-size:13px;font-weight:700;color:#F8FAFC">⚡ Active Strategy: ${pInfo.name}</span>
          <span class="b b-p" style="font-size:9.5px;letter-spacing:0.05em">${pInfo.badge}</span>
          <span style="font-size:11px;color:#94A3B8">· ⏱ ${pInfo.speed}</span>
        </div>
        <div style="font-size:11px;color:#38BDF8;font-weight:600">
          Max Daily Drawdown Cap: ${pInfo.max_daily_drawdown_pct.toFixed(1)}%
        </div>
      </div>
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(145px,1fr));gap:8px;background:#06080F;padding:10px 12px;border-radius:6px;font-family:'JetBrains Mono',monospace;font-size:11px">
        <div><span style="color:var(--tx3)">Risk Per Trade:</span> <b style="color:#F8FAFC">${pInfo.risk_per_trade_pct.toFixed(2)}% ($${riskDollar})</b></div>
        <div><span style="color:var(--tx3)">Meme Risk Collar:</span> <b style="color:#FBBF24">${pInfo.meme_risk_pct.toFixed(2)}%</b></div>
        <div><span style="color:var(--cy)">Target 1 (50%):</span> <b style="color:#38BDF8">${pInfo.target_1_r}R (~+$${tp1Profit})</b></div>
        <div><span style="color:var(--gr)">Target 2 (Runner):</span> <b style="color:#34D399">${pInfo.target_2_r}R (~+$${tp2Profit})</b></div>
        <div><span style="color:#A78BFA">Max Trade Yield:</span> <b style="color:#C4B5FD">+$${totalMaxProfit}</b></div>
      </div>
      <div style="margin-top:8px;font-size:11.5px;color:#94A3B8;line-height:1.4">
        <span style="text-decoration:underline;text-decoration-color:#38BDF8;text-underline-offset:3px;color:#E2E8F0;font-weight:500">${pInfo.description}</span>
      </div>
    `;

    // Also update stats cards
    const dtH = $('cDtHeader');
    if (dtH) dtH.innerText = `${pInfo.target_1_r}R ➔ ${pInfo.target_2_r}R`;
    const dtS1 = $('cDtSub1');
    if (dtS1) dtS1.innerText = `TP1: ${pInfo.target_1_r}R (50% Exit)`;
    const dtS2 = $('cDtSub2');
    if (dtS2) dtS2.innerText = (pInfo.id === 'FAST_SCALPER' ? 'Rapid Scalp TP2' : 'Defensive SL at BE');
    const maxLockEl = $('cMaxLock');
    if (maxLockEl) maxLockEl.innerText = `Max Lock: ${pInfo.max_daily_drawdown_pct.toFixed(2)}%`;
  }

  // 2. Stats
  if (d.account) {
    const acc = d.account;
    $('cBal').innerText = '$' + acc.balance.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    if (d.testnet_info) {
      $('cPk').innerHTML = `<span style="color:#38BDF8">Avail: $${d.testnet_info.available_balance.toFixed(2)}</span>`;
    } else {
      $('cPk').innerText = '$' + acc.peak_balance.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }
    
    const grossVal = acc.gross_pnl !== undefined ? acc.gross_pnl : acc.realized_pnl;
    const feeVal = acc.total_fees !== undefined ? acc.total_fees : 0.0;
    const netVal = acc.net_pnl !== undefined ? acc.net_pnl : (grossVal - feeVal);

    const pnlEl = $('cPnl');
    pnlEl.innerText = (netVal >= 0 ? '+' : '') + '$' + netVal.toFixed(2);
    pnlEl.className = 'kv ' + (netVal >= 0 ? 'g' : 'r');

    const subBk = $('cPnlSubBreakdown');
    if (subBk) subBk.innerText = `Net: ${netVal >= 0 ? '+' : ''}$${netVal.toFixed(2)}`;

    const grossEl = $('cGrossPnl');
    if (grossEl) {
      grossEl.innerText = (grossVal >= 0 ? '+' : '') + '$' + grossVal.toFixed(2);
      grossEl.className = grossVal >= 0 ? 'g' : 'r';
    }
    const feeEl = $('cTotalFees');
    if (feeEl) feeEl.innerText = '-$' + feeVal.toFixed(2);

    $('cWr').innerText = acc.win_rate_pct + '%';
    $('cTrades').innerText = acc.total_trades + ` (${acc.wins}W / ${acc.losses}L)`;

    const ddEl = $('cDd');
    ddEl.innerText = acc.daily_drawdown_pct.toFixed(2) + '%';
    ddEl.className = 'kv ' + (acc.daily_drawdown_pct > 0.8 ? 'r' : 'a');

    const lockEl = $('cLockStatus');
    if (acc.is_locked) {
      lockEl.innerText = 'LOCKED (1% BREACH)';
      lockEl.className = 'r';
    } else {
      lockEl.innerText = 'SAFE / ACTIVE';
      lockEl.className = 'g';
    }
  }

  // 3. Active Positions (What is Taken, SL, TP1, TP2)
  const posCount = $('cryptoPosCount');
  if (posCount) posCount.innerText = (d.open_positions.length) + ' OPEN';

  const posGrid = $('cryptoPositionsGrid');
  if (!d.open_positions || !d.open_positions.length) {
    posGrid.innerHTML = '<div class="empty">No active trades open. Bot is continuously scanning the universe for high-probability setups.</div>';
  } else {
    posGrid.innerHTML = d.open_positions.map(p => {
      const isLong = p.direction === 'LONG';
      const sideClass = isLong ? 'b-l' : 'b-s';
      const pnlColor = p.unrealized_pnl >= 0 ? 'color:var(--gr)' : 'color:var(--rd)';
      const pnlSign = p.unrealized_pnl >= 0 ? '+' : '';

      const markVal = (p.current_price !== undefined && p.current_price !== null ? p.current_price : p.entry_price);
      const isProfitMove = isLong ? (markVal >= p.entry_price) : (markVal <= p.entry_price);
      const markColor = isProfitMove ? '#10B981' : '#F43F5E';
      const markArrow = isProfitMove ? '▲' : '▼';

      const ageMins = p.entry_time ? Math.floor((Date.now() / 1000 - p.entry_time) / 60) : 0;
      const ageBadge = `<span class="b b-d" style="font-size:9.5px;color:#94A3B8">⏱ ${ageMins}m</span>`;
      const stagnantBadge = p.is_stagnant 
        ? `<span class="b" style="font-size:9.5px;background:rgba(245,158,11,0.2);color:#FBBF24;border:1px solid #F59E0B;font-weight:700">⏳ STAGNANT (${ageMins}m)</span>` 
        : '';

      const t1Badge = p.t1_hit 
        ? '<span class="b" style="font-size:10px;background:rgba(16,185,129,0.2);color:#10B981;border:1px solid #10B981;font-weight:700">✓ TP1 HIT (50% SECURED)</span>' 
        : `<span class="b b-d" style="font-size:9.5px">⏳ TP1 Pending (${p.target_1.toFixed(p.entry_price<1?6:2)})</span>`;
      const defBadge = p.defensive_active 
        ? '<span class="b" style="font-size:10px;background:rgba(56,189,248,0.2);color:#38BDF8;border:1px solid #38BDF8;font-weight:600">🛡️ FEE-COVERED BE ARMED</span>' 
        : `<span class="b b-q" style="font-size:9.5px">🛑 HARD STOP (${p.current_stop.toFixed(p.entry_price<1?6:2)})</span>`;

      const feeCoverPrice = p.entry_price * (isLong ? 1.0011 : 0.9989);

      return `
        <div style="background:#0F172A;border:1px solid var(--bdr);border-left:4px solid ${isLong?'#10B981':'#F43F5E'};border-radius:10px;padding:14px;display:flex;flex-direction:column;gap:10px">
          <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px">
            <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
              <b style="font-size:15px;color:#F8FAFC">${p.symbol}</b>
              <span class="b ${sideClass}">${p.direction}</span>
              <span class="b b-d" style="font-size:9.5px">${p.engine}</span>
              ${ageBadge}
              ${stagnantBadge}
              ${t1Badge}
              ${defBadge}
            </div>
            <div style="display:flex;align-items:center;gap:12px">
              <div style="text-align:right">
                <div style="font-size:14px;font-weight:700;${pnlColor}">${pnlSign}$${p.unrealized_pnl.toFixed(2)} (${pnlSign}${p.unrealized_r}R)</div>
                <div style="font-size:10px;color:var(--tx3)">Size: ${p.quantity}</div>
              </div>
              <button class="btn btn-x" onclick="cryptoClosePos('${p.position_id}')" style="padding:4px 10px;font-size:10px">✕ Close</button>
            </div>
          </div>

          <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:8px;background:#090D15;padding:10px 12px;border-radius:8px;font-family:'JetBrains Mono',monospace;font-size:11px">
            <div><span style="color:var(--tx3)">Entry Price:</span> <b style="color:#F8FAFC">$${p.entry_price.toFixed(p.entry_price<1?6:2)}</b></div>
            <div><span style="color:var(--tx2)">Dynamic Mark Price:</span> <b style="color:${markColor}">$${markVal.toFixed(p.entry_price<1?6:2)} ${markArrow}</b></div>
            <div><span style="color:#64748B">Fee-Cover BE:</span> <b style="color:#94A3B8">$${feeCoverPrice.toFixed(p.entry_price<1?6:2)}</b></div>
            <div><span style="color:var(--rd)">Hard Stop (SL):</span> <b style="color:#F43F5E">$${p.current_stop.toFixed(p.entry_price<1?6:2)}</b></div>
            <div><span style="color:var(--cy)">Target 1:</span> <b style="color:#38BDF8">$${p.target_1.toFixed(p.entry_price<1?6:2)}</b> ${p.t1_hit ? '<span style="color:#10B981;font-weight:800">✓ DONE</span>' : ''}</div>
            <div><span style="color:var(--gr)">Target 2:</span> <b style="color:#34D399">$${p.target_2.toFixed(p.entry_price<1?6:2)}</b></div>
          </div>
        </div>
      `;
    }).join('');
  }

  // 4. Opportunity Analysis List
  const anaList = $('cryptoAnalysisList');
  if (!d.latest_analyses || !d.latest_analyses.length) {
    anaList.innerHTML = '<div class="empty">Analyzing market structure across Top 12 Prime coins...</div>';
  } else {
    anaList.innerHTML = d.latest_analyses.map(a => {
      const isLong = a.direction === 'LONG';
      const sideClass = isLong ? 'b-l' : 'b-s';
      return `
        <div style="background:#090D15;border:1px solid var(--bdr);border-radius:8px;padding:12px;display:flex;flex-direction:column;gap:6px">
          <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px">
            <div style="display:flex;gap:8px;align-items:center">
              <b style="color:#F8FAFC">${a.symbol}</b>
              <span class="b ${sideClass}">${a.direction}</span>
              <span class="b b-d">${a.engine}</span>
              <span class="b b-p" style="font-size:9.5px">Confidence: ${(a.confidence_score*100).toFixed(0)}%</span>
            </div>
            <div style="font-size:11px;font-family:'JetBrains Mono',monospace;color:var(--tx2)">
              SL: $${a.stop_loss.toFixed(a.current_price<1?6:2)} | TP1: $${a.target_1.toFixed(a.current_price<1?6:2)} | TP2: $${a.target_2.toFixed(a.current_price<1?6:2)}
            </div>
          </div>
          <div style="font-size:11.5px;color:#94A3B8;line-height:1.4">
            <b>Why Opportunity Exists:</b> ${a.reason}
          </div>
        </div>
      `;
    }).join('');
  }

  // 5. Which Coins Picked and Why (Focus Cards)
  const focusWrap = $('cryptoFocusCards');
  const focusPicks = (d.screener_candidates || []).filter(c => c.is_active_focus);
  if (focusWrap) {
    if (!focusPicks.length) {
      focusWrap.innerHTML = '<div class="empty">No focus coins flagged yet. Run Screener.</div>';
    } else {
      focusWrap.innerHTML = focusPicks.map(c => {
        const isPos = c.change_24h >= 0;
        const chgClass = isPos ? 'g' : 'r';
        const chgSign = isPos ? '+' : '';
        const sectorColor = c.sector === 'MEME' ? 'rgba(236,72,153,.2);color:#F472B6;border:1px solid rgba(236,72,153,.4)' : 'rgba(99,102,241,.2);color:#A5B4FC;border:1px solid rgba(99,102,241,.4)';

        return `
          <div style="background:#0F172A;border:1px solid var(--bdr);border-radius:10px;padding:12px;display:flex;flex-direction:column;gap:8px">
            <div style="display:flex;justify-content:space-between;align-items:center">
              <div style="display:flex;align-items:center;gap:6px">
                <b style="font-size:14px;color:#F8FAFC">${c.symbol}</b>
                <span class="b" style="${sectorColor};font-size:9px">${c.sector}</span>
              </div>
              <span class="b b-p" style="font-size:9.5px">Score: ${c.score}</span>
            </div>
            <div style="display:flex;justify-content:space-between;font-size:11px;font-family:'JetBrains Mono',monospace">
              <span>Price: <b>$${c.price.toFixed(c.price<1?6:2)}</b></span>
              <span class="${chgClass}">24h: <b>${chgSign}${c.change_24h}%</b></span>
              <span style="color:var(--tx2)">Vol: $${(c.volume_24h/1000000).toFixed(1)}M</span>
            </div>
            <div style="font-size:11px;color:#CBD5E1;background:#090D15;padding:8px;border-radius:6px;border:1px solid rgba(255,255,255,.04);line-height:1.4">
              <span style="color:var(--am);font-weight:700">WHY PICKED:</span> ${c.why_picked}
            </div>
          </div>
        `;
      }).join('');
    }
  }

  // 6. Screener Table
  cryptoFilterTable();

  // 7. Recent Closed Trades Table
  const trTb = $('cryptoTradesTb');
  if (trTb) {
    if (!d.closed_trades || !d.closed_trades.length) {
      trTb.innerHTML = '<tr><td colspan="10" class="empty">No closed trades yet.</td></tr>';
    } else {
      trTb.innerHTML = d.closed_trades.map(t => {
        const isLong = t.direction === 'LONG';
        const exitP = t.exit_price || t.entry_price;
        const grossPnl = ((exitP - t.entry_price) * (isLong ? 1 : -1)) * (t.quantity || 1);
        const fee = (t.fees_paid !== undefined && t.fees_paid > 0) ? t.fees_paid : ((t.quantity || 1) * t.entry_price * 0.0010);
        const netPnl = grossPnl - fee;
        const grossColor = grossPnl >= 0 ? 'g' : 'r';
        const grossSign = grossPnl >= 0 ? '+' : '';
        const netColor = netPnl >= 0 ? 'g' : 'r';
        const netSign = netPnl >= 0 ? '+' : '';
        const dateStr = new Date(t.exit_time * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
        return `
          <tr>
            <td>${dateStr}</td>
            <td><b>${t.symbol}</b></td>
            <td>${t.engine}</td>
            <td><span class="b ${isLong?'b-l':'b-s'}">${t.direction}</span></td>
            <td>$${t.entry_price.toFixed(t.entry_price<1?6:2)} ➔ $${t.exit_price ? t.exit_price.toFixed(t.entry_price<1?6:2) : '--'}</td>
            <td class="${grossColor}"><b>${grossSign}$${grossPnl.toFixed(2)}</b></td>
            <td style="color:#EF4444;font-family:'JetBrains Mono',monospace">-$${fee.toFixed(2)}</td>
            <td class="${netColor}"><b>${netSign}$${netPnl.toFixed(2)}</b></td>
            <td class="${grossColor}"><b>${grossSign}${t.unrealized_r}R</b></td>
            <td><span class="b b-p">${escHtml(t.exit_reason || 'CLOSED')}</span></td>
          </tr>
        `;
      }).join('');
    }
  }

  // 7b. AI Asset Intelligence & Behavioral Memory Table
  const intelTb = $('cryptoIntelligenceTb');
  if (intelTb) {
    if (!d.coin_intelligence || !d.coin_intelligence.length) {
      intelTb.innerHTML = '<tr><td colspan="8" class="empty">No intelligence metrics yet.</td></tr>';
    } else {
      intelTb.innerHTML = d.coin_intelligence.map(c => {
        const isQuar = c.is_quarantined;
        const statusBadge = isQuar 
          ? `<span class="b" style="background:#7F1D1D;color:#FCA5A5;border:1px solid #EF4444">🔴 QUARANTINED (${c.quarantine_remaining_hours}h)</span>`
          : (c.is_prime ? `<span class="b" style="background:#064E3B;color:#6EE7B7;border:1px solid #10B981">🟢 PRIME (ACTIVE)</span>` : `<span class="b b-d">⚪ ALTCOIN</span>`);
        const winColor = c.win_rate >= 50 ? 'g' : (c.total_trades > 0 ? 'r' : 'dim');
        const netColor = c.net_pnl > 0 ? 'g' : (c.net_pnl < 0 ? 'r' : 'dim');
        const netSign = c.net_pnl > 0 ? '+' : '';
        const grossColor = c.gross_pnl > 0 ? 'g' : (c.gross_pnl < 0 ? 'r' : 'dim');
        const grossSign = c.gross_pnl > 0 ? '+' : '';
        return `
          <tr style="${isQuar ? 'opacity:0.85;background:rgba(239,68,68,0.06)' : ''}">
            <td>${statusBadge}</td>
            <td><b>${c.symbol}</b></td>
            <td class="${winColor}"><b>${c.total_trades > 0 ? c.win_rate + '%' : '--'}</b></td>
            <td>${c.total_trades} (${c.wins}W / ${c.losses}L)</td>
            <td class="${grossColor}"><b>${grossSign}$${c.gross_pnl.toFixed(2)}</b></td>
            <td style="color:#EF4444;font-family:'JetBrains Mono',monospace">-$${c.total_fees.toFixed(2)}</td>
            <td class="${netColor}"><b>${netSign}$${c.net_pnl.toFixed(2)}</b></td>
            <td style="font-size:11px;color:${isQuar?'#FCA5A5':'var(--t2)'}">${escHtml(c.debrief)}</td>
          </tr>
        `;
      }).join('');
    }
  }

  // 8. Bot Activity Stream
  const actList = $('cryptoActivityList');
  if (actList) {
    if (!d.activity_logs || !d.activity_logs.length) {
      actList.innerHTML = '<div class="empty">Awaiting activity logs...</div>';
    } else {
      actList.innerHTML = d.activity_logs.map(l => {
        const timeStr = new Date(l.timestamp * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
        let badgeClass = 'b-d';
        let borderLeftColor = '#64748B';
        if (l.level === 'SUCCESS') { badgeClass = 'b-p'; borderLeftColor = '#10B981'; }
        else if (l.level === 'WARNING') { badgeClass = 'b-q'; borderLeftColor = '#F59E0B'; }
        else if (l.level === 'DANGER') { badgeClass = 'b-x'; borderLeftColor = '#EF4444'; }
        else if (l.level === 'INFO') { badgeClass = 'b-d'; borderLeftColor = '#38BDF8'; }

        return `
          <div style="background:#0D131F;border:1px solid var(--bdr);border-left:3px solid ${borderLeftColor};border-radius:6px;padding:8px 10px;line-height:1.4">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
              <span class="b ${badgeClass}" style="font-size:9px">${escHtml(l.action)}</span>
              <span style="color:var(--tx3);font-size:9.5px;font-family:'JetBrains Mono',monospace">${timeStr}</span>
            </div>
            <div style="color:#E2E8F0;word-break:break-word;font-size:11px">
              <b style="color:var(--am)">[${escHtml(l.coin)}]</b> ${escHtml(l.detail)}
            </div>
          </div>
        `;
      }).join('');
    }
  }
}

function cryptoFilterTable() {
  const q = ($('cryptoSearch') ? $('cryptoSearch').value : '').toUpperCase();
  const tb = $('cryptoScreenerTb');
  if (!tb) return;
  const filtered = allCryptoScreener.filter(c => c.symbol.includes(q) || c.sector.includes(q) || c.name.toUpperCase().includes(q));
  if (!filtered.length) {
    tb.innerHTML = '<tr><td colspan="7" class="empty">No matching coins in universe.</td></tr>';
    return;
  }
  tb.innerHTML = filtered.map(c => {
    const isPos = c.change_24h >= 0;
    const chgClass = isPos ? 'g' : 'r';
    const chgSign = isPos ? '+' : '';
    const focusTag = c.is_active_focus ? '<span class="b b-p" style="font-size:8.5px;margin-left:4px">ACTIVE FOCUS</span>' : '';
    return `
      <tr>
        <td><b>${c.symbol}</b>${focusTag}</td>
        <td><span class="b b-d" style="font-size:9.5px">${c.sector}</span></td>
        <td>$${c.price.toFixed(c.price<1?6:2)}</td>
        <td class="${chgClass}"><b>${chgSign}${c.change_24h}%</b></td>
        <td>$${(c.volume_24h/1000000).toFixed(1)}M</td>
        <td><b>${c.score}</b></td>
        <td style="color:#CBD5E1;font-size:11px">${c.why_picked}</td>
      </tr>
    `;
  }).join('');
}

async function cryptoToggle() {
  await fetch(cryptoRunning ? '/api/crypto/stop' : '/api/crypto/start', { method: 'POST' });
  setTimeout(loadCryptoState, 200);
}
async function cryptoScan() {
  await fetch('/api/crypto/scan', { method: 'POST' });
  setTimeout(loadCryptoState, 400);
}
async function cryptoFlatten() {
  if (confirm('Flatten ALL open crypto positions?')) {
    await fetch('/api/crypto/flatten', { method: 'POST' });
    setTimeout(loadCryptoState, 200);
  }
}
async function cryptoClosePos(id) {
  if (confirm('Close position ' + id + '?')) {
    await fetch('/api/crypto/close', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id })
    });
    setTimeout(loadCryptoState, 200);
  }
}
async function cryptoReset() {
  if (confirm('Reset Crypto Sentinel state to $1,000?')) {
    await fetch('/api/crypto/reset', { method: 'POST' });
    setTimeout(loadCryptoState, 200);
  }
}
async function cryptoChangeMode(mode) {
  await fetch('/api/crypto/mode', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mode })
  });
  setTimeout(loadCryptoState, 200);
}

async function cryptoChangeProfile(profile) {
  await fetch('/api/crypto/profile', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ profile })
  });
  setTimeout(loadCryptoState, 200);
}

async function loadPolymarketState() {
  try {
    const res = await fetch('/api/polymarket/state');
    const d = await res.json();
    renderPolymarket(d);
  } catch (e) {}
}

function formatEndDate(isoStr) {
  if (!isoStr) return 'Date TBD';
  try {
    const d = new Date(isoStr);
    if (isNaN(d.getTime())) return isoStr;
    const now = new Date();
    const diffMs = d.getTime() - now.getTime();
    const diffDays = Math.ceil(diffMs / (1000 * 60 * 60 * 24));
    const dateFormatted = d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    if (diffDays > 0) {
      const daysText = diffDays === 1 ? 'closes tomorrow' : `in ${diffDays}d`;
      return `${dateFormatted} (${daysText})`;
    } else if (diffDays === 0) {
      return `${dateFormatted} (closes today)`;
    } else {
      return `${dateFormatted} (closed)`;
    }
  } catch (e) {
    return isoStr;
  }
}

// ── Polymarket Multi-Timeframe Timeline Engine ────────────────────────
function selectPolyTimelineCoin(coin) {
  polyCurrentCoin = coin;
  ['BTC', 'ETH', 'SOL', 'XRP'].forEach(c => {
    const btn = $('polyCoinTab_' + c);
    if (btn) btn.className = (c === coin) ? 'poly-coin-tab-btn active' : 'poly-coin-tab-btn';
  });
  fetchPolyTimeline(polyCurrentCoin, polyCurrentTf);
}

function selectPolyTimelineTf(tf) {
  polyCurrentTf = tf;
  ['5m', '15m', '1h'].forEach(t => {
    const btn = $('polyTfBtn_' + t);
    if (btn) btn.className = (t === tf) ? 'poly-tf-btn active' : 'poly-tf-btn';
  });
  fetchPolyTimeline(polyCurrentCoin, polyCurrentTf);
}

function fetchPolyTimeline(coin, tf) {
  const url = `/api/polymarket/crypto/timeline?coin=${encodeURIComponent(coin)}&tf=${encodeURIComponent(tf)}`;
  fetch(url)
    .then(r => r.json())
    .then(data => {
      polyTimelineCache[`${coin}_${tf}`] = data;
      renderPolyTimeline(data);
    })
    .catch(err => console.error("Error fetching timeline:", err));
}

function renderPolyTimeline(tl) {
  if (!tl) return;
  const coin = tl.coin || polyCurrentCoin;
  const tf = tl.timeframe || polyCurrentTf;
  const coinIcons = {'BTC':'🟠','ETH':'🔷','SOL':'🟣','XRP':'⚪'};
  const icon = coinIcons[coin] || '🪙';
  const dec = coin === 'XRP' ? 4 : 2;

  // 1. Update Title & Header
  if ($('polyTimelineCoinIcon')) $('polyTimelineCoinIcon').innerText = icon;
  if ($('polyTimelineTitle')) $('polyTimelineTitle').innerText = `${coin} Up or Down ${tf}`;
  
  const act = tl.active_round || {};
  if ($('polyTimelineWindow')) {
    const winStr = act.time_window_et ? `${act.time_window_et} · ${act.time_window_utc}` : `${tf.toUpperCase()} Fast-Expiry Round`;
    $('polyTimelineWindow').innerText = winStr;
  }

  // 2. Price to Beat (Strike) & Spot
  const cDataForPtb = (window._lastPolyData && window._lastPolyData.btc_5m && window._lastPolyData.btc_5m.coins) ? window._lastPolyData.btc_5m.coins[coin] : null;
  if ($('polyTimelinePtb')) {
    const ptbVal = (act.price_to_beat !== undefined && act.price_to_beat !== null) ? act.price_to_beat : (cDataForPtb ? cDataForPtb.strike_price : null);
    if (ptbVal !== undefined && ptbVal !== null && ptbVal > 0) {
      $('polyTimelinePtb').innerText = '$' + ptbVal.toLocaleString('en-US', {minimumFractionDigits: dec, maximumFractionDigits: dec});
    } else {
      $('polyTimelinePtb').innerText = 'Strike Locking...';
    }
  }

  // Current Spot from live matrix
  if ($('polyTimelineSpot') && window._lastPolyData && window._lastPolyData.btc_5m && window._lastPolyData.btc_5m.coins) {
    const cData = window._lastPolyData.btc_5m.coins[coin];
    if (cData && cData.spot_price) {
      const sp = cData.spot_price;
      const ptb = (act.price_to_beat !== undefined && act.price_to_beat !== null) ? act.price_to_beat : (cData.strike_price || sp);
      const diff = sp - ptb;
      const diffSign = diff >= 0 ? '+' : '';
      const diffColor = diff >= 0 ? 'var(--gr)' : 'var(--rd)';
      $('polyTimelineSpot').innerHTML = `$${sp.toLocaleString('en-US', {minimumFractionDigits: dec, maximumFractionDigits: dec})} <span style="font-size:11px;color:${diffColor}">(${diffSign}$${diff.toFixed(dec)})</span>`;
    }
  }

  // 3. Slug and Direct Links
  if ($('poly5mRoundId')) {
    $('poly5mRoundId').innerText = act.slug || `${coin.toLowerCase()}-updown-${tf}`;
  }
  if ($('polyTimelineDirectLink')) {
    $('polyTimelineDirectLink').href = act.polymarket_url || `https://polymarket.com/event/${act.slug}`;
  }
  if ($('poly5mOrderbookBadge')) {
    if (act.closed) {
      $('poly5mOrderbookBadge').innerText = '🔴 Round Closed';
      $('poly5mOrderbookBadge').style.background = 'rgba(239,68,68,.15)';
      $('poly5mOrderbookBadge').style.color = '#F87171';
    } else if (act.accepting_orders) {
      $('poly5mOrderbookBadge').innerText = '🟢 Accepting Orders';
      $('poly5mOrderbookBadge').style.background = 'rgba(16,185,129,.15)';
      $('poly5mOrderbookBadge').style.color = 'var(--gr)';
    } else {
      $('poly5mOrderbookBadge').innerText = '🟡 Pending Orders';
      $('poly5mOrderbookBadge').style.background = 'rgba(245,158,11,.15)';
      $('poly5mOrderbookBadge').style.color = '#FBBF24';
    }
  }

  // 4. Polymarket Horizon Ribbon Bar (Exact Replica of Polymarket UI)
  const ribbon = $('polyTimelineRibbon');
  if (ribbon) {
    let html = '';

    // Past rounds expander / outcome pills
    html += `
      <div style="display:inline-flex;align-items:center;gap:5px;border-right:1px solid rgba(255,255,255,.1);padding-right:8px;margin-right:4px">
        <span class="poly-pill-past-btn" title="Resolved rounds on Polymarket">Past ▾</span>
    `;

    (tl.past_rounds || []).forEach(p => {
      const isUp = (p.outcome === 'UP');
      const cls = isUp ? 'up' : 'down';
      const arrow = isUp ? '▲' : '▼';
      const label = `${p.label} - ${p.outcome}${p.price_to_beat ? ' ($' + p.price_to_beat + ')' : ''}`;
      html += `
        <a href="${p.polymarket_url}" target="_blank" rel="noopener noreferrer" class="poly-pill-outcome ${cls}" title="${label}">
          ${arrow}
        </a>
      `;
    });
    html += `</div>`;

    // Active round pill (with pulsating live indicator)
    const actLabel = act.label || 'Active';
    html += `
      <a href="${act.polymarket_url}" target="_blank" rel="noopener noreferrer" class="poly-pill-active" title="Active Round: Closes in ${act.closes_in}">
        <span class="poly-pulse-dot" style="width:8px;height:8px;background:#38BDF8;box-shadow:0 0 8px #38BDF8"></span>
        <span>${actLabel}</span>
        <span style="font-size:10px;color:#A5B4FC;background:rgba(255,255,255,.08);padding:1px 6px;border-radius:10px" id="polyPillActiveTimer">${act.closes_in || 'Live'}</span>
      </a>
    `;

    // Upcoming rounds pills
    (tl.upcoming_rounds || []).forEach(u => {
      html += `
        <a href="${u.polymarket_url}" target="_blank" rel="noopener noreferrer" class="poly-pill-upcoming" title="Starts ${u.status} (${u.time_window_et})">
          <span>${u.label}</span>
          <span style="font-size:9.5px;color:var(--tx3)">(${u.status})</span>
        </a>
      `;
    });

    ribbon.innerHTML = html;
  }

  // 5. Upcoming Rounds Grid Cards
  const upGrid = $('poly5mUpcomingGrid');
  if (upGrid && tl.upcoming_rounds) {
    if ($('polyUpcomingHeaderLabel')) {
      $('polyUpcomingHeaderLabel').innerText = `🗓️ Polymarket API Schedule · Next Upcoming ${tf.toUpperCase()} Rounds (24/7 Aligned):`;
    }
    upGrid.innerHTML = tl.upcoming_rounds.map((u, idx) => {
      const intervalNum = parseInt(tf) || 5;
      const unit = tf.slice(-1).toUpperCase();
      return `
        <div style="background:rgba(0,0,0,.35);border:1px solid rgba(255,255,255,.07);border-radius:8px;padding:10px;display:flex;flex-direction:column;gap:6px">
          <div style="display:flex;justify-content:space-between;align-items:center">
            <span style="font-size:11px;font-weight:800;color:#38BDF8">
              ${idx === 0 ? `⏭ NEXT ROUND (+${tf.toUpperCase()})` : `ROUND +${(idx+1)*intervalNum}${unit}`}
            </span>
            <span class="b b-p" style="font-size:9.5px;padding:2px 7px">${u.status || 'SCHEDULED'}</span>
          </div>
          <div style="display:flex;justify-content:space-between;align-items:center;font-size:11px">
            <span style="color:var(--tx3)">Time Window (ET):</span>
            <span style="color:#A5B4FC;font-family:'JetBrains Mono',monospace;font-weight:700">${u.time_window_et}</span>
          </div>
          <div style="display:flex;justify-content:space-between;align-items:center;font-size:10.5px">
            <span style="color:var(--tx3)">Time Window (UTC):</span>
            <span style="color:var(--tx2);font-family:'JetBrains Mono',monospace">${u.time_window_utc}</span>
          </div>
          <div style="border-top:1px dashed rgba(255,255,255,.07);padding-top:5px;margin-top:2px;display:flex;justify-content:space-between;align-items:center">
            <span style="font-size:9.5px;color:var(--tx3)">Direct Contract:</span>
            <a href="${u.polymarket_url}" target="_blank" rel="noopener noreferrer" style="font-size:10px;color:#38BDF8;text-decoration:none;font-weight:600">Open on Polymarket ↗</a>
          </div>
          <!-- Clickable & Underlined 4-Coin Projected Strikes -->
          <div style="border-top:1px dashed rgba(255,255,255,.07);padding-top:4px;margin-top:2px">
            <div style="font-size:9.5px;color:var(--tx3);margin-bottom:3px;font-weight:700">Projected Strikes (Click to Open Round):</div>
            <div style="display:flex;flex-wrap:wrap;gap:5px">
              ${['BTC', 'ETH', 'SOL', 'XRP'].map(sym => {
                const dec = sym === 'XRP' ? 4 : 2;
                const cData = (window._lastPolyData && window._lastPolyData.btc_5m && window._lastPolyData.btc_5m.coins) ? window._lastPolyData.btc_5m.coins[sym] : null;
                const px = cData ? (cData.spot_price || cData.current_price || 0) : 0;
                const cSlug = `${sym.toLowerCase()}-updown-${tf}-${u.timestamp}`;
                const cUrl = `https://polymarket.com/event/${cSlug}`;
                return `
                  <a href="${cUrl}" target="_blank" rel="noopener noreferrer" style="font-size:9.5px;color:#38BDF8;text-decoration:underline;text-underline-offset:2px;font-family:'JetBrains Mono',monospace;font-weight:700;display:inline-flex;align-items:center;gap:3px;background:rgba(255,255,255,.04);padding:2px 6px;border-radius:4px;border:1px solid rgba(255,255,255,.08);transition:all .15s" title="Open ${sym} ${tf} contract directly on Polymarket.com">
                    <span>${coinIcons[sym] || ''}${sym}: $${px.toFixed(dec)}</span>
                    <span style="font-size:8px">↗</span>
                  </a>
                `;
              }).join('')}
            </div>
          </div>
        </div>
      `;
    }).join('');
  }
}

function renderPolymarket(d) {
  if (!d) return;
  window._lastPolyData = d;
  polyRunning = !!d.running;
  const polyBtn = $('polyEngBtn');
  if (polyBtn) {
    polyBtn.innerText = polyRunning ? '⏹ Pause Auto-Pilot' : '▶ Start Auto-Pilot';
    polyBtn.className = 'btn ' + (polyRunning ? 'btn-stop' : 'btn-go');
  }
  const gatePill = $('polyGatewayPill');
  if (gatePill) {
    gatePill.innerText = polyRunning ? 'AUTO-PILOT ACTIVE' : 'STANDBY';
    gatePill.className = 'stream-pill ' + (polyRunning ? '' : 'disconnected');
  }

  // Active Working Gig Banner
  if ($('polyGigText') && d.current_gig) {
    $('polyGigText').innerText = d.current_gig;
  }
  const resBtn = $('polyResearchBtn');
  if (resBtn) {
    if (d.is_researching) {
      resBtn.innerHTML = '⏳ Researching News...';
      resBtn.style.opacity = '0.7';
    } else {
      resBtn.innerHTML = '🔬 Deep Research Cycle';
      resBtn.style.opacity = '1';
    }
  }

  // KPIs
  if (d.kpis) {
    const k = d.kpis;
    if ($('polyKpiMarkets')) $('polyKpiMarkets').innerText = k.monitored_markets || 0;
    if ($('polyKpiEquity')) $('polyKpiEquity').innerText = '$' + (k.portfolio_equity || 25).toLocaleString('en-US', {minimumFractionDigits:2, maximumFractionDigits:2});
    if ($('polyKpiCash')) $('polyKpiCash').innerText = '$' + (k.cash || 25).toLocaleString('en-US', {minimumFractionDigits:2, maximumFractionDigits:2});
    if ($('polyKpiInvested')) $('polyKpiInvested').innerText = '$' + (Math.max(0, (k.portfolio_equity - k.cash)) || 0).toLocaleString('en-US', {minimumFractionDigits:2, maximumFractionDigits:2});
    if ($('polyKpiEdgeOpp')) $('polyKpiEdgeOpp').innerText = k.opportunities || 0;
    const pnl = k.total_pnl || 0;
    const pnlEl = $('polyKpiPnl');
    if (pnlEl) {
      pnlEl.innerText = (pnl >= 0 ? '+' : '') + '$' + pnl.toFixed(2);
      pnlEl.className = 'kv ' + (pnl >= 0 ? 'g' : 'r');
    }
    if ($('polyKpiCommissions')) $('polyKpiCommissions').innerText = '$' + (k.scalper_commissions || 0).toFixed(3);
    if ($('polyKpiScalperPnl')) {
      const spnl = k.scalper_pnl || 0;
      $('polyKpiScalperPnl').innerText = (spnl >= 0 ? '+' : '') + '$' + spnl.toFixed(2);
      $('polyKpiScalperPnl').className = spnl >= 0 ? 'g' : 'r';
    }
  }

  // Markets Table & Cards
  if (d.markets) {
    allPolyMarkets = d.markets;
    filterPolyMarkets();
  }

  // Breaking News & Verified Evidence
  if (d.recent_evidence) {
    allPolyEvidence = d.recent_evidence;
    renderPolyEvidence(allPolyEvidence);
  }

  // Active Open Bets Grid (Visual Trade Slips with End Date, Strategy Badge, Dynamic TP/SL & Reason)
  window.lastPolyData = d;
  const posGrid = $('polyPositionsGrid');
  const allPos = (d.portfolio && d.portfolio.open_positions) || [];
  const pos = (typeof currentPolyBetFilter !== 'undefined' && currentPolyBetFilter !== 'ALL')
    ? allPos.filter(p => (p.strategy_type || 'ASYMMETRIC_EDGE') === currentPolyBetFilter)
    : allPos;

  if ($('polyPosCount')) $('polyPosCount').innerText = `${allPos.length} Open (${pos.length} shown)`;
  if (posGrid) {
    if (!pos.length) {
      posGrid.innerHTML = `
        <div class="empty" style="grid-column:1/-1;padding:32px 16px;text-align:center">
          <div style="font-size:26px;margin-bottom:8px">🎯</div>
          <div style="font-weight:700;color:var(--tx1);font-size:14px;margin-bottom:6px">No Active Bets Open ${currentPolyBetFilter !== 'ALL' ? 'for this Strategy' : ''}</div>
          <div style="font-size:12px;color:var(--tx2);max-width:540px;margin:0 auto;line-height:1.5">
            The AI Dual-Engine is actively scanning: <b>💎 Yield Harvester</b> (80-96¢, $75 max) and <b>🎯 Asymmetric Hunter</b> (5-65¢, $25 max) with automated Take-Profit and Stop-Loss exits.
          </div>
        </div>
      `;
    } else {
      posGrid.innerHTML = pos.map(p => {
        const pnl = p.unrealized_pnl || 0;
        const pc = pnl >= 0 ? 'var(--gr)' : 'var(--rd)';
        const sg = pnl >= 0 ? '+' : '';
        const pnlPct = p.cost_basis > 0 ? ((pnl / p.cost_basis) * 100).toFixed(1) : '0.0';
        const isYes = p.outcome === 'YES';
        const outcomeBg = isYes ? 'rgba(56,189,248,.12)' : 'rgba(244,63,94,.12)';
        const outcomeColor = isYes ? '#38BDF8' : '#F43F5E';
        const outcomeBorder = isYes ? 'rgba(56,189,248,.3)' : 'rgba(244,63,94,.3)';
        const maxPayout = (p.shares * 1.0).toFixed(2);
        const maxProfit = (p.shares * 1.0 - p.cost_basis).toFixed(2);
        const endDateStr = formatEndDate(p.end_date);
        const whyReason = p.reason || 'AI edge calculated from real-time probabilistic divergence and news sentiment.';
        
        const isYield = (p.strategy_type === 'HIGH_PROBABILITY_YIELD');
        const stratBadge = isYield 
          ? `<span style="display:inline-block;padding:2px 8px;border-radius:4px;font-size:10px;font-weight:800;letter-spacing:0.5px;background:rgba(234,179,8,.15);color:#FBBF24;border:1px solid rgba(234,179,8,.4)">💎 YIELD HARVESTER</span>`
          : `<span style="display:inline-block;padding:2px 8px;border-radius:4px;font-size:10px;font-weight:800;letter-spacing:0.5px;background:rgba(129,140,248,.15);color:#A5B4FC;border:1px solid rgba(129,140,248,.4)">🎯 ASYMMETRIC EDGE</span>`;

        const tpVal = p.take_profit_px ? Number(p.take_profit_px).toFixed(3) : null;
        const slVal = p.stop_loss_px ? Number(p.stop_loss_px).toFixed(3) : null;
        const exitTargetsHtml = (tpVal && slVal) ? `
          <div style="display:flex;justify-content:space-between;align-items:center;background:rgba(0,0,0,.25);border:1px solid rgba(255,255,255,.08);border-radius:6px;padding:6px 10px;font-size:11px;font-family:'JetBrains Mono',monospace">
            <span style="color:var(--gr)">🎯 Auto TP Target: <b>$${tpVal}</b></span>
            <span style="color:var(--rd)">🛡️ Emergency SL: <b>$${slVal}</b></span>
          </div>
        ` : '';

        return `
          <div style="background:var(--bg3);border:1px solid ${outcomeBorder};border-radius:10px;padding:16px;display:flex;flex-direction:column;gap:12px;box-shadow:0 4px 14px rgba(0,0,0,.25)">
            <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px">
              <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap">
                <span style="display:inline-block;padding:3px 9px;border-radius:6px;font-size:11px;font-weight:800;letter-spacing:0.5px;background:${outcomeBg};color:${outcomeColor};border:1px solid ${outcomeBorder}">
                  BOUGHT ${p.outcome}
                </span>
                ${stratBadge}
                <span style="font-size:11px;color:var(--tx3);background:rgba(255,255,255,.05);padding:2px 7px;border-radius:4px">${p.category || 'Prediction'}</span>
              </div>
              <div style="text-align:right">
                <div style="font-size:10.5px;color:var(--tx3);font-family:'JetBrains Mono',monospace">Unrealized P&L</div>
                <div style="font-size:15px;font-weight:800;color:${pc};font-family:'JetBrains Mono',monospace">${sg}$${pnl.toFixed(2)} (${sg}${pnlPct}%)</div>
              </div>
            </div>

            <div style="font-size:14px;font-weight:700;color:var(--tx1);line-height:1.35">${p.question || p.market_id}</div>

            <!-- Resolution / Closing Date Callout -->
            <div style="display:flex;align-items:center;gap:6px;padding:7px 10px;background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.07);border-radius:6px;font-size:11.5px">
              <span style="font-size:13px">📅</span>
              <span style="color:var(--tx2);font-weight:600">Market Closes:</span>
              <span style="color:#A5B4FC;font-weight:700;font-family:'JetBrains Mono',monospace">${endDateStr}</span>
            </div>

            <!-- Active Dynamic Exits (Auto TP & SL) -->
            ${exitTargetsHtml}

            <!-- Position Metrics Grid -->
            <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;padding:10px;background:var(--bg2);border-radius:6px;text-align:center">
              <div>
                <div style="font-size:10px;color:var(--tx3)">Shares</div>
                <div style="font-size:12px;font-weight:700;color:var(--tx1);font-family:'JetBrains Mono',monospace">${p.shares}</div>
              </div>
              <div>
                <div style="font-size:10px;color:var(--tx3)">Entry Price</div>
                <div style="font-size:12px;font-weight:700;color:var(--tx1);font-family:'JetBrains Mono',monospace">$${p.avg_entry_price.toFixed(3)}</div>
              </div>
              <div>
                <div style="font-size:10px;color:var(--tx3)">Current Price</div>
                <div style="font-size:12px;font-weight:700;color:var(--tx1);font-family:'JetBrains Mono',monospace">$${p.current_price.toFixed(3)}</div>
              </div>
              <div>
                <div style="font-size:10px;color:var(--tx3)">Total Outlay</div>
                <div style="font-size:12px;font-weight:700;color:var(--tx1);font-family:'JetBrains Mono',monospace">$${p.cost_basis.toFixed(2)}</div>
              </div>
            </div>

            <!-- Potential Payout -->
            <div style="display:flex;justify-content:space-between;align-items:center;font-size:11.5px;padding:6px 10px;background:rgba(16,185,129,.05);border:1px solid rgba(16,185,129,.15);border-radius:6px">
              <span style="color:var(--tx2)">Payout if correct ($1.00):</span>
              <span style="color:var(--gr);font-weight:700;font-family:'JetBrains Mono',monospace">$${maxPayout} (+$${maxProfit} net profit)</span>
            </div>

            <!-- Why We Bought This Callout Box -->
            <div style="background:rgba(99,102,241,.07);border:1px solid rgba(99,102,241,.2);border-radius:8px;padding:10px 12px">
              <div style="display:flex;align-items:center;gap:5px;font-size:11px;font-weight:800;color:#A5B4FC;margin-bottom:4px;letter-spacing:0.3px">
                <span>💡</span> WHY WE BOUGHT THIS:
              </div>
              <div style="font-size:12px;color:var(--tx1);line-height:1.45">${whyReason}</div>
            </div>

            <div style="display:flex;gap:8px;margin-top:auto">
              <button class="btn btn-demo" style="flex:1;justify-content:center;padding:7px;font-size:11px" onclick="openDeepDive('${p.market_id}')">
                🔬 Dossier
              </button>
              <button class="btn btn-stop" style="flex:1;justify-content:center;padding:7px;font-size:11px" onclick="polyClosePosition(${p.id}, '${p.outcome}', ${p.shares}, ${p.shares * p.current_price})">
                💰 Sell Now ($${(p.shares * p.current_price).toFixed(2)})
              </button>
            </div>
          </div>
        `;
      }).join('');
    }
  }

  // Recent Paper Trades Table
  const tradesTb = $('polyTradesTb');
  const trades = (d.portfolio && d.portfolio.recent_trades) || [];
  if (tradesTb) {
    if (!trades.length) {
      tradesTb.innerHTML = '<tr><td colspan="10" class="empty">No simulated executions yet.</td></tr>';
    } else {
      tradesTb.innerHTML = trades.map(t => {
        const isY = (t.strategy_type === 'HIGH_PROBABILITY_YIELD');
        const stratTag = isY 
          ? `<span style="color:#FBBF24;font-size:10.5px;font-weight:700">💎 YIELD</span>` 
          : `<span style="color:#A5B4FC;font-size:10.5px;font-weight:700">🎯 EDGE</span>`;
        const trig = t.exit_trigger || '';
        const trigBadge = trig === 'TAKE_PROFIT' 
          ? `<span class="b" style="background:rgba(16,185,129,.2);color:var(--gr)">🎯 TP HIT</span>`
          : (trig === 'STOP_LOSS' 
            ? `<span class="b" style="background:rgba(244,63,94,.2);color:var(--rd)">🛡️ SL HIT</span>`
            : (trig === 'MANUAL' || trig === 'MANUAL_FLATTEN'
              ? `<span class="b" style="background:rgba(234,179,8,.2);color:#FBBF24">💰 SOLD</span>`
              : (trig === 'EXPIRATION' 
                ? `<span class="b" style="background:rgba(99,102,241,.2);color:#A5B4FC">📅 SETTLED</span>`
                : `<span class="b b-p">⚡ ENTRY</span>`)));
        return `
          <tr>
            <td style="color:var(--tx3);font-family:'JetBrains Mono',monospace">${(t.timestamp || '').slice(11, 19)}</td>
            <td><span class="b b-p">${t.action}</span></td>
            <td><span class="b ${t.outcome === 'YES' ? 'b-l' : 'b-s'}">${t.outcome}</span></td>
            <td>${stratTag}</td>
            <td><b>${t.question || t.market_id}</b></td>
            <td style="color:#A5B4FC;font-family:'JetBrains Mono',monospace;font-size:11px">${formatEndDate(t.end_date)}</td>
            <td style="font-family:'JetBrains Mono',monospace">${t.shares}</td>
            <td style="font-family:'JetBrains Mono',monospace">$${t.price.toFixed(3)}</td>
            <td style="font-family:'JetBrains Mono',monospace"><b>$${t.dollar_value.toFixed(2)}</b></td>
            <td style="font-size:11px;color:var(--tx2);max-width:280px;line-height:1.3" title="${t.reason || ''}">
              <div style="margin-bottom:3px">${trigBadge}</div>
              <div>${(t.reason || 'AI edge execution').slice(0, 100)}${(t.reason && t.reason.length > 100) ? '...' : ''}</div>
            </td>
          </tr>
        `;
      }).join('');
    }
  }

  // AI Gateway stats
  if (d.gateway_stats) {
    if ($('polyAiCalls')) $('polyAiCalls').innerText = d.gateway_stats.total_calls || 0;
    if ($('polyAiLatency')) $('polyAiLatency').innerText = (d.gateway_stats.avg_latency_ms || 0) + ' ms';
  }

  // Activity list
  const actList = $('polyActivityList');
  if (actList && d.activity && d.activity.length) {
    actList.innerHTML = d.activity.map(act => `
      <div class="act-item ${act.level}">
        <div class="act-top">
          <span class="act-tag" style="background:rgba(255,255,255,.05);color:var(--tx2);">${act.category}</span>
          <span class="act-time">${act.timestamp || ''}</span>
        </div>
        <div class="act-title">${act.title}</div>
        <div class="act-desc">${act.details}</div>
      </div>
    `).join('');
  }

  // ── Render 5-Minute Multi-Crypto Microstructure Scalper (BTC, ETH, SOL, XRP) ──────
  if (d.btc_5m) {
    const s = d.btc_5m;
    if ($('poly5mBal')) $('poly5mBal').innerText = '$' + (s.balance !== undefined ? s.balance : 50).toFixed(2);
    if ($('poly5mPnl')) {
      const pnlVal = s.realized_pnl || 0;
      $('poly5mPnl').innerText = (pnlVal >= 0 ? '+' : '') + '$' + pnlVal.toFixed(2);
      $('poly5mPnl').style.color = pnlVal >= 0 ? 'var(--gr)' : 'var(--rd)';
    }
    if ($('poly5mWinRate')) $('poly5mWinRate').innerText = (s.win_rate || 0).toFixed(1) + '%';
    if ($('poly5mFees')) $('poly5mFees').innerText = '$' + (s.total_commissions_paid || 0).toFixed(3);
    if ($('poly5mRecord')) $('poly5mRecord').innerText = `${s.total_won || 0}W - ${s.total_lost || 0}L`;
    
    const toggleBtn = $('btn5mToggle');
    const statusBadge = $('poly5mStatusBadge');
    if (toggleBtn) {
      if (!s.is_enabled) {
        toggleBtn.innerText = '▶ Start 5M Scalper';
        toggleBtn.className = 'btn btn-demo';
        if (statusBadge) {
          statusBadge.innerText = '⏸ SCALPER PAUSED · CLICK BUTTON TO START';
          statusBadge.style.background = 'rgba(239,68,68,.15)';
          statusBadge.style.color = '#F87171';
        }
      } else if (s.waiting_for_next_round) {
        toggleBtn.innerText = '⏳ Armed (Wait Session)';
        toggleBtn.className = 'btn btn-g';
        if (statusBadge) {
          const targetUtc = s.target_round_ts ? new Date(s.target_round_ts * 1000).toISOString().slice(11, 16) + ' UTC' : 'Next Round';
          statusBadge.innerText = `⏳ ARMED · WAITING FOR FRESH 5M SESSION AT ${targetUtc} (SKIPPED MID-CANDLE)`;
          statusBadge.style.background = 'rgba(99,102,241,.2)';
          statusBadge.style.color = '#A5B4FC';
        }
      } else {
        toggleBtn.innerText = '⏹ Pause 5M Scalper';
        toggleBtn.className = 'btn btn-stop';
        if (statusBadge) {
          statusBadge.innerText = '🟢 BTC QUANTITATIVE SCALPER ACTIVE (SWEET SPOT 20¢ - 82¢)';
          statusBadge.style.background = 'rgba(16,185,129,.15)';
          statusBadge.style.color = 'var(--gr)';
        }
      }
    }

    const liveAccBadge = $('polyLiveAccountBadge');
    let isLiveMode = false;
    if (d.live_account) {
      const la = d.live_account;
      isLiveMode = (la.live_enabled || la.trading_mode === 'LIVE');
      
      // Update Mode Buttons
      const btnPaper = $('btnPolyModePaper');
      const btnLive = $('btnPolyModeLive');
      if (btnPaper && btnLive) {
        if (isLiveMode) {
          btnLive.style.background = 'rgba(239,68,68,.3)';
          btnLive.style.color = '#F87171';
          btnPaper.style.background = 'transparent';
          btnPaper.style.color = 'var(--tx3)';
        } else {
          btnPaper.style.background = 'rgba(99,102,241,.3)';
          btnPaper.style.color = '#A5B4FC';
          btnLive.style.background = 'transparent';
          btnLive.style.color = 'var(--tx3)';
        }
      }

      if (liveAccBadge) {
        if (la.connected) {
          const addrStr = la.wallet_address ? la.wallet_address.slice(0, 6) + '...' + la.wallet_address.slice(-4) : 'Connected';
          const balStr = (la.usdc_balance || 0).toFixed(2);
          const modeStr = isLiveMode ? '🔴 LIVE REAL TRADING' : '🟡 PAPER (Wallet Linked)';
          liveAccBadge.innerText = `${modeStr} · ${addrStr} ($${balStr} USDC.e)`;
          liveAccBadge.style.background = isLiveMode ? 'rgba(239,68,68,.15)' : 'rgba(245,158,11,.15)';
          liveAccBadge.style.color = isLiveMode ? '#F87171' : '#FBBF24';
        } else {
          liveAccBadge.innerText = '📝 Paper Simulation Mode';
          liveAccBadge.style.background = 'rgba(255,255,255,.06)';
          liveAccBadge.style.color = 'var(--tx3)';
        }
      }

      if (isLiveMode && $('poly5mBal') && la.connected) {
        $('poly5mBal').innerText = '$' + (la.usdc_balance || 0).toFixed(2) + ' (USDC.e)';
      }
    }

    const r = s.round;
    if (r) {
      const sigBadge = $('poly5mSignalBadge');
      if (sigBadge) {
        sigBadge.innerText = (r.signal !== 'ABSTAIN' ? `${r.signal} ON ${r.symbol}` : 'ABSTAIN');
        sigBadge.className = 'b ' + (r.signal === 'BUY_UP' ? 'b-l' : (r.signal === 'BUY_DOWN' ? 'b-s' : 'b-p'));
      }
      if ($('poly5mPatternBadge')) $('poly5mPatternBadge').innerText = `${r.symbol}: ${r.ict_fvg_status || 'NEUTRAL'}`;
      if ($('poly5mReason')) $('poly5mReason').innerText = r.signal_reason || '';
    }

    // Render Next 5M Session Predictions (BTC Only)
    const predGrid = $('poly5mPredictionsGrid');
    const predCountdown = $('polyPredCountdown');
    if (predGrid && s.predictions) {
      const predCoins = ['BTC'];
      let cdSec = 0;
      predGrid.innerHTML = predCoins.map(sym => {
        const p = s.predictions[sym] || {};
        const dir = p.prediction || 'NEUTRAL';
        const conf = p.confidence || 50;
        const cat = p.catalyst || 'Analyzing price action...';
        if (p.seconds_until_next_round) cdSec = p.seconds_until_next_round;

        let dirColor = '#94A3B8';
        let dirBg = 'rgba(255,255,255,.05)';
        let dirIcon = '⚪';
        if (dir === 'UP') {
          dirColor = '#34D399';
          dirBg = 'rgba(16,185,129,.15)';
          dirIcon = '🟢';
        } else if (dir === 'DOWN') {
          dirColor = '#F87171';
          dirBg = 'rgba(239,68,68,.15)';
          dirIcon = '🔴';
        }

        return `
          <div style="background:rgba(0,0,0,.3);border:1px solid rgba(255,255,255,.08);border-radius:6px;padding:8px 10px;display:flex;flex-direction:column;gap:5px">
            <div style="display:flex;justify-content:space-between;align-items:center">
              <span style="font-size:12px;font-weight:800;color:#F8FAFC">${sym}</span>
              <span style="font-size:10.5px;font-weight:700;color:${dirColor};background:${dirBg};padding:2px 7px;border-radius:4px;display:inline-flex;align-items:center;gap:4px">
                ${dirIcon} ${dir}
              </span>
            </div>
            <div style="display:flex;justify-content:space-between;align-items:center;font-size:10px;color:var(--tx3)">
              <span>AI Confidence:</span>
              <span style="font-weight:700;color:#F8FAFC">${conf.toFixed(0)}%</span>
            </div>
            <div style="width:100%;height:4px;background:rgba(255,255,255,.08);border-radius:2px;overflow:hidden">
              <div style="width:${conf}%;height:100%;background:${dir === 'UP' ? '#10B981' : (dir === 'DOWN' ? '#EF4444' : '#6366F1')};border-radius:2px"></div>
            </div>
            <div style="font-size:9.5px;color:#94A3B8;line-height:1.3;margin-top:2px" title="${cat}">
              ${cat.length > 55 ? cat.slice(0, 52) + '...' : cat}
            </div>
          </div>
        `;
      }).join('');

      if (predCountdown && cdSec > 0) {
        const m = Math.floor(cdSec / 60);
        const sec = cdSec % 60;
        predCountdown.innerText = `Next Round Starting in ${m.toString().padStart(2, '0')}:${sec.toString().padStart(2, '0')}`;
      }
    }

    // Render Polymarket Multi-Timeframe Timeline Ribbon & Upcoming Rounds
    if (s.timeline) {
      const tCoin = s.timeline.coin || 'BTC';
      const tTf = s.timeline.timeframe || '5m';
      polyTimelineCache[`${tCoin}_${tTf}`] = s.timeline;
    }

    const currentKey = `${polyCurrentCoin}_${polyCurrentTf}`;
    if (polyTimelineCache[currentKey]) {
      renderPolyTimeline(polyTimelineCache[currentKey]);
    } else {
      fetchPolyTimeline(polyCurrentCoin, polyCurrentTf);
    }

    // Render 4-Coin Parallel Live Contract Slugs in Header
    const activeBar = $('polyActiveCoinsBar');
    if (activeBar && s.coins) {
      const coinIcons = {'BTC':'🟠','ETH':'🔷','SOL':'🟣','XRP':'⚪'};
      activeBar.innerHTML = Object.keys(s.coins).map(sym => {
        const c = s.coins[sym];
        const isFocus = (sym === polyCurrentCoin);
        const slug = c.slug || c.round_id || `${sym.toLowerCase()}-updown-5m`;
        const polyUrl = c.polymarket_url || `https://polymarket.com/event/${slug}`;
        const borderCol = isFocus ? 'rgba(56,189,248,.6)' : 'rgba(255,255,255,.1)';
        const bgCol = isFocus ? 'rgba(56,189,248,.15)' : 'rgba(0,0,0,.3)';
        return `
          <div style="background:${bgCol};border:1px solid ${borderCol};border-radius:6px;padding:3px 8px;display:inline-flex;align-items:center;gap:6px">
            <span style="font-size:12px">${coinIcons[sym] || ''}</span>
            <span style="font-size:11px;font-weight:800;color:var(--tx1)">${sym}:</span>
            <a href="${polyUrl}" target="_blank" rel="noopener noreferrer" style="font-size:10.5px;color:#38BDF8;font-family:'JetBrains Mono',monospace;text-decoration:underline;text-underline-offset:2px;font-weight:700" title="Verify ${sym} active contract live on Polymarket.com">
              ${slug} ↗
            </a>
          </div>
        `;
      }).join('');
    }

    // Render BTC Live Terminal Card
    const coinsGrid = $('poly5mCoinsGrid');
    if (coinsGrid && s.coins) {
      const coinIcons = {'BTC':'🟠','ETH':'🔷','SOL':'🟣','XRP':'⚪'};
      const bestSym = 'BTC';
      const cStats = s.coin_stats || {};

      coinsGrid.innerHTML = Object.keys(s.coins).filter(sym => sym === 'BTC').map(sym => {
        const c = s.coins[sym];
        const isBest = (sym === bestSym);
        const decDigits = sym === 'XRP' ? 4 : 2;
        const deltaVal = c.price_delta || 0;
        const deltaColor = deltaVal >= 0 ? 'var(--gr)' : 'var(--rd)';
        const deltaStr = (deltaVal >= 0 ? '+' : '') + '$' + deltaVal.toFixed(decDigits);
        
        const spotPx = c.spot_price || c.current_price || 0;
        const twapPx = c.twap_price || c.current_price || 0;
        const lagVal = c.oracle_lag_delta || (spotPx - twapPx);
        const lagColor = lagVal > 0 ? 'var(--gr)' : (lagVal < 0 ? 'var(--rd)' : 'var(--tx3)');
        const lagDir = lagVal > 0 ? '▲ Spot Leading Up' : (lagVal < 0 ? '▼ Spot Leading Down' : '● In Sync');
        const projTwap = c.projected_twap || twapPx;

        const stat = cStats[sym] || { trades: 0, wins: 0, losses: 0, pnl: 0, commissions_paid: 0 };
        const statPnlColor = stat.pnl >= 0 ? 'var(--gr)' : 'var(--rd)';

        const edgeUp = ((c.calculated_prob_up - c.market_price_up) * 100).toFixed(1);
        const edgeDown = ((c.calculated_prob_down - c.market_price_down) * 100).toFixed(1);
        const borderStyle = isBest ? 'border:1.5px solid #FBBF24;box-shadow:0 0 12px rgba(245,158,11,.2)' : 'border:1px solid var(--bdr)';
        const cardBg = isBest ? 'background:rgba(245,158,11,.05)' : 'background:var(--bg2)';
        const polyUrl = c.polymarket_url || `https://polymarket.com/event/${c.slug || c.round_id}`;

        return `
          <div style="${cardBg};${borderStyle};border-radius:8px;padding:12px;display:flex;flex-direction:column;gap:8px">
            <div style="display:flex;justify-content:space-between;align-items:center">
              <div style="display:flex;align-items:center;gap:6px">
                <span style="font-size:15px">${coinIcons[sym] || '🪙'}</span>
                <a href="${polyUrl}" target="_blank" rel="noopener noreferrer" style="font-size:13px;font-weight:800;color:var(--tx1);text-decoration:none;display:inline-flex;align-items:center;gap:3px" title="Open ${sym} 5m contract directly on Polymarket.com">
                  ${sym}/USDT <span style="font-size:9.5px;color:#38BDF8">↗</span>
                </a>
                ${isBest ? '<span style="font-size:9.5px;background:#FBBF24;color:#000;font-weight:900;padding:1px 5px;border-radius:3px">FOCUS</span>' : ''}
              </div>
              <div style="display:flex;align-items:center;gap:6px">
                <span class="b ${c.signal === 'BUY_UP' ? 'b-l' : (c.signal === 'BUY_DOWN' ? 'b-s' : 'b-p')}" style="padding:1px 6px;font-size:10px">${c.signal}</span>
                <a href="${polyUrl}" target="_blank" rel="noopener noreferrer" style="font-size:10px;color:#38BDF8;font-weight:700;background:rgba(56,189,248,.12);border:1px solid rgba(56,189,248,.25);padding:2px 7px;border-radius:4px;text-decoration:none;display:inline-flex;align-items:center;gap:2px" title="Verify ${sym} live on Polymarket">
                  <span>🔗 Trade</span> <span>↗</span>
                </a>
              </div>
            </div>

            <!-- Active Contract Slug Line (Underlined & Direct Link) -->
            <div style="display:flex;justify-content:space-between;align-items:center;background:rgba(255,255,255,.02);border:1px solid rgba(255,255,255,.05);padding:4px 8px;border-radius:4px;font-size:10px">
              <span style="color:var(--tx3);font-weight:700">Contract:</span>
              <a href="${polyUrl}" target="_blank" rel="noopener noreferrer" style="font-family:'JetBrains Mono',monospace;color:#38BDF8;font-weight:700;text-decoration:underline;text-underline-offset:2px" title="Click to verify ${sym} contract on Polymarket">
                ${c.slug || c.round_id} ↗
              </a>
            </div>

            <!-- DUAL PRICE: Live Spot vs Polymarket TWAP Oracle -->
            <div style="background:rgba(0,0,0,.35);border:1px solid rgba(255,255,255,.05);border-radius:6px;padding:7px 9px;display:flex;flex-direction:column;gap:4px">
              <div style="display:flex;justify-content:space-between;align-items:center">
                <span style="font-size:10px;color:var(--tx3)">Live Binance Spot:</span>
                <span style="font-size:12px;font-weight:800;color:#F8FAFC;font-family:'JetBrains Mono',monospace">$${spotPx.toLocaleString('en-US', {minimumFractionDigits: decDigits, maximumFractionDigits: decDigits})}</span>
              </div>
              <div style="display:flex;justify-content:space-between;align-items:center">
                <span style="font-size:10px;color:var(--tx3)">Polymarket Chainlink TWAP:</span>
                <span style="font-size:12px;font-weight:800;color:#38BDF8;font-family:'JetBrains Mono',monospace">$${twapPx.toLocaleString('en-US', {minimumFractionDigits: decDigits, maximumFractionDigits: decDigits})}</span>
              </div>
              <div style="display:flex;justify-content:space-between;align-items:center;border-top:1px dashed rgba(255,255,255,.08);padding-top:3px;margin-top:2px">
                <span style="font-size:9.5px;color:var(--tx3)">Oracle Delta &amp; Lag:</span>
                <span style="font-size:10.5px;font-weight:700;color:${lagColor};font-family:'JetBrains Mono',monospace">${(lagVal >= 0 ? '+' : '')}$${lagVal.toFixed(decDigits)} (${lagDir})</span>
              </div>
              <div style="display:flex;justify-content:space-between;align-items:center">
                <span style="font-size:9.5px;color:var(--tx3)">60s Projected TWAP:</span>
                <span style="font-size:11px;font-weight:700;color:#A5B4FC;font-family:'JetBrains Mono',monospace">$${projTwap.toLocaleString('en-US', {minimumFractionDigits: decDigits, maximumFractionDigits: decDigits})}</span>
              </div>
            </div>

            <!-- Price vs Strike -->
            <div style="display:flex;justify-content:space-between;align-items:baseline;background:rgba(0,0,0,.2);border-radius:6px;padding:6px 8px">
              <div>
                <div style="font-size:9px;color:var(--tx3)">Locked Strike (P₀)</div>
                <div style="font-size:12px;font-weight:800;color:var(--tx1);font-family:'JetBrains Mono',monospace">$${(c.strike_price || 0).toLocaleString('en-US', {minimumFractionDigits: decDigits})}</div>
              </div>
              <div style="text-align:right">
                <div style="font-size:9px;color:var(--tx3)">Delta vs Strike</div>
                <div style="font-size:12px;font-weight:800;color:${deltaColor};font-family:'JetBrains Mono',monospace">${deltaStr} (${(c.z_score || 0).toFixed(1)}σ)</div>
              </div>
            </div>

            <!-- Probability & Edge -->
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;font-size:10.5px">
              <div style="background:rgba(56,189,248,.05);border:1px solid rgba(56,189,248,.15);border-radius:4px;padding:4px 6px">
                <div style="color:#38BDF8;font-weight:700">▲ Up ${((c.calculated_prob_up || 0.5) * 100).toFixed(0)}%</div>
                <div style="color:var(--tx3);font-size:9.5px">Mkt: ${((c.market_price_up || 0.5) * 100).toFixed(0)}¢ (${edgeUp >= 0 ? '+' : ''}${edgeUp}%)</div>
              </div>
              <div style="background:rgba(244,63,94,.05);border:1px solid rgba(244,63,94,.15);border-radius:4px;padding:4px 6px">
                <div style="color:#F43F5E;font-weight:700">▼ Down ${((c.calculated_prob_down || 0.5) * 100).toFixed(0)}%</div>
                <div style="color:var(--tx3);font-size:9.5px">Mkt: ${((c.market_price_down || 0.5) * 100).toFixed(0)}¢ (${edgeDown >= 0 ? '+' : ''}${edgeDown}%)</div>
              </div>
            </div>

            <!-- Per-Coin Record & P&L -->
            <div style="display:flex;justify-content:space-between;align-items:center;font-size:9.5px;color:var(--tx3);background:rgba(255,255,255,.02);padding:3px 6px;border-radius:4px">
              <span>Record: <b style="color:var(--tx1)">${stat.wins || 0}W - ${stat.losses || 0}L</b></span>
              <span>Net P&amp;L: <b style="color:${statPnlColor}">${stat.pnl >= 0 ? '+' : ''}$${(stat.pnl || 0).toFixed(2)}</b></span>
              <span>Fees: <b style="color:#FBBF24">$${(stat.commissions_paid || 0).toFixed(3)}</b></span>
            </div>

            <!-- Next 5 Scheduled Rounds Strip for this coin (Click to Open) -->
            <div style="border-top:1px dashed rgba(255,255,255,.08);padding-top:6px;margin-top:2px">
              <div style="font-size:9.5px;color:var(--tx3);margin-bottom:4px;display:flex;justify-content:space-between">
                <span style="font-weight:700;color:var(--tx2)">Next 5M Rounds (Click to Open):</span>
                <span style="color:#A5B4FC;font-family:'JetBrains Mono',monospace">24/7 Epochs</span>
              </div>
              <div style="display:flex;flex-wrap:wrap;gap:4px">
                ${(c.next_rounds || []).map(nr => `
                  <a href="${nr.url}" target="_blank" rel="noopener noreferrer" style="font-size:9.5px;font-family:'JetBrains Mono',monospace;background:rgba(56,189,248,.08);border:1px solid rgba(56,189,248,.25);color:#38BDF8;padding:2px 6px;border-radius:4px;text-decoration:underline;text-underline-offset:2px;display:inline-flex;align-items:center;gap:3px;font-weight:700;transition:all .15s" title="Starts ${nr.status} (${nr.time_utc})">
                    <span>${nr.label} (${nr.time_utc.slice(0,5)})</span>
                    <span style="font-size:8px">↗</span>
                  </a>
                `).join('')}
              </div>
            </div>
          </div>
        `;
      }).join('');
    }

    // Active trade slip (Supports up to 2 parallel coin trades with staggered condition timer)
    const slip = $('poly5mActiveSlip');
    if (slip) {
      const activeTrades = (s.active_trades && s.active_trades.length) ? s.active_trades : (s.active_trade ? [s.active_trade] : []);
      if (activeTrades.length > 0) {
        const coinIcons = {'BTC':'🟠','ETH':'🔷','SOL':'🟣','XRP':'⚪'};
        const isSingleTradeMode = s.max_concurrent_trades === 1;
        const lowBalance2ndCoin = (!isSingleTradeMode && activeTrades.length === 1 && (s.balance !== undefined && s.balance < 10.0));
        const staggerBanner = isSingleTradeMode
          ? `<div style="background:rgba(59,130,246,.08);border:1px dashed rgba(59,130,246,.25);border-radius:6px;padding:6px 10px;font-size:10.5px;color:#60A5FA;margin-bottom:8px;display:flex;align-items:center;gap:6px">
              <span>🎯</span> <span><b>Single-Trade Priority Mode:</b> 1 active position max ($5.00 outlay). Other 3 coins locked until current trade resolves.</span>
            </div>`
          : (lowBalance2ndCoin
            ? `<div style="background:rgba(239,68,68,.1);border:1px dashed rgba(239,68,68,.3);border-radius:6px;padding:6px 10px;font-size:10.5px;color:var(--rd);margin-bottom:8px;display:flex;align-items:center;gap:6px">
                <span>🛡️</span> <span><b>Bankroll Protection:</b> Available balance is <b>$${(s.balance || 0).toFixed(2)}</b> (&lt; $10.00). 2nd coin trade is locked until bankroll recovers &ge; $10.00.</span>
              </div>`
            : ((activeTrades.length === 1 && (s.stagger_timer_remaining || 0) > 0)
              ? `<div style="background:rgba(245,158,11,.1);border:1px dashed rgba(245,158,11,.3);border-radius:6px;padding:6px 10px;font-size:10.5px;color:#FBBF24;margin-bottom:8px;display:flex;align-items:center;gap:6px">
                  <span>⏳</span> <span><b>Condition Timer Active:</b> 2nd coin slot unlocks in <b>${s.stagger_timer_remaining}s</b> (Verifying independent momentum &amp; &ge;70% edge).</span>
                </div>`
              : (activeTrades.length === 1
                ? `<div style="background:rgba(16,185,129,.08);border:1px dashed rgba(16,185,129,.25);border-radius:6px;padding:6px 10px;font-size:10.5px;color:var(--gr);margin-bottom:8px;display:flex;align-items:center;gap:6px">
                    <span>🎯</span> <span><b>2nd Coin Slot Ready:</b> Monitoring remaining 3 coins for verified displacement &amp; 20¢–82¢ sweet spot ($10 bullet ready).</span>
                  </div>`
                : '')));

        slip.innerHTML = staggerBanner + `<div style="display:grid;grid-template-columns:${activeTrades.length > 1 ? 'repeat(auto-fit,minmax(280px,1fr))' : '1fr'};gap:10px">` + activeTrades.map(t => {
          const isUp = t.outcome === 'UP';
          const dec = t.symbol === 'XRP' ? 4 : 2;
          const floatingVal = t.floating_value !== undefined ? t.floating_value : t.cost;
          const floatingPnl = t.floating_pnl !== undefined ? t.floating_pnl : 0;
          const floatingPct = t.floating_pnl_pct !== undefined ? t.floating_pnl_pct : 0;
          const pnlColor = floatingPnl >= 0 ? 'var(--gr)' : 'var(--rd)';
          const pnlSign = floatingPnl >= 0 ? '+' : '';
          const entryOdds = (t.entry_price * 100).toFixed(0);
          const curOdds = t.current_price !== undefined ? (t.current_price * 100).toFixed(0) : entryOdds;

          return `
            <div style="background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.08);border-radius:6px;padding:10px;display:flex;flex-direction:column;gap:6px">
              <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:6px">
                <div style="display:flex;align-items:center;gap:6px">
                  <span style="font-size:14px">${coinIcons[t.symbol] || '🪙'}</span>
                  <span class="b ${isUp ? 'b-l' : 'b-s'}" style="font-size:10px;padding:2px 7px;white-space:nowrap;letter-spacing:0.3px">ACTIVE ${t.outcome} on ${t.symbol}</span>
                </div>
                <div style="font-family:'JetBrains Mono',monospace;font-size:11.5px;font-weight:700;color:var(--tx1);background:rgba(255,255,255,.05);padding:2px 7px;border-radius:4px;white-space:nowrap">
                  $${t.cost.toFixed(2)} Outlay
                </div>
              </div>

              <!-- LIVE FLOATING MARKET VALUE & REAL-TIME P&L -->
              <div style="background:rgba(0,0,0,.35);border:1px solid rgba(255,255,255,.08);border-radius:6px;padding:8px 10px">
                <div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:3px">
                  <span style="font-size:10px;color:var(--tx3);text-transform:uppercase;font-weight:700">Live Floating Value:</span>
                  <span style="font-size:14px;font-weight:800;color:${pnlColor};font-family:'JetBrains Mono',monospace">
                    $${floatingVal.toFixed(2)} <span style="font-size:11px">(${pnlSign}$${floatingPnl.toFixed(2)} · ${pnlSign}${floatingPct}%)</span>
                  </span>
                </div>
                <div style="display:flex;justify-content:space-between;align-items:center;font-size:10px;color:var(--tx2)">
                  <span>Odds Movement: <b>${entryOdds}¢ → <span style="color:#38BDF8">${curOdds}¢</span></b></span>
                  <button class="btn btn-demo" style="padding:2px 7px;font-size:9.5px;font-weight:700" onclick="poly5mCashout('${t.symbol}')">
                    💰 Cash Out ($${floatingVal.toFixed(2)})
                  </button>
                </div>
              </div>

              <div style="font-size:11px;color:var(--tx2)">
                <b>${t.shares}</b> shares @ $${t.entry_price.toFixed(3)} | Fee: <b style="color:#FBBF24">$${(t.commission || 0).toFixed(3)}</b>
              </div>

              <div style="background:rgba(0,0,0,.25);border-radius:4px;padding:5px 8px;font-size:10px;display:flex;flex-direction:column;gap:2px">
                <div style="display:flex;justify-content:space-between">
                  <span style="color:var(--tx3)">Spot at Entry:</span>
                  <span style="font-family:'JetBrains Mono',monospace;color:var(--tx1)">$${(t.spot_price_at_entry || 0).toFixed(dec)}</span>
                </div>
                <div style="display:flex;justify-content:space-between">
                  <span style="color:var(--tx3)">TWAP Oracle at Entry:</span>
                  <span style="font-family:'JetBrains Mono',monospace;color:#38BDF8">$${(t.twap_price_at_entry || 0).toFixed(dec)}</span>
                </div>
                <div style="display:flex;justify-content:space-between">
                  <span style="color:var(--tx3)">Oracle Lead Delta:</span>
                  <span style="font-family:'JetBrains Mono',monospace;color:${(t.oracle_lag_at_entry || 0) >= 0 ? 'var(--gr)' : 'var(--rd)'}">${(t.oracle_lag_at_entry || 0) >= 0 ? '+' : ''}$${(t.oracle_lag_at_entry || 0).toFixed(dec)}</span>
                </div>
              </div>

              <!-- Max Settlement Payout -->
              <div style="display:flex;justify-content:space-between;align-items:center;font-size:10.5px;border-top:1px dashed rgba(255,255,255,.06);padding-top:4px">
                <span style="color:var(--tx3)">Max Payout at $1.00:</span>
                <span style="color:var(--gr);font-weight:700;font-family:'JetBrains Mono',monospace">$${(t.shares * 1.0).toFixed(2)} (+$${(t.shares * 1.0 - t.cost - (t.commission || 0)).toFixed(2)} Net)</span>
              </div>
            </div>
          `;
        }).join('') + '</div>';
      } else {
        slip.innerHTML = '<div style="font-size:11.5px;color:var(--tx3)">No active position for this 5-minute round. Monitoring 4 coins in parallel ($5 outlay · exactly 1 trade active across all coins)...</div>';
      }
    }

    // History
    const histList = $('poly5mHistoryList');
    if (histList) {
      if (s.history && s.history.length) {
        histList.innerHTML = s.history.map(h => {
          const isWon = h.status === 'WON';
          const dec = h.symbol === 'XRP' ? 4 : 2;
          const entryTwap = h.twap_price_at_entry ? `$${h.twap_price_at_entry.toFixed(dec)}` : '';
          const settlePx = h.settlement_price ? `$${h.settlement_price.toFixed(dec)}` : '';
          const pxDetail = (entryTwap && settlePx) ? ` · TWAP: ${entryTwap} → ${settlePx}` : '';
          const feeStr = h.commission ? ` · Fee: $${h.commission.toFixed(3)}` : '';
          let triggerBadge = '';
          if (h.reason && h.reason.includes('Auto Take-Profit')) {
            triggerBadge = '<span class="b" style="background:rgba(16,185,129,.2);color:var(--gr);font-size:9px;padding:1px 4px;margin-left:4px">🎯 TP HIT</span>';
          } else if (h.reason && h.reason.includes('Auto Stop-Loss')) {
            triggerBadge = '<span class="b" style="background:rgba(244,63,94,.2);color:var(--rd);font-size:9px;padding:1px 4px;margin-left:4px">🛡️ SL HIT</span>';
          } else if (h.reason && h.reason.includes('Early Cashout')) {
            triggerBadge = '<span class="b" style="background:rgba(245,158,11,.2);color:#FBBF24;font-size:9px;padding:1px 4px;margin-left:4px">💰 CASH OUT</span>';
          }

          return `
            <div style="display:flex;justify-content:space-between;align-items:center;background:rgba(255,255,255,.02);padding:5px 8px;border-radius:4px;font-size:11px">
              <div>
                <span class="b ${h.outcome === 'UP' ? 'b-l' : 'b-s'}" style="padding:1px 5px;font-size:9.5px">${h.outcome}</span>
                <b style="color:var(--tx1);margin-left:4px">${h.symbol || 'BTC'}</b>
                ${triggerBadge}
                <span style="font-family:'JetBrains Mono',monospace;margin-left:4px;color:var(--tx3)">${h.round_id.slice(-6)}</span>
                <span style="font-size:9.5px;color:var(--tx3)">${pxDetail}${feeStr}</span>
              </div>
              <span style="color:${isWon ? 'var(--gr)' : 'var(--rd)'};font-weight:700;font-family:'JetBrains Mono',monospace">
                ${isWon ? '+' : ''}$${h.pnl.toFixed(2)} (${h.status})
              </span>
            </div>
          `;
        }).join('');
      } else {
        histList.innerHTML = '<div style="font-size:11.5px;color:var(--tx3)">No completed 5M scalps yet.</div>';
      }
    }
  }
}

function filterPolyMarkets() {
  const q = ($('polySearch') ? $('polySearch').value : '').toLowerCase();
  let f = allPolyMarkets.filter(m => (m.question || '').toLowerCase().includes(q) || (m.category || '').toLowerCase().includes(q));

  if (currentPolyCategory === 'OPPORTUNITY') {
    f = f.filter(m => Math.abs(m.edge || 0) >= 0.06);
  } else if (currentPolyCategory !== 'ALL') {
    f = f.filter(m => (m.category || '').toLowerCase().includes(currentPolyCategory.toLowerCase()));
  }

  renderPolyCards(f);
  renderPolyTable(f);
}

function renderPolyCards(list) {
  const wrap = $('polyCardsWrap');
  if (!wrap) return;
  if (!list.length) {
    wrap.innerHTML = '<div class="empty" style="grid-column:1/-1">No prediction contracts match the filter criteria.</div>';
    return;
  }

  wrap.innerHTML = list.map(m => {
    const pYes = m.price_yes || 0.5;
    const pNo = m.price_no || 0.5;
    const pYesPct = Math.round(pYes * 100);
    const pNoPct = Math.round(pNo * 100);
    const forecast = m.forecast_probability || pYes;
    const forecastPct = (forecast * 100).toFixed(1);
    const indepPct = m.independent_probability ? (m.independent_probability * 100).toFixed(1) + '%' : forecastPct + '%';
    const baseRatePct = m.base_rate ? (m.base_rate * 100).toFixed(1) + '%' : '30.0%';
    const edge = m.edge || 0;
    const edgePct = (edge * 100).toFixed(1);
    const edgeSign = edge >= 0 ? '+' : '';
    const hasEdge = Math.abs(edge) >= 0.06;
    const edgeColor = hasEdge ? (edge >= 0 ? 'var(--gr)' : 'var(--rd)') : 'var(--tx2)';
    const isAbstain = !!m.recommend_abstain;
    const signalBadge = isAbstain
      ? '<span class="b" style="background:rgba(239,68,68,.15);color:var(--rd);border:1px solid rgba(239,68,68,.3)">ABSTAIN</span>'
      : (edge >= 0.06 ? '<span class="b b-l">BUY YES</span>' : (edge <= -0.06 ? '<span class="b b-s">BUY NO</span>' : '<span class="b b-d">HOLD</span>'));
    const thesis = m.reasoning || 'Awaiting initial Bayesian intelligence synthesis...';
    const closeStr = formatEndDate(m.end_date);

    const qScore = Math.round(m.qualification_score || 70);
    const qTier = m.qualification_tier || 'MONITOR';
    const qBg = qTier === 'DEEP_RESEARCH' ? 'rgba(16,185,129,.15)' : (qTier === 'MONITOR' ? 'rgba(245,158,11,.15)' : 'rgba(255,255,255,.05)');
    const qColor = qTier === 'DEEP_RESEARCH' ? 'var(--gr)' : (qTier === 'MONITOR' ? 'var(--am)' : 'var(--tx3)');
    const qualPill = `<span style="font-size:10px;font-weight:700;padding:2px 7px;border-radius:4px;background:${qBg};color:${qColor};border:1px solid ${qColor}44">${qTier} ${qScore}/100</span>`;
    const redTeamWarning = m.counterarguments ? `<div style="font-size:10px;color:var(--am);margin-top:6px;padding:4px 8px;background:rgba(245,158,11,.08);border-radius:4px;border-left:2px solid var(--am);line-height:1.3"><b>🛡️ Red Team:</b> ${m.counterarguments.slice(0, 120)}...</div>` : '';

    return `
      <div class="pm-card">
        <div class="pm-card-top">
          <div style="display:flex;align-items:center;gap:6px">
            <span class="b b-p">${m.category || 'General'}</span>
            ${qualPill}
          </div>
          <span style="font-size:11px;color:#A5B4FC;font-weight:600;display:flex;align-items:center;gap:4px">
            📅 Closes: ${closeStr}
          </span>
          <span class="pm-vol">$${(m.volume_24h || 0).toLocaleString('en-US', {maximumFractionDigits:0})} Vol</span>
        </div>
        <div class="pm-card-title">${m.question}</div>

        <!-- Polymarket Probability Bar -->
        <div class="pm-bar-wrap">
          <div style="display:flex;justify-content:space-between;font-size:11px;font-family:'JetBrains Mono',monospace">
            <span style="color:#38BDF8;font-weight:700">YES ${pYesPct}%</span>
            <span style="color:#94A3B8;font-weight:700">NO ${pNoPct}%</span>
          </div>
          <div class="pm-prob-bar">
            <div class="pm-bar-yes" style="width:${pYesPct}%"></div>
            <div class="pm-bar-no" style="width:${pNoPct}%"></div>
          </div>
        </div>

        <!-- Outcomes Buttons (Polymarket Style) -->
        <div class="pm-outcomes-wrap">
          <div class="pm-btn yes">
            <span style="font-size:12px;font-weight:700;color:#38BDF8">YES</span>
            <span style="font-size:13px;font-weight:800;font-family:'JetBrains Mono',monospace">$${pYes.toFixed(2)}</span>
          </div>
          <div class="pm-btn no">
            <span style="font-size:12px;font-weight:700;color:#94A3B8">NO</span>
            <span style="font-size:13px;font-weight:800;font-family:'JetBrains Mono',monospace">$${pNo.toFixed(2)}</span>
          </div>
        </div>

        <!-- AI Superforecaster Edge Intelligence -->
        <div class="pm-ai-box">
          <div style="display:flex;justify-content:space-between;align-items:center;font-size:11px">
            <span style="color:#A5B4FC;font-weight:700">AI Model Forecast: ${forecastPct}%</span>
            <span style="color:${edgeColor};font-weight:800;font-family:'JetBrains Mono',monospace">${edgeSign}${edgePct}% Edge</span>
          </div>
          <div style="display:flex;justify-content:space-between;align-items:center;margin-top:2px;font-size:10px;color:var(--tx3)">
            <span>Blind AI: <b style="color:#F8FAFC">${indepPct}</b> | Base: ${baseRatePct}</span>
            <div>${signalBadge}</div>
          </div>
          ${redTeamWarning}
          <div class="pm-thesis"><b>💡 Adversarial Synthesis:</b> ${thesis}</div>
        </div>

        <button class="btn btn-demo" style="width:100%;justify-content:center;padding:7px;margin-top:auto" onclick="openDeepDive('${m.id}')">
          🔬 Open Evidence Dossier &amp; Timeline
        </button>
      </div>
    `;
  }).join('');
}

function renderPolyTable(list) {
  const tb = $('polyMarketTb');
  if (!tb) return;
  if (!list.length) {
    tb.innerHTML = '<tr><td colspan="10" class="empty">No matching prediction contracts found.</td></tr>';
    return;
  }
  tb.innerHTML = list.map(m => {
    const edge = m.edge || 0;
    const edgePct = (edge * 100).toFixed(1);
    const edgeSign = edge >= 0 ? '+' : '';
    const edgeColor = Math.abs(edge) >= 0.06 ? (edge >= 0 ? 'g' : 'r') : 'tx2';
    const isAbstain = !!m.recommend_abstain;
    const action = isAbstain
      ? '<span class="b" style="background:rgba(239,68,68,.15);color:var(--rd);border:1px solid rgba(239,68,68,.3)">ABSTAIN</span>'
      : (edge >= 0.06 ? '<span class="b b-l">BUY YES</span>' : (edge <= -0.06 ? '<span class="b b-s">BUY NO</span>' : '<span class="b b-d">HOLD</span>'));
    const qScore = Math.round(m.qualification_score || 70);
    const qTier = m.qualification_tier || 'MONITOR';
    const qColor = qTier === 'DEEP_RESEARCH' ? 'var(--gr)' : (qTier === 'MONITOR' ? 'var(--am)' : 'var(--tx3)');

    return `<tr>
      <td><b>${m.question}</b></td>
      <td><span class="b b-p">${m.category}</span></td>
      <td><span style="color:${qColor};font-weight:700;font-size:11px">${qTier} (${qScore})</span></td>
      <td style="color:#A5B4FC;font-family:'JetBrains Mono',monospace;font-size:11px">${formatEndDate(m.end_date)}</td>
      <td>$${(m.volume_24h || 0).toLocaleString('en-US', {maximumFractionDigits:0})}</td>
      <td>$${m.price_yes.toFixed(2)} / $${m.price_no.toFixed(2)}</td>
      <td style="color:#38BDF8;font-weight:700">${((m.independent_probability || m.price_yes) * 100).toFixed(1)}%</td>
      <td style="color:#A5B4FC;font-weight:700">${((m.forecast_probability || 0.5) * 100).toFixed(1)}%</td>
      <td class="${edgeColor}"><b>${edgeSign}${edgePct}%</b></td>
      <td>${action}</td>
      <td>
        <button class="btn btn-demo" style="padding:4px 8px;font-size:10.5px;" onclick="openDeepDive('${m.id}')">Dossier</button>
      </td>
    </tr>`;
  }).join('');
}

function renderPolyEvidence(evidenceList) {
  const wrap = $('polyNewsFeed');
  if (!wrap) return;
  if ($('polyEvidenceCount')) $('polyEvidenceCount').innerText = `${evidenceList.length} Analyzed Articles`;
  if (!evidenceList.length) {
    wrap.innerHTML = '<div class="empty" style="grid-column:1/-1">No news evidence ingested yet. Trigger a research cycle to begin scraping.</div>';
    return;
  }

  wrap.innerHTML = evidenceList.map(ev => {
    const sent = ev.sentiment_impact || 0;
    let sentClass = 'neutral';
    let sentLabel = '⚪ NEUTRAL BASELINE';
    if (sent > 0.1) {
      sentClass = 'bullish';
      sentLabel = `🟢 FAVORABLE TO 'YES' (+${Math.round(sent*100)}%)`;
    } else if (sent < -0.1) {
      sentClass = 'bearish';
      sentLabel = `🔴 DELAY / FAVORABLE TO 'NO' (${Math.round(sent*100)}%)`;
    }

    const credPct = Math.round((ev.credibility_score || 0.85) * 100);

    return `
      <div class="news-item-card">
        <div class="news-top">
          <span class="sentiment-pill ${sentClass}">${sentLabel}</span>
          <span style="font-size:9.5px;color:var(--tx3);font-family:'JetBrains Mono',monospace">${credPct}% Verified</span>
        </div>
        <div class="news-headline">${ev.title}</div>
        <div style="display:flex;align-items:center;gap:6px;font-size:10px;color:var(--tx3);margin-top:2px">
          <span style="color:#A5B4FC;font-weight:600">Source: ${ev.source_name}</span>
          <span>•</span>
          <span style="color:var(--tx2)">Affects: ${ev.market_question ? ev.market_question.slice(0, 35) + '...' : 'General'}</span>
        </div>
        <div class="news-summary">${ev.summary}</div>
      </div>
    `;
  }).join('');
}

async function openDeepDive(marketId) {
  try {
    const res = await fetch('/api/polymarket/timeline?id=' + encodeURIComponent(marketId));
    const d = await res.json();
    const modal = $('polyModal');
    const m = allPolyMarkets.find(x => x.id === marketId) || {};
    $('modalQuestion').innerText = m.question || marketId;
    $('modalCategory').innerText = m.category || 'PREDICTION CONTRACT';
    let resDetails = '';
    if (m.resolution_spec) {
      try {
        const rs = typeof m.resolution_spec === 'string' ? JSON.parse(m.resolution_spec) : m.resolution_spec;
        resDetails = `
          <div style="margin-top:10px;padding:12px;background:rgba(99,102,241,.06);border:1px solid rgba(99,102,241,.2);border-radius:8px;font-size:11.5px">
            <div style="font-weight:700;color:#A5B4FC;margin-bottom:4px">📜 Agent 01 · Resolution Specification</div>
            <div style="color:var(--tx1);margin-bottom:3px"><b>YES Trigger:</b> ${rs.yes_condition || 'Standard occurrence'}</div>
            <div style="color:var(--tx2);margin-bottom:3px"><b>NO Trigger:</b> ${rs.no_condition || 'Failure to occur by deadline'}</div>
            <div style="color:var(--tx3);font-size:10.5px"><b>Standard:</b> ${rs.effective_vs_announced || 'Official Release'} | <b>Ambiguity Risk:</b> <span style="color:${rs.ambiguity_risk === 'HIGH' ? 'var(--rd)' : 'var(--gr)'}">${rs.ambiguity_risk || 'LOW'}</span></div>
          </div>
        `;
      } catch (err) {}
    }

    $('modalResolution').innerHTML = 'Resolution Source: ' + (m.resolution_source || 'Polymarket UMA Oracle') + ' · 📅 Market Closes: ' + formatEndDate(m.end_date) + resDetails;

    // Render Timeline
    const tlList = $('modalTimelineList');
    if (d.timeline && d.timeline.length) {
      tlList.innerHTML = d.timeline.map((item, idx) => `
        <div style="background:#090D15;border:1px solid var(--bdr);border-radius:8px;padding:10px 14px;display:flex;flex-direction:column;gap:4px">
          <div style="display:flex;justify-content:space-between;align-items:center">
            <span style="font-size:11px;font-weight:700;color:#A5B4FC">Revision #${idx + 1} · Forecast: ${(item.forecast_probability * 100).toFixed(1)}%</span>
            <span style="font-size:9.5px;color:var(--tx3)">${(item.created_at || '').slice(0, 19).replace('T', ' ')}</span>
          </div>
          <div style="font-size:10.5px;color:var(--tx2);line-height:1.4">${item.reasoning}</div>
          <div style="font-size:9px;color:var(--tx3);font-family:'JetBrains Mono',monospace">Engine: ${item.model_used} | Market: ${(item.market_probability * 100).toFixed(1)}% | Edge: ${(item.edge * 100).toFixed(1)}%</div>
        </div>
      `).join('');
    } else {
      tlList.innerHTML = '<div class="empty">No prior forecast revisions recorded.</div>';
    }

    // Render Evidence
    const evList = $('modalEvidenceList');
    if (d.evidence && d.evidence.length) {
      evList.innerHTML = d.evidence.map(item => `
        <div style="background:#090D15;border:1px solid var(--bdr);border-radius:8px;padding:10px 14px;display:flex;flex-direction:column;gap:4px">
          <div style="display:flex;justify-content:space-between;align-items:center">
            <span style="font-size:11.5px;font-weight:700;color:#F8FAFC">${item.title}</span>
            <span class="b b-p">${item.source_name}</span>
          </div>
          <div style="font-size:10.5px;color:var(--tx2);line-height:1.35">${item.summary}</div>
          <div style="display:flex;justify-content:space-between;font-size:9px;color:var(--tx3);margin-top:2px">
            <span>Credibility Score: ${(item.credibility_score * 100).toFixed(0)}%</span>
            <span>Sentiment Impact: ${(item.sentiment_impact >= 0 ? '+' : '')}${(item.sentiment_impact * 100).toFixed(0)}%</span>
          </div>
        </div>
      `).join('');
    } else {
      evList.innerHTML = '<div class="empty">No external evidence linked yet.</div>';
    }

    modal.style.display = 'flex';
  } catch (e) {}
}

function closeDeepDive() {
  $('polyModal').style.display = 'none';
}

async function polyScan() {
  await fetch('/api/polymarket/scan', { method: 'POST' });
  setTimeout(loadPolymarketState, 300);
}

async function polyResearch() {
  const btn = $('polyResearchBtn');
  if (btn) {
    btn.innerHTML = '⏳ Research Active...';
    btn.style.opacity = '0.7';
  }
  await fetch('/api/polymarket/research', { method: 'POST' });
  setTimeout(loadPolymarketState, 300);
}

async function polyReset() {
  if (confirm('Reset Polymarket system? This pauses auto-pilot, clears all bets and news evidence, and restores fresh $500.00 bankroll.')) {
    await fetch('/api/polymarket/reset', { method: 'POST' });
    setTimeout(loadPolymarketState, 300);
  }
}

async function polyClosePosition(id, outcome, shares, currentVal) {
  if (confirm(`Liquidate ${shares} shares of ${outcome} now for $${currentVal.toFixed(2)} cash?`)) {
    const res = await fetch('/api/polymarket/close', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({id: id})
    });
    const d = await res.json();
    if (d.ok) {
      loadPolymarketState();
    }
  }
}

async function polyFlattenAll() {
  if (confirm('Liquidate ALL active open paper bets at current market prices?')) {
    const res = await fetch('/api/polymarket/flatten', { method: 'POST' });
    const d = await res.json();
    if (d.ok) {
      loadPolymarketState();
    }
  }
}

// ── Polymarket Live API & Credentials Management ───────────────────────
function openPolyKeyModal() {
  const modal = $('polyKeyModal');
  if (!modal) return;
  const resBox = $('polyModalTestResult');
  if (resBox) resBox.style.display = 'none';

  // Fetch current live account status to prefill if exists
  fetch('/api/polymarket/live/status')
    .then(r => r.json())
    .then(data => {
      if (data && data.configured) {
        if ($('polyModalFunderAddress') && data.funder_address) {
          $('polyModalFunderAddress').value = data.funder_address;
        }
      }
    })
    .catch(() => {});

  modal.style.display = 'flex';
}

function closePolyKeyModal() {
  const modal = $('polyKeyModal');
  if (modal) modal.style.display = 'none';
}

function togglePolyKeyVisibility() {
  const inp = $('polyModalPrivateKey');
  if (!inp) return;
  inp.type = (inp.type === 'password') ? 'text' : 'password';
}

async function testPolyCredentials() {
  const btn = $('btnTestPolyCreds');
  const resBox = $('polyModalTestResult');
  const pk = ($('polyModalPrivateKey')?.value || '').trim();
  const funder = ($('polyModalFunderAddress')?.value || '').trim();
  const sigType = parseInt($('polyModalSigType')?.value || '0', 10);

  if (resBox) {
    resBox.style.display = 'block';
    resBox.style.background = 'rgba(56,189,248,.1)';
    resBox.style.border = '1px solid rgba(56,189,248,.3)';
    resBox.style.color = '#38BDF8';
    resBox.innerText = '⏳ Connecting to Polygon RPC & Polymarket CLOB... Testing signature & querying balance...';
  }
  if (btn) btn.disabled = true;

  try {
    const res = await fetch('/api/polymarket/live/test', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        private_key: pk,
        funder_address: funder,
        signature_type: sigType
      })
    });
    const d = await res.json();
    if (resBox) {
      if (d.connected) {
        resBox.style.background = 'rgba(16,185,129,.12)';
        resBox.style.border = '1px solid #10B981';
        resBox.style.color = '#10B981';
        resBox.innerHTML = `
          ✅ <b>Pre-Flight Connection Successful!</b><br>
          • Wallet Address: <code>${d.wallet_address || 'OK'}</code><br>
          • Funder Address: <code>${d.funder_address || 'Direct Signer'}</code><br>
          • Spendable USDC.e Balance: <b>$${(d.usdc_balance || 0).toFixed(2)}</b><br>
          • CTF Token Allowance: <b>$${(d.allowance || 0).toFixed(2)}</b><br>
          Ready for live gasless execution!
        `;
      } else {
        resBox.style.background = 'rgba(239,68,68,.12)';
        resBox.style.border = '1px solid #EF4444';
        resBox.style.color = '#F87171';
        resBox.innerHTML = `❌ <b>Connection Failed:</b> ${d.reason || 'Invalid credentials or network timeout'}`;
      }
    }
  } catch (err) {
    if (resBox) {
      resBox.style.background = 'rgba(239,68,68,.12)';
      resBox.style.border = '1px solid #EF4444';
      resBox.style.color = '#F87171';
      resBox.innerText = '❌ Error testing connection: ' + err.message;
    }
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function savePolyCredentials() {
  const btn = $('btnSavePolyCreds');
  const pk = ($('polyModalPrivateKey')?.value || '').trim();
  const funder = ($('polyModalFunderAddress')?.value || '').trim();
  const sigType = parseInt($('polyModalSigType')?.value || '0', 10);

  if (!pk) {
    alert('Please enter your Polygon private key.');
    return;
  }

  if (btn) btn.disabled = true;
  try {
    const res = await fetch('/api/polymarket/live/save', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        private_key: pk,
        funder_address: funder,
        signature_type: sigType
      })
    });
    const d = await res.json();
    if (d.ok) {
      alert('✅ Polymarket live credentials saved securely in .env and applied to Live Executor!');
      closePolyKeyModal();
      loadPolymarketState();
    } else {
      alert('❌ Failed to save credentials: ' + (d.reason || 'Unknown error'));
    }
  } catch (err) {
    alert('❌ Error saving credentials: ' + err.message);
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function setPolyTradingMode(isLive) {
  if (isLive) {
    // Check if live account is configured
    try {
      const res = await fetch('/api/polymarket/live/status');
      const st = await res.json();
      if (!st.configured) {
        alert('⚠️ No Polymarket live credentials configured yet.\nPlease enter your Polygon Private Key in the setup modal to enable Live Mode.');
        openPolyKeyModal();
        return;
      }
    } catch (e) {}
  }

  const res = await fetch('/api/polymarket/live/toggle-mode', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ live_enabled: isLive, mode: isLive ? 'LIVE' : 'PAPER' })
  });
  const d = await res.json();
  loadPolymarketState();
}

async function polyToggle5mScalper() {
  // Check if current mode is LIVE and scalper is stopped -> Show safety confirmation
  const isLive = window.lastPolyData?.live_account?.trading_mode === 'LIVE' || window.lastPolyData?.live_account?.live_enabled;
  const isStopped = !window.lastPolyData?.btc_5m?.is_enabled;

  if (isLive && isStopped) {
    const balEl = $('polyConfirmLiveBalance');
    if (balEl && window.lastPolyData?.live_account) {
      balEl.innerText = '$' + (window.lastPolyData.live_account.usdc_balance || 0).toFixed(2) + ' USDC.e';
    }
    const modal = $('polyLiveConfirmModal');
    if (modal) {
      modal.style.display = 'flex';
      return;
    }
  }

  await _doPolyToggle5mScalper();
}

async function _doPolyToggle5mScalper() {
  const res = await fetch('/api/polymarket/5m/toggle', { method: 'POST' });
  const d = await res.json();
  if (d.ok) {
    loadPolymarketState();
  }
}

function closePolyLiveConfirmModal(confirmed) {
  const modal = $('polyLiveConfirmModal');
  if (modal) modal.style.display = 'none';
  if (confirmed) {
    _doPolyToggle5mScalper();
  }
}

async function poly5mCashout(sym) {
  if (confirm(`Cash out and lock in live profit on ${sym} now?`)) {
    const res = await fetch('/api/polymarket/5m/cashout', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ symbol: sym })
    });
    const d = await res.json();
    if (d.ok) {
      loadPolymarketState();
    }
  }
}

async function polyForceSettle() {
  const res = await fetch('/api/polymarket/5m/settle', { method: 'POST' });
  const d = await res.json();
  loadPolymarketState();
}

let currentPolyBetFilter = 'ALL';
function setPolyBetFilter(filter) {
  currentPolyBetFilter = filter;
  ['All', 'Yield', 'Edge'].forEach(id => {
    const el = document.getElementById('btnPolyFilter' + id);
    if (el) el.classList.remove('active');
  });
  if (filter === 'ALL' && document.getElementById('btnPolyFilterAll')) document.getElementById('btnPolyFilterAll').classList.add('active');
  if (filter === 'HIGH_PROBABILITY_YIELD' && document.getElementById('btnPolyFilterYield')) document.getElementById('btnPolyFilterYield').classList.add('active');
  if (filter === 'ASYMMETRIC_EDGE' && document.getElementById('btnPolyFilterEdge')) document.getElementById('btnPolyFilterEdge').classList.add('active');
  if (window.lastPolyData) renderPolymarketState(window.lastPolyData);
}

connectStream();
</script>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def handle(self):
        """Catch browser disconnects (Cmd+R, tab close) without noisy console tracebacks."""
        try:
            super().handle()
        except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError):
            pass

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._html(HTML)
        elif self.path == "/api/state":
            self._json(BOT.get_full_state())
        elif self.path == "/api/crypto/state":
            self._json(CRYPTO_BOT.get_dashboard_state())
        elif self.path == "/api/crypto/export-dataset":
            self._json(CRYPTO_BOT.storage.export_dataset_json())
        elif self.path == "/api/polymarket/state":
            self._json(POLY_BOT.get_full_state())
        elif self.path == "/api/polymarket/live/status":
            self._json(POLY_BOT.get_live_account_status())
        elif self.path.startswith("/api/polymarket/crypto/timeline"):
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            coin = qs.get("coin", ["BTC"])[0]
            tf = qs.get("tf", ["5m"])[0]
            self._json(POLY_BOT.btc_analyzer.get_polymarket_timeline(coin, tf))
        elif self.path.startswith("/api/polymarket/timeline"):
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            if "coin" in qs or "tf" in qs:
                coin = qs.get("coin", ["BTC"])[0]
                tf = qs.get("tf", ["5m"])[0]
                self._json(POLY_BOT.btc_analyzer.get_polymarket_timeline(coin, tf))
            else:
                m_id = qs.get("id", [""])[0]
                self._json(POLY_BOT.memory.get_market_timeline(m_id))
        elif self.path == "/api/session-debriefs":
            self._json(BOT.storage.get_latest_session_debriefs(limit=10))
        elif self.path == "/api/stream":
            self._handle_sse_stream()
        else:
            self.send_error(404)

    def _handle_sse_stream(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        initial_payload = f"data: {json.dumps(BOT.get_full_state())}\n\n"
        self.wfile.write(initial_payload.encode())
        self.wfile.flush()

        sub_queue = BOT.subscribe()
        try:
            while True:
                try:
                    event_data = sub_queue.get(timeout=15)
                    self.wfile.write(event_data.encode())
                    self.wfile.flush()
                except queue.Empty:
                    self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            BOT.unsubscribe(sub_queue)

    def do_POST(self):
        if self.path == "/api/bot/start":
            BOT.start(); self._json({"ok": True})
        elif self.path == "/api/bot/stop":
            BOT.stop(); self._json({"ok": True})
        elif self.path == "/api/bot/demo":
            BOT.run_demo(); self._json({"ok": True})
        elif self.path == "/api/bot/flatten":
            BOT.flatten_all(); self._json({"ok": True})
        elif self.path == "/api/bot/close":
            body = self._read_body()
            BOT.close_single(body.get("id", "")); self._json({"ok": True})
        elif self.path == "/api/bot/reset":
            BOT.reset_account(); self._json({"ok": True})
        elif self.path == "/api/polymarket/scan":
            POLY_BOT.trigger_sync_async(); self._json({"ok": True, "status": "SYNC_STARTED"})
        elif self.path == "/api/polymarket/research":
            ok = POLY_BOT.trigger_research_async()
            self._json({"ok": True, "active": ok})
        elif self.path == "/api/polymarket/start":
            POLY_BOT.start(); self._json({"ok": True})
        elif self.path == "/api/polymarket/stop":
            POLY_BOT.stop(); self._json({"ok": True})
        elif self.path == "/api/polymarket/reset":
            POLY_BOT.reset_system(); self._json({"ok": True})
        elif self.path == "/api/polymarket/close":
            body = self._read_body()
            pos_id = int(body.get("id", 0))
            res = POLY_BOT.close_position(pos_id)
            self._json({"ok": True, "result": res})
        elif self.path == "/api/polymarket/flatten":
            res = POLY_BOT.flatten_all()
            self._json({"ok": True, "closed_count": len(res)})
        elif self.path == "/api/polymarket/5m/toggle":
            is_active = POLY_BOT.toggle_5m_scalper()
            self._json({"ok": True, "is_enabled": is_active})
        elif self.path == "/api/polymarket/5m/cashout":
            body = self._read_body()
            sym = body.get("symbol", "")
            res = POLY_BOT.cashout_5m_trade(sym)
            self._json({"ok": True, "result": res})
        elif self.path == "/api/polymarket/5m/settle":
            count = POLY_BOT.force_settle_5m()
            self._json({"ok": True, "settled_count": count})
        elif self.path == "/api/polymarket/live/test":
            body = self._read_body()
            pk = body.get("private_key", "")
            funder = body.get("funder_address", "")
            sig_type = body.get("signature_type")
            res = POLY_BOT.test_live_credentials(pk, funder, sig_type)
            self._json(res)
        elif self.path == "/api/polymarket/live/save":
            body = self._read_body()
            pk = body.get("private_key", "")
            funder = body.get("funder_address", "")
            sig_type = body.get("signature_type")
            live_enabled = bool(body.get("live_enabled", False))
            res = POLY_BOT.update_live_credentials(pk, funder, sig_type, live_enabled)
            self._json(res)
        elif self.path == "/api/polymarket/live/toggle-mode":
            body = self._read_body()
            is_live = bool(body.get("live_enabled", False)) or (str(body.get("mode", "")).upper() == "LIVE")
            status = POLY_BOT.set_live_mode(is_live)
            self._json({"ok": True, "status": status})
        elif self.path == "/api/crypto/start":
            CRYPTO_BOT.start(); self._json({"ok": True})
        elif self.path == "/api/crypto/stop":
            CRYPTO_BOT.stop(); self._json({"ok": True})
        elif self.path == "/api/crypto/scan":
            CRYPTO_BOT.force_scan(); self._json({"ok": True})
        elif self.path == "/api/crypto/flatten":
            CRYPTO_BOT.flatten_all(); self._json({"ok": True})
        elif self.path == "/api/crypto/close":
            body = self._read_body()
            pos_id = body.get("id", "")
            account = CRYPTO_BOT.storage.get_account()
            open_pos = CRYPTO_BOT.storage.get_open_positions()
            target = next((p for p in open_pos if p.position_id == pos_id), None)
            if target:
                p = CRYPTO_BOT.data_feed.get_current_price(target.symbol) or target.current_price or target.entry_price
                CRYPTO_BOT.order_mgr.close_position_manually(pos_id, p, account)
            self._json({"ok": True})
        elif self.path == "/api/crypto/reset":
            CRYPTO_BOT.reset(); self._json({"ok": True})
        elif self.path == "/api/crypto/mode":
            body = self._read_body()
            mode = body.get("mode", "SIMULATED_PAPER")
            CRYPTO_BOT.storage.set_mode(mode)
            self._json({"ok": True})
        elif self.path == "/api/crypto/profile":
            body = self._read_body()
            prof = body.get("profile", "MODERATE_GROWTH")
            CRYPTO_BOT.set_strategy_profile(prof)
            self._json({"ok": True, "profile": prof})
        else:
            self.send_error(404)

    def _read_body(self):
        n = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(n)
        return json.loads(raw.decode()) if raw else {}

    def _json(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def _html(self, content):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(content.encode())


class SilentThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    def handle_error(self, request, client_address):
        """Suppress benign browser disconnect errors when user refreshes or closes tab."""
        import sys
        err_type = sys.exc_info()[0]
        if err_type in (ConnectionResetError, BrokenPipeError, ConnectionAbortedError):
            return
        super().handle_error(request, client_address)


def arm_engines_on_boot(poly_bot, crypto_bot):
    """
    Starts the autonomous engines that are safe to run unattended on server boot.
    The Polymarket 5M scalper is deliberately left untouched: its trading mode is
    decided once at construction from POLYMARKET_LIVE_ENABLED, and arming it
    requires an explicit operator action (Start Auto-Pilot / scalper toggle).
    """
    crypto_bot.start()


def run_web_dashboard(port: int = 8080, host: str = "0.0.0.0"):
    import os
    port = int(os.environ.get("PORT", port))
    host = os.environ.get("HOST", "0.0.0.0")
    srv = SilentThreadingHTTPServer((host, port), Handler)
    print("=" * 84)
    print("  ICT & POLYMARKET SENTINEL AI — COMMAND CENTER")
    print(f"  Open in Browser: http://{host}:{port}")
    print("  Dual-Engine Intelligence · Live Activity Stream · Automated Auto-Pilot")
    print("=" * 84)
    print("[*] Stream active. Press Ctrl+C in terminal to shutdown.\n")
    arm_engines_on_boot(poly_bot=POLY_BOT, crypto_bot=CRYPTO_BOT)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n[!] Shutting down.")
        BOT.stop()
        POLY_BOT.stop()
        CRYPTO_BOT.stop()
        srv.server_close()
