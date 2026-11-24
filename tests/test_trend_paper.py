"""
Tests for the forward paper trader of the daily trend strategy: it sizes from closes up to the
decision day only, fills at the real bid/ask when live and at the close when catching up, charges
funding with the right sign, never trades the same day twice, and books equity consistently.
"""

import os
import tempfile
import unittest

import numpy as np

import tests  # noqa: F401
from research import trend_paper as tp

DAY = 86400
T0 = 1_790_000_000 - 1_790_000_000 % DAY


class FakeMarket:
    """Two coins: UP rises every day, DOWN falls every day."""

    def __init__(self, n_days=120, spread=0.001):
        self.n = n_days
        self.spread = spread
        self.funding_rows = {}
        self.quotes_asked = 0

    def last_open(self):
        return T0 + DAY * (self.n - 1)

    def daily(self, coin, limit=200):
        k = np.arange(self.n)
        px = 100 * (1.01 ** k if coin == "UP" else 0.99 ** k)
        return [(int(T0 + DAY * i), float(p)) for i, p in zip(k, px)][-limit:]

    def funding(self, coin, since_ts):
        return [r for r in self.funding_rows.get(coin, []) if r[0] > since_ts]

    def quote(self, coin):
        self.quotes_asked += 1
        c = self.daily(coin)[-1][1]
        return c * (1 - self.spread / 2), c * (1 + self.spread / 2)


class ZigzagMarket(FakeMarket):
    """UP climbs in a zigzag (higher highs, higher lows), DOWN falls in one; daily OHLC available."""

    def _path(self, coin):
        k = np.arange(self.n)
        wave = 6 * np.sin(2 * np.pi * k / 20)
        trend = 0.5 * k if coin == "UP" else -0.5 * k
        return 200 + trend + wave

    def daily(self, coin, limit=200):
        return [(int(T0 + DAY * i), float(p)) for i, p in enumerate(self._path(coin))][-limit:]

    def daily_ohlc(self, coin, limit=400):
        return [(t, p, p * 1.002, p * 0.998, p) for t, p in self.daily(coin, limit)][-limit:]


def book():
    path = os.path.join(tempfile.mkdtemp(), "paper.db")
    return tp.PaperBook(path)


class TestTargets(unittest.TestCase):
    def test_equal_weight_long_short_from_sma(self):
        m = FakeMarket()
        closes = {c: m.daily(c) for c in ("UP", "DOWN")}
        day = m.last_open()
        tgt = tp.target_weights(closes, day, n=50, long_only=False)
        self.assertEqual(tgt, {"UP": 0.5, "DOWN": -0.5})
        self.assertEqual(tp.target_weights(closes, day, n=50, long_only=True), {"UP": 0.5, "DOWN": 0.0})

    def test_targets_ignore_closes_after_the_decision_day(self):
        m = FakeMarket()
        closes = {c: m.daily(c) for c in ("UP", "DOWN")}
        day = T0 + DAY * 90
        a = tp.target_weights(closes, day, 50, False)
        later = {c: [(t, p * (50 if t > day else 1)) for t, p in rows] for c, rows in closes.items()}
        self.assertEqual(tp.target_weights(later, day, 50, False), a)

    def test_young_coins_are_left_out(self):
        m = FakeMarket(n_days=40)
        closes = {c: m.daily(c) for c in ("UP", "DOWN")}
        self.assertEqual(tp.target_weights(closes, m.last_open(), 50, False), {"UP": 0.0, "DOWN": 0.0})


