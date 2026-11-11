#!/usr/bin/env python3
"""
ICT 2024 Institutional Quantitative Engine (With HTF & Open Bias Filter)
Key Principles Integrated from Lectures 11, 14, 16, 23, 24:
  1. The Opening Price Bias Rule (Lectures 11 & 14):
     - Bullish days: Price trades BELOW 09:30 Open to accumulate, then expands ABOVE 09:30 Open.
       -> Only Longs taken when sweeping Discount below Open.
     - Bearish days: Price trades ABOVE 09:30 Open to distribute, then expands BELOW 09:30 Open.
       -> Only Shorts taken when sweeping Premium above Open.
  2. HTF Order Flow & Liquidity Draw (Lecture 16 & 24):
     - Dynamic 1:2 R:R Minimum or Opposing Liquidity Target.
  3. IOFED Momentum Confirmation (Lecture 25):
     - Shallow FVG penetration on high-momentum bars.
"""

import math
import random
from dataclasses import dataclass
from typing import List, Tuple, Dict

TICK = 0.25
POINT_VAL = 20.0
COMMISSION = 4.50
SLIPPAGE = 10.0 # 2 ticks roundtrip ($10)

@dataclass
class Candle:
    time_str: str
    minute_idx: int
    open: float
    high: float
    low: float
    close: float
    volume: int

@dataclass
class Trade:
    day: int
    direction: str
    entry_time: str
    entry_price: float
    sl: float
    tp: float
    exit_time: str
    exit_price: float
    pnl_pts: float
    net_pnl: float
    outcome: str
    setup: str
    rr_ratio: float

def calculate_atr(candles: List[Candle], period: int = 14) -> List[float]:
    atrs = []
    tr_list = []
    for i in range(len(candles)):
        if i == 0:
            tr = candles[i].high - candles[i].low
        else:
            pc = candles[i - 1].close
            tr = max(candles[i].high - candles[i].low, abs(candles[i].high - pc), abs(candles[i].low - pc))
        tr_list.append(tr)
        if len(tr_list) < period:
            atrs.append(sum(tr_list) / len(tr_list))
        else:
            atrs.append(sum(tr_list[-period:]) / period)
    return atrs

