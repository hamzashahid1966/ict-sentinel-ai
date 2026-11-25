import unittest

import numpy as np

from research import ict_mayne as m


def bars(rows, step=3600, t0=1_700_000_000 // 86400 * 86400):
    """rows of (o, h, l, c) -> array (t, o, h, l, c)."""
    return np.array([[t0 + i * step, *r] for i, r in enumerate(rows)], dtype=float)


class TestSimulate(unittest.TestCase):
    def setUp(self):
        self.lo = np.array([99.0, 99.5, 101.0, 103.0])
        self.hi = np.array([101.0, 102.5, 104.0, 106.5])
        self.cl = np.array([100.0, 102.0, 103.5, 106.0])

    def test_half_at_2r_then_target(self):
        net, gross, ex, why = m.simulate(self.lo, self.hi, self.cl, 0, 100.0, 98.0, 104.0, 106.0, False)
        self.assertEqual(why, "target")
        self.assertEqual(ex, 3)
        self.assertAlmostEqual(gross, 0.5 * 2 + 0.5 * 3)       # half at 2R, half at 3R
        self.assertLess(net, gross)                             # fees cost something

    def test_stop_checked_first(self):
        lo = np.array([97.0]); hi = np.array([110.0]); cl = np.array([100.0])
        net, gross, ex, why = m.simulate(lo, hi, cl, 0, 100.0, 98.0, 104.0, 106.0, False)
        self.assertEqual(why, "stop")
        self.assertAlmostEqual(gross, -1.0)

    def test_short_side_via_signing(self):
        o, h, l, c = m.signed(np.array([100.0]), np.array([101.0]), np.array([95.0]), np.array([96.0]), -1)
        self.assertEqual((h[0], l[0]), (-95.0, -101.0))         # a short's "high" is the real low


class TestPoi(unittest.TestCase):
    def test_fvg_in_discount_is_chosen(self):
        # leg from 100 up to 200 with a gap between candle 1's high (120) and candle 3's low (125)
        o = np.array([101, 110, 122, 126, 160, 190.0])
        h = np.array([105, 120, 130, 150, 185, 200.0])
        l = np.array([100, 108, 121, 125, 158, 188.0])
        c = np.array([104, 119, 128, 148, 182, 198.0])
        z = m.find_poi((o, h, l, c), 0, 5, 5, 100.0, 200.0)
        self.assertIsNotNone(z)
        self.assertLessEqual(z[1], 150.0)                       # in discount

    def test_no_zone_when_touched(self):
        o = np.array([101, 110, 122, 126, 160, 190.0, 150])
        h = np.array([105, 120, 130, 150, 185, 200.0, 190])
        l = np.array([100, 108, 121, 125, 158, 188.0, 100.5])  # later candle ran through every zone
        c = np.array([104, 119, 128, 148, 182, 198.0, 120])
        self.assertIsNone(m.find_poi((o, h, l, c), 0, 5, 6, 100.0, 200.0))


class TestHtf(unittest.TestCase):
    def test_daily_groups_from_hours(self):
        L = bars([(1, 2, 0.5, 1.5)] * 48)
        gid, o, h, l, c = m.build_htf(L, 86400)
        self.assertEqual(len(o), 2)
        self.assertEqual(gid[23], 0)
        self.assertEqual(gid[24], 1)

    def test_no_lookahead(self):
        """Trades found on a prefix of the data are the same trades found on the full data."""
        rng = np.random.default_rng(3)
        p = 100 * np.exp(np.cumsum(rng.normal(0, 0.006, 24 * 400)))
        o = np.r_[p[0], p[:-1]]
        h = np.maximum(o, p) * (1 + rng.uniform(0, 0.004, len(p)))
        l = np.minimum(o, p) * (1 - rng.uniform(0, 0.004, len(p)))
        L = bars(list(zip(o, h, l, p)))
        cut = 24 * 300
        def run(arr):
            gid, *H = m.build_htf(arr, 86400)
            f = dict.fromkeys(("msb", "armed", "tapped", "trigger", "rr_fail", "limit_missed"), 0)
            return m.run_coin("X", arr, gid, H, "market", f)
        full = [t for t in run(L) if t["exit_t"] < L[cut - 1, 0] and t["why"] != "open"]
        part = [t for t in run(L[:cut]) if t["why"] != "open"]
        self.assertTrue(len(full) > 0)
        self.assertEqual([(t["entry_t"], round(t["net"], 9)) for t in full],
                         [(t["entry_t"], round(t["net"], 9)) for t in part if t["exit_t"] < L[cut - 1, 0]])


if __name__ == "__main__":
    unittest.main()
