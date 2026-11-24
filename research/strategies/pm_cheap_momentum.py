"""
Example Polymarket strategy: back the side the price is already moving toward, but only while
the market still prices it cheaply.
"""

KIND = "polymarket"
NAME = "pm_cheap_momentum"
CHECKPOINT = 120
PARAMS = {"min_move": 0.0005, "max_price": 0.70}
HYPOTHESIS = """With two minutes left, if the USD price (Coinbase) is already 0.05% past the start price, the market
underprices that side when it still costs under 70c."""


def decide(ctx, min_move, max_price):
    if len(ctx.cb_close) < 3 or not ctx.price_to_beat > 0 or not ctx.cb_close[-1] > 0:
        return None
    move = ctx.cb_close[-1] / ctx.price_to_beat - 1      # Coinbase USD: closest to the Chainlink settlement
    if move > min_move and ctx.p_up + 0.01 < max_price:
        return "UP"
    if move < -min_move and (1 - ctx.p_up) + 0.01 < max_price:
        return "DOWN"
    return None
