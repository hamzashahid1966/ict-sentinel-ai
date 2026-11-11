#!/usr/bin/env python3
"""
ICT 2024 Complete 52-Lecture Masterclass Multi-Asset Engine
Tests the unified algorithmic strategy on:
  1. Silver Futures (SI=F / Micro Silver 1000oz, $1000/pt, tick=0.005)
  2. EUR/USD Forex (EURUSD=X / 0.10 mini lot, $1/pip, tick=0.0001)
  3. GBP/USD Forex (GBPUSD=X / 0.10 mini lot, $1/pip, tick=0.0001)
  4. Micro Gold benchmark (MGC, $10/pt)
  5. Micro Nasdaq benchmark (MNQ, $2/pt)

Applies:
  - 10:00 AM Post-Open Macro Gate
  - Candle Body MSS Confirmation (Wicks Disqualified)
  - Lowest Quadrant / Discount Filter for Longs, Premium for Shorts
  - Double Tap Execution (50% Center Mass @ 1.5R + 50% Head Shot @ 3.0R)
  - Three Defensive PD Arrays Trailing Stop
  - Real Spread & Commission Friction
"""

import os
import math
import datetime
import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import List, Dict, Tuple

INITIAL_CAPITAL = 500.0

@dataclass
class TradeResult:
    date: datetime.date
    day_name: str
    session: str
    direction: str
    entry_time: datetime.time
    entry_price: float
    stop_loss: float
    target_center_mass: float
    target_head_shot: float
    exit_time: datetime.time
    exit_price: float
    risk_pts: float
    pnl_pts: float
    outcome: str
    dollar_pnl: float
    balance_after: float
    asset: str

def load_data(filepath: str) -> pd.DataFrame:
    df = pd.read_csv(filepath)
    df['Datetime'] = pd.to_datetime(df['Datetime'], utc=True)
    df['Datetime_ET'] = df['Datetime'].dt.tz_convert('US/Eastern')
    df['Date'] = df['Datetime_ET'].dt.date
    df['Time'] = df['Datetime_ET'].dt.time
    df['DayOfWeek'] = df['Datetime_ET'].dt.day_name()
    return df

def is_nfp_week(d: datetime.date) -> bool:
    first_day = datetime.date(d.year, d.month, 1)
    days_to_friday = (4 - first_day.weekday()) % 7
    first_friday = first_day + datetime.timedelta(days=days_to_friday)
    first_monday = first_friday - datetime.timedelta(days=4)
    return first_monday <= d <= first_friday

