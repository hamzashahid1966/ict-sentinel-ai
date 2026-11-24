"""
Maker (resting limit order) backtest on Polymarket 5-minute crypto rounds, using the order book the
round recorder saves about every 1.7 seconds (polymarket_sentinel/round_recorder.db).

Idea: instead of paying the spread and the taker fee, rest bids on both tokens and let sellers
come to us. Makers pay no fee (Polymarket fee docs; the discretionary maker rebate is counted as 0).
The risk is adverse selection: a resting bid tends to fill when the price is moving against it.

PRE-REGISTERED (fixed before the first run)
-------------------------------------------
PRIMARY  at 240 s before the close, read the Up book (last sample at or before that moment, at
         most 3 s old). Rest a bid for Up at the best Up bid and a bid for Down at 1 - best Up ask
         (the best Down bid). 5 dollars of notional per side. Cancel whatever has not filled 15 s
         before the close. Hold fills to settlement on the official outcome.
FILL     strict: an Up bid at p fills at p at the first later sample whose best Up ask <= p
         (a seller is willing to trade at our price, so the queue ahead of us is gone). A Down bid
         at q fills when the best Up bid >= 1 - q. Rounds with a book gap > 10 s between the
         posting time and the cancel time are skipped.
VARIANTS (reported, not judged) posting at 180 / 120 / 60 s; improving each side by 1 cent when
         the spread is >= 3 cents; a lenient fill rule (also fills when the best bid drops below
         our price, i.e. assumes everyone ahead of us traded or cancelled).
CONTROL  taker at the same moment: buy a random side at the ask and pay the 0.07*p*(1-p) fee.
PASS     total P&L > 0 and the 95% bootstrap interval (resampling rounds) is above 0.
         Mean > 0 with the interval including 0 is INCONCLUSIVE (rerun at >= 2,000 rounds).

CORRECTION (2026-11-23, after the first run; recorded rather than hidden)
    1. Five dollars per side buys unequal share counts (6.7 Up at 0.75 vs 20.8 Down at 0.24), so a
       "both filled" round was really a leveraged bet on the underdog, not a captured spread. The
       first run's +10..46% per dollar was that luck. The maker idea needs EQUAL shares: when both
       fill, (1 - p_up - p_down) x shares is locked whatever the outcome. Primary is now 10 shares
       per side.
    2. The 10 s gap filter dropped 264 of 293 rounds. A gap can only hide a touch that reverted
       before the next sample, i.e. a fill we would have liked (or the second leg of a pair), so
       keeping those rounds understates the maker. Primary now allows gaps up to 120 s; the
       gap-free subset is still reported.
    The first run's numbers are kept in the report history for reference.

Run:  python -m research.pm5m_maker
"""

import argparse
import json
import os
import sqlite3
import time
from collections import defaultdict

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "polymarket_sentinel", "round_recorder.db")
OUT = os.path.join(ROOT, "docs", "PM5M_MAKER_RESULTS.md")
ROUND = 300
EPS = 1e-9
MAX_QUOTE_AGE = 3.0
MAX_GAP = 10.0


def quote_prices(bid, ask, improve=False):
    up, down = bid, 1.0 - ask
    if improve and ask - bid >= 0.03 - EPS:
        up, down = up + 0.01, down + 0.01
    return round(up, 3), round(down, 3)


def simulate_round(ts, bid, ask, round_ts, outcome, post_remaining=240, cancel_remaining=15,
                   notional=5.0, shares=None, improve=False, lenient=False, max_gap=MAX_GAP):
    """Fills of the two resting bids in one round, or None when the book data is not usable."""
    T = round_ts + ROUND - post_remaining
    C = round_ts + ROUND - cancel_remaining
    k = int(np.searchsorted(ts, T, side="right")) - 1
    if k < 0 or T - ts[k] > MAX_QUOTE_AGE:
        return None
    window = ts[(ts >= ts[k]) & (ts <= C)]
    edges = np.r_[window, C]
    if len(window) == 0 or np.diff(edges).max() > max_gap:
        return None
    b0, a0 = float(bid[k]), float(ask[k])
    if not (0 < b0 < a0 < 1):
        return None
    p_up, p_dn = quote_prices(b0, a0, improve)
    later = np.flatnonzero((ts > T) & (ts <= C))
    fills = []
    for side, price in (("UP", p_up), ("DOWN", p_dn)):
        if price <= 0:
            continue
        if side == "UP":
            hit = ask[later] <= price + EPS
            if lenient:
                hit |= bid[later] < price - EPS
        else:
            hit = bid[later] >= 1.0 - price - EPS
            if lenient:
                hit |= ask[later] > 1.0 - price + EPS
        if not hit.any():
            continue
        j = later[int(np.argmax(hit))]
        q = shares if shares is not None else notional / price
        won = 1.0 if outcome == side else 0.0
        fills.append({"side": side, "price": price, "shares": q, "fill_ts": float(ts[j]),
                      "pnl": q * (won - price), "won": won})
    return fills


