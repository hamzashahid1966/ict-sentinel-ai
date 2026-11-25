"""
4-hour range + 5-minute re-entry (Data Trader video), with the session filters traders suggest.

PRE-REGISTERED 2026-11-25, before any run. Source: the user's file
4_hour_range_5_minute_re_entry_strategy_checklist.md, plus a viewer comment the user forwarded:
"never enter during or 1 hour into the 9:30 open ... safer overnight or after hours".

  Data       Binance USDT-M 5-minute perp candles since 2019, 12 coins. Every calendar day (crypto trades
             weekends); no news filter (no calendar in the repo).
  Range      the first 4-hour candle of the New York day: 00:00-04:00 New York time (DST handled).
             Its high and low are known once the 03:55 candle closes. Days missing range candles are skipped.
  Trigger    after 04:00, a 5-minute candle CLOSES above the range high, and a later candle the same day
             closes back inside the range (below the high, above the low): SHORT. Mirror for the low: LONG.
             A close outside on the other side restarts the watch on that side.
  Entry      next candle's open. Stop: the extreme since the first close outside (highest high for a
             short), as the video's standard stop. Target 2R. If neither is hit, exit at the day's last
             candle (23:55 New York). Skip trades with a stop narrower than 0.25% of price (fees and
             slippage alone would be ~0.7R). The video's discretionary "wide breakout" stop is not tested.
             One trade at a time per coin; after it closes, a fresh close outside is needed.
  Variants   by the time of the trigger candle (New York time):
               all-day    04:00-24:00 (the video's rule)
               skip-open  as all-day, but no entries 09:30-10:30 (the comment's advice)
               after-10   10:00-24:00 only
               off-hours  outside the 09:30-16:00 cash session only ("overnight or after hours")
             A trigger outside the window is not taken and the watch restarts.
  Costs      0.05% taker fee per fill; 0.02% slippage on entry, stop and day-end exits. Stop is checked
             before target inside a candle.
  Controls   20 runs, same entries and stop distance, coin-flip direction, identical exits.
  PASS       per variant, all of: (1) mean net R 95% CI (bootstrap by month) above 0; (2) mean net R above
             the 95th percentile of the coin-flip controls; (3) last third of the period mean net R > 0;
             (4) at least 55% of months positive. Four variants, so one pass by luck is possible.
Research only: reads cached history, places no orders.

Usage:
  python3 -m research.range_reentry
  python3 -m research.range_reentry --coins BTC,ETH
"""

import argparse
import os
import time

import numpy as np
import pandas as pd

from research.gianluca_vp import SLIP, equity, month_ci, simulate
from research.lab import ALL_COINS, _perp_klines

MIN_WIDTH, RR, N_CONTROLS = 0.0025, 2.0, 20
WINDOWS = {
    "all-day": lambda m: m >= 240,
    "skip-open": lambda m: m >= 240 and not (570 <= m < 630),
    "after-10": lambda m: m >= 600,
    "off-hours": lambda m: m >= 240 and not (570 <= m < 960),
}
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(coin):
    a = _perp_klines(coin, "5m")[:, :5]
    a = a[a[:, 0] + 300 <= time.time()]
    live = np.nonzero(a[:, 2] > a[:, 3])[0]
    return a[live[0]:] if len(live) else a[:0]


def ny_clock(t):
    ts = pd.to_datetime(t, unit="s", utc=True).tz_convert("America/New_York")
    return (ts.hour * 60 + ts.minute).values, ts.normalize().asi8 // 86_400_000_000_000


