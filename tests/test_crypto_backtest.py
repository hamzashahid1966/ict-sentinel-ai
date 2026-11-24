"""
Tests for the Crypto Sentinel backtest: it must decide like the live bot (same BTC trend rule,
same quarantine bookkeeping), never look ahead, and fill/charge pessimistically and honestly.
"""

import random
import time
import unittest
from unittest.mock import patch

import numpy as np

import tests  # noqa: F401
from research import crypto_backtest as bt
from crypto_sentinel.models import CryptoCandle


def _coin(n=3 * 1440, t0=1790000000 - 1790000000 % 3600, seed=2, symbol="BTCUSDT"):
    rng = np.random.default_rng(seed)
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.001, n)))
    o = np.r_[c[0], c[:-1]]
    h = np.maximum(o, c) * 1.0005
    l = np.minimum(o, c) * 0.9995
    qv = rng.uniform(1e5, 2e5, n)
    t = t0 + 60 * np.arange(n)
    return bt.CoinData(symbol, t, o, h, l, c, qv)


class TestSameDecisionsAsLive(unittest.TestCase):
    def test_btc_trend_matches_the_live_data_feed(self):
        from crypto_sentinel.data_feed import CryptoDataFeed
        feed = CryptoDataFeed.__new__(CryptoDataFeed)
        rng = random.Random(4)
        for _ in range(200):
            m5 = [100 * (1 + rng.uniform(-0.004, 0.004)) for _ in range(15)]
            h1 = [100 * (1 + rng.uniform(-0.01, 0.01)) for _ in range(20)]
            cand = lambda xs: [CryptoCandle(0, x, x, x, x, 1.0) for x in xs]
            with patch.object(feed, "fetch_candles", side_effect=lambda sym, timeframe="5m", limit=50: cand(m5 if timeframe == "5m" else h1)):
                live = feed.get_btc_trend()
            self.assertEqual(bt.btc_trend(m5, h1), live)

    def test_quarantine_matches_live_storage(self):
        from crypto_sentinel.storage import CryptoStorageEngine
        st = CryptoStorageEngine(db_path=":memory:")
        q = bt.Quarantine()
        rng = random.Random(7)
        now = 1_790_000_000
        for _ in range(60):
            now += rng.choice([600, 3600, 30000, 90000])
            net = rng.choice([-3.9, -1.2, 0.4, 1.7, -0.3, 2.2])
            with patch("crypto_sentinel.storage.time.time", return_value=float(now)):
                live_q = st.is_coin_quarantined("SOLUSDT")[0]
                st.record_coin_trade_outcome("SOLUSDT", net, 0.0, net > 0, "x")
            self.assertEqual(q.active("SOLUSDT", now), live_q)
            q.record("SOLUSDT", net, now)


class TestNoLookAhead(unittest.TestCase):
    def test_closed_and_forming_bars_use_only_past_minutes(self):
        d = _coin()
        T = int(d.t[2000]) + 60 - (int(d.t[2000]) + 60) % 300 + 300
        m5 = d.closed(300, T, 30)
        self.assertLessEqual(m5[-1].timestamp + 300, T)
        h1 = d.with_forming(3600, T, 50)
        a = d.with_forming(900, T, 30)[-1]
        d2 = _coin()
        future = d2.t >= T
        d2.h[future] *= 2
        d2.l[future] *= 0.5
        d2.c[future] *= 3
        d2.o[future] *= 3
        d2.bars = {tf: d2._aggregate(tf) for tf in (300, 900, 3600)}
        d2.bar_index = {tf: {int(b.timestamp): i for i, b in enumerate(bs)} for tf, bs in d2.bars.items()}
        self.assertEqual([c.close for c in d2.closed(300, T, 30)], [c.close for c in m5])
        self.assertEqual([c.high for c in d2.with_forming(3600, T, 50)], [c.high for c in h1])
        self.assertEqual(d2.with_forming(900, T, 30)[-1].close, a.close)


