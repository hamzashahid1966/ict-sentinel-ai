#!/usr/bin/env python3
import json
import math
from datetime import datetime, timezone

with open('data/gold/gold_5m_weekdays.json') as f:
    bars = json.load(f)

for b in bars:
    dt = datetime.fromtimestamp(b['time'] / 1000, tz=timezone.utc)
    b['dt'] = dt
    b['date_str'] = dt.strftime('%Y-%m-%d')
    b['hour'] = dt.hour

# 1. H1 Bars and EMAs
h1_bars = []
curr_h1 = None
for b in bars:
    hour_key = b['dt'].strftime('%Y-%m-%d %H:00')
    if curr_h1 is None or curr_h1['key'] != hour_key:
        if curr_h1 is not None:
            h1_bars.append(curr_h1)
        curr_h1 = {'key': hour_key, 'open': b['open'], 'high': b['high'], 'low': b['low'], 'close': b['close']}
    else:
        curr_h1['high'] = max(curr_h1['high'], b['high'])
        curr_h1['low'] = min(curr_h1['low'], b['low'])
        curr_h1['close'] = b['close']
if curr_h1 is not None:
    h1_bars.append(curr_h1)

alpha20 = 2.0 / 21.0
alpha50 = 2.0 / 51.0
e20 = h1_bars[0]['close']
e50 = h1_bars[0]['close']
for hb in h1_bars:
    e20 = alpha20 * hb['close'] + (1 - alpha20) * e20
    e50 = alpha50 * hb['close'] + (1 - alpha50) * e50
    hb['ema20'] = e20
    hb['ema50'] = e50
h1_lookup = {hb['key']: hb for hb in h1_bars}

# M5 EMA
prev_m5 = bars[0]['close']
for b in bars:
    prev_m5 = alpha20 * b['close'] + (1 - alpha20) * prev_m5
    b['m5_ema'] = prev_m5

# Daily levels
daily_stats = {}
for b in bars:
    d = b['date_str']
    if d not in daily_stats:
        daily_stats[d] = {'asia_high': -1e9, 'asia_low': 1e9}
    if 0 <= b['hour'] < 7:
        daily_stats[d]['asia_high'] = max(daily_stats[d]['asia_high'], b['high'])
        daily_stats[d]['asia_low'] = min(daily_stats[d]['asia_low'], b['low'])

