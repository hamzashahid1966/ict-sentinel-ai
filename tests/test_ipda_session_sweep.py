"""
Unit tests for IPDA Engine: Session-Wide Sweep Memory & Multi-Candle Retest Window.
Verifies:
1. Inside-range condition (screenshot state) produces Confluence 60 and HUNTING_SWEEP.
2. Multi-candle lookback: Sweep at bar -6 with FVG at bar -4 and retest at bar -1 triggers valid signal.
3. 50% Consequent Encroachment (C.E.) violation disqualifies the setup.
"""

import unittest
import datetime
from ict_sentinel.models import Candle
from ict_sentinel.ipda_engine import IPDAEngine

class TestIPDASessionSweep(unittest.TestCase):
    def setUp(self):
        self.ipda = IPDAEngine()
        self.test_date = datetime.date(2026, 11, 16) # Monday (No NFP)

    def _create_asian_reference_bars(self, base_px=3970.0, high_offset=25.0, low_offset=5.0):
        """Creates 15 Asian session bars (20:00 to 21:10 EST) establishing Ref High 3995.0 and Low 3965.0."""
        bars = []
        for i in range(15):
            t = datetime.time(20 + (i * 5) // 60, (i * 5) % 60)
            dt_et = datetime.datetime.combine(self.test_date, t)
            # High 3995.0 on bar 3, Low 3965.0 on bar 7
            h = base_px + (high_offset if i == 3 else 15.0)
            l = base_px - (low_offset if i == 7 else 0.0)
            c = Candle(
                timestamp=dt_et,
                timestamp_et=dt_et,
                open=base_px + 5.0,
                high=h,
                low=l,
                close=base_px + 7.0,
                volume=100.0
            )
            bars.append(c)
        return bars

    def test_inside_range_screenshot_state(self):
        """
        When trading inside Asian reference range with no sweep:
        Confluence score MUST be 60/100, status HUNTING_SWEEP, Liquidity Sweep: NO (Inside Range).
        """
        candles = self._create_asian_reference_bars()
        # Add 6 London bars inside the range (02:00 to 02:25 EST)
        for i in range(6):
            t = datetime.time(2, i * 5)
            dt_et = datetime.datetime.combine(self.test_date, t)
            # Oscillation inside 3970.0 - 3980.0 (Range is 3965.0 - 3995.0)
            c = Candle(
                timestamp=dt_et,
                timestamp_et=dt_et,
                open=3975.0,
                high=3980.0,
                low=3972.0,
                close=3977.0,
                volume=150.0
            )
            candles.append(c)

        sig = self.ipda.evaluate_market("GOLD", candles)
        self.assertIsNone(sig, "No trade should be taken when price is oscillating inside the range.")

        diag = self.ipda.diagnose_market("GOLD", candles)
        self.assertEqual(diag["score"], 60, "Confluence score inside range must be 60/100.")
        self.assertEqual(diag["status"], "HUNTING_SWEEP")
        self.assertEqual(diag["checklist"]["Liquidity Sweep"], "NO (Inside Range)")
        self.assertEqual(diag["checklist"]["Candle Body MSS"], "WAITING")
        self.assertEqual(diag["checklist"]["50% C.E. Respect"], "PENDING")

    def test_session_wide_sweep_with_multi_candle_retest(self):
        """
        Verifies that a BSL sweep occurring 6 candles ago (02:10 EST)
        followed by displacement, FVG formation, and retest at 02:30 EST (bar -1)
        triggers a valid SHORT signal.
        """
        candles = self._create_asian_reference_bars() # Ref High = 3995.0, Ref Low = 3965.0 (Range = 30 pts)
        ref_high = 3995.0
        ref_low = 3965.0

        # Bar 0 (02:00): inside range
        t0 = datetime.datetime.combine(self.test_date, datetime.time(2, 0))
        candles.append(Candle(t0, t0, open=3980.0, high=3985.0, low=3978.0, close=3982.0, volume=100.0))

        # Bar 1 (02:05): Judas Swing sweeps BSL above 3995.0 (High 3997.0, Close 3994.0)
        t1 = datetime.datetime.combine(self.test_date, datetime.time(2, 5))
        candles.append(Candle(t1, t1, open=3985.0, high=3997.0, low=3984.0, close=3994.0, volume=300.0))

        # Bar 2 (02:10): Bearish displacement start (c0 of SIBI: low = 3996.0)
        t2 = datetime.datetime.combine(self.test_date, datetime.time(2, 10))
        candles.append(Candle(t2, t2, open=3996.5, high=3996.8, low=3996.0, close=3995.0, volume=250.0))

        # Bar 3 (02:15): Strong displacement down (c1: body break below sweep bar low 3984.0)
        t3 = datetime.datetime.combine(self.test_date, datetime.time(2, 15))
        candles.append(Candle(t3, t3, open=3995.0, high=3995.2, low=3982.0, close=3983.0, volume=400.0))

        # Bar 4 (02:20): Completes FVG (c2: high = 3994.5). SIBI gap is [3994.5, 3996.0], CE = 3995.25.
        t4 = datetime.datetime.combine(self.test_date, datetime.time(2, 20))
        candles.append(Candle(t4, t4, open=3983.0, high=3994.5, low=3981.0, close=3982.0, volume=250.0))

        # Bar 5 (02:25): Pause bar, respects CE (close = 3988.0 <= CE 3995.25)
        t5 = datetime.datetime.combine(self.test_date, datetime.time(2, 25))
        candles.append(Candle(t5, t5, open=3982.0, high=3989.0, low=3981.0, close=3988.0, volume=150.0))

        # Bar 6 (02:30): Retests into FVG (High = 3995.0 >= fvg_low 3994.5, Close = 3994.8 <= fvg_high 3996.0)
        t6 = datetime.datetime.combine(self.test_date, datetime.time(2, 30))
        candles.append(Candle(t6, t6, open=3988.0, high=3995.0, low=3987.0, close=3994.8, volume=200.0))

        # Evaluate setup with our upgraded session-wide memory
        sig = self.ipda.evaluate_market("GOLD", candles)
        self.assertIsNotNone(sig, "Session-wide sweep with multi-candle retest must trigger a valid signal!")
        self.assertEqual(sig.direction, "SHORT")
        self.assertEqual(sig.entry_price, 3994.5)
        self.assertGreater(sig.stop_loss, 3997.0) # Stop placed above the Judas Swing sweep wick
        self.assertEqual(sig.pd_array.array_type, "SIBI")

        # Verify diagnosis reports the sweep time and confirms MSS
        diag = self.ipda.diagnose_market("GOLD", candles)
        self.assertEqual(diag["score"], 100)
        self.assertIn("BSL SWEPT", diag["checklist"]["Liquidity Sweep"])
        self.assertEqual(diag["checklist"]["Candle Body MSS"], "CONFIRMED")
        self.assertEqual(diag["checklist"]["50% C.E. Respect"], "RESPECTED")

    def test_ce_violation_disqualifies_setup(self):
        """
        If candle bodies close above 50% Consequent Encroachment (3995.25),
        the setup MUST be rejected (Institutional rule from Lectures 35 & 41).
        """
        candles = self._create_asian_reference_bars()
        # Repeat above setup but Bar 5 closes above CE (3995.8 > 3995.25)
        t0 = datetime.datetime.combine(self.test_date, datetime.time(2, 0))
        candles.append(Candle(t0, t0, open=3980.0, high=3985.0, low=3978.0, close=3982.0, volume=100.0))

        t1 = datetime.datetime.combine(self.test_date, datetime.time(2, 5))
        candles.append(Candle(t1, t1, open=3985.0, high=3997.0, low=3984.0, close=3994.0, volume=300.0))

        t2 = datetime.datetime.combine(self.test_date, datetime.time(2, 10))
        candles.append(Candle(t2, t2, open=3996.5, high=3996.8, low=3996.0, close=3995.0, volume=250.0))

        t3 = datetime.datetime.combine(self.test_date, datetime.time(2, 15))
        candles.append(Candle(t3, t3, open=3995.0, high=3995.2, low=3982.0, close=3983.0, volume=400.0))

        t4 = datetime.datetime.combine(self.test_date, datetime.time(2, 20))
        candles.append(Candle(t4, t4, open=3983.0, high=3994.5, low=3981.0, close=3982.0, volume=250.0))

        # Bar 5 VIOLATES CE: closes at 3995.8 (above CE 3995.25)
        t5 = datetime.datetime.combine(self.test_date, datetime.time(2, 25))
        candles.append(Candle(t5, t5, open=3982.0, high=3996.0, low=3981.0, close=3995.8, volume=300.0))

        # Bar 6 retests
        t6 = datetime.datetime.combine(self.test_date, datetime.time(2, 30))
        candles.append(Candle(t6, t6, open=3995.8, high=3996.0, low=3994.0, close=3994.8, volume=200.0))

        sig = self.ipda.evaluate_market("GOLD", candles)
        self.assertIsNone(sig, "Setup with violated 50% CE must be rejected!")

if __name__ == '__main__':
    unittest.main()
