"""
Slow strategies on Binance USDT-M perpetuals, where trading costs are small next to the move:
daily trend following and delta-neutral funding carry.

PRE-REGISTERED (written before any run; parameters are fixed, nothing is fitted to the data)
-------------------------------------------------------------------------------------------
Data: Binance public daily klines (perp and spot) and the full perp funding history, fetched
from 2019-09-01 and cached in real_data/slow/. Evaluation 2020-01-01 .. last complete UTC day.
Universe: the live bot's 12 coins (BTC ETH SOL XRP BNB DOGE ZEC HYPE NEAR SUI ADA LINK); a coin
joins 60 days after its first perp bar. Caveat: the list is chosen today, so it carries
survivorship bias toward coins that did well. The random controls and buy-and-hold share it.

Costs: perp 0.05% taker + 0.02% slippage per side (0.07%); spot 0.10% + 0.02% (0.12%).
Funding: every settlement is charged to the position held over it; a long pays positive funding.
A position decided at the close of day d earns day d+1's return and day d+1's settlements
(those after 00:00 of d+1 up to and including 00:00 of d+2).

T. Trend following (primary: T1)
    signal at the close of day d = sign(close_d - SMA_n(close)_d), +1 long / -1 short
    equal weight across the active coins, gross leverage 1, rebalanced daily (costs charged on
    the turnover against the drifted weights)
    T1 SMA20 long/short (PRIMARY) | T2 SMA50 long/short | T3 SMA20 long-only | T4 SMA50 long-only
    benchmark: equal-weight buy and hold of the same perps (funding and rebalancing costs paid)
    control: 200 random signal series per coin with the same number of flips as T1
    PASS (T1): net return > 0, Sharpe >= 0.5, beats the 95th percentile of the random
    controls, and positive in at least 4 of the 7 calendar years 2020..2026

C. Delta-neutral funding carry (long spot + short perp, same quantity)
    signal at the close of day d = mean daily funding of days d-2..d, x365
    enter when > 10% a year, exit when < 0%; each coin gets 1/N of equity, of which 75% is
    notional (the rest is perp margin); entry and exit pay all four legs (0.19% of notional)
    control: 200 random-timing runs per coin with the same holding episodes placed at random
    PASS: net return > 0, positive in at least 2/3 of calendar quarters, max drawdown <= 10%,
    and beats the 95th percentile of the random-timing controls

Run:  python -m research.slow_strategies [--refresh] [--controls 200]
"""

import argparse
import json
import os
import time
import urllib.request
from dataclasses import dataclass, field

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "real_data", "slow")
OUT = os.path.join(ROOT, "docs", "SLOW_STRATEGIES_RESULTS.md")
COINS = ["BTC", "ETH", "SOL", "XRP", "BNB", "DOGE", "ZEC", "HYPE", "NEAR", "SUI", "ADA", "LINK"]
DAY = 86400
FETCH_START = 1_567_296_000      # 2019-09-01
EVAL_START = 1_577_836_800       # 2020-01-01
LISTING_DAYS = 60
PERP_COST = 0.0007
SPOT_COST = 0.0012
CARRY_COST = PERP_COST + SPOT_COST


# ---------------------------------------------------------------- data

def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "research-backtest"})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except Exception:
            if attempt == 4:
                raise
            time.sleep(2 * (attempt + 1))


