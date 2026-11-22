"""
Tests for the gold London-model backtester's fill and exit simulator.
The simulator is deliberately conservative: a bar that touches both the stop and
the target is counted as a stop.
"""

import datetime
import unittest

from ict_sentinel.config import NY_TZ
from ict_sentinel.models import Candle
from ict_sentinel.ipda_engine import AlgorithmicSignal
from ict_sentinel.gold_backtest import BacktestConfig, simulate_trade, RegimeGate


def _bar(ts_utc, o, h, l, c):
    return Candle(timestamp=ts_utc, timestamp_et=ts_utc.astimezone(NY_TZ), open=o, high=h, low=l, close=c, volume=1.0)


def _bars(start_utc, ohlc):
    return [_bar(start_utc + datetime.timedelta(minutes=5 * i), *x) for i, x in enumerate(ohlc)]


def _long_signal():
    return AlgorithmicSignal(asset="GOLD", session="LONDON_CORE", direction="LONG", entry_price=3000.0,
                             stop_loss=2996.0, risk_pts=4.0, target_center_mass=3006.4, target_head_shot=3010.0,
                             pd_array=None, ai_rationale="t")


T0 = datetime.datetime(2026, 2, 10, 9, 0, tzinfo=datetime.timezone.utc)  # 04:00 EST, inside London Core


class TestFixedTargetExit(unittest.TestCase):
    def test_entry_next_open_with_slippage_and_target_fill(self):
        cfg = BacktestConfig(exit_model="fixed_1_6r", friction_pts=0.30, slippage_pts=0.10, equity=10000.0, risk_pct=0.5)
        bars = _bars(T0, [(3000.0, 3001.0, 2999.0, 3000.5), (3000.5, 3003.0, 3000.0, 3002.0), (3002.0, 3008.0, 3001.5, 3007.0)])
        r = simulate_trade(_long_signal(), bars, cfg, units=10.0)
        self.assertAlmostEqual(r.entry_price, 3000.6)          # next bar open (3000.5) + slippage
        self.assertEqual(r.outcome, "TARGET")
        self.assertAlmostEqual(r.exit_price, 3000.6 + 1.6 * 4.0)  # 1.6R from the filled entry, stop distance from signal
        self.assertAlmostEqual(r.pnl_pts, 6.4 - 0.30)
        self.assertAlmostEqual(r.dollar_pnl, (6.4 - 0.30) * 10.0)
        self.assertAlmostEqual(r.r_multiple, (6.4 - 0.30) / 4.0)

    def test_stop_counts_first_when_bar_touches_both(self):
        cfg = BacktestConfig(exit_model="fixed_1_6r")
        bars = _bars(T0, [(3000.0, 3001.0, 2999.0, 3000.5), (3000.5, 3010.0, 2990.0, 3005.0)])
        r = simulate_trade(_long_signal(), bars, cfg, units=10.0)
        self.assertEqual(r.outcome, "STOP")
        self.assertAlmostEqual(r.exit_price, 2996.0 - 0.10)   # stop filled with adverse slippage


class TestProductionSingleContractExit(unittest.TestCase):
    def test_breakeven_shield_after_1r_then_reversal(self):
        cfg = BacktestConfig(exit_model="production", friction_pts=0.30, slippage_pts=0.10)
        # bar 1: fills entry 3000.6; bar 2: reaches +1R (3004.6) -> stop moves to BE + buffer; bar 3: reverses to the shield
        bars = _bars(T0, [(3000.0, 3001.0, 2999.0, 3000.5), (3000.5, 3005.0, 3000.2, 3004.5), (3004.5, 3004.8, 2999.0, 3000.0)])
        r = simulate_trade(_long_signal(), bars, cfg, units=10.0)
        self.assertEqual(r.outcome, "DEFENSIVE_STOP")
        self.assertGreater(r.exit_price, 3000.6)               # shield sits above the filled entry
        self.assertLess(r.pnl_pts, 1.0)

    def test_full_target_is_two_r(self):
        cfg = BacktestConfig(exit_model="production")
        bars = _bars(T0, [(3000.0, 3001.0, 2999.0, 3000.5), (3000.5, 3012.0, 3000.2, 3011.0)])
        r = simulate_trade(_long_signal(), bars, cfg, units=10.0)
        self.assertEqual(r.outcome, "TARGET")
        self.assertAlmostEqual(r.exit_price, 3000.6 + 2.0 * 4.0)


class TestSessionDeadline(unittest.TestCase):
    def test_position_flattened_at_session_exit_time(self):
        cfg = BacktestConfig(exit_model="fixed_1_6r")
        # Start at 06:55 ET so the second bar after entry is 07:15 ET, the LONDON_CORE exit deadline.
        start = datetime.datetime(2026, 2, 10, 11, 55, tzinfo=datetime.timezone.utc)
        bars = _bars(start, [(3000.0, 3001.0, 2999.0, 3000.5), (3000.5, 3002.0, 3000.0, 3001.0),
                             (3001.0, 3002.0, 3000.5, 3001.5), (3001.5, 3002.5, 3001.0, 3002.0), (3002.0, 3003.0, 3001.5, 3002.5)])
        r = simulate_trade(_long_signal(), bars, cfg, units=10.0)
        self.assertEqual(r.outcome, "SESSION_EXPIRATION")
        self.assertEqual(r.exit_time.astimezone(NY_TZ).strftime("%H:%M"), "07:15")


