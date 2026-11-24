"""
The "predict the next candle" closure signatures (docs/HOW_TO_PREDICT_NEXT_CANDLE_DIRECTION_ICT_LOGIC.md,
section 5.1) applied to Polymarket 5-minute Up/Down rounds.

PRE-REGISTERED 2026-11-24, before any run. At the start of each round, classify the 5-minute
candle that just closed (ending exactly at the round start) against the one before it, with the
document's code: bearish reversal or bearish continuation -> bet DOWN; bullish reversal or bullish
continuation -> bet UP; inside / other -> no bet. The round IS the next 5-minute candle.
Price: the Polymarket price seen about one minute in (CHECKPOINT 240 s before the close, as for
the EMA tests) + 1c spread, taker fee, held to the official result. If that price was seen before
the signal candle had closed, the round is skipped. Coins: BTC, ETH, SOL, XRP.
"""

import numpy as np

from research.strategies.ict_candle_signature import classify
from research.strategies.pm_reverse_ema import five_minute

KIND = "polymarket"
NAME = "pm_candle_signature"
CHECKPOINT = 240
LOOKBACK = 30                # 1m candles: enough for the last two complete 5-minute candles
PARAMS = {}
HYPOTHESIS = """The closure signature of the 5-minute candle that just closed predicts the next
5-minute round better than the ~50c Polymarket price implies, by more than the spread and fee."""


def decide(ctx):
    if len(ctx.t) < 10:
        return None
    t5, o, h, l, c, v = five_minute(ctx.t, ctx.open, ctx.high, ctx.low, ctx.close, ctx.volume)
    if len(t5) < 2 or t5[-1] + 300 != ctx.round_ts or t5[-2] + 300 != t5[-1]:
        return None
    s = classify(h[-2:-1], l[-2:-1], h[-1:], l[-1:], c[-1:])[0]
    return "UP" if s > 0 else ("DOWN" if s < 0 else None)
