"""
Backtest: 1-minute volume-delta rule on Polymarket 5-minute Up/Down markets.

The rule (as proposed): use the last four COMPLETED Binance 1-minute candles; if volume delta is
above +0.20 buy Up, below -0.20 buy Down; at most one $10 paper trade per market, only when the
price, spread and depth gates pass.

PRE-REGISTERED DESIGN (fixed 2026-11-23 before the run)
  Markets     BTC, ETH, SOL, XRP 5m rounds with an official outcome, 2026-05-24 .. 2026-11-23.
  Volume delta at decision time t:  VD = sum(taker_buy - taker_sell) / sum(volume) over the 4 Binance
              1m candles that opened t-240 .. t-60 (all closed by t), in quote currency (USDT).
              taker_sell = volume - taker_buy. VD is in [-1, +1].
  Decisions   t = round open, +1, +2, +3, +4 minutes. First t where the signal and gates pass;
              one trade per market at most.
  Price       Polymarket Up price at the last history point at or before t (at most 60s old).
              Ask = side price + 1c (spread allowance).
              CORRECTION (found after the first run, before any tuning): history points sit ~4s
              after each minute, so "at or before t" was ~56s old while the signal's newest candle
              closed at t: the backtest bought at a price from BEFORE the move it reacted to. The
              valid execution is --quote after: the first history point after t (within 60s),
              i.e. a price that exists once the signal is known.
  Price gate  ask between 0.20 and 0.80 (not specified in the proposal; chosen to avoid paying
              near-certain prices or chasing long shots). Other bands are reported, not used.
  Spread/depth gates  historical order books are not available: the backtest assumes a 1c spread
              and that $10 fills at the ask. The live recorder's books (since 07:35 UTC today)
              are used separately to show how often real spreads/depth would pass.
  Trade       $10 at the ask; Polymarket fee 0.07*p*(1-p) per share; held to settlement.
  Controls    20 runs with the same entries but the side chosen by coin flip; and the opposite side.
  PASS        all of: total P&L > 0; win-rate 95% CI lower bound above the average break-even
              (ask + fee per share); at least 4 of 6 full months positive; at least 3 of 4 coins
              positive; P&L above the 95th percentile of the coin-flip controls.
Research only: reads the local history store, places no orders.
"""

import argparse
import math
import os
import random
import sqlite3
import statistics
import time
from bisect import bisect_right
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB = os.environ.get("MARKET_HISTORY_DB", os.path.join(ROOT, "real_data", "market_history.db"))
COINS = ("BTC", "ETH", "SOL", "XRP")
THRESHOLD = 0.20
STAKE = 10.0
SPREAD = 0.01
PRICE_GATE = (0.20, 0.80)
DECISION_OFFSETS = (0, 60, 120, 180, 240)
MAX_QUOTE_AGE = 60


