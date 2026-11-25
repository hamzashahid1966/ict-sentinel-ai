"""
Polymarket 15-minute "Bitcoin Up or Down" rounds: does any simple rule make money after fees?

PRE-REGISTERED 2026-11-25, before any run.
  Data       The last 90 days of 15-minute BTC rounds (btc-updown-15m-<start>), from Polymarket's public
             APIs: the resolved winner (gamma), and the Up price minute by minute (CLOB prices-history,
             last-trade price). Down price = 1 - Up price. BTC itself: Binance BTCUSDT perp 1-minute candles.
  Bet        $1 at the Up/Down price + 1c (spread), taker fee 0.07 * p * (1 - p) per share, held to the
             result (same as the lab's 5-minute Polymarket tests). The price used at minute m is the last
             recorded price at or before round start + m minutes.
  Rules      FAV10  at minute 10, buy the side priced >= 0.50 if its price is 0.55-0.90 (what the live
                    5-minute bot mostly did: buy the favourite late).
             DOG5   at minute 5, buy the cheaper side if its price is 0.10-0.45.
             LAG    each minute 2..13: BTC's move since the round opened, r = ln(close / round open), and
                    1-minute volatility s over the previous 60 minutes give a fair chance of Up,
                    P = Phi(r / (s * sqrt(minutes left))). Buy the side whose fair chance beats its
                    price + 1c by at least 0.05, once per round (tests whether Polymarket lags Binance).
  Control    per rule, 50 runs with the same rounds, minute and prices but the side chosen by coin flip.
  PASS       per rule, all of: (1) mean profit per $1 bet, 95% CI (bootstrap by day) above 0; (2) above
             the 95th percentile of the coin-flip controls; (3) mean > 0 in the last third of the days;
             (4) at least 55% of weeks positive. Three rules, so one pass by luck is possible.
  Also       calibration: at minute 10, how often the side priced X actually won.
Research only: public data, places no orders.

Usage:
  python3 -m research.pm15m --download      # fetch / extend the cache (resumable)
  python3 -m research.pm15m                 # backtest from the cache
"""

import argparse
import json
import math
import os
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "real_data", "pm15m")
ROUNDS = os.path.join(CACHE, "rounds.jsonl")
BTC = os.path.join(CACHE, "btc_1m.json")
OUT = os.path.join(ROOT, "docs", "PM15M_BACKTEST.md")
DAYS, STEP = 90, 900
TF = "15m"
SCAN_MINUTES = (3, 5, 8, 10, 12)


def use_timeframe(tf):
    """Switch the module to the 5-minute rounds (band scan only; the three rules are for 15 minutes)."""
    global ROUNDS, OUT, STEP, TF, SCAN_MINUTES, BTC
    if tf == "5m":
        ROUNDS = os.path.join(CACHE, "rounds_5m.jsonl")
        BTC = os.path.join(CACHE, "btc_1m_5m.json")
        OUT = os.path.join(ROOT, "docs", "PM5M_PRICE_BANDS.md")
        STEP, TF, SCAN_MINUTES = 300, "5m", (1, 2, 3, 4)
SPREAD, FEE = 0.01, 0.07
N_CONTROLS = 50


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "research-lab"})
    for k in range(4):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except Exception:
            if k == 3:
                return None
            time.sleep(2 * (k + 1))


def fetch_round(start):
    ev = _get(f"https://gamma-api.polymarket.com/events?slug=btc-updown-{TF}-{start}")
    if ev is None:                                              # network trouble: not cached, retried later
        return {"start": start, "unresolved": True}
    if not ev:
        return {"start": start, "missing": True}
    m = ev[0]["markets"][0]
    try:
        outcomes = json.loads(m["outcomes"])
        prices = [float(x) for x in json.loads(m["outcomePrices"])]
        tokens = json.loads(m["clobTokenIds"])
    except Exception:
        return {"start": start, "missing": True}
    if not m.get("closed") or max(prices) < 0.99:
        return {"start": start, "missing": True, "unresolved": True}
    up_i = outcomes.index("Up")
    winner = "Up" if prices[up_i] > 0.5 else "Down"
    h = _get(f"https://clob.polymarket.com/prices-history?market={tokens[up_i]}"
             f"&startTs={start}&endTs={start + STEP}&fidelity=1")
    if h is None:
        return {"start": start, "unresolved": True}
    hist = [(int(x["t"]), float(x["p"])) for x in h.get("history", [])]
    return {"start": start, "winner": winner, "up": hist}


