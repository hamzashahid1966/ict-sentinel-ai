#!/usr/bin/env python3
"""
ICT Sentinel AI - Main Autonomous Entrypoint & CLI Controller
Supports:
  python main.py --run        : Runs the continuous live real-time paper trading engine
  python main.py --status     : Displays the current portfolio metrics & open positions
  python main.py --audit      : Displays historical trade logs and AI reasoning
  python main.py --memory     : Displays the Adaptive Memory, Bayesian Quality Scores & learned reflections
  python main.py --demo-run   : Executes an accelerated multi-asset live simulation
"""

import sys
import time
import argparse
import datetime
from ict_sentinel.config import ASSET_SPECS
from ict_sentinel.models import Candle
from ict_sentinel.storage import StorageEngine
from ict_sentinel.data_feed import DataFeedEngine
from ict_sentinel.ipda_engine import IPDAEngine
from ict_sentinel.ai_advisor import AIAdvisor
from ict_sentinel.order_manager import OrderManager
from ict_sentinel.dashboard import DashboardRenderer
from ict_sentinel.memory_engine import MemoryEngine

def run_agent_cycle(data_feed: DataFeedEngine, ipda: IPDAEngine, order_mgr: OrderManager, storage: StorageEngine, advisor: AIAdvisor, memory_engine: MemoryEngine):
    now_et = datetime.datetime.now(datetime.timezone.utc).astimezone(datetime.timezone(datetime.timedelta(hours=-5)))
    active_session = ipda.get_current_session(now_et.time()) or "OFF-SESSION (WAITING)"
    prices = {}

    for asset in ASSET_SPECS:
        candles = data_feed.fetch_recent_bars(asset, interval="5m", limit=60)
        if not candles:
            continue

        current_bar = candles[-1]
        prices[asset] = current_bar.close

        # 1. Update existing positions (Check Center Mass 1.5R, Trailing Stops & trigger Memory post-mortem)
        order_mgr.update_positions_with_bar(asset, current_bar)

        # 2. Evaluate for new algorithmic setups with Memory Engine gating
        signal = ipda.evaluate_market(asset, candles, memory_engine=memory_engine)
        if signal:
            order_mgr.open_position_from_signal(signal, current_bar.timestamp_et)

    # Render Telemetry Dashboard with Adaptive Memory
    account = storage.get_account_state()
    open_positions = storage.load_open_positions()
    trades = storage.get_trade_history()
    recent_logs = storage.get_recent_ai_logs(limit=5)
    weights = memory_engine.get_all_weights()
    reflections = memory_engine.get_recent_reflections(limit=3)
    DashboardRenderer.render(
        account=account,
        open_positions=open_positions,
        trades=trades,
        recent_logs=recent_logs,
        prices=prices,
        active_session=active_session,
        adaptive_weights=weights,
        reflections=reflections
    )

def show_status(storage: StorageEngine):
    account = storage.get_account_state()
    open_positions = storage.load_open_positions()
    trades = storage.get_trade_history()
    wins = [t for t in trades if t.dollar_pnl > 0]
    losses = [t for t in trades if t.dollar_pnl < 0]
    total = len(trades)
    win_rate = (len(wins) / total * 100.0) if total > 0 else 0.0

    print("=" * 80)
    print("  ICT SENTINEL AI — PORTFOLIO STATUS")
    print("=" * 80)
    print(f"  Account Balance:       ${account.balance:9.2f}")
    print(f"  Peak Balance:          ${account.peak_balance:9.2f}")
    print(f"  Realized Net PnL:      ${account.realized_pnl:+9.2f}")
    print(f"  Win Rate:              {win_rate:6.1f}% ({len(wins)}W / {len(losses)}L)")
    print(f"  Max Drawdown:          ${account.max_drawdown_dollars:6.2f} ({account.max_drawdown_pct:.1f}%)")
    print(f"  Open Positions:        {len(open_positions)}")
    print("-" * 80)
    if open_positions:
        print("  ACTIVE OPEN POSITIONS:")
        for p in open_positions:
            print(f"    [{p.asset}] {p.direction} @ {p.entry_price:.2f} | Stop: {p.active_trailing_stop:.2f} | CM Target: {p.target_center_mass:.2f} | Status: {p.status}")
    else:
        print("  No open positions currently.")
    print("=" * 80)

