"""
ICT Sentinel AI - Comparative Empirical Evaluation
Backtesting Mulham Trading 12-Hour Course vs Official ICT 2024 52-Lecture Mentorship
Assets tested: EUR/USD, GBP/USD, Nasdaq Micro (NQ), Micro Gold (GC)
"""

import pandas as pd
import numpy as np
import datetime

def load_clean(path):
    df = pd.read_csv(path)
    col = 'Datetime' if 'Datetime' in df.columns else ('datetime' if 'datetime' in df.columns else df.columns[0])
    df['dt'] = pd.to_datetime(df[col], utc=True).dt.tz_convert('America/New_York')
    df = df.sort_values('dt').reset_index(drop=True)
    df['date'] = df['dt'].dt.date
    return df

def run_multi_asset_backtest():
    datasets = {
        'EURUSD': ('/Users/hamzashahid/Documents/Per/Projects/ict_sentinel_ai/real_data/EURUSD_5m_60d.csv', 10000.0, 0.0004),
        'GBPUSD': ('/Users/hamzashahid/Documents/Per/Projects/ict_sentinel_ai/real_data/GBPUSD_5m_60d.csv', 10000.0, 0.0005),
        'GOLD': ('/Users/hamzashahid/Documents/Per/Projects/ict_sentinel_ai/real_data/GC_F_5m_60d.csv', 10.0, 2.0),
        'NASDAQ': ('/Users/hamzashahid/Documents/Per/Projects/ict_sentinel_ai/real_data/NQ_F_5m_60d.csv', 2.0, 10.0)
    }

    models = {
        'Mulham_Asian_Sweep': {'trades': 0, 'wins': 0, 'losses': 0, 'pnl_r': 0.0},
        'Mulham_2_Lines_PDH_PDL': {'trades': 0, 'wins': 0, 'losses': 0, 'pnl_r': 0.0},
        'Mulham_1_Rectangle_FVG': {'trades': 0, 'wins': 0, 'losses': 0, 'pnl_r': 0.0},
        'Official_ICT_2024_Sentinel': {'trades': 0, 'wins': 0, 'losses': 0, 'pnl_r': 0.0, 'scratches': 0}
    }

    summary_per_asset = {}

    for asset_name, (csv_path, pt_val, min_risk) in datasets.items():
        df = load_clean(csv_path)
        days = df['date'].unique()
        
        asset_stats = {
            'Mulham_Asian_Sweep': {'trades': 0, 'wins': 0, 'losses': 0, 'pnl_r': 0.0},
            'Mulham_2_Lines': {'trades': 0, 'wins': 0, 'losses': 0, 'pnl_r': 0.0},
            'Mulham_1_Rectangle': {'trades': 0, 'wins': 0, 'losses': 0, 'pnl_r': 0.0},
            'ICT_2024_Sentinel': {'trades': 0, 'wins': 0, 'losses': 0, 'pnl_r': 0.0}
        }

        for i in range(1, len(days)):
            prev_day = df[df['date'] == days[i-1]]
            day_bars = df[df['date'] == days[i]].reset_index(drop=True)
            if len(day_bars) < 40 or len(prev_day) < 40:
                continue

            pdh = prev_day['High'].max()
            pdl = prev_day['Low'].min()

            # Asian Range (before 02:00 EST)
            asian_bars = day_bars[day_bars['dt'].dt.time < datetime.time(2, 0)]
            if len(asian_bars) >= 6:
                ah = asian_bars['High'].max()
                al = asian_bars['Low'].min()

                # --- 1. Mulham Asian Sweep Strategy ---
                # Window: 01:30 - 03:00 EST. Sweep AH or AL -> enter 2R target with static stop
                as_window = day_bars[(day_bars['dt'].dt.time >= datetime.time(1, 30)) & (day_bars['dt'].dt.time <= datetime.time(3, 0))]
                post_as = day_bars[day_bars['dt'].dt.time > datetime.time(3, 0)]
                if len(as_window) > 0 and len(post_as) > 10:
                    if as_window['High'].max() > ah:
                        entry = as_window['Close'].iloc[-1]
                        stop = as_window['High'].max()
                        risk = stop - entry
                        if risk >= min_risk:
                            tp = entry - 2.0 * risk
                            win = False
                            for _, r in post_as.iterrows():
                                if r['Low'] <= tp: win = True; break
                                if r['High'] >= stop: win = False; break
                            asset_stats['Mulham_Asian_Sweep']['trades'] += 1
                            if win:
                                asset_stats['Mulham_Asian_Sweep']['wins'] += 1
                                asset_stats['Mulham_Asian_Sweep']['pnl_r'] += 2.0
                            else:
                                asset_stats['Mulham_Asian_Sweep']['losses'] += 1
                                asset_stats['Mulham_Asian_Sweep']['pnl_r'] -= 1.0

                # --- 2. Mulham 2 Lines (PDH / PDL Sweep) ---
                # Anytime during the day, if price sweeps PDH or PDL
                for idx in range(10, len(day_bars) - 10):
                    bar = day_bars.iloc[idx]
                    if bar['High'] > pdh and bar['Close'] < pdh: # Swept PDH
                        entry = bar['Close']
                        stop = bar['High'] + min_risk * 0.2
                        risk = stop - entry
                        if risk >= min_risk:
                            tp = entry - 2.0 * risk
                            future = day_bars.iloc[idx+1:]
                            win = False
                            for _, r in future.iterrows():
                                if r['Low'] <= tp: win = True; break
                                if r['High'] >= stop: win = False; break
                            asset_stats['Mulham_2_Lines']['trades'] += 1
                            if win:
                                asset_stats['Mulham_2_Lines']['wins'] += 1
                                asset_stats['Mulham_2_Lines']['pnl_r'] += 2.0
                            else:
                                asset_stats['Mulham_2_Lines']['losses'] += 1
                                asset_stats['Mulham_2_Lines']['pnl_r'] -= 1.0
                            break

                # --- 3. Mulham 1 Rectangle (Pure FVG Retest) ---
                # Find any 5m FVG with displacement, trade 2R retest
                for idx in range(2, min(50, len(day_bars) - 10)):
                    c0, c1, c2 = day_bars.iloc[idx-2], day_bars.iloc[idx-1], day_bars.iloc[idx]
                    if c0['Low'] > c2['High']: # Bearish FVG
                        entry = c0['Low']
                        stop = c1['High']
                        risk = stop - entry
                        if risk >= min_risk:
                            tp = entry - 2.0 * risk
                            future = day_bars.iloc[idx+1:]
                            win = False
                            for _, r in future.iterrows():
                                if r['Low'] <= tp: win = True; break
                                if r['High'] >= stop: win = False; break
                            asset_stats['Mulham_1_Rectangle']['trades'] += 1
                            if win:
                                asset_stats['Mulham_1_Rectangle']['wins'] += 1
                                asset_stats['Mulham_1_Rectangle']['pnl_r'] += 2.0
                            else:
                                asset_stats['Mulham_1_Rectangle']['losses'] += 1
                                asset_stats['Mulham_1_Rectangle']['pnl_r'] -= 1.0
                            break

                # --- 4. Official ICT 2024 Sentinel AI (Full 52-Lecture Rules) ---
                # London (02:00-04:30 EST): Require Sweep + Candle Body MSS + 50% CE Defense + Double Tap
                london = day_bars[(day_bars['dt'].dt.time >= datetime.time(2, 0)) & (day_bars['dt'].dt.time <= datetime.time(4, 30))]
                if len(london) >= 5:
                    swept_h = london['High'].max() > ah
                    swept_l = london['Low'].min() < al
                    if swept_h and not swept_l:
                        # Find displacement candle with body MSS
                        for j in range(2, len(london)):
                            b0, b1, b2 = london.iloc[j-2], london.iloc[j-1], london.iloc[j]
                            # Body MSS (Lecture 48)
                            if min(b1['Open'], b1['Close']) < b0['Low'] and b0['Low'] > b2['High']:
                                fvg_h, fvg_l = b0['Low'], b2['High']
                                ce = fvg_l + 0.5 * (fvg_h - fvg_l)
                                entry = fvg_h
                                stop = london['High'].max() + min_risk * 0.2
                                risk = stop - entry
                                if risk >= min_risk:
                                    tp1 = entry - 1.5 * risk
                                    tp2 = entry - 3.0 * risk
                                    cm_hit = False
                                    act_stop = stop
                                    pnl = 0.0
                                    outcome = 'LOSS'
                                    post = day_bars.iloc[day_bars[day_bars['dt'] == b2['dt']].index[0]+1:]

                                    for _, r in post.iterrows():
                                        # Early scratch defense: body close > 50% CE
                                        if not cm_hit and r['Close'] > ce:
                                            outcome = 'SCRATCH'
                                            pnl = -0.3
                                            break
                                        if not cm_hit and r['Low'] <= tp1:
                                            cm_hit = True
                                            act_stop = entry # Breakeven!
                                            pnl += 0.5 * 1.5
                                        if cm_hit and r['Low'] <= tp2:
                                            pnl += 0.5 * 3.0
                                            outcome = 'WIN'
                                            break
                                        if r['High'] >= act_stop:
                                            if cm_hit:
                                                outcome = 'DEFENSIVE_STOP'
                                            else:
                                                outcome = 'LOSS'
                                                pnl = -1.0
                                            break
                                    asset_stats['ICT_2024_Sentinel']['trades'] += 1
                                    if outcome in ['WIN', 'DEFENSIVE_STOP']:
                                        asset_stats['ICT_2024_Sentinel']['wins'] += 1
                                        asset_stats['ICT_2024_Sentinel']['pnl_r'] += pnl
                                    else:
                                        asset_stats['ICT_2024_Sentinel']['losses'] += 1
                                        asset_stats['ICT_2024_Sentinel']['pnl_r'] += pnl
                                    break

        summary_per_asset[asset_name] = asset_stats

    return summary_per_asset

if __name__ == '__main__':
    results = run_multi_asset_backtest()
    print('\n==================== RIGOROUS MULTI-ASSET COMPARISON ====================')
    for asset, models in results.items():
        print(f'\n--- Asset: {asset} ---')
        for mname, st in models.items():
            t = st['trades']
            w = st['wins']
            l = st['losses']
            wr = (w / t * 100) if t else 0
            pnl = st['pnl_r']
            print(f'{mname:25s} | Trades: {t:2d} | WinRate: {wr:5.1f}% | Net PnL: {pnl:+6.2f}R')