def taker_control(ts, bid, ask, round_ts, outcome, post_remaining, rng, notional=5.0):
    T = round_ts + ROUND - post_remaining
    k = int(np.searchsorted(ts, T, side="right")) - 1
    if k < 0 or T - ts[k] > MAX_QUOTE_AGE:
        return None
    side = "UP" if rng.random() < 0.5 else "DOWN"
    p = float(ask[k]) if side == "UP" else 1.0 - float(bid[k])
    if not 0 < p < 1:
        return None
    q = notional / p
    fee = 0.07 * q * p * (1 - p)
    return q * ((1.0 if outcome == side else 0.0) - p) - fee


# ---------------------------------------------------------------- data & report

def load(db=DB):
    con = sqlite3.connect(db)
    books = {}
    for coin in ("BTC", "ETH", "SOL", "XRP"):
        rows = {}
        for src in ("pm_up_bid", "pm_up_ask"):
            rows[src] = con.execute("SELECT ts, value FROM ticks WHERE coin=? AND source=? ORDER BY ts",
                                    (coin, src)).fetchall()
        bid = dict(rows["pm_up_bid"])
        pairs = [(t, bid[t], a) for t, a in rows["pm_up_ask"] if t in bid]
        if pairs:
            arr = np.array(pairs, dtype=float)
            books[coin] = (arr[:, 0], arr[:, 1], arr[:, 2])
    rounds = []
    for coin, rts, js in con.execute("SELECT coin, round_ts, summary_json FROM rounds"):
        s = json.loads(js)
        if s.get("outcome_official") in ("UP", "DOWN") and coin in books:
            rounds.append((coin, int(rts), s["outcome_official"]))
    return books, sorted(rounds, key=lambda r: (r[1], r[0]))


def run(books, rounds, **kw):
    per_round, fills, used = [], [], 0
    for coin, rts, outcome in rounds:
        ts, b, a = books[coin]
        lo, hi = np.searchsorted(ts, rts - 10), np.searchsorted(ts, rts + ROUND + 5)
        f = simulate_round(ts[lo:hi], b[lo:hi], a[lo:hi], rts, outcome, **kw)
        if f is None:
            continue
        used += 1
        per_round.append(sum(x["pnl"] for x in f))
        for x in f:
            x["coin"] = coin
        fills += f
    return used, np.array(per_round), fills


def boot_ci(x, rng, n=5000):
    if len(x) == 0:
        return (0.0, 0.0)
    s = rng.choice(x, size=(n, len(x)), replace=True).sum(axis=1)
    return float(np.percentile(s, 2.5)), float(np.percentile(s, 97.5))


