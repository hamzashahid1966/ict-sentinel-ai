"""
ChatGPT's "Reverse EMA + Volume + ATR + EMA distance" rule, tested on real Polymarket BTC 5-minute rounds.

PRE-REGISTERED 2026-11-24, before any run on Polymarket data. The rules are copied as ChatGPT
stated them (shared chat, 2026-11-24); nothing is changed or fitted here. ChatGPT reported
61.9% on Aug-Oct 2026 Binance BTC/USDT 5m candles (126 signals) and 51.4% on November (35).

On 5-minute candles (UTC buckets, which line up with the Polymarket rounds), at the close of the
candle that ends exactly when the round starts:
  UP   : EMA9 crosses below EMA21 on this candle (it was >= on the previous candle)
         and close < EMA50
         and volume > the average volume of the previous 20 candles
         and ATR(14) > the median ATR of the previous 288 candles (24 hours)
         and EMA50 - close > 1 x ATR
  DOWN : the mirror (EMA9 crosses above EMA21, close > EMA50, close - EMA50 > 1 x ATR, same filters)
  otherwise: no bet.
EMAs are the usual recursive ones (alpha 2/(n+1)); ATR is Wilder's (alpha 1/14) of the true range.
The bet is $1 on the predicted side at the Polymarket price seen about one minute into the round
(CHECKPOINT 240 s before the close, the same as configs A-H) + 1c spread, taker fee, held to the
official result. If that price was seen before the signal candle had closed, the round is
skipped: the signal could not have been known yet.
"""

import numpy as np
from scipy.signal import lfilter

KIND = "polymarket"
NAME = "pm_reverse_ema"
CHECKPOINT = 240
LOOKBACK = 3000              # 1m candles = 600 five-minute candles: 288-candle ATR median plus warm-up
COINS = ["BTC"]
PARAMS = {}
HYPOTHESIS = """After a high-volume, high-volatility EMA9/21 cross that leaves price more than one ATR
beyond EMA50, the next 5-minute candle reverses more often than the ~50c Polymarket price implies,
by more than the spread and fee."""


def _ema(x, alpha):
    """Recursive EMA seeded with x[0]: y[0] = x[0], y[i] = a*x[i] + (1-a)*y[i-1]."""
    y, _ = lfilter([alpha], [1, alpha - 1], x[1:], zi=[(1 - alpha) * x[0]])
    return np.r_[x[0], y]


def signals(o, h, l, c, v, start=300):
    """+1 = predict UP, -1 = predict DOWN, 0 = no signal, for each 5-minute candle from `start` on."""
    n = len(c)
    out = np.zeros(n)
    if n < 300:
        return out
    e9, e21, e50 = _ema(c, 2 / 10), _ema(c, 2 / 22), _ema(c, 2 / 51)
    tr = np.r_[h[0] - l[0], np.maximum(h[1:] - l[1:], np.maximum(np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])))]
    atr = _ema(tr, 1 / 14)
    for i in range(max(start, 300), n):
        vol_ok = v[i] > v[i - 20:i].mean()
        atr_ok = atr[i] > np.median(atr[i - 288:i])
        if not (vol_ok and atr_ok):
            continue
        cross_dn = e9[i - 1] >= e21[i - 1] and e9[i] < e21[i]
        cross_up = e9[i - 1] <= e21[i - 1] and e9[i] > e21[i]
        if cross_dn and c[i] < e50[i] and e50[i] - c[i] > atr[i]:
            out[i] = 1
        elif cross_up and c[i] > e50[i] and c[i] - e50[i] > atr[i]:
            out[i] = -1
    return out


def five_minute(t, o, h, l, c, v):
    """Complete UTC 5-minute candles (all five 1m candles present) from 1m arrays."""
    b = (t // 300).astype(np.int64)
    starts = np.r_[0, np.flatnonzero(np.diff(b)) + 1]
    ends = np.r_[starts[1:], len(b)]
    full = (ends - starts) == 5
    s, e = starts[full], ends[full]
    return (b[s] * 300, o[s], np.maximum.reduceat(h, starts)[full], np.minimum.reduceat(l, starts)[full],
            c[e - 1], np.add.reduceat(v, starts)[full])


def decide(ctx):
    if len(ctx.t) < 1600:
        return None
    t5, o, h, l, c, v = five_minute(ctx.t, ctx.open, ctx.high, ctx.low, ctx.close, ctx.volume)
    if len(t5) < 300 or t5[-1] + 300 != ctx.round_ts:     # the signal candle must end exactly at the round start
        return None
    s = signals(o, h, l, c, v, start=len(c) - 1)[-1]      # only the signal candle; earlier ones warm the indicators
    return "UP" if s > 0 else ("DOWN" if s < 0 else None)
