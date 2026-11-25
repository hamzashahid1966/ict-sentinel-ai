"""
The Trading Channel two-time-frame major-swing pullback, tested as its checklist says.

PRE-REGISTERED 2026-11-25, before any run. Source: the user's file
the_trading_channel_two_time_frame_pullback_strategy_checklist.md. Long shown; short is the mirror.

  Data       Binance USDT-M perp candles since 2019, 12 coins. The higher time frame (HTF) is built from
             the execution time frame (LTF) and used only after each HTF candle closed.
  Pairs      15m->5m, 1h->15m, 4h->1h, 1D->4h (HTF -> entry), as listed in the video.
  Major swings  minor wiggles are ignored by using 7-candle swings on the HTF (a high above the 3 candles
             on each side), confirmed 3 candles later. Break of structure (BOS) = an HTF candle CLOSES
             above the latest unbroken major swing high. The broken high becomes the zone level; the
             lowest low between that swing high and the BOS candle is the pullback low (invalidation).
  Trend      clear only after 2 BOS in a row in the same direction (higher highs + higher lows). An HTF
             close below the invalidation low ends the trend (chop) until 2 new BOS line up.
  Zone       broken level +/- 0.5 x HTF ATR(14) (a zone, not a thin line). Re-drawn at every new BOS.
  Target     the impulse top (highest high since the BOS), extended while price keeps rising before the
             pullback; if price returns to it before an entry, the setup is gone (let it go).
  LTF        price pulls back into the zone; then two 3-candle swing lows form INSIDE the zone (double
             bottom); after the second one is confirmed, the first green candle is the rejection
             candle. An LTF close below the zone kills the setup until the next BOS.
  Entry      next LTF open. Stop: below the lower of the two bottoms by 0.5 x LTF ATR(14). Target: the
             impulse top; skip unless it is at least 2R away and the stop is at least 0.25% of price.
             No time limit, one trade per coin at a time.
  Costs      0.05% taker fee per fill, 0.02% slippage on entry and stop. Stop checked before target.
  Controls   20 runs, same entries, stop and target distances, coin-flip direction.
  PASS       per pair, all of: (1) mean net R 95% CI (bootstrap by month) above 0; (2) above the 95th
             percentile of the coin-flip controls; (3) last third of the period mean net R > 0;
             (4) at least 55% of months positive. Four pairs, so one pass by luck is possible.
Research only: reads cached history, places no orders.

Usage:
  python3 -m research.tc_pullback
  python3 -m research.tc_pullback --pairs 4h-1h --coins BTC
"""

import argparse
import os
import time

import numpy as np

from research.gianluca_vp import atr14, equity, month_ci
from research.ict_mayne import SLIP, build_htf, simulate
from research.lab import ALL_COINS, _perp_klines

K, ZONE_ATR, STOP_ATR, MIN_RR, MIN_WIDTH, N_CONTROLS = 3, 0.5, 0.5, 2.0, 0.0025, 20
PAIRS = {"15m-5m": ("5m", 900), "1h-15m": ("15m", 3600), "4h-1h": ("1h", 14400), "1D-4h": ("4h", 86400)}
STEP = {"5m": 300, "15m": 900, "1h": 3600, "4h": 14400}
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_ltf(coin, ltf):
    src = "1h" if ltf == "4h" else ltf
    a = _perp_klines(coin, src)[:, :5]
    a = a[a[:, 0] + STEP[src] <= time.time()]
    live = np.nonzero(a[:, 2] > a[:, 3])[0]
    a = a[live[0]:] if len(live) else a[:0]
    if ltf == "4h" and len(a):
        gid, o, h, l, c = build_htf(a, 14400)
        starts = np.r_[0, np.nonzero(np.diff(gid))[0] + 1]
        a = np.column_stack([a[starts, 0], o, h, l, c])[:-1]          # drop a possibly unfinished 4h candle
    return a


