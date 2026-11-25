"""
Close-race and display fixes for Crypto Sentinel.

Production 2026-11-23 07:56:50 UTC (testnet): the dashboard closed SOLUSDT manually
(booked MANUAL_CLOSE) while the bot's 5-second cycle still held the position from before.
Two seconds later the cycle found SOL gone from Binance and booked it AGAIN as
EXCHANGE_CLOSE at the entry price, overwriting the manual record and double-counting the
loss in coin learning. The same race can double-book P&L in REAL_DATA_PAPER mode.

Rules under test:
  - a CLOSED position record is final: nothing may reopen or re-close it
  - every booking path re-checks the stored position under one lock before touching money
  - the dashboard shows the live mark price, not the entry price, for open paper trades
"""

import time
import unittest
from unittest.mock import MagicMock, patch

import tests  # noqa: F401
import crypto_sentinel.order_manager as om_mod
from crypto_sentinel.storage import CryptoStorageEngine
from crypto_sentinel.order_manager import CryptoOrderManager
from crypto_sentinel.models import CryptoPosition


def _pos(**kw):
    base = dict(position_id="POS_SOL_1", symbol="SOLUSDT", engine="C_LIQUIDATION_SWEEP", direction="SHORT",
                entry_price=71.79, quantity=10.0, initial_stop=72.53, current_stop=72.53,
                target_1=71.49, target_2=71.20, entry_time=time.time() - 600, status="OPEN")
    base.update(kw)
    return CryptoPosition(**base)


def _storage(mode, balance=1000.0):
    st = CryptoStorageEngine(db_path=":memory:")
    st.set_mode(mode)
    st.update_account(balance=balance, realized_pnl_delta=0.0)
    return st


class TestClosedIsFinal(unittest.TestCase):
    def test_closed_record_cannot_be_reopened_or_reclosed(self):
        st = _storage("BINANCE_TESTNET")
        st.save_position(_pos())
        closed = _pos(status="CLOSED", exit_reason="MANUAL_CLOSE", exit_price=72.05, exit_time=time.time())
        st.save_position(closed)
        st.save_position(_pos(status="OPEN"))
        st.save_position(_pos(status="CLOSED", exit_reason="EXCHANGE_CLOSE", exit_price=71.79, exit_time=time.time()))
        got = st.get_position("POS_SOL_1")
        self.assertEqual(got.status, "CLOSED")
        self.assertEqual(got.exit_reason, "MANUAL_CLOSE")
        self.assertEqual(got.exit_price, 72.05)
        self.assertEqual(st.get_open_positions(), [])

    def test_get_position_returns_none_for_unknown(self):
        self.assertIsNone(_storage("BINANCE_TESTNET").get_position("nope"))


class TestRealPaperRace(unittest.TestCase):
    def test_stale_cycle_copy_cannot_book_a_manually_closed_trade_again(self):
        st = _storage("REAL_DATA_PAPER")
        om = CryptoOrderManager(st)
        st.save_position(_pos())
        stale = st.get_open_positions()[0]          # the cycle's copy, taken before the manual close
        self.assertTrue(om.close_position_manually("POS_SOL_1", 72.0, st.get_account(), quote=(71.99, 72.01)))
        bal_after_manual = st.get_account().balance
        om.update_position_with_price(stale, 72.60, st.get_account(), quote=(72.59, 72.61))   # stop would trigger
        self.assertAlmostEqual(st.get_account().balance, bal_after_manual, places=9)
        self.assertEqual(st.get_position("POS_SOL_1").exit_reason, "MANUAL_CLOSE")

    def test_funding_is_not_booked_on_a_closed_trade(self):
        st = _storage("REAL_DATA_PAPER")
        om = CryptoOrderManager(st)
        st.save_position(_pos())
        stale = st.get_open_positions()[0]
        om.close_position_manually("POS_SOL_1", 72.0, st.get_account(), quote=(71.99, 72.01))
        b = st.get_account().balance
        with patch.object(om, "_real_get", return_value=[{"fundingTime": int(time.time() * 1000) - 5, "fundingRate": "0.01", "markPrice": "72"}]):
            om.settle_funding(stale, st.get_account(), force=True)
        self.assertAlmostEqual(st.get_account().balance, b, places=9)


class TestTestnetRace(unittest.TestCase):
    def test_cycle_does_not_overwrite_a_manual_close_with_exchange_close(self):
        from crypto_sentinel.controller import CryptoBotController
        bot = CryptoBotController()
        bot.storage = _storage("BINANCE_TESTNET")
        bot.order_mgr = CryptoOrderManager(bot.storage)
        bot.storage.save_position(_pos())
        stale_list = bot.storage.get_open_positions()
        with patch.multiple(om_mod, BINANCE_TESTNET_API_KEY="k", BINANCE_TESTNET_API_SECRET="s"), \
             patch.object(bot.order_mgr, "_dispatch_binance_testnet_close", return_value=True):
            bot.order_mgr.close_position_manually("POS_SOL_1", 71.99, bot.storage.get_account())
        learn = MagicMock()
        bot.order_mgr._record_closed_trade_learning = learn
        bot.data_feed = MagicMock()
        bot.data_feed.scan_top_50.return_value = []
        with patch.object(bot.order_mgr, "fetch_binance_testnet_positions", return_value=[]), \
             patch.object(bot.storage, "get_open_positions", side_effect=[stale_list, [], [], []]):
            bot.run_cycle()
        self.assertEqual(bot.storage.get_position("POS_SOL_1").exit_reason, "MANUAL_CLOSE")
        learn.assert_not_called()


class TestLiveMarkOnDashboard(unittest.TestCase):
    def test_open_paper_trade_shows_live_mark_and_pnl_on_the_open_size(self):
        from crypto_sentinel.controller import CryptoBotController
        bot = CryptoBotController()
        bot.storage = _storage("REAL_DATA_PAPER")
        bot.order_mgr = CryptoOrderManager(bot.storage)
        bot.storage.save_position(_pos(direction="LONG", entry_price=0.6718, initial_stop=0.6658, current_stop=0.6658,
                                       quantity=600.0, target_1=0.6742, target_2=0.6766, symbol="SUIUSDT"))
        bot.data_feed = MagicMock()
        bot.data_feed.get_current_price.return_value = 0.6700
        p = bot.get_dashboard_state()["open_positions"][0]
        self.assertEqual(p["current_price"], 0.6700)
        self.assertAlmostEqual(p["unrealized_pnl"], round((0.6700 - 0.6718) * 600.0, 2))
        self.assertAlmostEqual(p["unrealized_r"], round((0.6700 - 0.6718) / 0.0060, 2))

    def test_after_target_1_paper_pnl_counts_only_the_open_half(self):
        from crypto_sentinel.controller import CryptoBotController
        bot = CryptoBotController()
        bot.storage = _storage("REAL_DATA_PAPER")
        bot.order_mgr = CryptoOrderManager(bot.storage)
        bot.storage.save_position(_pos(direction="SHORT", entry_price=0.05561, initial_stop=0.0561, current_stop=0.055586,
                                       quantity=4081.0, target_1=0.055414, target_2=0.055218, symbol="DOGEUSDT",
                                       t1_hit=True, status="T1_HIT", defensive_active=True))
        bot.data_feed = MagicMock()
        bot.data_feed.get_current_price.return_value = 0.05540
        p = bot.get_dashboard_state()["open_positions"][0]
        self.assertAlmostEqual(p["unrealized_pnl"], round((0.05561 - 0.05540) * 4081.0 / 2, 2))


if __name__ == "__main__":
    unittest.main()