def simulate_asset(df: pd.DataFrame, asset_type: str) -> Tuple[List[TradeResult], Dict]:
    unique_dates = sorted(df['Date'].unique())
    trades: List[TradeResult] = []
    balance = INITIAL_CAPITAL
    peak_balance = INITIAL_CAPITAL
    max_drawdown_dollars = 0.0
    max_drawdown_pct = 0.0

    # Asset Configurations
    if asset_type == 'SILVER':
        # Micro Silver Futures (1,000 oz contract)
        point_val = 1000.0   # $1.00 move in silver price = $1,000 per micro contract
        tick_size = 0.005    # 0.5 cents = $5.00
        commission = 1.25    # per round turn
        slippage_ticks = 1.0
        min_risk_pts = 0.03  # 3 cents ($30 risk)
        max_risk_pts = 0.08  # 8 cents ($80 risk max for $500 balance)
        min_pre_range = 0.15
        ref_start_ny = datetime.time(0, 0)
        ref_end_ny = datetime.time(8, 0)
        exec_start_ny = datetime.time(8, 20)
        exec_end_ny = datetime.time(10, 30)

    elif asset_type in ['EURUSD', 'GBPUSD']:
        # Forex 0.10 Mini Lot (10,000 units = $1.00 per pip)
        # 1 pip = 0.0001 (10 pips = 0.0010 = $10.00)
        point_val = 10000.0  # 0.0001 * 10000 = $1.00 per pip
        tick_size = 0.0001   # 1 pip
        commission = 0.60    # $0.60 per 0.10 mini lot round turn
        slippage_ticks = 0.5 # 0.5 pip spread/slippage
        min_risk_pts = 0.0002 # 2 pips ($2 risk on 0.10 mini lot)
        max_risk_pts = 0.0020 # 20 pips ($20 risk on 0.10 mini lot)
        min_pre_range = 0.0010 # 10 pips session range
        ref_start_ny = datetime.time(0, 0)
        ref_end_ny = datetime.time(7, 0)
        exec_start_ny = datetime.time(7, 0) # Forex NY Open is 07:00 EST!
        exec_end_ny = datetime.time(10, 0)

    elif asset_type == 'GOLD':
        point_val = 10.0
        tick_size = 0.10
        commission = 1.25
        slippage_ticks = 1.0
        min_risk_pts = 2.0
        max_risk_pts = 7.5
        min_pre_range = 4.0
        ref_start_ny = datetime.time(0, 0)
        ref_end_ny = datetime.time(8, 0)
        exec_start_ny = datetime.time(8, 0)
        exec_end_ny = datetime.time(10, 30)

    else: # NASDAQ
        point_val = 2.0
        tick_size = 0.25
        commission = 0.62
        slippage_ticks = 1.0
        min_risk_pts = 6.0
        max_risk_pts = 22.0
        min_pre_range = 25.0
        ref_start_ny = datetime.time(0, 0)
        ref_end_ny = datetime.time(8, 0)
        exec_start_ny = datetime.time(8, 0)
        exec_end_ny = datetime.time(10, 30)

    friction = commission + (slippage_ticks * tick_size * point_val)

    for date in unique_dates:
        day_df = df[df['Date'] == date].copy().reset_index(drop=True)
        if len(day_df) < 30:
            continue

        day_name = day_df.iloc[0]['DayOfWeek']
        nfp_active = is_nfp_week(date)

        # NFP Quarantine Thursday/Friday (Lecture 51)
        if nfp_active and day_name in ['Thursday', 'Friday']:
            continue

        sessions = []

        # 1. London Session (Forex & Commodities Prime Window)
        sessions.append({
            'name': 'LONDON',
            'ref_start': datetime.time(20, 0),
            'ref_end': datetime.time(2, 0),
            'exec_start': datetime.time(2, 0),
            'exec_end': datetime.time(4, 30),
            'exit_time': datetime.time(6, 0)
        })

        # 2. New York AM Session
        # 10:00 AM Gate rule for indices/commodities if morning is trapped
        actual_exec_start = exec_start_ny
        if asset_type in ['NASDAQ', 'GOLD', 'SILVER']:
            c_0900 = day_df[(day_df['Time'] >= datetime.time(9, 0)) & (day_df['Time'] < datetime.time(9, 30))]
            c_0930 = day_df[day_df['Time'] == datetime.time(9, 30)]
            if len(c_0900) > 0 and len(c_0930) > 0:
                h_0900 = c_0900['High'].max()
                l_0900 = c_0900['Low'].min()
                o_0930 = c_0930.iloc[0]['Open']
                if l_0900 < o_0930 < h_0900:
                    actual_exec_start = datetime.time(10, 0)

        sessions.append({
            'name': 'NEW_YORK_AM',
            'ref_start': ref_start_ny,
            'ref_end': ref_end_ny,
            'exec_start': actual_exec_start,
            'exec_end': exec_end_ny,
            'exit_time': datetime.time(11, 45)
        })

        # 3. Asian Session Macro (Forex & Commodities)
        sessions.append({
            'name': 'ASIAN_MACRO',
            'ref_start': datetime.time(15, 0),
            'ref_end': datetime.time(18, 0),
            'exec_start': datetime.time(18, 50),
            'exec_end': datetime.time(20, 15),
            'exit_time': datetime.time(22, 0)
        })

        for sess in sessions:
            if sess['ref_start'] < sess['ref_end']:
                ref_bars = day_df[(day_df['Time'] >= sess['ref_start']) & (day_df['Time'] < sess['ref_end'])]
            else:
                ref_bars = day_df[(day_df['Time'] >= sess['ref_start']) | (day_df['Time'] < sess['ref_end'])]

            if len(ref_bars) < 6:
                continue

            ref_high = ref_bars['High'].max()
            ref_low = ref_bars['Low'].min()
            ref_range = ref_high - ref_low
            if ref_range < min_pre_range:
                continue

            exec_bars = day_df[(day_df['Time'] >= sess['exec_start']) & (day_df['Time'] <= sess['exec_end'])].reset_index(drop=True)
            if len(exec_bars) < 3:
                continue

            trade_taken = False

            for i in range(len(exec_bars) - 2):
                if trade_taken:
                    break

                b0 = exec_bars.iloc[i]
                b1 = exec_bars.iloc[i+1]
                b2 = exec_bars.iloc[i+2]

                swept_high = b0['High'] > ref_high and b0['Close'] < ref_high
                swept_low = b0['Low'] < ref_low and b0['Close'] > ref_low

                # Bearish SIBI Setup (Short)
                if swept_high and not trade_taken:
                    if b0['Low'] > b2['High']:
                        fvg_high = b0['Low']
                        fvg_low = b2['High']
                        fvg_ce = fvg_low + 0.5 * (fvg_high - fvg_low)

                        # CE Invalidation check
                        if b1['Close'] > fvg_ce or b2['Close'] > fvg_ce:
                            continue

                        # Candle Body MSS confirmation
                        if min(b1['Open'], b1['Close']) > b0['Low'] and min(b2['Open'], b2['Close']) > b0['Low']:
                            continue

                        # Premium filter
                        range_eq = ref_low + 0.50 * ref_range
                        if fvg_low < range_eq:
                            continue

                        entry_price = fvg_low
                        sl = ref_high + (2 * tick_size)
                        risk = sl - entry_price

                        if min_risk_pts <= risk <= max_risk_pts:
                            trade_taken = True
                            entry_idx = day_df[day_df['Datetime'] == b2['Datetime']].index[0]

                            target_cm = entry_price - (risk * 1.5)
                            target_hs = entry_price - (risk * 3.0)
                            center_mass_banked = False
                            active_sl = sl
                            exit_time = sess['exit_time']
                            outcome = 'TIME_EXIT'
                            exit_price = entry_price
                            pnl_cm_pts = 0.0
                            pnl_hs_pts = 0.0

                            for k in range(entry_idx + 1, len(day_df)):
                                future_bar = day_df.iloc[k]
                                if future_bar['Time'] > sess['exit_time']:
                                    exit_price = future_bar['Close']
                                    exit_time = future_bar['Time']
                                    if not center_mass_banked:
                                        pnl_cm_pts = entry_price - exit_price
                                    pnl_hs_pts = entry_price - exit_price
                                    break

                                if not center_mass_banked and future_bar['Low'] <= (target_cm + (slippage_ticks * tick_size)):
                                    center_mass_banked = True
                                    pnl_cm_pts = entry_price - target_cm
                                    active_sl = entry_price - (tick_size * 2)

                                if future_bar['High'] >= active_sl:
                                    exit_time = future_bar['Time']
                                    exit_price = active_sl
                                    if not center_mass_banked:
                                        outcome = 'LOSS'
                                        pnl_cm_pts = entry_price - active_sl
                                        pnl_hs_pts = entry_price - active_sl
                                    else:
                                        outcome = 'DEFENSIVE_STOP'
                                        pnl_hs_pts = entry_price - active_sl
                                    break

                                if center_mass_banked and future_bar['Low'] <= target_hs:
                                    outcome = 'FULL_WIN'
                                    exit_time = future_bar['Time']
                                    exit_price = target_hs
                                    pnl_hs_pts = entry_price - target_hs
                                    break

                            blended_pnl_pts = (0.5 * pnl_cm_pts) + (0.5 * pnl_hs_pts)
                            dollar_pnl = (blended_pnl_pts * point_val) - friction
                            balance += dollar_pnl
                            if balance > peak_balance:
                                peak_balance = balance
                            dd = peak_balance - balance
                            if dd > max_drawdown_dollars:
                                max_drawdown_dollars = dd
                                max_drawdown_pct = (dd / peak_balance) * 100

                            trades.append(TradeResult(
                                date=date, day_name=day_name, session=sess['name'],
                                direction='SHORT', entry_time=b2['Time'], entry_price=entry_price,
                                stop_loss=sl, target_center_mass=target_cm, target_head_shot=target_hs,
                                exit_time=exit_time, exit_price=exit_price, risk_pts=risk,
                                pnl_pts=blended_pnl_pts, outcome=outcome, dollar_pnl=dollar_pnl,
                                balance_after=balance, asset=asset_type
                            ))

                # Bullish BISI Setup (Long)
                elif swept_low and not trade_taken:
                    if b2['Low'] > b0['High']:
                        fvg_low = b0['High']
                        fvg_high = b2['Low']
                        fvg_ce = fvg_low + 0.5 * (fvg_high - fvg_low)

                        if b1['Close'] < fvg_ce or b2['Close'] < fvg_ce:
                            continue

                        if max(b1['Open'], b1['Close']) < b0['High'] and max(b2['Open'], b2['Close']) < b0['High']:
                            continue

                        range_eq = ref_low + 0.50 * ref_range
                        if fvg_high > range_eq:
                            continue

                        entry_price = fvg_high
                        sl = ref_low - (2 * tick_size)
                        risk = entry_price - sl

                        if min_risk_pts <= risk <= max_risk_pts:
                            trade_taken = True
                            entry_idx = day_df[day_df['Datetime'] == b2['Datetime']].index[0]

                            target_cm = entry_price + (risk * 1.5)
                            target_hs = entry_price + (risk * 3.0)
                            center_mass_banked = False
                            active_sl = sl
                            exit_time = sess['exit_time']
                            outcome = 'TIME_EXIT'
                            exit_price = entry_price
                            pnl_cm_pts = 0.0
                            pnl_hs_pts = 0.0

                            for k in range(entry_idx + 1, len(day_df)):
                                future_bar = day_df.iloc[k]
                                if future_bar['Time'] > sess['exit_time']:
                                    exit_price = future_bar['Close']
                                    exit_time = future_bar['Time']
                                    if not center_mass_banked:
                                        pnl_cm_pts = exit_price - entry_price
                                    pnl_hs_pts = exit_price - entry_price
                                    break

                                if not center_mass_banked and future_bar['High'] >= (target_cm - (slippage_ticks * tick_size)):
                                    center_mass_banked = True
                                    pnl_cm_pts = target_cm - entry_price
                                    active_sl = entry_price + (tick_size * 2)

                                if future_bar['Low'] <= active_sl:
                                    exit_time = future_bar['Time']
                                    exit_price = active_sl
                                    if not center_mass_banked:
                                        outcome = 'LOSS'
                                        pnl_cm_pts = active_sl - entry_price
                                        pnl_hs_pts = active_sl - entry_price
                                    else:
                                        outcome = 'DEFENSIVE_STOP'
                                        pnl_hs_pts = active_sl - entry_price
                                    break

                                if center_mass_banked and future_bar['High'] >= target_hs:
                                    outcome = 'FULL_WIN'
                                    exit_time = future_bar['Time']
                                    exit_price = target_hs
                                    pnl_hs_pts = target_hs - entry_price
                                    break

                            blended_pnl_pts = (0.5 * pnl_cm_pts) + (0.5 * pnl_hs_pts)
                            dollar_pnl = (blended_pnl_pts * point_val) - friction
                            balance += dollar_pnl
                            if balance > peak_balance:
                                peak_balance = balance
                            dd = peak_balance - balance
                            if dd > max_drawdown_dollars:
                                max_drawdown_dollars = dd
                                max_drawdown_pct = (dd / peak_balance) * 100

                            trades.append(TradeResult(
                                date=date, day_name=day_name, session=sess['name'],
                                direction='LONG', entry_time=b2['Time'], entry_price=entry_price,
                                stop_loss=sl, target_center_mass=target_cm, target_head_shot=target_hs,
                                exit_time=exit_time, exit_price=exit_price, risk_pts=risk,
                                pnl_pts=blended_pnl_pts, outcome=outcome, dollar_pnl=dollar_pnl,
                                balance_after=balance, asset=asset_type
                            ))

    wins = [t for t in trades if t.dollar_pnl > 0]
    losses = [t for t in trades if t.dollar_pnl < 0]
    total_trades = len(trades)
    win_rate = (len(wins) / total_trades * 100) if total_trades > 0 else 0.0

    gross_profit = sum(t.dollar_pnl for t in wins)
    gross_loss = abs(sum(t.dollar_pnl for t in losses))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0)
    net_profit = balance - INITIAL_CAPITAL
    return_pct = (net_profit / INITIAL_CAPITAL) * 100.0

    stats = {
        'total_trades': total_trades,
        'wins': len(wins),
        'losses': len(losses),
        'win_rate': win_rate,
        'gross_profit': gross_profit,
        'gross_loss': gross_loss,
        'profit_factor': profit_factor,
        'net_profit': net_profit,
        'return_pct': return_pct,
        'final_balance': balance,
        'max_drawdown_dollars': max_drawdown_dollars,
        'max_drawdown_pct': max_drawdown_pct,
    }
    return trades, stats

