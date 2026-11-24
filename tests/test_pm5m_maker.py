"""
Tests for the Polymarket maker (resting limit order) backtest: orders are priced from the book at
the posting time only, fill only when the market trades through to them before the cancel time,
the Down side is mapped from the Up book correctly, and P&L settles on the official outcome.
"""

import unittest

import numpy as np

import tests  # noqa: F401
from research import pm5m_maker as mk

R = 1_795_449_000          # round start (multiple of 300)
END = R + 300


def book(points):
    """points: list of (seconds_from_round_start, bid, ask) for the Up token."""
    ts = np.array([R + p[0] for p in points], dtype=float)
    return ts, np.array([p[1] for p in points]), np.array([p[2] for p in points])


def steady(bid, ask, until=290, step=2):
    return [(s, bid, ask) for s in range(0, until + 1, step)]


class TestFills(unittest.TestCase):
    def test_up_bid_fills_only_when_the_ask_comes_down_to_it(self):
        pts = steady(0.50, 0.52, until=100) + [(102, 0.47, 0.50)] + steady(0.40, 0.42, until=290)[52:]
        ts, b, a = book(pts)
        fills = mk.simulate_round(ts, b, a, R, "DOWN", post_remaining=240)
        up = [f for f in fills if f["side"] == "UP"]
        self.assertEqual(len(up), 1)
        self.assertEqual(up[0]["price"], 0.50)
        self.assertEqual(up[0]["fill_ts"], R + 102)
        self.assertAlmostEqual(up[0]["pnl"], (5 / 0.50) * (0 - 0.50))

    def test_no_fill_without_a_touch_and_touches_after_cancel_ignored(self):
        pts = steady(0.50, 0.52, until=286) + [(288, 0.45, 0.48), (290, 0.45, 0.48)]
        ts, b, a = book(pts)
        fills = mk.simulate_round(ts, b, a, R, "UP", post_remaining=240, cancel_remaining=15)
        self.assertEqual([f for f in fills if f["side"] == "UP"], [])

    def test_down_bid_is_one_minus_up_ask_and_fills_when_up_bid_reaches_it(self):
        pts = steady(0.50, 0.52, until=100) + [(102, 0.52, 0.54)] + steady(0.60, 0.62, until=290)[52:]
        ts, b, a = book(pts)
        fills = mk.simulate_round(ts, b, a, R, "UP", post_remaining=240)
        down = [f for f in fills if f["side"] == "DOWN"]
        self.assertEqual(len(down), 1)
        self.assertAlmostEqual(down[0]["price"], 0.48)
        self.assertAlmostEqual(down[0]["pnl"], (5 / 0.48) * (0 - 0.48))

    def test_both_sides_filled_lock_the_spread(self):
        pts = (steady(0.50, 0.52, until=100) + [(102, 0.47, 0.50)] + [(104, 0.52, 0.55)]
               + steady(0.51, 0.53, until=290)[53:])
        ts, b, a = book(pts)
        for outcome in ("UP", "DOWN"):
            fills = mk.simulate_round(ts, b, a, R, outcome, post_remaining=240, notional=None, shares=10)
            self.assertEqual({f["side"] for f in fills}, {"UP", "DOWN"})
            self.assertAlmostEqual(sum(f["pnl"] for f in fills), 10 * (1 - 0.50 - 0.48))

    def test_improve_adds_a_tick_only_when_the_spread_allows(self):
        ts, b, a = book(steady(0.50, 0.53))
        self.assertEqual(mk.quote_prices(0.50, 0.53, improve=True), (0.51, 0.48))
        self.assertEqual(mk.quote_prices(0.50, 0.51, improve=True), (0.50, 0.49))
        self.assertEqual(mk.quote_prices(0.50, 0.53, improve=False), (0.50, 0.47))

    def test_quote_uses_only_book_samples_up_to_the_post_time(self):
        pts = steady(0.50, 0.52, until=58) + steady(0.70, 0.72, until=290)[31:]
        ts, b, a = book(pts)
        fills_a = mk.simulate_round(ts, b, a, R, "UP", post_remaining=240)
        # the quote is taken at second 60 from the last sample at or before it (second 58: 0.50/0.52)
        self.assertEqual([f["price"] for f in fills_a if f["side"] == "DOWN"], [0.48])

    def test_round_with_a_data_gap_is_skipped(self):
        pts = steady(0.50, 0.52, until=100) + steady(0.50, 0.52, until=290)[70:]   # 40s hole
        ts, b, a = book(pts)
        self.assertIsNone(mk.simulate_round(ts, b, a, R, "UP", post_remaining=240))

    def test_lenient_rule_also_fills_when_the_bid_drops_below(self):
        pts = steady(0.50, 0.52, until=100) + [(102, 0.49, 0.51)] + steady(0.49, 0.51, until=290)[52:]
        ts, b, a = book(pts)
        strict = mk.simulate_round(ts, b, a, R, "UP", post_remaining=240)
        lenient = mk.simulate_round(ts, b, a, R, "UP", post_remaining=240, lenient=True)
        self.assertEqual([f for f in strict if f["side"] == "UP"], [])
        self.assertEqual(len([f for f in lenient if f["side"] == "UP"]), 1)


if __name__ == "__main__":
    unittest.main()
