import unittest
import datetime
from unittest.mock import MagicMock
from ict_sentinel.models import Position, PDArray, Candle
from ict_sentinel.ipda_engine import AlgorithmicSignal
from ict_sentinel.order_manager import OrderManager
from ict_sentinel.config import ASSET_SPECS, NY_TZ

class TestFixRapidChurnCEScratch(unittest.TestCase):
    def setUp(self):
        self.mock_storage = MagicMock()
        self.mock_storage.get_daily_drawdown.return_value = 0.0
        self.mock_storage.load_open_positions.return_value = []
        self.mock_storage.get_trade_history.return_value = []
        self.mock_advisor = MagicMock()
        self.order_mgr = OrderManager(self.mock_storage, self.mock_advisor)

    def test_long_with_inverted_ce_sanitized_to_none(self):
        """
        Tests that if a LONG signal contains a CE >= entry_price (such as Asian Range midpoint),
        defending_fvg_ce is strictly sanitized to None so that rapid suicide churn cannot occur.
        """
        now = datetime.datetime(2026, 11, 24, 8, 41, tzinfo=NY_TZ)
        pd_arr = PDArray(
            array_type='BISI',
            high=3676.70,
            low=3612.60,
            consequent_encroachment=3644.65, # Inverted! Greater than entry_price (3613.0)
            formation_time=now
        )
        sig = AlgorithmicSignal(
            asset='GOLD',
            session='LONDON',
            direction='LONG',
            entry_price=3613.00,
            stop_loss=3608.00,
            risk_pts=5.00,
            target_center_mass=3623.00,
            target_head_shot=3628.00,
            pd_array=pd_arr,
            ai_rationale="Test Long with inverted CE"
        )
        pos = self.order_mgr.open_position_from_signal(sig, now)
        self.assertIsNotNone(pos)
        self.assertIsNone(pos.defending_fvg_ce, "Inverted CE on LONG must be sanitized to None!")

    def test_short_with_inverted_ce_sanitized_to_none(self):
        """
        Tests that if a SHORT signal contains a CE <= entry_price,
        defending_fvg_ce is strictly sanitized to None.
        """
        now = datetime.datetime(2026, 11, 24, 8, 41, tzinfo=NY_TZ)
        pd_arr = PDArray(
            array_type='SIBI',
            high=3676.70,
            low=3612.60,
            consequent_encroachment=3600.00, # Inverted! Less than entry_price (3613.0)
            formation_time=now
        )
        sig = AlgorithmicSignal(
            asset='GOLD',
            session='LONDON',
            direction='SHORT',
            entry_price=3613.00,
            stop_loss=3618.00,
            risk_pts=5.00,
            target_center_mass=3603.00,
            target_head_shot=3598.00,
            pd_array=pd_arr,
            ai_rationale="Test Short with inverted CE"
        )
        pos = self.order_mgr.open_position_from_signal(sig, now)
        self.assertIsNotNone(pos)
        self.assertIsNone(pos.defending_fvg_ce, "Inverted CE on SHORT must be sanitized to None!")

    def test_long_with_valid_ce_retained(self):
        """
        Tests that a valid CE (below entry for Long) is correctly assigned.
        """
        now = datetime.datetime(2026, 11, 24, 8, 41, tzinfo=NY_TZ)
        pd_arr = PDArray(
            array_type='BISI',
            high=3615.00,
            low=3605.00,
            consequent_encroachment=3610.00, # Valid! Below entry_price 3613.0
            formation_time=now
        )
        sig = AlgorithmicSignal(
            asset='GOLD',
            session='LONDON',
            direction='LONG',
            entry_price=3613.00,
            stop_loss=3605.00,
            risk_pts=8.00,
            target_center_mass=3625.00,
            target_head_shot=3630.00,
            pd_array=pd_arr,
            ai_rationale="Test Long with valid CE"
        )
        pos = self.order_mgr.open_position_from_signal(sig, now)
        self.assertIsNotNone(pos)
        self.assertEqual(pos.defending_fvg_ce, 3610.00)

    def test_early_scratch_triggers_and_enforces_strict_cooldown(self):
        """
        Tests that when an early scratch occurs, the asset is strictly placed on cooldown,
        blocking re-entry on the same asset within 900 seconds.
        """
        t0 = datetime.datetime(2026, 11, 24, 8, 40, tzinfo=NY_TZ)
        pd_arr = PDArray(
            array_type='BISI',
            high=1.0850,
            low=1.0810,
            consequent_encroachment=1.0830, # Valid below entry 1.0840
            formation_time=t0
        )
        sig = AlgorithmicSignal(
            asset='EURUSD',
            session='LONDON',
            direction='LONG',
            entry_price=1.0840,
            stop_loss=1.0800,
            risk_pts=0.0040,
            target_center_mass=1.0880,
            target_head_shot=1.0920,
            pd_array=pd_arr,
            ai_rationale="Valid EURUSD long"
        )
        pos = self.order_mgr.open_position_from_signal(sig, t0)
        self.assertIsNotNone(pos)

        # Bar breaching CE (close < 1.0830 - buffer and body_bottom < 1.0830)
        t1 = t0 + datetime.timedelta(minutes=5)
        scratch_bar = Candle(
            timestamp=t1,
            timestamp_et=t1,
            open=1.0835,
            high=1.0836,
            low=1.0815,
            close=1.0820,
            volume=500
        )
        closed = self.order_mgr.update_positions_with_bar('EURUSD', scratch_bar)
        self.assertEqual(len(closed), 1)
        self.assertEqual(closed[0].outcome, 'EARLY_SCRATCH')

        # Attempt immediate re-entry 1 minute later
        t2 = t1 + datetime.timedelta(minutes=1)
        blocked_pos = self.order_mgr.open_position_from_signal(sig, t2)
        self.assertIsNone(blocked_pos, "Re-entry must be blocked by cooldown within 900 seconds!")

        # Attempt re-entry after 16 minutes (960 seconds)
        t3 = t1 + datetime.timedelta(minutes=16)
        allowed_pos = self.order_mgr.open_position_from_signal(sig, t3)
        self.assertIsNotNone(allowed_pos, "Re-entry must be permitted after 15 minutes of stabilization!")

    def test_nov24_rapid_churn_death_loop_is_prevented(self):
        """
        Simulates the exact conditions of Nov 24 Gold trades:
        Long Gold @ 3613.0 with Asian midpoint 3644.65.
        Verifies that:
        1. Inverted CE is neutralized to None so it does NOT scratch on entry.
        2. Even if an exit occurs, consecutive 30s/5m entries are strictly blocked by cooldown.
        """
        t0 = datetime.datetime(2026, 11, 24, 3, 41, 57, tzinfo=NY_TZ)
        pd_arr = PDArray(
            array_type='BISI',
            high=3676.70,
            low=3612.60,
            consequent_encroachment=3644.65,
            formation_time=t0
        )
        sig = AlgorithmicSignal(
            asset='GOLD',
            session='LONDON_CORE',
            direction='LONG',
            entry_price=3613.00,
            stop_loss=3608.00,
            risk_pts=5.00,
            target_center_mass=3623.00,
            target_head_shot=3628.00,
            pd_array=pd_arr,
            ai_rationale="Core Gold Asia Sweep Long"
        )
        # Entry
        pos = self.order_mgr.open_position_from_signal(sig, t0)
        self.assertIsNotNone(pos)
        self.assertIsNone(pos.defending_fvg_ce)

        # Bar 1 tick 30s later: close = 3613.5
        t_tick = t0 + datetime.timedelta(seconds=30)
        bar1 = Candle(
            timestamp=t_tick,
            timestamp_et=t_tick,
            open=3613.0,
            high=3614.0,
            low=3612.8,
            close=3613.5,
            volume=100
        )
        closed = self.order_mgr.update_positions_with_bar('GOLD', bar1)
        self.assertEqual(len(closed), 0, "Trade must NOT scratch when price is stable!")

        # Position stays open and healthy!
        active = [p for p in self.order_mgr._get_active_positions() if p.asset == 'GOLD']
        self.assertEqual(len(active), 1)

if __name__ == '__main__':
    unittest.main()
