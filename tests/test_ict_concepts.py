"""
Tests for the ICT concept harness: each detector finds exactly its defined pattern, none of them
looks ahead, and the trade simulator charges costs and orders fills pessimistically.
"""

import calendar
import unittest

import numpy as np

import tests  # noqa: F401
from research import ict_concepts as ic
from research.crypto_backtest import CoinData

T0 = 1_790_006_400  # 2026-09-21 16:00 UTC, multiple of 3600


def bars5(o, h, l, c, t0=T0):
    b = ic.Bars5.__new__(ic.Bars5)
    n = len(c)
    b.t = t0 + 300 * np.arange(n, dtype=np.int64)
    b.o, b.h, b.l, b.c = map(lambda x: np.array(x, dtype=float), (o, h, l, c))
    b.h1_t = np.array([], dtype=np.int64)
    b.h1_c = np.array([])
    return b


def flat(n, px=100.0, wiggle=0.05):
    c = [px + (wiggle if i % 2 else -wiggle) for i in range(n)]
    o = [px] * n
    return o, [x + 0.1 for x in c], [x - 0.1 for x in c], c


def coin_1m(path, t0=T0):
    """path: list of (o, h, l, c) per minute."""
    a = np.array(path, dtype=float)
    t = t0 + 60 * np.arange(len(a))
    return CoinData("SOLUSDT", t, a[:, 0], a[:, 1], a[:, 2], a[:, 3], np.ones(len(a)))


class TestDetectors(unittest.TestCase):
    def test_bullish_fvg_with_displacement(self):
        o, h, l, c = flat(25)
        # candle i-2 high 100.15; candle i-1 big green impulse; candle i low 101.0 -> gap 100.15..101.0
        o[23], c[23], h[23], l[23] = 100.0, 101.4, 101.5, 99.9
        o[24], c[24], h[24], l[24] = 101.3, 101.6, 101.8, 101.0
        h[22], l[22] = 100.15, 99.6
        s = ic.detect_fvg("SOLUSDT", bars5(o, h, l, c))
        self.assertEqual(len(s), 1)
        self.assertEqual(s[0].direction, "LONG")
        self.assertAlmostEqual(s[0].level, (101.0 + 100.15) / 2)
        self.assertEqual(s[0].stop, 99.6)
        self.assertEqual(s[0].t_signal, T0 + 25 * 300)

    def test_sweep_then_structure_shift(self):
        o, h, l, c = flat(30)
        l[22] = 99.0                        # takes the 20-bar low (99.85)
        c[24], h[24] = 100.4, 100.5         # closes above the 5-bar high before the sweep (100.15)
        s = [x for x in ic.detect_sweep_mss("SOLUSDT", bars5(o, h, l, c)) if x.direction == "LONG"]
        self.assertEqual(len(s), 1)
        self.assertEqual(s[0].stop, 99.0)
        self.assertEqual(s[0].kind, "market")
        self.assertEqual(s[0].t_signal, T0 + 25 * 300)

    def test_smt_trades_the_coin_that_swept(self):
        ob, hb, lb, cb = flat(25)
        oe, he, le, ce = flat(25, px=2000, wiggle=1)
        hb[23] = 100.6                      # BTC takes its 20-bar high, ETH does not
        s = ic.detect_smt(bars5(ob, hb, lb, cb), bars5(oe, he, le, ce))
        shorts = [x for x in s if x.direction == "SHORT"]
        self.assertEqual([(x.symbol, x.stop) for x in shorts], [("BTCUSDT", 100.6)])

    def test_detectors_do_not_look_ahead(self):
        rng = np.random.default_rng(5)
        n = 600
        c = 100 * np.exp(np.cumsum(rng.normal(0, 0.004, n)))
        o = np.r_[c[0], c[:-1]]
        h = np.maximum(o, c) * (1 + np.abs(rng.normal(0, 0.002, n)))
        l = np.minimum(o, c) * (1 - np.abs(rng.normal(0, 0.002, n)))
        full = bars5(o, h, l, c)
        for k in (200, 350, 480):
            part = bars5(o[:k], h[:k], l[:k], c[:k])
            cutoff = int(part.t[-1]) + 300
            for det in (ic.detect_fvg, ic.detect_sweep_mss):
                a = [(x.direction, x.t_signal, x.level, x.stop) for x in det("X", full) if x.t_signal <= cutoff]
                b = [(x.direction, x.t_signal, x.level, x.stop) for x in det("X", part)]
                self.assertEqual(a, b, det.__name__)


