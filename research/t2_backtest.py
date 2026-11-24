"""
Trade-by-trade backtest of T2, the strategy running in the forward paper test
(research/trend_paper.py): daily SMA50 long/short on the 12 coins, equal weight across the coins
listed for 60+ days, gross leverage 1, rebalanced daily, 0.07% per side, funding charged.

The portfolio numbers come from research/slow_strategies.py (the same engine as the study that
picked T2). This script adds what that study did not show: the individual trades.
  trade   = one coin held on one side without interruption (a flip closes one and opens another)
  entry   = the close of the day the signal appeared; exit = the close of the day it changed
  result  = side x price change of that coin over the trade, minus 2 x 0.07% costs, minus the
            funding paid (plus funding received), in % of the money put in that coin
Run:  python -m research.t2_backtest [--refresh]     -> docs/T2_BACKTEST.md
"""

import argparse
import os
import time

import numpy as np

from research import slow_strategies as ss

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "T2_BACKTEST.md")
N, COST, CAPITAL = 50, ss.PERP_COST, 1000.0


def day(t):
    return time.strftime("%Y-%m-%d", time.gmtime(int(t)))


def trades(p, sig):
    """Every uninterrupted same-side holding, per coin."""
    out = []
    px = np.vstack([ss._ffill(row) if np.isfinite(row).any() else row for row in p.perp])
    D = len(p.t)
    last_act = int(np.flatnonzero(p.trend_active.any(axis=0))[-1])   # last day a position could be decided
    for i, coin in enumerate(p.coins):
        s = sig[i]
        d = 0
        while d < D - 1:
            if s[d] == 0:
                d += 1
                continue
            a, side = d, s[d]
            while d + 1 < D and s[d + 1] == side:
                d += 1
            b = d                                   # last signal day of this run
            exit_day = min(b + 1, D - 1)            # earns days a+1 .. b+1 (open trades: marked at the last close)
            open_now = b >= last_act                # still held after the last complete day
            entry, exit_ = px[i, a], px[i, exit_day]
            fund = float(p.fund[i, a + 1:exit_day + 1].sum())
            gross = side * (exit_ / entry - 1)
            net = gross - side * fund - (COST if open_now else 2 * COST)
            out.append(dict(coin=coin, side="LONG" if side > 0 else "SHORT", entry_day=day(p.t[a]),
                            exit_day="open" if open_now else day(p.t[exit_day]), days=exit_day - a,
                            entry=entry, exit=exit_, gross=gross, funding=-side * fund, net=net, open=open_now,
                            year=int(day(p.t[a])[:4])))
            d += 1
    return out


def equity_stats(t, rets):
    eq = CAPITAL * np.cumprod(1 + rets)
    peak = np.maximum.accumulate(eq)
    dd = 1 - eq / peak
    k = int(np.argmax(dd))
    pk = int(np.argmax(eq[:k + 1]))
    rec = np.flatnonzero(eq[k:] >= peak[k])
    under, cur = 0, 0
    for x in dd:
        cur = cur + 1 if x > 0 else 0
        under = max(under, cur)
    return eq, dict(max_dd=float(dd[k]), dd_peak=day(t[pk]), dd_trough=day(t[k]),
                    dd_recovered=day(t[k + rec[0]]) if len(rec) else "not yet", longest_underwater_days=under)


