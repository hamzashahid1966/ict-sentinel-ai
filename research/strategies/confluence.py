"""
Multi-indicator confluence strategy (the user's list), as a position strategy on Binance perps.

PRE-REGISTERED 2026-11-24, before any run. Parameters are the conventional defaults, not fitted.
Primary: 5m candles, all 12 coins. Secondary: the same rules on 15m and 1h (--timeframe).

LONG entry at the close of a candle when ALL of these hold (SHORT = the exact mirror):
  1. EMA 9 and 21   momentum      EMA9 > EMA21
  2. EMA 50         trend         close > EMA50
  3. VWAP           positioning   close > VWAP (session VWAP, resets 00:00 UTC, typical price)
  4. Order flow     pressure      this candle's delta > 0 (taker buy - taker sell volume)
     and CVD                      and the sum of delta over the last 12 candles > 0
  5. Candle         structure     close in the top 40% of the candle's range (strong close or
                                  lower-wick rejection; the bottom 40% for shorts)
  6. Volume         strength      volume > 1.2 x the average of the previous 20 candles
  7. Volatility     strength      ATR(14)/close above its median of the last 100 candles
  -  Liquidity imbalance (order book): NOT TESTED. There is no historical Binance order book in
     the saved data, so this filter is left out.
EXIT: the close crosses back through EMA21 (long: close < EMA21), a full opposite signal
(flip), or after 12 candles, whichever comes first.
Costs and judgement: the lab's fixed procedure (0.07% per side, funding, 200 random-timing
controls, holdout, look-ahead check).
"""

import numpy as np
import pandas as pd

KIND = "position"
NAME = "confluence"
TIMEFRAME = "5m"
PARAMS = {"cvd_n": 12, "vol_mult": 1.2, "max_hold": 12}
HYPOTHESIS = """When momentum (EMA9>21), trend (EMA50), VWAP side, order flow and CVD, a strong
candle close, above-average volume and above-median volatility all agree, price continues in
that direction long enough to beat the 0.14% round-trip cost."""


def ema(x: pd.Series, n: int) -> pd.Series:
    return x.ewm(span=n, adjust=False, min_periods=n).mean()


def conditions(df: pd.DataFrame, cvd_n: int, vol_mult: float):
    c, h, l, o, v = df.c, df.h, df.l, df.o, df.volume
    e9, e21, e50 = ema(c, 9), ema(c, 21), ema(c, 50)
    tp = (h + l + c) / 3
    day = df.index.floor("D")
    vwap = (tp * v).groupby(day).cumsum() / v.groupby(day).cumsum()
    delta = 2 * df.buy_volume - v
    cvd = delta.rolling(cvd_n).sum()
    rng = (h - l).replace(0, np.nan)
    cpos = (c - l) / rng
    vol_ok = v > vol_mult * v.shift(1).rolling(20).mean()
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atrp = tr.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean() / c
    volat_ok = atrp > atrp.rolling(100).median()
    strength = vol_ok & volat_ok
    long_ = (e9 > e21) & (c > e50) & (c > vwap) & (delta > 0) & (cvd > 0) & (cpos >= 0.6) & strength
    short = (e9 < e21) & (c < e50) & (c < vwap) & (delta < 0) & (cvd < 0) & (cpos <= 0.4) & strength
    return long_.values, short.values, c.values, e21.values


def signal(df, cvd_n, vol_mult, max_hold):
    long_, short, c, e21 = conditions(df, cvd_n, vol_mult)
    pos = np.zeros(len(df))
    cur, held = 0.0, 0
    for i in range(len(df)):
        if cur != 0:
            held += 1
            against = (cur > 0 and c[i] < e21[i]) or (cur < 0 and c[i] > e21[i])
            if against or held >= max_hold:
                cur, held = 0.0, 0
        if long_[i] and cur <= 0:
            cur, held = 1.0, 0
        elif short[i] and cur >= 0:
            cur, held = -1.0, 0
        pos[i] = cur
    return pos