class TestRun(unittest.TestCase):
    def setUp(self):
        self.m = FakeMarket()
        self.b = book()
        self.variants = {"LS": (50, False)}
        self.coins = ["UP", "DOWN"]

    def run_at(self, now):
        return tp.run_once(self.b, self.m, now=now, variants=self.variants, coins=self.coins, capital=1000.0)

    def test_first_run_enters_live_at_bid_ask_with_fee(self):
        now = self.m.last_open() + DAY + 3600
        self.run_at(now)
        fills = self.b.fills("LS")
        self.assertEqual({f["coin"] for f in fills}, {"UP", "DOWN"})
        for f in fills:
            self.assertEqual(f["mode"], "live")
            c = self.m.daily(f["coin"])[-1][1]
            if f["qty"] > 0:
                self.assertAlmostEqual(f["price"], c * 1.0005)
            else:
                self.assertAlmostEqual(f["price"], c * 0.9995)
            self.assertAlmostEqual(f["fee"], abs(f["qty"]) * f["price"] * 0.0005)
        pos = self.b.positions("LS")
        self.assertGreater(pos["UP"], 0)
        self.assertLess(pos["DOWN"], 0)
        # equity after entry = capital - spread/2 - fees on 1000 of notional
        eq = self.b.cash("LS") + sum(q * self.m.daily(c)[-1][1] for c, q in pos.items())
        self.assertAlmostEqual(eq, 1000 - 1000 * 0.0005 - 1000 * 0.0005, places=6)

    def test_coin_subset_account_trades_only_its_coins_with_full_weight(self):
        self.variants = {"LS": (50, False), "SUB": (50, False, ("UP",))}
        self.run_at(self.m.last_open() + DAY + 3600)
        self.assertEqual({f["coin"] for f in self.b.fills("SUB")}, {"UP"})
        self.assertEqual({f["coin"] for f in self.b.fills("LS")}, {"UP", "DOWN"})
        notional = sum(abs(f["qty"]) * f["price"] for f in self.b.fills("SUB"))
        self.assertAlmostEqual(notional, 1000 * (1 - 0.0005), delta=1.0)     # all the equity in its one coin

    def test_ema_structure_long_only_buys_the_rising_zigzag_only(self):
        self.m = ZigzagMarket(n_days=160)
        self.variants = {"ES": (50, True, None, "ema_structure")}
        self.run_at(self.m.last_open() + DAY + 3600)
        pos = self.b.positions("ES")
        self.assertGreater(pos.get("UP", 0), 0)
        self.assertNotIn("DOWN", pos)
        ohlc = {c: self.m.daily_ohlc(c) for c in ("UP", "DOWN")}
        w = tp.es_target_weights(ohlc, self.m.last_open(), 50, True)
        self.assertAlmostEqual(w["UP"], 0.5)          # equal weight across the 2 eligible coins
        self.assertEqual(w["DOWN"], 0.0)
        later = {c: rows + [(rows[-1][0] + DAY, 1e9, 1e9, 1e9, 1e9)] for c, rows in ohlc.items()}
        self.assertEqual(tp.es_target_weights(later, self.m.last_open(), 50, True), w)   # later candles ignored

    def test_ema_structure_long_short_shorts_the_falling_zigzag(self):
        m = ZigzagMarket(n_days=160)
        ohlc = {c: m.daily_ohlc(c) for c in ("UP", "DOWN")}
        w = tp.es_target_weights(ohlc, m.last_open(), 50, False)
        self.assertAlmostEqual(w["UP"], 0.5)
        self.assertAlmostEqual(w["DOWN"], -0.5)

    def test_dashboard_values_positions_at_live_mids_or_last_fill(self):
        self.run_at(self.m.last_open() + DAY + 3600)
        pos = self.b.positions("LS")
        mids = {c: self.m.daily(c)[-1][1] for c in pos}
        d = tp.dashboard_state(self.b, mids, variants=self.variants)["accounts"]["LS"]
        self.assertTrue(d["live_prices"])
        self.assertAlmostEqual(d["equity"], self.b.cash("LS") + sum(q * mids[c] for c, q in pos.items()))
        self.assertEqual(d["longs"], ["UP"])
        self.assertEqual(d["shorts"], ["DOWN"])
        self.assertEqual(d["fills"], 2)
        q = {c: (mids[c] * 0.999, mids[c] * 1.001) for c in pos}
        cv = tp.dashboard_state(self.b, mids, variants=self.variants, quotes=q)["accounts"]["LS"]
        exp = self.b.cash("LS")
        for c, qty in pos.items():
            px = q[c][0] if qty > 0 else q[c][1]
            exp += qty * px - abs(qty) * px * 0.0005
        self.assertAlmostEqual(cv["close_value"], exp)
        self.assertGreater(cv["close_cost"], 0)
        off = tp.dashboard_state(self.b, None, variants=self.variants)["accounts"]["LS"]
        self.assertFalse(off["live_prices"])
        last = {f["coin"]: f["price"] for f in self.b.fills("LS")}
        self.assertAlmostEqual(off["equity"], self.b.cash("LS") + sum(q * last[c] for c, q in pos.items()))

    def test_same_day_is_never_traded_twice(self):
        now = self.m.last_open() + DAY + 3600
        self.run_at(now)
        n = len(self.b.fills("LS"))
        self.run_at(now + 1800)
        self.assertEqual(len(self.b.fills("LS")), n)

    def test_missed_days_catch_up_at_the_close(self):
        self.m.n = 100
        self.run_at(self.m.last_open() + DAY + 600)
        self.m.n = 103                                # three new closes while the machine was off
        self.run_at(self.m.last_open() + DAY + 600)
        days = self.b.days("LS")
        self.assertEqual([d["mode"] for d in days], ["live", "catchup", "catchup", "live"])
        catch = [f for f in self.b.fills("LS") if f["mode"] == "catchup"]
        for f in catch:
            close = dict(self.m.daily(f["coin"]))[f["day"]]
            self.assertAlmostEqual(f["price"], close * (1.0002 if f["qty"] > 0 else 0.9998))

    def test_long_pays_positive_funding_short_receives(self):
        now = self.m.last_open() + DAY + 600
        self.run_at(now)
        pos = self.b.positions("LS")
        cash0 = self.b.cash("LS")
        self.m.n += 1
        ts = self.m.last_open() + 8 * 3600
        self.m.funding_rows = {"UP": [(ts, 0.001, 110.0)], "DOWN": [(ts, 0.001, 50.0)]}
        self.run_at(self.m.last_open() + DAY + 600)
        paid = {f["coin"]: f["amount"] for f in self.b.funding_rows("LS")}
        self.assertAlmostEqual(paid["UP"], -pos["UP"] * 0.001 * 110.0)
        self.assertAlmostEqual(paid["DOWN"], -pos["DOWN"] * 0.001 * 50.0)
        self.assertLess(paid["UP"], 0)
        self.assertGreater(paid["DOWN"], 0)
        self.assertNotEqual(self.b.cash("LS"), cash0)

    def test_tiny_rebalances_below_min_notional_are_skipped(self):
        now = self.m.last_open() + DAY + 600
        self.run_at(now)
        n = len(self.b.fills("LS"))
        self.m.n += 1
        self.run_at(self.m.last_open() + DAY + 600)
        new = self.b.fills("LS")[n:]
        for f in new:
            self.assertGreaterEqual(abs(f["qty"]) * f["price"], tp.MIN_NOTIONAL)


