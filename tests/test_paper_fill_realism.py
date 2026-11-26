"""
Paper fills must reflect the live CLOB, not Gamma's stale outcome prices.

Observed 2026-11-22: Gamma reported UP at 31.5c for a full minute while the live
book moved from 13.5c to 4.5c. The paper scalper "bought" at those stale prices
and reported wins that no real counterparty would have given it, while the live
executor was rejecting the same entries ("best ask is 54-99c, exceeds ceiling").
"""

import time
import unittest
from unittest.mock import MagicMock, patch

import tests  # noqa: F401
from polymarket_sentinel.crypto_5m.models import Btc5mRound, Btc5mTrade
from polymarket_sentinel.crypto_5m.round_analyzer import MultiCryptoRoundAnalyzer, best_levels
from polymarket_sentinel.crypto_5m.paper_scalper import MultiCryptoPaperScalper


GAMMA_EVENT = [{
    "title": "Bitcoin Up or Down - test", "closed": False, "eventMetadata": {},
    "markets": [{"outcomePrices": '["0.315", "0.685"]', "acceptingOrders": True, "closed": False,
                 "clobTokenIds": '["TOK_UP", "TOK_DOWN"]', "endDate": None}],
}]
BOOK_UP = {"bids": [{"price": "0.03", "size": "100"}, {"price": "0.12", "size": "40"}],
           "asks": [{"price": "0.20", "size": "10"}, {"price": "0.14", "size": "80"}]}
BOOK_DOWN = {"bids": [{"price": "0.85", "size": "50"}, {"price": "0.80", "size": "9"}],
             "asks": [{"price": "0.87", "size": "30"}, {"price": "0.95", "size": "5"}]}


def _round(**kw):
    base = dict(round_id="btc-updown-5m-1795376400", slug="s", title="t", strike_price=60000.0, current_btc_price=60010.0,
                price_delta=10.0, start_time=1795376400, end_time=1795376700, seconds_remaining=120,
                market_price_up=0.50, market_price_down=0.50, calculated_prob_up=0.9, calculated_prob_down=0.1,
                z_score=2.0, ict_fvg_status="BULLISH_DISPLACEMENT", signal="BUY_UP", signal_reason="[EARLY VALUE SCALP] test",
                symbol="BTC", clob_token_ids=["TOK_UP", "TOK_DOWN"])
    base.update(kw)
    return Btc5mRound(**base)


class TestBestLevels(unittest.TestCase):
    def test_best_bid_is_highest_and_best_ask_is_lowest(self):
        self.assertEqual(best_levels(BOOK_UP), (0.12, 0.14))
        self.assertEqual(best_levels({"bids": [], "asks": []}), (None, None))


class TestAnalyzerUsesLiveBook(unittest.TestCase):
    def _analyzer(self, book_ok=True):
        an = MultiCryptoRoundAnalyzer(MagicMock())

        def http(url, timeout=2.5):
            if "gamma-api" in url:
                return GAMMA_EVENT
            if not book_ok:
                raise OSError("clob down")
            if "TOK_UP" in url:
                return BOOK_UP
            if "TOK_DOWN" in url:
                return BOOK_DOWN
            raise AssertionError(url)
        an._http_json = http
        return an

    def test_buy_price_is_live_ask_and_sell_price_is_live_bid(self):
        d = self._analyzer().fetch_polymarket_market("BTC", 1795376400)
        self.assertEqual(d["price_source"], "clob")
        self.assertEqual(d["price_up"], 0.14)       # what a buyer of UP pays now
        self.assertEqual(d["price_down"], 0.87)     # what a buyer of DOWN pays now
        self.assertEqual(d["bid_up"], 0.12)         # what a seller of UP receives
        self.assertEqual(d["bid_down"], 0.85)
        self.assertEqual(d["gamma_price_up"], 0.315)

    def test_falls_back_to_gamma_and_says_so_when_book_unavailable(self):
        d = self._analyzer(book_ok=False).fetch_polymarket_market("BTC", 1795376400)
        self.assertEqual(d["price_source"], "gamma")
        self.assertEqual(d["price_up"], 0.315)


class TestPaperFillsAtLiveAsk(unittest.TestCase):
    def _scalper(self):
        sc = MultiCryptoPaperScalper(analyzer=MagicMock(), initial_bankroll=50.0, auto_start=False)
        sc.is_enabled = True
        return sc

    def test_paper_entry_fills_at_the_ask_not_a_stale_quote(self):
        sc = self._scalper()
        r = _round(market_price_up=0.96, bid_up=0.94, price_source="clob")
        sc._execute_entry(r)
        t = sc.active_trades.get("BTC")
        self.assertIsNotNone(t)
        self.assertAlmostEqual(t.entry_price, 0.96)
        self.assertAlmostEqual(t.cost, round(t.shares * 0.96, 2))

    def test_paper_entry_refused_without_a_live_book(self):
        sc = self._scalper()
        sc._execute_entry(_round(market_price_up=0.32, price_source="gamma"))
        self.assertEqual(sc.active_trades, {})

    def test_paper_exit_prices_off_the_bid(self):
        sc = self._scalper()
        sc.paper_exit_mode = "SCALP"          # early exits only exist in the old quick-exit mode
        sc.active_trades["BTC"] = Btc5mTrade(id=1, round_id="btc-updown-5m-1795376400", action="BUY", outcome="UP", shares=10.0,
                                             entry_price=0.50, cost=5.0, pnl=0.0, timestamp="2026-11-22T19:40:10+00:00",
                                             reason="[EARLY VALUE SCALP] test", symbol="BTC", mode="PAPER", status="OPEN")
        sc.cashout_trade = MagicMock(return_value={})
        # ask has run to 95c but the best bid is only 60c: a seller gets 60c
        sc._check_dynamic_exits({"BTC": _round(market_price_up=0.95, bid_up=0.60, price_source="clob", seconds_remaining=150)})
        sc.cashout_trade.assert_called_once()
        self.assertAlmostEqual(sc.cashout_trade.call_args.kwargs["exit_price"], 0.60)


if __name__ == "__main__":
    unittest.main()
