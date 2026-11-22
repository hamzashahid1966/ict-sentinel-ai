"""
Crypto Sentinel exchange-integrity tests.

Reproduces the faults behind the Nov 21 testnet losses:
  1. A failed position fetch was indistinguishable from "no positions", so live
     positions were booked as closed (EXCHANGE_CLOSE) while still open on Binance.
  2. Closes were booked before Binance confirmed them; a failed close order left
     the position open on the exchange.
  3. After Target 1 the synced quantity was halved again, so the final close sent
     only a quarter of the position.
  4. Orphans were adopted with a 1.5% stop around their stale entry and were
     stopped out instantly at market.
  5. NEAR/AVAX quantities were formatted to 0.1 although Binance trades them in
     whole units (HTTP 400).
  6. The data feed invented prices, screener statistics and candles.
  7. Stops lived only in the bot; nothing protected a position on the exchange.
"""

import time
import unittest
from unittest.mock import MagicMock, patch

import tests  # noqa: F401
import crypto_sentinel.order_manager as om_mod
from crypto_sentinel.storage import CryptoStorageEngine
from crypto_sentinel.order_manager import CryptoOrderManager
from crypto_sentinel.models import CryptoPosition, AnalysisOpportunity
from crypto_sentinel.data_feed import CryptoDataFeed


def _keys():
    return patch.multiple(om_mod, BINANCE_TESTNET_API_KEY="k", BINANCE_TESTNET_API_SECRET="s")


def _pos(**kw):
    base = dict(position_id="POS_X", symbol="ETHUSDT", engine="B_MOMENTUM_IMP", direction="SHORT",
                entry_price=1640.0, quantity=0.30, initial_stop=1660.0, current_stop=1660.0,
                target_1=1632.0, target_2=1624.0, entry_time=time.time() - 60, status="OPEN")
    base.update(kw)
    return CryptoPosition(**base)


def _testnet_storage():
    st = CryptoStorageEngine(db_path=":memory:")
    st.set_mode("BINANCE_TESTNET")
    return st


class TestPositionFetchFailure(unittest.TestCase):
    def test_fetch_returns_none_on_network_error_and_list_when_flat(self):
        om = CryptoOrderManager(_testnet_storage())
        with _keys():
            with patch.object(om, "_signed_request", side_effect=OSError("nodename nor servname provided")):
                self.assertIsNone(om.fetch_binance_testnet_positions())
            with patch.object(om, "_signed_request", return_value=[{"symbol": "ETHUSDT", "positionAmt": "0"}]):
                self.assertEqual(om.fetch_binance_testnet_positions(), [])

    def test_run_cycle_does_not_book_phantom_closes_when_exchange_unreachable(self):
        from crypto_sentinel.controller import CryptoBotController
        bot = CryptoBotController()
        bot.storage = _testnet_storage()
        bot.order_mgr = CryptoOrderManager(bot.storage)
        bot.storage.save_position(_pos())
        bot.data_feed = MagicMock()
        with _keys(), patch.object(bot.order_mgr, "fetch_binance_testnet_positions", return_value=None):
            bot.run_cycle()
        open_now = bot.storage.get_open_positions()
        self.assertEqual([p.position_id for p in open_now], ["POS_X"])
        bot.data_feed.scan_top_50.assert_not_called()   # stands aside: no new entries while blind

    def test_dashboard_sync_neither_closes_nor_adopts_when_exchange_unreachable(self):
        from crypto_sentinel.controller import CryptoBotController
        bot = CryptoBotController()
        bot.storage = _testnet_storage()
        bot.order_mgr = CryptoOrderManager(bot.storage)
        bot.storage.save_position(_pos())
        with _keys(), patch.object(bot.order_mgr, "fetch_binance_testnet_positions", return_value=None), \
             patch.object(bot.order_mgr, "fetch_binance_testnet_account", return_value=None):
            bot.get_dashboard_state()
        self.assertEqual([p.position_id for p in bot.storage.get_open_positions()], ["POS_X"])