class TestRegimeGate(unittest.TestCase):
    def test_two_consecutive_losses_quarantine_the_pair(self):
        gate = RegimeGate()
        ok, _, _ = gate.evaluate_setup_viability("GOLD", "LONDON_CORE", "IMP_PULLBACK")
        self.assertTrue(ok)
        gate.record("GOLD", "LONDON_CORE", -40.0)
        gate.record("GOLD", "LONDON_CORE", -40.0)
        ok, _, reason = gate.evaluate_setup_viability("GOLD", "LONDON_CORE", "IMP_PULLBACK")
        self.assertFalse(ok)
        self.assertIn("QUARANTINED", reason)
        # Production semantics: one win after two losses leaves the pair in OBSERVATION with a
        # quality score of 3/7 = 0.43, still under the 0.45 execution hurdle. A second win releases it.
        gate.record("GOLD", "LONDON_CORE", 60.0)
        self.assertFalse(gate.evaluate_setup_viability("GOLD", "LONDON_CORE", "IMP_PULLBACK")[0])
        gate.record("GOLD", "LONDON_CORE", 60.0)
        self.assertTrue(gate.evaluate_setup_viability("GOLD", "LONDON_CORE", "IMP_PULLBACK")[0])


if __name__ == "__main__":
    unittest.main()


class TestVariantOptions(unittest.TestCase):
    """Options added for the strategy search: time exit, wider stop, trend and setup filters."""

    def test_time_exit_ignores_targets_and_closes_at_deadline(self):
        from ict_sentinel.gold_backtest import BacktestConfig as C
        cfg = C(exit_model="time_exit", stop_mult=1.0)
        start = datetime.datetime(2026, 2, 10, 11, 55, tzinfo=datetime.timezone.utc)  # 06:55 EST
        # a 40-point spike would hit any fixed target; time exit must hold to the 07:15 deadline
        bars = _bars(start, [(3000.0, 3001.0, 2999.0, 3000.5), (3000.5, 3040.0, 3000.0, 3030.0),
                             (3030.0, 3031.0, 3020.0, 3025.0), (3025.0, 3026.0, 3015.0, 3020.0), (3020.0, 3021.0, 3010.0, 3015.0)])
        r = simulate_trade(_long_signal(), bars, cfg, units=10.0)
        self.assertEqual(r.outcome, "SESSION_EXPIRATION")
        self.assertAlmostEqual(r.exit_price, 3015.0)   # close of the 07:15 bar

    def test_stop_mult_widens_the_structural_stop_and_risk(self):
        from ict_sentinel.gold_backtest import BacktestConfig as C
        cfg = C(exit_model="time_exit", stop_mult=2.0)
        bars = _bars(T0, [(3000.0, 3001.0, 2999.0, 3000.5), (3000.5, 3001.0, 2994.0, 2995.0), (2995.0, 2996.0, 2990.0, 2991.0)])
        r = simulate_trade(_long_signal(), bars, cfg, units=10.0)
        # original stop 2996 is pierced on bar 2 but the widened stop (2996 - 4 = 2992) holds until bar 3
        self.assertEqual(r.outcome, "STOP")
        self.assertAlmostEqual(r.exit_price, 2992.0 - 0.10)
        self.assertAlmostEqual(r.risk_pts, 8.0)

    def test_daily_trend_uses_only_completed_days(self):
        from ict_sentinel.gold_backtest import DailyTrend
        t = DailyTrend(ema_len=3)
        day = datetime.date(2026, 2, 2)
        for i, close in enumerate([100.0, 101.0, 102.0, 103.0]):
            t.observe(day + datetime.timedelta(days=i), close)
        # the 5th day is in progress: its bars must not influence the trend read for that day
        self.assertEqual(t.direction(day + datetime.timedelta(days=4)), "UP")
        t.observe(day + datetime.timedelta(days=4), 50.0)
        self.assertEqual(t.direction(day + datetime.timedelta(days=4)), "UP")
        self.assertEqual(t.direction(day + datetime.timedelta(days=5)), "DOWN")

    def test_signal_filters(self):
        from ict_sentinel.gold_backtest import BacktestConfig as C, signal_allowed
        cfg = C(setups=("IMP_PULLBACK",), trend_filter=True)
        self.assertTrue(signal_allowed(cfg, "IMP_PULLBACK", "LONG", "UP"))
        self.assertFalse(signal_allowed(cfg, "IMP_PULLBACK", "SHORT", "UP"))
        self.assertFalse(signal_allowed(cfg, "ASIA_SWEEP", "LONG", "UP"))
        self.assertTrue(signal_allowed(C(), "ASIA_SWEEP", "SHORT", "UP"))


class TestRandomEntryControl(unittest.TestCase):
    def test_random_control_is_seeded_and_uses_engine_bounds(self):
        from ict_sentinel.gold_backtest import BacktestConfig as C, random_signal
        import random
        # 40 bars of London Core tape, mild noise around 3000
        start = datetime.datetime(2026, 2, 10, 9, 0, tzinfo=datetime.timezone.utc)
        bars = _bars(start, [(3000.0 + (i % 5) * 0.4, 3001.5 + (i % 5) * 0.4, 2999.0 + (i % 5) * 0.4, 3000.5 + (i % 5) * 0.4) for i in range(40)])
        a = random_signal(bars, "LONDON_CORE", random.Random(7))
        b = random_signal(bars, "LONDON_CORE", random.Random(7))
        self.assertEqual((a.direction, a.stop_loss, a.risk_pts), (b.direction, b.stop_loss, b.risk_pts))
        self.assertIn(a.direction, ("LONG", "SHORT"))
        self.assertGreaterEqual(a.risk_pts, 1.5)
        self.assertLessEqual(a.risk_pts, 15.0)
        self.assertEqual(a.pd_array.array_type, "RANDOM")
        self.assertEqual(a.session, "LONDON_CORE")
        if a.direction == "LONG":
            self.assertAlmostEqual(a.entry_price - a.stop_loss, a.risk_pts)
        else:
            self.assertAlmostEqual(a.stop_loss - a.entry_price, a.risk_pts)
