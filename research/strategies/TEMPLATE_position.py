"""
TEMPLATE for a position strategy. Copy this file, rename it, edit the parts marked EDIT.

Test it:
    python3 -m research.lab run my_idea --part dev     # iterate freely on the first two thirds
    python3 -m research.lab run my_idea                # final judgement, once

What signal() gets: one coin's candles as a pandas DataFrame with a UTC time index and columns
    o h l c        open, high, low, close
    volume         base-asset volume
    buy_volume     buyer-initiated part of the volume (sell volume = volume - buy_volume)
    funding        funding rate settled during the candle
(With HISTORY = "long" only c and funding are filled.)

What signal() returns: one number per candle, the position to hold AFTER that candle closes:
    +1 fully long, -1 fully short, 0 flat, anything in between = partial. NaN counts as flat.
Use only rolling/past calculations (rolling, ewm, shift(+n)). Never shift(-n), never centered
windows, never the whole-column mean/max: the lab checks this and fails the strategy if the
signal changes when future candles are removed.
"""

import numpy as np
import pandas as pd

KIND = "position"
NAME = "template_position"                       # EDIT: report name
TIMEFRAME = "1h"                                 # EDIT: 1m 5m 15m 1h 4h 1d
HISTORY = ""                                     # "long" (only with 1d) = daily closes back to 2019
# COINS = ["BTC", "ETH"]                         # optional; default = all 12
PARAMS = {"fast": 20, "slow": 100}               # EDIT: anything you may want to vary with --set
HYPOTHESIS = """EDIT: write what should work and why, BEFORE running it."""


def signal(df: pd.DataFrame, fast: int, slow: int) -> pd.Series:
    fast_ma = df.c.rolling(fast).mean()
    slow_ma = df.c.rolling(slow).mean()
    return np.sign(fast_ma - slow_ma)            # +1 when the fast average is above the slow one
