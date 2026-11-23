"""
Unit tests for NextSessionPredictor.
Validates candle anatomy parsing, momentum clustering, ICT sweep rejections, and confidence synthesis.
"""

import unittest
from unittest.mock import MagicMock
from polymarket_sentinel.crypto_5m.session_predictor import NextSessionPredictor


class TestNextSessionPredictor(unittest.TestCase):
    def setUp(self):
        self.mock_feed = MagicMock()
        self.mock_feed.get_price.return_value = 60000.0
        self.mock_feed._tick_history = {"BTC": [], "ETH": [], "SOL": [], "XRP": []}
        self.predictor = NextSessionPredictor(self.mock_feed)

    def test_bullish_expansion_prediction(self):
        """When prior 5M candle has strong green body (>65% ratio) with small wicks, forecast must be UP."""
        cur_round_ts = 1700000100  # Exactly divisible by 300
        prev_start = cur_round_ts - 300

        # Construct ticks for prior candle: opens at 60000, low 59990, high 60055, closes at 60050
        ticks = [
            (prev_start + 10, 60000.0),
            (prev_start + 50, 59990.0),
            (prev_start + 200, 60055.0),
            (prev_start + 290, 60050.0),
            # Current candle ticks
            (cur_round_ts + 10, 60051.0),
            (cur_round_ts + 20, 60053.0)
        ]
        self.mock_feed._tick_history["BTC"] = ticks
        self.mock_feed.get_price.return_value = 60053.0

        res = self.predictor.predict_coin("BTC", now_ts=cur_round_ts + 20)
        self.assertEqual(res["prediction"], "UP")
        self.assertGreaterEqual(res["confidence"], 68.0)
        self.assertIn("Green", res["catalyst"])

    def test_bearish_expansion_prediction(self):
        """When prior 5M candle has strong red body (>65% ratio) dropping $50, forecast must be DOWN."""
        cur_round_ts = 1700000100  # Exactly divisible by 300
        prev_start = cur_round_ts - 300

        # Construct ticks for prior candle: opens at 60050, high 60055, low 59990, closes at 60000
        ticks = [
            (prev_start + 10, 60050.0),
            (prev_start + 50, 60055.0),
            (prev_start + 200, 59990.0),
            (prev_start + 290, 60000.0),
            # Current candle ticks
            (cur_round_ts + 10, 59998.0),
            (cur_round_ts + 20, 59995.0)
        ]
        self.mock_feed._tick_history["BTC"] = ticks
        self.mock_feed.get_price.return_value = 59995.0

        res = self.predictor.predict_coin("BTC", now_ts=cur_round_ts + 20)
        self.assertEqual(res["prediction"], "DOWN")
        self.assertGreaterEqual(res["confidence"], 68.0)
        self.assertIn("Red", res["catalyst"])

    def test_ict_turtle_soup_wick_reversal(self):
        """When prior 5M candle spiked high but rejected with a long upper wick, forecast must predict DOWN reversal."""
        cur_round_ts = 1700000100  # Exactly divisible by 300
        prev_start = cur_round_ts - 300

        # Opens at 60000, spikes to 60080 (long wick), but closes at 60005 (body only $5, upper wick $75)
        ticks = [
            (prev_start + 10, 60000.0),
            (prev_start + 150, 60080.0),
            (prev_start + 290, 60005.0),
            # Current candle ticks pushing down
            (cur_round_ts + 10, 60002.0),
            (cur_round_ts + 20, 59998.0)
        ]
        self.mock_feed._tick_history["BTC"] = ticks
        self.mock_feed.get_price.return_value = 59998.0

        res = self.predictor.predict_coin("BTC", now_ts=cur_round_ts + 20)
        self.assertEqual(res["prediction"], "DOWN")
        self.assertIn("Turtle Soup", res["catalyst"])

    def test_predict_all_coins(self):
        """Predicts across BTC, ETH, SOL, XRP and returns dictionary with metrics."""
        res = self.predictor.predict_all_coins(now_ts=1700000100)
        self.assertIn("BTC", res)
        self.assertIn("ETH", res)
        self.assertIn("SOL", res)
        self.assertIn("XRP", res)
        for sym in ["BTC", "ETH", "SOL", "XRP"]:
            self.assertIn("prediction", res[sym])
            self.assertIn("confidence", res[sym])


