"""
Tests for the local market-history store: parsers for Binance 1m klines, Coinbase 1m
candles and Polymarket 5m round events, and the SQLite store they write into.
"""

import os
import sqlite3
import tempfile
import unittest

import tests  # noqa: F401
from market_data import history as mh


class TestParsers(unittest.TestCase):
    def test_binance_kline_keeps_taker_buy_volume(self):
        row = [1795419840000, "61512.32", "61514.66", "61500.00", "61500.01", "6.35151", 1795419899999,
               "390676.0379919", 2257, "1.92023", "118113.7894818", "0"]
        self.assertEqual(mh.parse_binance_kline("BTCUSDT", row),
                         ("BTCUSDT", 1795419840, 61512.32, 61514.66, 61500.0, 61500.01, 6.35151,
                          390676.0379919, 2257, 1.92023, 118113.7894818))

    def test_coinbase_candle_column_order_is_time_low_high_open_close_volume(self):
        row = [1779858000, 75445.73, 75493.26, 75450.00, 75475.15, 1.56871015]
        self.assertEqual(mh.parse_coinbase_candle("BTC-USD", row),
                         ("BTC-USD", 1779858000, 75450.00, 75493.26, 75445.73, 75475.15, 1.56871015))

    def _event(self, prices='["0", "1"]', closed=True, meta=None):
        return {
            "slug": "btc-updown-5m-1792821600", "closed": closed, "volume": 27376.05,
            "eventMetadata": meta if meta is not None else {"finalPrice": 80629.4, "priceToBeat": 80670.18},
            "markets": [{"conditionId": "0xabc", "clobTokenIds": '["UP_TOKEN", "DOWN_TOKEN"]',
                         "outcomePrices": prices, "closed": closed, "volumeNum": 27376.05}],
        }

    def test_gamma_event_resolved_down(self):
        r = mh.parse_gamma_event("BTC", self._event())
        self.assertEqual(r["coin"], "BTC")
        self.assertEqual(r["round_ts"], 1792821600)
        self.assertEqual(r["outcome"], "DOWN")
        self.assertEqual(r["up_token"], "UP_TOKEN")
        self.assertEqual(r["down_token"], "DOWN_TOKEN")
        self.assertEqual(r["price_to_beat"], 80670.18)
        self.assertEqual(r["final_price"], 80629.4)
        self.assertEqual(r["volume"], 27376.05)
        self.assertEqual(r["closed"], 1)

    def test_gamma_event_unresolved_has_no_outcome(self):
        r = mh.parse_gamma_event("BTC", self._event(prices='["0.55", "0.45"]', closed=False, meta={}))
        self.assertIsNone(r["outcome"])
        self.assertIsNone(r["price_to_beat"])

    def test_gamma_event_garbage_returns_none(self):
        self.assertIsNone(mh.parse_gamma_event("BTC", {"slug": "nonsense"}))


class TestStore(unittest.TestCase):
    def setUp(self):
        self.db = os.path.join(tempfile.mkdtemp(), "h.db")
        self.store = mh.HistoryStore(self.db)

    def test_upserts_are_idempotent_and_resume_points_advance(self):
        rows = [("BTCUSDT", 60 * i, 1.0, 2.0, 0.5, 1.5, 10.0, 15.0, 3, 4.0, 6.0) for i in range(5)]
        self.store.put_binance(rows)
        self.store.put_binance(rows[2:])
        self.assertEqual(sqlite3.connect(self.db).execute("select count(*) from binance_1m").fetchone()[0], 5)
        self.assertEqual(self.store.last_binance_t("BTCUSDT"), 240)
        self.assertIsNone(self.store.last_binance_t("ETHUSDT"))

    def test_rounds_needing_prices(self):
        base = {"slug": "s", "condition_id": "c", "down_token": "d", "outcome": "UP", "price_to_beat": 1.0,
                "final_price": 2.0, "volume": 3.0, "closed": 1}
        self.store.put_rounds([dict(base, coin="BTC", round_ts=300, up_token="t1"),
                               dict(base, coin="BTC", round_ts=600, up_token="t2")])
        self.store.put_prices([("BTC", 300, 250, 0.5), ("BTC", 300, 310, 0.6)])
        self.store.mark_prices_done("BTC", 300)
        self.assertEqual(self.store.rounds_needing_prices(), [("BTC", 600, "t2")])
        self.assertEqual(self.store.known_round_ts("BTC"), {300, 600})


if __name__ == "__main__":
    unittest.main()
