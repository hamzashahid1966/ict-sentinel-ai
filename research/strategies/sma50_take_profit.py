"""
T2 (daily SMA50 long/short) with a take-profit: lock the gain once a trade is up enough.

PRE-REGISTERED 2026-11-24, before any run. Same rule as sma50_trend_daily.py (T2), plus:
  when a position's gain since entry, at a daily close, reaches tp (e.g. +20%), close it and stay
  out of that coin until the SMA50 side changes; then enter the new side as usual.
tp = 0 means no take-profit (plain T2). Tested at 0.10, 0.20, 0.30.
"""

import numpy as np

KIND = "position"
NAME = "sma50_take_profit"
TIMEFRAME = "1d"
HISTORY = "long"
PARAMS = {"n": 50, "tp": 0.20}
HYPOTHESIS = """Locking in a trade's profit once it reaches tp keeps more of the gains than holding
until the trend flips."""


def signal(df, n, tp):
    c = df.c.values
    side = np.sign(c - df.c.rolling(n).mean().values)
    side = np.nan_to_num(side)
    out = np.zeros(len(c))
    cur, entry, locked = 0.0, np.nan, 0.0          # locked = the side we took profit on
    for i in range(len(c)):
        s = side[i]
        if locked and s != locked:
            locked = 0.0                            # the trend changed: allowed in again
        if cur != 0 and s != cur:
            cur = 0.0                               # normal exit / flip
        if cur == 0 and s != 0 and s != locked:
            cur, entry = s, c[i]
        if cur != 0 and tp > 0 and cur * (c[i] / entry - 1) >= tp:
            locked, cur = cur, 0.0                  # take profit at this close
        out[i] = cur
    return out
