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

    def test_rate_limit_reply_is_reported_without_hammering(self):
        import io
        import urllib.error
        err = urllib.error.HTTPError("u", 418, "I'm a teapot", {}, io.BytesIO(b'{"code":-1003,"msg":"IP banned until 1"}'))
        with mock.patch("urllib.request.urlopen", side_effect=err) as op, mock.patch("time.sleep") as sl:
            with self.assertRaises(RuntimeError) as cm:
                tp.BinanceMarket()._get("https://example.invalid")
        self.assertIn("-1003", str(cm.exception))
        self.assertEqual(op.call_count, 1)                     # no retry storm on a ban
        sl.assert_not_called()

    def test_ban_time_is_read_and_respected(self):
        import io
        import urllib.error
        until_ms = 1795717854860
        body = ('{"code":-1003,"msg":"Way too many requests; IP(1.2.3.4) banned until %d. Please use the websocket"}'
                % until_ms).encode()
        err = urllib.error.HTTPError("u", 418, "I'm a teapot", {}, io.BytesIO(body))
        self.addCleanup(setattr, tp, "BAN_UNTIL", 0.0)
        tp.BAN_UNTIL = 0.0
        with mock.patch("urllib.request.urlopen", side_effect=err), mock.patch("time.time", return_value=1795610000):
            with self.assertRaises(RuntimeError):
                tp.BinanceMarket()._get("https://example.invalid")
        self.assertAlmostEqual(tp.BAN_UNTIL, until_ms / 1000)
        with mock.patch("urllib.request.urlopen") as op, mock.patch("time.time", return_value=1795610100):
            self.assertGreater(tp.retry_wait(), 100000)
            with self.assertRaises(RuntimeError):
                tp.BinanceMarket()._get("https://example.invalid")
            op.assert_not_called()                              # no request while banned
        with mock.patch("time.time", return_value=until_ms / 1000 + 1):
            self.assertEqual(tp.retry_wait(), 0.0)

    def test_429_uses_retry_after(self):
        self.assertEqual(tp.ban_until_from(429, "slow down", "30", now=1000), 1060)    # at least 60 s
        self.assertEqual(tp.ban_until_from(429, "slow down", "600", now=1000), 1600)

    def test_scheduler_off_unless_asked(self):
        from ict_sentinel import web_server
        with mock.patch.dict(os.environ, {"TREND_PAPER_SCHEDULER": "0"}):
            self.assertIsNone(web_server.start_trend_scheduler())


if __name__ == "__main__":
    unittest.main()