def pct(x, d=1):
    return f"{100 * x:+.{d}f}%"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="download the latest daily candles and funding first")
    ap.add_argument("--coins", help="comma list (default: the paper test's 12 coins)")
    a = ap.parse_args(argv)
    coins = [c.strip().upper() for c in a.coins.split(",")] if a.coins else list(ss.COINS)
    raw = {c: ss.load(c, refresh=a.refresh) for c in coins}
    out = OUT if not a.coins else OUT.replace(".md", f"_{'-'.join(coins)}.md")
    p = ss.build_panel(raw)
    sig = ss.panel_signal(p.perp, p.trend_active, N, False)
    bh_sig = np.where(p.trend_active, 1.0, 0.0)
    res = ss.run_trend(p.perp, p.fund, sig, p.trend_active)
    bh = ss.run_trend(p.perp, p.fund, bh_sig, p.trend_active)
    ev = p.t >= ss.EVAL_START
    t, r, rb = p.t[ev], res.returns[ev], bh.returns[ev]
    eq, st = equity_stats(t, r)
    eqb, stb = equity_stats(t, rb)
    tr = trades(p, sig)
    closed = [x for x in tr if not x["open"]]
    wins = [x for x in closed if x["net"] > 0]
    losses = [x for x in closed if x["net"] <= 0]
    years = sorted({int(day(x)[:4]) for x in t})

    L = [f"# T2 backtest, trade by trade ({day(t[0])} .. {day(t[-1])})", "",
         "T2 = the strategy in the forward paper test: once a day, each coin is long above its 50-day average "
         "and short below it; equal money in each listed coin; 0.07% per side; funding charged. "
         f"Generated {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())} by `python -m research.t2_backtest`. "
         "The coin list is chosen today (survivorship bias: coins that died are not in it).", "",
         "## $1,000 over the whole period", "",
         "| | T2 | buy and hold (same coins) |", "|---|---|---|",
         f"| end value | ${eq[-1]:,.0f} | ${eqb[-1]:,.0f} |",
         f"| total | {pct(eq[-1] / CAPITAL - 1, 0)} | {pct(eqb[-1] / CAPITAL - 1, 0)} |",
         f"| worst drop from a peak | -{100 * st['max_dd']:.1f}% ({st['dd_peak']} to {st['dd_trough']}, "
         f"recovered {st['dd_recovered']}) | -{100 * stb['max_dd']:.1f}% ({stb['dd_peak']} to {stb['dd_trough']}) |",
         f"| longest time below a previous peak | {st['longest_underwater_days']} days | {stb['longest_underwater_days']} days |",
         f"| fees paid | {pct(-res.costs[ev].sum())} of capital (simple sum) | {pct(-bh.costs[ev].sum())} |",
         f"| funding | {pct(res.funding[ev].sum())} (simple sum) | {pct(bh.funding[ev].sum())} |", ""]

    L += ["## Each calendar year", "", "| year | T2 | buy and hold | T2 trades opened | T2 win rate |", "|---|---|---|---|---|"]
    for y in years:
        m = np.array([int(day(x)[:4]) == y for x in t])
        ty = [x for x in closed if x["year"] == y]
        wr = f"{100 * np.mean([x['net'] > 0 for x in ty]):.0f}%" if ty else "-"
        L.append(f"| {y} | {pct(np.prod(1 + r[m]) - 1)} | {pct(np.prod(1 + rb[m]) - 1)} | "
                 f"{sum(1 for x in tr if x['year'] == y)} | {wr} |")
    L.append("")

    mon = {}
    for x, v in zip(t, r):
        mon.setdefault(day(x)[:7], []).append(v)
    mret = {k: float(np.prod(1 + np.array(v)) - 1) for k, v in mon.items()}
    best = sorted(mret.items(), key=lambda kv: -kv[1])[:5]
    worst = sorted(mret.items(), key=lambda kv: kv[1])[:5]
    L += ["## Months", "",
          f"Positive months: {sum(v > 0 for v in mret.values())} of {len(mret)}. "
          f"Average month: {pct(np.mean(list(mret.values())))}; median month: {pct(np.median(list(mret.values())))}.", "",
          "Best: " + " | ".join(f"{k} {pct(v)}" for k, v in best),
          "", "Worst: " + " | ".join(f"{k} {pct(v)}" for k, v in worst), ""]

    L += ["## Recent periods (T2 vs buy and hold)", "", "| last | T2 | buy and hold |", "|---|---|---|"]
    for n in (30, 90, 180, 365):
        L.append(f"| {n} days | {pct(np.prod(1 + r[-n:]) - 1)} | {pct(np.prod(1 + rb[-n:]) - 1)} |")
    L.append("")

    nw, nl = len(wins), len(losses)
    aw = np.mean([x["net"] for x in wins]) if wins else 0.0
    al = np.mean([x["net"] for x in losses]) if losses else 0.0
    hold = np.array([x["days"] for x in closed])
    L += ["## The trades", "",
          f"Closed trades: {len(closed)} over {len(years)} years "
          f"(about {len(closed) / (len(t) / 365):.0f} a year across all coins, "
          f"{len(closed) / (len(t) / 365) / len(p.coins):.0f} per coin a year). Still open: {len(tr) - len(closed)}.", "",
          "| | count | share | average result | median days held |", "|---|---|---|---|---|",
          f"| winners | {nw} | {100 * nw / len(closed):.0f}% | {pct(aw)} | {np.median([x['days'] for x in wins]):.0f} |",
          f"| losers | {nl} | {100 * nl / len(closed):.0f}% | {pct(al)} | {np.median([x['days'] for x in losses]):.0f} |",
          f"| all | {len(closed)} | | {pct(np.mean([x['net'] for x in closed]))} | {np.median(hold):.0f} |", "",
          f"An average winner is {abs(aw / al):.1f}x the size of an average loser. "
          f"Trades held 1-3 days: {100 * np.mean(hold <= 3):.0f}%; held 30+ days: {100 * np.mean(hold >= 30):.0f}%.", ""]
    for side in ("LONG", "SHORT"):
        s = [x for x in closed if x["side"] == side]
        L.append(f"- {side}: {len(s)} trades, win rate {100 * np.mean([x['net'] > 0 for x in s]):.0f}%, "
                 f"average {pct(np.mean([x['net'] for x in s]))}")
    L.append("")
    L += ["### Per coin", "", "| coin | trades | win rate | average | best | worst | share of T2's profit |", "|---|---|---|---|---|---|---|"]
    for c in p.coins:
        s = [x for x in closed if x["coin"] == c]
        if not s:
            continue
        L.append(f"| {c} | {len(s)} | {100 * np.mean([x['net'] > 0 for x in s]):.0f}% | {pct(np.mean([x['net'] for x in s]))} | "
                 f"{pct(max(x['net'] for x in s), 0)} | {pct(min(x['net'] for x in s), 0)} | {100 * res.by_coin[p.coins.index(c)] / res.by_coin.sum():.0f}% |")
    L.append("")

    def rows(lst):
        return [f"| {x['coin']} | {x['side']} | {x['entry_day']} | {x['exit_day']} | {x['days']} | "
                f"{x['entry']:g} | {x['exit']:g} | {pct(x['net'])} |" for x in lst]
    head = ["| coin | side | entry | exit | days | entry price | exit price | result |", "|---|---|---|---|---|---|---|---|"]
    L += ["### 10 biggest winners", ""] + head + rows(sorted(closed, key=lambda x: -x["net"])[:10]) + [""]
    L += ["### 10 biggest losers", ""] + head + rows(sorted(closed, key=lambda x: x["net"])[:10]) + [""]
    L += ["### Last 20 closed trades", ""] + head + rows(sorted(closed, key=lambda x: x["exit_day"])[-20:]) + [""]
    L += ["### Open now (marked at the last complete day's close, entry cost only)", ""] + head + rows([x for x in tr if x["open"]]) + [""]

    if a.coins:
        L.insert(2, f"Coins: {', '.join(p.coins)} (not the paper test's 12).")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as f:
        f.write("\n".join(L) + "\n")
    print("\n".join(L))
    print(f"\nReport: {os.path.relpath(out, ROOT)}")


if __name__ == "__main__":
    main()
