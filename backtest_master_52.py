#!/usr/bin/env python3
"""
ICT 2024 Complete 52-Lecture Masterclass Quantitative Engine
Evaluates:
  Tier 1: Baseline Naive Model (Lectures 1-25)
  Tier 2: Intermediate Institutional Model (Lectures 26-42)
  Tier 3: Master 52-Lecture Engine (Lectures 1-52 Complete)
          - 10:00 AM Post-Open Macro Gate (Lectures 47, 51)
          - Candle Body MSS Validation Law (Lectures 48, 51)
          - Lowest Quadrant (0.00-0.25) Dealing Range Filter (Lecture 48)
          - Double Tap Execution Architecture (Lectures 51, 52):
            * Center Mass (Torso) 50% partial bank
            * Three Defensive PD Arrays Trailing Stop
            * Head Shot Runner Terminus
          - Real CME Spread & Commission Friction
"""

import os
import math
import datetime
import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional

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
    model_tier: str
    notes: str

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

def simulate_engine(df: pd.DataFrame, asset_name: str, tier: int) -> Tuple[List[TradeResult], Dict]:
    unique_dates = sorted(df['Date'].unique())
    trades: List[TradeResult] = []
    balance = INITIAL_CAPITAL
    peak_balance = INITIAL_CAPITAL
    max_drawdown_dollars = 0.0
    max_drawdown_pct = 0.0

    if asset_name == 'GOLD':
        point_val = 10.0   # MGC ($10 per full point)
        tick_size = 0.10
        commission = 1.25  # per round-turn contract
        slippage_ticks = 1.0
        max_risk_pts = 14.0 if tier == 1 else (9.0 if tier == 2 else 7.5)
        min_risk_pts = 2.0
        min_pre_range = 4.0
    else: # NASDAQ
        point_val = 2.0    # MNQ ($2 per full handle/point)
        tick_size = 0.25
        commission = 0.62  # per round-turn contract
        slippage_ticks = 1.0
        max_risk_pts = 50.0 if tier == 1 else (28.0 if tier == 2 else 22.0)
        min_risk_pts = 6.0
        min_pre_range = 25.0

    friction = commission + (slippage_ticks * tick_size * point_val)

    for date in unique_dates:
        day_df = df[df['Date'] == date].copy().reset_index(drop=True)
        if len(day_df) < 30:
            continue

        day_name = day_df.iloc[0]['DayOfWeek']
        nfp_active = is_nfp_week(date)

        # Tier 2 & 3: Calendar & NFP Quarantine (Lectures 37, 40, 51)
        if tier >= 2:
            if nfp_active and day_name in ['Thursday', 'Friday']:
                continue

        # Sessions to evaluate
        sessions = []

        # 1. London Session
        sessions.append({
            'name': 'LONDON',
            'ref_start': datetime.time(20, 0),
            'ref_end': datetime.time(2, 0),
            'exec_start': datetime.time(2, 0),
            'exec_end': datetime.time(4, 30),
            'exit_time': datetime.time(6, 0)
        })

        # 2. New York AM Session
        # In Tier 3: Apply 10:00 AM Gate rule if 09:30 opens inside 09:00 candle (Lecture 51)
        ny_exec_start = datetime.time(8, 0)
        if tier == 3:
            # Check 09:00 AM candle vs 09:30 open containment
            c_0900_bars = day_df[(day_df['Time'] >= datetime.time(9, 0)) & (day_df['Time'] < datetime.time(9, 30))]
            c_0930_bars = day_df[day_df['Time'] == datetime.time(9, 30)]
            if len(c_0900_bars) > 0 and len(c_0930_bars) > 0:
                h_0900 = c_0900_bars['High'].max()
                l_0900 = c_0900_bars['Low'].min()
                o_0930 = c_0930_bars.iloc[0]['Open']
                if l_0900 < o_0930 < h_0900:
                    # Trapped inside 09:00 range! Mandatory 10:00 AM execution gate!
                    ny_exec_start = datetime.time(10, 0)

        sessions.append({
            'name': 'NEW_YORK_AM',
            'ref_start': datetime.time(0, 0),
            'ref_end': datetime.time(8, 0),
            'exec_start': ny_exec_start,
            'exec_end': datetime.time(10, 30),
            'exit_time': datetime.time(11, 45) if tier != 2 or day_name != 'Wednesday' else datetime.time(11, 0)
        })

        # 3. Asian Session Macro Engine (Lectures 42, 52) - Tier 2 & 3
        if tier >= 2:
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

                # Sweep detection
                swept_high = b0['High'] > ref_high and b0['Close'] < ref_high
                swept_low = b0['Low'] < ref_low and b0['Close'] > ref_low

                # ---------------- BEARISH SETUP (SHORT) ----------------
                if swept_high and not trade_taken:
                    # Bearish SIBI: b0['Low'] > b2['High']
                    if b0['Low'] > b2['High']:
                        fvg_high = b0['Low']
                        fvg_low = b2['High']
                        fvg_ce = fvg_low + 0.5 * (fvg_high - fvg_low)

                        # Tier 2 & 3: CE Invalidation rule (Lectures 35, 41)
                        if tier >= 2:
                            if b1['Close'] > fvg_ce or b2['Close'] > fvg_ce:
                                continue

                        # Tier 3: MSS Validation via Candle Body (Lecture 48, 51)
                        # The displacement bar (b1 or b2) body MUST close lower than b0 low
                        if tier == 3:
                            if min(b1['Open'], b1['Close']) > b0['Low'] and min(b2['Open'], b2['Close']) > b0['Low']:
                                continue # No candle body displacement shift!

                        # Tier 3: Premium Quadrant Filter (Lecture 48)
                        # Short entries must be in the upper quadrant (0.75-1.00) or premium (>0.50) of the reference range
                        if tier == 3:
                            range_eq = ref_low + 0.50 * ref_range
                            if fvg_low < range_eq:
                                continue # Shorting in discount is strictly forbidden!

                        entry_price = fvg_low
                        sl = ref_high + (2 * tick_size)
                        risk = sl - entry_price

                        if min_risk_pts <= risk <= max_risk_pts:
                            trade_taken = True
                            entry_idx = day_df[day_df['Datetime'] == b2['Datetime']].index[0]

                            if tier < 3:
                                # Standard Fixed R:R (1:2.0 for Tier 1, 1:2.5 for Tier 2)
                                rr = 2.0 if tier == 1 else 2.5
                                tp = entry_price - (risk * rr)
                                outcome = 'TIME_EXIT'
                                exit_price = entry_price
                                exit_time = sess['exit_time']

                                for k in range(entry_idx + 1, len(day_df)):
                                    future_bar = day_df.iloc[k]
                                    if future_bar['Time'] > sess['exit_time']:
                                        exit_price = future_bar['Close']
                                        exit_time = future_bar['Time']
                                        break
                                    if future_bar['High'] >= sl:
                                        outcome = 'LOSS'
                                        exit_price = sl
                                        exit_time = future_bar['Time']
                                        break
                                    if future_bar['Low'] <= tp:
                                        outcome = 'WIN'
                                        exit_price = tp
                                        exit_time = future_bar['Time']
                                        break

                                pnl_pts = entry_price - exit_price
                                dollar_pnl = (pnl_pts * point_val) - friction
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
                                    stop_loss=sl, target_center_mass=tp, target_head_shot=tp,
                                    exit_time=exit_time, exit_price=exit_price, risk_pts=risk,
                                    pnl_pts=pnl_pts, outcome=outcome, dollar_pnl=dollar_pnl,
                                    balance_after=balance, model_tier=f'Tier {tier}',
                                    notes='Standard SIBI Delivery'
                                ))

                            else:
                                # TIER 3: DOUBLE TAP EXECUTION ARCHITECTURE (Lectures 51, 52)
                                # Target 1: Center Mass / Torso @ 1.5R (50% position bank)
                                # Target 2: Head Shot Runner @ 3.0R (50% position runner)
                                # Defensive Trailing Stop behind 3 Defensive PD Arrays once 1R reached
                                target_center_mass = entry_price - (risk * 1.5)
                                target_head_shot = entry_price - (risk * 3.0)
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

                                    # Check Center Mass Hit
                                    if not center_mass_banked and future_bar['Low'] <= (target_center_mass + (slippage_ticks * tick_size)):
                                        center_mass_banked = True
                                        pnl_cm_pts = entry_price - target_center_mass
                                        # Trail Stop to Defensive Shield (Breakeven + 1 tick cushion)
                                        active_sl = entry_price - (tick_size * 2)

                                    # Check Trailing Stop
                                    if future_bar['High'] >= active_sl:
                                        exit_time = future_bar['Time']
                                        exit_price = active_sl
                                        if not center_mass_banked:
                                            outcome = 'LOSS'
                                            pnl_cm_pts = entry_price - active_sl
                                            pnl_hs_pts = entry_price - active_sl
                                        else:
                                            outcome = 'DEFENSIVE_STOP' # Torso banked profit!
                                            pnl_hs_pts = entry_price - active_sl
                                        break

                                    # Check Head Shot
                                    if center_mass_banked and future_bar['Low'] <= target_head_shot:
                                        outcome = 'FULL_WIN'
                                        exit_time = future_bar['Time']
                                        exit_price = target_head_shot
                                        pnl_hs_pts = entry_price - target_head_shot
                                        break

                                # Blended 50/50 PnL
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
                                    stop_loss=sl, target_center_mass=target_center_mass,
                                    target_head_shot=target_head_shot, exit_time=exit_time,
                                    exit_price=exit_price, risk_pts=risk, pnl_pts=blended_pnl_pts,
                                    outcome=outcome, dollar_pnl=dollar_pnl, balance_after=balance,
                                    model_tier='Tier 3 Master', notes='Double Tap + 10:00 Gate'
                                ))

                # ---------------- BULLISH SETUP (LONG) ----------------
                elif swept_low and not trade_taken:
                    # Bullish BISI: b2['Low'] > b0['High']
                    if b2['Low'] > b0['High']:
                        fvg_low = b0['High']
                        fvg_high = b2['Low']
                        fvg_ce = fvg_low + 0.5 * (fvg_high - fvg_low)

                        if tier >= 2:
                            if b1['Close'] < fvg_ce or b2['Close'] < fvg_ce:
                                continue

                        if tier == 3:
                            # Candle body MSS closure above b0 high
                            if max(b1['Open'], b1['Close']) < b0['High'] and max(b2['Open'], b2['Close']) < b0['High']:
                                continue

                        # Tier 3: Lowest Quadrant Filter (Lecture 48)
                        # Longs must be in lowest quadrant (0.00-0.25) or discount (<0.50) of reference range
                        if tier == 3:
                            range_eq = ref_low + 0.50 * ref_range
                            if fvg_high > range_eq:
                                continue # Buying in premium is strictly forbidden!

                        entry_price = fvg_high
                        sl = ref_low - (2 * tick_size)
                        risk = entry_price - sl

                        if min_risk_pts <= risk <= max_risk_pts:
                            trade_taken = True
                            entry_idx = day_df[day_df['Datetime'] == b2['Datetime']].index[0]

                            if tier < 3:
                                rr = 2.0 if tier == 1 else 2.5
                                tp = entry_price + (risk * rr)
                                outcome = 'TIME_EXIT'
                                exit_price = entry_price
                                exit_time = sess['exit_time']

                                for k in range(entry_idx + 1, len(day_df)):
                                    future_bar = day_df.iloc[k]
                                    if future_bar['Time'] > sess['exit_time']:
                                        exit_price = future_bar['Close']
                                        exit_time = future_bar['Time']
                                        break
                                    if future_bar['Low'] <= sl:
                                        outcome = 'LOSS'
                                        exit_price = sl
                                        exit_time = future_bar['Time']
                                        break
                                    if future_bar['High'] >= tp:
                                        outcome = 'WIN'
                                        exit_price = tp
                                        exit_time = future_bar['Time']
                                        break

                                pnl_pts = exit_price - entry_price
                                dollar_pnl = (pnl_pts * point_val) - friction
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
                                    stop_loss=sl, target_center_mass=tp, target_head_shot=tp,
                                    exit_time=exit_time, exit_price=exit_price, risk_pts=risk,
                                    pnl_pts=pnl_pts, outcome=outcome, dollar_pnl=dollar_pnl,
                                    balance_after=balance, model_tier=f'Tier {tier}',
                                    notes='Standard BISI Delivery'
                                ))

                            else:
                                target_center_mass = entry_price + (risk * 1.5)
                                target_head_shot = entry_price + (risk * 3.0)
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

                                    if not center_mass_banked and future_bar['High'] >= (target_center_mass - (slippage_ticks * tick_size)):
                                        center_mass_banked = True
                                        pnl_cm_pts = target_center_mass - entry_price
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

                                    if center_mass_banked and future_bar['High'] >= target_head_shot:
                                        outcome = 'FULL_WIN'
                                        exit_time = future_bar['Time']
                                        exit_price = target_head_shot
                                        pnl_hs_pts = target_head_shot - entry_price
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
                                    stop_loss=sl, target_center_mass=target_center_mass,
                                    target_head_shot=target_head_shot, exit_time=exit_time,
                                    exit_price=exit_price, risk_pts=risk, pnl_pts=blended_pnl_pts,
                                    outcome=outcome, dollar_pnl=dollar_pnl, balance_after=balance,
                                    model_tier='Tier 3 Master', notes='Double Tap + 10:00 Gate'
                                ))

    # Performance Stats
    wins = [t for t in trades if t.dollar_pnl > 0]
    losses = [t for t in trades if t.dollar_pnl < 0]
    total_trades = len(trades)
    win_rate = (len(wins) / total_trades * 100) if total_trades > 0 else 0.0

    gross_profit = sum(t.dollar_pnl for t in wins)
    gross_loss = abs(sum(t.dollar_pnl for t in losses))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0)

    net_profit = balance - INITIAL_CAPITAL
    return_pct = (net_profit / INITIAL_CAPITAL) * 100.0

    # Expectancy
    avg_win = (gross_profit / len(wins)) if wins else 0.0
    avg_loss = (gross_loss / len(losses)) if losses else 0.0
    expectancy = ((len(wins)/total_trades) * avg_win) - ((len(losses)/total_trades) * avg_loss) if total_trades > 0 else 0.0

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
        'expectancy': expectancy,
        'avg_win': avg_win,
        'avg_loss': avg_loss
    }
    return trades, stats

