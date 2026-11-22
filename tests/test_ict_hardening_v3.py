"""
ICT Sentinel hardening, round 3:
1. The drawdown circuit breaker is a DAILY budget measured from the day's opening
   balance, so it releases on the next trading day instead of locking forever.
2. The IPDA engine refuses to evaluate stale bars when told the current time.
3. The permanent learning ledger is isolated: the knowledge directory can be
   redirected by environment, and the memory engine can be told not to persist.
"""

import datetime
import os
import tempfile
import unittest
import tests  # noqa: F401  (bootstraps ICT_KNOWLEDGE_DIR so test trades never touch the real ledger)
from unittest.mock import MagicMock

from ict_sentinel.config import NY_TZ
from ict_sentinel.storage import StorageEngine
from ict_sentinel.ai_advisor import AIAdvisor
from ict_sentinel.memory_engine import MemoryEngine
from ict_sentinel.order_manager import OrderManager
from ict_sentinel.ipda_engine import IPDAEngine, AlgorithmicSignal
from ict_sentinel.knowledge_engine import KnowledgeEngine
from ict_sentinel.models import Candle, PDArray, Position, TradeRecord


def _signal(asset="GOLD"):
    return AlgorithmicSignal(
        asset=asset, session="LONDON", direction="SHORT", entry_price=3770.0, stop_loss=3773.0,
        risk_pts=3.0, target_center_mass=3765.0, target_head_shot=3761.0,
        pd_array=PDArray("SIBI", 3772.0, 3770.0, 3771.0, datetime.datetime.now()), ai_rationale="t",
    )


class TestDailyDrawdownBudget(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.storage = StorageEngine(db_path=self.tmp.name)
        self.advisor = AIAdvisor()
        self.memory = MemoryEngine(self.storage, self.advisor, persist_knowledge=False)
        self.order_mgr = OrderManager(self.storage, self.advisor, memory_engine=self.memory)

    def tearDown(self):
        self.storage.close()
        os.unlink(self.tmp.name)

    def test_loss_today_blocks_today_but_releases_tomorrow(self):
        day1 = datetime.datetime(2026, 11, 18, 10, 0, tzinfo=NY_TZ)
        day2 = day1 + datetime.timedelta(days=1)

        # Anchor the day, then lose $55 within it.
        self.assertEqual(self.storage.get_daily_drawdown(day1.date().isoformat()), 0.0)
        self.storage.update_account_balance(-55.0, day_str=day1.date().isoformat())
        self.assertAlmostEqual(self.storage.get_daily_drawdown(day1.date().isoformat()), 55.0)
        self.assertIsNone(self.order_mgr.open_position_from_signal(_signal(), day1), "same-day loss must block")

        # Next day: budget resets from the new opening balance, trading resumes.
        self.assertEqual(self.storage.get_daily_drawdown(day2.date().isoformat()), 0.0)
        pos = self.order_mgr.open_position_from_signal(_signal(), day2)
        self.assertIsNotNone(pos, "breaker must release on the next trading day")


class TestStaleBarGuard(unittest.TestCase):
    def _candles(self, last_bar_utc: datetime.datetime, n=30):
        out = []
        for i in range(n):
            ts = last_bar_utc - datetime.timedelta(minutes=5 * (n - 1 - i))
            px = 3770.0 + i * 0.1
            out.append(Candle(timestamp=ts, timestamp_et=ts.astimezone(NY_TZ), open=px, high=px + 1, low=px - 1, close=px, volume=1.0))
        return out

    def test_refuses_bars_older_than_limit(self):
        now = datetime.datetime(2026, 11, 18, 14, 0, tzinfo=datetime.timezone.utc)  # 09:00 ET, NY AM window
        stale = self._candles(now - datetime.timedelta(hours=2))
        engine = IPDAEngine()
        self.assertIsNone(engine.evaluate_market("GOLD", stale, now_utc=now))
        self.assertFalse(IPDAEngine.bars_are_fresh(stale, now))

    def test_fresh_bars_pass_the_guard(self):
        now = datetime.datetime(2026, 11, 18, 14, 0, tzinfo=datetime.timezone.utc)
        fresh = self._candles(now - datetime.timedelta(minutes=4))
        self.assertTrue(IPDAEngine.bars_are_fresh(fresh, now))


class TestLearningLedgerIsolation(unittest.TestCase):
    def test_knowledge_dir_can_be_redirected_by_environment(self):
        with tempfile.TemporaryDirectory() as d:
            old = os.environ.get("ICT_KNOWLEDGE_DIR")
            os.environ["ICT_KNOWLEDGE_DIR"] = d
            try:
                ke = KnowledgeEngine()
                self.assertEqual(ke.knowledge_dir, os.path.abspath(d))
                ke.record_learning_episode({"episode_id": "x"})
                self.assertTrue(os.path.exists(os.path.join(d, "04_adaptive_learning_log.json")))
            finally:
                if old is None:
                    os.environ.pop("ICT_KNOWLEDGE_DIR", None)
                else:
                    os.environ["ICT_KNOWLEDGE_DIR"] = old

    def test_memory_engine_can_skip_persisting_to_ledger(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        storage = StorageEngine(db_path=tmp.name)
        try:
            advisor = AIAdvisor()
            advisor.knowledge = MagicMock()
            memory = MemoryEngine(storage, advisor, persist_knowledge=False)
            now = datetime.datetime(2026, 11, 18, 10, 0, tzinfo=NY_TZ)
            tr = TradeRecord("t1", "GOLD", "LONDON", "SHORT", "2026-11-18 09:00:00", 3770.0, "2026-11-18 10:00:00",
                             3765.0, 3.0, 5.0, 48.75, "FULL_WIN", "r")
            pos = Position("t1", "GOLD", "SHORT", 1, 3770.0, now, 3773.0, 3773.0, 3765.0, 3761.0)
            bar = Candle(now.astimezone(datetime.timezone.utc), now, 3765.0, 3766.0, 3764.0, 3765.0, 1.0)
            memory.process_trade_completion(tr, pos, bar)
            advisor.knowledge.record_learning_episode.assert_not_called()
            # DB-side memory still updates, so the demo keeps exercising the Bayesian gate.
            self.assertIsNotNone(storage.get_adaptive_weight("GOLD", "LONDON"))
        finally:
            storage.close()
            os.unlink(tmp.name)


if __name__ == "__main__":
    unittest.main()
