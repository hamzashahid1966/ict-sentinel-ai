"""
T2 (daily SMA50 long/short) with an exit that adapts to each trade instead of a fixed %.

PRE-REGISTERED 2026-11-24, before any run. Same entries as T2; a trade also ends early when:
  mode "atr"      trailing stop: the close falls k x ATR(14) below the best close since entry
                  (long; mirror for shorts). ATR = Wilder's 14-day average true range, so the stop
                  is wide for wild coins and tight for calm ones. Tested at k = 3 and k = 5.
  mode "giveback" once the trade has been up at least 1 x ATR(14 at entry), close it if it gives
                  back half of its best open profit (measured at daily closes).
After an early exit, that coin stays flat until the SMA50 side changes; then T2 enters as usual.
mode "none" = plain T2.
"""

import numpy as np
import pandas as pd

KIND = "position"
NAME = "sma50_trailing"
TIMEFRAME = "1d"
HISTORY = "long"
PARAMS = {"n": 50, "mode": "atr", "k": 3.0}
HYPOTHESIS = """An exit that follows each trade (a volatility trailing stop, or giving back half the
open profit) keeps more of the big trends' gains than waiting for the SMA50 flip, with smaller
drops."""


def signal(df, n, mode, k):
    c, h, l = df.c.values, df.h.values, df.l.values
    side = np.nan_to_num(np.sign(c - df.c.rolling(n).mean().values))
    tr = np.maximum(h - l, np.maximum(np.abs(h - np.r_[np.nan, c[:-1]]), np.abs(l - np.r_[np.nan, c[:-1]])))
    atr = pd.Series(tr).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean().values
    out = np.zeros(len(c))
    cur, locked = 0.0, 0.0
    entry = best = atr_e = np.nan
    for i in range(len(c)):
        s = side[i]
        if locked and s != locked:
            locked = 0.0
        if cur != 0 and s != cur:
            cur = 0.0
        if cur == 0 and s != 0 and s != locked and np.isfinite(atr[i]):
            cur, entry, best, atr_e = s, c[i], c[i], atr[i]
        if cur != 0 and mode != "none":
            best = max(best, c[i]) if cur > 0 else min(best, c[i])
            exit_ = False
            if mode == "atr":
                exit_ = cur * (best - c[i]) >= k * atr[i]
            elif mode == "giveback":
                peak = cur * (best - entry)
                exit_ = peak >= atr_e and cur * (c[i] - entry) <= 0.5 * peak
            else:
                raise ValueError(f"unknown mode {mode!r}")
            if exit_:
                locked, cur = cur, 0.0
        out[i] = cur
    return out
