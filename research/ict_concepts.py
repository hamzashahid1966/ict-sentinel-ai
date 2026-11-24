"""
ICT concept test: do the core ICT setups predict direction on 6 months of real Binance data?

Each concept is coded with one exact definition, fixed before any result was seen, and traded
with the SAME execution so the concepts are compared on their signals, not on exit tuning.

PRE-REGISTERED DESIGN (fixed 2026-11-23)
  Data        Binance USDT-M 1-minute bars, 12 coins, 183 days. Setups are detected on CLOSED 5-minute
              bars built from the minutes; trades are executed and managed on 1-minute bars.
  Concepts    (bullish shown; bearish is the mirror)
   1 FVG      Fair value gap: low[i] > high[i-2], with displacement (candle i-1 green, body >= 1.5x the
              mean body of the previous 20 bars). Limit entry at the gap's 50% (consequent encroachment)
              within the next hour; stop at candle 1's low (low[i-2]).
   2 SWEEP_MSS Liquidity sweep then market structure shift: bar j takes the lowest low of the prior 20
              bars (sell-side liquidity); within the next 6 bars, a CLOSE above the highest high of the 5
              bars before the sweep, without the sweep low breaking again. Market entry at the next
              open; stop at the sweep low.
   3 KILLZONE Not a separate signal: every trade of every concept is tagged London killzone
              (02:00-05:00 New York time), New York killzone (07:00-10:00 NY) or outside, to test
              whether ICT timing improves results.
   4 OTE      Optimal trade entry with higher-timeframe bias: 1h close above a rising EMA50 (bias up).
              On 5m, an impulse leg in the last 24 bars from swing low L to swing high H (H printed 1-6
              bars ago, leg >= 3x ATR14, price now below H). Limit entry at the 70.5% retracement
              (H - 0.705*(H-L)) within the next hour, untouched since H; stop at L.
   5 SMT      BTC/ETH divergence: one coin takes its 20-bar high (low) on a bar while the other does
              not. Trade the coin that swept, against the sweep, at the next open; stop at its sweep
              extreme.
  Filters     stop width 0.30%-3.00% of price (narrower stops are dominated by costs). One open trade
              per coin per concept.
  Execution   target 2R, time exit after 4 hours. Limit entries fill only when price trades THROUGH
              the level; targets fill only when price trades through. Market entries and all stop /
              time exits pay 0.02% slippage; every fill pays the 0.05% taker fee. Inside a 1-minute
              bar the stop is checked first; a limit fill's own bar can stop it out but not reach target.
  Measure     R per trade: gross (direction only) and NET (after fees and slippage).
  Control     per concept, 20 runs with the same entries (coin, time, price, stop width) but the
              direction chosen by coin flip, executed identically.
  PASS        per concept, all of: (1) mean NET R 95% CI (bootstrap by trading day) above 0;
              (2) at least 4 of 6 months with positive net R; (3) mean net R above the 95th percentile
              of the 20 random-direction controls. Five concepts are tested, so one pass by luck
              is possible; a real edge should pass clearly.
Research only: reads the local history store, places no orders.

Usage:
  python3 -m research.ict_concepts                  # 12 coins, 183 days
  python3 -m research.ict_concepts --coins BTC,ETH --days 60
"""

import argparse
import math
import os
import random
import statistics
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

import numpy as np

from research.crypto_backtest import CoinData, load_coin, DEFAULT_DB, ROOT

COINS = ["BTC", "ETH", "SOL", "XRP", "BNB", "DOGE", "ZEC", "HYPE", "NEAR", "SUI", "ADA", "LINK"]
FEE = 0.0005
SLIP = 0.0002
TARGET_R = 2.0
MAX_HOLD = 4 * 3600
FILL_WINDOW = 12 * 300
MIN_STOP, MAX_STOP = 0.003, 0.03
NY = ZoneInfo("America/New_York")
LIMIT_CONCEPTS = {"FVG", "OTE"}