def run_coin(coin, A, window):
    t, o, h, l, c = (A[:, k] for k in range(5))
    mins, day = ny_clock(t)
    ok = WINDOWS[window]
    trades = []
    n, i = len(t), 0
    while i < n:
        d0 = day[i]
        j = i
        while j < n and day[j] == d0:
            j += 1
        a, b = i, j                                        # bars of this New York day: [a, b)
        i = j
        rng = [k for k in range(a, b) if mins[k] < 240]
        if len(rng) < 48:
            continue
        hi_r, lo_r = h[rng].max(), l[rng].min()
        side, ext, k = 0, None, rng[-1] + 1
        while k < b - 1:
            if c[k] > hi_r:
                if side != 1:
                    side, ext = 1, h[k]
                ext = max(ext, h[k])
            elif c[k] < lo_r:
                if side != -1:
                    side, ext = -1, l[k]
                ext = min(ext, l[k])
            elif side:                                     # closed back inside the range
                ext = max(ext, h[k]) if side == 1 else min(ext, l[k])
                d = -side                                  # fade the failed breakout
                if ok(mins[k]):
                    S = (o, h, l, c) if d == 1 else (-o, -l, -h, -c)
                    op_, hi_, lo_, cl_ = S
                    E = op_[k + 1] + SLIP * abs(op_[k + 1])
                    stop = d * ext
                    risk = E - stop
                    if risk > 0 and risk >= MIN_WIDTH * abs(E):
                        net, gross, ex, why = simulate(lo_, hi_, cl_, op_[k + 1], k + 1, b - 1, E, stop, E + RR * risk)
                        trades.append({"coin": coin, "dir": d, "entry_i": k + 1, "end_i": b - 1,
                                       "entry_t": int(t[k + 1]), "exit_t": int(t[ex]), "E": E, "risk": risk,
                                       "net": net, "gross": gross, "why": why, "min": int(mins[k])})
                        side, ext, k = 0, None, ex + 1
                        continue
                side, ext = 0, None
            k += 1
    return trades


def signed_cache(data, coin, d, cache):
    """(o, h, l, c) seen from side d, built once per coin and side."""
    if (coin, d) not in cache:
        A = data[coin]
        o, h, l, c = A[:, 1], A[:, 2], A[:, 3], A[:, 4]
        cache[(coin, d)] = (o, h, l, c) if d == 1 else (-o, -l, -h, -c)
    return cache[(coin, d)]


def controls(data, trades, n_runs=N_CONTROLS):
    out, cache = [], {}
    for s in range(n_runs):
        rng = np.random.default_rng(3000 + s)
        rs = []
        for tr in trades:
            d = 1 if rng.random() < 0.5 else -1
            op_, hi_, lo_, cl_ = signed_cache(data, tr["coin"], d, cache)
            i = tr["entry_i"]
            E = op_[i] + SLIP * abs(op_[i])
            net, *_ = simulate(lo_, hi_, cl_, op_[i], i, tr["end_i"], E, E - tr["risk"], E + RR * tr["risk"])
            rs.append(net)
        out.append(float(np.mean(rs)) if rs else 0.0)
    return out


def evaluate(name, trades, ctrl, span):
    r = np.array([x["net"] for x in trades])
    lo, hi = month_ci(trades)
    months = {}
    for tr in trades:
        months.setdefault(time.strftime("%Y-%m", time.gmtime(tr["exit_t"])), []).append(tr["net"])
    pos_m = float(np.mean([sum(v) > 0 for v in months.values()]))
    cut = span[0] + (span[1] - span[0]) * 2 / 3
    oos = [x["net"] for x in trades if x["entry_t"] >= cut]
    oos_mean = float(np.mean(oos)) if oos else 0.0
    c95 = float(np.percentile(ctrl, 95))
    eq, dd, sh = equity(trades)
    checks = [lo > 0, r.mean() > c95, oos_mean > 0, pos_m >= 0.55]
    return {"name": name, "n": len(trades), "win": float((r > 0).mean()), "gross": float(np.mean([x["gross"] for x in trades])),
            "mean": float(r.mean()), "ci": (lo, hi), "c95": c95, "cmean": float(np.mean(ctrl)), "oos": oos_mean,
            "oos_n": len(oos), "pos_m": pos_m, "n_m": len(months), "eq": eq, "dd": dd, "sharpe": sh, "checks": checks,
            "passed": all(checks), "trades": trades}


