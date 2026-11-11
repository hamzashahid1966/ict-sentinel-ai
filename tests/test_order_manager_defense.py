"""
Unit Test Suite for Active Position Defense & Cross-Session Debriefs
Verifies:
1. Early Scratch exit when 5m candle body closes through defending FVG 50% CE.
2. Session exit deadline liquidation.
3. Target 1 (Center Mass 1.5R) and Target 2 (Head Shot 3.0R) attributions.
4. Session debrief generation & persistence.
"""

import os
import unittest
import datetime
from ict_sentinel.models import Position, Candle, PDArray, TradeRecord
from ict_sentinel.storage import StorageEngine
from ict_sentinel.ai_advisor import AIAdvisor
from ict_sentinel.memory_engine import MemoryEngine
from ict_sentinel.order_manager import OrderManager
from ict_sentinel.ipda_engine import IPDAEngine

class TestOrderManagerDefense(unittest.TestCase):
    def setUp(self):
        self.test_db = "/tmp/test_defense_sentinel.db"
        if os.path.exists(self.test_db):
            os.remove(self.test_db)
        self.storage = StorageEngine(db_path=self.test_db)
        self.advisor = AIAdvisor()
        self.memory = MemoryEngine(self.storage, self.advisor)
        self.om = OrderManager(self.storage, self.advisor, memory_engine=self.memory)
        self.ipda = IPDAEngine()

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

    def test_early_scratch_on_fvg_ce_breach_long(self):
        """
        In a LONG position:
        Entry = 2700.0, Stop = 2695.0, 50% CE = 2698.0
        If a candle closes at 2697.5 (below 50% CE), early scratch MUST trigger!
        """
        pos = Position(
            position_id="scratch_long_1",
            asset="GOLD",
            direction="LONG",
            quantity=1,
            entry_price=2700.0,
            entry_time=datetime.datetime(2026, 11, 10, 8, 30),
            initial_stop_loss=2695.0,
            active_trailing_stop=2695.0,
            target_center_mass=2707.5,
            target_head_shot=2715.0,
            center_mass_filled=False,
            head_shot_filled=False,
            realized_pnl=0.0,
            status="OPEN",
            defensive_shields=[],
            defending_fvg_ce=2698.0,
            session_origin="NEW_YORK_AM"
        )
        self.om._sync_position(pos)

        # Candle closing at 2697.5 (violating 50% CE of 2698.0)
        violating_bar = Candle(
            timestamp=datetime.datetime(2026, 11, 10, 13, 35, tzinfo=datetime.timezone.utc),
            timestamp_et=datetime.datetime(2026, 11, 10, 8, 35),
            open=2699.0, high=2699.5, low=2697.0, close=2697.5, volume=100
        )

        closed = self.om.update_positions_with_bar("GOLD", violating_bar)
        self.assertEqual(len(closed), 1, "Should have triggered early scratch exit")
        tr = closed[0]
        self.assertEqual(tr.outcome, "EARLY_SCRATCH")
        self.assertEqual(tr.invalidation_reason, "50_PCT_CE_BREACH")
        self.assertEqual(tr.exit_price, 2697.5)
        # Verify position was removed from active cache
        self.assertEqual(len(self.om._get_active_positions()), 0)

    def test_early_scratch_on_fvg_ce_breach_short(self):
        """
        In a SHORT position:
        Entry = 2700.0, Stop = 2705.0, 50% CE = 2702.0
        If a candle closes at 2702.5 (above 50% CE), early scratch MUST trigger!
        """
        pos = Position(
            position_id="scratch_short_1",
            asset="GOLD",
            direction="SHORT",
            quantity=1,
            entry_price=2700.0,
            entry_time=datetime.datetime(2026, 11, 10, 8, 30),
            initial_stop_loss=2705.0,
            active_trailing_stop=2705.0,
            target_center_mass=2692.5,
            target_head_shot=2685.0,
            center_mass_filled=False,
            head_shot_filled=False,
            realized_pnl=0.0,
            status="OPEN",
            defensive_shields=[],
            defending_fvg_ce=2702.0,
            session_origin="NEW_YORK_AM"
        )
        self.om._sync_position(pos)

        # Candle closing at 2702.8 (violating 50% CE of 2702.0)
        violating_bar = Candle(
            timestamp=datetime.datetime(2026, 11, 10, 13, 35, tzinfo=datetime.timezone.utc),
            timestamp_et=datetime.datetime(2026, 11, 10, 8, 35),
            open=2701.0, high=2703.0, low=2700.5, close=2702.8, volume=100
        )

        closed = self.om.update_positions_with_bar("GOLD", violating_bar)
        self.assertEqual(len(closed), 1, "Should have triggered early scratch exit")
        tr = closed[0]
        self.assertEqual(tr.outcome, "EARLY_SCRATCH")
        self.assertEqual(tr.invalidation_reason, "50_PCT_CE_BREACH")

    def test_session_expiration_exit(self):
        """
        In a London position with exit deadline 06:00 EST.
        If current bar time is 06:05 EST, it MUST be liquidated at market.
        """
        pos = Position(
            position_id="session_exp_1",
            asset="EURUSD",
            direction="LONG",
            quantity=1,
            entry_price=1.0850,
            entry_time=datetime.datetime(2026, 11, 10, 3, 30),
            initial_stop_loss=1.0830,
            active_trailing_stop=1.0830,
            target_center_mass=1.0880,
            target_head_shot=1.0910,
            center_mass_filled=False,
            head_shot_filled=False,
            realized_pnl=0.0,
            status="OPEN",
            defensive_shields=[],
            defending_fvg_ce=1.0840,
            session_origin="LONDON"
        )
        self.om._sync_position(pos)

        # Candle at 06:00:00 EST
        expired_bar = Candle(
            timestamp=datetime.datetime(2026, 11, 10, 11, 0, tzinfo=datetime.timezone.utc),
            timestamp_et=datetime.datetime(2026, 11, 10, 6, 0),
            open=1.0860, high=1.0865, low=1.0855, close=1.0862, volume=100
        )

        closed = self.om.update_positions_with_bar("EURUSD", expired_bar)
        self.assertEqual(len(closed), 1, "Should have closed on session deadline")
        self.assertEqual(closed[0].outcome, "SESSION_EXPIRATION")

    def test_session_debrief_generation_and_persistence(self):
        """
        Verifies synthesis of session debrief with high/low, Asian sweep classification, and DB storage.
        """
        c1 = Candle(datetime.datetime.now(), datetime.datetime(2026, 11, 10, 21, 0), 1.0800, 1.0840, 1.0790, 1.0820, 100)
        c2 = Candle(datetime.datetime.now(), datetime.datetime(2026, 11, 10, 3, 0), 1.0820, 1.0860, 1.0810, 1.0815, 100) # swept Asian High 1.0840
        
        tr = TradeRecord("t1", "EURUSD", "LONDON", "SHORT", "2026-11-10 03:00:00", 1.0850, "2026-11-10 04:00:00", 1.0815, 0.0010, 0.0035, 35.0, "FULL_WIN", "Clean expansion")

        debrief = self.ipda.generate_session_debrief("LONDON", [c1, c2], [tr], "2026-11-10")
        self.assertEqual(debrief.session_name, "LONDON")
        self.assertEqual(debrief.asian_sweep_type, "ASIAN_BSL_SWEPT")
        self.assertEqual(debrief.cross_session_bias, "BEARISH_EXPANSION_CONTINUATION")

        self.storage.record_session_debrief(debrief)
        loaded = self.storage.get_latest_session_debrief("LONDON")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["cross_session_bias"], "BEARISH_EXPANSION_CONTINUATION")

if __name__ == "__main__":
    unittest.main()
