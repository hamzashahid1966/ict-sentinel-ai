"""
Tests for the strategy lab: positions earn the NEXT bar's return, costs and funding are charged
correctly, the look-ahead check catches signals that peek, controls keep the trades, the
Polymarket context only holds closed candles, and bet P&L includes spread and fee.
"""

import os
import tempfile
import unittest

import numpy as np
import pandas as pd

import tests  # noqa: F401
from research import lab

T0 = 1_790_000_000 - 1_790_000_000 % 86400


def write_strategy(body: str) -> str:
    d = tempfile.mkdtemp()
    p = os.path.join(d, "strat.py")
    with open(p, "w") as f:
        f.write(body)
    return p


def frame(closes, tf=3600):
    t = pd.to_datetime(T0 + tf * np.arange(len(closes)), unit="s", utc=True)
    c = np.asarray(closes, float)
    return pd.DataFrame({"o": c, "h": c, "l": c, "c": c, "volume": 1.0, "buy_volume": 0.5, "funding": 0.0}, index=t)


class TestEngine(unittest.TestCase):
    def one(self, closes, sig, funding=None, cost=0.0):
        n = len(closes)
        c = np.asarray(closes, float)[:, None]
        s = np.asarray(sig, float)[:, None]
        f = np.zeros((n, 1)) if funding is None else np.asarray(funding, float)[:, None]
        return lab.run_positions(T0 + 3600 * np.arange(n), 3600, c, s, f, np.ones((n, 1), bool), cost)

    def test_position_earns_the_next_bar_only(self):
        r = self.one([100, 110, 121, 121], [1, 0, 0, 0])
        np.testing.assert_allclose(r.ret, [0, 0.10, 0, 0])

    def test_costs_on_every_change_and_on_the_final_close(self):
        r = self.one([100, 100, 100, 100], [1, -1, -1, -1], cost=0.001)
        np.testing.assert_allclose(r.ret, [-0.001, -0.002, 0, -0.001])
        self.assertEqual(r.entries, 2)

    def test_long_pays_positive_funding_short_receives(self):
        f = [0, 0.01, 0, 0]
        self.assertAlmostEqual(self.one([100] * 4, [1] * 4, f).ret[1], -0.01)
        self.assertAlmostEqual(self.one([100] * 4, [-1] * 4, f).ret[1], 0.01)

    def test_each_coin_gets_one_over_n_and_inactive_coins_hold_cash(self):
        c = np.array([[100, np.nan], [110, 50], [110, 100]], float)
        s = np.ones((3, 2))
        act = ~np.isnan(c)
        r = lab.run_positions(T0 + 3600 * np.arange(3), 3600, c, s, np.zeros((3, 2)), act, 0.0)
        np.testing.assert_allclose(r.ret, [0, 0.05, 0.5])

    def test_rotation_control_keeps_the_positions(self):
        rng = np.random.default_rng(0)
        s = np.r_[np.zeros(5), np.ones(20), -np.ones(30), np.zeros(45)][:, None]
        act = np.ones_like(s, bool)
        for _ in range(10):
            r = lab.rotate_signals(s, act, rng)
            self.assertEqual(sorted(r[:, 0]), sorted(s[:, 0]))
            self.assertFalse(np.array_equal(r, s))


class TestData(unittest.TestCase):
    def test_resample_drops_candles_with_missing_minutes(self):
        t = T0 + 60 * np.r_[np.arange(10), np.arange(11, 15)]       # minute 10 missing
        x = np.arange(len(t), dtype=float) + 1
        out = lab.resample(t, x, x + 1, x - 1, x, np.ones_like(x), np.ones_like(x) / 2, 300)
        self.assertEqual(list(out.index), [T0, T0 + 300])
        self.assertEqual(out.loc[T0 + 300, "o"], 6)
        self.assertEqual(out.loc[T0 + 300, "c"], 10)
        self.assertEqual(out.loc[T0, "volume"], 5)

    def test_funding_goes_to_the_bar_it_settles_in(self):
        bars = T0 + 3600 * np.arange(3)
        f = lab.funding_for_bars(bars, 3600, np.array([T0 + 1800, T0 + 3600, T0 + 3601]), np.array([1.0, 2.0, 4.0]))
        np.testing.assert_allclose(f, [3.0, 4.0, 0.0])

    def test_polymarket_context_holds_only_closed_minutes(self):
        mt = T0 + 60 * np.arange(10)
        k = lab.closed_minutes_end(mt, T0 + 300)
        self.assertEqual(mt[k - 1] + 60, T0 + 300)       # candle 04:00 closed exactly at the decision
        self.assertEqual(lab.closed_minutes_end(mt, T0 + 299), 4)


