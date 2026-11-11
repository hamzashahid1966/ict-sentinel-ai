"""
Test Suite for ICT Sentinel AI Adaptive Memory & Self-Learning Engine
Verifies Bayesian Quality Score updating, episodic post-mortems, circuit breakers, and signal gating.
"""

import os
import unittest
import datetime
from ict_sentinel.storage import StorageEngine
from ict_sentinel.ai_advisor import AIAdvisor
from ict_sentinel.memory_engine import MemoryEngine
from ict_sentinel.models import Position, TradeRecord, Candle

class TestMemoryEngine(unittest.TestCase):
    def setUp(self):
        # Use isolated in-memory or temp SQLite DB for clean tests
        self.test_db = "/tmp/test_sentinel_memory.db"
        if os.path.exists(self.test_db):
            os.remove(self.test_db)
        self.storage = StorageEngine(db_path=self.test_db)
        self.advisor = AIAdvisor()
        self.memory = MemoryEngine(self.storage, self.advisor)

        self.dummy_candle = Candle(
            timestamp=datetime.datetime(2026, 11, 10, 8, 30, tzinfo=datetime.timezone.utc),
            timestamp_et=datetime.datetime(2026, 11, 10, 3, 30), # London session
            open=1.0850, high=1.0860, low=1.0845, close=1.0855, volume=100
        )

    def tearDown(self):
        if hasattr(self, 'storage'):
            self.storage.close()
        for suffix in ["", "-wal", "-shm"]:
            path = self.test_db + suffix
            if os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass

    def test_full_win_reflection_and_bayesian_update(self):
        pos = Position(
            position_id="test_win_pos",
            asset="GOLD",
            direction="LONG",
            quantity=1,
            entry_price=2700.0,
            entry_time=datetime.datetime(2026, 11, 10, 3, 0),
            initial_stop_loss=2695.0,
            active_trailing_stop=2700.2,
            target_center_mass=2707.5,
            target_head_shot=2715.0,
            center_mass_filled=True,
            head_shot_filled=True,
            realized_pnl=37.50,
            status="CLOSED",
            defensive_shields=[]
        )
        tr = TradeRecord(
            trade_id="test_win_pos",
            asset="GOLD",
            session="LONDON",
            direction="LONG",
            entry_time="2026-11-10 03:00:00",
            entry_price=2700.0,
            exit_time="2026-11-10 03:30:00",
            exit_price=2715.0,
            risk_pts=5.0,
            pnl_pts=15.0,
            dollar_pnl=75.0,
            outcome="FULL_WIN",
            ai_reasoning="Hit Head Shot 3.0R terminus."
        )

        self.memory.process_trade_completion(tr, pos, self.dummy_candle)

        # Verify Bayesian Weight
        weight = self.storage.get_adaptive_weight("GOLD", "LONDON")
        self.assertIsNotNone(weight)
        self.assertEqual(weight['wins'], 1)
        self.assertEqual(weight['losses'], 0)
        self.assertEqual(weight['status'], "PRIME")
        self.assertGreater(weight['quality_score'], 0.55)

        # Verify Reflection
        reflections = self.storage.get_recent_reflections()
        self.assertEqual(len(reflections), 1)
        self.assertEqual(reflections[0]['reflection_type'], "EXPANSION_SUCCESS")

    def test_circuit_breaker_on_consecutive_losses(self):
        """
        Verifies that 2 consecutive losses trigger automatic QUARANTINE status,
        and gate further trade signals.
        """
        pos = Position(
            position_id="pos1", asset="NASDAQ", direction="SHORT", quantity=1,
            entry_price=20500.0, entry_time=datetime.datetime(2026, 11, 10, 10, 15),
            initial_stop_loss=20520.0, active_trailing_stop=20520.0,
            target_center_mass=20470.0, target_head_shot=20440.0,
            center_mass_filled=False, head_shot_filled=False, realized_pnl=0.0,
            status="CLOSED", defensive_shields=[]
        )

        # Loss #1
        tr1 = TradeRecord(
            trade_id="pos1", asset="NASDAQ", session="NEW_YORK_AM", direction="SHORT",
            entry_time="2026-11-10 10:15:00", entry_price=20500.0, exit_time="2026-11-10 10:25:00",
            exit_price=20520.0, risk_pts=20.0, pnl_pts=-20.0, dollar_pnl=-40.0,
            outcome="LOSS", ai_reasoning="Stop loss triggered."
        )
        self.memory.process_trade_completion(tr1, pos, self.dummy_candle)
        weight1 = self.storage.get_adaptive_weight("NASDAQ", "NEW_YORK_AM")
        self.assertEqual(weight1['consecutive_losses'], 1)
        self.assertNotEqual(weight1['status'], "QUARANTINED")

        # Loss #2 (Triggers Circuit Breaker)
        tr2 = TradeRecord(
            trade_id="pos2", asset="NASDAQ", session="NEW_YORK_AM", direction="SHORT",
            entry_time="2026-11-10 10:30:00", entry_price=20510.0, exit_time="2026-11-10 10:40:00",
            exit_price=20530.0, risk_pts=20.0, pnl_pts=-20.0, dollar_pnl=-40.0,
            outcome="LOSS", ai_reasoning="Stop loss triggered second time."
        )
        self.memory.process_trade_completion(tr2, pos, self.dummy_candle)
        weight2 = self.storage.get_adaptive_weight("NASDAQ", "NEW_YORK_AM")
        self.assertEqual(weight2['consecutive_losses'], 2)
        self.assertEqual(weight2['status'], "QUARANTINED")

        # Test Signal Gating
        approved, conf, reason = self.memory.evaluate_setup_viability("NASDAQ", "NEW_YORK_AM", "SIBI")
        self.assertFalse(approved, "Setup must be rejected when session is QUARANTINED!")
        self.assertIn("QUARANTINED", reason)

if __name__ == "__main__":
    unittest.main()

