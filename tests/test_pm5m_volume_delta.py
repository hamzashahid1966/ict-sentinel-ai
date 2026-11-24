"""Tests for the Polymarket volume-delta backtest: correct delta, no look-ahead, one trade per market, honest settlement."""

import unittest

import numpy as np

import tests  # noqa: F401
from research import pm5m_volume_delta as vd

T0 = 1_790_000_100 - 1_790_000_100 % 300


def flow(buy_share):
    t = T0 - 600 + 60 * np.arange(len(buy_share))
    qv = np.full(len(buy_share), 1000.0)
    return vd.Flow(t, qv, qv * np.array(buy_share))


class TestVolumeDelta(unittest.TestCase):
    def test_delta_over_the_four_completed_candles_only(self):
        # minutes T0-600 .. ; the 4 completed before T0 are indices 6..9; index 10 (opens at T0) is still forming
        f = flow([0.5] * 6 + [0.7, 0.7, 0.7, 0.7] + [0.0] * 5)
        self.assertAlmostEqual(f.volume_delta(T0), 0.4)

    def test_changing_the_forming_candle_does_not_change_the_signal(self):
        a = flow([0.5] * 6 + [0.6] * 4 + [0.0] + [0.5] * 4)
        b = flow([0.5] * 6 + [0.6] * 4 + [1.0] + [0.5] * 4)
        self.assertEqual(a.volume_delta(T0), b.volume_delta(T0))

    def test_missing_minute_gives_no_signal(self):
        t = T0 - 600 + 60 * np.array([0, 1, 2, 3, 4, 5, 6, 8, 9, 10])
        f = vd.Flow(t, np.full(10, 1000.0), np.full(10, 600.0))
        self.assertIsNone(f.volume_delta(T0))


class TestPricesAndEntries(unittest.TestCase):
    def test_price_at_or_before_and_not_stale(self):
        pts = [(T0 - 50, 0.48), (T0 + 30, 0.55), (T0 + 200, 0.7)]
        self.assertEqual(vd.up_price_at(pts, T0), 0.48)
        self.assertEqual(vd.up_price_at(pts, T0 + 60), 0.55)
        self.assertIsNone(vd.up_price_at(pts, T0 + 150))

    def test_first_qualifying_minute_only_and_gates(self):
        f = flow([0.5] * 6 + [0.5] * 4 + [0.9] * 6)          # VD turns strongly positive later in the round
        pts = [(T0 - 10, 0.50), (T0 + 50, 0.52), (T0 + 110, 0.95), (T0 + 170, 0.60), (T0 + 230, 0.61)]
        e = vd.find_entry(f, T0, pts, quote="before")
        # +60s: last 4 candles = 3x0.5 and 1x0.9 -> VD 0.2 (not > 0.2); +120s: VD 0.4 but ask 0.96 fails the gate; +180s passes
        self.assertEqual(e["offset"], 180)
        self.assertEqual(e["side"], "UP")
        self.assertAlmostEqual(e["ask"], 0.61)

    def test_settlement_with_fee(self):
        shares = 10 / 0.6
        self.assertAlmostEqual(vd.settle("UP", 0.6, "UP"), shares - 10 - shares * 0.07 * 0.6 * 0.4)
        self.assertAlmostEqual(vd.settle("UP", 0.6, "DOWN"), -10 - shares * 0.07 * 0.6 * 0.4)


class TestQuoteAfterSignal(unittest.TestCase):
    def test_after_mode_uses_the_first_price_once_the_signal_is_known(self):
        pts = [(T0 - 56, 0.48), (T0 + 4, 0.58), (T0 + 64, 0.66)]
        self.assertEqual(vd.up_price_after(pts, T0), 0.58)
        self.assertEqual(vd.up_price_at(pts, T0), 0.48)          # the stale one the first run used
        self.assertIsNone(vd.up_price_after([(T0 - 5, 0.5), (T0 + 90, 0.6)], T0))

    def test_default_entry_prices_after_the_signal(self):
        f = flow([0.5] * 6 + [0.8] * 4 + [0.5] * 5)
        e = vd.find_entry(f, T0, [(T0 - 56, 0.40), (T0 + 4, 0.70)])
        self.assertAlmostEqual(e["ask"], 0.71)


if __name__ == "__main__":
    unittest.main()
