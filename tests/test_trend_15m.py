import unittest

from polymarket_sentinel.crypto_5m.trend_15m import Trend15mBot, fee

R = 1795700700 - 1795700700 % 900          # a 15-minute round start


class FakeAnalyzer:
    """Markets keyed by round start: dict(price_up, price_down, bid_up, bid_down, winning_outcome)."""

    def __init__(self):
        self.m = {}

    def set(self, r, up_ask, down_ask, up_bid=0.0, down_bid=0.0, winner=None):
        self.m[r] = {"found": True, "price_source": "clob", "price_up": up_ask, "price_down": down_ask,
                     "bid_up": up_bid, "bid_down": down_bid, "winning_outcome": winner}

    def fetch_polymarket_market(self, coin, round_ts, timeframe="5m"):
        assert timeframe == "15m"
        return self.m.get(round_ts, {"found": False})


def local_bot(an):
    return Trend15mBot(an, stake=20.0, bankroll=400.0, auto_start=False)


class TestTrend15m(unittest.TestCase):
    def test_buys_previous_winner_for_20_dollars_from_10_seconds(self):
        an = FakeAnalyzer()
        an.set(R - 900, 0.99, 0.01, winner="UP")
        an.set(R, 0.55, 0.46, 0.54, 0.45)
        b = local_bot(an)
        b.tick(R + 5)
        self.assertIsNone(b.active)                          # before 10 s
        b.tick(R + 11)
        self.assertEqual((b.active["side"], b.active["entry"], b.active["cost"]), ("UP", 0.55, 20.0))
        self.assertAlmostEqual(b.balance, 400 - 20 - fee(20 / 0.55, 0.55))

    def test_skips_outside_50_85(self):
        an = FakeAnalyzer()
        an.set(R - 900, 0.01, 0.99, winner="DOWN")
        an.set(R, 0.62, 0.39, 0.61, 0.38)                   # DOWN at 39c
        b = local_bot(an)
        b.tick(R + 11)
        self.assertIsNone(b.active)
        an.set(R, 0.40, 0.61, 0.39, 0.60)                   # one decision per round, even if it changes
        b.tick(R + 20)
        self.assertIsNone(b.active)

    def test_half_at_30_then_rest_at_45_and_profit_adds_up(self):
        an = FakeAnalyzer()
        an.set(R - 900, 0.99, 0.01, winner="UP")
        an.set(R, 0.50, 0.51, 0.49, 0.50)
        b = local_bot(an)
        b.tick(R + 11)
        an.set(R, 0.71, 0.30, 0.70, 0.29)
        b.tick(R + 100)
        self.assertTrue(b.active["half_sold"])
        an.set(R, 0.77, 0.24, 0.76, 0.23)
        b.tick(R + 200)
        self.assertIsNone(b.active)
        h = b.history[0]
        self.assertGreater(h["pnl"], 7.5)                    # about +40% on $20 across the two halves
        self.assertAlmostEqual(b.balance, 400 + b.realized_pnl, places=6)

    def test_held_to_the_result_and_lost(self):
        an = FakeAnalyzer()
        an.set(R - 900, 0.99, 0.01, winner="UP")
        an.set(R, 0.60, 0.41, 0.59, 0.40)
        b = local_bot(an)
        b.tick(R + 11)
        an.set(R, 0.45, 0.56, 0.44, 0.55)
        b.tick(R + 600)
        an.set(R, 0.01, 0.99, 0.0, 0.98, winner="DOWN")
        b.tick(R + 905)
        self.assertIsNone(b.active)
        self.assertAlmostEqual(b.history[0]["pnl"], round(-20 - fee(20 / 0.60, 0.60), 2))
        self.assertEqual(b.history[0]["status"], "LOST")

    def test_online_profile_cashes_out_all_at_40(self):
        an = FakeAnalyzer()
        an.set(R - 900, 0.99, 0.01, winner="UP")
        an.set(R, 0.60, 0.41, 0.59, 0.40)
        b = Trend15mBot(an, stake=20.0, bankroll=400.0, min_price=0.0, max_price=0.65, entry_seconds=30,
                        half_at=None, rest_at=None, single_tp=0.40, late_exit_seconds=None, auto_start=False)
        b.tick(R + 15)
        self.assertIsNone(b.active)                          # online rule decides at 30 s
        b.tick(R + 31)
        self.assertIsNotNone(b.active)
        an.set(R, 0.89, 0.12, 0.88, 0.11)
        b.tick(R + 120)
        self.assertIsNone(b.active)
        self.assertGreater(b.history[0]["pnl"], 8.0)

    def test_paused_bot_does_not_trade(self):
        an = FakeAnalyzer()
        an.set(R - 900, 0.99, 0.01, winner="UP")
        an.set(R, 0.55, 0.46, 0.54, 0.45)
        b = local_bot(an)
        b.toggle()
        b.tick(R + 11)
        self.assertIsNone(b.active)


if __name__ == "__main__":
    unittest.main()
