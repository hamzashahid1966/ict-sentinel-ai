"""
EMA 9/21 used the slow way: as a trend follower that always holds the side of the cross,
like the daily SMA50 rule that works, instead of predicting the next 5 minutes.

PRE-REGISTERED 2026-11-24, before any run. Conventional 9/21, nothing fitted.
Rule: at each candle close, long if EMA9 > EMA21, short if EMA9 < EMA21; hold until it flips.
Primary: daily candles since 2019 (all 12 coins). Secondary: the same rule on 4h and 1h
(--timeframe), which only have the ~6 months of saved 1-minute data.
"""

import numpy as np

KIND = "position"
NAME = "ema_cross_trend"
TIMEFRAME = "1d"
HISTORY = "long"
PARAMS = {"fast": 9, "slow": 21}
HYPOTHESIS = """Holding the side of the EMA9/21 cross captures multi-day crypto trends and earns
more than the trading costs, beating the same trades placed at random times."""


def signal(df, fast, slow):
    f = df.c.ewm(span=fast, adjust=False, min_periods=slow).mean()
    s = df.c.ewm(span=slow, adjust=False, min_periods=slow).mean()
    return np.sign(f - s).fillna(0)