def run_coin(coin, L, gid, H, funnel):
    t, o, h, l, c = (L[:, k] for k in range(5))
    Ho, Hh, Hl, Hc = H
    hatr, latr = atr14(Hh, Hl, Hc), atr14(h, l, c)
    S = {1: (o, h, l, c), -1: (-o, -l, -h, -c)}
    HS = {1: (Hh, Hl), -1: (-Hl, -Hh)}
    fh = fl = None
    fh_used = fl_used = -1
    trend, count, inval, bos_k = 0, 0, None, None
    setup, busy, n, trades = None, -1, len(t), []
    for i in range(n):
        if i > 0 and gid[i] != gid[i - 1]:
            k = gid[i - 1]
            if k >= 2 * K:
                ce = k - K
                win_h, win_l = np.r_[Hh[ce - K:ce], Hh[ce + 1:k + 1]], np.r_[Hl[ce - K:ce], Hl[ce + 1:k + 1]]
                if Hh[ce] > win_h.max():
                    fh = (ce, Hh[ce])
                if Hl[ce] < win_l.min():
                    fl = (ce, Hl[ce])
            bos = 0
            if fh and fh[0] != fh_used and Hc[k] > fh[1]:
                fh_used, bos = fh[0], 1
                count = count + 1 if trend == 1 else 1
                trend, level, inval, bos_k = 1, fh[1], Hl[fh[0]:k + 1].min(), k
            elif fl and fl[0] != fl_used and Hc[k] < fl[1]:
                fl_used, bos = fl[0], -1
                count = count + 1 if trend == -1 else 1
                trend, level, inval, bos_k = -1, fl[1], Hh[fl[0]:k + 1].max(), k
            elif (trend == 1 and Hc[k] < inval) or (trend == -1 and Hc[k] > inval):
                trend, count, setup = 0, 0, None
            if bos:
                setup = None
                if count >= 2 and i > busy:
                    d = bos
                    hh, _ = HS[d]
                    lv = d * level
                    setup = {"d": d, "zbot": lv - ZONE_ATR * hatr[k], "ztop": lv + ZONE_ATR * hatr[k],
                             "term": hh[bos_k:k + 1].max(), "tapped": False, "tap_i": -1, "lows": []}
                    funnel["bos2"] += 1
        if i <= busy or setup is None:
            continue
        d = setup["d"]
        op_, hi_, lo_, cl_ = S[d]
        if i >= 2 and setup["tapped"] and lo_[i - 1] < lo_[i - 2] and lo_[i - 1] < lo_[i] \
                and i - 1 >= setup["tap_i"] and setup["zbot"] <= lo_[i - 1] <= setup["ztop"]:
            setup["lows"].append((i - 1, lo_[i - 1]))                    # bar i confirms a swing low at i-1
        if not setup["tapped"]:
            if lo_[i] <= setup["ztop"]:
                setup["tapped"], setup["tap_i"] = True, i
                funnel["tapped"] += 1
            else:
                setup["term"] = max(setup["term"], hi_[i])
                continue
        if cl_[i] < setup["zbot"] or hi_[i] >= setup["term"]:
            setup = None
            continue
        lows = setup["lows"]
        if len(lows) >= 2 and i > lows[-1][0] and cl_[i] > op_[i]:
            funnel["double"] += 1
            if i + 1 >= n:
                break
            E = op_[i + 1] + SLIP * abs(op_[i + 1])
            stop = min(lows[-1][1], lows[-2][1]) - STOP_ATR * latr[i]
            risk, T = E - stop, setup["term"]
            if risk > 0 and risk >= MIN_WIDTH * abs(E) and T - E >= MIN_RR * risk:
                net, gross, ex, why = simulate(lo_, hi_, cl_, i + 1, E, stop, T, T, False, op_[i + 1])
                trades.append({"coin": coin, "dir": d, "entry_i": i + 1, "entry_t": int(t[i + 1]),
                               "exit_t": int(t[min(ex, n - 1)]), "E": E, "risk": risk, "rr": (T - E) / risk,
                               "net": net, "gross": gross, "why": why})
                busy = ex
            else:
                funnel["rr_fail"] += 1
            setup = None
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
        rng = np.random.default_rng(4000 + s)
        rs = []
        for tr in trades:
            d = 1 if rng.random() < 0.5 else -1
            op_, hi_, lo_, cl_ = signed_cache(data, tr["coin"], d, cache)
            i = tr["entry_i"]
            E = op_[i] + SLIP * abs(op_[i])
            T = E + tr["rr"] * tr["risk"]
            net, *_ = simulate(lo_, hi_, cl_, i, E, E - tr["risk"], T, T, False, op_[i])
            rs.append(net)
        out.append(float(np.mean(rs)) if rs else 0.0)
    return out


