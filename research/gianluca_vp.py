"""
Gian Luca's statistical volume-profile strategy (IQCapital video), tested as its checklist says.

PRE-REGISTERED 2026-11-25, before any run. Source: the user's file
gian_luca_statistical_volume_profile_strategy_checklist.md. Long shown; short is the mirror.

  Data       Binance USDT-M 15-minute perp candles since 2019, 12 coins (the video calibrates on 15m NQ).
  Session    New York cash session 09:30-16:00 New York time (DST handled), every calendar day
             (crypto trades weekends). News filter: first-Friday-of-the-month (NFP) sessions are skipped;
             CPI dates are not filtered (no calendar in the repo).
  Profile    Per session, a volume profile of 50 price bins between the session low and high; each
             candle's volume is spread evenly over its high-low range. POC = the fullest bin; the value
             area grows from the POC towards the fuller neighbour until it holds 70% of the volume.
  Trend      value-area progression: the last session's VAH and VAL both above the session before
             (both below = downtrend; otherwise no trade).
  Pullback   during today's session price trades into the prior session's value area (low <= prior
             VAH). The setup dies for the day if a candle closes below the prior VAL.
  Trigger    after the pullback touch, a bullish VALID candle (body > its longest wick) closes above the
             previous candle's high by at least 0.25 x ATR(14) (the video's "6 points" re-scaled to
             each coin's volatility), the previous candle is also valid, and the trigger candle's volume
             is below the average volume of the 20 candles before it ("low effort, high result").
  Entry      next candle's open. Stop: the lowest low since the pullback touch. Target: 2R. Exit at the
             session close if neither is hit. Skip if the stop is narrower than 0.25% of price. One
             trade per coin per session.
  Costs      0.05% taker fee per fill; 0.02% slippage on the entry, stop and session-close exits. Stop is
             checked before target inside a candle.
  Meta-label 5 points, scored with information available at entry:
               1 ATR(14) percentile over the last 200 candles in 51-75 ("High")
               2 the model's last two closed trades were loss then win
               3 regime fresh: the ATR percentile bucket changed within the last 60 candles (0-30 of 200)
               4 low effort, high result (always 1: the trigger requires it)
               5 New York session (always 1: only NY is traded)
  Kelly      from the model's own closed trades before each entry (needs 50): f = W - (1-W)/b, b = avg
             win / avg loss in R. Risk = f x 0.5 (score 5), 0.25 (4), 1/6 (3), 1/10 (2 or less), capped at
             2% of equity; before 50 trades, and whenever f <= 0, risk 0.5%.
  Measure    R per trade gross and net; flat 1% risk equity and Kelly-sized equity; daily Sharpe.
  Controls   20 runs, same entries and stop distance, coin-flip direction, identical exits.
  PASS       all of: (1) mean net R 95% CI (bootstrap by month) above 0; (2) mean net R above the 95th
             percentile of the coin-flip controls; (3) out-of-sample (last third of the period) mean net
             R > 0; (4) at least 55% of months positive. Separately: the meta-label is useful only if
             trades scoring 4-5 have a higher mean net R than trades scoring 2-3 in BOTH halves.
Research only: reads cached history, places no orders.

Usage:
  python3 -m research.gianluca_vp
  python3 -m research.gianluca_vp --coins BTC,ETH
"""

import argparse
import os
import time

import numpy as np
import pandas as pd

from research.lab import ALL_COINS, _perp_klines

FEE, SLIP = 0.0005, 0.0002
MIN_WIDTH, RR, BREAK_ATR = 0.0025, 2.0, 0.25
BINS, VA_SHARE = 50, 0.70
N_CONTROLS = 20
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(coin):
    a = _perp_klines(coin, "15m")[:, :6]
    a = a[a[:, 0] + 900 <= time.time()]
    live = np.nonzero(a[:, 2] > a[:, 3])[0]
    return a[live[0]:] if len(live) else a[:0]


def value_area(h, l, v, bins=BINS, share=VA_SHARE):
    """(VAH, POC, VAL) of one session; volume of each candle spread evenly over its range."""
    lo, hi = l.min(), h.max()
    if hi <= lo:
        return hi, hi, lo
    edges = np.linspace(lo, hi, bins + 1)
    prof = np.zeros(bins)
    for hh, ll, vv in zip(h, l, v):
        a = min(int((ll - lo) / (hi - lo) * bins), bins - 1)
        b = min(int((hh - lo) / (hi - lo) * bins), bins - 1)
        prof[a:b + 1] += vv / (b - a + 1)
    poc = int(np.argmax(prof))
    a = b = poc
    total, got = prof.sum(), prof[poc]
    while got < share * total and (a > 0 or b < bins - 1):
        up = prof[b + 1] if b < bins - 1 else -1
        dn = prof[a - 1] if a > 0 else -1
        if up >= dn:
            b += 1
            got += up
        else:
            a -= 1
            got += dn
    return edges[b + 1], (edges[poc] + edges[poc + 1]) / 2, edges[a]


