"""
Unit Tests for Core Gold Model v1.6 (Dual-Engine IMP + Asia Sweep Reclaim)
"""

import unittest
import datetime
from ict_sentinel.models import Candle
from ict_sentinel.ipda_engine import IPDAEngine

class TestGoldImpSweep(unittest.TestCase):
    def setUp(self):
        self.ipda = IPDAEngine()

    def _create_candle(self, dt_utc: datetime.datetime, o: float, h: float, l: float, c: float) -> Candle:
        # Convert UTC to ET
        dt_et = dt_utc - datetime.timedelta(hours=5)
        return Candle(
            timestamp=dt_utc,
            timestamp_et=dt_et,
            open=o,
            high=h,
            low=l,
            close=c,
            volume=100.0
        )

    def test_stand_down_outside_london_core(self):
        """Verifies bot stands down on Gold outside 07:00 - 12:00 UTC (e.g. 14:00 UTC)"""
        base_date = datetime.date(2026, 11, 16)
        candles = []
        for i in range(30):
            t = datetime.datetime.combine(base_date, datetime.time(13, 0)) + datetime.timedelta(minutes=i*5)
            candles.append(self._create_candle(t, 3870, 3872, 3869, 3871))
        
        signal = self.ipda.evaluate_market('GOLD', candles)
        self.assertIsNone(signal, "Must stand down on Gold outside London Core window")

    def test_sweep_buy_asia_low_reclaim(self):
        """Verifies Engine B triggers Sweep-Buy when price sweeps below Asia Low and reclaims with green candle"""
        base_date = datetime.date(2026, 11, 16)
        candles = []

        # 1. Asia Session bars (00:00 to 07:00 UTC): Asia Low = 3850.0, Asia High = 3870.0
        for i in range(12):
            t = datetime.datetime.combine(base_date, datetime.time(2, 0)) + datetime.timedelta(minutes=i*5)
            candles.append(self._create_candle(t, 3860, 3870, 3850, 3865))

        # 2. London Core bars (07:00 UTC onward)
        # Bar 1 (07:00): Normal inside bar
        candles.append(self._create_candle(datetime.datetime.combine(base_date, datetime.time(7, 0)), 3855, 3858, 3852, 3853))
        # Bar 2 (07:05): Pierces Asia Low (3850.0) with low 3847.0, closes 3849.0
        candles.append(self._create_candle(datetime.datetime.combine(base_date, datetime.time(7, 5)), 3853, 3854, 3847, 3849))
        # Bar 3 (07:10): Reclaims back ABOVE Asia Low with bullish green candle: open 3849, low 3848, high 3856, close 3855 (> 3850 & > open)
        candles.append(self._create_candle(datetime.datetime.combine(base_date, datetime.time(7, 10)), 3849, 3856, 3848, 3855))

        signal = self.ipda.evaluate_market('GOLD', candles)
        self.assertIsNotNone(signal, "Sweep-Buy signal must trigger on Asia Low reclaim")
        self.assertEqual(signal.direction, 'LONG')
        self.assertEqual(signal.entry_price, 3855.0)
        # Structural SL = min(curr.low=3848, prev.low=3847) - 0.50 = 3846.50
        self.assertEqual(signal.stop_loss, 3846.50)
        self.assertEqual(signal.risk_pts, 8.50)
        # Target = 3855 + (8.50 * 1.6) = 3855 + 13.60 = 3868.60
        self.assertEqual(signal.target_center_mass, 3868.60)
        self.assertIn("Sweep-Buy", signal.ai_rationale)

    def test_imp_momentum_pullback_long(self):
        """Verifies Engine A triggers IMP-Long when Asia High broken, pullback respects level, and swing breaks"""
        base_date = datetime.date(2026, 11, 16)
        candles = []

        # 1. Asia Session (00:00 to 07:00 UTC): Asia High = 3860.0, Asia Low = 3840.0
        for i in range(12):
            t = datetime.datetime.combine(base_date, datetime.time(3, 0)) + datetime.timedelta(minutes=i*5)
            candles.append(self._create_candle(t, 3845, 3860, 3840, 3850))

        # 2. London Breakout (07:00 to 07:15 UTC): Breaks above Asia High (3860.0)
        candles.append(self._create_candle(datetime.datetime.combine(base_date, datetime.time(7, 0)), 3855, 3868, 3854, 3866))
        # 3. Pullback (07:05 to 07:15): Pulls back to 3861 (within $1 of 3860 level), swing high is 3867
        candles.append(self._create_candle(datetime.datetime.combine(base_date, datetime.time(7, 5)), 3866, 3867, 3861, 3862))
        candles.append(self._create_candle(datetime.datetime.combine(base_date, datetime.time(7, 10)), 3862, 3864, 3861, 3863))
        # 4. Trigger (07:15): Breaks above swing high (3867) to 3869
        candles.append(self._create_candle(datetime.datetime.combine(base_date, datetime.time(7, 15)), 3863, 3870, 3862, 3869))

        signal = self.ipda.evaluate_market('GOLD', candles)
        self.assertIsNotNone(signal, "IMP-Long signal must trigger on pullback continuation")
        self.assertEqual(signal.direction, 'LONG')
        self.assertEqual(signal.entry_price, 3869.0)
        self.assertIn("IMP-Long", signal.ai_rationale)
        self.assertGreater(signal.target_center_mass, signal.entry_price)

if __name__ == '__main__':
    unittest.main()