@dataclass
class Setup:
    symbol: str
    concept: str
    direction: str          # LONG / SHORT
    t_signal: int           # time the setup is known (close of its last 5m bar)
    kind: str               # "market" or "limit"
    level: float            # limit price (limit) or reference close (market)
    stop: float
    expiry: int


@dataclass
class Trade:
    symbol: str
    concept: str
    direction: str
    entry_time: int
    entry: float
    stop: float
    exit_time: int
    exit: float
    reason: str
    gross_r: float
    net_r: float
    session: str


# ── 5-minute arrays (closed bars only) ───────────────────────────────────────

class Bars5:
    def __init__(self, d: CoinData):
        bs = d.bars[300]
        self.t = np.array([b.timestamp for b in bs], dtype=np.int64)
        self.o = np.array([b.open for b in bs])
        self.h = np.array([b.high for b in bs])
        self.l = np.array([b.low for b in bs])
        self.c = np.array([b.close for b in bs])
        hb = d.bars[3600]
        self.h1_t = np.array([b.timestamp for b in hb], dtype=np.int64)
        self.h1_c = np.array([b.close for b in hb])

    def close_time(self, i: int) -> int:
        return int(self.t[i]) + 300


def _ok_width(entry: float, stop: float) -> bool:
    w = abs(entry - stop) / entry if entry > 0 else 0.0
    return MIN_STOP <= w <= MAX_STOP


def detect_fvg(sym: str, b: Bars5) -> List[Setup]:
    out = []
    body = np.abs(b.c - b.o)
    for i in range(22, len(b.t)):
        if b.t[i] - b.t[i - 2] != 600:
            continue
        mean_body = body[i - 21:i - 1].mean()
        if mean_body <= 0 or body[i - 1] < 1.5 * mean_body:
            continue
        ts = b.close_time(i)
        if b.c[i - 1] > b.o[i - 1] and b.l[i] > b.h[i - 2]:
            lvl, stop = (b.l[i] + b.h[i - 2]) / 2, b.l[i - 2]
            if _ok_width(lvl, stop):
                out.append(Setup(sym, "FVG", "LONG", ts, "limit", lvl, stop, ts + FILL_WINDOW))
        elif b.c[i - 1] < b.o[i - 1] and b.h[i] < b.l[i - 2]:
            lvl, stop = (b.h[i] + b.l[i - 2]) / 2, b.h[i - 2]
            if _ok_width(lvl, stop):
                out.append(Setup(sym, "FVG", "SHORT", ts, "limit", lvl, stop, ts + FILL_WINDOW))
    return out


def detect_sweep_mss(sym: str, b: Bars5) -> List[Setup]:
    out = []
    n = len(b.t)
    for j in range(20, n - 1):
        lo20, hi20 = b.l[j - 20:j].min(), b.h[j - 20:j].max()
        if b.l[j] < lo20:      # sell-side liquidity taken -> look for bullish shift
            swing_high, sweep_low = b.h[j - 5:j].max(), b.l[j]
            for k in range(j + 1, min(n, j + 7)):
                if b.l[k] < sweep_low:
                    break
                if b.c[k] > swing_high:
                    if _ok_width(b.c[k], sweep_low):
                        ts = b.close_time(k)
                        out.append(Setup(sym, "SWEEP_MSS", "LONG", ts, "market", b.c[k], sweep_low, ts + 300))
                    break
        if b.h[j] > hi20:      # buy-side liquidity taken -> look for bearish shift
            swing_low, sweep_high = b.l[j - 5:j].min(), b.h[j]
            for k in range(j + 1, min(n, j + 7)):
                if b.h[k] > sweep_high:
                    break
                if b.c[k] < swing_low:
                    if _ok_width(b.c[k], sweep_high):
                        ts = b.close_time(k)
                        out.append(Setup(sym, "SWEEP_MSS", "SHORT", ts, "market", b.c[k], sweep_high, ts + 300))
                    break
    return out