def show_memory(memory_engine: MemoryEngine, storage: StorageEngine):
    weights = memory_engine.get_all_weights()
    reflections = memory_engine.get_recent_reflections(limit=20)

    print("=" * 95)
    print("  ICT SENTINEL AI — ADAPTIVE MEMORY & SELF-LEARNING INTELLIGENCE")
    print("=" * 95)
    print("\n[ 1. DYNAMIC BAYESIAN QUALITY SCORES & REGIME STATUS ]")
    if not weights:
        print("  (No regime history recorded yet. Bot will update memory automatically as trades complete.)")
    else:
        print(f"  {'REGIME':<22} | {'RECORD':<10} | {'BAYESIAN SCORE':<16} | {'STATUS':<15} | {'CONSECUTIVE LOSSES'}")
        print("  " + "-" * 88)
        for w in weights:
            rec_str = f"{w['wins']}W / {w['losses']}L"
            print(f"  {w['key_pair']:<22} | {rec_str:<10} | {w['quality_score']*100:13.1f}% | {w['status']:<15} | {w['consecutive_losses']}")

    print("\n[ 2. INSTITUTIONAL POST-MORTEM REFLECTIONS & LESSONS LEARNED ]")
    if not reflections:
        print("  (Awaiting first closed trade reflection...)")
    else:
        for r in reflections:
            print(f"  [{r['timestamp']}] [{r['asset']}::{r['session']}] Reflection: {r['reflection_type']}")
            print(f"    ├─ Lesson: {r['lesson']}")
            print(f"    └─ Action Taken: {r['action_taken']}\n")
    print("=" * 95)

def show_audit(storage: StorageEngine):
    trades = storage.get_trade_history(limit=50)
    logs = storage.get_recent_ai_logs(limit=20)

    print("=" * 90)
    print("  ICT SENTINEL AI — COMPLETE HISTORICAL AUDIT & REASONING LOG")
    print("=" * 90)
    if not trades:
        print("  No closed trades recorded yet.")
    else:
        print(f"  {'DATE / TIME':<20} | {'ASSET':<8} | {'DIR':<5} | {'ENTRY':<10} | {'EXIT':<10} | {'OUTCOME':<15} | {'NET PNL'}")
        print("  " + "-" * 86)
        for t in trades:
            print(f"  {t.exit_time:<20} | {t.asset:<8} | {t.direction:<5} | {t.entry_price:<10.2f} | {t.exit_price:<10.2f} | {t.outcome:<15} | ${t.dollar_pnl:+7.2f}")

    print("\n" + "=" * 90)
    print("  RECENT AI INSTITUTIONAL REASONING LOGS:")
    print("-" * 90)
    for l in logs:
        print(f"  [{l.timestamp}] [{l.asset}] {l.message}")
        for r in l.reasoning.split('\n'):
            print(f"    └─ {r}")
    print("=" * 90)