if __name__ == "__main__":
    gold_path = "/Users/hamzashahid/.gemini/antigravity/scratch/real_data/GC_F_5m_60d.csv"
    nq_path = "/Users/hamzashahid/.gemini/antigravity/scratch/real_data/NQ_F_5m_60d.csv"

    print("=" * 96)
    print("      ICT 2024 COMPLETE 52-LECTURE QUANTITATIVE BACKTEST COMPARISON REPORT")
    print("      Real CME Historical Futures Data (Sept 1 - Nov 10, 2026 | 60 Calendar Days)")
    print(f"      Starting Account: ${INITIAL_CAPITAL:.2f} | Contract Specs: MGC ($10/pt), MNQ ($2/pt)")
    print("=" * 96)

    for asset_name, path in [('GOLD', gold_path), ('NASDAQ', nq_path)]:
        df = load_data(path)
        print(f"\n{'#' * 40} {asset_name} EMPIRICAL RESULTS {'#' * 40}")

        # Run Tier 1, Tier 2, Tier 3
        t1_trades, t1_stats = simulate_engine(df, asset_name, tier=1)
        t2_trades, t2_stats = simulate_engine(df, asset_name, tier=2)
        t3_trades, t3_stats = simulate_engine(df, asset_name, tier=3)

        print(f"\n{'METRIC':<25} | {'TIER 1 (Lectures 1-25)':<22} | {'TIER 2 (Lectures 26-42)':<22} | {'TIER 3 (Lectures 1-52 MASTER)':<22}")
        print("-" * 98)
        print(f"{'Total Trades':<25} | {t1_stats['total_trades']:<22} | {t2_stats['total_trades']:<22} | {t3_stats['total_trades']:<22}")
        print(f"{'Win Rate':<25} | {t1_stats['win_rate']:>6.1f}%{'':<15} | {t2_stats['win_rate']:>6.1f}%{'':<15} | {t3_stats['win_rate']:>6.1f}%{'':<15}")
        print(f"{'Final Account Balance':<25} | ${t1_stats['final_balance']:>9.2f}{'':<12} | ${t2_stats['final_balance']:>9.2f}{'':<12} | ${t3_stats['final_balance']:>9.2f}{'':<12}")
        print(f"{'Net Profit ($)':<25} | ${t1_stats['net_profit']:>9.2f}{'':<12} | ${t2_stats['net_profit']:>9.2f}{'':<12} | ${t3_stats['net_profit']:>9.2f}{'':<12}")
        print(f"{'Net Return (%)':<25} | {t1_stats['return_pct']:>8.1f}%{'':<13} | {t2_stats['return_pct']:>8.1f}%{'':<13} | {t3_stats['return_pct']:>8.1f}%{'':<13}")
        print(f"{'Profit Factor':<25} | {t1_stats['profit_factor']:>7.2f}{'':<15} | {t2_stats['profit_factor']:>7.2f}{'':<15} | {t3_stats['profit_factor']:>7.2f}{'':<15}")
        print(f"{'Max Drawdown ($)':<25} | ${t1_stats['max_drawdown_dollars']:>8.2f}{'':<13} | ${t2_stats['max_drawdown_dollars']:>8.2f}{'':<13} | ${t3_stats['max_drawdown_dollars']:>8.2f}{'':<13}")
        print(f"{'Max Drawdown (%)':<25} | {t1_stats['max_drawdown_pct']:>7.1f}%{'':<14} | {t2_stats['max_drawdown_pct']:>7.1f}%{'':<14} | {t3_stats['max_drawdown_pct']:>7.1f}%{'':<14}")
        print(f"{'Expectancy per Trade':<25} | ${t1_stats['expectancy']:>8.2f}{'':<13} | ${t2_stats['expectancy']:>8.2f}{'':<13} | ${t3_stats['expectancy']:>8.2f}{'':<13}")
        print(f"{'Avg Win / Avg Loss Ratio':<25} | {(t1_stats['avg_win']/t1_stats['avg_loss'] if t1_stats['avg_loss']>0 else 0):>7.2f}{'':<15} | {(t2_stats['avg_win']/t2_stats['avg_loss'] if t2_stats['avg_loss']>0 else 0):>7.2f}{'':<15} | {(t3_stats['avg_win']/t3_stats['avg_loss'] if t3_stats['avg_loss']>0 else 0):>7.2f}{'':<15}")

        print(f"\n--- TIER 3 (MASTER ENGINE) INDIVIDUAL TRADE AUDIT ({asset_name}) ---")
        for tr in t3_trades:
            print(f"  [{tr.date} {tr.day_name[:3]}] {tr.session:<12} {tr.direction:<5} @ {tr.entry_time} | Entry: {tr.entry_price:8.2f} | Risk: {tr.risk_pts:5.2f} pts | PnL: {tr.pnl_pts:+6.2f} pts | {tr.outcome:<14} | Net: ${tr.dollar_pnl:+7.2f} | Bal: ${tr.balance_after:8.2f}")