class TestLookahead(unittest.TestCase):
    def test_peeking_signal_is_caught_and_causal_one_passes(self):
        df = frame(100 + np.cumsum(np.random.default_rng(1).normal(0, 1, 400)))
        causal = lambda d: np.sign(d.c - d.c.rolling(20).mean())
        peek = lambda d: np.sign(d.c.shift(-1) - d.c)
        centred = lambda d: np.sign(d.c - d.c.rolling(21, center=True).mean())
        self.assertIsNone(lab.lookahead_check(causal, df, {}))
        self.assertIsNotNone(lab.lookahead_check(peek, df, {}))
        self.assertIsNotNone(lab.lookahead_check(centred, df, {}))


class TestPolymarket(unittest.TestCase):
    def test_decision_is_made_when_the_price_was_seen_not_at_the_checkpoint(self):
        rts = np.array([T0, T0 + 300])
        rounds = pd.DataFrame({"coin": "BTC", "round_ts": rts, "outcome": ["UP", "DOWN"], "price_to_beat": 100.0,
                               "t_point": rts + 130, "p_up": 0.5})        # price 50 s older than the 180 s checkpoint
        mt = (T0 - 3600) + 60 * np.arange(80 + 10)
        ones = np.ones(len(mt))
        pm = lab.PMData(rounds, {"BTC": (mt.astype(float), ones, ones, ones, ones * 100, ones, ones / 2)})
        seen = []
        path = write_strategy("KIND='polymarket'\nCHECKPOINT=120\nSEEN=[]\n"
                              "def decide(ctx):\n    SEEN.append((ctx.round_ts, ctx.t_decision, ctx.secs_left, len(ctx.close)))\n"
                              "    return None\n")
        st = lab.load_strategy(path, {})
        lab.run_polymarket_strategy(st, ["BTC"], "full", n_controls=10, data=pm)
        for rts_, t_dec, left, n in st.module.SEEN:
            self.assertEqual(t_dec, rts_ + 130)
            self.assertEqual(left, 170)
            k = lab.closed_minutes_end(mt, t_dec)
            self.assertEqual(n, min(k, lab.PM_LOOKBACK))
            self.assertLessEqual(mt[k - 1] + 60, t_dec)

    def test_strategy_lookback_and_minute_times(self):
        rts = np.array([T0, T0 + 300])
        rounds = pd.DataFrame({"coin": "BTC", "round_ts": rts, "outcome": ["UP", "DOWN"], "price_to_beat": 100.0,
                               "t_point": rts + 170, "p_up": 0.5})
        mt = (T0 - 3600) + 60 * np.arange(80)
        ones = np.ones(len(mt))
        pm = lab.PMData(rounds, {"BTC": (mt.astype(float), ones, ones, ones, ones * 100, ones, ones / 2)})
        path = write_strategy("KIND='polymarket'\nCHECKPOINT=120\nLOOKBACK=20\nSEEN=[]\n"
                              "def decide(ctx):\n    SEEN.append((ctx.t_decision, ctx.t.copy(), len(ctx.close)))\n"
                              "    return None\n")
        st = lab.load_strategy(path, {})
        lab.run_polymarket_strategy(st, ["BTC"], "full", n_controls=10, data=pm)
        for t_dec, t, n in st.module.SEEN:
            self.assertEqual(n, 20)
            self.assertEqual(len(t), 20)
            self.assertEqual(t[-1], t_dec - (t_dec % 60) - 60)     # the last minute that closed by t_dec

    def test_bet_pnl_includes_spread_and_fee(self):
        p = 0.60 + 0.01
        win = lab.pm_bet_pnl("UP", 0.60, True)
        self.assertAlmostEqual(win, 1 / p - 1 - (1 / p) * 0.07 * p * (1 - p))
        self.assertAlmostEqual(lab.pm_bet_pnl("UP", 0.60, False), -1 - (1 / p) * 0.07 * p * (1 - p))
        q = 0.40 + 0.01
        self.assertAlmostEqual(lab.pm_bet_pnl("DOWN", 0.60, False), 1 / q - 1 - (1 / q) * 0.07 * q * (1 - q))
        self.assertIsNone(lab.pm_bet_pnl("UP", 0.985, True))

    def test_run_on_synthetic_rounds(self):
        n = 300
        rts = T0 + 300 * np.arange(n)
        up = np.arange(n) % 2 == 0
        rounds = pd.DataFrame({"coin": "BTC", "round_ts": rts, "outcome": np.where(up, "UP", "DOWN"),
                               "price_to_beat": 100.0, "t_point": rts + 170, "p_up": 0.5})
        mt = (T0 - 3600) + 60 * np.arange(n * 5 + 120)
        ones = np.ones(len(mt))
        pm = lab.PMData(rounds, {"BTC": (mt.astype(float), ones, ones, ones, ones * 100, ones, ones / 2)})
        path = write_strategy("KIND='polymarket'\nNAME='always_up'\nCHECKPOINT=120\n"
                              "def decide(ctx):\n    assert ctx.t_decision == ctx.round_ts + 170\n"
                              "    assert len(ctx.close) == 0 or ctx.close is not None\n"
                              "    return 'UP'\n")
        st = lab.load_strategy(path, {})
        rep = lab.run_polymarket_strategy(st, ["BTC"], "full", n_controls=50, data=pm)
        self.assertEqual(rep.summary["bets"], n)
        exp = n / 2 * lab.pm_bet_pnl("UP", 0.5, True) + n / 2 * lab.pm_bet_pnl("UP", 0.5, False)
        self.assertAlmostEqual(rep.summary["net"], exp)
        self.assertFalse(rep.passed)


