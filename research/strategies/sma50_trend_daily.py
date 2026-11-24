"""
Example and sanity check: the daily SMA50 long/short trend strategy (T2 from the slow-strategy
study, now running as a forward paper test), re-run through the lab on daily closes since 2019.
The lab's result should be close to docs/SLOW_STRATEGIES_RESULTS.md (small differences: the lab
uses fixed 1/N weights instead of equal weight across the coins listed so far, and no 60-day
listing delay).
"""

import numpy as np

KIND = "position"
NAME = "sma50_trend_daily"
TIMEFRAME = "1d"
HISTORY = "long"
PARAMS = {"n": 50}
HYPOTHESIS = """Crypto trends persist for weeks: holding the side of the 50-day average earns more
than the trading costs and beats the same trades placed at random times."""


def signal(df, n):
    sma = df.c.rolling(n).mean()
    return np.sign(df.c - sma)
