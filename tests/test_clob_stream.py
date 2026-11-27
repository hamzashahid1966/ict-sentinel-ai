import time
import unittest
from unittest.mock import MagicMock

from polymarket_sentinel.crypto_5m.clob_stream import ClobBookStream, needs_decoding
from polymarket_sentinel.crypto_5m.round_analyzer import MultiCryptoRoundAnalyzer


class TestClobStream(unittest.TestCase):
    def stream(self):
        s = ClobBookStream()
        s._connected = True                       # pretend the socket is open (no network in tests)
        return s

    def test_book_and_updates(self):
        s = self.stream()
        self.assertIsNone(s.top("tok"))           # asked before any data: registers the token, no answer
        self.assertIn("tok", s._pending)
        s.handle({"event_type": "book", "asset_id": "tok", "bids": [{"price": "0.48", "size": "5"}, {"price": "0.49", "size": "1"}],
                  "asks": [{"price": "0.52", "size": "2"}, {"price": "0.51", "size": "3"}], "timestamp": "1"})
        self.assertEqual(s.top("tok"), (0.49, 0.51))
        s.handle({"event_type": "best_bid_ask", "asset_id": "tok", "best_bid": "0.55", "best_ask": "0.56"})
        self.assertEqual(s.top("tok"), (0.55, 0.56))
        s.handle({"event_type": "price_change", "market": "m", "price_changes": [
            {"asset_id": "tok", "price": "0.57", "size": "4", "side": "BUY", "best_bid": "0.57", "best_ask": "0.58"}]})
        self.assertEqual(s.top("tok"), (0.57, 0.58))

    def test_unhealthy_stream_answers_nothing(self):
        s = self.stream()
        s.handle({"event_type": "best_bid_ask", "asset_id": "tok", "best_bid": "0.4", "best_ask": "0.41"})
        s._last_msg = time.time() - 60            # silent for a minute
        self.assertIsNone(s.top("tok"))
        s._connected = False
        s._last_msg = time.time()
        self.assertIsNone(s.top("tok"))

    def test_late_stream_answers_nothing(self):
        s = self.stream()
        now_ms = time.time() * 1000
        s.handle({"event_type": "best_bid_ask", "asset_id": "tok", "best_bid": "0.4", "best_ask": "0.41",
                  "timestamp": str(int(now_ms - 500))})
        self.assertEqual(s.top("tok"), (0.4, 0.41))             # half a second behind: fine
        s.handle({"event_type": "best_bid_ask", "asset_id": "tok", "best_bid": "0.3", "best_ask": "0.31",
                  "timestamp": str(int(now_ms - 20000))})
        self.assertGreater(s.lag, 19)
        self.assertIsNone(s.top("tok"))                         # 20 s behind: let the analyzer use REST
        s.handle({"event_type": "best_bid_ask", "asset_id": "tok", "best_bid": "0.35", "best_ask": "0.36",
                  "timestamp": str(int(time.time() * 1000))})
        self.assertEqual(s.top("tok"), (0.35, 0.36))            # caught up again

    def test_price_change_frames_are_skipped_others_decoded(self):
        self.assertFalse(needs_decoding('{"market":"m","price_changes":[{"asset_id":"t","best_bid":"0.5"}],'
                                        '"timestamp":"1","event_type":"price_change"}'))
        self.assertTrue(needs_decoding('{"event_type":"best_bid_ask","asset_id":"t","best_bid":"0.5","best_ask":"0.51"}'))
        self.assertTrue(needs_decoding('[{"event_type":"book","asset_id":"t","bids":[],"asks":[]}]'))
        self.assertTrue(needs_decoding('[{"event_type":"price_change"},{"event_type":"best_bid_ask"}]'))
        self.assertTrue(needs_decoding('{"event_type":"last_trade_price","price":"0.5"}'))

    def test_analyzer_prefers_stream_and_falls_back_to_rest(self):
        an = MultiCryptoRoundAnalyzer.__new__(MultiCryptoRoundAnalyzer)
        an._book_cache = {}
        an._http_json = MagicMock(return_value={"bids": [{"price": "0.30", "size": "1"}], "asks": [{"price": "0.32", "size": "1"}]})
        an.live_book = self.stream()
        an.live_book.handle({"event_type": "best_bid_ask", "asset_id": "tok", "best_bid": "0.61", "best_ask": "0.62"})
        book = an._fetch_clob_book("tok")
        self.assertEqual((book["bids"][0]["price"], book["asks"][0]["price"], book["source"]), ("0.61", "0.62", "ws"))
        an._http_json.assert_not_called()
        an.live_book._connected = False             # stream down: REST as before
        book = an._fetch_clob_book("tok")
        self.assertEqual(book["asks"][0]["price"], "0.32")
        an._http_json.assert_called_once()


if __name__ == "__main__":
    unittest.main()