def fmt(results, coins, span):
    out = ["# 4-hour range + 5-minute re-entry: backtest", "",
           f"Generated {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}. 5-minute candles, "
           f"{time.strftime('%Y-%m', time.gmtime(span[0]))} to {time.strftime('%Y-%m', time.gmtime(span[1]))}. "
           f"Coins: {', '.join(coins)}.",
           "Rules pre-registered in `research/range_reentry.py` (2026-11-25) before any run. R = amount risked per trade. "
           "Net = after 0.05% fee per fill and 0.02% slippage. Equity = 1% risk per trade, compounding.", "",
           "| variant | trades | win % | avg R gross | avg R net | 95% CI | coin-flip 95th | last third avg R | months + | 1% risk equity | max drop | Sharpe | PASS |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in results:
        out.append(f"| {r['name']} | {r['n']} | {100 * r['win']:.1f}% | {r['gross']:+.3f} | {r['mean']:+.3f} | "
                   f"{r['ci'][0]:+.3f} to {r['ci'][1]:+.3f} | {r['c95']:+.3f} | {r['oos']:+.3f} ({r['oos_n']}) | "
                   f"{100 * r['pos_m']:.0f}% of {r['n_m']} | {100 * (r['eq'] - 1):+.1f}% | {100 * r['dd']:.1f}% | "
                   f"{r['sharpe']:.2f} | {'**yes**' if r['passed'] else 'no'} |")
    base = results[0]["trades"]
    out += ["", "## All-day trades by New York hour of the trigger", "", "| NY hour | trades | win % | avg net R |", "|---|---|---|---|"]
    for hr in range(4, 24):
        g = [x["net"] for x in base if x["min"] // 60 == hr]
        if g:
            out.append(f"| {hr:02d}:00 | {len(g)} | {100 * np.mean(np.array(g) > 0):.0f}% | {np.mean(g):+.3f} |")
    out += ["", "## All-day: years and coins", "", "| year | trades | avg net R |", "|---|---|---|"]
    yrs = {}
    for x in base:
        yrs.setdefault(time.strftime("%Y", time.gmtime(x["entry_t"])), []).append(x["net"])
    out += [f"| {y} | {len(v)} | {np.mean(v):+.3f} |" for y, v in sorted(yrs.items())]
    out += ["", "| coin | trades | avg net R |", "|---|---|---|"]
    for cn in coins:
        g = [x["net"] for x in base if x["coin"] == cn]
        if g:
            out.append(f"| {cn} | {len(g)} | {np.mean(g):+.3f} |")
    ex = {k: sum(1 for x in base if x["why"] == k) for k in ("target", "stop", "close")}
    out += ["", f"All-day exits: {ex['target']} target, {ex['stop']} stop, {ex['close']} at the day's end. "
            f"Coin-flip direction average: {results[0]['cmean']:+.3f} R."]
    return "\n".join(out) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--coins", default=",".join(ALL_COINS))
    ap.add_argument("--out", default=os.path.join(ROOT, "docs", "RANGE_REENTRY_BACKTEST.md"))
    a = ap.parse_args(argv)
    data = {}
    for cn in (x.strip().upper() for x in a.coins.split(",")):
        A = load(cn)
        if len(A) >= 5000:
            data[cn] = A
    span = (min(A[0, 0] for A in data.values()), max(A[-1, 0] for A in data.values()))
    results = []
    for w in WINDOWS:
        trades = [x for cn, A in data.items() for x in run_coin(cn, A, w)]
        r = evaluate(w, trades, controls(data, trades), span)
        results.append(r)
        print(f"{w}: {r['n']} trades, avg net R {r['mean']:+.3f}, pass={r['passed']}", flush=True)
    with open(a.out, "w") as f:
        f.write(fmt(results, list(data), span))
    print("wrote", a.out)


if __name__ == "__main__":
    main()
