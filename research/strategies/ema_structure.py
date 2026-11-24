"""
EMA trend + market structure (higher highs / higher lows), as a slow position strategy.

PRE-REGISTERED 2026-11-24, before any run. Conventional settings, nothing fitted.
  EMA side     close > EMA50 -> bullish, close < EMA50 -> bearish
  Swing points a swing high is a candle whose high is the highest of the 5 candles on each side
               (5 left, 5 right); a swing low is the mirror. A swing is only KNOWN 5 candles later,
               at the close of the 5th candle after it (no look-ahead).
  Structure    bullish = the last known swing high is above the one before it AND the last known
               swing low is above the one before it (higher high + higher low);
               bearish = lower high + lower low; anything else = no clear structure.
Modes (PARAMS "mode"):
  both       long when EMA and structure are both bullish, short when both bearish, else flat  PRIMARY
  structure  structure alone (long bullish, short bearish, else flat)
  ema        EMA side alone (always long or short; the EMA version of T2)
"long_only" = 1 turns every short into flat.
Primary: daily candles since 2019, 12 coins. Secondary: the same rules on 1h candles since 2019
(--timeframe 1h --history long). Costs and judgement: the lab's fixed procedure.
"""

import numpy as np
import pandas as pd

KIND = "position"
NAME = "ema_structure"
TIMEFRAME = "1d"
HISTORY = "long"
PARAMS = {"mode": "both", "ema": 50, "k": 5, "long_only": 0}
HYPOTHESIS = """Holding the side where the EMA trend and the swing structure (HH/HL or LH/LL) agree
captures trends with fewer false flips than either alone, earning more than costs and beating
random timing."""


def structure(h, l, k):
    """+1 bullish (HH+HL), -1 bearish (LH+LL), 0 unclear, using only swings confirmed by bar i."""
    n = len(h)
    s = np.zeros(n)
    hs, ls = [], []                                  # confirmed swing highs / lows (values)
    for i in range(2 * k, n):
        j = i - k                                    # candidate pivot, confirmed at bar i
        win_h, win_l = h[j - k:i + 1], l[j - k:i + 1]
        if h[j] == win_h.max() and np.isfinite(h[j]):
            hs.append(h[j])
        if l[j] == win_l.min() and np.isfinite(l[j]):
            ls.append(l[j])
        if len(hs) >= 2 and len(ls) >= 2:
            if hs[-1] > hs[-2] and ls[-1] > ls[-2]:
                s[i] = 1
            elif hs[-1] < hs[-2] and ls[-1] < ls[-2]:
                s[i] = -1
    return s


def signal(df, mode, ema, k, long_only):
    c = df.c
    e = c.ewm(span=ema, adjust=False, min_periods=ema).mean()
    side = np.sign(c - e).fillna(0).values
    if mode == "ema":
        out = side
    else:
        st = structure(df.h.values, df.l.values, int(k))
        if mode == "structure":
            out = st
        elif mode == "both":
            out = np.where((side > 0) & (st > 0), 1.0, np.where((side < 0) & (st < 0), -1.0, 0.0))
        else:
            raise ValueError(f"unknown mode {mode!r}")
    out = np.asarray(out, dtype=float)
    return np.maximum(out, 0.0) if int(long_only) else out
