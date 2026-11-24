"""
Tests for the slow-strategy harness (daily trend following and delta-neutral funding carry):
signals never look ahead, funding is charged to the right day with the right sign, and costs
are charged on every change of position.
"""

import unittest

import numpy as np

import tests  # noqa: F401
from research import slow_strategies as ss

DAY = 86400
T0 = 1_704_067_200  # 2024-01-01 00:00 UTC


def days(n):
    return T0 + DAY * np.arange(n, dtype=np.int64)


class TestFunding(unittest.TestCase):
    def test_settlements_map_to_the_day_they_are_earned(self):
        t = days(3)
        # settlements at 08:00, 16:00 of day 0 and 00:00 of day 1 belong to holding day 0
        f_t = np.array([T0 + 8 * 3600, T0 + 16 * 3600, T0 + DAY, T0 + DAY + 8 * 3600], dtype=np.int64)
        f_r = np.array([0.001, 0.002, 0.003, 0.004])
        out = ss.funding_per_day(t, f_t, f_r)
        np.testing.assert_allclose(out, [0.006, 0.004, 0.0])

    def test_long_pays_positive_funding_short_receives(self):
        close = np.array([[100.0, 100.0, 100.0]])
        fund = np.array([[0.0, 0.01, 0.0]])
        active = np.ones_like(close, dtype=bool)
        long_ = ss.run_trend(close, fund, np.ones_like(close), active, cost=0.0)
        short = ss.run_trend(close, fund, -np.ones_like(close), active, cost=0.0)
        self.assertAlmostEqual(long_.returns[1], -0.01)
        self.assertAlmostEqual(short.returns[1], +0.01)


class TestTrend(unittest.TestCase):
    def test_signal_uses_only_closes_up_to_the_decision_day(self):
        rng = np.random.default_rng(3)
        c = 100 * np.exp(np.cumsum(rng.normal(0, 0.03, 300)))
        s = ss.trend_signal(c, 20, long_only=False)
        for k in (50, 150, 250):
            c2 = c.copy()
            c2[k + 1:] *= rng.uniform(0.2, 5.0, len(c2) - k - 1)
            self.assertTrue(np.array_equal(ss.trend_signal(c2, 20, False)[:k + 1], s[:k + 1]))

    def test_signal_flat_during_warmup_and_long_only_never_short(self):
        c = np.r_[np.linspace(100, 50, 40), np.linspace(50, 120, 40)]
        s = ss.trend_signal(c, 20, long_only=True)
        self.assertTrue((s[:19] == 0).all())
        self.assertTrue(set(np.unique(s)) <= {0.0, 1.0})
        self.assertEqual(s[-1], 1.0)
        self.assertEqual(ss.trend_signal(c, 20, long_only=False)[30], -1.0)

    def test_position_earns_next_day_return_and_pays_cost_on_flip(self):
        close = np.array([[100.0, 110.0, 99.0, 99.0]])
        sig = np.array([[1.0, -1.0, -1.0, -1.0]])
        active = np.ones_like(close, dtype=bool)
        r = ss.run_trend(close, np.zeros_like(close), sig, active, cost=0.001)
        # day 1: long from close 0 -> +10%, entry cost 0.001 charged at close 0
        self.assertAlmostEqual(r.returns[1], 0.10 - 0.001)
        # day 2: flipped to short at close 1 (turnover 2 on a drifted weight of 1) -> -(-10%) = +10%
        self.assertAlmostEqual(r.returns[2], 0.10 - 0.002)

    def test_equal_weight_across_active_coins(self):
        close = np.array([[100.0, 110.0], [100.0, 90.0]])
        sig = np.ones_like(close)
        active = np.ones_like(close, dtype=bool)
        r = ss.run_trend(close, np.zeros_like(close), sig, active, cost=0.0)
        self.assertAlmostEqual(r.returns[1], 0.0)

    def test_random_control_keeps_flip_count(self):
        sig = np.array([0, 0, 1, 1, -1, -1, -1, 1, 1, 1], dtype=float)
        active = np.r_[np.zeros(2, bool), np.ones(8, bool)]
        rng = np.random.default_rng(1)
        for _ in range(20):
            r = ss.random_like(sig, active, rng)
            self.assertEqual(ss.flips(r[active]), ss.flips(sig[active]))
            self.assertTrue((r[~active] == 0).all())


class TestCarry(unittest.TestCase):
    def test_carry_earns_funding_and_basis_and_pays_four_legs(self):
        # one coin, entry when 3-day annualised funding > 10%
        n = 8
        perp = np.full((1, n), 100.0)
        spot = np.full((1, n), 100.0)
        fund = np.full((1, n), 0.0009)          # 0.09%/day = 32.85%/yr -> in trade
        spot[0, 5], perp[0, 5] = 101.0, 100.5    # basis move day 5: spot +1%, perp +0.5%
        active = np.ones((1, n), bool)
        r = ss.run_carry(spot, perp, fund, active, enter=0.10, exit_=0.0, slot_frac=0.75)
        held = r.held[0]
        self.assertFalse(held[:2].any())         # needs 3 days of funding first
        self.assertTrue(held[2:-1].all())
        # day 4: decision at close 2 held -> funding 0.0009 on 0.75 notional
        self.assertAlmostEqual(r.returns[4], 0.75 * 0.0009)
        self.assertAlmostEqual(r.returns[5], 0.75 * (0.01 - 0.005 + 0.0009))
        # entry cost charged on the first held day: four legs 0.0012 + 0.0007
        self.assertAlmostEqual(r.returns[3], 0.75 * (0.0009 - 0.0019))

    def test_carry_exits_when_funding_turns_negative(self):
        n = 10
        fund = np.r_[np.full(4, 0.001), np.full(6, -0.001)][None, :]
        ones = np.full((1, n), 100.0)
        r = ss.run_carry(ones, ones, fund, np.ones((1, n), bool), enter=0.10, exit_=0.0, slot_frac=1.0)
        # held[d] = in the trade after the decision at close d.
        # entered at close 2; the 3-day average goes below zero at close 5 -> flat after it
        self.assertTrue(r.held[0, 2:5].all())
        self.assertFalse(r.held[0, 5:].any())


if __name__ == "__main__":
    unittest.main()
