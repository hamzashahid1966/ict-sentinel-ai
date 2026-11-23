"""
Order-flow capture for the 5m round recorder: Binance taker flow and book depth,
Polymarket Up-token book depth, and a report that asks whether flow at a moment in
the round predicts the official outcome better than the market price at that moment.
"""

import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import tests  # noqa: F401  (bootstraps the knowledge dir)
from polymarket_sentinel.crypto_5m import round_recorder as rr


class TestFlowMath(unittest.TestCase):
    def test_taker_flow_splits_by_aggressor_in_quote_currency(self):
        trades = [
            {"a": 1, "p": "100.0", "q": "2.0", "m": False},  # buyer took the ask -> taker buy
            {"a": 2, "p": "101.0", "q": "1.0", "m": True},   # buyer was maker -> taker sell
            {"a": 3, "p": "100.5", "q": "4.0", "m": False},
        ]
        buy, sell = rr.taker_flow(trades)
        self.assertAlmostEqual(buy, 200.0 + 402.0)
        self.assertAlmostEqual(sell, 101.0)

    def test_book_imbalance_and_spread_from_binance_depth(self):
        depth = {"bids": [["100.0", "3"], ["99.9", "1"]], "asks": [["100.1", "1"], ["100.2", "1"]]}
        imb, spread_bps = rr.book_imbalance(depth)
        bid_n, ask_n = 300.0 + 99.9, 100.1 + 100.2
        self.assertAlmostEqual(imb, (bid_n - ask_n) / (bid_n + ask_n), places=6)
        self.assertAlmostEqual(spread_bps, 0.1 / 100.05 * 1e4, places=3)

    def test_book_imbalance_handles_empty_book(self):
        self.assertEqual(rr.book_imbalance({"bids": [], "asks": []}), (None, None))

    def test_clob_book_levels_use_best_prices_regardless_of_order(self):
        book = {"bids": [{"price": "0.40", "size": "10"}, {"price": "0.47", "size": "50"}, {"price": "0.44", "size": "20"}],
                "asks": [{"price": "0.60", "size": "5"}, {"price": "0.49", "size": "30"}, {"price": "0.52", "size": "40"}]}
        lv = rr.clob_book_levels(book, window=0.05)
        self.assertEqual(lv["bid"], 0.47)
        self.assertEqual(lv["ask"], 0.49)
        self.assertAlmostEqual(lv["bid_depth"], 70.0)   # 0.47 and 0.44 are within 5c of 0.47
        self.assertAlmostEqual(lv["ask_depth"], 70.0)   # 0.49 and 0.52
        self.assertAlmostEqual(lv["imbalance"], 0.0)

    def test_clob_book_levels_empty_side(self):
        self.assertIsNone(rr.clob_book_levels({"bids": [], "asks": []}))


