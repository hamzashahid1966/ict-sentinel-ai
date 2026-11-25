"""
Trader Mayne's ICT framework ("ICT Made Easy"), tested exactly as its pre-trade checklist says.

PRE-REGISTERED 2026-11-25, before any run. Source: the user's file
trader_mayne_ict_complete_strategy_pre_trade_checklist.md. Bullish shown; bearish is the mirror.

  Data       Binance USDT-M perp candles since 2019, 12 coins (research/lab.py cache). The higher time
             frame (HTF) is built from the lower one (LTF); an HTF candle is used only after it closed.
  Pairs      W-D (weekly -> daily), D-1h (daily -> 1-hour), 4h-15m (4-hour -> 15-minute). The 1h -> 5m
             scalping pair is not tested (no 5-minute history since 2019).
  Swings     3-candle swings: high above both neighbours (low below both), confirmed one candle later.
  HTF        1 trend: last two confirmed swing highs AND last two swing lows rising (falling for bearish);
               anything else = chop, stay out.
             2 MSB: an HTF candle CLOSES above the latest swing high while the trend is up.
             3 range: origin = lowest low between that swing high and the MSB candle; terminus = highest
               high since the origin (extended while price keeps making highs; a new MSB re-anchors).
             4 the MSB took external liquidity; the setup now waits for the pullback.
             5 POI: bullish FVG (low[i] > high[i-2]) formed inside the leg, or the order block (last
               down-close candle before the MSB). Only zones not touched by any later closed HTF candle
               and whose top is in discount (<= 50% of the range). Prefer one overlapping OTE
               (61.8%-78.6% retracement); among those (or, if none, among all) the highest one.
             Cancel the setup if price trades below the origin (range invalid) or reaches the terminus
               before entry (it left without us: let it go).
  LTF        6 price taps the zone (LTF low <= zone top).
             8 after the tap, a 3-candle LTF swing low forms and is then swept (a lower low), and an LTF
               candle CLOSES above the latest LTF swing high that came before the sweep (MSS).
  Entry      variant "market": next LTF open after the MSS candle.
             variant "breaker": limit at the high of the last up-close LTF candle between that swing high
               and the sweep (the breaker block), capped at the MSS close, valid for 12 LTF candles.
  Risk       9 stop: just beyond the sweep extreme (lowest low from the sweep to the MSS).
             10 target: the HTF terminus (opposing external liquidity). Skip if it is under 2R away or the
               stop is narrower than 0.25% of price (costs dominate). Half the position closes at 2R, the
               rest at the target or the stop. No time limit; one trade per coin at a time.
  Costs      0.05% taker fee on every fill; 0.02% slippage on market entries and stop exits. Inside a
             candle the stop is checked first; a limit fill's own candle can stop it out but not reach a
             target. Funding is not charged (noted in the report with holding times).
  Measure    R per trade, gross and NET. 1% of the account risked per trade for the equity line.
  Controls   20 runs with the same entries (coin, time, price, stop distance, target distance) but the
             direction chosen by coin flip, simulated identically.
  PASS       per variant, all of: (1) mean net R 95% CI (bootstrap by month) above 0; (2) mean net R above
             the 95th percentile of the coin-flip controls; (3) mean net R > 0 in the last third of the
             period (holdout); (4) at least 55% of months with trades have positive net R.
             Six variants are tested, so one pass by luck is possible.
Research only: reads cached history, places no orders.

Usage:
  python3 -m research.ict_mayne                       # all pairs, both entries, 12 coins
  python3 -m research.ict_mayne --pairs D-1h --coins BTC,ETH
"""

import argparse
import os
import time

import numpy as np

from research.lab import ALL_COINS, _perp_klines

FEE, SLIP = 0.0005, 0.0002
MIN_WIDTH, MIN_RR, PARTIAL_R = 0.0025, 2.0, 2.0
LIMIT_BARS, N_CONTROLS = 12, 20
PAIRS = {"W-D": ("1d", "W"), "D-1h": ("1h", 86400), "4h-15m": ("15m", 14400)}
STEP = {"1d": 86400, "1h": 3600, "15m": 900}
WEEK0 = 4 * 86400                                   # 1970-01-05 was a Monday (Binance weeks)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_ltf(coin, ltf):
    """Complete LTF candles (t, o, h, l, c), without the flat placeholder rows some files start with."""
    a = _perp_klines(coin, ltf)[:, :5]
    a = a[a[:, 0] + STEP[ltf] <= time.time()]
    live = np.nonzero(a[:, 2] > a[:, 3])[0]
    return a[live[0]:] if len(live) else a[:0]