def _ema(x: np.ndarray, span: int) -> np.ndarray:
    a = 2 / (span + 1)
    out = np.empty_like(x)
    out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = a * x[i] + (1 - a) * out[i - 1]
    return out


def _atr(b: Bars5, n: int = 14) -> np.ndarray:
    prev_c = np.r_[b.c[0], b.c[:-1]]
    tr = np.maximum(b.h - b.l, np.maximum(np.abs(b.h - prev_c), np.abs(b.l - prev_c)))
    out = np.full(len(tr), np.nan)
    cs = np.cumsum(tr)
    out[n - 1:] = (cs[n - 1:] - np.r_[0, cs[:-n]]) / n
    return out


def htf_bias(b: Bars5, ts: int, ema50: np.ndarray) -> int:
    """+1 / -1 / 0 from the last CLOSED 1h bar at time ts: close vs a rising / falling EMA50."""
    k = int(np.searchsorted(b.h1_t, ts - 3600, side="right")) - 1
    if k < 55:
        return 0
    if b.h1_c[k] > ema50[k] and ema50[k] > ema50[k - 5]:
        return 1
    if b.h1_c[k] < ema50[k] and ema50[k] < ema50[k - 5]:
        return -1
    return 0


def detect_ote(sym: str, b: Bars5) -> List[Setup]:
    out = []
    if len(b.h1_c) < 60:
        return out
    ema50 = _ema(b.h1_c, 50)
    atr = _atr(b)
    used = set()
    for i in range(30, len(b.t)):
        if np.isnan(atr[i]):
            continue
        ts = b.close_time(i)
        bias = htf_bias(b, ts, ema50)
        if bias == 0:
            continue
        w0 = i - 23
        if bias > 0:
            ih = w0 + int(np.argmax(b.h[w0:i + 1]))
            if not (i - 6 <= ih <= i - 1) or ih <= w0 or (sym, "L", ih) in used:
                continue
            il = w0 + int(np.argmin(b.l[w0:ih]))
            H, L = b.h[ih], b.l[il]
            if H - L < 3 * atr[i] or b.c[i] >= H:
                continue
            lvl = H - 0.705 * (H - L)
            if b.l[ih + 1:i + 1].min() <= lvl or not _ok_width(lvl, L):
                continue
            used.add((sym, "L", ih))
            out.append(Setup(sym, "OTE", "LONG", ts, "limit", lvl, L, ts + FILL_WINDOW))
        else:
            il = w0 + int(np.argmin(b.l[w0:i + 1]))
            if not (i - 6 <= il <= i - 1) or il <= w0 or (sym, "S", il) in used:
                continue
            ih = w0 + int(np.argmax(b.h[w0:il]))
            H, L = b.h[ih], b.l[il]
            if H - L < 3 * atr[i] or b.c[i] <= L:
                continue
            lvl = L + 0.705 * (H - L)
            if b.h[il + 1:i + 1].max() >= lvl or not _ok_width(lvl, H):
                continue
            used.add((sym, "S", il))
            out.append(Setup(sym, "OTE", "SHORT", ts, "limit", lvl, H, ts + FILL_WINDOW))
    return out


def detect_smt(btc: Bars5, eth: Bars5) -> List[Setup]:
    out = []
    common = np.intersect1d(btc.t, eth.t)
    ib = {int(t): i for i, t in enumerate(btc.t)}
    ie = {int(t): i for i, t in enumerate(eth.t)}
    for t in common[21:]:
        i, j = ib[int(t)], ie[int(t)]
        if i < 20 or j < 20:
            continue
        b_hh, e_hh = btc.h[i] > btc.h[i - 20:i].max(), eth.h[j] > eth.h[j - 20:j].max()
        b_ll, e_ll = btc.l[i] < btc.l[i - 20:i].min(), eth.l[j] < eth.l[j - 20:j].min()
        ts = int(t) + 300
        for sym, bars, k, swept_hi, swept_lo, other_hi, other_lo in (("BTCUSDT", btc, i, b_hh, b_ll, e_hh, e_ll),
                                                                     ("ETHUSDT", eth, j, e_hh, e_ll, b_hh, b_ll)):
            if swept_hi and not other_hi and _ok_width(bars.c[k], bars.h[k]):
                out.append(Setup(sym, "SMT", "SHORT", ts, "market", bars.c[k], bars.h[k], ts + 300))
            if swept_lo and not other_lo and _ok_width(bars.c[k], bars.l[k]):
                out.append(Setup(sym, "SMT", "LONG", ts, "market", bars.c[k], bars.l[k], ts + 300))
    return out