class TestConfirmedCloses(unittest.TestCase):
    def setUp(self):
        self.st = _testnet_storage()
        self.om = CryptoOrderManager(self.st)
        self.acc = self.st.get_account()

    def test_failed_close_keeps_position_open_and_books_nothing(self):
        pos = _pos()
        self.st.save_position(pos)
        bal = self.acc.balance
        with _keys(), patch.object(self.om, "_dispatch_binance_testnet_close", return_value=False) as close:
            self.om.update_position_with_price(pos, 1665.0, self.acc)   # through the 1660 stop
        close.assert_called_once()
        self.assertNotEqual(pos.status, "CLOSED")
        self.assertEqual(self.st.get_account().balance, bal)

    def test_confirmed_close_is_booked(self):
        pos = _pos()
        self.st.save_position(pos)
        with _keys(), patch.object(self.om, "_dispatch_binance_testnet_close", return_value=True):
            self.om.update_position_with_price(pos, 1665.0, self.acc)
        self.assertEqual(pos.status, "CLOSED")
        self.assertEqual(pos.exit_reason, "INITIAL_STOP_LOSS")

    def test_full_close_uses_live_exchange_amount_after_target_one(self):
        pos = _pos(quantity=0.30)
        self.st.save_position(pos)
        calls = []
        def fake_close(symbol, direction, qty, reason, full=False):
            calls.append((qty, full))
            return True
        with _keys(), patch.object(self.om, "_dispatch_binance_testnet_close", side_effect=fake_close), \
             patch.object(self.om, "_sync_exchange_stop", return_value=True):
            self.om.update_position_with_price(pos, 1631.0, self.acc)   # T1
            self.assertTrue(pos.t1_hit)
            self.assertAlmostEqual(pos.quantity, 0.15)                 # local size now mirrors the exchange
            self.om.update_position_with_price(pos, 1623.0, self.acc)  # T2
        self.assertEqual(calls[0], (0.15, False))
        self.assertTrue(calls[1][1], "final close must flatten whatever Binance still holds")

    def test_failed_partial_close_does_not_mark_target_one(self):
        pos = _pos()
        self.st.save_position(pos)
        with _keys(), patch.object(self.om, "_dispatch_binance_testnet_close", return_value=False):
            self.om.update_position_with_price(pos, 1631.0, self.acc)
        self.assertFalse(pos.t1_hit)
        self.assertAlmostEqual(pos.quantity, 0.30)

    def test_close_dispatch_reports_failure(self):
        with _keys(), patch.object(self.om, "_signed_request", side_effect=OSError("down")), \
             patch.object(self.om, "_cancel_open_orders", return_value=True):
            self.assertFalse(self.om._dispatch_binance_testnet_close("ETHUSDT", "SHORT", 0.3, "STOP", full=False))


class TestAdoptionStops(unittest.TestCase):
    def test_adopted_orphan_gets_a_stop_beyond_the_current_price(self):
        from crypto_sentinel.controller import CryptoBotController
        bot = CryptoBotController()
        bot.storage = _testnet_storage()
        bot.order_mgr = CryptoOrderManager(bot.storage)
        orphan = {"symbol": "BTCUSDT", "positionAmt": "-0.006", "entryPrice": "58234.1",
                  "markPrice": "59844.0", "unRealizedProfit": "-9.66"}
        with _keys(), patch.object(bot.order_mgr, "fetch_binance_testnet_positions", return_value=[orphan]), \
             patch.object(bot.order_mgr, "fetch_binance_testnet_account", return_value=None), \
             patch.object(bot.order_mgr, "_sync_exchange_stop", return_value=True):
            bot.get_dashboard_state()
        adopted = [p for p in bot.storage.get_open_positions() if p.symbol == "BTCUSDT"]
        self.assertEqual(len(adopted), 1)
        self.assertGreater(adopted[0].current_stop, 59844.0)   # a short's stop must sit above the market

    def test_sync_guard_never_resets_a_stop_into_the_market(self):
        from crypto_sentinel.controller import CryptoBotController
        bot = CryptoBotController()
        bot.storage = _testnet_storage()
        bot.order_mgr = CryptoOrderManager(bot.storage)
        # stored stop is >8% from the exchange entry, which trips the recalibration guard
        bot.storage.save_position(_pos(symbol="BTCUSDT", entry_price=58234.1, initial_stop=60745.0, current_stop=60745.0,
                                       target_1=57000.0, target_2=56000.0, quantity=0.006))
        live = {"symbol": "BTCUSDT", "positionAmt": "-0.006", "entryPrice": "53000.0",
                "markPrice": "59844.0", "unRealizedProfit": "-41.0"}
        with _keys(), patch.object(bot.order_mgr, "fetch_binance_testnet_positions", return_value=[live]), \
             patch.object(bot.order_mgr, "fetch_binance_testnet_account", return_value=None), \
             patch.object(bot.order_mgr, "_sync_exchange_stop", return_value=True):
            bot.get_dashboard_state()
        p = bot.storage.get_open_positions()[0]
        self.assertGreater(p.current_stop, 59844.0)


