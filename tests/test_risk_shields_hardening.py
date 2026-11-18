"""
Test Suite: Risk Shields & Strategy Hardening Verification
Validates:
1. Daily Drawdown Circuit Breaker ($50.00 max risk cap)
2. 15-Minute Asset Re-entry Cooldown
3. Non-FVG PDArray defense (defending_fvg_ce = None)
4. Off-Session Evaluation Gate
5. Bayesian Memory Scrutiny for Gold Strategy
"""

import unittest
import datetime
import os
import tempfile
from ict_sentinel.models import Candle, PDArray, Position, AccountState
from ict_sentinel.order_manager import OrderManager
from ict_sentinel.storage import StorageEngine
from ict_sentinel.ai_advisor import AIAdvisor
from ict_sentinel.memory_engine import MemoryEngine
from ict_sentinel.ipda_engine import AlgorithmicSignal, IPDAEngine

class TestRiskShieldsHardening(unittest.TestCase):
    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.temp_db.close()
        self.storage = StorageEngine(db_path=self.temp_db.name)
        self.advisor = AIAdvisor()
        self.memory = MemoryEngine(self.storage, self.advisor)
        self.order_mgr = OrderManager(self.storage, self.advisor, self.memory)
        self.ipda = IPDAEngine()

    def tearDown(self):
        if os.path.exists(self.temp_db.name):
            os.remove(self.temp_db.name)

    def test_daily_drawdown_circuit_breaker(self):
        """Verify that when drawdown reaches or exceeds $50.00, order_manager blocks entries."""
        # Initial capital: $500. Peak: $500. Balance: $445 (Drawdown: $55.00 > $50.00 budget)
        self.storage.update_account_balance(-55.0)
        acct = self.storage.get_account_state()
        self.assertGreaterEqual(acct.peak_balance - acct.balance, 50.0)

        sig = AlgorithmicSignal(
            asset='GOLD',
            session='LONDON',
            direction='SHORT',
            entry_price=3770.0,
            stop_loss=3773.0,
            risk_pts=3.0,
            target_center_mass=3765.0,
            target_head_shot=3761.0,
            pd_array=PDArray('SIBI', 3772.0, 3770.0, 3771.0, datetime.datetime.now()),
            ai_rationale='Valid test signal'
        )

        pos = self.order_mgr.open_position_from_signal(sig, datetime.datetime.now())
        self.assertIsNone(pos, "Order should be BLOCKED by Daily Drawdown Circuit Breaker!")

    def test_reentry_cooldown_filter(self):
        """Verify 15-minute cooldown prevents rapid back-to-back entries on the same asset."""
        now = datetime.datetime(2026, 11, 18, 10, 0, 0)
        # Register a cooldown exit at 10:00:00
        self.order_mgr._asset_cooldowns['GOLD'] = now

        sig = AlgorithmicSignal(
            asset='GOLD',
            session='LONDON',
            direction='SHORT',
            entry_price=3770.0,
            stop_loss=3773.0,
            risk_pts=3.0,
            target_center_mass=3765.0,
            target_head_shot=3761.0,
            pd_array=PDArray('SIBI', 3772.0, 3770.0, 3771.0, now),
            ai_rationale='Valid test signal'
        )

        # 5 minutes later: Should be BLOCKED
        t_5m = now + datetime.timedelta(minutes=5)
        pos_blocked = self.order_mgr.open_position_from_signal(sig, t_5m)
        self.assertIsNone(pos_blocked, "Order should be BLOCKED during 15-minute cooldown!")

        # 16 minutes later: Should be APPROVED
        t_16m = now + datetime.timedelta(minutes=16)
        pos_approved = self.order_mgr.open_position_from_signal(sig, t_16m)
        self.assertIsNotNone(pos_approved, "Order should be APPROVED after cooldown expires!")

    def test_gold_non_fvg_defense_null_ce(self):
        """Verify that Core Gold Model (ASIA_SWEEP / IMP_PULLBACK) does NOT set defending_fvg_ce."""
        sig = AlgorithmicSignal(
            asset='GOLD',
            session='LONDON_CORE',
            direction='LONG',
            entry_price=3779.8,
            stop_loss=3775.0,
            risk_pts=4.8,
            target_center_mass=3787.0,
            target_head_shot=3795.0,
            pd_array=PDArray('ASIA_SWEEP', 3851.4, 3777.5, None, datetime.datetime.now()),
            ai_rationale='Core Gold Model v1.6 Sweep-Buy'
        )

        pos = self.order_mgr.open_position_from_signal(sig, datetime.datetime.now())
        self.assertIsNotNone(pos)
        self.assertIsNone(pos.defending_fvg_ce, "Non-FVG setup MUST have defending_fvg_ce = None to avoid instant scratch!")

        # Send a bar at 05:30 EST with close at 3779.0 (below Asian range midpoint 3814.45)
        bar_time = datetime.datetime(2026, 11, 18, 5, 30, 0)
        bar = Candle(
            timestamp=bar_time,
            timestamp_et=bar_time,
            open=3779.5, high=3780.0, low=3778.5, close=3779.0, volume=100
        )
        closed = self.order_mgr.update_positions_with_bar('GOLD', bar)
        self.assertEqual(len(closed), 0, "Position should NOT be scratched prematurely on normal price action!")

    def test_off_session_evaluation_gate(self):
        """Verify evaluate_market returns None during true off-session (07:15 EST pre-NY pause) and for Forex in London Core."""
        # 1. 07:15 EST is in the universal pre-NY transition (London Core ended at 07:00, NY opens at 08:00)
        off_time = datetime.datetime(2026, 11, 18, 7, 15, 0)
        candles = []
        for i in range(25):
            t = off_time - datetime.timedelta(minutes=(25 - i) * 5)
            candles.append(Candle(t, t, 3770.0, 3775.0, 3768.0, 3772.0, 500))

        sig_gold = self.ipda.evaluate_market('GOLD', candles, memory_engine=self.memory)
        self.assertIsNone(sig_gold, "No signals should ever be generated during universal OFF-SESSION (07:15 EST)!")

        # 2. 05:00 EST is London Core: Forex (GBPUSD) must stand down
        core_time = datetime.datetime(2026, 11, 18, 5, 0, 0)
        fx_candles = []
        for i in range(25):
            t = core_time - datetime.timedelta(minutes=(25 - i) * 5)
            fx_candles.append(Candle(t, t, 1.3200, 1.3210, 1.3195, 1.3205, 500))

        sig_fx = self.ipda.evaluate_market('GBPUSD', fx_candles, memory_engine=self.memory)
        self.assertIsNone(sig_fx, "Forex must stand down during London Core; only Gold is active!")

    def test_memory_engine_gate_for_gold(self):
        """Verify that when Gold is in OBSERVATION with low quality score, evaluate_market rejects it."""
        # Force Gold regime into OBSERVATION with BQS 0.35 (simulating recent loss)
        self.storage.update_adaptive_weight('GOLD', 'LONDON', win=False, quality_score=0.35, consecutive_losses=1, status='OBSERVATION')

        approved, q_score, reason = self.memory.evaluate_setup_viability('GOLD', 'LONDON', 'IMP_PULLBACK')
        self.assertFalse(approved, "Regime in OBSERVATION with BQS < 0.45 must be rejected!")
        self.assertIn("FILTERED", reason)

if __name__ == '__main__':
    unittest.main()