# ── execution on 1-minute bars ───────────────────────────────────────────────

def session_of(ts: int) -> str:
    h = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(NY).hour
    if 2 <= h < 5:
        return "LONDON_KZ"
    if 7 <= h < 10:
        return "NY_KZ"
    return "OUTSIDE_KZ"


def simulate(d: CoinData, s: Setup, direction: Optional[str] = None, fill_override: Optional[Tuple[int, float, bool]] = None,
             stop_override: Optional[float] = None) -> Optional[Trade]:
    """Fill the setup, then manage stop / 2R target / 4h time exit on 1-minute bars."""
    direction = direction or s.direction
    long = direction == "LONG"
    # 1. entry
    if fill_override:
        fill_t, fill, limit_fill = fill_override
    elif s.kind == "market":
        i = d.idx(s.t_signal)
        if i is None:
            return None
        fill_t = s.t_signal
        fill = float(d.o[i]) * (1 + SLIP if long else 1 - SLIP)
        limit_fill = False
    else:
        fill_t = None
        for m in range(s.t_signal, s.expiry, 60):
            i = d.idx(m)
            if i is None:
                continue
            if (long and d.l[i] < s.level) or (not long and d.h[i] > s.level):
                fill_t, fill = m, float(min(d.o[i], s.level) if long else max(d.o[i], s.level))
                break
            if (long and d.l[i] <= s.stop) or (not long and d.h[i] >= s.stop):
                return None
        if fill_t is None:
            return None
        limit_fill = True
    stop = stop_override if stop_override is not None else s.stop
    if (long and fill <= stop) or (not long and fill >= stop):
        return None
    risk = abs(fill - stop)
    target = fill + TARGET_R * risk if long else fill - TARGET_R * risk
    # 2. manage
    exit_px, exit_t, reason = None, None, None
    for m in range(fill_t, fill_t + MAX_HOLD, 60):
        i = d.idx(m)
        if i is None:
            continue
        o, h, l, c = float(d.o[i]), float(d.h[i]), float(d.l[i]), float(d.c[i])
        if (long and l <= stop) or (not long and h >= stop):
            lvl = min(o, stop) if long else max(o, stop)
            if m == fill_t and limit_fill:
                lvl = stop
            exit_px, exit_t, reason = lvl * (1 - SLIP if long else 1 + SLIP), m + 60, "STOP"
            break
        if not (m == fill_t and limit_fill) and ((long and h > target) or (not long and l < target)):
            exit_px, exit_t, reason = target, m + 60, "TARGET"
            break
    if exit_px is None:
        i = d.idx(fill_t + MAX_HOLD - 60)
        if i is None:
            return None
        exit_px, exit_t, reason = float(d.c[i]) * (1 - SLIP if long else 1 + SLIP), fill_t + MAX_HOLD, "TIME"
    sgn = 1 if long else -1
    gross = sgn * (exit_px - fill)
    net = gross - FEE * (fill + exit_px)
    return Trade(s.symbol, s.concept, direction, fill_t, fill, stop, exit_t, exit_px, reason,
                 gross / risk, net / risk, session_of(fill_t))


def run_concept(data: Dict[str, CoinData], setups: List[Setup]) -> List[Trade]:
    """One open trade per coin per concept: a setup is skipped while the previous one is still open."""
    trades = []
    busy_until: Dict[str, int] = {}
    for s in sorted(setups, key=lambda x: x.t_signal):
        if s.t_signal < busy_until.get(s.symbol, 0):
            continue
        tr = simulate(data[s.symbol], s)
        if tr:
            trades.append(tr)
            busy_until[s.symbol] = tr.exit_time
    return trades


