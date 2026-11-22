"""
Tests for the Polymarket 5m round recorder: per-round comparison of
Chainlink (resolution series), Binance (USDT tape), Coinbase (USD tape, the
closest public proxy for TradingView's USD index) and the Polymarket odds.
"""

import unittest

from polymarket_sentinel.crypto_5m.round_recorder import (
    value_at, summarize_round, aggregate_report, format_round_line,
)


def _series(start_ts, values, step=1.0):
    return [(start_ts + i * step, v) for i, v in enumerate(values)]


class TestValueAt(unittest.TestCase):
    def test_returns_nearest_sample_within_tolerance(self):
        s = _series(1000.0, [10.0, 11.0, 12.0])
        self.assertEqual(value_at(s, 1001.4), 11.0)

    def test_returns_none_when_no_sample_is_close_enough(self):
        s = _series(1000.0, [10.0, 11.0])
        self.assertIsNone(value_at(s, 1010.0, tolerance=2.0))


class TestSummarizeRound(unittest.TestCase):
    def setUp(self):
        self.round_ts = 1795372200  # 18:30 UTC
        end = self.round_ts + 300
        # Chainlink TWAP: 60,589 at open, 60,601 at close -> UP
        self.series = {
            "chainlink_twap": [(self.round_ts, 60589.45), (self.round_ts + 150, 60595.0), (end, 60601.0)],
            "chainlink_spot": [(self.round_ts, 60592.0), (end, 60600.0)],
            "binance": [(self.round_ts, 60678.76), (end, 60690.0)],
            "coinbase": [(self.round_ts, 60581.91), (end, 60598.0)],
            "clob_up": [(self.round_ts + 1, 0.50), (self.round_ts + 150, 0.62), (end - 1, 0.97)],
        }

    def test_builds_comparison_against_chainlink_open(self):
        s = summarize_round("BTC", self.round_ts, self.series, official={"price_to_beat": 60589.45, "outcome": "UP"})
        self.assertEqual(s.coin, "BTC")
        self.assertEqual(s.chainlink_twap_open, 60589.45)
        self.assertEqual(s.binance_open, 60678.76)
        self.assertAlmostEqual(s.binance_minus_chainlink_open, 89.31, places=2)
        self.assertAlmostEqual(s.coinbase_minus_chainlink_open, -7.54, places=2)
        self.assertEqual(s.outcome_from_twap, "UP")
        self.assertEqual(s.outcome_official, "UP")
        self.assertAlmostEqual(s.official_minus_our_strike, 0.0, places=2)
        self.assertEqual(s.clob_up_open, 0.50)
        self.assertEqual(s.clob_up_close, 0.97)

    def test_down_outcome_and_missing_official_data(self):
        self.series["chainlink_twap"][-1] = (self.round_ts + 300, 60580.0)
        s = summarize_round("BTC", self.round_ts, self.series, official={})
        self.assertEqual(s.outcome_from_twap, "DOWN")
        self.assertIsNone(s.outcome_official)
        self.assertIsNone(s.official_minus_our_strike)

    def test_format_line_mentions_outcome_and_gaps(self):
        s = summarize_round("BTC", self.round_ts, self.series, official={"price_to_beat": 60589.45, "outcome": "UP"})
        line = format_round_line(s)
        self.assertIn("BTC", line)
        self.assertIn("UP", line)
        self.assertIn("+89.31", line)


class TestAggregateReport(unittest.TestCase):
    def test_reports_mean_gaps_and_agreement(self):
        rts = 1795372200
        base = {
            "chainlink_twap": [(rts, 100.0), (rts + 300, 101.0)],
            "chainlink_spot": [(rts, 100.0), (rts + 300, 101.0)],
            "binance": [(rts, 100.3), (rts + 300, 101.3)],
            "coinbase": [(rts, 99.9), (rts + 300, 100.9)],
            "clob_up": [(rts + 1, 0.5), (rts + 299, 0.9)],
        }
        a = summarize_round("BTC", rts, base, official={"price_to_beat": 100.0, "outcome": "UP"})
        b = summarize_round("BTC", rts + 300, {k: [(t + 300, v) for t, v in s] for k, s in base.items()},
                            official={"price_to_beat": 100.05, "outcome": "DOWN"})
        rep = aggregate_report([a, b])
        self.assertEqual(rep["rounds"], 2)
        self.assertAlmostEqual(rep["mean_binance_minus_chainlink_open"], 0.3, places=6)
        self.assertAlmostEqual(rep["mean_coinbase_minus_chainlink_open"], -0.1, places=6)
        self.assertEqual(rep["twap_vs_official_agreement"], 0.5)
        self.assertAlmostEqual(rep["mean_abs_official_minus_our_strike"], 0.025, places=6)


if __name__ == "__main__":
    unittest.main()
