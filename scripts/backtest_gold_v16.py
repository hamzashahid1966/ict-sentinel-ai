#!/usr/bin/env python3
"""
Institutional Backtesting Engine for Core Gold Model (v1.6)
Validates Pine Script v1.6 across 6+ months of historical 5m Gold data (PAXGUSDT / XAUUSD).
"""

import os
import json
import math
from datetime import datetime, timezone

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "gold")
DATA_FILE = os.path.join(DATA_DIR, "gold_5m_may_nov_2026.json")

def run_backtest(initial_capital=10000.0, risk_pct=0.5, rr_ratio=1.6, max_trades_per_day=3):
    if not os.path.exists(DATA_FILE):
        print(f"Error: {DATA_FILE} not found. Run fetch_gold_data.py first.")
        return

    with open(DATA_FILE, 'r') as f:
        bars = json.load(f)

    print(f"Loaded {len(bars)} continuous 5-minute bars.")
    start_dt = datetime.fromtimestamp(bars[0]['time'] / 1000, tz=timezone.utc)
    end_dt = datetime.fromtimestamp(bars[-1]['time'] / 1000, tz=timezone.utc)
    print(f"Period: {start_dt.strftime('%Y-%m-%d %H:%M')} to {end_dt.strftime('%Y-%m-%d %H:%M')} UTC")

    # 1. Precalculate Timestamps and Dates
    for b in bars:
        dt = datetime.fromtimestamp(b['time'] / 1000, tz=timezone.utc)
        b['dt'] = dt
        b['date_str'] = dt.strftime('%Y-%m-%d')
        b['hour'] = dt.hour
        b['minute'] = dt.minute

    # 2. Build Hourly (H1) Bars and EMAs
    h1_bars = []
    curr_h1 = None
    
    for b in bars:
        hour_key = b['dt'].strftime('%Y-%m-%d %H:00')
        if curr_h1 is None or curr_h1['key'] != hour_key:
            if curr_h1 is not None:
                h1_bars.append(curr_h1)
            curr_h1 = {
                'key': hour_key,
                'open': b['open'],
                'high': b['high'],
                'low': b['low'],
                'close': b['close'],
                'end_time': b['time']
            }
        else:
            curr_h1['high'] = max(curr_h1['high'], b['high'])
            curr_h1['low'] = min(curr_h1['low'], b['low'])
            curr_h1['close'] = b['close']
            curr_h1['end_time'] = b['time']
    if curr_h1 is not None:
        h1_bars.append(curr_h1)

    # Compute H1 EMAs (20 and 50)
    alpha_h1_20 = 2.0 / (20.0 + 1.0)
    alpha_h1_50 = 2.0 / (50.0 + 1.0)
    
    h1_ema20 = []
    h1_ema50 = []
    
    prev_ema20 = h1_bars[0]['close']
    prev_ema50 = h1_bars[0]['close']
    
    for hb in h1_bars:
        c = hb['close']
        prev_ema20 = alpha_h1_20 * c + (1.0 - alpha_h1_20) * prev_ema20
        prev_ema50 = alpha_h1_50 * c + (1.0 - alpha_h1_50) * prev_ema50
        hb['ema20'] = prev_ema20
        hb['ema50'] = prev_ema50

    # Map H1 closed EMAs into a lookup table by hour key
    h1_lookup = {hb['key']: hb for hb in h1_bars}

    # 3. Compute M5 20 EMA
    alpha_m5_20 = 2.0 / (20.0 + 1.0)
    prev_m5 = bars[0]['close']
    for b in bars:
        prev_m5 = alpha_m5_20 * b['close'] + (1.0 - alpha_m5_20) * prev_m5
        b['m5_ema'] = prev_m5

    # 4. Compute Daily & Asia High/Low levels
    # Asia session: 00:00 to 07:00 UTC
    daily_stats = {}
    for b in bars:
        d = b['date_str']
        if d not in daily_stats:
            daily_stats[d] = {
                'high': b['high'],
                'low': b['low'],
                'asia_high': None,
                'asia_low': None,
                'asia_high_running': -1e9,
                'asia_low_running': 1e9
            }
        ds = daily_stats[d]
        ds['high'] = max(ds['high'], b['high'])
        ds['low'] = min(ds['low'], b['low'])
        
        if 0 <= b['hour'] < 7:
            ds['asia_high_running'] = max(ds['asia_high_running'], b['high'])
            ds['asia_low_running'] = min(ds['asia_low_running'], b['low'])
            ds['asia_high'] = ds['asia_high_running']
            ds['asia_low'] = ds['asia_low_running']

    # Get sorted days for PDH/PDL
    sorted_days = sorted(daily_stats.keys())
    for idx, d in enumerate(sorted_days):
        if idx > 0:
            daily_stats[d]['pdh'] = daily_stats[sorted_days[idx-1]]['high']
            daily_stats[d]['pdl'] = daily_stats[sorted_days[idx-1]]['low']
        else:
            daily_stats[d]['pdh'] = None
            daily_stats[d]['pdl'] = None

    # 5. Run Strategy Execution Simulation
    equity = initial_capital
    peak_equity = initial_capital
    max_drawdown = 0.0
    max_drawdown_pct = 0.0

    trades = []
    daily_trades_count = {}
    
    current_day = None
    bull_broken = False
    bear_broken = False
    active_bull_level = None
    active_bear_level = None

    open_trade = None

    for i in range(2, len(bars)):
        b = bars[i]
        b_prev = bars[i-1]
        b_prev2 = bars[i-2]
        d = b['date_str']

        # Manage open trade first
        if open_trade is not None:
            hit_sl = False
            hit_tp = False
            exit_price = None

            if open_trade['side'] == 'LONG':
                if b['low'] <= open_trade['sl']:
                    hit_sl = True
                    exit_price = open_trade['sl']
                elif b['high'] >= open_trade['tp']:
                    hit_tp = True
                    exit_price = open_trade['tp']
            elif open_trade['side'] == 'SHORT':
                if b['high'] >= open_trade['sl']:
                    hit_sl = True
                    exit_price = open_trade['sl']
                elif b['low'] <= open_trade['tp']:
                    hit_tp = True
                    exit_price = open_trade['tp']

            if hit_sl or hit_tp:
                # Calculate PnL with slippage ($2) and commission ($0.04/contract)
                qty = open_trade['qty']
                if open_trade['side'] == 'LONG':
                    gross_pnl = (exit_price - open_trade['entry']) * qty
                else:
                    gross_pnl = (open_trade['entry'] - exit_price) * qty
                
                commission = qty * 0.04 * 2
                slippage = (2.0 if hit_sl else 0.0) * qty # slippage on stop hits
                net_pnl = gross_pnl - commission - slippage

                equity += net_pnl
                peak_equity = max(peak_equity, equity)
                dd = peak_equity - equity
                dd_pct = (dd / peak_equity) * 100.0 if peak_equity > 0 else 0
                max_drawdown = max(max_drawdown, dd)
                max_drawdown_pct = max(max_drawdown_pct, dd_pct)

                open_trade['exit_time'] = b['dt']
                open_trade['exit_price'] = exit_price
                open_trade['net_pnl'] = net_pnl
                open_trade['return_pct'] = (net_pnl / (open_trade['equity_at_entry'])) * 100.0
                open_trade['result'] = 'WIN' if net_pnl > 0 else 'LOSS'
                trades.append(open_trade)
                open_trade = None

        # Reset daily state
        if d != current_day:
            current_day = d
            bull_broken = False
            bear_broken = False
            active_bull_level = None
            active_bear_level = None
            if d not in daily_trades_count:
                daily_trades_count[d] = 0

        # Session filter: 07:00 to 17:00 UTC
        in_trade_session = (7 <= b['hour'] < 17)
        if not in_trade_session:
            active_bull_level = None
            active_bear_level = None
            continue

        if daily_trades_count[d] >= max_trades_per_day:
            continue

        if open_trade is not None:
            continue

        ds = daily_stats[d]
        asia_high = ds['asia_high']
        asia_low = ds['asia_low']

        if asia_high is None or asia_low is None:
            continue

        # Fetch H1 regime from previous closed hour
        prev_hour_dt = datetime.fromtimestamp(b['time'] / 1000 - 3600, tz=timezone.utc)
        prev_hour_key = prev_hour_dt.strftime('%Y-%m-%d %H:00')
        hb = h1_lookup.get(prev_hour_key)
        if hb is None:
            continue

        h1_bullish = (hb['ema20'] > hb['ema50']) and (b['close'] > hb['ema20'])
        h1_bearish = (hb['ema20'] < hb['ema50']) and (b['close'] < hb['ema20'])

        # Track Breakouts
        if h1_bullish and not bull_broken:
            if b['close'] > asia_high and b_prev['close'] <= asia_high:
                bull_broken = True
                active_bull_level = asia_high

        if h1_bearish and not bear_broken:
            if b['close'] < asia_low and b_prev['close'] >= asia_low:
                bear_broken = True
                active_bear_level = asia_low

        # Entry Signals
        swing_high2 = max(b_prev['high'], b_prev2['high'])
        swing_low2 = min(b_prev['low'], b_prev2['low'])

        # Signal 1: IMP-Long
        condA_Long = (h1_bullish and active_bull_level is not None and
                      b_prev['low'] >= active_bull_level - 1.0 and
                      b_prev['close'] >= b_prev['m5_ema'] and
                      b['close'] > swing_high2 and b_prev['close'] <= swing_high2)

        # Signal 2: IMP-Short
        condA_Short = (h1_bearish and active_bear_level is not None and
                       b_prev['high'] <= active_bear_level + 1.0 and
                       b_prev['close'] <= b_prev['m5_ema'] and
                       b['close'] < swing_low2 and b_prev['close'] >= swing_low2)

        # Signal 3: Sweep-Buy
        condB_Buy = ((b_prev['low'] < asia_low or b_prev2['low'] < asia_low) and
                     b_prev['close'] <= asia_low and b['close'] > asia_low and
                     b['close'] > b['open'])

        # Signal 4: Sweep-Sell
        condB_Sell = ((b_prev['high'] > asia_high or b_prev2['high'] > asia_high) and
                      b_prev['close'] >= asia_high and b['close'] < asia_high and
                      b['close'] < b['open'])

        # Execute Entry
        risk_cash = initial_capital * (risk_pct / 100.0) # $50 fixed fraction
        entry_price = b['close']

        if condA_Long or condB_Buy:
            sig = "IMP-Long" if condA_Long else "Sweep-Buy"
            if condA_Long:
                sl = min(b['low'], swing_low2) - 0.50
            else:
                sl = min(b['low'], b_prev['low']) - 0.50
            sl_dist = entry_price - sl
            if 1.50 <= sl_dist <= 15.0:
                qty = max(1, round(risk_cash / sl_dist))
                tp = entry_price + (sl_dist * rr_ratio)
                open_trade = {
                    'side': 'LONG',
                    'signal': sig,
                    'entry_time': b['dt'],
                    'entry': entry_price,
                    'sl': sl,
                    'tp': tp,
                    'qty': qty,
                    'equity_at_entry': equity
                }
                daily_trades_count[d] += 1
                active_bull_level = None

        elif condA_Short or condB_Sell:
            sig = "IMP-Short" if condA_Short else "Sweep-Sell"
            if condA_Short:
                sl = max(b['high'], swing_high2) + 0.50
            else:
                sl = max(b['high'], b_prev['high']) + 0.50
            sl_dist = sl - entry_price
            if 1.50 <= sl_dist <= 15.0:
                qty = max(1, round(risk_cash / sl_dist))
                tp = entry_price - (sl_dist * rr_ratio)
                open_trade = {
                    'side': 'SHORT',
                    'signal': sig,
                    'entry_time': b['dt'],
                    'entry': entry_price,
                    'sl': sl,
                    'tp': tp,
                    'qty': qty,
                    'equity_at_entry': equity
                }
                daily_trades_count[d] += 1
                active_bear_level = None

    # Performance Analysis
    total_trades = len(trades)
    if total_trades == 0:
        print("No trades triggered.")
        return

    wins = [t for t in trades if t['result'] == 'WIN']
    losses = [t for t in trades if t['result'] == 'LOSS']

    win_rate = (len(wins) / total_trades) * 100.0
    gross_profit = sum(t['net_pnl'] for t in wins)
    gross_loss = abs(sum(t['net_pnl'] for t in losses))
    net_pnl = sum(t['net_pnl'] for t in trades)
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float('inf')

    avg_win = (gross_profit / len(wins)) if wins else 0
    avg_loss = (gross_loss / len(losses)) if losses else 0
    payoff_ratio = (avg_win / avg_loss) if avg_loss > 0 else float('inf')
    expectancy = (net_pnl / total_trades)

    # Buy and Hold comparison
    gold_start = bars[0]['close']
    gold_end = bars[-1]['close']
    gold_return_pct = ((gold_end - gold_start) / gold_start) * 100.0

    print("\n" + "="*70)
    print("  INSTITUTIONAL QUANT REPORT: CORE GOLD MODEL (v1.6)")
    print("="*70)
    print(f"  Period Tested:           {start_dt.strftime('%b %d, %Y')} to {end_dt.strftime('%b %d, %Y')} ({round((bars[-1]['time'] - bars[0]['time'])/(86400*1000))} Days)")
    print(f"  Initial Capital:         ${initial_capital:,.2f} USD")
    print(f"  Final Equity:            ${equity:,.2f} USD")
    print(f"  Net Profit:              ${net_pnl:+,.2f} USD ({(net_pnl/initial_capital)*100:+.2f}%)")
    print(f"  Buy & Hold Gold Return:  {gold_return_pct:+.2f}%")
    print(f"  Alpha Generated:         {((net_pnl/initial_capital)*100 - gold_return_pct):+.2f}%")
    print(f"  Profit Factor:           {profit_factor:.3f}")
    print(f"  Max Drawdown:            ${max_drawdown:,.2f} USD ({max_drawdown_pct:.2f}%)")
    print(f"  Total Trades:            {total_trades}")
    print(f"  Win Rate:                {win_rate:.2f}% ({len(wins)}W / {len(losses)}L)")
    print(f"  Average Win:             ${avg_win:,.2f}")
    print(f"  Average Loss:            ${avg_loss:,.2f}")
    print(f"  Payoff Ratio (R):        {payoff_ratio:.2f}:1")
    print(f"  Per-Trade Expectancy:    ${expectancy:+,.2f} USD")
    print("="*70)

    # Signal Breakdown
    print("\n--- PERFORMANCE BY ENGINE / SIGNAL ---")
    signals = ["IMP-Short", "Sweep-Buy", "IMP-Long", "Sweep-Sell"]
    for s in signals:
        s_trades = [t for t in trades if t['signal'] == s]
        if s_trades:
            s_wins = [t for t in s_trades if t['result'] == 'WIN']
            s_pnl = sum(t['net_pnl'] for t in s_trades)
            s_wr = (len(s_wins) / len(s_trades)) * 100.0
            print(f"  {s:<12}: {len(s_trades):>2} trades | {s_wr:>5.1f}% WR | PnL: ${s_pnl:>+8.2f} USD")

    # Monthly Breakdown
    print("\n--- MONTHLY PERFORMANCE BREAKDOWN ---")
    month_keys = sorted(list(set(t['entry_time'].strftime('%Y-%m') for t in trades)))
    for m in month_keys:
        m_trades = [t for t in trades if t['entry_time'].strftime('%Y-%m') == m]
        m_wins = [t for t in m_trades if t['result'] == 'WIN']
        m_pnl = sum(t['net_pnl'] for t in m_trades)
        m_wr = (len(m_wins) / len(m_trades)) * 100.0 if m_trades else 0
        status = "PROFITABLE" if m_pnl > 0 else "DRAWDOWN"
        print(f"  {m}: {len(m_trades):>2} trades | {m_wr:>5.1f}% WR | Net: ${m_pnl:>+8.2f} USD [{status}]")

    print("="*70 + "\n")

    # Save results to JSON for documentation
    summary_path = os.path.join(DATA_DIR, "backtest_v16_summary.json")
    with open(summary_path, 'w') as f:
        json.dump({
            'period': f"{start_dt.strftime('%Y-%m-%d')} to {end_dt.strftime('%Y-%m-%d')}",
            'initial_capital': initial_capital,
            'final_equity': equity,
            'net_pnl': net_pnl,
            'profit_factor': profit_factor,
            'win_rate': win_rate,
            'total_trades': total_trades,
            'max_drawdown_pct': max_drawdown_pct,
            'gold_return_pct': gold_return_pct,
            'trades': [{
                'entry_time': t['entry_time'].strftime('%Y-%m-%d %H:%M'),
                'exit_time': t['exit_time'].strftime('%Y-%m-%d %H:%M'),
                'side': t['side'],
                'signal': t['signal'],
                'entry': t['entry'],
                'exit': t['exit_price'],
                'pnl': t['net_pnl'],
                'result': t['result']
            } for t in trades]
        }, f, indent=2)

if __name__ == "__main__":
    run_backtest()