def simulate(filter_sweep_by_trend=True, enable_imp=True, enable_sweep=True, min_sweep_dist=1.5, rr_ratio=1.6):
    trades = []
    equity = 10000.0
    open_trade = None
    daily_count = {}
    current_day = None
    bull_broken = False
    bear_broken = False
    active_bull_level = None
    active_bear_level = None

    for i in range(2, len(bars)):
        b = bars[i]
        b_prev = bars[i-1]
        b_prev2 = bars[i-2]
        d = b['date_str']

        if open_trade is not None:
            hit_sl = False
            hit_tp = False
            exit_p = None
            if open_trade['side'] == 'LONG':
                if b['low'] <= open_trade['sl']:
                    hit_sl = True
                    exit_p = open_trade['sl']
                elif b['high'] >= open_trade['tp']:
                    hit_tp = True
                    exit_p = open_trade['tp']
            else:
                if b['high'] >= open_trade['sl']:
                    hit_sl = True
                    exit_p = open_trade['sl']
                elif b['low'] <= open_trade['tp']:
                    hit_tp = True
                    exit_p = open_trade['tp']

            if hit_sl or hit_tp:
                qty = open_trade['qty']
                gross = (exit_p - open_trade['entry']) * qty if open_trade['side'] == 'LONG' else (open_trade['entry'] - exit_p) * qty
                net = gross - (qty * 0.04 * 2) - ((2.0 if hit_sl else 0.0) * qty)
                open_trade['net_pnl'] = net
                open_trade['result'] = 'WIN' if net > 0 else 'LOSS'
                trades.append(open_trade)
                equity += net
                open_trade = None

        if d != current_day:
            current_day = d
            bull_broken = False
            bear_broken = False
            active_bull_level = None
            active_bear_level = None
            daily_count[d] = 0

        if not (7 <= b['hour'] < 17):
            active_bull_level = None
            active_bear_level = None
            continue

        if daily_count[d] >= 3 or open_trade is not None:
            continue

        ds = daily_stats[d]
        asia_high = ds['asia_high']
        asia_low = ds['asia_low']
        if asia_high <= 0 or asia_low >= 1e8:
            continue

        prev_hour_key = datetime.fromtimestamp(b['time'] / 1000 - 3600, tz=timezone.utc).strftime('%Y-%m-%d %H:00')
        hb = h1_lookup.get(prev_hour_key)
        if hb is None:
            continue

        h1_bull = (hb['ema20'] > hb['ema50']) and (b['close'] > hb['ema20'])
        h1_bear = (hb['ema20'] < hb['ema50']) and (b['close'] < hb['ema20'])

        # IMP Tracking
        if h1_bull and not bull_broken and b['close'] > asia_high and b_prev['close'] <= asia_high:
            bull_broken = True
            active_bull_level = asia_high
        if h1_bear and not bear_broken and b['close'] < asia_low and b_prev['close'] >= asia_low:
            bear_broken = True
            active_bear_level = asia_low

        sw_h = max(b_prev['high'], b_prev2['high'])
        sw_l = min(b_prev['low'], b_prev2['low'])

        # IMP Long / Short
        imp_l = enable_imp and h1_bull and active_bull_level is not None and b_prev['low'] >= active_bull_level - 1.0 and b_prev['close'] >= b_prev['m5_ema'] and b['close'] > sw_h and b_prev['close'] <= sw_h
        imp_s = enable_imp and h1_bear and active_bear_level is not None and b_prev['high'] <= active_bear_level + 1.0 and b_prev['close'] <= b_prev['m5_ema'] and b['close'] < sw_l and b_prev['close'] >= sw_l

        # Sweep Buy / Sell
        # When filter_sweep_by_trend is True, ONLY buy sweeps if H1 is bullish (or not bearish), and ONLY sell sweeps if H1 is bearish (or not bullish)
        # Also require the sweep to have meaningfully pierced Asia Low (e.g. by at least min_sweep_dist) to avoid microscopic noise!
        pierced_low = min(b_prev['low'], b_prev2['low'])
        pierced_high = max(b_prev['high'], b_prev2['high'])

        sweep_l = enable_sweep and (not filter_sweep_by_trend or h1_bull) and (asia_low - pierced_low >= min_sweep_dist) and b_prev['close'] <= asia_low and b['close'] > asia_low and b['close'] > b['open']
        sweep_s = enable_sweep and (not filter_sweep_by_trend or h1_bear) and (pierced_high - asia_high >= min_sweep_dist) and b_prev['close'] >= asia_high and b['close'] < asia_high and b['close'] < b['open']

        risk_cash = 50.0
        entry = b['close']

        if imp_l or sweep_l:
            sig = "IMP-Long" if imp_l else "Sweep-Buy"
            sl = (min(b['low'], sw_l) if imp_l else min(b['low'], b_prev['low'])) - 0.50
            sl_d = entry - sl
            if 1.5 <= sl_d <= 15.0:
                qty = max(1, round(risk_cash / sl_d))
                open_trade = {'side': 'LONG', 'signal': sig, 'entry': entry, 'sl': sl, 'tp': entry + sl_d * rr_ratio, 'qty': qty, 'time': b['dt']}
                daily_count[d] += 1
                active_bull_level = None

        elif imp_s or sweep_s:
            sig = "IMP-Short" if imp_s else "Sweep-Sell"
            sl = (max(b['high'], sw_h) if imp_s else max(b['high'], b_prev['high'])) + 0.50
            sl_d = sl - entry
            if 1.5 <= sl_d <= 15.0:
                qty = max(1, round(risk_cash / sl_d))
                open_trade = {'side': 'SHORT', 'signal': sig, 'entry': entry, 'sl': sl, 'tp': entry - sl_d * rr_ratio, 'qty': qty, 'time': b['dt']}
                daily_count[d] += 1
                active_bear_level = None

    if not trades:
        return 0, 0, 0, 0
    wins = [t for t in trades if t['result'] == 'WIN']
    losses = [t for t in trades if t['result'] == 'LOSS']
    gp = sum(t['net_pnl'] for t in wins)
    gl = abs(sum(t['net_pnl'] for t in losses))
    net = sum(t['net_pnl'] for t in trades)
    pf = (gp / gl) if gl > 0 else 0
    wr = (len(wins) / len(trades)) * 100
    return len(trades), wr, pf, net

print("Simulating configurations across 6+ months (May - Nov 2026):")
print("-" * 65)
print(f"{'Configuration':<35} | {'Trades':<6} | {'WR%':<6} | {'PF':<5} | {'Net PnL':<10}")
print("-" * 65)

configs = [
    ("v1.6 Naive (Both, No Trend Sweep)", False, True, True, 0.0),
    ("v1.6 with Trend-Filtered Sweeps", True, True, True, 0.0),
    ("Trend Sweeps + Min Sweep ($1.50)", True, True, True, 1.5),
    ("Trend Sweeps + Min Sweep ($2.00)", True, True, True, 2.0),
    ("IMP Only (No Sweeps)", False, True, False, 0.0),
    ("IMP Only + 2.0R Target", False, True, False, 0.0, 2.0),
]

for item in configs:
    name = item[0]
    filt = item[1]
    e_imp = item[2]
    e_sw = item[3]
    m_dist = item[4]
    rr = item[5] if len(item) > 5 else 1.6
    n, wr, pf, net = simulate(filter_sweep_by_trend=filt, enable_imp=e_imp, enable_sweep=e_sw, min_sweep_dist=m_dist, rr_ratio=rr)
    print(f"{name:<35} | {n:<6} | {wr:<6.1f} | {pf:<5.2f} | ${net:>+8.2f}")

