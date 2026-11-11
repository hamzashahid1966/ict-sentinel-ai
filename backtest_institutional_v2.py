#!/usr/bin/env python3
"""
ICT 2024 Institutional Quantitative Engine v2.0
Comparative Empirical Analysis: Phase 1 (Lectures 1-25) vs. Phase 2 (Lectures 26-42)

Evaluates:
  1. Baseline Naive Model (Lectures 1-25):
     - Trades all days indiscriminately
     - Binary FVG entry on touch
     - Standard 1:2 R:R target
  2. Upgraded Institutional Engine (Lectures 26-42):
     - Calendar & Macro Gate: Monday/Tuesday active; Wednesday hard cutoff at 11:00 AM;
       Thursday/Friday NFP week mandatory quarantine (Lectures 37, 40, 41, 42)
     - Inefficiency Quadrant Law: 50% Consequent Encroachment body invalidation filter (Lectures 35, 41, 42)
     - Asian Session Macro Engine: 18:50-19:10 & 19:50-20:10 EST windows (Lecture 42)
     - Micro contract sizing ($500 starting capital on MNQ and MGC)
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
    take_profit: float
    exit_time: datetime.time
    exit_price: float
    risk_pts: float
    pnl_pts: float
    outcome: str
    dollar_pnl: float
    balance_after: float
    setup_name: str

def load_data(filepath: str) -> pd.DataFrame:
    df = pd.read_csv(filepath)
    df['Datetime'] = pd.to_datetime(df['Datetime'], utc=True)
    df['Datetime_ET'] = df['Datetime'].dt.tz_convert('US/Eastern')
    df['Date'] = df['Datetime_ET'].dt.date
    df['Time'] = df['Datetime_ET'].dt.time
    df['DayOfWeek'] = df['Datetime_ET'].dt.day_name()
    return df

def is_nfp_week(d: datetime.date) -> bool:
    # First Friday of the month is NFP.
    # Check if this date falls in the week containing the first Friday.
    first_day = datetime.date(d.year, d.month, 1)
    # Days until first Friday
    days_to_friday = (4 - first_day.weekday()) % 7
    first_friday = first_day + datetime.timedelta(days=days_to_friday)
    first_monday = first_friday - datetime.timedelta(days=4)
    return first_monday <= d <= first_friday

def run_simulation(df: pd.DataFrame, asset_name: str, point_val: float, commission: float, slippage_ticks: float, tick_size: float, use_advanced_rules: bool) -> Tuple[List[TradeResult], Dict]:
    unique_dates = sorted(df['Date'].unique())
    trades: List[TradeResult] = []
    balance = INITIAL_CAPITAL
    peak_balance = INITIAL_CAPITAL
    max_drawdown = 0.0

    friction = commission + (slippage_ticks * tick_size * point_val)

    # Asset specific thresholds
    if asset_name == 'GOLD':
        max_risk_pts = 14.0 if not use_advanced_rules else 9.0
        min_risk_pts = 2.0
        rr_multiplier = 2.0 if not use_advanced_rules else 2.5
        min_pre_range = 4.0
    else: # NASDAQ
        max_risk_pts = 50.0 if not use_advanced_rules else 28.0
        min_risk_pts = 6.0
        rr_multiplier = 2.0 if not use_advanced_rules else 2.5
        min_pre_range = 25.0

    for date in unique_dates:
        day_df = df[df['Date'] == date].copy().reset_index(drop=True)
        if len(day_df) < 30:
            continue
        
        day_name = day_df.iloc[0]['DayOfWeek']
        nfp_active = is_nfp_week(date)

        # ADVANCED RULE 1: DAY-OF-WEEK & MACRO NEWS GATE (Lectures 37, 40, 41, 42)
        if use_advanced_rules:
            # During NFP week: Quarantine Thursday & Friday completely
            if nfp_active and day_name in ['Thursday', 'Friday']:
                continue

        # Sessions to check
        sessions_to_evaluate = []
        
        # 1. London Session
        sessions_to_evaluate.append({
            'name': 'LONDON',
            'ref_start': datetime.time(20, 0),
            'ref_end': datetime.time(2, 0),
            'exec_start': datetime.time(2, 0),
            'exec_end': datetime.time(4, 30),
            'exit_time': datetime.time(6, 0)
        })

        # 2. New York AM Session
        sessions_to_evaluate.append({
            'name': 'NEW_YORK_AM',
            'ref_start': datetime.time(0, 0),
            'ref_end': datetime.time(8, 0),
            'exec_start': datetime.time(8, 0),
            'exec_end': datetime.time(10, 30) if not (use_advanced_rules and day_name == 'Wednesday') else datetime.time(10, 30),
            'exit_time': datetime.time(11, 45)
        })

        # 3. Asian Session Macro Engine (Lecture 42) - Only active in Upgraded Model
        if use_advanced_rules:
            sessions_to_evaluate.append({
                'name': 'ASIAN_MACRO',
                'ref_start': datetime.time(15, 0), # Market-on-Close reference
                'ref_end': datetime.time(18, 0),
                'exec_start': datetime.time(18, 50), # Macro 1 start
                'exec_end': datetime.time(20, 15),   # Macro 2 end
                'exit_time': datetime.time(22, 0)    # 10:00 PM session terminus
            })

        for sess in sessions_to_evaluate:
            # ADVANCED RULE 1B: Wednesday Hard Cutoff at 11:00 AM EST (Lecture 40)
            if use_advanced_rules and day_name == 'Wednesday' and sess['name'] == 'NEW_YORK_AM':
                # Force cutoff at 11:00 AM
                sess['exec_end'] = datetime.time(10, 30)
                sess['exit_time'] = datetime.time(11, 0)

            # Build reference range
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

            # Execution window bars
            exec_bars = day_df[(day_df['Time'] >= sess['exec_start']) & (day_df['Time'] <= sess['exec_end'])].reset_index(drop=True)
            if len(exec_bars) < 3:
                continue

            trade_taken = False

            for i in range(len(exec_bars) - 2):
                bar = exec_bars.iloc[i]
                t = bar['Time']

                # Turtle Soup Sweep Detection
                swept_high = bar['High'] > ref_high and bar['Close'] < ref_high
                swept_low = bar['Low'] < ref_low and bar['Close'] > ref_low

                # Check Bearish Reversal (Swept High)
                if swept_high and not trade_taken:
                    # Look for Bearish FVG (SIBI): Bar 0 Low > Bar 2 High
                    if i + 2 < len(exec_bars):
                        b0 = exec_bars.iloc[i]
                        b1 = exec_bars.iloc[i+1]
                        b2 = exec_bars.iloc[i+2]
                        if b0['Low'] > b2['High']:
                            fvg_high = b0['Low']
                            fvg_low = b2['High']
                            fvg_ce = fvg_low + 0.5 * (fvg_high - fvg_low)
                            fvg_upper_quadrant = fvg_low + 0.75 * (fvg_high - fvg_low)

                            # ADVANCED RULE 2: INEFFICIENCY QUADRANT & CE INVALIDATION (Lectures 35, 41, 42)
                            if use_advanced_rules:
                                # Re-test candle body must NOT close above Consequent Encroachment
                                if b1['Close'] > fvg_ce or b2['Close'] > fvg_ce:
                                    continue # Disqualified: Smart money failed to respect CE!

                            entry_price = fvg_low
                            sl = ref_high + (2 * tick_size)
                            risk = sl - entry_price

                            if min_risk_pts <= risk <= max_risk_pts:
                                tp = entry_price - (risk * rr_multiplier)
                                
                                # Evaluate forward price delivery until session exit
                                entry_idx = day_df[day_df['Datetime'] == b2['Datetime']].index[0]
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

                                pnl_pts = entry_price - exit_price if outcome != 'LOSS' else -risk
                                dollar_gain = (pnl_pts * point_val) - friction
                                balance += dollar_gain
                                if balance > peak_balance:
                                    peak_balance = balance
                                dd = peak_balance - balance
                                if dd > max_drawdown:
                                    max_drawdown = dd

                                trades.append(TradeResult(
                                    date=date, day_name=day_name, session=sess['name'], direction='SHORT',
                                    entry_time=t, entry_price=entry_price, stop_loss=sl, take_profit=tp,
                                    exit_time=exit_time, exit_price=exit_price, risk_pts=risk, pnl_pts=pnl_pts,
                                    outcome=outcome, dollar_pnl=dollar_gain, balance_after=balance,
                                    setup_name='BEARISH_TURTLE_SOUP_SIBI'
                                ))
                                trade_taken = True
                                break

                # Check Bullish Reversal (Swept Low)
                if swept_low and not trade_taken:
                    # Look for Bullish FVG (BISI): Bar 2 Low > Bar 0 High
                    if i + 2 < len(exec_bars):
                        b0 = exec_bars.iloc[i]
                        b1 = exec_bars.iloc[i+1]
                        b2 = exec_bars.iloc[i+2]
                        if b2['Low'] > b0['High']:
                            fvg_high = b2['Low']
                            fvg_low = b0['High']
                            fvg_ce = fvg_low + 0.5 * (fvg_high - fvg_low)
                            fvg_lower_quadrant = fvg_low + 0.25 * (fvg_high - fvg_low)

                            # ADVANCED RULE 2: INEFFICIENCY QUADRANT & CE INVALIDATION
                            if use_advanced_rules:
                                # Re-test candle body must NOT close below Consequent Encroachment
                                if b1['Close'] < fvg_ce or b2['Close'] < fvg_ce:
                                    continue # Disqualified: Smart money failed to respect CE!

                            entry_price = fvg_high
                            sl = ref_low - (2 * tick_size)
                            risk = entry_price - sl

                            if min_risk_pts <= risk <= max_risk_pts:
                                tp = entry_price + (risk * rr_multiplier)

                                entry_idx = day_df[day_df['Datetime'] == b2['Datetime']].index[0]
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

                                pnl_pts = exit_price - entry_price if outcome != 'LOSS' else -risk
                                dollar_gain = (pnl_pts * point_val) - friction
                                balance += dollar_gain
                                if balance > peak_balance:
                                    peak_balance = balance
                                dd = peak_balance - balance
                                if dd > max_drawdown:
                                    max_drawdown = dd

                                trades.append(TradeResult(
                                    date=date, day_name=day_name, session=sess['name'], direction='LONG',
                                    entry_time=t, entry_price=entry_price, stop_loss=sl, take_profit=tp,
                                    exit_time=exit_time, exit_price=exit_price, risk_pts=risk, pnl_pts=pnl_pts,
                                    outcome=outcome, dollar_pnl=dollar_gain, balance_after=balance,
                                    setup_name='BULLISH_TURTLE_SOUP_BISI'
                                ))
                                trade_taken = True
                                break

    wins = [t for t in trades if t.outcome == 'WIN']
    losses = [t for t in trades if t.outcome == 'LOSS']
    ties = [t for t in trades if t.outcome == 'TIME_EXIT']

    gross_profit = sum(t.dollar_pnl for t in wins)
    gross_loss = abs(sum(t.dollar_pnl for t in losses)) if losses else 0.001
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

    metrics = {
        'total_trades': len(trades),
        'wins': len(wins),
        'losses': len(losses),
        'ties': len(ties),
        'win_rate': (len(wins) / len(trades) * 100) if trades else 0.0,
        'final_balance': balance,
        'net_profit': balance - INITIAL_CAPITAL,
        'roi_pct': ((balance - INITIAL_CAPITAL) / INITIAL_CAPITAL) * 100,
        'max_drawdown': max_drawdown,
        'max_drawdown_pct': (max_drawdown / peak_balance * 100) if peak_balance > 0 else 0.0,
        'profit_factor': profit_factor
    }

    return trades, metrics

def main():
    gold_path = '/Users/hamzashahid/.gemini/antigravity/scratch/real_data/GC_F_5m_60d.csv'
    nq_path = '/Users/hamzashahid/.gemini/antigravity/scratch/real_data/NQ_F_5m_60d.csv'

    df_gold = load_data(gold_path)
    df_nq = load_data(nq_path)

    print("==========================================================================================")
    print("                  ICT 2024 QUANTITATIVE BACKTEST COMPARISON REPORT")
    print("==========================================================================================")
    print("Testing on Real CME Historical Data (September 1 - November 10, 2026 / 60 Calendar Days)")
    print("Starting Capital: $500.00 | Micro Contracts (MGC & MNQ)\n")

    # 1. COMEX GOLD
    trades_gold_base, m_gold_base = run_simulation(
        df_gold, 'GOLD', point_val=10.0, commission=1.50, slippage_ticks=1.0, tick_size=0.10, use_advanced_rules=False
    )
    trades_gold_adv, m_gold_adv = run_simulation(
        df_gold, 'GOLD', point_val=10.0, commission=1.50, slippage_ticks=1.0, tick_size=0.10, use_advanced_rules=True
    )

    # 2. NASDAQ FUTURES
    trades_nq_base, m_nq_base = run_simulation(
        df_nq, 'NASDAQ', point_val=2.0, commission=1.24, slippage_ticks=1.0, tick_size=0.25, use_advanced_rules=False
    )
    trades_nq_adv, m_nq_adv = run_simulation(
        df_nq, 'NASDAQ', point_val=2.0, commission=1.24, slippage_ticks=1.0, tick_size=0.25, use_advanced_rules=True
    )

    print("------------------------------------------------------------------------------------------")
    print("1. MICRO GOLD FUTURES (MGC - $10/pt) COMPARISON:")
    print("------------------------------------------------------------------------------------------")
    print(f"BASELINE MODEL (Lectures 1-25):")
    print(f"  Trades: {m_gold_base['total_trades']} | Wins: {m_gold_base['wins']} | Losses: {m_gold_base['losses']} | Ties: {m_gold_base['ties']}")
    print(f"  Win Rate:       {m_gold_base['win_rate']:.1f}%")
    print(f"  Final Balance:  ${m_gold_base['final_balance']:.2f} (Net: ${m_gold_base['net_profit']:+.2f} / {m_gold_base['roi_pct']:+.1f}%)")
    print(f"  Max Drawdown:   ${m_gold_base['max_drawdown']:.2f} ({m_gold_base['max_drawdown_pct']:.1f}%)")
    print(f"  Profit Factor:  {m_gold_base['profit_factor']:.2f}")

    print(f"\nUPGRADED INSTITUTIONAL MODEL (Lectures 26-42):")
    print(f"  Trades: {m_gold_adv['total_trades']} | Wins: {m_gold_adv['wins']} | Losses: {m_gold_adv['losses']} | Ties: {m_gold_adv['ties']}")
    print(f"  Win Rate:       {m_gold_adv['win_rate']:.1f}%")
    print(f"  Final Balance:  ${m_gold_adv['final_balance']:.2f} (Net: ${m_gold_adv['net_profit']:+.2f} / {m_gold_adv['roi_pct']:+.1f}%)")
    print(f"  Max Drawdown:   ${m_gold_adv['max_drawdown']:.2f} ({m_gold_adv['max_drawdown_pct']:.1f}%)")
    print(f"  Profit Factor:  {m_gold_adv['profit_factor']:.2f}")

    print("\n------------------------------------------------------------------------------------------")
    print("2. MICRO NASDAQ FUTURES (MNQ - $2/pt) COMPARISON:")
    print("------------------------------------------------------------------------------------------")
    print(f"BASELINE MODEL (Lectures 1-25):")
    print(f"  Trades: {m_nq_base['total_trades']} | Wins: {m_nq_base['wins']} | Losses: {m_nq_base['losses']} | Ties: {m_nq_base['ties']}")
    print(f"  Win Rate:       {m_nq_base['win_rate']:.1f}%")
    print(f"  Final Balance:  ${m_nq_base['final_balance']:.2f} (Net: ${m_nq_base['net_profit']:+.2f} / {m_nq_base['roi_pct']:+.1f}%)")
    print(f"  Max Drawdown:   ${m_nq_base['max_drawdown']:.2f} ({m_nq_base['max_drawdown_pct']:.1f}%)")
    print(f"  Profit Factor:  {m_nq_base['profit_factor']:.2f}")

    print(f"\nUPGRADED INSTITUTIONAL MODEL (Lectures 26-42):")
    print(f"  Trades: {m_nq_adv['total_trades']} | Wins: {m_nq_adv['wins']} | Losses: {m_nq_adv['losses']} | Ties: {m_nq_adv['ties']}")
    print(f"  Win Rate:       {m_nq_adv['win_rate']:.1f}%")
    print(f"  Final Balance:  ${m_nq_adv['final_balance']:.2f} (Net: ${m_nq_adv['net_profit']:+.2f} / {m_nq_adv['roi_pct']:+.1f}%)")
    print(f"  Max Drawdown:   ${m_nq_adv['max_drawdown']:.2f} ({m_nq_adv['max_drawdown_pct']:.1f}%)")
    print(f"  Profit Factor:  {m_nq_adv['profit_factor']:.2f}")

    print("\n==========================================================================================")
    print("UPGRADED TRADE AUDIT (Gold Advanced Trades):")
    for t in trades_gold_adv:
        print(f"  [{t.date} {t.day_name[:3]}] {t.session:<12} {t.direction:<5} @ {t.entry_time} | Risk: {t.risk_pts:4.1f} pts | PnL: {t.pnl_pts:+5.1f} pts | {t.outcome:<9} | Net: ${t.dollar_pnl:+6.2f} | Bal: ${t.balance_after:6.2f}")

    print("\nUPGRADED TRADE AUDIT (Nasdaq Advanced Trades):")
    for t in trades_nq_adv:
        print(f"  [{t.date} {t.day_name[:3]}] {t.session:<12} {t.direction:<5} @ {t.entry_time} | Risk: {t.risk_pts:4.1f} pts | PnL: {t.pnl_pts:+5.1f} pts | {t.outcome:<9} | Net: ${t.dollar_pnl:+6.2f} | Bal: ${t.balance_after:6.2f}")

if __name__ == '__main__':
    main()

