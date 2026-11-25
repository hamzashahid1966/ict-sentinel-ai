"""Pre-registered 2026-11-25 ~12:45 UTC, before running. Does the bigger trend tell the next 5-minute round?
Data: Polymarket 5m and 15m BTC rounds (cached). Each bet: $1 at the side's price at the 5m round's
minute 1 (first recorded price after 60 s) + 1c, fee 0.07 p(1-p)/share, held to the result.
  M1  follow the last 5m round: buy the side that won the previous 5m round.
  M2  inside a 15m window: buy the 2nd and 3rd 5m rounds in the direction of the 15m window so far
      (Up if BTC is above the 15m window's open, judged by the 15m market price > 0.5 at that time).
  M3  strong 15m trend: when the 15m market prices one side >= 0.70 at the 5m round's start, buy that
      side on the 5m round.
Control: same bets, coin-flip side. Also the plain hit rate: how often round k+1 = round k."""
import json, numpy as np, sys
sys.path.insert(0, ".")
from research import pm15m as pm
def load(p):
    out = []
    for ln in open(p):
        try:
            r = json.loads(ln)
        except Exception:
            continue
        if not r.get("missing") and len(r.get("up", [])) >= 2:
            out.append(r)
    return {r["start"]: r for r in out}
r5 = load("real_data/pm15m/rounds_5m.jsonl"); r15 = load("real_data/pm15m/rounds.jsonl")
def side_price(r, side, sec=60):
    p = pm.price_at(r["up"], r["start"] + sec)
    if p is None: return None
    return (p if side == "Up" else 1 - p) + pm.SPREAD
bets = {"M1": [], "M2": [], "M3": []}
same, n = 0, 0
for s, r in sorted(r5.items()):
    prev = r5.get(s - 300)
    if prev:
        n += 1; same += prev["winner"] == r["winner"]
        px = side_price(r, prev["winner"])
        if px: bets["M1"].append((s, prev["winner"], px, prev["winner"] == r["winner"]))
    w = s - s % 900
    if w in r15 and s != w:
        p15 = pm.price_at(r15[w]["up"], s)
        if p15 is not None:
            side = "Up" if p15 > 0.5 else "Down"
            px = side_price(r, side)
            if px: bets["M2"].append((s, side, px, side == r["winner"]))
            if max(p15, 1 - p15) >= 0.70:
                if px: bets["M3"].append((s, side, px, side == r["winner"]))
print(f"5m rounds {len(r5)}; next round same direction as previous: {100*same/n:.1f}% of {n}")
for k, b in bets.items():
    if not b: print(k, "no bets"); continue
    pnl = np.array([pm.bet(px, won) for _, _, px, won in b])
    rng = np.random.default_rng(1); ctrl = []
    for _ in range(50):
        t = []
        for s, side, px, won in b:
            flip = rng.random() < 0.5
            cpx = px if not flip else (1 - (px - pm.SPREAD)) + pm.SPREAD
            t.append(pm.bet(cpx, won if not flip else not won))
        ctrl.append(np.mean(t))
    h = len(b) // 2
    print(f"{k}: {len(b)} bets, won {100*np.mean([x[3] for x in b]):.1f}%, avg price {np.mean([x[2] for x in b]):.3f}, "
          f"profit per $1 {pnl.mean():+.4f} (first half {pnl[:h].mean():+.4f}, second half {pnl[h:].mean():+.4f}), "
          f"coin-flip avg {np.mean(ctrl):+.4f} / 95th {np.percentile(ctrl,95):+.4f}")
