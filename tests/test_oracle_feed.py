"""
Oracle Feed Integrity Tests for the Polymarket 5M scalper.

Polymarket Up/Down markets resolve on Chainlink's BTC/USD 60-second TWAP, not on
Binance BTCUSDT. These tests pin down three behaviours:
1. The legacy RTDS frames carrying Chainlink spot / TWAP parse into (topic, coin, ts, value).
2. The exchange price feed never fabricates ticks and never reports itself warm
   until a real exchange print has arrived (the hard-coded fallback price must
   never become a strike).
3. The round analyzer abstains and locks no strike while the feed is cold.
"""

import json
import time
import unittest
from unittest.mock import MagicMock, patch

from polymarket_sentinel.crypto_5m.chainlink_feed import parse_rtds_frame
from polymarket_sentinel.crypto_5m.price_feed import MultiCryptoPriceFeed, DEFAULT_FALLBACK_PRICES
from polymarket_sentinel.crypto_5m.round_analyzer import MultiCryptoRoundAnalyzer


class TestRtdsFrameParser(unittest.TestCase):
    def test_parses_snapshot_frame_into_per_second_points(self):
        frame = json.dumps({
            "topic": "crypto_prices_twap_sixty", "type": "subscribe",
            "payload": {"symbol": "btc/usd", "data": [
                {"timestamp": 1795371180000, "value": 60625.88},
                {"timestamp": 1795371181000, "value": 60626.10},
            ]},
        })
        points = parse_rtds_frame(frame)
        self.assertEqual(points, [
            ("crypto_prices_twap_sixty", "BTC", 1795371180.0, 60625.88),
            ("crypto_prices_twap_sixty", "BTC", 1795371181.0, 60626.10),
        ])

    def test_parses_live_update_frame_and_normalises_symbol(self):
        frame = json.dumps({
            "connection_id": "x", "topic": "crypto_prices_chainlink", "type": "update",
            "timestamp": 1795371283000,
            "payload": {"full_accuracy_value": "70320955590940875000", "symbol": "sol/usd",
                        "timestamp": 1795371283000, "value": 70.32095559},
        })
        self.assertEqual(parse_rtds_frame(frame),
                         [("crypto_prices_chainlink", "SOL", 1795371283.0, 70.32095559)])

    def test_ignores_non_price_frames(self):
        self.assertEqual(parse_rtds_frame("PONG"), [])
        self.assertEqual(parse_rtds_frame(json.dumps({"message": "Invalid request body"})), [])


class TestExchangeFeedIntegrity(unittest.TestCase):
    def _cold_feed(self):
        return MultiCryptoPriceFeed(start_background=False, use_chainlink=False)

    def test_feed_is_cold_and_has_no_ticks_before_any_real_print(self):
        feed = self._cold_feed()
        self.assertFalse(feed.is_warm("BTC"))
        self.assertEqual(feed._tick_history["BTC"], [])

    def test_offline_refresh_does_not_fabricate_ticks(self):
        feed = self._cold_feed()
        with patch.object(feed, "_fetch_binance_batch", return_value={}), \
             patch.object(feed, "_fetch_coinbase", return_value={}):
            feed._refresh_prices()
            feed._refresh_prices()
        self.assertEqual(feed._tick_history["BTC"], [])
        self.assertFalse(feed.is_warm("BTC"))

    def test_feed_warms_only_on_real_exchange_print(self):
        feed = self._cold_feed()
        real = {"BTC": 60700.0, "ETH": 1712.0, "SOL": 70.3, "XRP": 0.928}
        with patch.object(feed, "_fetch_binance_batch", return_value=real):
            feed._refresh_prices()
        self.assertTrue(feed.is_warm("BTC"))
        self.assertEqual(feed.get_price("BTC"), 60700.0)
        self.assertNotEqual(feed.get_twap_price("BTC"), DEFAULT_FALLBACK_PRICES["BTC"])

    def test_oracle_analysis_prefers_fresh_chainlink_series(self):
        feed = self._cold_feed()
        with patch.object(feed, "_fetch_binance_batch", return_value={"BTC": 60700.0, "ETH": 1.0, "SOL": 1.0, "XRP": 1.0}):
            feed._refresh_prices()
        chainlink = MagicMock()
        chainlink.get_spot.return_value = (60615.0, 1.0)   # (value, age_seconds)
        chainlink.get_twap.return_value = (60592.0, 1.0)
        feed.chainlink = chainlink

        oracle = feed.get_oracle_analysis("BTC")
        self.assertEqual(oracle["source"], "chainlink")
        self.assertEqual(oracle["spot"], 60615.0)
        self.assertEqual(oracle["twap"], 60592.0)
        self.assertEqual(oracle["exchange_spot"], 60700.0)

    def test_oracle_analysis_falls_back_to_exchange_when_chainlink_stale(self):
        feed = self._cold_feed()
        with patch.object(feed, "_fetch_binance_batch", return_value={"BTC": 60700.0, "ETH": 1.0, "SOL": 1.0, "XRP": 1.0}):
            feed._refresh_prices()
        chainlink = MagicMock()
        chainlink.get_spot.return_value = (60615.0, 45.0)  # 45s old: stale
        chainlink.get_twap.return_value = (60592.0, 45.0)
        feed.chainlink = chainlink

        oracle = feed.get_oracle_analysis("BTC")
        self.assertEqual(oracle["source"], "binance")
        self.assertEqual(oracle["spot"], 60700.0)


class TestBinanceBatchRequest(unittest.TestCase):
    def test_batch_url_has_no_whitespace_in_symbols_parameter(self):
        """Binance rejects any whitespace (raw or %20) inside the symbols JSON array with HTTP 400."""
        feed = MultiCryptoPriceFeed(start_background=False, use_chainlink=False)
        url = feed._binance_batch_url()
        self.assertNotIn(" ", url)
        self.assertNotIn("%20", url)
        self.assertIn("BTCUSDT", url)
        self.assertIn("XRPUSDT", url)


class TestAnalyzerStrikeGuard(unittest.TestCase):
    def test_cold_feed_abstains_and_locks_no_strike(self):
        feed = MagicMock(spec=MultiCryptoPriceFeed)
        feed.is_warm.return_value = False
        feed.get_oracle_analysis.return_value = {
            "spot": DEFAULT_FALLBACK_PRICES["BTC"], "twap": DEFAULT_FALLBACK_PRICES["BTC"],
            "lag_delta": 0.0, "projected_twap": DEFAULT_FALLBACK_PRICES["BTC"],
            "source": "binance", "exchange_spot": DEFAULT_FALLBACK_PRICES["BTC"],
        }
        feed.get_volatility.return_value = 15.0
        analyzer = MultiCryptoRoundAnalyzer(feed)
        round_ts = (int(time.time()) // 300) * 300
        with patch.object(analyzer, "fetch_polymarket_market", return_value={
            "found": False, "slug": f"btc-updown-5m-{round_ts}", "title": "t", "price_up": 0.5, "price_down": 0.5,
            "accepting_orders": True, "closed": False, "resolution_status": "", "winning_outcome": None,
            "price_to_beat": None, "end_date_iso": None, "clob_token_ids": None,
        }):
            r = analyzer.analyze_single_coin("BTC", round_ts + 120, round_ts)

        self.assertEqual(r.signal, "ABSTAIN")
        self.assertIn("warming", r.signal_reason.lower())
        self.assertEqual(analyzer._strike_prices, {})


if __name__ == "__main__":
    unittest.main()