def build_htf(L, period):
    """Group LTF candles into HTF candles. Returns (gid per LTF bar, HTF o, h, l, c)."""
    t = L[:, 0].astype(np.int64)
    key = (t - WEEK0) // 604800 if period == "W" else t // period
    _, start, gid = np.unique(key, return_index=True, return_inverse=True)
    end = np.r_[start[1:], len(t)]
    o = L[start, 1]
    h = np.maximum.reduceat(L[:, 2], start)
    l = np.minimum.reduceat(L[:, 3], start)
    c = L[end - 1, 4]
    return gid, o, h, l, c


def signed(o, h, l, c, d):
    """Prices seen from the trade's side: for shorts everything is negated, so the long logic applies."""
    return (o, h, l, c) if d == 1 else (-o, -l, -h, -c)


def find_poi(Hs, oi, msb, k, origin, term):
    """Point of interest in signed space (long logic): (bottom, top) or None. Uses HTF candles <= k."""
    Ho, Hh, Hl, Hc = Hs
    R = term - origin
    if R <= 0:
        return None
    eq, ote_lo, ote_hi = origin + 0.5 * R, term - 0.786 * R, term - 0.618 * R
    cands = []
    for i in range(max(oi + 2, 2), k + 1):                      # fair value gaps inside the leg
        if Hl[i] > Hh[i - 2]:
            bot, top = Hh[i - 2], Hl[i]
            if i < k and Hl[i + 1:k + 1].min() <= top:
                continue
            cands.append((bot, top))
    for j in range(msb - 1, max(oi - 1, 0) - 1, -1):            # order block: last down-close before the MSB
        if Hc[j] < Ho[j]:
            bot, top = Hl[j], Hh[j]
            if msb == k or Hl[msb + 1:k + 1].min() > top:
                cands.append((bot, top))
            break
    keep = [z for z in cands if z[1] <= eq]
    if not keep:
        return None
    ote = [z for z in keep if z[1] >= ote_lo and z[0] <= ote_hi]
    return max(ote or keep, key=lambda z: z[1])


def simulate(lo, hi, cl, start, E, stop, p1, T, no_target_first, raw_E=None):
    """One trade in signed space from bar `start`. Returns (net_r, gross_r, exit_i, reason).
    E is the fill price (with slippage for market entries); raw_E, the price before slippage, gives gross R."""
    risk = E - stop
    raw_E = E if raw_E is None else raw_E
    left, net, gross, fees = 1.0, 0.0, 0.0, FEE * abs(E)
    half = False
    reason, j = "open", len(cl) - 1
    for j in range(start, len(cl)):
        if lo[j] <= stop:
            px = stop - SLIP * abs(stop)
            net += left * (px - E)
            gross += left * (stop - raw_E)
            fees += left * FEE * abs(px)
            left, reason = 0.0, "stop"
            break
        if j == start and no_target_first:
            continue
        if not half and hi[j] > p1:
            net += 0.5 * (p1 - E)
            gross += 0.5 * (p1 - raw_E)
            fees += 0.5 * FEE * abs(p1)
            left, half = 0.5, True
        if hi[j] > T:
            net += left * (T - E)
            gross += left * (T - raw_E)
            fees += left * FEE * abs(T)
            left, reason = 0.0, "target"
            break
    if left > 0:                                                # still open at the end of the data
        px = cl[j]
        net += left * (px - E)
        gross += left * (px - raw_E)
        fees += left * FEE * abs(px)
    return (net - fees) / risk, gross / risk, j, reason