class Flow:
    """Binance 1m quote volume and taker-buy quote volume on a minute grid."""

    def __init__(self, t: np.ndarray, qv: np.ndarray, tbq: np.ndarray):
        self.t0 = int(t[0])
        n = int((t[-1] - t[0]) // 60) + 1
        self.qv = np.full(n, np.nan)
        self.tbq = np.full(n, np.nan)
        idx = ((t - self.t0) // 60).astype(int)
        self.qv[idx], self.tbq[idx] = qv, tbq

    def volume_delta(self, t_decision: int, n: int = 4) -> Optional[float]:
        """VD over the n completed 1m candles before t_decision (opened t-60n .. t-60)."""
        end = (t_decision - self.t0) // 60          # index of the candle opening at t (still forming)
        start = end - n
        if start < 0 or end > len(self.qv):
            return None
        q, b = self.qv[start:end], self.tbq[start:end]
        if np.isnan(q).any() or q.sum() <= 0:
            return None
        return float((2 * b.sum() - q.sum()) / q.sum())


def load_flow(db: str, coin: str) -> Optional[Flow]:
    with sqlite3.connect(db) as c:
        rows = c.execute("SELECT t, quote_volume, taker_buy_quote FROM binance_1m WHERE symbol=? ORDER BY t", (f"{coin}USDT",)).fetchall()
    if not rows:
        return None
    a = np.array(rows, dtype=float)
    return Flow(a[:, 0].astype(np.int64), a[:, 1], a[:, 2])


def load_markets(db: str, coin: str) -> Dict[int, Dict]:
    with sqlite3.connect(db) as c:
        rounds = {r: o for r, o in c.execute("SELECT round_ts, outcome FROM pm_rounds WHERE coin=? AND outcome IS NOT NULL", (coin,))}
        prices: Dict[int, List[Tuple[int, float]]] = {}
        for r, t, p in c.execute("SELECT round_ts, t, p_up FROM pm_prices WHERE coin=? ORDER BY round_ts, t", (coin,)):
            prices.setdefault(r, []).append((t, p))
    return {r: {"outcome": o, "prices": prices.get(r, [])} for r, o in rounds.items() if prices.get(r)}


def up_price_after(points: List[Tuple[int, float]], t: int, max_wait: int = MAX_QUOTE_AGE) -> Optional[float]:
    """First Up price strictly after t (within max_wait seconds): executable once the signal is known."""
    ts = [p[0] for p in points]
    i = bisect_right(ts, t)
    if i >= len(points) or points[i][0] - t > max_wait:
        return None
    p = points[i][1]
    return p if 0.0 < p < 1.0 else None


def up_price_at(points: List[Tuple[int, float]], t: int, max_age: int = MAX_QUOTE_AGE) -> Optional[float]:
    """Last Up price at or before t, if it is at most max_age seconds old."""
    ts = [p[0] for p in points]
    i = bisect_right(ts, t) - 1
    if i < 0 or t - points[i][0] > max_age:
        return None
    p = points[i][1]
    return p if 0.0 < p < 1.0 else None


def fee(shares: float, p: float) -> float:
    return shares * 0.07 * p * (1 - p)


def settle(side: str, ask: float, outcome: str, stake: float = STAKE) -> float:
    shares = stake / ask
    return (shares if side == outcome else 0.0) - stake - fee(shares, ask)


def find_entry(flow: Flow, rts: int, points, threshold: float = THRESHOLD,
               gate: Tuple[float, float] = PRICE_GATE, quote: str = "after") -> Optional[Dict]:
    for off in DECISION_OFFSETS:
        t = rts + off
        vd = flow.volume_delta(t)
        if vd is None or abs(vd) <= threshold:
            continue
        up = up_price_after(points, t) if quote == "after" else up_price_at(points, t)
        if up is None:
            continue
        side = "UP" if vd > 0 else "DOWN"
        ask = (up if side == "UP" else 1 - up) + SPREAD
        if not (gate[0] <= ask <= gate[1]):
            continue
        return {"t": t, "offset": off, "vd": vd, "side": side, "ask": ask}
    return None


def run(db: str = DEFAULT_DB, coins: Sequence[str] = COINS, threshold: float = THRESHOLD,
        gate: Tuple[float, float] = PRICE_GATE, verbose: bool = True, quote: str = "after") -> List[Dict]:
    trades = []
    for coin in coins:
        flow = load_flow(db, coin)
        if flow is None:
            continue
        markets = load_markets(db, coin)
        n0 = len(trades)
        for rts, m in markets.items():
            e = find_entry(flow, rts, m["prices"], threshold, gate, quote)
            if e:
                e.update(coin=coin, round_ts=rts, outcome=m["outcome"], pnl=settle(e["side"], e["ask"], m["outcome"]))
                trades.append(e)
        if verbose:
            print(f"  {coin}: {len(markets):,} markets, {len(trades) - n0:,} trades", flush=True)
    return trades


def wilson(k: int, n: int, z: float = 1.96) -> Tuple[float, float]:
    if n == 0:
        return 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - h, c + h


def coin_flip(trades: List[Dict], seed: int) -> float:
    rng = random.Random(seed)
    tot = 0.0
    for t in trades:
        side = rng.choice(("UP", "DOWN"))
        up = (t["ask"] - SPREAD) if t["side"] == "UP" else 1 - (t["ask"] - SPREAD)
        ask = (up if side == "UP" else 1 - up) + SPREAD
        if 0 < ask < 1:
            tot += settle(side, ask, t["outcome"])
    return tot


def opposite(trades: List[Dict]) -> float:
    tot = 0.0
    for t in trades:
        up = (t["ask"] - SPREAD) if t["side"] == "UP" else 1 - (t["ask"] - SPREAD)
        side = "DOWN" if t["side"] == "UP" else "UP"
        ask = (up if side == "UP" else 1 - up) + SPREAD
        if 0 < ask < 1:
            tot += settle(side, ask, t["outcome"])
    return tot


def report(trades: List[Dict], controls: List[float], fade: float, variants: Dict[str, List[Dict]]) -> Tuple[str, bool]:
    L = []
    n = len(trades)
    wins = sum(t["side"] == t["outcome"] for t in trades)
    pnl = sum(t["pnl"] for t in trades)
    avg_ask = statistics.mean(t["ask"] for t in trades) if trades else 0.0
    be = statistics.mean(t["ask"] + 0.07 * t["ask"] * (1 - t["ask"]) for t in trades) if trades else 0.0
    lo, hi = wilson(wins, n)
    L.append(f"Volume-delta rule on Polymarket 5m (|VD| > {THRESHOLD}, last 4 completed Binance 1m candles, $10, ask {PRICE_GATE[0]}-{PRICE_GATE[1]})")
    L.append("=" * len(L[0]))
    L.append(f"trades {n:,} | win {wins/n*100:.2f}% (95% CI {lo*100:.2f}-{hi*100:.2f}) | avg ask {avg_ask:.3f} | "
             f"break-even {be*100:.2f}% | P&L {pnl:+,.2f} on ${n*STAKE:,.0f} staked ({pnl/(n*STAKE)*100:+.2f}%)")

    def table(title, key):
        L.append(title)
        g: Dict[str, List[Dict]] = {}
        for t in trades:
            g.setdefault(key(t), []).append(t)
        for k in sorted(g):
            v = g[k]
            w = sum(x["side"] == x["outcome"] for x in v)
            p = sum(x["pnl"] for x in v)
            L.append(f"  {k:<16} {len(v):>6} trades  win {w/len(v)*100:5.1f}%  avg ask {statistics.mean(x['ask'] for x in v):.3f}  "
                     f"P&L {p:+10.2f} ({p/(len(v)*STAKE)*100:+.2f}%)")
    table("by coin", lambda t: t["coin"])
    table("by month", lambda t: time.strftime("%Y-%m", time.gmtime(t["round_ts"])))
    table("by entry minute (seconds into the round)", lambda t: f"+{t['offset']:>3}s")
    table("by |volume delta|", lambda t: "0.20-0.30" if abs(t["vd"]) < 0.3 else ("0.30-0.45" if abs(t["vd"]) < 0.45 else "0.45+"))
    table("by side", lambda t: t["side"])
    L.append("")
    L.append(f"controls: coin-flip side median {statistics.median(controls):+,.2f}, 95th pct {np.percentile(controls, 95):+,.2f} | "
             f"opposite side {fade:+,.2f}")
    L.append("price-gate sensitivity (same rule, other ask bands; not part of the pass mark):")
    for k, v in variants.items():
        if v:
            w = sum(x["side"] == x["outcome"] for x in v)
            p = sum(x["pnl"] for x in v)
            L.append(f"  {k:<14} {len(v):>6} trades  win {w/len(v)*100:5.1f}%  avg ask {statistics.mean(x['ask'] for x in v):.3f}  "
                     f"P&L {p:+10.2f} ({p/(len(v)*STAKE)*100:+.2f}%)")
    months: Dict[str, float] = {}
    for t in trades:
        k = time.strftime("%Y-%m", time.gmtime(t["round_ts"]))
        months[k] = months.get(k, 0.0) + t["pnl"]
    full = {k: v for k, v in months.items() if k not in ("2026-05", "2026-11")}
    coins: Dict[str, float] = {}
    for t in trades:
        coins[t["coin"]] = coins.get(t["coin"], 0.0) + t["pnl"]
    p95 = float(np.percentile(controls, 95))
    checks = {"P&L > 0": pnl > 0, "win CI above break-even": lo > be,
              f"full months positive {sum(v > 0 for v in full.values())}/{len(full)} (need 4)": sum(v > 0 for v in full.values()) >= 4,
              f"coins positive {sum(v > 0 for v in coins.values())}/4 (need 3)": sum(v > 0 for v in coins.values()) >= 3,
              "beats 95th pct of coin flips": pnl > p95}
    ok = all(checks.values())
    L.append("PASS MARK: " + " | ".join(f"{k} {v}" for k, v in checks.items()) + f"  ==> {'PASS' if ok else 'FAIL'}")
    return "\n".join(L), ok


def main(argv=None):
    ap = argparse.ArgumentParser(description="Backtest the 1m volume-delta rule on Polymarket 5m markets")
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--controls", type=int, default=20)
    ap.add_argument("--quote", choices=["after", "before"], default="after",
                    help="after = first price after the signal (valid); before = last price before it (stale, look-ahead)")
    ap.add_argument("--out", default=os.path.join(ROOT, "docs", "PM5M_VOLUME_DELTA_RESULTS.md"))
    args = ap.parse_args(argv)
    print("running pre-registered rule ...", flush=True)
    trades = run(args.db, quote=args.quote)
    controls = [coin_flip(trades, s) for s in range(args.controls)]
    variants = {}
    for name, g in (("no price gate", (0.0, 0.99)), ("ask <= 0.60", (0.0, 0.60)), ("ask 0.60-0.90", (0.60, 0.90))):
        variants[name] = run(args.db, gate=g, verbose=False, quote=args.quote)
    text, ok = report(trades, controls, opposite(trades), variants)
    text = f"quote timing: {args.quote} the signal\n" + text
    print("\n" + text)
    with open(args.out, "w") as f:
        f.write("```\n" + text + "\n```\n\nSee research/pm5m_volume_delta.py for the pre-registered design.\n")
    print(f"\nreport written to {args.out}")


if __name__ == "__main__":
    main()
