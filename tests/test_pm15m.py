import unittest

from research import pm15m as pm


class TestPm15m(unittest.TestCase):
    def test_bet_matches_lab_formula(self):
        price = 0.51
        shares = 1 / price
        self.assertAlmostEqual(pm.bet(price, True), shares - 1 - shares * 0.07 * price * (1 - price))
        self.assertAlmostEqual(pm.bet(price, False), -1 - shares * 0.07 * price * (1 - price))
        self.assertIsNone(pm.bet(1.0, True))

    def test_price_at_uses_only_the_past(self):
        hist = [(100, 0.4), (160, 0.6), (220, 0.8)]
        self.assertIsNone(pm.price_at(hist, 99))
        self.assertEqual(pm.price_at(hist, 200), 0.6)

    def test_rules(self):
        s = 1_795_000_500 - 1_795_000_500 % 900
        hist = [(s + 60 * k, 0.30 if k < 8 else 0.75) for k in range(15)]     # Up 0.30 early, 0.75 late
        btc = [[s - 60 * k, 100.0, 100.0 + 0.01 * (k % 2)] for k in range(60, 0, -1)]
        btc += [[s + 60 * k, 100.0, 100.0] for k in range(15)]               # BTC flat: fair ~ 0.5
        bets = pm.decisions([{"start": s, "winner": "Up", "up": hist}], btc)
        by = {b["rule"]: b for b in bets}
        self.assertEqual((by["FAV10"]["side"], round(by["FAV10"]["price"], 2)), ("Up", 0.76))
        self.assertEqual((by["DOG5"]["side"], round(by["DOG5"]["price"], 2)), ("Up", 0.31))
        self.assertTrue(by["FAV10"]["won"] and by["DOG5"]["won"])
        self.assertEqual(by["LAG"]["side"], "Up")                           # 0.5 fair vs 0.31 price at minute 2
        self.assertEqual(by["LAG"]["minute"], 2)


if __name__ == "__main__":
    unittest.main()