def run_coin(coin, L, gid, H, entry_mode, funnel):
    t, Lh, Ll = L[:, 0], L[:, 2], L[:, 3]
    LS = {d: signed(L[:, 1], L[:, 2], L[:, 3], L[:, 4], d) for d in (1, -1)}
    HS = {d: signed(*H, d) for d in (1, -1)}
    Hh_raw, Hl_raw, Hc_raw = H[1], H[2], H[3]
    n = len(t)
    sh, sl = [], []                    # HTF confirmed swings (idx, value), raw prices
    sh_used = sl_used = -1
    lsh = lsl = None                   # latest confirmed LTF swing high / low (idx, value), raw
    setup = pending = None
    busy_until = -1
    trades = []

    for i in range(n):
        if i > 0 and gid[i] != gid[i - 1]:                      # HTF candle k just closed
            k = gid[i - 1]
            if k >= 2:
                if Hh_raw[k - 1] > Hh_raw[k - 2] and Hh_raw[k - 1] > Hh_raw[k]:
                    sh.append((k - 1, Hh_raw[k - 1]))
                if Hl_raw[k - 1] < Hl_raw[k - 2] and Hl_raw[k - 1] < Hl_raw[k]:
                    sl.append((k - 1, Hl_raw[k - 1]))
            trend = 0
            if len(sh) >= 2 and len(sl) >= 2:
                if sh[-1][1] > sh[-2][1] and sl[-1][1] > sl[-2][1]:
                    trend = 1
                elif sh[-1][1] < sh[-2][1] and sl[-1][1] < sl[-2][1]:
                    trend = -1
            msb, broken = 0, None
            if sh and sh[-1][0] != sh_used and Hc_raw[k] > sh[-1][1]:
                sh_used = sh[-1][0]
                if trend == 1:
                    msb, broken = 1, sh_used
            if sl and sl[-1][0] != sl_used and Hc_raw[k] < sl[-1][1]:
                sl_used = sl[-1][0]
                if trend == -1:
                    msb, broken = -1, sl_used
            free = i > busy_until and pending is None
            if free and msb:
                d = msb
                Ho, Hh, Hl, Hc = HS[d]
                oi = broken + int(np.argmin(Hl[broken:k + 1]))
                setup = {"d": d, "oi": oi, "msb": k, "origin": Hl[oi], "term": Hh[oi:k + 1].max(),
                         "zone": None, "tapped": False, "tap_i": -1, "sweep": None, "armed": False}
                funnel["msb"] += 1
            elif free and setup is not None and not setup["tapped"]:
                Ho, Hh, Hl, Hc = HS[setup["d"]]
                setup["term"] = max(setup["term"], Hh[k])
                if Hl[k] < setup["origin"]:
                    setup = None
            if free and setup is not None and not setup["tapped"]:
                setup["zone"] = find_poi(HS[setup["d"]], setup["oi"], setup["msb"], k, setup["origin"], setup["term"])
                if setup["zone"] is not None and not setup["armed"]:
                    setup["armed"] = True
                    funnel["armed"] += 1

        if i > busy_until and pending is not None:              # waiting for a breaker retest
            d = pending["d"]
            o_, hi_, lo_, cl_ = LS[d]
            if hi_[i] > pending["T"]:
                pending, setup = None, None
                funnel["limit_missed"] += 1
            elif lo_[i] < pending["E"]:
                net, gross, ex, why = simulate(lo_, hi_, cl_, i, pending["E"], pending["stop"], pending["p1"],
                                               pending["T"], True)
                trades.append(_trade(coin, d, t, i, ex, pending, net, gross, why, "limit"))
                busy_until, pending, setup = ex, None, None
            elif i - pending["from"] >= LIMIT_BARS:
                pending = None
                funnel["limit_missed"] += 1
                if setup is not None:
                    setup["sweep"] = None

        elif i > busy_until and setup is not None and setup["zone"] is not None:
            d = setup["d"]
            o_, hi_, lo_, cl_ = LS[d]
            z_bot, z_top = setup["zone"]
            if not setup["tapped"] and lo_[i] <= z_top:
                setup["tapped"], setup["tap_i"] = True, i
                funnel["tapped"] += 1
            if setup["tapped"]:
                if lo_[i] < setup["origin"] or hi_[i] >= setup["term"]:
                    setup = None
                else:
                    sw_low = _sw(lsl, lsh, d, "low")
                    sw_high = _sw(lsl, lsh, d, "high")
                    sw = setup["sweep"]
                    if sw is None and sw_low is not None and sw_low[0] >= setup["tap_i"] and lo_[i] < sw_low[1] \
                            and sw_high is not None:
                        sw = setup["sweep"] = {"i": i, "low": lo_[i], "ref_i": sw_high[0], "ref": sw_high[1]}
                    elif sw is not None:
                        sw["low"] = min(sw["low"], lo_[i])
                    if sw is not None and cl_[i] > sw["ref"]:
                        funnel["trigger"] += 1
                        stop = sw["low"]
                        if entry_mode == "market":
                            if i + 1 < n:
                                E = o_[i + 1] + SLIP * abs(o_[i + 1])
                                risk = E - stop
                                if risk > 0 and risk >= MIN_WIDTH * abs(E) and setup["term"] - E >= MIN_RR * risk:
                                    p1 = E + PARTIAL_R * risk
                                    net, gross, ex, why = simulate(lo_, hi_, cl_, i + 1, E, stop, p1, setup["term"],
                                                                   False, o_[i + 1])
                                    tr = {"E": E, "stop": stop, "p1": p1, "T": setup["term"]}
                                    trades.append(_trade(coin, d, t, i + 1, ex, tr, net, gross, why, "market"))
                                    busy_until, setup = ex, None
                                else:
                                    funnel["rr_fail"] += 1
                                    setup["sweep"] = None
                        else:
                            lvl = sw["ref"]
                            for j in range(sw["i"], sw["ref_i"] - 1, -1):
                                if cl_[j] > o_[j]:
                                    lvl = hi_[j]
                                    break
                            E = min(lvl, cl_[i])
                            risk = E - stop
                            if risk > 0 and risk >= MIN_WIDTH * abs(E) and setup["term"] - E >= MIN_RR * risk:
                                pending = {"d": d, "E": E, "stop": stop, "p1": E + PARTIAL_R * risk,
                                           "T": setup["term"], "from": i}
                            else:
                                funnel["rr_fail"] += 1
                                setup["sweep"] = None

        if i >= 2:                                              # bar i confirms an LTF swing at i-1
            if Lh[i - 1] > Lh[i - 2] and Lh[i - 1] > Lh[i]:
                lsh = (i - 1, Lh[i - 1])
            if Ll[i - 1] < Ll[i - 2] and Ll[i - 1] < Ll[i]:
                lsl = (i - 1, Ll[i - 1])
    return trades