class TestRecorderFlowSampling(unittest.TestCase):
    def _rec(self):
        d = tempfile.mkdtemp()
        db = os.path.join(d, "rec.db")
        with patch("polymarket_sentinel.crypto_5m.chainlink_feed.ChainlinkOracleFeed"):
            rec = rr.RoundRecorder(coins=("BTC",), db_path=db)
        return rec, db

    def test_flow_sample_persists_binance_and_polymarket_series(self):
        rec, db = self._rec()
        rec.gamma["BTC"] = {"found": True, "up_token": "TOKEN_UP"}
        rec._agg_last_id["BTC"] = 10
        with patch.object(rec, "_fetch_agg_trades", return_value=[{"a": 11, "p": "100", "q": "1", "m": False},
                                                                     {"a": 12, "p": "100", "q": "3", "m": True}]), \
             patch.object(rec, "_fetch_depth", return_value={"bids": [["100", "2"]], "asks": [["100.1", "1"]]}), \
             patch.object(rec, "_fetch_clob_book", return_value={"bids": [{"price": "0.45", "size": "10"}],
                                                                   "asks": [{"price": "0.47", "size": "30"}]}):
            rec._sample_flow(1795376450.0)
        rows = dict(sqlite3.connect(db).execute("select source, value from ticks").fetchall())
        self.assertEqual(rows["bn_buy_usd"], 100.0)
        self.assertEqual(rows["bn_sell_usd"], 300.0)
        self.assertIn("bn_book_imb", rows)
        self.assertIn("bn_spread_bps", rows)
        self.assertEqual(rows["pm_up_bid"], 0.45)
        self.assertEqual(rows["pm_up_ask"], 0.47)
        self.assertAlmostEqual(rows["pm_book_imb"], (10 - 30) / 40)
        self.assertEqual(rec._agg_last_id["BTC"], 12)

    def test_first_flow_poll_only_anchors_the_trade_id(self):
        rec, db = self._rec()
        with patch.object(rec, "_fetch_agg_trades", return_value=[{"a": 500, "p": "100", "q": "9", "m": False}]), \
             patch.object(rec, "_fetch_depth", return_value=None), \
             patch.object(rec, "_fetch_clob_book", return_value=None):
            rec._sample_flow(1795376450.0)
        sources = [r[0] for r in sqlite3.connect(db).execute("select source from ticks").fetchall()]
        self.assertNotIn("bn_buy_usd", sources)
        self.assertEqual(rec._agg_last_id["BTC"], 500)


    def test_failed_trade_fetch_records_no_flow_rather_than_zero(self):
        rec, db = self._rec()
        rec._agg_last_id["BTC"] = 10
        with patch.object(rec, "_fetch_agg_trades", return_value=None), \
             patch.object(rec, "_fetch_depth", return_value=None), \
             patch.object(rec, "_fetch_clob_book", return_value=None):
            rec._sample_flow(1795376450.0)
        sources = [r[0] for r in sqlite3.connect(db).execute("select source from ticks").fetchall()]
        self.assertNotIn("bn_buy_usd", sources)

    def test_quiet_second_records_zero_flow(self):
        rec, db = self._rec()
        rec._agg_last_id["BTC"] = 10
        with patch.object(rec, "_fetch_agg_trades", return_value=[]), \
             patch.object(rec, "_fetch_depth", return_value=None), \
             patch.object(rec, "_fetch_clob_book", return_value=None):
            rec._sample_flow(1795376450.0)
        rows = dict(sqlite3.connect(db).execute("select source, value from ticks").fetchall())
        self.assertEqual(rows.get("bn_buy_usd"), 0.0)

class TestFlowReport(unittest.TestCase):
    def _round(self, rts, outcome, flow_sign):
        end = rts + 300
        s = {"bn_buy_usd": [], "bn_sell_usd": [], "pm_up_bid": [], "pm_up_ask": [], "bn_book_imb": [], "pm_book_imb": []}
        for t in range(rts, end + 1):
            s["bn_buy_usd"].append((t, 1000.0 if flow_sign > 0 else 200.0))
            s["bn_sell_usd"].append((t, 200.0 if flow_sign > 0 else 1000.0))
            s["pm_up_bid"].append((t, 0.49))
            s["pm_up_ask"].append((t, 0.51))
            s["bn_book_imb"].append((t, 0.1 * flow_sign))
            s["pm_book_imb"].append((t, 0.0))
        return s, outcome

    def test_features_at_checkpoint(self):
        s, _ = self._round(1795376400, "UP", +1)
        f = rr.flow_features(s, 1795376400, checkpoint_s=60)
        self.assertAlmostEqual(f["flow_imb"], (1000 - 200) / 1200)
        self.assertAlmostEqual(f["market_up"], 0.50)
        self.assertEqual(f["up_ask"], 0.51)
        self.assertAlmostEqual(f["down_ask"], 0.51)

    def test_features_none_without_market_price(self):
        s, _ = self._round(1795376400, "UP", +1)
        s["pm_up_bid"], s["pm_up_ask"] = [], []
        self.assertIsNone(rr.flow_features(s, 1795376400, checkpoint_s=60))

    def test_report_detects_flow_that_beats_the_market(self):
        rows = []
        for i in range(30):
            sign = 1 if i % 2 == 0 else -1
            s, out = self._round(1795376400 + 300 * i, "UP" if sign > 0 else "DOWN", sign)
            f = rr.flow_features(s, 1795376400 + 300 * i, checkpoint_s=60)
            rows.append(dict(f, outcome=out))
        rep = rr.flow_report_from_rows(rows)
        self.assertEqual(rep["n"], 30)
        self.assertGreater(rep["top_bucket"]["up_rate"], rep["top_bucket"]["market_up"])
        self.assertLess(rep["bottom_bucket"]["up_rate"], rep["bottom_bucket"]["market_up"])
        self.assertEqual(rep["follow_flow"]["wins"], 30)
        self.assertGreater(rep["follow_flow"]["pnl"], 0)


if __name__ == "__main__":
    unittest.main()
