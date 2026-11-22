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
