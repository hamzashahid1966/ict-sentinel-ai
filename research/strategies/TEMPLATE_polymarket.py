"""
TEMPLATE for a Polymarket 5-minute Up/Down strategy. Copy this file, rename it, edit the parts
marked EDIT.

Test it:
    python3 -m research.lab run my_pm_idea --part dev     # iterate freely on the first two thirds
    python3 -m research.lab run my_pm_idea                # final judgement, once

decide(ctx) is called once per round, at the latest saved market price at or before CHECKPOINT
seconds before the close (prices are saved about once a minute, so usually 0-90 s earlier).
You only see candles that had closed by that moment. ctx has:
    ctx.coin            "BTC" "ETH" "SOL" "XRP"
    ctx.p_up            market price of the Up token at that moment (0..1) = the crowd's probability
    ctx.price_to_beat   the round's official start price (Up wins if the close is above it)
    ctx.close, ctx.open, ctx.high, ctx.low, ctx.volume, ctx.buy_volume
                        numpy arrays of the last 240 Binance 1-minute candles that had CLOSED
                        by the decision, oldest first (ctx.close[-1] = most recent)
    ctx.cb_close        Coinbase USD close of the same minutes (NaN where missing): closer to the
                        Chainlink USD settlement price than Binance, which is quoted in USDT
    ctx.secs_left (actual seconds left), ctx.round_ts, ctx.t_decision, ctx.hour (UTC),
    ctx.weekday (0 = Monday)
Return "UP", "DOWN" or None (no bet). Each bet is $1 at the market price + 1c, taker fee, held
to the official result.

Note: rounds settle on Chainlink's USD price. Binance quotes in USDT, which trades slightly off
$1, so ctx.close[-1] / ctx.price_to_beat is biased; ctx.cb_close[-1] / ctx.price_to_beat is the
better estimate of where the round stands (still not exact).
"""

KIND = "polymarket"
NAME = "template_polymarket"                     # EDIT
CHECKPOINT = 120                                 # EDIT: seconds before the close (30..280)
# COINS = ["BTC"]                                # optional; default = BTC ETH SOL XRP
PARAMS = {"min_move": 0.0005, "max_price": 0.70}  # EDIT
HYPOTHESIS = """EDIT: write what should work and why, BEFORE running it."""


def decide(ctx, min_move: float, max_price: float):
    if len(ctx.close) < 3:
        return None
    move = ctx.cb_close[-1] / ctx.price_to_beat - 1       # how far price is from the start price (USD)
    if move > min_move and ctx.p_up < max_price:
        return "UP"
    if move < -min_move and (1 - ctx.p_up) < max_price:
        return "DOWN"
    return None