def random_direction(data: Dict[str, CoinData], trades: List[Trade], seed: int) -> List[Trade]:
    rng = random.Random(seed)
    out = []
    for t in trades:
        direction = rng.choice(("LONG", "SHORT"))
        width = abs(t.entry - t.stop)
        stop = t.entry - width if direction == "LONG" else t.entry + width
        s = Setup(t.symbol, t.concept, direction, t.entry_time, "market", t.entry, stop, t.entry_time + 300)
        tr = simulate(data[t.symbol], s, direction=direction,
                      fill_override=(t.entry_time, t.entry, t.concept in LIMIT_CONCEPTS), stop_override=stop)
        if tr:
            out.append(tr)
    return out


# ── statistics and report ────────────────────────────────────────────────────

def day_bootstrap_ci(trades: List[Trade], n_boot: int = 2000, seed: int = 0) -> Tuple[float, float, float]:
    if not trades:
        return 0.0, 0.0, 0.0
    by_day: Dict[int, List[float]] = {}
    for t in trades:
        by_day.setdefault(t.entry_time // 86400, []).append(t.net_r)
    sums = np.array([sum(v) for v in by_day.values()])
    cnts = np.array([len(v) for v in by_day.values()])
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(sums), size=(n_boot, len(sums)))
    boots = sums[idx].sum(axis=1) / cnts[idx].sum(axis=1)
    return float(sums.sum() / cnts.sum()), float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))


def evaluate(name: str, trades: List[Trade], controls: List[List[Trade]]) -> Dict:
    mean, lo, hi = day_bootstrap_ci(trades)
    months: Dict[str, float] = {}
    for t in trades:
        k = time.strftime("%Y-%m", time.gmtime(t.entry_time))
        months[k] = months.get(k, 0.0) + t.net_r
    ctrl = [statistics.mean(x.net_r for x in c) for c in controls if c]
    p95 = float(np.percentile(ctrl, 95)) if ctrl else float("nan")
    full = [k for k in months]
    pos = sum(1 for k in full if months[k] > 0)
    res = {"name": name, "n": len(trades), "win": sum(t.net_r > 0 for t in trades) / len(trades) if trades else 0.0,
           "gross_r": statistics.mean(t.gross_r for t in trades) if trades else 0.0, "net_r": mean, "ci": (lo, hi),
           "total_r": sum(t.net_r for t in trades), "months": months, "months_pos": pos, "months_n": len(full),
           "ctrl_median": statistics.median(ctrl) if ctrl else float("nan"), "ctrl_p95": p95,
           "sessions": {}, "coins": {}, "exits": {}}
    for key, attr in (("sessions", "session"), ("coins", "symbol"), ("exits", "reason")):
        g: Dict[str, List[float]] = {}
        for t in trades:
            g.setdefault(getattr(t, attr), []).append(t.net_r)
        res[key] = {k: (len(v), statistics.mean(v)) for k, v in g.items()}
    res["pass"] = lo > 0 and pos >= 4 and (not ctrl or mean > p95)
    return res


