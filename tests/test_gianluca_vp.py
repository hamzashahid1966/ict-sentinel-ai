import unittest

import numpy as np

from research import gianluca_vp as g


class TestPieces(unittest.TestCase):
    def test_valid_candle(self):
        self.assertTrue(g.is_valid(100, 106, 99, 105))          # body 5 > wicks 1, 1
        self.assertFalse(g.is_valid(100, 110, 99, 102))         # upper wick 8 > body 2

    def test_value_area_holds_poc(self):
        h = np.array([101, 101, 101, 101, 110.0])
        l = np.array([100, 100, 100, 100, 100.0])
        v = np.array([10, 10, 10, 10, 1.0])
        vah, poc, val = g.value_area(h, l, v)
        self.assertTrue(val <= poc <= vah)
        self.assertLess(vah, 102)                               # volume sits in 100-101

    def test_sessions_follow_new_york_time(self):
        # 2026-07-01 (EDT, UTC-4): 09:30 NY = 13:30 UTC; 2026-01-05 (EST, UTC-5): 09:30 NY = 14:30 UTC
        for day, open_utc in ((1782864000, 13.5), (1767571200, 14.5)):
            t = day + np.arange(0, 86400, 900)
            (a, b, _), = g.sessions(t)
            self.assertAlmostEqual((t[a] - day) / 3600, open_utc)
            self.assertEqual(b - a, 26)                         # 6.5 hours of 15-minute candles

    def test_simulate_target_and_session_close(self):
        lo = np.array([99.5, 100.0, 100.5]); hi = np.array([101.0, 103.0, 104.5]); cl = np.array([100.5, 102.0, 104.0])
        net, gross, ex, why = g.simulate(lo, hi, cl, cl, 0, 2, 100.0, 98.0, 104.0)
        self.assertEqual((why, ex), ("target", 2))
        net, gross, ex, why = g.simulate(lo, hi, cl, cl, 0, 1, 100.0, 98.0, 104.0)
        self.assertEqual(why, "close")

    def test_no_lookahead(self):
        rng = np.random.default_rng(5)
        n = 96 * 120
        t0 = 1767225600                                         # 2026-01-01 00:00 UTC
        p = 100 * np.exp(np.cumsum(rng.normal(0, 0.003, n)))
        o = np.r_[p[0], p[:-1]]
        h = np.maximum(o, p) * (1 + rng.uniform(0, 0.002, n))
        l = np.minimum(o, p) * (1 - rng.uniform(0, 0.002, n))
        v = rng.uniform(50, 150, n)
        A = np.column_stack([t0 + 900 * np.arange(n), o, h, l, p, v])
        cut = 96 * 90
        full = [(x["entry_t"], round(x["net"], 9)) for x in g.run_coin("X", A) if x["entry_t"] < A[cut - 1, 0] - 86400]
        part = [(x["entry_t"], round(x["net"], 9)) for x in g.run_coin("X", A[:cut]) if x["entry_t"] < A[cut - 1, 0] - 86400]
        self.assertTrue(len(full) > 0)
        self.assertEqual(full, part)


if __name__ == "__main__":
    unittest.main()