def run_demo_simulation(storage: StorageEngine, ipda: IPDAEngine, advisor: AIAdvisor, order_mgr: OrderManager, memory_engine: MemoryEngine):
    """
    Executes an accelerated multi-asset paper trading simulation using
    real CME and Forex market data to verify all system components.
    """
    from ict_sentinel.config import BASE_DIR
    import os
    import pandas as pd

    data_files = {
        'GOLD': os.path.join(BASE_DIR, '..', 'real_data', 'GC_F_5m_60d.csv'),
        'SILVER': os.path.join(BASE_DIR, '..', 'real_data', 'SI_F_5m_60d.csv'),
        'NASDAQ': os.path.join(BASE_DIR, '..', 'real_data', 'NQ_F_5m_60d.csv'),
        'GBPUSD': os.path.join(BASE_DIR, '..', 'real_data', 'GBPUSD_5m_60d.csv'),
        'EURUSD': os.path.join(BASE_DIR, '..', 'real_data', 'EURUSD_5m_60d.csv'),
    }

    print("\n[*] Starting accelerated multi-asset paper trading simulation with Self-Learning Memory...")
    for asset, path in data_files.items():
        if not os.path.exists(path):
            continue
        print(f"[*] Processing {asset} live tape simulation...")
        df = pd.read_csv(path)
        dt_col = 'Datetime' if 'Datetime' in df.columns else 'Date'
        df[dt_col] = pd.to_datetime(df[dt_col], utc=True)
        df['Datetime_ET'] = df[dt_col].dt.tz_convert('US/Eastern')

        # Run bar by bar over recent 1500 bars (~2 weeks of real continuous market tape)
        recent_df = df.tail(1500).reset_index(drop=True)
        rolling_candles = []

        for idx, row in recent_df.iterrows():
            c = from_row = Candle(
                timestamp=row[dt_col].to_pydatetime(),
                timestamp_et=row['Datetime_ET'].to_pydatetime(),
                open=float(row['Open']),
                high=float(row['High']),
                low=float(row['Low']),
                close=float(row['Close']),
                volume=float(row.get('Volume', 0))
            )
            rolling_candles.append(c)
            if len(rolling_candles) > 60:
                rolling_candles.pop(0)

            if len(rolling_candles) >= 20:
                order_mgr.update_positions_with_bar(asset, c)
                sig = ipda.evaluate_market(asset, rolling_candles, memory_engine=memory_engine)
                if sig:
                    order_mgr.open_position_from_signal(sig, c.timestamp_et)

    print("[+] Accelerated paper trading simulation completed successfully!\n")
    show_status(storage)
    show_memory(memory_engine, storage)

def main():
    parser = argparse.ArgumentParser(description="ICT Sentinel AI - Autonomous Paper Trading Engine")
    parser.add_argument("--run", action="store_true", help="Run the continuous live real-time paper trading engine")
    parser.add_argument("--web", action="store_true", help="Launch the interactive Web Control Center (browser GUI)")
    parser.add_argument("--port", type=int, default=8080, help="Web dashboard port (default: 8080)")
    parser.add_argument("--status", action="store_true", help="Display current account status and open positions")
    parser.add_argument("--audit", action="store_true", help="Display trade audit and AI reasoning history")
    parser.add_argument("--memory", action="store_true", help="Display Adaptive Memory, Bayesian Quality Scores & reflections")
    parser.add_argument("--demo-run", action="store_true", help="Run accelerated simulation on real data")
    parser.add_argument("--interval", type=int, default=15, help="Polling interval in seconds (default: 15)")

    args = parser.parse_args()

    storage = StorageEngine()
    advisor = AIAdvisor()
    memory_engine = MemoryEngine(storage, advisor)
    order_mgr = OrderManager(storage, advisor, memory_engine=memory_engine)
    ipda = IPDAEngine()
    data_feed = DataFeedEngine(mode="live")

    if args.web:
        from ict_sentinel.web_server import run_web_dashboard
        run_web_dashboard(port=args.port)
        return

    if args.status:
        show_status(storage)
        return

    if args.audit:
        show_audit(storage)
        return

    if args.memory:
        show_memory(memory_engine, storage)
        return

    if args.demo_run:
        run_demo_simulation(storage, ipda, advisor, order_mgr, memory_engine)
        return

    # Default action or --run: Execute continuous monitoring loop
    print("[*] Launching ICT Sentinel AI Autonomous Engine...")
    print("[*] Press Ctrl+C to stop.\n")
    try:
        while True:
            run_agent_cycle(data_feed, ipda, order_mgr, storage, advisor, memory_engine)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\n[!] Gracefully shutting down ICT Sentinel AI. State preserved in SQLite database.")

if __name__ == "__main__":
    main()