class TestSimulator(unittest.TestCase):
    def _setup(self, kind="market", direction="LONG", level=100.0, stop=99.0):
        return ic.Setup("SOLUSDT", "TEST", direction, T0, kind, level, stop, T0 + 3600)

    def test_market_long_hits_2r_target_net_of_costs(self):
        path = [(100.0, 100.5, 99.8, 100.3)] + [(100.3, 102.3, 100.2, 102.2)] + [(102.2, 102.3, 102.0, 102.1)] * 5
        tr = ic.simulate(coin_1m(path), self._setup())
        fill = 100.0 * 1.0002
        risk = fill - 99.0
        target = fill + 2 * risk
        self.assertEqual(tr.reason, "TARGET")
        self.assertAlmostEqual(tr.exit, target)
        self.assertAlmostEqual(tr.gross_r, 2.0)
        self.assertAlmostEqual(tr.net_r, (target - fill - 0.0005 * (fill + target)) / risk)

    def test_stop_checked_before_target_in_one_bar(self):
        path = [(100.0, 103.0, 98.5, 101.0)] + [(101, 101, 101, 101)] * 3
        tr = ic.simulate(coin_1m(path), self._setup())
        self.assertEqual(tr.reason, "STOP")
        self.assertLess(tr.net_r, -1.0)

    def test_limit_fills_only_when_traded_through_and_fill_bar_cannot_reach_target(self):
        s = self._setup(kind="limit", level=100.0, stop=99.0)
        touch_only = [(100.5, 100.6, 100.0, 100.4)] * 5
        self.assertIsNone(ic.simulate(coin_1m(touch_only), s))
        path = [(100.5, 103.0, 99.9, 102.9), (102.9, 103.5, 102.8, 103.4)] + [(103.4, 103.4, 103.3, 103.3)] * 3
        tr = ic.simulate(coin_1m(path), s)
        self.assertEqual(tr.entry, 100.0)
        self.assertEqual(tr.entry_time, T0)
        self.assertEqual(tr.exit_time, T0 + 120)   # target only from the second bar

    def test_time_exit_after_four_hours(self):
        path = [(100.0, 100.2, 99.9, 100.1)] * (4 * 60 + 5)
        tr = ic.simulate(coin_1m(path), self._setup())
        self.assertEqual(tr.reason, "TIME")
        self.assertEqual(tr.exit_time, T0 + 4 * 3600)

    def test_short_mirror(self):
        path = [(100.0, 101.2, 99.9, 101.1)] + [(101, 101, 101, 101)] * 3
        tr = ic.simulate(coin_1m(path), self._setup(direction="SHORT", stop=101.0))
        self.assertEqual(tr.reason, "STOP")
        self.assertAlmostEqual(tr.exit, 101.0 * 1.0002)


class TestSessions(unittest.TestCase):
    def test_killzones_follow_new_york_time_through_daylight_saving(self):
        ts = lambda s: calendar.timegm(__import__("time").strptime(s, "%Y-%m-%d %H:%M"))
        self.assertEqual(ic.session_of(ts("2026-07-15 07:30")), "LONDON_KZ")   # 03:30 EDT
        self.assertEqual(ic.session_of(ts("2026-11-20 08:30")), "LONDON_KZ")   # 03:30 EST
        self.assertEqual(ic.session_of(ts("2026-11-20 13:00")), "NY_KZ")       # 08:00 EST
        self.assertEqual(ic.session_of(ts("2026-11-20 18:00")), "OUTSIDE_KZ")


if __name__ == "__main__":
    unittest.main()