def _sw(lsl, lsh, d, which):
    """Latest confirmed LTF swing in signed space: 'low' = support side for this trade direction."""
    if d == 1:
        s = lsl if which == "low" else lsh
        return s
    s = lsh if which == "low" else lsl
    return None if s is None else (s[0], -s[1])


def _trade(coin, d, t, i, ex, tr, net, gross, why, kind):
    return {"coin": coin, "dir": d, "entry_t": int(t[i]), "exit_t": int(t[min(ex, len(t) - 1)]), "entry_i": i,
            "E": tr["E"], "stop": tr["stop"], "p1": tr["p1"], "T": tr["T"], "net": net, "gross": gross,
            "why": why, "kind": kind}


def control_runs(data, trades, n_runs=N_CONTROLS):
    """Same entries, coin-flip direction, same stop and target distances (in R)."""
    out, cache = [], {}
    for s in range(n_runs):
        rng = np.random.default_rng(1000 + s)
        rs = []
        for tr in trades:
            d0, d = tr["dir"], (1 if rng.random() < 0.5 else -1)
            E_raw = d0 * tr["E"]
            risk = tr["E"] - tr["stop"]
            rr = (tr["T"] - tr["E"]) / risk
            key = (tr["coin"], d)
            if key not in cache:
                L = data[tr["coin"]]
                cache[key] = signed(L[:, 1], L[:, 2], L[:, 3], L[:, 4], d)
            o_, hi_, lo_, cl_ = cache[key]
            E = d * E_raw
            net, *_ = simulate(lo_, hi_, cl_, tr["entry_i"], E, E - risk, E + PARTIAL_R * risk, E + rr * risk,
                               tr["kind"] == "limit")
            rs.append(net)
        out.append(float(np.mean(rs)) if rs else 0.0)
    return out