class TestPositionRun(unittest.TestCase):
    def test_trend_on_a_trending_series_beats_its_controls_and_passes_lookahead(self):
        rng = np.random.default_rng(3)
        steps = np.repeat(rng.choice([-1, 1], 40), 50) * 0.004 + rng.normal(0, 0.002, 2000)
        data = {"AAA": frame(100 * np.exp(np.cumsum(steps)))}
        path = write_strategy("import numpy as np\nKIND='position'\nNAME='t'\nTIMEFRAME='1h'\nPARAMS={'n': 10}\n"
                              "def signal(df, n):\n    return np.sign(df.c - df.c.rolling(n).mean())\n")
        st = lab.load_strategy(path, {})
        rep = lab.run_position_strategy(st, ["AAA"], "full", n_controls=50, data=data)
        crit = {name: ok for name, ok, _ in rep.criteria}
        self.assertTrue(crit["no look-ahead"])
        self.assertTrue(crit["net result > 0"])
        self.assertTrue(crit["beats 95th pct of random-timing controls"])

    def test_dev_part_never_sees_the_last_third(self):
        seen = {}
        data = {"AAA": frame(np.linspace(100, 200, 900))}
        path = write_strategy("KIND='position'\nNAME='t'\nTIMEFRAME='1h'\n"
                              "def signal(df):\n    import builtins\n    builtins._lab_last = df.index[-1]\n    return df.c * 0\n")
        st = lab.load_strategy(path, {})
        lab.run_position_strategy(st, ["AAA"], "dev", n_controls=0, data=data)
        import builtins
        self.assertLess(builtins._lab_last, data["AAA"].index[600])

    def test_unknown_param_override_is_rejected(self):
        path = write_strategy("KIND='position'\nPARAMS={'n': 1}\ndef signal(df, n):\n    return df.c * 0\n")
        with self.assertRaises(SystemExit):
            lab.load_strategy(path, {"m": 2})


if __name__ == "__main__":
    unittest.main()
