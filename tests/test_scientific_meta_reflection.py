"""
Test Suite: Scientific Meta-Reflection & Goal-Seeking Engine
Validates:
1. Rolling Sharpe Ratio and Profit Factor calculation across trade sequences.
2. Single-variable scientific hypothesis generation.
3. Persistence and retrieval in SQLite meta_reflections table.
4. Institutional benchmark comparison (Goal: Sharpe 1.5, PF 2.0).
"""

import unittest
import tempfile
import os
import datetime
from ict_sentinel.models import TradeRecord
from ict_sentinel.storage import StorageEngine
from ict_sentinel.ai_advisor import AIAdvisor
from ict_sentinel.memory_engine import MemoryEngine
from ict_sentinel.config import INSTITUTIONAL_GOALS

class TestScientificMetaReflection(unittest.TestCase):
    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.temp_db.close()
        self.storage = StorageEngine(db_path=self.temp_db.name)
        self.advisor = AIAdvisor()
        self.memory = MemoryEngine(self.storage, self.advisor)

    def tearDown(self):
        if os.path.exists(self.temp_db.name):
            os.remove(self.temp_db.name)

    def test_meta_reflection_on_empty_ledger(self):
        """Verify baseline initialization when no trades exist."""
        reflection = self.memory.synthesize_weekly_meta_reflection()
        self.assertEqual(reflection['total_trades'], 0)
        self.assertEqual(reflection['status'], "INITIALIZING")
        self.assertEqual(reflection['variable_tested'], "Baseline Initialization")

    def test_meta_reflection_on_winning_streak(self):
        """Verify that a winning series meeting goals produces a CONFIRMED baseline hypothesis."""
        for i in range(4):
            tr = TradeRecord(
                trade_id=f"win_{i}",
                asset="GOLD",
                session="LONDON_CORE",
                direction="SHORT",
                entry_time=f"2026-11-18 0{i+2}:00:00",
                entry_price=3770.0,
                exit_time=f"2026-11-18 0{i+3}:00:00",
                exit_price=3764.0,
                risk_pts=3.0,
                pnl_pts=6.0,
                dollar_pnl=60.0,
                outcome="FULL_WIN",
                ai_reasoning="Target reached"
            )
            self.storage.record_closed_trade(tr)

        reflection = self.memory.synthesize_weekly_meta_reflection()
        self.assertEqual(reflection['total_trades'], 4)
        self.assertEqual(reflection['win_rate'], 100.0)
        self.assertGreater(reflection['profit_factor'], 2.0)
        self.assertEqual(reflection['status'], "CONFIRMED")
        self.assertIn("Center Mass Scaling Target", reflection['variable_tested'])
        self.assertIn("1.5R", reflection['hypothesis'])

    def test_meta_reflection_on_underperforming_regime(self):
        """Verify that elevated losses trigger a single-variable hypothesis test on stop buffers."""
        # 3 losses, 1 win (WR: 25%)
        for i in range(3):
            tr = TradeRecord(
                trade_id=f"loss_{i}",
                asset="SILVER",
                session="NEW_YORK_AM",
                direction="LONG",
                entry_time=f"2026-11-18 0{i+8}:00:00",
                entry_price=45.5,
                exit_time=f"2026-11-18 0{i+8}:30:00",
                exit_price=45.45,
                risk_pts=0.05,
                pnl_pts=-0.05,
                dollar_pnl=-35.0,
                outcome="LOSS",
                ai_reasoning="Stop triggered"
            )
            self.storage.record_closed_trade(tr)

        reflection = self.memory.synthesize_weekly_meta_reflection()
        self.assertEqual(reflection['status'], "TESTING")
        self.assertIn("Stop Buffer", reflection['variable_tested'])
        self.assertIn("3 ticks", reflection['hypothesis'])

    def test_meta_reflection_persistence(self):
        """Verify meta_reflections are stored and retrievable in StorageEngine."""
        self.memory.synthesize_weekly_meta_reflection()
        records = self.storage.get_latest_meta_reflections(limit=5)
        self.assertEqual(len(records), 1)
        self.assertIn("window_name", records[0])
        self.assertIn("variable_tested", records[0])
        self.assertIn("realized_sharpe", records[0])

if __name__ == '__main__':
    unittest.main()
