import os
import tempfile
import unittest
from unittest import mock

from research import trend_paper as tp


class TestTrendOnServer(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.dir.name, "disk", "trend_paper.db")

    def tearDown(self):
        self.dir.cleanup()

    def test_new_disk_starts_from_seed_once(self):
        seed = os.path.join(self.dir.name, "seed.db")
        with open(seed, "wb") as f:
            f.write(b"seed-bytes")
        self.assertTrue(tp.ensure_db(self.db, seed))
        with open(self.db, "rb") as f:
            self.assertEqual(f.read(), b"seed-bytes")
        with open(self.db, "wb") as f:
            f.write(b"progress")
        self.assertFalse(tp.ensure_db(self.db, seed))          # never overwrites a running test
        with open(self.db, "rb") as f:
            self.assertEqual(f.read(), b"progress")

    def test_check_writes_a_line_last_run_reads(self):
        with mock.patch.object(tp, "run_once", return_value=["T2_SMA50_LS 2026-11-25 live"]):
            line = tp.scheduled_check(self.db, market=object(), now=1795651500)
        self.assertTrue(line.startswith("[2026-"))
        self.assertEqual(tp.last_run(os.path.join(os.path.dirname(self.db), "trend_paper.log")), line[1:20])

    def test_network_error_is_logged_but_not_counted_as_a_check(self):
        with mock.patch.object(tp, "run_once", side_effect=OSError("no route")):
            line = tp.scheduled_check(self.db, market=object(), now=1795651500)
        self.assertTrue(line.startswith("! ["))
        self.assertIsNone(tp.last_run(os.path.join(os.path.dirname(self.db), "trend_paper.log")))

    def test_failed_attempt_is_reported(self):
        log = os.path.join(os.path.dirname(self.db), "trend_paper.log")
        with mock.patch.object(tp, "run_once", side_effect=OSError("no route")):
            tp.scheduled_check(self.db, market=object(), now=1795651500)
        self.assertIn("no route", tp.last_check_problem(log))
        with mock.patch.object(tp, "run_once", return_value=[]):
            tp.scheduled_check(self.db, market=object(), now=1795655100)
        self.assertIsNone(tp.last_check_problem(log))

    def test_scheduler_off_unless_asked(self):
        from ict_sentinel import web_server
        with mock.patch.dict(os.environ, {"TREND_PAPER_SCHEDULER": "0"}):
            self.assertIsNone(web_server.start_trend_scheduler())


if __name__ == "__main__":
    unittest.main()
