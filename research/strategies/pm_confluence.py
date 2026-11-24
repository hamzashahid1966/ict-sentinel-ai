"""
The same confluence rules applied to Polymarket 5-minute Up/Down rounds.

PRE-REGISTERED 2026-11-24, before any run. Decision about one minute into the round (CHECKPOINT
240 s before the close), when the market still prices Up and Down near 50c, using the Binance
1-minute candles that had closed by then.

Bet UP when ALL hold (DOWN = mirror), on 1-minute candles:
  EMA9 > EMA21; close > EMA50; close > VWAP of the last 240 minutes (ctx holds 240 candles, so
  a rolling VWAP replaces the session VWAP); last minute's delta > 0 and the sum of delta over
  the last 12 minutes > 0; last candle closes in the top 40% of its range; volume of the last
  5 minutes > 1.2 x the 240-minute average per 5 minutes; ATR(14) above its 240-minute median.
Liquidity imbalance: not tested (no historical order book).
Price paid: the market price + 1c, taker fee, held to the official result.
"""

import numpy as np

KIND = "polymarket"
NAME = "pm_confluence"
CHECKPOINT = 240
PARAMS = {"cvd_n": 12, "vol_mult": 1.2}
HYPOTHESIS = """At the start of a round, when the 1-minute momentum, trend, VWAP side, order flow,
candle close, volume and volatility all agree, that side wins more often than its ~50c price
implies, by more than the spread and fee."""


def _ema_last(x, n):
    """Last value of the recursive EMA seeded with x[0], computed in closed form (fast)."""
    a = 2 / (n + 1)
    k = np.arange(len(x) - 1)
    return float((a * (1 - a) ** k * x[:0:-1]).sum() + (1 - a) ** (len(x) - 1) * x[0])


def decide(ctx, cvd_n, vol_mult):
    c, h, l, v, bv = ctx.close, ctx.high, ctx.low, ctx.volume, ctx.buy_volume
    if len(c) < 200:
        return None
    vol_ok = v[-5:].sum() > vol_mult * v.mean() * 5
    tr = np.maximum(h[1:] - l[1:], np.maximum(np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])))
    atr = np.convolve(tr, np.ones(14) / 14, mode="valid")
    volat_ok = atr[-1] > np.median(atr)
    if not (vol_ok and volat_ok):
        return None
    delta = 2 * bv - v
    cvd = delta[-cvd_n:].sum()
    rng = h[-1] - l[-1]
    cpos = (c[-1] - l[-1]) / rng if rng > 0 else 0.5
    tp = (h + l + c) / 3
    vwap = (tp * v).sum() / v.sum() if v.sum() > 0 else c[-1]
    e9, e21, e50 = _ema_last(c, 9), _ema_last(c, 21), _ema_last(c, 50)
    if e9 > e21 and c[-1] > e50 and c[-1] > vwap and delta[-1] > 0 and cvd > 0 and cpos >= 0.6:
        return "UP"
    if e9 < e21 and c[-1] < e50 and c[-1] < vwap and delta[-1] < 0 and cvd < 0 and cpos <= 0.4:
        return "DOWN"
    return None
