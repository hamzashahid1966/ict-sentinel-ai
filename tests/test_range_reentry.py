import unittest

import numpy as np

from research import range_reentry as rr

DAY = 1782864000 + 4 * 3600          # 2026-07-01 00:00 New York (EDT) in UTC


def day_bars(path):
    """288 five-minute candles for one New York day; `path(k)` gives (o, h, l, c) for candle k."""
    rows = [[DAY + 300 * k, *path(k)] for k in range(288)]
    return np.array(rows, dtype=float)


class TestRangeReentry(unittest.TestCase):
    def test_failed_breakout_above_is_shorted(self):
        def path(k):
            if k < 48:
                return (100, 101, 99, 100)                  # range 99-101
            if k == 60:
                return (100.5, 102.5, 100.4, 102.0)         # closes above the high
            if k == 61:
                return (102.0, 102.2, 100.0, 100.5)         # closes back inside -> short
            if k > 61:
                return (100.0, 100.1, 90.0, 92.0)           # falls hard: target
            return (100, 100.6, 99.6, 100.2)
        tr = rr.run_coin("X", day_bars(path), "all-day")
        self.assertEqual(len(tr), 1)
        t = tr[0]
        self.assertEqual(t["dir"], -1)
        self.assertEqual(t["why"], "target")
        self.assertAlmostEqual(t["risk"], 102.5 - 100.0 * (1 - rr.SLIP), places=6)  # short sold a bit lower; stop at the breakout high
        self.assertAlmostEqual(t["gross"], 2.0, places=1)

    def test_window_blocks_the_open(self):
        # trigger at 09:35 New York: allowed all-day, blocked by skip-open and off-hours
        k0 = (9 * 60 + 30) // 5
        def path(k):
            if k < 48:
                return (100, 101, 99, 100)
            if k == k0:
                return (100.5, 102.5, 100.4, 102.0)
            if k == k0 + 1:
                return (102.0, 102.2, 100.0, 100.5)
            return (100, 100.6, 99.6, 100.2)
        A = day_bars(path)
        self.assertEqual(len(rr.run_coin("X", A, "all-day")), 1)
        self.assertEqual(len(rr.run_coin("X", A, "skip-open")), 0)
        self.assertEqual(len(rr.run_coin("X", A, "off-hours")), 0)

    def test_wick_outside_does_not_count(self):
        def path(k):
            if k < 48:
                return (100, 101, 99, 100)
            if k == 60:
                return (100.5, 103.0, 100.4, 100.8)         # wick above, close inside
            return (100, 100.6, 99.6, 100.2)
        self.assertEqual(rr.run_coin("X", day_bars(path), "all-day"), [])


if __name__ == "__main__":
    unittest.main()
