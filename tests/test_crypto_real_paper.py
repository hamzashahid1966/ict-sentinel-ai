"""
REAL_DATA_PAPER mode for Crypto Sentinel: paper trading on REAL Binance USDT-M data.

Why: the testnet tracks real Binance within ~0.03% most of the time but prints phantom
wicks (up to 1.6% on BTC, 12-167 minutes a day per coin over 0.3%) that trigger stops and
targets the real market never reached, and fills against a fake order book.

Rules under test:
  - every price is real Binance: mark price for stop/target triggers, best bid/ask for fills
  - entries fill at the real ask (long) / bid (short); exits at the real bid (long) / ask (short)
  - a triggered stop books at the real fill, not at the stop price (gaps cost money)
  - taker fees (0.05% a side) come out of the balance
  - funding settlements are charged/credited from Binance's real settled rates, once each
  - the mode trades the 12 most liquid established coins and keeps its own database
"""

import json
import os
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

import tests  # noqa: F401
from crypto_sentinel.storage import CryptoStorageEngine
from crypto_sentinel.order_manager import CryptoOrderManager, paper_entry_fill
from crypto_sentinel.models import CryptoPosition, AnalysisOpportunity
from crypto_sentinel.data_feed import RealBinanceQuotes, CryptoDataFeed

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FEE = 0.0005


def _real_storage(balance=1000.0):
    st = CryptoStorageEngine(db_path=":memory:")
    st.set_mode("REAL_DATA_PAPER")
    acc = st.get_account()
    st.update_account(balance=balance, realized_pnl_delta=0.0)
    return st


def _opp(direction="LONG", price=100.0, stop=99.0):
    return AnalysisOpportunity(symbol="SOLUSDT", engine="B_MOMENTUM_IMP", direction=direction,
                               status="OPPORTUNITY_CONFIRMED", confidence_score=0.8, reason="t",
                               current_price=price, stop_loss=stop, target_1=0, target_2=0, risk_r=1.0)


class TestRealBinanceQuotes(unittest.TestCase):
    def test_parses_mark_and_book(self):
        q = RealBinanceQuotes()
        premium = [{"symbol": "SOLUSDT", "markPrice": "71.96", "lastFundingRate": "0.0001", "nextFundingTime": 1795420800000}]
        book = [{"symbol": "SOLUSDT", "bidPrice": "71.95", "askPrice": "71.97", "bidQty": "10", "askQty": "12"}]
        with patch.object(q, "_get", side_effect=lambda url: premium if "premiumIndex" in url else book):
            q.refresh(force=True)
        self.assertEqual(q.mark("SOLUSDT"), 71.96)
        self.assertEqual(q.quote("SOLUSDT"), (71.95, 71.97))
        self.assertIsNone(q.mark("NOPEUSDT"))
        self.assertIsNone(q.quote("NOPEUSDT"))

    def test_uses_real_mainnet_host(self):
        q = RealBinanceQuotes()
        urls = []
        with patch.object(q, "_get", side_effect=lambda url: urls.append(url) or []):
            q.refresh(force=True)
        self.assertTrue(urls and all(u.startswith("https://fapi.binance.com/") for u in urls))

    def test_data_feed_in_real_mode_prices_from_real_mark(self):
        feed = CryptoDataFeed.__new__(CryptoDataFeed)
        feed._price_cache = {"SOLUSDT": 999.0}  # stale testnet price must not be used
        feed.price_source = "real"
        feed.real_quotes = RealBinanceQuotes()
        with patch.object(feed.real_quotes, "refresh"), \
             patch.object(feed.real_quotes, "mark", return_value=71.96), \
             patch.object(feed.real_quotes, "quote", return_value=(71.95, 71.97)):
            self.assertEqual(feed.get_current_price("SOLUSDT"), 71.96)
            self.assertEqual(feed.get_quote("SOLUSDT"), (71.95, 71.97))


class TestEntryFill(unittest.TestCase):
    def test_long_buys_ask_short_sells_bid(self):
        self.assertEqual(paper_entry_fill("LONG", (99.9, 100.1), stop=99.0), 100.1)
        self.assertEqual(paper_entry_fill("SHORT", (99.9, 100.1), stop=101.0), 99.9)

    def test_refuses_without_quote_or_when_fill_is_through_the_stop(self):
        self.assertIsNone(paper_entry_fill("LONG", None, stop=99.0))
        self.assertIsNone(paper_entry_fill("LONG", (98.9, 99.0), stop=99.0))
        self.assertIsNone(paper_entry_fill("SHORT", (101.0, 101.2), stop=101.0))