def download(days=DAYS, workers=16):
    os.makedirs(CACHE, exist_ok=True)
    have = set()
    if os.path.exists(ROUNDS):
        with open(ROUNDS) as f:
            have = {json.loads(ln)["start"] for ln in f if ln.strip()}
    now = int(time.time())
    last = now - now % STEP - STEP                                  # last round already finished
    todo = [t for t in range(last, last - days * 86400 - 1, -STEP) if t not in have]   # newest first
    print(f"{len(have)} cached, {len(todo)} to fetch", flush=True)
    done = 0
    with ThreadPoolExecutor(workers) as ex, open(ROUNDS, "a") as f:
        for r in ex.map(fetch_round, todo):
            if r.get("unresolved"):
                continue
            f.write(json.dumps(r) + "\n")
            done += 1
            if done % 200 == 0:
                print(done, "rounds", flush=True)
                f.flush()
    # BTC 1-minute candles over the same span (+1 hour for the volatility window)
    rows, t0 = [], (last - days * 86400 - 3600) * 1000
    while True:
        page = _get(f"https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT&interval=1m&startTime={t0}&limit=1500")
        if not page:
            break
        rows += [[int(k[0]) // 1000, float(k[1]), float(k[4])] for k in page]
        if len(page) < 1500:
            break
        t0 = int(page[-1][0]) + 60000
        time.sleep(0.2)
    with open(BTC, "w") as f:
        json.dump(rows, f)
    print("btc 1m candles", len(rows), flush=True)


def price_at(hist, t):
    """Last recorded Up price at or before t, or None."""
    p = None
    for ts, px in hist:
        if ts > t:
            break
        p = px
    return p


def bet(price, won):
    """Profit of a $1 bet bought at `price` (already including the spread)."""
    if not 0.0 < price < 1.0:
        return None
    shares = 1.0 / price
    return shares * won - 1.0 - shares * FEE * price * (1 - price)


def _phi(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def decisions(rounds, btc):
    """Every rule's bets: list of dicts (rule, start, side, price, won)."""
    bt = {t: (o, c) for t, o, c in btc}
    out = []
    for r in rounds:
        s, hist = r["start"], r["up"]
        if len(hist) < 3:
            continue
        up_won = r["winner"] == "Up"
        # FAV10
        p = price_at(hist, s + 600)
        if p is not None:
            side, px = ("Up", p) if p >= 0.5 else ("Down", 1 - p)
            if 0.55 <= px <= 0.90:
                out.append({"rule": "FAV10", "start": s, "p_up": p, "side": side, "won": (side == "Up") == up_won})
        # DOG5
        p = price_at(hist, s + 300)
        if p is not None:
            side, px = ("Up", p) if p < 0.5 else ("Down", 1 - p)
            if 0.10 <= px <= 0.45:
                out.append({"rule": "DOG5", "start": s, "p_up": p, "side": side, "won": (side == "Up") == up_won})
        # LAG
        if s not in bt:
            continue
        open_px = bt[s][0]
        prev = [bt.get(s - 60 * k) for k in range(60, 0, -1)]
        if any(x is None for x in prev):
            continue
        rets = np.diff(np.log([x[1] for x in prev]))
        sig = float(np.std(rets))
        if sig <= 0:
            continue
        for m in range(2, 14):
            cur = bt.get(s + 60 * (m - 1))                          # candle that closed at minute m
            p = price_at(hist, s + 60 * m)
            if cur is None or p is None:
                continue
            fair = _phi(math.log(cur[1] / open_px) / (sig * math.sqrt(15 - m)))
            e_up, e_dn = fair - (p + SPREAD), (1 - fair) - (1 - p + SPREAD)
            if max(e_up, e_dn) >= 0.05:
                side = "Up" if e_up >= e_dn else "Down"
                out.append({"rule": "LAG", "start": s, "p_up": p, "side": side, "won": (side == "Up") == up_won,
                            "minute": m})
                break
    for d in out:
        px = (d["p_up"] if d["side"] == "Up" else 1 - d["p_up"]) + SPREAD
        d["price"] = px
        d["pnl"] = bet(px, d["won"])
    return [d for d in out if d["pnl"] is not None]


def controls(bets, rounds_by_start, n=N_CONTROLS):
    res = []
    for k in range(n):
        rng = np.random.default_rng(500 + k)
        tot = []
        for d in bets:
            side = "Up" if rng.random() < 0.5 else "Down"
            up_won = rounds_by_start[d["start"]]["winner"] == "Up"
            pnl = bet((d["p_up"] if side == "Up" else 1 - d["p_up"]) + SPREAD, (side == "Up") == up_won)
            if pnl is not None:
                tot.append(pnl)
        res.append(float(np.mean(tot)) if tot else 0.0)
    return res


def day_ci(bets, n_boot=2000, seed=0):
    by = {}
    for d in bets:
        by.setdefault(d["start"] // 86400, []).append(d["pnl"])
    g = list(by.values())
    rng = np.random.default_rng(seed)
    m = [np.mean([x for j in rng.integers(0, len(g), len(g)) for x in g[j]]) for _ in range(n_boot)]
    return float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))


def report(rounds, bets):
    by_start = {r["start"]: r for r in rounds}
    span = (min(by_start), max(by_start))
    cut = span[0] + (span[1] - span[0]) * 2 / 3
    up_share = np.mean([r["winner"] == "Up" for r in rounds])
    lines = [f"# Polymarket {TF} BTC rounds: backtest", "",
             f"Generated {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}. Rounds "
             f"{time.strftime('%Y-%m-%d', time.gmtime(span[0]))} to {time.strftime('%Y-%m-%d', time.gmtime(span[1]))}: "
             f"{len(rounds)} resolved, Up won {100 * up_share:.1f}%.",
             "Rules pre-registered in `research/pm15m.py` (2026-11-25) before any run. Each bet: $1 at the price + 1c, "
             "taker fee 0.07*p*(1-p) per share, held to the result.", "",
             "| rule | bets | win % | avg price paid | profit per $1 | 95% CI | coin-flip 95th | last third | weeks + | total on $1 bets | PASS |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for rule in (("FAV10", "DOG5", "LAG") if TF == "15m" else ()):
        b = [d for d in bets if d["rule"] == rule]
        if not b:
            lines.append(f"| {rule} | 0 | | | | | | | | | no |")
            continue
        pnl = np.array([d["pnl"] for d in b])
        lo, hi = day_ci(b)
        c = controls(b, by_start)
        c95 = float(np.percentile(c, 95))
        late = [d["pnl"] for d in b if d["start"] >= cut]
        weeks = {}
        for d in b:
            weeks.setdefault(d["start"] // (7 * 86400), []).append(d["pnl"])
        wpos = float(np.mean([sum(v) > 0 for v in weeks.values()]))
        checks = [lo > 0, pnl.mean() > c95, (np.mean(late) if late else 0) > 0, wpos >= 0.55]
        lines.append(f"| {rule} | {len(b)} | {100 * np.mean([d['won'] for d in b]):.1f}% | "
                     f"{np.mean([d['price'] for d in b]):.3f} | {pnl.mean():+.4f} | {lo:+.4f} to {hi:+.4f} | {c95:+.4f} | "
                     f"{np.mean(late) if late else 0:+.4f} ({len(late)}) | {100 * wpos:.0f}% of {len(weeks)} | "
                     f"{pnl.sum():+.1f} | {'**yes**' if all(checks) else 'no'} |")
    if TF == "15m":
        lines += ["", "## Is the price right? (minute 10)", "",
                  "How often the side priced in each band actually won. If the market is fair, the win rate is close "
                  "to the price; a rule only makes money where the win rate beats price + 1c + fees.", "",
                  "| price of the side | sides | won % |", "|---|---|---|"]
        rows = []
        for r in rounds:
            p = price_at(r["up"], r["start"] + 600)
            if p is None:
                continue
            rows.append((p, r["winner"] == "Up"))
            rows.append((1 - p, r["winner"] == "Down"))
        for a in np.arange(0.0, 1.0, 0.1):
            g = [w for p, w in rows if a <= p < a + 0.1]
            if g:
                lines.append(f"| {a:.1f}-{a + 0.1:.1f} | {len(g)} | {100 * np.mean(g):.1f}% |")
    lines += ["", "## Which entry prices pay? (every band, every minute)", "",
              "Buying the side at that price band at that minute, $1 per round, with spread and fee. This is a "
              "scan of many bands, so some look good by luck: a band counts as consistent only if it has 100+ "
              "bets and made money in BOTH halves of the period.", "",
              "| minute | price band | bets | won % | profit per $1 | first half | second half | consistent |",
              "|---|---|---|---|---|---|---|---|"]
    mid = span[0] + (span[1] - span[0]) / 2
    for m in SCAN_MINUTES:
        rows = []
        for r in rounds:
            p = price_at(r["up"], r["start"] + 60 * m)
            if p is None:
                continue
            for side_p, won in ((p, r["winner"] == "Up"), (1 - p, r["winner"] == "Down")):
                pnl = bet(side_p + SPREAD, won)
                if pnl is not None:
                    rows.append((side_p, won, pnl, r["start"] < mid))
        for a in np.arange(0.05, 0.95, 0.05):
            g = [x for x in rows if a <= x[0] < a + 0.05]
            if len(g) < 30:
                continue
            h1 = [x[2] for x in g if x[3]]
            h2 = [x[2] for x in g if not x[3]]
            ok = len(g) >= 100 and h1 and h2 and np.mean(h1) > 0 and np.mean(h2) > 0
            lines.append(f"| {m} | {a:.2f}-{a + 0.05:.2f} | {len(g)} | {100 * np.mean([x[1] for x in g]):.1f}% | "
                         f"{np.mean([x[2] for x in g]):+.4f} | {np.mean(h1) if h1 else 0:+.4f} | "
                         f"{np.mean(h2) if h2 else 0:+.4f} | {'**yes**' if ok else ''} |")
    lag = [d for d in bets if d["rule"] == "LAG"]
    if lag:
        lines += ["", "## LAG: by minute of entry", "", "| minute | bets | win % | profit per $1 |", "|---|---|---|---|"]
        for m in range(2, 14):
            g = [d for d in lag if d.get("minute") == m]
            if g:
                lines.append(f"| {m} | {len(g)} | {100 * np.mean([d['won'] for d in g]):.0f}% | "
                             f"{np.mean([d['pnl'] for d in g]):+.4f} |")
    return "\n".join(lines) + "\n"


def late_dog_holdout(rounds, before_ts, minute=4, lo=0.25, hi=0.40, n_controls=N_CONTROLS):
    """FOLLOW-UP, PRE-REGISTERED 2026-11-25 12:25 UTC after the 5-minute band scan (2026-11-11..25) showed
    minute-4 underdogs at 0.25-0.40 paying in both halves. Tested ONLY on older rounds that the scan never
    saw (start < before_ts): at minute 4 of a 5-minute round buy the side priced 0.25-0.40, $1, spread + fee.
    PASS = mean profit 95% CI (by day) above 0 and above the coin-flip controls' 95th percentile."""
    bets = []
    for r in rounds:
        if r["start"] >= before_ts:
            continue
        p = price_at(r["up"], r["start"] + 60 * minute)
        if p is None:
            continue
        for side, sp in (("Up", p), ("Down", 1 - p)):
            if lo <= sp < hi:
                won = (side == "Up") == (r["winner"] == "Up")
                bets.append({"start": r["start"], "p_up": p, "side": side, "won": won, "price": sp + SPREAD,
                             "pnl": bet(sp + SPREAD, won)})
    if not bets:
        return None
    by_start = {r["start"]: r for r in rounds}
    c = controls(bets, by_start, n_controls)
    lo_ci, hi_ci = day_ci(bets)
    pnl = np.array([b["pnl"] for b in bets])
    return {"bets": len(bets), "win": float(np.mean([b["won"] for b in bets])), "price": float(np.mean([b["price"] for b in bets])),
            "mean": float(pnl.mean()), "ci": (lo_ci, hi_ci), "c95": float(np.percentile(c, 95)),
            "days": (time.strftime("%Y-%m-%d", time.gmtime(min(b["start"] for b in bets))),
                     time.strftime("%Y-%m-%d", time.gmtime(max(b["start"] for b in bets)))),
            "passed": bool(lo_ci > 0 and pnl.mean() > np.percentile(c, 95))}


def load():
    with open(ROUNDS) as f:
        rounds = [json.loads(ln) for ln in f if ln.strip()]
    rounds = [r for r in rounds if not r.get("missing")]
    with open(BTC) as f:
        btc = json.load(f)
    return rounds, btc


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--download", action="store_true")
    ap.add_argument("--days", type=int, default=DAYS)
    ap.add_argument("--out", default=None)
    ap.add_argument("--tf", default="15m", choices=["15m", "5m"])
    a = ap.parse_args(argv)
    use_timeframe(a.tf)
    a.out = a.out or OUT
    if a.download:
        download(a.days)
        return
    rounds, btc = load()
    bets = decisions(rounds, btc) if TF == "15m" else []
    text = report(rounds, bets)
    with open(a.out, "w") as f:
        f.write(text)
    print(text)


if __name__ == "__main__":
    main()
