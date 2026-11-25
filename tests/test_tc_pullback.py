import unittest

import numpy as np

from research import tc_pullback as tc
from research.ict_mayne import build_htf


def random_walk(n, seed, step=3600, t0=1_700_000_000 // 86400 * 86400):
    rng = np.random.default_rng(seed)
    p = 100 * np.exp(np.cumsum(rng.normal(0, 0.006, n)))
    o = np.r_[p[0], p[:-1]]
    h = np.maximum(o, p) * (1 + rng.uniform(0, 0.004, n))
    l = np.minimum(o, p) * (1 - rng.uniform(0, 0.004, n))
    return np.column_stack([t0 + step * np.arange(n), o, h, l, p])


class TestTcPullback(unittest.TestCase):
    def run_on(self, L):
        gid, *H = build_htf(L, 14400)
        f = dict.fromkeys(("bos2", "tapped", "double", "rr_fail"), 0)
        return tc.run_coin("X", L, gid, H, f), f

    def test_finds_trades_and_no_lookahead(self):
        L = random_walk(24 * 500, 7)
        cut = 24 * 380
        full, f = self.run_on(L)
        part, _ = self.run_on(L[:cut])
        self.assertGreater(f["bos2"], 0)
        self.assertGreater(len(full), 0)
        done = lambda ts: [(x["entry_t"], round(x["net"], 9)) for x in ts if x["exit_t"] < L[cut - 1, 0] and x["why"] != "open"]
        self.assertEqual(done(full), done(part))

    def test_stop_below_both_bottoms_and_target_at_least_2r(self):
        trades, _ = self.run_on(random_walk(24 * 500, 7))
        for x in trades:
            self.assertGreaterEqual(x["rr"], 2.0)
            self.assertGreater(x["risk"], 0)


if __name__ == "__main__":
    unittest.main()