class TestRealPaperAccounting(unittest.TestCase):
    def setUp(self):
        self.st = _real_storage(1000.0)
        self.om = CryptoOrderManager(self.st)

    def _open_long(self, fill=100.1, stop=99.0, qty=10.0):
        return self.om.open_position(_opp("LONG", 100.0, stop), qty, "REAL_DATA_PAPER", fill_price=fill)

    def test_entry_at_fill_with_fee_out_of_balance_and_targets_from_fill(self):
        pos = self._open_long()
        self.assertEqual(pos.entry_price, 100.1)
        self.assertAlmostEqual(self.st.get_account().balance, 1000.0 - 10 * 100.1 * FEE, places=6)
        self.assertGreater(pos.target_1, 100.1)
        r = 100.1 - 99.0
        self.assertAlmostEqual(pos.target_2 - 100.1, (pos.target_1 - 100.1) * (pos.target_2 - 100.1) / (pos.target_1 - 100.1), places=6)
        self.assertGreater(pos.target_1 - 100.1, 0.0)
        self.assertLess(pos.target_1 - 100.1, r * 10)

    def test_gapped_stop_books_at_the_real_bid_not_the_stop(self):
        pos = self._open_long()
        bal_after_entry = self.st.get_account().balance
        acc = self.st.get_account()
        # mark trades through the 99.0 stop; real bid is 98.5
        self.om.update_position_with_price(pos, 98.6, acc, quote=(98.5, 98.7))
        self.assertEqual(pos.status, "CLOSED")
        self.assertEqual(pos.exit_price, 98.5)
        expected = bal_after_entry + (98.5 - 100.1) * 10 - 10 * 98.5 * FEE
        self.assertAlmostEqual(self.st.get_account().balance, expected, places=6)

    def test_target_1_partial_books_half_at_bid_and_target_2_the_rest(self):
        pos = self._open_long()
        acc = self.st.get_account()
        b0 = acc.balance
        t1_bid = pos.target_1 + 0.01
        self.om.update_position_with_price(pos, pos.target_1 + 0.02, acc, quote=(t1_bid, t1_bid + 0.02))
        self.assertTrue(pos.t1_hit)
        b1 = self.st.get_account().balance
        self.assertAlmostEqual(b1, b0 + (t1_bid - 100.1) * 5 - 5 * t1_bid * FEE, places=6)
        acc = self.st.get_account()
        t2_bid = pos.target_2 + 0.01
        self.om.update_position_with_price(pos, pos.target_2 + 0.02, acc, quote=(t2_bid, t2_bid + 0.02))
        self.assertEqual(pos.status, "CLOSED")
        self.assertAlmostEqual(self.st.get_account().balance, b1 + (t2_bid - 100.1) * 5 - 5 * t2_bid * FEE, places=6)

    def test_short_exits_at_the_ask(self):
        pos = self.om.open_position(_opp("SHORT", 100.0, 101.0), 10.0, "REAL_DATA_PAPER", fill_price=99.9)
        b0 = self.st.get_account().balance
        acc = self.st.get_account()
        self.om.update_position_with_price(pos, 101.2, acc, quote=(101.2, 101.4))
        self.assertEqual(pos.exit_price, 101.4)
        self.assertAlmostEqual(self.st.get_account().balance, b0 + (99.9 - 101.4) * 10 - 10 * 101.4 * FEE, places=6)

    def test_manual_close_uses_real_quote_and_charges_fee(self):
        pos = self._open_long()
        b0 = self.st.get_account().balance
        ok = self.om.close_position_manually(pos.position_id, 101.0, self.st.get_account(), quote=(100.9, 101.1))
        self.assertTrue(ok)
        self.assertAlmostEqual(self.st.get_account().balance, b0 + (100.9 - 100.1) * 10 - 10 * 100.9 * FEE, places=6)