def month_ci(trades, n_boot=2000, seed=0):
    if not trades:
        return 0.0, 0.0
    by = {}
    for tr in trades:
        by.setdefault(time.strftime("%Y-%m", time.gmtime(tr["entry_t"])), []).append(tr["net"])
    groups = list(by.values())
    rng = np.random.default_rng(seed)
    means = []
    for _ in range(n_boot):
        pick = [groups[j] for j in rng.integers(0, len(groups), len(groups))]
        flat = [x for g in pick for x in g]
        means.append(np.mean(flat))
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def evaluate(name, trades, controls, span, funnel):
    r = np.array([tr["net"] for tr in trades]) if trades else np.zeros(0)
    res = {"name": name, "n": len(trades), "funnel": dict(funnel)}
    if not len(r):
        res.update(passed=False, mean=0.0)
        return res
    lo, hi = month_ci(trades)
    months = {}
    for tr in trades:
        months.setdefault(time.strftime("%Y-%m", time.gmtime(tr["exit_t"])), []).append(tr["net"])
    pos_m = sum(1 for v in months.values() if sum(v) > 0) / len(months)
    cut = span[0] + (span[1] - span[0]) * 2 / 3
    hold = [tr["net"] for tr in trades if tr["entry_t"] >= cut]
    c95 = float(np.percentile(controls, 95)) if controls else 0.0
    eq, peak, dd = 1.0, 1.0, 0.0
    for tr in sorted(trades, key=lambda x: x["exit_t"]):
        eq *= 1 + 0.01 * tr["net"]
        peak = max(peak, eq)
        dd = min(dd, eq / peak - 1)
    years = {}
    for tr in trades:
        years.setdefault(time.strftime("%Y", time.gmtime(tr["entry_t"])), []).append(tr["net"])
    holds_h = [(tr["exit_t"] - tr["entry_t"]) / 3600 for tr in trades]
    res.update(
        mean=float(r.mean()), gross=float(np.mean([tr["gross"] for tr in trades])), win=float((r > 0).mean()),
        total=float(r.sum()), ci=(lo, hi), pos_months=pos_m, n_months=len(months),
        hold_mean=float(np.mean(hold)) if hold else 0.0, hold_n=len(hold), ctrl95=c95,
        ctrl_mean=float(np.mean(controls)) if controls else 0.0, equity=eq, max_dd=dd,
        years={y: (len(v), float(np.sum(v))) for y, v in sorted(years.items())},
        longs=[tr["net"] for tr in trades if tr["dir"] == 1], shorts=[tr["net"] for tr in trades if tr["dir"] == -1],
        reasons={k: sum(1 for tr in trades if tr["why"] == k) for k in ("stop", "target", "open")},
        median_hold_h=float(np.median(holds_h)),
        coins={c: (sum(1 for tr in trades if tr["coin"] == c), float(sum(tr["net"] for tr in trades if tr["coin"] == c)))
               for c in sorted({tr["coin"] for tr in trades})},
    )
    res["checks"] = [lo > 0, res["mean"] > c95, res["hold_mean"] > 0, pos_m >= 0.55]
    res["passed"] = all(res["checks"])
    return res


