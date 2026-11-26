"""
Polymarket 5-minute BTC: does taking profit later (or not stopping out) change the result?

PRE-REGISTERED 2026-11-25 ~12:50 UTC, before running. Data: the round recorder's Polymarket best bid/ask
(every few seconds) for live 5-minute BTC rounds since 2026-11-23, winner = outcome_official.
Entry (like the live bot's "late yield harvest"): the first moment 30-120 s into a round when the
favourite's ask is 0.70-0.80; buy $5 at that ask. Selling uses the best bid (Down bid = 1 - Up ask).
Fee 0.07 * p * (1 - p) per share on every buy and sell. Exits compared on the SAME entries:
  BOT     the live bot's paper rules: sell when bid >= 0.88, or gain >= 6c, or bid >= 0.84; after 45 s a
          4c gain, after 90 s a 2c gain, after 120 s any gain, in the last 45 s any gain; stop when the
          price <= 0.50; otherwise hold to the result
  HOLD    hold every trade to the result
  TP95    sell only when the bid reaches 0.95, else hold; no stop
  STOP50  no take-profit; stop at 0.50; else hold
Research only: reads the recorder database, places no orders.
"""
import bisect
import json
import sqlite3

import numpy as np

FEE = 0.07
DB = "file:polymarket_sentinel/round_recorder.db?mode=ro"


def fee(p, shares):
    return shares * FEE * p * (1 - p)


def main():
    db = sqlite3.connect(DB, uri=True)
    def series(src):
        rows = db.execute("select ts, value from ticks where coin='BTC' and source=? order by ts", (src,)).fetchall()
        return [r[0] for r in rows], [r[1] for r in rows]
    at, av = series("pm_up_ask")
    bt, bv = series("pm_up_bid")
    rounds = [(r, json.loads(s)) for r, s in db.execute("select round_ts, summary_json from rounds where coin='BTC'")]
    rounds = sorted((r, s["outcome_official"]) for r, s in rounds
                    if r >= at[0] + 60 and s.get("outcome_official") in ("UP", "DOWN"))
    results = {k: [] for k in ("BOT", "HOLD", "TP95", "STOP50")}
    for r, winner in rounds:
        i0, i1 = bisect.bisect_left(at, r + 30), bisect.bisect_left(at, r + 120)
        entry = None
        for i in range(i0, i1):
            j = bisect.bisect_right(bt, at[i]) - 1
            if j < 0:
                continue
            up_ask, up_bid = av[i], bv[j]
            for side, ask in (("UP", up_ask), ("DOWN", 1 - up_bid)):
                if 0.70 <= ask <= 0.80:
                    entry = (at[i], side, ask)
                    break
            if entry:
                break
        if not entry:
            continue
        t0, side, px = entry
        shares = 5.0 / px
        cost = 5.0 + fee(px, shares)
        won = side == winner
        # path of (time, sell price = bid of our side, mid of our side)
        path = []
        k0, k1 = bisect.bisect_right(bt, t0), bisect.bisect_left(bt, r + 300)
        for k in range(k0, k1):
            m = bisect.bisect_right(at, bt[k]) - 1
            ub, ua = bv[k], av[m]
            bid = ub if side == "UP" else 1 - ua
            mid = (ub + ua) / 2 if side == "UP" else 1 - (ub + ua) / 2
            path.append((bt[k], bid, mid))
        def settle():
            return shares * (1.0 if won else 0.0) - cost
        def sell(bid):
            return shares * bid - fee(bid, shares) - cost
        # BOT
        out = None
        for t, bid, mid in path:
            age, rem, gain = t - t0, r + 300 - t, max(mid, bid) - px
            prof = gain >= 0.005
            if max(mid, bid) >= 0.88 or (prof and (gain >= 0.06 or max(mid, bid) >= 0.84)) \
                    or (age >= 45 and gain >= 0.04) or (age >= 90 and gain >= 0.02) \
                    or (age >= 120 and prof) or (rem <= 45 and prof):
                out = sell(bid if bid > px else mid)
                break
            if mid <= 0.50:
                out = sell(mid)
                break
        results["BOT"].append(settle() if out is None else out)
        results["HOLD"].append(settle())
        out = next((sell(bid) for t, bid, mid in path if bid >= 0.95), None)
        results["TP95"].append(settle() if out is None else out)
        out = next((sell(mid) for t, bid, mid in path if mid <= 0.50), None)
        results["STOP50"].append(settle() if out is None else out)
    n = len(results["HOLD"])
    print(f"{n} trades (entries 30-120 s in, favourite at 0.70-0.80), $5 each")
    for k, v in results.items():
        v = np.array(v)
        wins, losses = v[v > 0], v[v <= 0]
        print(f"{k:7s} total {v.sum():+8.2f}  per trade {v.mean():+.3f}  won {100 * len(wins) / n:4.1f}%  "
              f"avg win {wins.mean() if len(wins) else 0:+.2f}  avg loss {losses.mean() if len(losses) else 0:+.2f}")


if __name__ == "__main__":
    main()
