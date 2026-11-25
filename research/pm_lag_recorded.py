"""LAG on recorded executable prices (pre-registered 2026-11-25 ~12:35 UTC, before running):
5-minute BTC rounds recorded since 2026-11-23. Each second-level snapshot from 30 s to 270 s into the
round: fair P(Up) = Phi(ln(binance_now / binance_round_open) / (sigma_1m * sqrt(minutes left))), sigma_1m
from Binance 1-minute closes over the previous 60 minutes. Buy Up at the recorded best ask if
fair - ask >= 0.05, or Down at (1 - best Up bid) if (1 - fair) - that >= 0.05; first signal per round.
Fill = the first recorded ask at least `delay` seconds after the signal (2 s and 5 s tested), must still
show edge >= 0.0 there, else skip. Fee 0.07*p*(1-p)/share. Winner = outcome_official. Control: coin flip."""
import bisect, json, math, sqlite3, sys
import numpy as np
sys.path.insert(0, ".")
from research import pm15m as pm

db = sqlite3.connect("file:polymarket_sentinel/round_recorder.db?mode=ro", uri=True)
def series(src):
    rows = db.execute("select ts, value from ticks where coin='BTC' and source=? order by ts", (src,)).fetchall()
    return [r[0] for r in rows], [r[1] for r in rows]
bt_t, bt_v = series("binance"); ask_t, ask_v = series("pm_up_ask"); bid_t, bid_v = series("pm_up_bid")
def at(ts_list, vals, t):
    i = bisect.bisect_right(ts_list, t) - 1
    return (ts_list[i], vals[i]) if i >= 0 else (None, None)
def first_after(ts_list, vals, t):
    i = bisect.bisect_left(ts_list, t)
    return (ts_list[i], vals[i]) if i < len(ts_list) else (None, None)
k1m = {int(t): c for t, o, c in json.load(open("real_data/pm15m/btc_1m_5m.json"))}
rounds = [(r, json.loads(s)) for r, s in db.execute("select round_ts, summary_json from rounds where coin='BTC' order by round_ts")]
rounds = [(r, s) for r, s in rounds if r >= ask_t[0] + 60 and s.get("outcome_official") in ("UP", "DOWN")]

def run(delay, thr=0.05):
    out = []
    for r, s in rounds:
        prev = [k1m.get(r - 60 * k) for k in range(61, 0, -1)]
        if any(x is None for x in prev): continue
        sig = float(np.std(np.diff(np.log(prev))))
        _, o = at(bt_t, bt_v, r)
        if not o or sig <= 0: continue
        for sec in range(30, 271, 2):
            t = r + sec
            tb, b = at(bt_t, bt_v, t); ta, a = at(ask_t, ask_v, t); tq, q = at(bid_t, bid_v, t)
            if None in (tb, ta, tq) or t - tb > 10 or t - ta > 10: continue
            fair = pm._phi(math.log(b / o) / (sig * math.sqrt((300 - sec) / 60)))
            eu, ed = fair - a, (1 - fair) - (1 - q)
            if max(eu, ed) < thr: continue
            side = "UP" if eu >= ed else "DOWN"
            # fill after the delay at the then-current price
            if side == "UP":
                tf, px = first_after(ask_t, ask_v, t + delay)
            else:
                tf, bq = first_after(bid_t, bid_v, t + delay); px = None if bq is None else 1 - bq
            if px is None or tf - t > delay + 10 or not 0 < px < 1: break
            won = side == s["outcome_official"]
            out.append((r, side, px, pm.bet(px, won), won))
            break
    return out

for delay in (2, 5):
    res = run(delay)
    pnl = np.array([x[3] for x in res])
    rng = np.random.default_rng(0); ctrl = []
    outcome = {r: s["outcome_official"] for r, s in rounds}
    for k in range(50):
        tot = []
        for r, side, px, _, _ in res:
            cs = "UP" if rng.random() < 0.5 else "DOWN"
            cpx = px if cs == side else 1 - px + 0.01
            tot.append(pm.bet(min(max(cpx, 0.01), 0.99), cs == outcome[r]))
        ctrl.append(np.mean(tot))
    days = {}
    for x in res: days.setdefault(x[0] // 86400, []).append(x[3])
    print(f"delay {delay}s: {len(res)} bets of {len(rounds)} rounds | win {100*np.mean([x[4] for x in res]):.1f}% | avg price {np.mean([x[2] for x in res]):.3f} | profit per $1 {pnl.mean():+.4f} | per day {[round(float(np.mean(v)),3) for v in days.values()]} | coin-flip 95th {np.percentile(ctrl,95):+.4f}")
