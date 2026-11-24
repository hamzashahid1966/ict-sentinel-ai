"""
"Predict the next candle" closure signatures (Bucko Trades, as written up in
docs/HOW_TO_PREDICT_NEXT_CANDLE_DIRECTION_ICT_LOGIC.md, section 5.1), as a position strategy.

PRE-REGISTERED 2026-11-24, before any run. The classifier is the document's own code, unchanged:
  took a high, closed back below it                  -> bearish reversal  -> SHORT the next candle
  took a low, closed back above it                   -> bullish reversal  -> LONG the next candle
  took the high and closed above it                  -> bullish continuation -> LONG
  took the low and closed below it                   -> bearish continuation -> SHORT
  inside candle / anything else                      -> no position ("never trade the inside candle")
The checks run in the document's order (so an outside candle that closes below the previous low
counts as a bearish reversal, exactly as its code does). The position is held for exactly the next
candle and re-decided at its close. The video claims about 80% of next candles follow the call.
Primary: daily candles since 2019 (UTC days), 12 coins. Secondary: 4h and 1h (6 months of data).
Costs and judgement: the lab's fixed procedure.
"""

import numpy as np

KIND = "position"
NAME = "ict_candle_signature"
TIMEFRAME = "1d"
HISTORY = "long"
PARAMS = {}
HYPOTHESIS = """A candle that sweeps the previous candle's high/low and closes back inside predicts a
reversal on the next candle; one that closes beyond it predicts continuation. Following the call
earns more than costs and beats random timing."""


def classify(ph, pl, h, l, c):
    """The document's classify_candle_signature, vectorised. +1 long, -1 short, 0 none."""
    took_high, took_low = h > ph, l < pl
    closed_above_high, closed_below_low = c > ph, c < pl
    out = np.zeros(len(c))
    done = np.zeros(len(c), bool)
    for cond, val in ((took_high & ~closed_above_high & (c < ph), -1),     # bearish reversal
                      (took_low & ~closed_below_low & (c > pl), 1),        # bullish reversal
                      (took_high & closed_above_high, 1),                  # bullish continuation
                      (took_low & closed_below_low, -1)):                  # bearish continuation
        hit = cond & ~done
        out[hit] = val
        done |= hit
    return out


def signal(df):
    h, l, c = df.h.values, df.l.values, df.c.values
    ph, pl = np.r_[np.nan, h[:-1]], np.r_[np.nan, l[:-1]]
    s = classify(ph, pl, h, l, c)
    s[np.isnan(ph) | np.isnan(h) | np.isnan(c)] = 0
    return s
