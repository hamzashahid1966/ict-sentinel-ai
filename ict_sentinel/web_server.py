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

from .config import ASSET_SPECS, INITIAL_CAPITAL
from .storage import StorageEngine
from .data_feed import DataFeedEngine
from .ipda_engine import IPDAEngine
from .ai_advisor import AIAdvisor
from .order_manager import OrderManager
from .memory_engine import MemoryEngine
from .models import Candle


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
        assets_synced = 0
        for asset in ASSET_SPECS:
            if self.stop_event.is_set():
                break
            candles = self.data_feed.fetch_recent_bars(asset, interval="5m", limit=60)
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

            # 2. Check for new signals
            signal = self.ipda.evaluate_market(asset, candles, memory_engine=self.memory_engine)
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

        now_et = datetime.datetime.now(datetime.timezone.utc).astimezone(
            datetime.timezone(datetime.timedelta(hours=-5))
        )
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
            })

        tds = []
        for t in trades:
            tds.append({
                "id": t.trade_id, "a": t.asset, "ss": t.session,
                "d": t.direction, "et": t.entry_time, "ep": t.entry_price,
                "xt": t.exit_time, "xp": t.exit_price,
                "pnl": t.dollar_pnl, "out": t.outcome, "ai": t.ai_reasoning,
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
        if not self.is_running:
            micro_state = "Engine Idle (Click 'Start Engine' to activate live tape scanning)"
        elif len(open_pos) > 0:
            micro_state = f"Managing {len(open_pos)} active Double Tap position(s) with Defensive Shields"
        elif session == "OFF-SESSION":
            next_name = session_info.get("label", "Next Session")
            micro_state = f"Engine Armed & Monitoring Tape — Standing by for {next_name}"
        else:
            micro_state = f"Actively scanning 5m bars in {session} for sweeps & body MSS"

        return {
            "running": self.is_running,
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
                "tt": total, "w": len(wins), "l": len(losses_list),
            },
            "eq": eq, "assets": assets, "pos": pos,
            "trades": tds, "logs": lg,
            "diagnostics": diagnostics,
            "mem": weights, "ref": reflections,
            "activity": self.activity_events,
            "risk_guards": {
                "consecutive_losses": cons_losses,
                "max_consecutive_allowed": 2,
                "daily_risk_budget": 50.00,
                "drawdown_current": round(acct.max_drawdown_dollars, 2)
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
</style>
</head>
<body>

<header>
  <div class="hl">
    <div class="icon">⚡</div>
    <div>
      <div class="brand">ICT Sentinel AI — Command Center</div>
      <div class="sub">Event-Driven SSE Stream · Double Tap OMS · Live Activity Radar</div>
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
        <div class="ks"><span>Win Rate: <b id="kWr" class="g">0%</b></span><span>PF: <b id="kPf">0</b></span></div>
      </div>
      <div class="kc">
        <div class="kl">Trade Ledger</div>
        <div class="kv" id="kTt">0</div>
        <div class="ks"><span>Wins: <b id="kW" class="g">0</b></span><span>Losses: <b id="kL" class="r">0</b></span></div>
      </div>
      <div class="kc">
        <div class="kl">Risk & Drawdown</div>
        <div class="kv" id="kDD">$0.00</div>
        <div class="ks"><span>Max DD: <b id="kDDp">0%</b></span><span id="kOp">0 Brackets</span></div>
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
          <th>ID</th><th>Asset</th><th>Dir</th><th>Entry</th><th>Stop</th><th>CM 1.5R</th><th>HS 3.0R</th><th>Unreal PnL</th><th>Status</th><th>Action</th>
        </tr></thead><tbody id="pTb">
          <tr><td colspan="10" class="empty">No open positions. Real-time tape monitoring active...</td></tr>
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

<script>
let R=false,AT=[],currentSessionInfo=null;
const $=id=>document.getElementById(id);
const fx=(a,v)=>a.includes('USD')?v.toFixed(4):v.toFixed(2);

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
  if(!d.pos.length){pt.innerHTML='<tr><td colspan="10" class="empty">No open positions. Real-time tape monitoring active...</td></tr>'}
  else{pt.innerHTML=d.pos.map(p=>`<tr>
    <td>#${p.id}</td><td><b>${p.a}</b></td>
    <td><span class="b ${p.d==='LONG'?'b-l':'b-s'}">${p.d}</span></td>
    <td>${fx(p.a,p.ep)}</td><td class="r">${fx(p.a,p.ts)}</td>
    <td class="g">${fx(p.a,p.cm)}</td><td class="g">${fx(p.a,p.hs)}</td>
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

    $('ddBudgetVal').innerText=`$${rg.drawdown_current.toFixed(2)} / $${rg.daily_risk_budget.toFixed(2)}`;
    const ddPct=Math.min(100,(rg.drawdown_current/rg.daily_risk_budget)*100);
    const ddBar=$('ddBudgetBar');
    ddBar.style.width=`${ddPct}%`;
    ddBar.style.background=ddPct>70?'var(--rd)':(ddPct>40?'var(--am)':'var(--gr)');
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
    let bc='b-w';if(t.out==='DEFENSIVE_STOP')bc='b-d';else if(t.out==='LOSS')bc='b-x';
    const pc=t.pnl>=0?'g':'r',sg=t.pnl>=0?'+':'';
    return`<tr>
      <td>${t.xt}</td><td><b>${t.a}</b></td><td>${t.ss}</td>
      <td><span class="b ${t.d==='LONG'?'b-l':'b-s'}">${t.d}</span></td>
      <td>${fx(t.a,t.ep)} ➔ ${fx(t.a,t.xp)}</td>
      <td class="${pc}"><b>${sg}$${t.pnl.toFixed(2)}</b></td>
      <td><span class="b ${bc}">${t.out}</span></td>
      <td style="color:var(--tx2);font-size:10.5px;max-width:240px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${t.ai}</td>
    </tr>`}).join('');
}

async function toggle(){await fetch(R?'/api/bot/stop':'/api/bot/start',{method:'POST'});}
async function demo(){await fetch('/api/bot/demo',{method:'POST'});}
async function flatten(){if(confirm('Flatten ALL open positions at market price?')){await fetch('/api/bot/flatten',{method:'POST'});}}
async function cpos(id){if(confirm('Close position #'+id+'?')){await fetch('/api/bot/close',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id})});}}
async function reset(){if(confirm('Reset account to $500 and clear all history?')){await fetch('/api/bot/reset',{method:'POST'});}}

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

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._html(HTML)
        elif self.path == "/api/state":
            self._json(BOT.get_full_state())
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
    def handle_error(self, request, client_address):
        """Suppress benign browser disconnect errors when user refreshes or closes tab."""
        import sys
        err_type = sys.exc_info()[0]
        if err_type in (ConnectionResetError, BrokenPipeError, ConnectionAbortedError):
            return
        super().handle_error(request, client_address)


def run_web_dashboard(port: int = 8080, host: str = "0.0.0.0"):
    import os
    port = int(os.environ.get("PORT", port))
    host = os.environ.get("HOST", "0.0.0.0")
    srv = SilentThreadingHTTPServer((host, port), Handler)
    print("=" * 84)
    print("  ICT SENTINEL AI — COMMAND CENTER WITH LIVE ACTIVITY RADAR")
    print(f"  Open in Browser: http://{host}:{port}")
    print("  Dual-Column Workspace · Live Activity Stream · Risk Safeguards")
    print("=" * 84)
    print("[*] Stream active. Press Ctrl+C in terminal to shutdown.\n")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n[!] Shutting down.")
        BOT.stop()
        srv.server_close()
