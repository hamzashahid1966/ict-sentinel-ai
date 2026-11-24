"""
The session versions from docs/HOW_TO_PREDICT_NEXT_CANDLE_DIRECTION_ICT_LOGIC.md, on New York time.

PRE-REGISTERED 2026-11-24, before any run. Built from 1h candles (6 months, 12 coins); the
signature classifier is the document's code (see ict_candle_signature.py).

variant "quarterly6h" (Bucko, 6-hour Quarterly Theory sessions):
  The New York day is cut into four 6-hour candles starting 18:00 NY (Asia 18-00, London 00-06,
  NY AM 06-12, NY PM 12-18). At the close of each one, classify it against the previous one and
  hold the call for the whole next 6-hour candle. Inside / other -> no position.
variant "novo3" (Novo Legacy, 3-candle 4H framework):
  Candle 1 = 01:00-05:00 NY, Candle 2 = 05:00-09:00 NY. At 09:00 NY classify Candle 2 against
  Candle 1 (London sweeps Asia and closes back inside -> reversal; closes beyond -> continuation)
  and hold that direction through Candle 3, 09:00-13:00 NY. Flat the rest of the day.
New York time follows daylight saving (America/New_York). A session candle with any hour missing
is skipped. Costs and judgement: the lab's fixed procedure.
"""

import numpy as np
import pandas as pd

from research.strategies.ict_candle_signature import classify

KIND = "position"
NAME = "ict_sessions_ny"
TIMEFRAME = "1h"
PARAMS = {"variant": "novo3"}
HYPOTHESIS = """The closure signature of a session candle (6-hour quarter, or London vs Asia on the
4-hour cycle) predicts the direction of the next session candle well enough to beat costs and
random timing."""


def _session_candles(df, hours, start_hour):
    """Group 1h bars into complete NY-time session candles of `hours` hours whose first hour is
    start_hour (+ k*hours). Returns (label per bar or -1, frame of candles with last-bar positions)."""
    ny = df.index.tz_convert("America/New_York")
    h = ny.hour.values
    k = ((h - start_hour) % 24) // hours                                  # which session of the day
    first = ny - pd.to_timedelta((h - start_hour) % hours, unit="h")      # open of its session
    g = pd.DataFrame({"key": np.asarray(first.asi8), "pos": np.arange(len(df)), "o": df.o.values, "h": df.h.values,
                      "l": df.l.values, "c": df.c.values, "slot": k})
    agg = g.groupby("key", sort=True).agg(n=("pos", "size"), last=("pos", "max"), o=("o", "first"), h=("h", "max"),
                                          l=("l", "min"), c=("c", "last"), slot=("slot", "first"))
    return agg[agg.n == hours]


def signal(df, variant):
    n = len(df)
    s = np.zeros(n)
    if variant == "quarterly6h":
        q = _session_candles(df, 6, 18)
        ph, pl = q.h.shift(1).values, q.l.shift(1).values
        contiguous = (q.index.to_series().diff() == 6 * 3600 * 10**9).values
        sig = classify(ph, pl, q.h.values, q.l.values, q.c.values)
        sig[~contiguous | np.isnan(ph)] = 0
        for last, v in zip(q["last"].values, sig):
            if v:
                s[last:last + 6] = v            # s[i] earns bar i+1 -> the next six hours
        return s
    if variant == "novo3":
        q = _session_candles(df, 4, 1)          # 4h NY candles starting 01:00, 05:00, 09:00, ...
        q = q[q.slot.isin([0, 1])]
        c1 = q[q.slot == 0]
        c2 = q[q.slot == 1]
        c1_by_next = pd.Series(range(len(c1)), index=c1.index + 4 * 3600 * 10**9)
        for key, row in c2.iterrows():
            if key not in c1_by_next.index:
                continue
            a = c1.iloc[c1_by_next[key]]
            v = classify(np.array([a.h]), np.array([a.l]), np.array([row.h]), np.array([row.l]), np.array([row.c]))[0]
            if v:
                last = int(row["last"])
                s[last:last + 4] = v            # holds 09:00-13:00 NY
        return s
    raise ValueError(f"unknown variant {variant!r}")