class TestPositionBook(unittest.TestCase):
    def test_open_close_flip_and_locked_in_profit(self):
        f = lambda coin, qty, price, ts: {"coin": coin, "qty": qty, "price": price, "ts": ts, "fee": abs(qty)}
        pb = tp.position_book([f("A", 2, 100, 1), f("A", 1, 130, 2),       # long 3 at avg 110
                               f("A", -1, 120, 3),                          # trim 1: +10
                               f("A", -4, 90, 4),                           # close 2 (-40) and flip short 2 at 90
                               f("B", -1, 50, 5), f("B", 1, 40, 6)])        # short closed: +10
        a, b = pb["A"], pb["B"]
        self.assertAlmostEqual(a["qty"], -2)
        self.assertAlmostEqual(a["entry"], 90)
        self.assertEqual(a["opened_ts"], 4)
        self.assertAlmostEqual(a["realized"], 10 - 40)
        self.assertEqual(a["closed"], 1)
        self.assertEqual(b["qty"], 0)
        self.assertAlmostEqual(b["realized"], 10)
        self.assertEqual(b["closed"], 1)
        self.assertAlmostEqual(a["fees_open"], 4 * 2 / 4)      # the flip fill's share for the new 2-unit short
        self.assertEqual(b["fees_open"], 0.0)                  # closed trade: nothing open

    def test_fees_of_the_open_trade_add_up(self):
        f = lambda qty, ts: {"coin": "A", "qty": qty, "price": 100, "ts": ts, "fee": 0.5}
        pb = tp.position_book([f(1, 1), f(1, 2), f(-0.5, 3)])
        self.assertAlmostEqual(pb["A"]["fees_open"], 1.5)       # open + add + trim


class TestExecutionCheck(unittest.TestCase):
    def test_paper_tracks_the_close_replay_when_spread_is_zero(self):
        m = FakeMarket(n_days=100, spread=0.0)
        b = book()
        v = {"T2_SMA50_LS": (50, False)}
        for k in range(10):
            m.n = 100 + k
            tp.run_once(b, m, now=m.last_open() + DAY + 600, variants=v, coins=["UP", "DOWN"], capital=1000.0)
        days = [d["day"] for d in b.days("T2_SMA50_LS")]
        closes = {c: m.daily(c) for c in ("UP", "DOWN")}
        paper = b.days("T2_SMA50_LS")[-1]["equity_close"] / 1000 - 1
        replay = tp.replay_return(closes, {}, (50, False), days)
        self.assertGreater(abs(replay), 0.01)                # something actually happened
        self.assertAlmostEqual(paper, replay, delta=0.002)   # fee basis and the $5 skip differ slightly


if __name__ == "__main__":
    unittest.main()