def _klines(base, sym, limit):
    out, cur = [], FETCH_START * 1000
    now_ms = int(time.time() * 1000)
    while cur < now_ms:
        rows = _get(f"{base}?symbol={sym}&interval=1d&startTime={cur}&limit={limit}")
        if not isinstance(rows, list) or not rows:
            break
        out += [[int(r[0]) // 1000, float(r[4])] for r in rows]
        cur = int(rows[-1][0]) + DAY * 1000
        if len(rows) < limit:
            break
        time.sleep(0.2)
    # keep complete days only
    return [r for r in out if r[0] + DAY <= now_ms // 1000]


def _funding(sym):
    out, cur = [], FETCH_START * 1000
    while True:
        rows = _get(f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={sym}&startTime={cur}&limit=1000")
        if not isinstance(rows, list) or not rows:
            break
        out += [[int(r["fundingTime"]) // 1000, float(r["fundingRate"])] for r in rows]
        cur = int(rows[-1]["fundingTime"]) + 1
        if len(rows) < 1000:
            break
        time.sleep(0.2)
    return out


def load(coin, refresh=False):
    os.makedirs(CACHE, exist_ok=True)
    sym = f"{coin}USDT"
    data = {}
    for kind, fn in (("perp", lambda: _klines("https://fapi.binance.com/fapi/v1/klines", sym, 1500)),
                     ("spot", lambda: _klines("https://api.binance.com/api/v3/klines", sym, 1000)),
                     ("funding", lambda: _funding(sym))):
        path = os.path.join(CACHE, f"{kind}_{sym}.json")
        if refresh or not os.path.exists(path):
            rows = fn()
            with open(path, "w") as f:
                json.dump(rows, f)
        with open(path) as f:
            data[kind] = np.array(json.load(f), dtype=float).reshape(-1, 2)
    return data


def funding_per_day(day_t, f_t, f_r):
    """Sum of the settlements in (day open, day open + 1 day] for each day."""
    day_t = np.asarray(day_t, dtype=np.int64)
    f_t = np.asarray(f_t, dtype=np.int64)
    f_r = np.asarray(f_r, dtype=float)
    out = np.zeros(len(day_t))
    if len(f_t) == 0:
        return out
    idx = np.searchsorted(day_t, f_t, side="left") - 1      # day whose open is strictly before t
    ok = (idx >= 0) & (f_t <= day_t[np.clip(idx, 0, None)] + DAY)
    np.add.at(out, idx[ok], f_r[ok])
    return out


@dataclass
class Panel:
    coins: list
    t: np.ndarray
    perp: np.ndarray
    spot: np.ndarray
    fund: np.ndarray
    trend_active: np.ndarray
    carry_active: np.ndarray


def build_panel(raw):
    coins = [c for c in COINS if c in raw and len(raw[c]["perp"])]
    last = min(int(raw[c]["perp"][-1, 0]) for c in coins if raw[c]["perp"][-1, 0] > EVAL_START)
    t = np.arange(FETCH_START, last + 1, DAY, dtype=np.int64)
    n, D = len(coins), len(t)
    perp, spot, fund = np.full((n, D), np.nan), np.full((n, D), np.nan), np.zeros((n, D))
    first = np.zeros(n, dtype=np.int64)
    for i, c in enumerate(coins):
        for arr, key in ((perp, "perp"), (spot, "spot")):
            rows = raw[c][key]
            if len(rows):
                k = ((rows[:, 0].astype(np.int64) - FETCH_START) // DAY)
                ok = (k >= 0) & (k < D)
                arr[i, k[ok]] = rows[ok, 1]
        f = raw[c]["funding"]
        if len(f):
            fund[i] = funding_per_day(t, f[:, 0], f[:, 1])
        first[i] = int(np.argmax(np.isfinite(perp[i])))
    nxt = lambda a: np.c_[np.isfinite(a[:, 1:]), np.zeros((n, 1), bool)]
    listed = np.arange(D)[None, :] >= (first[:, None] + LISTING_DAYS)
    in_eval = (t >= EVAL_START)[None, :]
    trend_active = listed & in_eval & np.isfinite(perp) & nxt(perp)
    carry_active = trend_active & np.isfinite(spot) & nxt(spot)
    return Panel(coins, t, perp, spot, fund, trend_active, carry_active)


# ---------------------------------------------------------------- trend

def trend_signal(close, n, long_only):
    c = np.asarray(close, dtype=float)
    s = np.zeros(len(c))
    if len(c) < n:
        return s
    cs = np.cumsum(np.r_[0.0, c])
    sma = (cs[n:] - cs[:-n]) / n                    # sma[k] = mean(c[k .. k+n-1])
    s[n - 1:] = np.sign(c[n - 1:] - sma)
    return np.maximum(s, 0.0) if long_only else s


def panel_signal(perp, active, n, long_only):
    out = np.zeros_like(perp)
    for i in range(perp.shape[0]):
        ok = np.isfinite(perp[i])
        if ok.any():
            a, b = int(np.argmax(ok)), len(ok) - int(np.argmax(ok[::-1]))
            seg = perp[i, a:b].copy()
            seg = np.where(np.isfinite(seg), seg, np.nan)
            seg = _ffill(seg)
            out[i, a:b] = trend_signal(seg, n, long_only)
    return np.where(active, out, 0.0)


def _ffill(x):
    idx = np.where(np.isfinite(x), np.arange(len(x)), 0)
    np.maximum.accumulate(idx, out=idx)
    return x[idx]


@dataclass
class Result:
    returns: np.ndarray
    price: np.ndarray = None
    funding: np.ndarray = None
    costs: np.ndarray = None
    turnover: float = 0.0
    held: np.ndarray = None
    by_coin: np.ndarray = None


def _ret(px):
    r = np.zeros_like(px)
    with np.errstate(invalid="ignore", divide="ignore"):
        r[:, 1:] = px[:, 1:] / px[:, :-1] - 1.0
    return np.nan_to_num(r, nan=0.0, posinf=0.0, neginf=0.0)


def run_trend(close, fund, sig, active, cost=PERP_COST):
    close = np.asarray(close, dtype=float)
    sig = np.where(active, sig, 0.0)
    n_act = np.maximum(active.sum(axis=0), 1)
    w = sig / n_act[None, :]
    r = _ret(close)
    C, D = close.shape
    price, funding, costs = np.zeros(D), np.zeros(D), np.zeros(D)
    by_coin = np.zeros(C)
    prev_drift = np.zeros(C)
    total_turn = 0.0
    for d in range(1, D):
        wp = w[:, d - 1]
        turn = np.abs(wp - prev_drift).sum()
        total_turn += turn
        pc = wp * r[:, d] - wp * fund[:, d]
        price[d] = (wp * r[:, d]).sum()
        funding[d] = -(wp * fund[:, d]).sum()
        costs[d] = -cost * turn
        by_coin += pc - cost * np.abs(wp - prev_drift)
        prev_drift = wp * (1 + r[:, d]) / (1 + price[d])
    # close whatever is still open at the final close
    final = np.abs(prev_drift).sum()
    costs[-1] -= cost * final
    total_turn += final
    rets = price + funding + costs
    return Result(rets, price, funding, costs, total_turn, by_coin=by_coin)


def flips(x):
    x = np.asarray(x)
    return int(np.sum(x[1:] != x[:-1])) if len(x) > 1 else 0


def random_like(sig, active, rng):
    out = np.zeros(len(sig))
    a = np.asarray(sig)[active]
    if len(a) == 0:
        return out
    vals = (-1.0, 1.0) if (a < 0).any() else (0.0, 1.0)
    F = flips(a)
    x = np.empty(len(a))
    cur = rng.choice(vals)
    pos = set((rng.choice(len(a) - 1, size=F, replace=False) + 1).tolist()) if F else set()
    for k in range(len(a)):
        if k in pos:
            cur = vals[1] if cur == vals[0] else vals[0]
        x[k] = cur
    out[active] = x
    return out


# ---------------------------------------------------------------- carry

def carry_held(fund, active, enter, exit_):
    C, D = fund.shape
    held = np.zeros((C, D), bool)
    for i in range(C):
        on = False
        for d in range(D):
            if not active[i, d] or d == D - 1:
                on = False
            elif d >= 2 and active[i, d - 2]:
                ann = fund[i, d - 2:d + 1].mean() * 365.0
                if not on and ann > enter:
                    on = True
                elif on and ann < exit_:
                    on = False
            held[i, d] = on
    return held


def eval_carry(spot, perp, fund, active, held, slot_frac=0.75):
    C, D = spot.shape
    n_act = np.maximum(active.sum(axis=0), 1)
    w = np.where(held, slot_frac / n_act[None, :], 0.0)
    rs, rp = _ret(spot), _ret(perp)
    rets, price, funding, costs = np.zeros(D), np.zeros(D), np.zeros(D), np.zeros(D)
    by_coin = np.zeros(C)
    turn_total = 0.0
    for d in range(1, D):
        wp = w[:, d - 1]
        wpp = w[:, d - 2] if d >= 2 else np.zeros(C)
        trade = np.abs(wp - wpp)
        if d == D - 1:
            trade = trade + np.abs(wp)          # final close
        turn_total += trade.sum()
        price[d] = (wp * (rs[:, d] - rp[:, d])).sum()
        funding[d] = (wp * fund[:, d]).sum()
        costs[d] = -CARRY_COST * trade.sum()
        by_coin += wp * (rs[:, d] - rp[:, d] + fund[:, d]) - CARRY_COST * trade
    rets = price + funding + costs
    return Result(rets, price, funding, costs, turn_total, held=held, by_coin=by_coin)


def run_carry(spot, perp, fund, active, enter=0.10, exit_=0.0, slot_frac=0.75):
    held = carry_held(fund, active, enter, exit_)
    return eval_carry(spot, perp, fund, active, held, slot_frac)


def random_timing(held_row, active_row, rng):
    idx = np.flatnonzero(active_row)
    out = np.zeros(len(held_row), bool)
    if len(idx) == 0:
        return out
    h = held_row[idx]
    eps, run = [], 0
    for v in h:
        if v:
            run += 1
        elif run:
            eps.append(run)
            run = 0
    if run:
        eps.append(run)
    if not eps:
        return out
    k, G = len(eps), len(h) - sum(eps)
    cuts = np.sort(rng.choice(G + k, size=k, replace=False))
    gaps = np.diff(np.r_[-1, cuts]) - 1                # k gaps before each episode, sum <= G
    rng.shuffle(eps)
    x = np.zeros(len(h), bool)
    p = 0
    for g, L in zip(gaps, eps):
        p += int(g)
        x[p:p + L] = True
        p += L
    x[-1] = False
    out[idx] = x
    return out


# ---------------------------------------------------------------- stats & report

def stats(t, rets, mask):
    r = rets[mask]
    eq = np.cumprod(1 + r)
    yrs = len(r) / 365.0
    total = eq[-1] - 1 if len(eq) else 0.0
    cagr = eq[-1] ** (1 / yrs) - 1 if len(eq) and eq[-1] > 0 else -1.0
    vol = r.std() * np.sqrt(365)
    sharpe = r.mean() / r.std() * np.sqrt(365) if r.std() > 0 else 0.0
    dd = float((1 - eq / np.maximum.accumulate(eq)).max()) if len(eq) else 0.0
    years, quarters = {}, {}
    tt = t[mask]
    for ts, x in zip(tt, r):
        tm = time.gmtime(int(ts))
        years.setdefault(tm.tm_year, []).append(x)
        quarters.setdefault((tm.tm_year, (tm.tm_mon - 1) // 3 + 1), []).append(x)
    yr = {y: float(np.prod(1 + np.array(v)) - 1) for y, v in years.items()}
    qr = {q: float(np.prod(1 + np.array(v)) - 1) for q, v in quarters.items()}
    last12 = float(np.prod(1 + r[-365:]) - 1)
    return dict(total=total, cagr=cagr, vol=vol, sharpe=sharpe, dd=dd, years=yr, quarters=qr, last12=last12)


def fmt_pct(x):
    return f"{100 * x:+.1f}%"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--controls", type=int, default=200)
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args(argv)

    raw = {}
    for c in COINS:
        try:
            raw[c] = load(c, a.refresh)
            print(f"  {c}: perp {len(raw[c]['perp'])} days, spot {len(raw[c]['spot'])} days, "
                  f"funding {len(raw[c]['funding'])} settlements")
        except Exception as e:
            print(f"  {c}: FAILED {e}")
    P = build_panel(raw)
    eval_mask = P.t >= EVAL_START
    start = time.strftime("%Y-%m-%d", time.gmtime(int(P.t[eval_mask][0])))
    end = time.strftime("%Y-%m-%d", time.gmtime(int(P.t[-1])))
    rng = np.random.default_rng(20261123)
    L = []
    say = lambda s="": (print(s), L.append(s))

    say(f"# Slow strategies on Binance perps ({start} .. {end})")
    say()
    say("Pre-registered rules are in the header of `research/slow_strategies.py`. Costs: perp 0.07% per side, "
        "spot 0.12% per side; funding charged on every settlement. Universe chosen today (survivorship bias; "
        "shared by the controls and buy and hold).")
    say()
    say("## Trend following")
    say()
    say("| variant | total | CAGR | Sharpe | max DD | last 12m | funding | costs | turnover/yr | years + |")
    say("|---|---|---|---|---|---|---|---|---|---|")
    variants = [("T1 SMA20 long/short (PRIMARY)", 20, False), ("T2 SMA50 long/short", 50, False),
                ("T3 SMA20 long-only", 20, True), ("T4 SMA50 long-only", 50, True)]
    res = {}
    for name, n, lo in variants + [("Buy and hold (benchmark)", None, True)]:
        sig = np.where(P.trend_active, 1.0, 0.0) if n is None else panel_signal(P.perp, P.trend_active, n, lo)
        r = run_trend(P.perp, P.fund, sig, P.trend_active)
        s = stats(P.t, r.returns, eval_mask)
        res[name] = (sig, r, s)
        yrs = len(s["years"])
        pos = sum(v > 0 for v in s["years"].values())
        say(f"| {name} | {fmt_pct(s['total'])} | {fmt_pct(s['cagr'])} | {s['sharpe']:.2f} | {100 * s['dd']:.1f}% | "
            f"{fmt_pct(s['last12'])} | {fmt_pct(r.funding[eval_mask].sum())} | {fmt_pct(r.costs[eval_mask].sum())} | "
            f"{r.turnover / (eval_mask.sum() / 365):.1f} | {pos}/{yrs} |")
    say()
    say("Calendar years:")
    say()
    years = sorted(res[variants[0][0]][2]["years"])
    say("| variant | " + " | ".join(str(y) for y in years) + " |")
    say("|---|" + "---|" * len(years))
    for name in res:
        s = res[name][2]
        say(f"| {name} | " + " | ".join(fmt_pct(s["years"].get(y, 0.0)) for y in years) + " |")
    say()
    sig1, r1, s1 = res[variants[0][0]]
    say("Per coin, T1 (sum of daily contributions to portfolio return):")
    say()
    say(" | ".join(f"{c} {fmt_pct(x)}" for c, x in zip(P.coins, r1.by_coin)))
    say()
    ctl = []
    for _ in range(a.controls):
        rs = np.vstack([random_like(sig1[i], P.trend_active[i], rng) for i in range(len(P.coins))])
        ctl.append(stats(P.t, run_trend(P.perp, P.fund, rs, P.trend_active).returns, eval_mask)["total"])
    ctl = np.array(ctl)
    p95 = float(np.percentile(ctl, 95))
    yrs_pos = sum(v > 0 for v in s1["years"].values())
    t_pass = [s1["total"] > 0, s1["sharpe"] >= 0.5, s1["total"] > p95, yrs_pos >= 4]
    say(f"Random controls for T1 ({a.controls}, same flip count per coin): median {fmt_pct(np.median(ctl))}, "
        f"95th pct {fmt_pct(p95)}, best {fmt_pct(ctl.max())}; T1 ranks above "
        f"{100 * (ctl < s1['total']).mean():.0f}% of them.")
    say()
    say(f"**PASS MARK T1:** net > 0 {t_pass[0]} | Sharpe >= 0.5 {t_pass[1]} ({s1['sharpe']:.2f}) | "
        f"beats random 95th pct {t_pass[2]} | years positive {yrs_pos}/{len(s1['years'])} (need 4) {t_pass[3]} "
        f"==> **{'PASS' if all(t_pass) else 'FAIL'}**")
    say()

    say("## Delta-neutral funding carry (long spot + short perp)")
    say()
    rc = run_carry(P.spot, P.perp, P.fund, P.carry_active)
    sc = stats(P.t, rc.returns, eval_mask)
    always = eval_carry(P.spot, P.perp, P.fund, P.carry_active,
                        carry_held(P.fund, P.carry_active, -1e9, -1e9))
    sa = stats(P.t, always.returns, eval_mask)
    say("| variant | total | CAGR | Sharpe | max DD | last 12m | funding | basis | costs | days in trade |")
    say("|---|---|---|---|---|---|---|---|---|---|")
    for name, r, s in (("C enter >10%/yr, exit <0% (PRIMARY)", rc, sc), ("Always on (reference)", always, sa)):
        say(f"| {name} | {fmt_pct(s['total'])} | {fmt_pct(s['cagr'])} | {s['sharpe']:.2f} | {100 * s['dd']:.1f}% | "
            f"{fmt_pct(s['last12'])} | {fmt_pct(r.funding[eval_mask].sum())} | {fmt_pct(r.price[eval_mask].sum())} | "
            f"{fmt_pct(r.costs[eval_mask].sum())} | {int(r.held[:, eval_mask].sum())} |")
    say()
    say("Calendar years (C): " + " | ".join(f"{y} {fmt_pct(v)}" for y, v in sorted(sc["years"].items())))
    say()
    say("Per coin (C): " + " | ".join(f"{c} {fmt_pct(x)} ({int(rc.held[i].sum())}d)"
                                      for i, (c, x) in enumerate(zip(P.coins, rc.by_coin))))
    say()
    cc = []
    for _ in range(a.controls):
        hr = np.vstack([random_timing(rc.held[i], P.carry_active[i], rng) for i in range(len(P.coins))])
        cc.append(stats(P.t, eval_carry(P.spot, P.perp, P.fund, P.carry_active, hr).returns, eval_mask)["total"])
    cc = np.array(cc)
    c95 = float(np.percentile(cc, 95))
    q_pos = sum(v > 0 for v in sc["quarters"].values())
    q_n = len(sc["quarters"])
    c_pass = [sc["total"] > 0, q_pos >= 2 * q_n / 3, sc["dd"] <= 0.10, sc["total"] > c95]
    say(f"Random-timing controls ({a.controls}, same episodes placed at random): median {fmt_pct(np.median(cc))}, "
        f"95th pct {fmt_pct(c95)}, best {fmt_pct(cc.max())}.")
    say()
    say(f"**PASS MARK C:** net > 0 {c_pass[0]} | quarters positive {q_pos}/{q_n} (need 2/3) {c_pass[1]} | "
        f"max DD <= 10% {c_pass[2]} ({100 * sc['dd']:.1f}%) | beats random-timing 95th pct {c_pass[3]} "
        f"==> **{'PASS' if all(c_pass) else 'FAIL'}**")
    say()
    say("Quarters (C): " + " | ".join(f"{y}Q{q} {fmt_pct(v)}" for (y, q), v in sorted(sc["quarters"].items())))

    with open(a.out, "w") as f:
        f.write("\n".join(L) + "\n")
    print(f"\nreport written to {a.out}")


if __name__ == "__main__":
    main()
