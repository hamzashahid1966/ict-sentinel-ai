"""Fallback to Binance's public daily files while the API has banned the server's IP."""
import os
import tempfile
import unittest
from unittest import mock

from research import trend_paper as tp
from tests.test_trend_paper import DAY, FakeMarket, book


class NoQuoteMarket(FakeMarket):
    live_quotes = False

    def quote(self, coin):
        raise AssertionError("an archive market must never be asked for live quotes")


class TestArchiveFallback(unittest.TestCase):
    def test_archive_days_are_traded_at_the_close_not_live(self):
        m, b = NoQuoteMarket(), book()
        tp.run_once(b, m, now=m.last_open() + DAY + 3600, variants={"LS": (50, False)}, coins=["UP", "DOWN"],
                    capital=1000.0)
        fills = b.fills("LS")
        self.assertTrue(fills)
        self.assertEqual({f["mode"] for f in fills}, {"catchup"})

    def test_parses_published_daily_files(self):
        now = 1795651200 + 5 * 3600                           # 2026-11-26 05:00 UTC
        a = tp.ArchiveMarket(cache_dir=tempfile.mkdtemp(), now=now)
        header = "open_time,open,high,low,close,volume,close_time,quote_volume,count,taker_buy_volume,taker_buy_quote_volume,ignore\n"
        def fake(url):
            if "/daily/klines/" in url and url.endswith("2026-11-24.zip"):
                return header + "1795478400000,61240.00,61663.10,59251.00,59801.30,1,1795564799999,1,1,1,1,0\n"
            return None                                         # not published
        with mock.patch.object(a, "_file", side_effect=fake):
            rows = a.daily_ohlc("BTC", 30)
        self.assertEqual(rows, [(1795478400, 61240.0, 61663.1, 59251.0, 59801.3)])
        self.assertEqual(a.daily("BTC", 30), [(1795478400, 59801.3)])
        self.assertRaises(RuntimeError, a.quote, "BTC")

    def test_check_switches_to_archive_when_banned(self):
        d = tempfile.mkdtemp()
        db = os.path.join(d, "t.db")
        self.addCleanup(setattr, tp, "BAN_UNTIL", 0.0)
        tp.BAN_UNTIL = 0.0
        calls = []

        def fake_run(book, market, now=None):
            calls.append(type(market).__name__)
            if isinstance(market, tp.BinanceMarket):
                tp.BAN_UNTIL = 4e9                               # the API answers 418 mid-run
                raise RuntimeError("Binance HTTP 418")
            return ["LS 2026-11-25 catchup"]

        with mock.patch.object(tp, "run_once", side_effect=fake_run):
            line = tp.scheduled_check(db)
        self.assertEqual(calls, ["BinanceMarket", "ArchiveMarket"])
        self.assertIn("public daily files", line)
        self.assertTrue(line.startswith("[20"))                 # counts as a successful check
        with mock.patch.object(tp, "run_once", side_effect=fake_run):
            tp.scheduled_check(db)
        self.assertEqual(calls[-1], "ArchiveMarket")            # still banned: straight to the archive


if __name__ == "__main__":
    unittest.main()
