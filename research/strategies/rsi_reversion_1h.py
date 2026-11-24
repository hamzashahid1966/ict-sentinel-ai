"""
Example: hourly RSI mean reversion. Buy when RSI(14) is oversold, short when overbought,
get out when it crosses back through 50.
"""

import numpy as np
import pandas as pd

KIND = "position"
NAME = "rsi_reversion_1h"
TIMEFRAME = "1h"
PARAMS = {"n": 14, "low": 30, "high": 70}
HYPOTHESIS = """Hourly overshoots revert: after RSI(14) goes below 30 (above 70) price tends to
bounce (fall back) by more than the round-trip cost of 0.14%."""


def rsi(close: pd.Series, n: int) -> pd.Series:
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn)


def signal(df, n, low, high):
    r = rsi(df.c, n).values
    pos = np.zeros(len(r))
    cur = 0.0
    for i, x in enumerate(r):
        if np.isnan(x):
            cur = 0.0
        elif x < low:
            cur = 1.0
        elif x > high:
            cur = -1.0
        elif (cur > 0 and x >= 50) or (cur < 0 and x <= 50):
            cur = 0.0
        pos[i] = cur
    return pos