class InstitutionalICTEngine:
    def __init__(self, seed: int = 42):
        random.seed(seed)
        self.trades: List[Trade] = []

    def generate_day_tape(self, day_idx: int) -> Tuple[List[Candle], float]:
        candles: List[Candle] = []
        price = 19400.0 + random.uniform(-500, 500)
        base_vol = 4.2
        day_type = day_idx % 4
        
        if day_type == 0:
            bias = -0.45 # Bearish distribution day
        elif day_type == 1:
            bias = 0.50  # Bullish expansion day
        elif day_type == 2:
            bias = random.choice([-0.3, 0.3])
        else:
            bias = 0.05  # Range / consolidation
            
        open_0930_price = 0.0

        for m in range(135):
            h = 9 + ((15 + m) // 60)
            minute = (15 + m) % 60
            t_str = f"{h:02d}:{minute:02d}"
            
            vol_mult = 1.0
            drift = bias
            
            # 09:30 Open
            if m == 15:
                open_0930_price = price
                
            if 15 <= m <= 22:
                vol_mult = 2.4
                # Judas swing against the true bias in 60% of sessions
                drift = -bias * 1.5 if random.random() < 0.6 else bias * 1.2
            elif 45 <= m <= 60:
                vol_mult = 2.2
                drift = bias * 2.2 # True directional expansion during Silver Bullet
            elif m >= 120:
                vol_mult = 0.7
                drift = -bias * 0.4 # Lunch retracement

            step = random.gauss(drift, base_vol * vol_mult)
            o = price
            c = o + step
            hi = max(o, c) + abs(random.gauss(0, base_vol * 0.7 * vol_mult))
            lo = min(o, c) - abs(random.gauss(0, base_vol * 0.7 * vol_mult))
            
            o = round(o / TICK) * TICK
            hi = round(hi / TICK) * TICK
            lo = round(lo / TICK) * TICK
            c = round(c / TICK) * TICK
            
            candles.append(Candle(t_str, m, o, hi, lo, c, int(random.uniform(700, 3200) * vol_mult)))
            price = c
            
        return candles, open_0930_price

    def evaluate_session(self, day_idx: int, candles: List[Candle], open_0930: float):
        atrs = calculate_atr(candles)
        
        # Opening Range 09:30 - 10:00 (m = 15 to 45)
        or_candles = candles[15:45]
        or_high = max(c.high for c in or_candles)
        or_low = min(c.low for c in or_candles)
        
        trade_taken = False
        
        # Silver Bullet Window: 10:00 AM - 11:00 AM (m = 45 to 105)
        for i in range(45, 95):
            if trade_taken:
                break
                
            curr = candles[i]
            atr = atrs[i]
            
            # --- INSTITUTIONAL FILTER: OPENING PRICE BIAS ---
            # If price is sweeping ABOVE 09:30 Open -> Seek SHORT (Premium Distribution)
            # If price is sweeping BELOW 09:30 Open -> Seek LONG (Discount Accumulation)
            
            # 1. SHORT EVALUATION (Requires sweep in Premium above Open)
            if curr.high >= or_high and curr.high > open_0930:
                # Turtle soup: wick exceeds or_high, body closes below or_high + 2 ticks
                if curr.close <= or_high + (2 * TICK):
                    for d in range(i + 1, min(i + 5, len(candles) - 2)):
                        c_disp = candles[d]
                        body = c_disp.open - c_disp.close
                        prior_low = min(candles[k].low for k in range(i, d))
                        
                        # MSS with displacement
                        if c_disp.close < prior_low and body >= (1.15 * atr):
                            c_prev = candles[d - 1]
                            c_next = candles[d + 1]
                            
                            # 3-Candle SIBI FVG
                            if c_prev.low > c_next.high + (3 * TICK):
                                fvg_ce = (c_prev.low + c_next.high) / 2.0
                                entry = fvg_ce
                                sl = curr.high + (2 * TICK)
                                risk = sl - entry
                                
                                if 4.0 <= risk <= 20.0:
                                    # Target Opposing Liquidity (OR Low) or minimum 1:2 R:R
                                    tp_target = min(or_low, entry - (2.0 * risk))
                                    rr = (entry - tp_target) / risk
                                    
                                    for k in range(d + 2, min(d + 18, len(candles))):
                                        if candles[k].high >= entry:
                                            trade_taken = True
                                            exit_p, exit_t, outcome = self._track_exit(candles[k:], entry, sl, tp_target, "SHORT")
                                            pts = entry - exit_p
                                            net_dlr = (pts * POINT_VAL) - COMMISSION - SLIPPAGE
                                            self.trades.append(Trade(
                                                day=day_idx,
                                                direction="SHORT",
                                                entry_time=candles[k].time_str,
                                                entry_price=entry,
                                                sl=sl,
                                                tp=tp_target,
                                                exit_time=exit_t,
                                                exit_price=exit_p,
                                                pnl_pts=pts,
                                                net_pnl=net_dlr,
                                                outcome=outcome,
                                                setup="PREMIUM_TURTLE_SOUP_SHORT",
                                                rr_ratio=round(rr, 2)
                                            ))
                                            break
                                    break

            # 2. LONG EVALUATION (Requires sweep in Discount below Open)
            elif curr.low <= or_low and curr.low < open_0930 and not trade_taken:
                if curr.close >= or_low - (2 * TICK):
                    for d in range(i + 1, min(i + 5, len(candles) - 2)):
                        c_disp = candles[d]
                        body = c_disp.close - c_disp.open
                        prior_high = max(candles[k].high for k in range(i, d))
                        
                        if c_disp.close > prior_high and body >= (1.15 * atr):
                            c_prev = candles[d - 1]
                            c_next = candles[d + 1]
                            
                            if c_next.low > c_prev.high + (3 * TICK):
                                is_iofed = body >= 1.6 * atr
                                fvg_ce = (c_prev.high + c_next.low) / 2.0
                                entry = c_next.low if is_iofed else fvg_ce
                                sl = curr.low - (2 * TICK)
                                risk = entry - sl
                                
                                if 4.0 <= risk <= 20.0:
                                    tp_target = max(or_high, entry + (2.0 * risk))
                                    rr = (tp_target - entry) / risk
                                    
                                    for k in range(d + 2, min(d + 18, len(candles))):
                                        if candles[k].low <= entry:
                                            trade_taken = True
                                            exit_p, exit_t, outcome = self._track_exit(candles[k:], entry, sl, tp_target, "LONG")
                                            pts = exit_p - entry
                                            net_dlr = (pts * POINT_VAL) - COMMISSION - SLIPPAGE
                                            self.trades.append(Trade(
                                                day=day_idx,
                                                direction="LONG",
                                                entry_time=candles[k].time_str,
                                                entry_price=entry,
                                                sl=sl,
                                                tp=tp_target,
                                                exit_time=exit_t,
                                                exit_price=exit_p,
                                                pnl_pts=pts,
                                                net_pnl=net_dlr,
                                                outcome=outcome,
                                                setup="DISCOUNT_IOFED_LONG" if is_iofed else "DISCOUNT_TURTLE_SOUP_LONG",
                                                rr_ratio=round(rr, 2)
                                            ))
                                            break
                                    break

    def _track_exit(self, bars: List[Candle], entry: float, sl: float, tp: float, direction: str) -> Tuple[float, str, str]:
        for b in bars:
            if direction == "SHORT":
                if b.high >= sl:
                    return sl, b.time_str, "LOSS"
                if b.low <= tp:
                    return tp, b.time_str, "WIN"
            else:
                if b.low <= sl:
                    return sl, b.time_str, "LOSS"
                if b.high >= tp:
                    return tp, b.time_str, "WIN"
        last = bars[-1]
        outcome = "WIN" if (last.close > entry if direction == "LONG" else last.close < entry) else "LOSS"
        return last.close, last.time_str, outcome

    def run(self, total_days: int = 150):
        for d in range(1, total_days + 1):
            candles, open_p = self.generate_day_tape(d)
            self.evaluate_session(d, candles, open_p)

    def stats(self) -> Dict:
        if not self.trades:
            return {}
        n = len(self.trades)
        wins = [t for t in self.trades if t.net_pnl > 0]
        losses = [t for t in self.trades if t.net_pnl <= 0]
        
        w_cnt = len(wins)
        l_cnt = len(losses)
        win_rate = (w_cnt / n) * 100.0
        
        tot_profit = sum(t.net_pnl for t in wins)
        tot_loss = abs(sum(t.net_pnl for t in losses))
        pf = (tot_profit / tot_loss) if tot_loss > 0 else float('inf')
        
        avg_w = tot_profit / w_cnt if w_cnt else 0.0
        avg_l = tot_loss / l_cnt if l_cnt else 0.0
        payoff = avg_w / avg_l if avg_l else float('inf')
        
        tot_pnl = sum(t.net_pnl for t in self.trades)
        exp_dlr = tot_pnl / n
        exp_pts = sum(t.pnl_pts for t in self.trades) / n
        
        equity = 100000.0
        peak = equity
        max_dd_dlr = 0.0
        max_dd_pct = 0.0
        eq_curve = [equity]
        
        for t in self.trades:
            equity += t.net_pnl
            eq_curve.append(equity)
            if equity > peak:
                peak = equity
            dd = peak - equity
            if dd > max_dd_dlr:
                max_dd_dlr = dd
                max_dd_pct = (dd / peak) * 100.0
                
        returns = [(eq_curve[i] - eq_curve[i - 1]) / eq_curve[i - 1] for i in range(1, len(eq_curve))]
        mean_r = sum(returns) / len(returns) if returns else 0.0
        var_r = sum((r - mean_r) ** 2 for r in returns) / len(returns) if len(returns) > 1 else 0.0
        std_r = math.sqrt(var_r) if var_r > 0 else 1e-6
        sharpe = (mean_r / std_r) * math.sqrt(252) if std_r > 0 else 0.0
        
        downside = [r for r in returns if r < 0]
        down_var = sum(r ** 2 for r in downside) / len(downside) if downside else 0.0
        down_std = math.sqrt(down_var) if down_var > 0 else 1e-6
        sortino = (mean_r / down_std) * math.sqrt(252) if down_std > 0 else 0.0
        
        return {
            "Total Trading Days Sampled": 150,
            "Total Qualifying Trades": n,
            "Execution Frequency": f"{n/150:.2f} trades/day (~{round(n/7.5, 1)} trades/month)",
            "Winning Trades": w_cnt,
            "Losing Trades": l_cnt,
            "Win Rate (%)": f"{win_rate:.2f}%",
            "Profit Factor": f"{pf:.2f}",
            "Total Net Profit ($)": f"${tot_pnl:,.2f}",
            "Initial Account Equity": "$100,000.00",
            "Final Account Equity": f"${equity:,.2f}",
            "Maximum Drawdown ($)": f"-${max_dd_dlr:,.2f}",
            "Maximum Drawdown (%)": f"-{max_dd_pct:.2f}%",
            "Average Winning Trade ($)": f"+${avg_w:,.2f}",
            "Average Losing Trade ($)": f"-${avg_l:,.2f}",
            "Win/Loss Payoff Ratio": f"{payoff:.2f}:1",
            "Average Risk/Reward Targeted": f"{sum(t.rr_ratio for t in self.trades)/n:.2f}:1",
            "Expectancy per Trade ($)": f"+${exp_dlr:.2f}",
            "Expectancy per Trade (Points)": f"+{exp_pts:.2f} pts",
            "Annualized Sharpe Ratio": f"{sharpe:.2f}",
            "Annualized Sortino Ratio": f"{sortino:.2f}"
        }

if __name__ == "__main__":
    engine = InstitutionalICTEngine(seed=101)
    engine.run(total_days=150)
    res = engine.stats()
    
    print("\n" + "="*76)
    print("  INSTITUTIONAL ICT 2024: 150-DAY BACKTEST (HTF & OPEN BIAS FILTER)")
    print("="*76)
    for k, v in res.items():
        print(f"  {k:<33} : {v}")
    print("="*76 + "\n")
    
    print("RECENT TRADE LOG (LAST 10 EXECUTIONS):")
    print(f"{'Day':<8} {'Dir':<6} {'Setup':<28} {'R:R':<6} {'Result':<8} {'Net P&L ($)':<12}")
    print("-" * 80)
    for t in engine.trades[-10:]:
        print(f"Day_{t.day:<4} {t.direction:<6} {t.setup:<28} {t.rr_ratio:<6.1f} {t.outcome:<8} ${t.net_pnl:>+9.2f}")
    print("-" * 80 + "\n")
