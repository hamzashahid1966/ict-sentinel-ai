import time
import unittest
from unittest.mock import MagicMock

from polymarket_sentinel.crypto_5m.models import Btc5mRound
from polymarket_sentinel.crypto_5m.paper_scalper import Btc5mPaperScalper


def rd(round_ts, up_ask, down_ask, up_bid=0.0, down_bid=0.0):
    return Btc5mRound(price_source="clob", round_id=f"btc-updown-5m-{round_ts}", slug="m", title="BTC",
                      strike_price=60000.0, current_btc_price=60000.0, price_delta=0.0, start_time=round_ts,
                      end_time=round_ts + 300, seconds_remaining=200, market_price_up=up_ask, market_price_down=down_ask,
                      calculated_prob_up=0.5, calculated_prob_down=0.5, z_score=0.0, ict_fvg_status="NEUTRAL",
                      signal="ABSTAIN", signal_reason="", symbol="BTC", bid_up=up_bid, bid_down=down_bid)


class TestTrend1(unittest.TestCase):
    def setUp(self):
        self.an = MagicMock()
        self.s = Btc5mPaperScalper(self.an, initial_bankroll=50.0, auto_start=False)
        self.s.trend_stake = 1.0                             # the rule's tests use $1 trades
        self.s.is_enabled = True
        self.ts = 1795700100 - 1795700100 % 300

    def prev(self, winner):
        self.an.fetch_polymarket_market.return_value = {"found": True, "winning_outcome": winner}

    def test_default_is_the_trend_rule(self):
        self.assertEqual(self.s.paper_strategy, "TREND1")

    def test_buys_previous_winner_with_one_dollar(self):
        self.prev("UP")
        self.s._trend1_entry({"BTC": rd(self.ts, 0.55, 0.46)}, self.ts, self.ts + 40)
        t = self.s.active_trades["BTC"]
        self.assertEqual((t.outcome, t.entry_price), ("UP", 0.55))
        self.assertAlmostEqual(t.cost, 1.0, places=2)
        self.an.fetch_polymarket_market.assert_called_with("BTC", self.ts - 300)

    def test_skips_above_65c_and_before_30s(self):
        self.prev("DOWN")
        self.s._trend1_entry({"BTC": rd(self.ts, 0.30, 0.71)}, self.ts, self.ts + 20)
        self.assertEqual(self.s.active_trades, {})                      # too early
        self.s._trend1_entry({"BTC": rd(self.ts, 0.30, 0.71)}, self.ts, self.ts + 40)
        self.assertEqual(self.s.active_trades, {})                      # 71c > 65c cap
        self.s._trend1_entry({"BTC": rd(self.ts, 0.30, 0.60)}, self.ts, self.ts + 60)
        self.assertEqual(self.s.active_trades, {})                      # one decision per round

    def test_cashes_out_at_40_percent_else_holds(self):
        self.prev("UP")
        self.s._trend1_entry({"BTC": rd(self.ts, 0.50, 0.51)}, self.ts, self.ts + 40)
        self.s._check_dynamic_exits({"BTC": rd(self.ts, 0.66, 0.35, up_bid=0.64, down_bid=0.34)})
        self.assertIn("BTC", self.s.active_trades)                      # +28%: hold
        self.s._check_dynamic_exits({"BTC": rd(self.ts, 0.20, 0.81, up_bid=0.18, down_bid=0.80)})
        self.assertIn("BTC", self.s.active_trades)                      # deep dip: no stop, hold
        self.s._check_dynamic_exits({"BTC": rd(self.ts, 0.77, 0.24, up_bid=0.76, down_bid=0.23)})
        self.assertNotIn("BTC", self.s.active_trades)                   # +40% or more: cashed out
        self.assertGreater(self.s.trade_history[0].pnl, 0.35)

    def test_unknown_previous_result_waits(self):
        self.an.fetch_polymarket_market.return_value = {"found": True, "winning_outcome": None, "price_up": 0.5}
        self.s._trend1_entry({"BTC": rd(self.ts, 0.50, 0.51)}, self.ts, self.ts + 40)
        self.assertEqual(self.s.active_trades, {})
        self.assertNotIn(f"{self.ts}_TREND1", self.s.rejected_rounds)  # retried next tick


if __name__ == "__main__":
    unittest.main()