def describe(name, used, pr, fills, rng):
    tot = pr.sum() if len(pr) else 0.0
    lo, hi = boot_ci(pr, rng)
    n_up = sum(f["side"] == "UP" for f in fills)
    n_dn = len(fills) - n_up
    wins = np.mean([f["won"] for f in fills]) if fills else 0.0
    px = np.mean([f["price"] for f in fills]) if fills else 0.0
    staked = sum(f["shares"] * f["price"] for f in fills)
    return (f"| {name} | {used} | {len(fills)} ({n_up} up / {n_dn} down) | {100 * len(fills) / max(2 * used, 1):.0f}% | "
            f"{100 * wins:.1f}% | {px:.3f} | {100 * (wins - px):+.1f} pts | {tot:+.2f} | "
            f"{100 * tot / staked if staked else 0:+.1f}% | ({lo:+.2f}, {hi:+.2f}) |"), tot, lo


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DB)
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args(argv)
    books, rounds = load(a.db)
    rng = np.random.default_rng(20261123)
    first = time.strftime("%Y-%m-%d %H:%M", time.gmtime(rounds[0][1])) if rounds else "-"
    last = time.strftime("%Y-%m-%d %H:%M", time.gmtime(rounds[-1][1])) if rounds else "-"
    L = []
    say = lambda s="": (print(s), L.append(s))
    say(f"# Polymarket 5m maker backtest ({first} .. {last} UTC)")
    say()
    say(f"Rounds with an official outcome: {len(rounds)} "
        f"({', '.join(f'{c} {sum(r[0] == c for r in rounds)}' for c in books)}). Rules: header of "
        "`research/pm5m_maker.py`. Maker fee 0, rebate counted as 0. P&L in dollars; 10 shares per side "
        "(about 10 dollars of outlay per round).")
    say()
    say("| variant | rounds | fills | fill rate | fills won | avg price | won - price | P&L | per $ | 95% CI |")
    say("|---|---|---|---|---|---|---|---|---|---|")
    base = dict(post_remaining=240, notional=None, shares=10, max_gap=120)
    used, pr, fills = run(books, rounds, **base)
    line, tot, lo = describe("**PRIMARY** post 240s, best prices, strict, gaps <= 120s", used, pr, fills, rng)
    say(line)
    prim = (used, pr, fills, tot, lo)
    for name, kw in (("gap-free rounds only (<= 10s)", dict(max_gap=10)),
                     ("post 180s", dict(post_remaining=180)), ("post 120s", dict(post_remaining=120)),
                     ("post 60s", dict(post_remaining=60)), ("improve 1c", dict(improve=True)),
                     ("lenient fills", dict(lenient=True)),
                     ("first run's design: $5 per side, gap-free", dict(notional=5.0, shares=None, max_gap=10))):
        u, p, f = run(books, rounds, **{**base, **kw})
        say(describe(name, u, p, f, rng)[0])
    say()
    used, pr, fills, tot, lo = prim
    # both-sides and by coin
    by_round = defaultdict(list)
    for f in fills:
        by_round[(f["coin"], int(f["fill_ts"]) // ROUND)].append(f)
    both = [v for v in by_round.values() if len(v) == 2]
    one = [v for v in by_round.values() if len(v) == 1]
    one_lost = [v for v in one if v[0]["won"] == 0]
    say(f"Primary: both sides filled in {len(both)} rounds (P&L {sum(x['pnl'] for v in both for x in v):+.2f}, "
        f"the locked spread); one side only in {len(one)} rounds (P&L {sum(x['pnl'] for v in one for x in v):+.2f}, "
        f"{len(one_lost)} of them lost); no fill in {used - len(both) - len(one)} rounds.")
    say()
    say("By coin (primary): " + " | ".join(
        f"{c} {sum(f['pnl'] for f in fills if f['coin'] == c):+.2f} ({sum(f['coin'] == c for f in fills)} fills)"
        for c in books))
    say()
    ctl = []
    for coin, rts, outcome in rounds:
        ts, b, a_ = books[coin]
        lo_i, hi_i = np.searchsorted(ts, rts - 10), np.searchsorted(ts, rts + ROUND + 5)
        v = taker_control(ts[lo_i:hi_i], b[lo_i:hi_i], a_[lo_i:hi_i], rts, outcome, 240, rng)
        if v is not None:
            ctl.append(v)
    ctl = np.array(ctl)
    clo, chi = boot_ci(ctl, rng)
    say(f"Taker control (random side at the ask, 240s, fee paid): {len(ctl)} trades, P&L {ctl.sum():+.2f} "
        f"({100 * ctl.sum() / (5 * max(len(ctl), 1)):+.1f}% per $), 95% CI ({clo:+.2f}, {chi:+.2f}).")
    say()
    verdict = "PASS" if tot > 0 and lo > 0 else ("INCONCLUSIVE" if tot > 0 else "FAIL")
    say(f"**PASS MARK (primary):** P&L > 0 {tot > 0} ({tot:+.2f}) | 95% CI above 0 {lo > 0} ==> **{verdict}**")
    with open(a.out, "w") as fh:
        fh.write("\n".join(L) + "\n")
    print(f"\nreport written to {a.out}")


if __name__ == "__main__":
    main()