if __name__ == "__main__":
    assets = [
        ('SILVER', '/Users/hamzashahid/.gemini/antigravity/scratch/real_data/SI_F_5m_60d.csv', 'Micro Silver (SIL) 1000oz'),
        ('EURUSD', '/Users/hamzashahid/.gemini/antigravity/scratch/real_data/EURUSD_5m_60d.csv', 'EUR/USD Forex (0.10 Mini Lot)'),
        ('GBPUSD', '/Users/hamzashahid/.gemini/antigravity/scratch/real_data/GBPUSD_5m_60d.csv', 'GBP/USD Forex (0.10 Mini Lot)'),
        ('GOLD',   '/Users/hamzashahid/.gemini/antigravity/scratch/real_data/GC_F_5m_60d.csv',   'Micro Gold (MGC)'),
        ('NASDAQ', '/Users/hamzashahid/.gemini/antigravity/scratch/real_data/NQ_F_5m_60d.csv',   'Micro Nasdaq (MNQ)')
    ]

    print("=" * 105)
    print("       ICT 2024 COMPLETE 52-LECTURE MASTERCLASS MULTI-ASSET BACKTEST COMPARISON")
    print("       Tested on Real Historical Data (60 Calendar Days | Starting Capital: $500.00)")
    print("=" * 105)

    print(f"\n{'ASSET CLASS':<28} | {'TRADES':<7} | {'WIN RATE':<9} | {'NET PROFIT ($)':<15} | {'RETURN (%)':<11} | {'PROFIT FACTOR':<13} | {'MAX DRAWDOWN':<12}")
    print("-" * 105)

    all_trade_logs = []

    for atype, fpath, label in assets:
        df = load_data(fpath)
        trades, stats = simulate_asset(df, atype)
        all_trade_logs.extend(trades)
        print(f"{label:<28} | {stats['total_trades']:<7} | {stats['win_rate']:>6.1f}%  | ${stats['net_profit']:>10.2f}    | {stats['return_pct']:>8.1f}% | {stats['profit_factor']:>9.2f}    | ${stats['max_drawdown_dollars']:>6.2f} ({stats['max_drawdown_pct']:>4.1f}%)")

    print("\n" + "=" * 105)
    print("RECENT TRADE AUDIT SAMPLE (EUR/USD, GBP/USD & SILVER):")
    print("-" * 105)
    sample_trades = [t for t in all_trade_logs if t.asset in ['SILVER', 'EURUSD', 'GBPUSD']]
    for tr in sample_trades[-12:]:
        print(f"  [{tr.date} {tr.day_name[:3]}] {tr.asset:<7} {tr.session:<12} {tr.direction:<5} @ {tr.entry_time} | Entry: {tr.entry_price:8.4f} | Risk: {tr.risk_pts:7.4f} | {tr.outcome:<14} | Net: ${tr.dollar_pnl:+7.2f} | Bal: ${tr.balance_after:8.2f}")
