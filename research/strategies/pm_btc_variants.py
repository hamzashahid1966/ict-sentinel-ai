"""
BTC 5-minute Polymarket prediction: indicator configurations A-H, each tested on its own.

PRE-REGISTERED 2026-11-24, before any run. Conventional settings, nothing fitted.
Market: BTC Up/Down 5-minute rounds, 2026-05-24 .. 2026-11-23 (~52,000 resolved rounds).
Decision: about one minute into the round (CHECKPOINT 240 s before the close), when Up/Down
still trade near 50c, at the latest saved market price, using the Binance 1-minute candles that
had closed by then (the last 240). Bet $1 on the indicated side at the market price + 1c,
taker fee, held to the official result. Judged by the lab's fixed procedure.

Common pieces (1-minute candles):
  trend      = EMA9 > EMA21 -> up, EMA9 < EMA21 -> down   (A uses EMA5 / EMA13)
  VWAP       = volume-weighted typical price of the last 240 minutes
  RSI        = Wilder RSI(14)
  volume_ok  = volume of the last 5 minutes > average 5-minute volume of the last 240 minutes
  CVD        = sum over the last 12 minutes of (taker buy - taker sell) volume
Variants (UP rule shown; DOWN is the mirror; if the rule is not met: no bet):
  A  EMA5 > EMA13                                       (bets every round)
  B  EMA9 > EMA21                                       (bets every round)
  C  B and close > EMA50
  D  B and RSI > 50
  E  B and close > VWAP
  F  E and volume_ok
  G  B and CVD > 0      -- the order-book imbalance part CANNOT be tested: no historical order
                           book exists in the saved data (the live recorder only has it from
                           2026-11-23, ~260 BTC rounds so far)
  H  B and a liquidity sweep with candle confirmation: in the last 15 minutes the low went below
     the lowest low of the 60 minutes before that (sell-side liquidity taken), the last close is
     back above that level, and the last candle is green and closes in the top 40% of its range
Eight variants are tested, so roughly one in twelve chance that at least one clears a single
5% test by luck; the lab's six criteria together are much stricter than one test.
"""

import numpy as np

KIND = "polymarket"
NAME = "pm_btc"
CHECKPOINT = 240
COINS = ["BTC"]
PARAMS = {"variant": "A"}
HYPOTHESIS = """Short-term 1-minute indicator signals predict the direction of the next BTC 5-minute
round better than the ~50c market price implies, by more than the 1c spread and the fee."""


def _ema_last(x, n=None, alpha=None):
    """Last value of the recursive EMA seeded with x[0] (closed form, exact)."""
    a = alpha if alpha is not None else 2 / (n + 1)
    k = np.arange(len(x) - 1)
    return float((a * (1 - a) ** k * x[:0:-1]).sum() + (1 - a) ** (len(x) - 1) * x[0])


def _rsi(c, n=14):
    d = np.diff(c)
    up = _ema_last(np.clip(d, 0, None), alpha=1 / n)
    dn = _ema_last(np.clip(-d, 0, None), alpha=1 / n)
    return 100.0 if dn == 0 else 100 - 100 / (1 + up / dn)


def _side(ok_up, ok_down):
    return "UP" if ok_up else ("DOWN" if ok_down else None)


def decide(ctx, variant):
    c, o, h, l, v, bv = ctx.close, ctx.open, ctx.high, ctx.low, ctx.volume, ctx.buy_volume
    if len(c) < 200:
        return None
    if variant == "A":
        f, s = _ema_last(c, 5), _ema_last(c, 13)
        return _side(f > s, f < s)
    e9, e21 = _ema_last(c, 9), _ema_last(c, 21)
    up, dn = e9 > e21, e9 < e21
    if variant == "B":
        return _side(up, dn)
    if variant == "C":
        e50 = _ema_last(c, 50)
        return _side(up and c[-1] > e50, dn and c[-1] < e50)
    if variant == "D":
        r = _rsi(c)
        return _side(up and r > 50, dn and r < 50)
    if variant in ("E", "F"):
        tp = (h + l + c) / 3
        vwap = (tp * v).sum() / v.sum() if v.sum() > 0 else c[-1]
        if variant == "F" and not v[-5:].sum() > v.mean() * 5:
            return None
        return _side(up and c[-1] > vwap, dn and c[-1] < vwap)
    if variant == "G":
        cvd = (2 * bv[-12:] - v[-12:]).sum()
        return _side(up and cvd > 0, dn and cvd < 0)
    if variant == "H":
        lo_prior, hi_prior = l[-75:-15].min(), h[-75:-15].max()
        rng = h[-1] - l[-1]
        cpos = (c[-1] - l[-1]) / rng if rng > 0 else 0.5
        bull = l[-15:].min() < lo_prior and c[-1] > lo_prior and c[-1] > o[-1] and cpos >= 0.6
        bear = h[-15:].max() > hi_prior and c[-1] < hi_prior and c[-1] < o[-1] and cpos <= 0.4
        return _side(up and bull, dn and bear)
    raise ValueError(f"unknown variant {variant!r}")