def is_valid(o, h, l, c):
    body = abs(c - o)
    return body > max(h - max(o, c), min(o, c) - l)


def atr14(h, l, c):
    pc = np.r_[c[0], c[:-1]]
    tr = np.maximum(h - l, np.maximum(abs(h - pc), abs(l - pc)))
    return pd.Series(tr).ewm(alpha=1 / 14, adjust=False).mean().values


def sessions(t):
    """List of (start, end_exclusive, local_date) for New York 09:30-16:00 sessions."""
    ts = pd.to_datetime(t, unit="s", utc=True).tz_convert("America/New_York")
    mins = ts.hour * 60 + ts.minute
    inside = (mins >= 570) & (mins < 960)
    days = np.where(inside, ts.normalize().asi8 // 86_400_000_000_000, -1)
    out, i, n = [], 0, len(t)
    while i < n:
        if days[i] < 0:
            i += 1
            continue
        j = i
        while j < n and days[j] == days[i]:
            j += 1
        out.append((i, j, ts[i].date()))
        i = j
    return out


def simulate(lo, hi, cl, op, start, end, E, stop, target):
    """Signed-space trade from bar `start` to bar `end` (inclusive, session close). (net_r, gross_r, exit_i, why)."""
    risk = E - stop
    raw_E = E - SLIP * abs(op)
    s_hit = lo[start:end + 1] <= stop
    t_hit = hi[start:end + 1] > target
    js = int(np.argmax(s_hit)) if s_hit.any() else 1 << 30
    jt = int(np.argmax(t_hit)) if t_hit.any() else 1 << 30
    if js <= jt and js < (1 << 30):                              # stop is checked first inside a candle
        j, px, why, rawpx = start + js, stop - SLIP * abs(stop), "stop", stop
    elif jt < (1 << 30):
        j, px, why, rawpx = start + jt, target, "target", target
    else:
        j, px, why, rawpx = end, cl[end] - SLIP * abs(cl[end]), "close", cl[end]
    fees = FEE * (abs(E) + abs(px))
    return (px - E - fees) / risk, (rawpx - raw_E) / risk, j, why


def run_coin(coin, A):
    t, o, h, l, c, v = (A[:, k] for k in range(6))
    atr = atr14(h, l, c)
    pct = pd.Series(atr).rolling(200).rank(pct=True).values * 100
    bucket = np.where(np.isnan(pct), -1, np.minimum((pct - 1e-9) // 25, 3))
    changed = np.r_[True, bucket[1:] != bucket[:-1]]
    last_change = np.maximum.accumulate(np.where(changed, np.arange(len(t)), 0))
    vma = pd.Series(v).rolling(20).mean().shift(1).values
    sess = sessions(t)
    vas = [value_area(h[a:b], l[a:b], v[a:b]) for a, b, _ in sess]
    S = {d: ((o, h, l, c) if d == 1 else (-o, -l, -h, -c)) for d in (1, -1)}
    trades = []
    for s in range(2, len(sess)):
        a, b, day = sess[s]
        if b - a < 4 or (day.weekday() == 4 and day.day <= 7):
            continue
        (vah1, _, val1), (vah2, _, val2) = vas[s - 1], vas[s - 2]
        d = 1 if (vah1 > vah2 and val1 > val2) else (-1 if (vah1 < vah2 and val1 < val2) else 0)
        if not d:
            continue
        op_, hi_, lo_, cl_ = S[d]
        top, bottom = (vah1, val1) if d == 1 else (-val1, -vah1)       # prior value area, signed
        touch, pull = -1, None
        for j in range(a + 1, b - 1):
            if touch < 0:
                if lo_[j] <= top:
                    touch, pull = j, lo_[j]
                else:
                    continue
            pull = min(pull, lo_[j])
            if cl_[j] < bottom:
                break
            if not (cl_[j] > op_[j] and is_valid(o[j], h[j], l[j], c[j]) and is_valid(o[j - 1], h[j - 1], l[j - 1], c[j - 1])):
                continue
            if cl_[j] <= hi_[j - 1] + BREAK_ATR * atr[j - 1] or not (v[j] < vma[j]):
                continue
            E = op_[j + 1] + SLIP * abs(op_[j + 1])
            risk = E - pull
            if risk <= 0 or risk < MIN_WIDTH * abs(E):
                break
            net, gross, ex, why = simulate(lo_, hi_, cl_, op_[j + 1], j + 1, b - 1, E, pull, E + RR * risk)
            p = pct[j]
            trades.append({"coin": coin, "dir": d, "entry_i": j + 1, "end_i": b - 1, "entry_t": int(t[j + 1]),
                           "exit_t": int(t[ex]), "E": E, "op": op_[j + 1], "risk": risk, "net": net, "gross": gross,
                           "why": why, "vol_high": bool(51 <= p <= 75) if not np.isnan(p) else False,
                           "fresh": bool(j - last_change[j] <= 60)})
            break
    return trades


def add_meta_and_kelly(trades):
    """Score 2 (autocorrelation) and Kelly sizing use only trades closed before each entry."""
    by_exit = sorted(trades, key=lambda x: x["exit_t"])
    exits = np.array([x["exit_t"] for x in by_exit])
    for tr in trades:
        k = int(np.searchsorted(exits, tr["entry_t"], side="right"))
        past = by_exit[:k]
        seq = past[-2:]
        auto = len(seq) == 2 and seq[0]["net"] <= 0 < seq[1]["net"]
        tr["score"] = int(tr["vol_high"]) + int(auto) + int(tr["fresh"]) + 2
        risk = 0.005
        if len(past) >= 50:
            r = np.array([x["net"] for x in past])
            W = (r > 0).mean()
            wins, losses = r[r > 0], -r[r <= 0]
            if len(wins) and len(losses) and losses.mean() > 0:
                f = W - (1 - W) / (wins.mean() / losses.mean())
                if f > 0:
                    tier = {5: 0.5, 4: 0.25, 3: 1 / 6}.get(tr["score"], 0.1)
                    risk = min(0.02, f * tier)
        tr["kelly_risk"] = risk


def equity(trades, risk_key=None):
    eq, peak, dd = 1.0, 1.0, 0.0
    daily = {}
    for tr in sorted(trades, key=lambda x: x["exit_t"]):
        rk = tr[risk_key] if risk_key else 0.01
        before = eq
        eq *= 1 + rk * tr["net"]
        peak = max(peak, eq)
        dd = min(dd, eq / peak - 1)
        day = tr["exit_t"] // 86400
        daily[day] = daily.get(day, 0.0) + np.log(eq / before)
    if not daily:
        return eq, dd, 0.0
    days = np.arange(min(daily), max(daily) + 1)
    r = np.array([daily.get(x, 0.0) for x in days])
    sharpe = r.mean() / r.std() * np.sqrt(365) if r.std() > 0 else 0.0
    return eq, dd, sharpe


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
        rng = np.random.default_rng(2000 + s)
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


def month_ci(trades, n_boot=2000, seed=0):
    by = {}
    for tr in trades:
        by.setdefault(time.strftime("%Y-%m", time.gmtime(tr["entry_t"])), []).append(tr["net"])
    groups = list(by.values())
    rng = np.random.default_rng(seed)
    means = [np.mean([x for j in rng.integers(0, len(groups), len(groups)) for x in groups[j]]) for _ in range(n_boot)]
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def report(trades, ctrl, coins, span):
    r = np.array([x["net"] for x in trades])
    lo, hi = month_ci(trades)
    months = {}
    for tr in trades:
        months.setdefault(time.strftime("%Y-%m", time.gmtime(tr["exit_t"])), []).append(tr["net"])
    pos_m = np.mean([sum(v) > 0 for v in months.values()])
    cut = span[0] + (span[1] - span[0]) * 2 / 3
    ins = [x for x in trades if x["entry_t"] < cut]
    oos = [x for x in trades if x["entry_t"] >= cut]
    oos_mean = float(np.mean([x["net"] for x in oos])) if oos else 0.0
    c95 = float(np.percentile(ctrl, 95))
    checks = [lo > 0, r.mean() > c95, oos_mean > 0, pos_m >= 0.55]
    eq1, dd1, sh1 = equity(trades)
    eqk, ddk, shk = equity(trades, "kelly_risk")

    def grp(ts):
        return (len(ts), float(np.mean([x["net"] for x in ts])) if ts else float("nan"))
    meta_rows, meta_ok = [], True
    for name, part in (("in-sample (first 2/3)", ins), ("out-of-sample (last 1/3)", oos)):
        hi_s = grp([x for x in part if x["score"] >= 4])
        lo_s = grp([x for x in part if x["score"] <= 3])
        meta_ok &= bool(hi_s[0] and lo_s[0] and hi_s[1] > lo_s[1])
        meta_rows.append(f"| {name} | {lo_s[0]} | {lo_s[1]:+.3f} | {hi_s[0]} | {hi_s[1]:+.3f} |")
    yrs = {}
    for tr in trades:
        yrs.setdefault(time.strftime("%Y", time.gmtime(tr["entry_t"])), []).append(tr["net"])
    out = ["# Gian Luca statistical volume-profile strategy: backtest", "",
           f"Generated {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}. 15-minute candles, New York session, "
           f"{time.strftime('%Y-%m', time.gmtime(span[0]))} to {time.strftime('%Y-%m', time.gmtime(span[1]))}. "
           f"Coins: {', '.join(coins)}.",
           "Rules pre-registered in `research/gianluca_vp.py` (2026-11-25) before any run. R = amount risked per trade. "
           "Net = after 0.05% fee per fill and 0.02% slippage. Funding not charged (trades last hours).", "",
           "| measure | result |", "|---|---|",
           f"| trades | {len(trades)} ({sum(x['dir'] == 1 for x in trades)} long, {sum(x['dir'] == -1 for x in trades)} short) |",
           f"| win rate | {100 * (r > 0).mean():.1f}% (2R target needs about 34% to break even before costs) |",
           f"| avg R gross / net | {np.mean([x['gross'] for x in trades]):+.3f} / {r.mean():+.3f} |",
           f"| 95% CI of avg net R | {lo:+.3f} to {hi:+.3f} |",
           f"| coin-flip direction (avg, 95th pct) | {np.mean(ctrl):+.3f}, {c95:+.3f} |",
           f"| in-sample avg net R | {np.mean([x['net'] for x in ins]):+.3f} ({len(ins)} trades) |",
           f"| out-of-sample avg net R | {oos_mean:+.3f} ({len(oos)} trades) |",
           f"| months positive | {100 * pos_m:.0f}% of {len(months)} |",
           f"| exits | {sum(x['why'] == 'target' for x in trades)} target, {sum(x['why'] == 'stop' for x in trades)} stop, "
           f"{sum(x['why'] == 'close' for x in trades)} session close |",
           f"| flat 1% risk: equity, max drop, Sharpe | {100 * (eq1 - 1):+.1f}%, {100 * dd1:.1f}%, {sh1:.2f} |",
           f"| meta-label + fractional Kelly: equity, max drop, Sharpe | {100 * (eqk - 1):+.1f}%, {100 * ddk:.1f}%, {shk:.2f} |",
           f"| PASS (CI > 0, beats coin flip, out-of-sample > 0, months >= 55%) | "
           f"{'**yes**' if all(checks) else 'no'} ({', '.join('yes' if x else 'no' for x in checks)}) |",
           "", "## Does the 5-point meta-label pick better trades?", "",
           f"Useful only if score 4-5 beats score 2-3 in both halves: **{'yes' if meta_ok else 'no'}**.", "",
           "| period | trades score 2-3 | avg net R | trades score 4-5 | avg net R |", "|---|---|---|---|---|", *meta_rows,
           "", "| score | trades | avg net R |", "|---|---|---|"]
    for sc in range(2, 6):
        g = grp([x for x in trades if x["score"] == sc])
        out.append(f"| {sc} | {g[0]} | {g[1]:+.3f} |")
    for key, label in (("vol_high", "ATR percentile 51-75"), ("fresh", "fresh regime")):
        y, n = grp([x for x in trades if x[key]]), grp([x for x in trades if not x[key]])
        out.append(f"| {label}: yes / no | {y[0]} / {n[0]} | {y[1]:+.3f} / {n[1]:+.3f} |")
    out += ["", "| year | trades | avg net R | total R |", "|---|---|---|---|"]
    out += [f"| {y} | {len(v)} | {np.mean(v):+.3f} | {np.sum(v):+.1f} |" for y, v in sorted(yrs.items())]
    out += ["", "| coin | trades | avg net R |", "|---|---|---|"]
    for cn in coins:
        g = grp([x for x in trades if x["coin"] == cn])
        if g[0]:
            out.append(f"| {cn} | {g[0]} | {g[1]:+.3f} |")
    return "\n".join(out) + "\n", all(checks), meta_ok


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--coins", default=",".join(ALL_COINS))
    ap.add_argument("--out", default=os.path.join(ROOT, "docs", "GIANLUCA_VP_BACKTEST.md"))
    a = ap.parse_args(argv)
    coins = [x.strip().upper() for x in a.coins.split(",")]
    data, trades = {}, []
    for cn in coins:
        A = load(cn)
        if len(A) < 5000:
            continue
        data[cn] = A
        trades += run_coin(cn, A)
        print(cn, len(trades), flush=True)
    add_meta_and_kelly(trades)
    span = (min(A[0, 0] for A in data.values()), max(A[-1, 0] for A in data.values()))
    text, passed, meta_ok = report(trades, controls(data, trades), list(data), span)
    with open(a.out, "w") as f:
        f.write(text)
    print(f"{len(trades)} trades, avg net R {np.mean([x['net'] for x in trades]):+.3f}, pass={passed}, meta useful={meta_ok}")
    print("wrote", a.out)


if __name__ == "__main__":
    main()