class TestLotSizes(unittest.TestCase):
    def test_quantity_is_floored_to_the_exchange_step(self):
        om = CryptoOrderManager(CryptoStorageEngine(db_path=":memory:"))
        om._lot_steps = {"NEARUSDT": 1.0, "INJUSDT": 0.1, "BTCUSDT": 0.0001}
        om._lot_steps_at = time.time()
        self.assertEqual(om._format_qty_for_symbol("NEARUSDT", 111.1), "111")
        self.assertEqual(om._format_qty_for_symbol("INJUSDT", 3.37), "3.3")
        self.assertEqual(om._format_qty_for_symbol("BTCUSDT", 0.00649), "0.0064")


class TestNoInventedMarketData(unittest.TestCase):
    def test_candles_are_empty_not_synthetic_when_unreachable(self):
        feed = CryptoDataFeed()
        with patch("crypto_sentinel.data_feed.direct_urlopen", side_effect=OSError("down")):
            self.assertEqual(feed.fetch_candles("NEARUSDT", "5m", 30), [])

    def test_price_has_no_random_drift_and_is_none_until_seen(self):
        with patch.object(CryptoDataFeed, "sync_testnet_prices"):   # constructed offline: nothing seen yet
            feed = CryptoDataFeed()
            self.assertIsNone(feed.get_current_price("NEARUSDT"))
        feed._price_cache["NEARUSDT"] = 2.637
        feed.last_sync_time = time.time()
        self.assertEqual(feed.get_current_price("NEARUSDT"), 2.637)
        self.assertEqual(feed.get_current_price("NEARUSDT"), 2.637)

    def test_screener_uses_real_24h_statistics(self):
        feed = CryptoDataFeed()
        tickers = {"BTCUSDT": {"lastPrice": "60000", "priceChangePercent": "-1.25", "quoteVolume": "9000000000",
                               "highPrice": "61000", "lowPrice": "59500"}}
        with patch.object(feed, "_fetch_24h_tickers", return_value=tickers), patch.object(feed, "sync_testnet_prices"):
            cands = feed.scan_top_50(prime_only=True)
        btc = [c for c in cands if c.symbol == "BTCUSDT"]
        self.assertEqual(len(btc), 1)
        self.assertAlmostEqual(btc[0].change_24h, -1.25)
        self.assertAlmostEqual(btc[0].volume_24h, 9000000000.0)
        self.assertEqual(len(cands), 1)   # coins without real statistics are not scored

    def test_screener_is_empty_when_statistics_unavailable(self):
        feed = CryptoDataFeed()
        with patch.object(feed, "_fetch_24h_tickers", return_value=None), patch.object(feed, "sync_testnet_prices"):
            self.assertEqual(feed.scan_top_50(prime_only=True), [])