def fmt(results, coins, spans):
    out = ["# Trader Mayne ICT framework: backtest", "",
           f"Generated {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}. Coins: {', '.join(coins)}.",
           "Rules pre-registered in `research/ict_mayne.py` (2026-11-25) from the pre-trade checklist, before any run.",
           "R = the amount risked on a trade (entry to stop). Net = after 0.05% fees per fill and 0.02% slippage.",
           "Equity = risking 1% of the account per trade, compounding. Funding is not charged.", "",
           "| variant | data | trades | win % | avg R gross | avg R net | 95% CI | coin-flip 95th | holdout avg R | months + | 1% risk equity | max drop | PASS |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in results:
        if not r["n"]:
            out.append(f"| {r['name']} | {spans[r['name']]} | 0 | | | | | | | | | | no |")
            continue
        out.append(f"| {r['name']} | {spans[r['name']]} | {r['n']} | {100 * r['win']:.0f}% | {r['gross']:+.3f} | "
                   f"{r['mean']:+.3f} | {r['ci'][0]:+.3f} to {r['ci'][1]:+.3f} | {r['ctrl95']:+.3f} | "
                   f"{r['hold_mean']:+.3f} ({r['hold_n']}) | {100 * r['pos_months']:.0f}% of {r['n_months']} | "
                   f"{100 * (r['equity'] - 1):+.1f}% | {100 * r['max_dd']:.1f}% | {'**yes**' if r['passed'] else 'no'} |")
    out += ["", "## How many setups survive each checklist step", "",
            "| variant | HTF trend + MSB | valid POI in discount/premium | price tapped POI | LTF sweep + MSS | failed 2R / stop-width check | breaker retest missed | trades |",
            "|---|---|---|---|---|---|---|---|"]
    for r in results:
        f = r["funnel"]
        out.append(f"| {r['name']} | {f['msb']} | {f['armed']} | {f['tapped']} | {f['trigger']} | {f['rr_fail']} | "
                   f"{f['limit_missed']} | {r['n']} |")
    for r in results:
        if not r["n"]:
            continue
        L, S = r["longs"], r["shorts"]
        out += ["", f"## {r['name']}", "",
                f"- Exits: {r['reasons']['target']} reached the target, {r['reasons']['stop']} stopped "
                f"(some after taking half at 2R), {r['reasons']['open']} still open at the end.",
                f"- Longs: {len(L)} trades, avg {np.mean(L) if L else 0:+.3f} R. Shorts: {len(S)} trades, "
                f"avg {np.mean(S) if S else 0:+.3f} R.",
                f"- Median time in a trade: {r['median_hold_h']:.0f} hours. Coin-flip direction average: {r['ctrl_mean']:+.3f} R.",
                f"- Checks (CI > 0, beats coin flip, holdout > 0, months >= 55%): "
                + ", ".join("yes" if c else "no" for c in r["checks"]), "",
                "| year | trades | net R |", "|---|---|---|"]
        out += [f"| {y} | {n} | {s:+.1f} |" for y, (n, s) in r["years"].items()]
        out += ["", "| coin | trades | net R |", "|---|---|---|"]
        out += [f"| {c} | {n} | {s:+.1f} |" for c, (n, s) in r["coins"].items()]
    return "\n".join(out) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", default=",".join(PAIRS))
    ap.add_argument("--coins", default=",".join(ALL_COINS))
    ap.add_argument("--entries", default="market,breaker")
    ap.add_argument("--out", default=os.path.join(ROOT, "docs", "ICT_MAYNE_BACKTEST.md"))
    a = ap.parse_args(argv)
    coins = [c.strip().upper() for c in a.coins.split(",")]
    results, spans = [], {}
    for pair in a.pairs.split(","):
        ltf, period = PAIRS[pair]
        data, htf = {}, {}
        for c in coins:
            L = load_ltf(c, ltf)
            if len(L) < 200:
                continue
            data[c] = L
            htf[c] = build_htf(L, period)
        lo_t = min(L[0, 0] for L in data.values())
        hi_t = max(L[-1, 0] for L in data.values())
        for mode in a.entries.split(","):
            name = f"{pair} {mode}"
            spans[name] = f"{time.strftime('%Y-%m', time.gmtime(lo_t))} to {time.strftime('%Y-%m', time.gmtime(hi_t))}"
            funnel = dict.fromkeys(("msb", "armed", "tapped", "trigger", "rr_fail", "limit_missed"), 0)
            trades = []
            for c, L in data.items():
                gid, *H = htf[c]
                trades += run_coin(c, L, gid, H, mode, funnel)
            controls = control_runs(data, trades)
            r = evaluate(name, trades, controls, (lo_t, hi_t), funnel)
            results.append(r)
            print(f"{name}: {r['n']} trades, avg net R {r.get('mean', 0):+.3f}, pass={r['passed']}", flush=True)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w") as f:
        f.write(fmt(results, coins, spans))
    print("wrote", a.out)


if __name__ == "__main__":
    main()