class TestFunding(unittest.TestCase):
    def test_long_pays_positive_funding_once_per_settlement_and_ignores_pre_entry(self):
        st = _real_storage(1000.0)
        om = CryptoOrderManager(st)
        pos = om.open_position(_opp("LONG", 100.0, 99.0), 10.0, "REAL_DATA_PAPER", fill_price=100.1)
        b0 = st.get_account().balance
        entry_ms = int(pos.entry_time * 1000)
        rows = [{"symbol": "SOLUSDT", "fundingTime": entry_ms - 1000, "fundingRate": "0.0005", "markPrice": "100.0"},
                {"symbol": "SOLUSDT", "fundingTime": entry_ms + 1000, "fundingRate": "0.0001", "markPrice": "102.0"}]
        with patch.object(om, "_real_get", return_value=rows):
            om.settle_funding(pos, st.get_account(), now=pos.entry_time + 10, force=True)
            om.settle_funding(pos, st.get_account(), now=pos.entry_time + 20, force=True)
        self.assertAlmostEqual(st.get_account().balance, b0 - 10 * 102.0 * 0.0001, places=6)
        self.assertAlmostEqual(pos.funding_paid, 10 * 102.0 * 0.0001, places=6)

    def test_short_receives_positive_funding(self):
        st = _real_storage(1000.0)
        om = CryptoOrderManager(st)
        pos = om.open_position(_opp("SHORT", 100.0, 101.0), 10.0, "REAL_DATA_PAPER", fill_price=99.9)
        b0 = st.get_account().balance
        rows = [{"symbol": "SOLUSDT", "fundingTime": int(pos.entry_time * 1000) + 5, "fundingRate": "0.0002", "markPrice": "100.0"}]
        with patch.object(om, "_real_get", return_value=rows):
            om.settle_funding(pos, st.get_account(), now=pos.entry_time + 10, force=True)
        self.assertAlmostEqual(st.get_account().balance, b0 + 10 * 100.0 * 0.0002, places=6)

    def test_funding_survives_a_save_and_reload(self):
        st = _real_storage(1000.0)
        om = CryptoOrderManager(st)
        pos = om.open_position(_opp("LONG", 100.0, 99.0), 10.0, "REAL_DATA_PAPER", fill_price=100.1)
        rows = [{"symbol": "SOLUSDT", "fundingTime": int(pos.entry_time * 1000) + 5, "fundingRate": "0.0001", "markPrice": "100.0"}]
        with patch.object(om, "_real_get", return_value=rows):
            om.settle_funding(pos, st.get_account(), now=pos.entry_time + 10, force=True)
        again = st.get_open_positions()[0]
        self.assertAlmostEqual(again.funding_paid, 0.1, places=6)
        self.assertGreater(again.last_funding_ts, pos.entry_time)


class TestRealModeConfig(unittest.TestCase):
    def _config_in_mode(self, mode):
        env = dict(os.environ, CRYPTO_EXECUTION_MODE=mode)
        env.pop("CRYPTO_DB_PATH", None)
        code = ("import json; from crypto_sentinel import config as c; "
                "print(json.dumps({'db': c.CRYPTO_DB_PATH, 'prime': c.TOP_PRIME_SYMBOLS, "
                "'universe': [u['symbol'] for u in c.TOP_50_UNIVERSE]}))")
        out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True, text=True, check=True)
        return json.loads(out.stdout.strip().splitlines()[-1])

    def test_real_mode_trades_the_12_liquid_coins_in_its_own_database(self):
        c = self._config_in_mode("REAL_DATA_PAPER")
        self.assertTrue(c["db"].endswith("crypto_real_paper.db"))
        self.assertEqual(c["prime"], ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT", "DOGEUSDT",
                                      "ZECUSDT", "HYPEUSDT", "NEARUSDT", "SUIUSDT", "ADAUSDT", "LINKUSDT"])
        for s in c["prime"]:
            self.assertIn(s, c["universe"])

    def test_testnet_mode_keeps_its_database(self):
        c = self._config_in_mode("BINANCE_TESTNET")
        self.assertTrue(c["db"].endswith("crypto_sentinel.db"))


if __name__ == "__main__":
    unittest.main()


class TestNewAccountProfile(unittest.TestCase):
    def test_new_account_starts_on_the_configured_default_profile(self):
        from crypto_sentinel.config import DEFAULT_STRATEGY_PROFILE
        st = CryptoStorageEngine(db_path=":memory:")
        self.assertEqual(st.get_account().strategy_profile, DEFAULT_STRATEGY_PROFILE)
        self.assertEqual(DEFAULT_STRATEGY_PROFILE, "FAST_SCALPER")


class TestRealPaperReset(unittest.TestCase):
    def test_reset_in_real_paper_mode_returns_to_initial_capital_not_the_testnet_wallet(self):
        from unittest.mock import MagicMock
        from crypto_sentinel.controller import CryptoBotController
        from crypto_sentinel.config import INITIAL_CAPITAL
        bot = CryptoBotController()
        bot.storage = _real_storage(1234.0)
        bot.order_mgr = CryptoOrderManager(bot.storage)
        bot.order_mgr.fetch_binance_testnet_account = MagicMock(return_value={"totalWalletBalance": "3543.54"})
        bot.reset()
        self.assertEqual(bot.storage.get_account().balance, INITIAL_CAPITAL)
        bot.order_mgr.fetch_binance_testnet_account.assert_not_called()