class TestExits(unittest.TestCase):
    def _long(self):
        return bt.open_sim_position("SOLUSDT", "B", "LONG", fill=100.0, stop=99.0, qty=10.0, ts=0, risk_dollars=10.0)

    def test_targets_from_fill_and_entry_fee(self):
        p = self._long()
        self.assertEqual((p.t1, p.t2), (100.4, 100.8))
        self.assertAlmostEqual(p.fees, 10 * 100 * 0.0005)

    def test_gap_through_stop_fills_at_the_open_with_slippage(self):
        p = self._long()
        cash, closed = bt.process_bar(p, o=98.5, h=98.7, l=98.3, c=98.6, bar_end=60)
        self.assertTrue(closed)
        fill = 98.5 * (1 - 0.0002)
        self.assertAlmostEqual(p.exit_price, fill)
        self.assertEqual(p.reason, "INITIAL_STOP_LOSS")
        self.assertAlmostEqual(cash, (fill - 100) * 10 - 10 * fill * 0.0005)

    def test_stop_is_checked_before_target_in_the_same_bar(self):
        p = self._long()
        _, closed = bt.process_bar(p, o=100.0, h=100.9, l=98.9, c=100.5, bar_end=60)
        self.assertTrue(closed)
        self.assertEqual(p.reason, "INITIAL_STOP_LOSS")

    def test_target_1_then_moved_stop_in_same_bar_is_pessimistic(self):
        p = self._long()
        _, closed = bt.process_bar(p, o=100.0, h=100.5, l=99.9, c=100.0, bar_end=60)
        self.assertTrue(closed)
        self.assertTrue(p.t1_hit)
        self.assertEqual(p.reason, "DEFENSIVE_STOP_OUT")
        self.assertAlmostEqual(p.stop, 100.05)

    def test_target_1_then_target_2_books_both_halves(self):
        p = self._long()
        bt.process_bar(p, o=100.1, h=100.45, l=100.1, c=100.4, bar_end=60)
        self.assertTrue(p.t1_hit)
        _, closed = bt.process_bar(p, o=100.4, h=100.9, l=100.3, c=100.85, bar_end=120)
        self.assertTrue(closed)
        self.assertEqual(p.reason, "TARGET_2_FULL_FILL")
        f1, f2 = 100.4 * (1 - 0.0002), 100.8 * (1 - 0.0002)
        self.assertAlmostEqual(p.gross, (f1 - 100) * 5 + (f2 - 100) * 5)
        self.assertAlmostEqual(p.fees, 10 * 100 * 0.0005 + 5 * f1 * 0.0005 + 5 * f2 * 0.0005)

    def test_stagnation_moves_stop_to_fee_cover_once(self):
        p = self._long()
        bt.process_bar(p, o=100.1, h=100.2, l=100.05, c=100.15, bar_end=45 * 60)
        self.assertTrue(p.stagnant)
        self.assertAlmostEqual(p.stop, 100.11)
        self.assertTrue(p.defensive)

    def test_short_stop_mirror(self):
        p = bt.open_sim_position("SOLUSDT", "C", "SHORT", fill=100.0, stop=101.0, qty=10.0, ts=0, risk_dollars=10.0)
        self.assertEqual((p.t1, p.t2), (99.6, 99.2))
        _, closed = bt.process_bar(p, o=100.5, h=101.2, l=100.4, c=101.1, bar_end=60)
        self.assertTrue(closed)
        self.assertAlmostEqual(p.exit_price, 101.0 * (1 + 0.0002))


class TestAccount(unittest.TestCase):
    def test_daily_lock_resets_at_midnight_only_when_enabled(self):
        a = bt.Account()
        a.new_time(0)
        a.add(-31.0)
        self.assertTrue(a.as_account().is_locked)
        a.new_time(86400)
        self.assertFalse(a.as_account().is_locked)
        b = bt.Account(daily_reset=False)
        b.new_time(0)
        b.add(-31.0)
        b.new_time(86400 * 5)
        self.assertTrue(b.as_account().is_locked)


class TestRunRestoresClock(unittest.TestCase):
    def test_backtest_runs_and_restores_the_risk_engine_clock(self):
        from crypto_sentinel import risk_engine
        d = _coin(n=4 * 1440)
        start = int(d.t[0]) + 3 * 86400
        res = bt.run_backtest({"BTCUSDT": d}, start, int(d.t[-1]), verbose=False)
        self.assertIs(risk_engine.time, time)
        self.assertGreater(len(res.equity), 0)


if __name__ == "__main__":
    unittest.main()