if __name__ == "__main__":
    unittest.main()


class TestPriorCandleHistoryCoverage(unittest.TestCase):
    """
    The predictor runs ~5s before a round opens. At that moment the candle it calls
    "prior" ended ~5 minutes ago, so the feed must still hold it, and the predictor must
    refuse to read a candle out of a handful of leftover ticks.
    """

    R = 1700000100  # round that is about to open (divisible by 300)

    def _predictor(self, ticks, spot):
        feed = MagicMock()
        feed.get_price.return_value = spot
        feed._tick_history = {"BTC": ticks, "ETH": [], "SOL": [], "XRP": []}
        return NextSessionPredictor(feed)

    def test_feed_keeps_enough_history_for_the_prior_candle_at_prediction_time(self):
        from unittest.mock import patch
        from polymarket_sentinel.crypto_5m import price_feed as pf
        feed = pf.MultiCryptoPriceFeed(start_background=False, use_chainlink=False)
        start = float(self.R - 900)
        with patch.object(feed, "_fetch_binance_batch", side_effect=lambda: {"BTC": 60000.0}), \
             patch.object(feed, "_fetch_coinbase", return_value={}):
            for i in range(0, 896, 1):
                with patch.object(pf.time, "time", return_value=start + i):
                    feed._refresh_prices()
        now = start + 895  # R-5
        cur_round = (int(now) // 300) * 300
        prior_window = [t for t, _ in feed._tick_history["BTC"] if cur_round - 300 <= t < cur_round]
        self.assertGreaterEqual(len(prior_window), 290)
        self.assertLessEqual(min(prior_window), cur_round - 300 + 5)

    def test_prior_candle_with_only_a_few_leftover_ticks_is_not_called(self):
        now = self.R - 5
        cur = self.R - 300
        # Only the last 5 seconds of the prior window survived: a 2-dollar drop that
        # used to be read as a "strong Red 100% body" candle.
        ticks = [(cur - 5, 60002.0), (cur - 3, 60001.0), (cur - 1, 60000.0)]
        ticks += [(cur + s, 60000.0 + 0.01 * s) for s in range(0, 295)]
        res = self._predictor(ticks, ticks[-1][1]).predict_coin("BTC", now_ts=now)
        self.assertEqual(res["prediction"], "NEUTRAL")
        self.assertNotIn("strong", res["catalyst"])
        self.assertIn("history", res["catalyst"].lower())

    def test_empty_history_gives_neutral_not_a_simulated_candle_call(self):
        res = self._predictor([], 60000.0).predict_coin("BTC", now_ts=self.R - 5)
        self.assertEqual(res["prediction"], "NEUTRAL")
        self.assertIn("history", res["catalyst"].lower())

    def test_full_one_second_history_reads_the_real_prior_candle(self):
        now = self.R - 5
        cur = self.R - 300
        prev = cur - 300
        # Prior candle: clean 60-dollar green expansion; forming candle drifts up.
        ticks = [(prev - 300 + s, 60000.0) for s in range(300)]
        ticks += [(prev + s, 60000.0 + 0.2 * s) for s in range(300)]
        ticks += [(cur + s, 60060.0 + 0.01 * s) for s in range(296)]
        res = self._predictor(ticks, ticks[-1][1]).predict_coin("BTC", now_ts=now)
        self.assertEqual(res["prediction"], "UP")
        self.assertIn("Green", res["catalyst"])
        self.assertAlmostEqual(res["metrics"]["prev_move"], 59.8, places=1)