class TestExchangeStops(unittest.TestCase):
    def test_entry_fill_places_a_protective_stop_on_binance(self):
        st = _testnet_storage()
        om = CryptoOrderManager(st)
        om._lot_steps, om._tick_sizes, om._lot_steps_at = {}, {}, time.time()
        pos = _pos()
        reqs = []
        def fake(method, path, params):
            reqs.append((method, path, dict(params)))
            if path == "/fapi/v1/order" and params.get("type") == "MARKET":
                return {"orderId": 1, "avgPrice": "1640.0", "executedQty": "0.30", "cumQuote": "492"}
            return {"orderId": 2}
        with _keys(), patch.object(om, "_signed_request", side_effect=fake):
            om._dispatch_binance_testnet_order(pos, "MARKET")
        stops = [(m, path, p) for m, path, p in reqs if p.get("type") == "STOP_MARKET"]
        self.assertEqual(len(stops), 1)
        method, path, params = stops[0]
        # Since 2025-12-09 Binance only accepts conditional orders on the Algo Order API (-4120 otherwise).
        self.assertEqual((method, path), ("POST", "/fapi/v1/algoOrder"))
        self.assertEqual(params["algoType"], "CONDITIONAL")
        self.assertEqual(params["closePosition"], "true")
        self.assertEqual(params["side"], "BUY")   # a short is protected by a buy stop
        self.assertAlmostEqual(float(params["triggerPrice"]), pos.initial_stop)
        self.assertIn(("DELETE", "/fapi/v1/algoOpenOrders"), [(m, pth) for m, pth, _ in reqs])  # old stop cleared first

    def test_full_close_cancels_resting_stop_orders(self):
        st = _testnet_storage()
        om = CryptoOrderManager(st)
        with _keys(), patch.object(om, "_signed_request", return_value={"orderId": 3}), \
             patch.object(om, "fetch_binance_testnet_positions", return_value=[{"symbol": "ETHUSDT", "positionAmt": "-0.15"}]), \
             patch.object(om, "_cancel_open_orders", return_value=True) as cancel:
            self.assertTrue(om._dispatch_binance_testnet_close("ETHUSDT", "SHORT", 0.15, "STOP", full=True))
        cancel.assert_called_once_with("ETHUSDT")


if __name__ == "__main__":
    unittest.main()


class TestExistingPositionsGetExchangeStops(unittest.TestCase):
    def test_live_position_gets_one_exchange_stop_after_restart(self):
        from crypto_sentinel.controller import CryptoBotController
        bot = CryptoBotController()
        bot.storage = _testnet_storage()
        bot.order_mgr = CryptoOrderManager(bot.storage)
        bot.storage.save_position(_pos())
        live = [{"symbol": "ETHUSDT", "positionAmt": "-0.30", "entryPrice": "1640.0", "markPrice": "1645.0", "unRealizedProfit": "-1.5"}]
        bot.data_feed = MagicMock()
        bot.data_feed.scan_top_50.return_value = []
        bot.data_feed.get_btc_trend.return_value = "NEUTRAL"
        with _keys(), patch.object(bot.order_mgr, "fetch_binance_testnet_positions", return_value=live), \
             patch.object(bot.order_mgr, "_sync_exchange_stop", return_value=True) as sync:
            bot.run_cycle()
            bot.run_cycle()
        self.assertEqual(sync.call_count, 1)



class TestExchangeStopRetryBackoff(unittest.TestCase):
    def test_failed_stop_placement_is_retried_at_most_once_a_minute(self):
        from crypto_sentinel.controller import CryptoBotController
        bot = CryptoBotController()
        bot.storage = _testnet_storage()
        bot.order_mgr = CryptoOrderManager(bot.storage)
        bot.storage.save_position(_pos())
        live = [{"symbol": "ETHUSDT", "positionAmt": "-0.30", "entryPrice": "1640.0", "markPrice": "1645.0", "unRealizedProfit": "-1.5"}]
        bot.data_feed = MagicMock()
        bot.data_feed.scan_top_50.return_value = []
        bot.data_feed.get_btc_trend.return_value = "NEUTRAL"
        with _keys(), patch.object(bot.order_mgr, "fetch_binance_testnet_positions", return_value=live), \
             patch.object(bot.order_mgr, "_sync_exchange_stop", return_value=False) as sync:
            bot.run_cycle()
            bot.run_cycle()
        self.assertEqual(sync.call_count, 1)