def format_report(results: List[Dict], span: str, coins: List[str]) -> str:
    L = [f"ICT concept test on real Binance 1m data ({', '.join(c.replace('USDT','') for c in coins)}; {span})"]
    L.append("=" * len(L[0]))
    L.append("R = profit in units of the stop distance. Net R is after the 0.05% fee per side and 0.02% slippage.")
    L.append("")
    L.append(f"{'concept':<10} {'trades':>6} {'win':>6} {'gross R':>8} {'net R':>8} {'net R 95% CI':>18} {'total R':>9} "
             f"{'months +':>9} {'random med':>11} {'random p95':>11}  verdict")
    for r in results:
        L.append(f"{r['name']:<10} {r['n']:>6} {r['win']*100:5.1f}% {r['gross_r']:+8.3f} {r['net_r']:+8.3f} "
                 f"({r['ci'][0]:+.3f}, {r['ci'][1]:+.3f}) {r['total_r']:+9.1f} {r['months_pos']:>4}/{r['months_n']:<4} "
                 f"{r['ctrl_median']:+11.3f} {r['ctrl_p95']:+11.3f}  {'PASS' if r['pass'] else 'FAIL'}")
    L.append("")
    L.append("killzones (net R per trade by session of entry, New York time):")
    for r in results:
        L.append(f"  {r['name']:<10} " + " | ".join(f"{k}: {n} trades {m:+.3f}R" for k, (n, m) in sorted(r["sessions"].items())))
    L.append("")
    L.append("by coin (net R per trade):")
    for r in results:
        L.append(f"  {r['name']:<10} " + " ".join(f"{k.replace('USDT','')}:{m:+.2f}({n})" for k, (n, m) in sorted(r["coins"].items())))
    L.append("")
    L.append("by exit:")
    for r in results:
        L.append(f"  {r['name']:<10} " + " | ".join(f"{k}: {n} trades {m:+.3f}R" for k, (n, m) in sorted(r["exits"].items())))
    L.append("")
    L.append("by month (total net R):")
    for r in results:
        L.append(f"  {r['name']:<10} " + " ".join(f"{k}:{v:+.1f}" for k, v in sorted(r["months"].items())))
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Test core ICT concepts on real Binance 1m history")
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--coins", default=",".join(COINS))
    ap.add_argument("--days", type=int, default=183)
    ap.add_argument("--controls", type=int, default=20)
    ap.add_argument("--out", default=os.path.join(ROOT, "docs", "ICT_CONCEPTS_RESULTS.md"))
    args = ap.parse_args(argv)
    end_ts = int(time.time() // 3600) * 3600 - 3600
    start_ts = end_ts - args.days * 86400
    data: Dict[str, CoinData] = {}
    bars: Dict[str, Bars5] = {}
    for c in [x.strip().upper() for x in args.coins.split(",") if x.strip()]:
        sym = f"{c}USDT"
        d = load_coin(args.db, sym, start_ts, end_ts + 6 * 3600)
        if d is None or len(d.t) < 10000:
            print(f"  {sym}: not enough data; skipped", flush=True)
            continue
        data[sym], bars[sym] = d, Bars5(d)
        print(f"  loaded {sym}: {len(d.t):,} minutes", flush=True)
    t0 = time.time()
    setups: Dict[str, List[Setup]] = {"FVG": [], "SWEEP_MSS": [], "OTE": [], "SMT": []}
    for sym, b in bars.items():
        setups["FVG"] += detect_fvg(sym, b)
        setups["SWEEP_MSS"] += detect_sweep_mss(sym, b)
        setups["OTE"] += detect_ote(sym, b)
    if "BTCUSDT" in bars and "ETHUSDT" in bars:
        setups["SMT"] = detect_smt(bars["BTCUSDT"], bars["ETHUSDT"])
    print("setups: " + ", ".join(f"{k} {len(v):,}" for k, v in setups.items()) + f" ({time.time() - t0:.0f}s)", flush=True)
    results = []
    for name, ss in setups.items():
        if not ss:
            continue
        tr = run_concept(data, ss)
        controls = [random_direction(data, tr, seed) for seed in range(args.controls)]
        results.append(evaluate(name, tr, controls))
        print(f"  {name}: {len(tr):,} trades simulated ({time.time() - t0:.0f}s)", flush=True)
    span = f"{time.strftime('%Y-%m-%d', time.gmtime(start_ts))}..{time.strftime('%Y-%m-%d', time.gmtime(end_ts))}"
    text = format_report(results, span, list(data))
    print("\n" + text)
    with open(args.out, "w") as f:
        f.write("```\n" + text + "\n```\n\nSee research/ict_concepts.py for the pre-registered definitions.\n")
    print(f"\nreport written to {args.out}")


if __name__ == "__main__":
    main()
