"""
The user's Polymarket 5-minute rule, tested before building it.

PRE-REGISTERED 2026-11-26, before running. Per 5-minute BTC round, $1:
  side      TREND1  the side that won the previous 5-minute round ("previous candle close")
            TREND3  the side that won at least 2 of the previous 3 rounds ("trend")
  entry     first price at least 30 s into the round; buy only if that side costs <= 0.65 (+1c spread)
  exit      cash out as soon as the side can be sold for >= +40% on the stake (sell price = price - 1c),
            otherwise hold to the result. Also shown: +50% and hold-only.
  costs     taker fee 0.07 * p * (1 - p) per share on the buy and on any sell
Data A: Polymarket price history (minute prices, ~41 days, research/pm15m.py cache).
Data B: the recorder's real best bid/ask every few seconds (2026-11-23 onward) for the same rule.
Control: same rounds and timing, side by coin flip.
"""
import bisect
import json
import sqlite3

import numpy as np

from research import pm15m as pm

FEE, SPREAD, MAX_PX = 0.07, 0.01, 0.65


def fee(p, shares):
    return shares * FEE * p * (1 - p)


def trade(px_in, path, won, tp):
    """$1 at px_in; path = [(sell price), ...] after entry; tp = profit target as a fraction (None = hold)."""
    shares = 1.0 / px_in
    cost = 1.0 + fee(px_in, shares)
    if tp is not None:
        for sp in path:
            val = shares * sp - fee(sp, shares)
            if val - cost >= tp:
                return val - cost
    return shares * (1.0 if won else 0.0) - cost


def run_history():
    pm.use_timeframe("5m")
    rounds = {}
    for ln in open(pm.ROUNDS):
        try:
            r = json.loads(ln)
        except Exception:
            continue
        if not r.get("missing") and len(r.get("up", [])) >= 3:
            rounds[r["start"]] = r
    starts = sorted(rounds)
    res = {}
    for sig in ("TREND1", "TREND3"):
        for tp in (0.40, 0.50, None):
            for ctrl in (False, True):
                rng = np.random.default_rng(7)
                out = []
                for s in starts:
                    prev = [rounds.get(s - 300 * k) for k in (1, 2, 3)]
                    if sig == "TREND1":
                        if not prev[0]:
                            continue
                        side = prev[0]["winner"]
                    else:
                        if not all(prev):
                            continue
                        ups = sum(p["winner"] == "Up" for p in prev)
                        side = "Up" if ups >= 2 else "Down"
                    if ctrl:
                        side = "Up" if rng.random() < 0.5 else "Down"
                    r = rounds[s]
                    p_up = pm.price_at(r["up"], s + 30)
                    if p_up is None:
                        continue
                    sp = p_up if side == "Up" else 1 - p_up
                    px_in = sp + SPREAD
                    if px_in > MAX_PX or px_in <= 0.02:
                        continue
                    path = [((p if side == "Up" else 1 - p) - SPREAD) for t, p in r["up"] if t > s + 30 and t < s + 300]
                    out.append((s, trade(px_in, path, side == r["winner"], tp)))
                res[(sig, tp, ctrl)] = out
    return res


def run_recorder():
    db = sqlite3.connect("file:polymarket_sentinel/round_recorder.db?mode=ro", uri=True)
    def series(src):
        rows = db.execute("select ts, value from ticks where coin='BTC' and source=? order by ts", (src,)).fetchall()
        return [r[0] for r in rows], [r[1] for r in rows]
    at, av = series("pm_up_ask")
    bt, bv = series("pm_up_bid")
    rs = {r: json.loads(s).get("outcome_official") for r, s in db.execute("select round_ts, summary_json from rounds where coin='BTC'")}
    rs = {r: o for r, o in rs.items() if o in ("UP", "DOWN")}
    res = {}
    for tp in (0.40, None):
        for ctrl in (False, True):
            rng = np.random.default_rng(7)
            out = []
            for r in sorted(rs):
                if r < at[0] + 60 or (r - 300) not in rs:
                    continue
                side = rs[r - 300]
                if ctrl:
                    side = "UP" if rng.random() < 0.5 else "DOWN"
                i = bisect.bisect_left(at, r + 30)
                j = bisect.bisect_right(bt, at[i]) - 1 if i < len(at) else -1
                if i >= len(at) or j < 0 or at[i] > r + 60:
                    continue
                px_in = av[i] if side == "UP" else 1 - bv[j]
                if px_in > MAX_PX or px_in <= 0.02:
                    continue
                path = []
                for k in range(bisect.bisect_right(bt, at[i]), bisect.bisect_left(bt, r + 300)):
                    m = bisect.bisect_right(at, bt[k]) - 1
                    path.append(bv[k] if side == "UP" else 1 - av[m])
                out.append((r, trade(px_in, path, side == rs[r], tp)))
            res[(tp, ctrl)] = out
    return res


def show(label, out):
    v = np.array([x[1] for x in out])
    h = len(v) // 2
    print(f"{label:38s} {len(v):5d} bets  total {v.sum():+8.2f}$  per $1 {v.mean():+.4f}  won {100 * np.mean(v > 0):4.1f}%  "
          f"halves {v[:h].mean():+.4f} / {v[h:].mean():+.4f}")


if __name__ == "__main__":
    print("A) Polymarket minute prices, ~41 days")
    for (sig, tp, ctrl), out in run_history().items():
        show(f"{sig} {'TP+' + str(int(tp * 100)) + '%' if tp else 'hold'} {'COIN-FLIP' if ctrl else ''}", out)
    print("B) recorder real bid/ask (TREND1)")
    for (tp, ctrl), out in run_recorder().items():
        show(f"TREND1 {'TP+40%' if tp else 'hold'} {'COIN-FLIP' if ctrl else ''}", out)