def evaluate(name, trades, ctrl, span, funnel):
    res = {"name": name, "n": len(trades), "funnel": dict(funnel), "passed": False}
    if not trades:
        return res
    r = np.array([x["net"] for x in trades])
    lo, hi = month_ci(trades)
    months = {}
    for tr in trades:
        months.setdefault(time.strftime("%Y-%m", time.gmtime(tr["exit_t"])), []).append(tr["net"])
    pos_m = float(np.mean([sum(v) > 0 for v in months.values()]))
    cut = span[0] + (span[1] - span[0]) * 2 / 3
    oos = [x["net"] for x in trades if x["entry_t"] >= cut]
    c95 = float(np.percentile(ctrl, 95))
    eq, dd, sh = equity(trades)
    checks = [lo > 0, r.mean() > c95, (np.mean(oos) if oos else 0) > 0, pos_m >= 0.55]
    yrs = {}
    for x in trades:
        yrs.setdefault(time.strftime("%Y", time.gmtime(x["entry_t"])), []).append(x["net"])
    res.update(win=float((r > 0).mean()), gross=float(np.mean([x["gross"] for x in trades])), mean=float(r.mean()),
               ci=(lo, hi), c95=c95, cmean=float(np.mean(ctrl)), oos=float(np.mean(oos)) if oos else 0.0,
               oos_n=len(oos), pos_m=pos_m, n_m=len(months), eq=eq, dd=dd, sharpe=sh, checks=checks,
               passed=all(checks), years={y: (len(v), float(np.mean(v))) for y, v in sorted(yrs.items())},
               med_rr=float(np.median([x["rr"] for x in trades])),
               hold_h=float(np.median([(x["exit_t"] - x["entry_t"]) / 3600 for x in trades])))
    return res


def fmt(results, coins):
    out = ["# The Trading Channel two-time-frame pullback: backtest", "",
           f"Generated {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}. Coins: {', '.join(coins)}.",
           "Rules pre-registered in `research/tc_pullback.py` (2026-11-25) before any run. R = amount risked per trade. "
           "Net = after 0.05% fee per fill and 0.02% slippage. Equity = 1% risk per trade, compounding. Funding not charged.", "",
           "| HTF -> entry | data | trades | win % | target (median R) | avg R gross | avg R net | 95% CI | coin-flip 95th | last third avg R | months + | 1% risk equity | max drop | Sharpe | PASS |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in results:
        if not r["n"]:
            out.append(f"| {r['name']} | {r['span']} | 0 | | | | | | | | | | | | no |")
            continue
        out.append(f"| {r['name']} | {r['span']} | {r['n']} | {100 * r['win']:.0f}% | {r['med_rr']:.1f} | {r['gross']:+.3f} | "
                   f"{r['mean']:+.3f} | {r['ci'][0]:+.3f} to {r['ci'][1]:+.3f} | {r['c95']:+.3f} | {r['oos']:+.3f} ({r['oos_n']}) | "
                   f"{100 * r['pos_m']:.0f}% of {r['n_m']} | {100 * (r['eq'] - 1):+.1f}% | {100 * r['dd']:.1f}% | {r['sharpe']:.2f} | "
                   f"{'**yes**' if r['passed'] else 'no'} |")
    out += ["", "## How many setups survive each step", "",
            "| HTF -> entry | trend (2 BOS) + zone | pulled back into zone | double bottom/top + rejection candle | failed 2R / stop-width | trades |",
            "|---|---|---|---|---|---|"]
    for r in results:
        f = r["funnel"]
        out.append(f"| {r['name']} | {f['bos2']} | {f['tapped']} | {f['double']} | {f['rr_fail']} | {r['n']} |")
    for r in results:
        if r["n"]:
            out += ["", f"## {r['name']}", "", f"Median time in a trade: {r['hold_h']:.0f} hours. "
                    f"Coin-flip direction average: {r['cmean']:+.3f} R.", "", "| year | trades | avg net R |", "|---|---|---|"]
            out += [f"| {y} | {n} | {m:+.3f} |" for y, (n, m) in r["years"].items()]
    return "\n".join(out) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", default=",".join(PAIRS))
    ap.add_argument("--coins", default=",".join(ALL_COINS))
    ap.add_argument("--out", default=os.path.join(ROOT, "docs", "TC_PULLBACK_BACKTEST.md"))
    a = ap.parse_args(argv)
    coins = [x.strip().upper() for x in a.coins.split(",")]
    results = []
    for pair in a.pairs.split(","):
        ltf, period = PAIRS[pair]
        data, trades = {}, []
        funnel = dict.fromkeys(("bos2", "tapped", "double", "rr_fail"), 0)
        for cn in coins:
            L = load_ltf(cn, ltf)
            if len(L) < 500:
                continue
            data[cn] = L
            gid, *H = build_htf(L, period)
            trades += run_coin(cn, L, gid, H, funnel)
        span = (min(L[0, 0] for L in data.values()), max(L[-1, 0] for L in data.values()))
        r = evaluate(pair, trades, controls(data, trades), span, funnel)
        r["span"] = f"{time.strftime('%Y-%m', time.gmtime(span[0]))} to {time.strftime('%Y-%m', time.gmtime(span[1]))}"
        results.append(r)
        print(f"{pair}: {r['n']} trades, avg net R {r.get('mean', 0):+.3f}, pass={r['passed']}", flush=True)
    with open(a.out, "w") as f:
        f.write(fmt(results, coins))
    print("wrote", a.out)


if __name__ == "__main__":
    main()
