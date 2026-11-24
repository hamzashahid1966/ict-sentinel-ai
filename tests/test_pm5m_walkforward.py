"""
Tests for the Polymarket 5m walk-forward research harness: no look-ahead in features,
correct fold ordering, honest trade simulation, checkpoint selection, and controls showing
the harness finds a real edge when one exists and does not invent one when none does.
"""

import math
import os
import sqlite3
import tempfile
import unittest

import numpy as np
import pandas as pd

import tests  # noqa: F401
from research import pm5m_walkforward as wf


def _minutes(n=2000, t0=1790000000 - 1790000000 % 300, seed=1):
    rng = np.random.default_rng(seed)
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.001, n)))
    o = np.r_[c[0], c[:-1]]
    h = np.maximum(o, c) * (1 + np.abs(rng.normal(0, 0.0005, n)))
    l = np.minimum(o, c) * (1 - np.abs(rng.normal(0, 0.0005, n)))
    qv = rng.uniform(1e5, 2e5, n)
    tbq = qv * rng.uniform(0.3, 0.7, n)
    idx = t0 + 60 * np.arange(n)
    return pd.DataFrame({"o": o, "h": h, "l": l, "c": c, "qv": qv, "tbq": tbq, "cb_c": c * 0.999, "cb_o": o * 0.999}, index=idx)


class TestNoLookAhead(unittest.TestCase):
    def test_decision_row_is_last_closed_minute(self):
        self.assertEqual(wf.decision_row(1790000136), 1790000040)  # 1790000100 still forming at +36s
        self.assertEqual(wf.decision_row(1790000160), 1790000100)

    def test_features_ignore_everything_after_the_decision(self):
        df = _minutes()
        rts = int(df.index[1500] - df.index[1500] % 300)
        t_dec = rts + 136  # 164s left
        f1 = wf.round_features(wf.minute_features(df), rts, t_dec)
        k = wf.decision_row(t_dec)
        df2 = df.copy()
        future = df2.index > k
        df2.loc[future, ["o", "h", "l", "c", "cb_c", "cb_o"]] *= 1.05
        df2.loc[future, "tbq"] = df2.loc[future, "qv"]
        f2 = wf.round_features(wf.minute_features(df2), rts, t_dec)
        for name in wf.ALL_FEATURES:
            self.assertAlmostEqual(f1[name], f2[name], places=12, msg=name)

    def test_distance_is_move_since_round_open(self):
        df = _minutes()
        rts = int(df.index[1500] - df.index[1500] % 300)
        mf = wf.minute_features(df)
        f = wf.round_features(mf, rts, rts + 136)
        k = wf.decision_row(rts + 136)
        self.assertAlmostEqual(f["dist_bn"], (df.loc[k, "c"] - df.loc[rts, "o"]) / df.loc[rts, "o"], places=12)
        self.assertAlmostEqual(f["secs_left_n"], 164 / 300)


class TestFolds(unittest.TestCase):
    def test_folds_are_ordered_non_overlapping_with_holdout_last(self):
        ts = np.arange(0, 120 * 86400, 300)
        folds = wf.make_folds(ts, fold_days=10, min_train_days=30, holdout_days=20)
        self.assertEqual(folds[-1][0], "holdout")
        self.assertEqual(folds[0][1], 30 * 86400)
        for (_, a1, b1), (_, a2, b2) in zip(folds, folds[1:]):
            self.assertEqual(b1, a2)
            self.assertLess(a1, b1)
        self.assertEqual(folds[-1][2], int(ts.max()) + 1)


class TestTrades(unittest.TestCase):
    def test_one_bet_per_round_at_first_qualifying_checkpoint_with_costs(self):
        test = pd.DataFrame({"coin": ["BTC"] * 3, "round_ts": [300] * 3, "secs_left": [164, 104, 44],
                             "p_up": [0.50, 0.50, 0.50], "y": [1, 1, 1]})
        q = np.array([0.52, 0.70, 0.90])  # first checkpoint: EV too small; second qualifies
        bets = wf.simulate_trades(test, q)
        self.assertEqual(len(bets), 1)
        b = bets.iloc[0]
        self.assertEqual(b.secs_left, 104)
        self.assertEqual(b.side, "UP")
        price = 0.51
        sh = 1 / price
        self.assertAlmostEqual(b.pnl, sh - 1 - sh * 0.07 * price * (1 - price), places=9)

    def test_down_side_and_no_bet_without_edge(self):
        test = pd.DataFrame({"coin": ["ETH", "ETH"], "round_ts": [300, 600], "secs_left": [104, 104],
                             "p_up": [0.80, 0.50], "y": [0, 1]})
        bets = wf.simulate_trades(test, np.array([0.40, 0.505]))
        self.assertEqual(len(bets), 1)
        self.assertEqual(bets.iloc[0].side, "DOWN")
        self.assertTrue(bets.iloc[0].won)


class TestMarketPoints(unittest.TestCase):
    def test_nearest_point_per_checkpoint_and_label(self):
        db = os.path.join(tempfile.mkdtemp(), "h.db")
        from market_data.history import HistoryStore
        st = HistoryStore(db)
        base = {"slug": "s", "condition_id": "c", "up_token": "u", "down_token": "d", "price_to_beat": 1.0,
                "final_price": 2.0, "volume": 1.0, "closed": 1}
        st.put_rounds([dict(base, coin="BTC", round_ts=300, outcome="UP")])
        st.put_prices([("BTC", 300, 300 + 136, 0.6), ("BTC", 300, 300 + 140, 0.7), ("BTC", 300, 300 + 196, 0.8),
                       ("BTC", 300, 300 + 256, 0.95), ("BTC", 300, 300 + 299, 1.0)])
        pts = wf.market_points(db, ["BTC"]).sort_values("checkpoint")
        self.assertEqual(list(pts.checkpoint), [60, 120, 180])
        # 180 checkpoint: 164s left (|16|) beats 160s left (|20|); the 1.0 point is excluded (settled)
        self.assertEqual(list(pts.p_up), [0.95, 0.8, 0.6])
        self.assertTrue((pts.y == 1).all())


class TestControls(unittest.TestCase):
    def _synthetic(self, edge: bool, n_rounds=6000, seed=3):
        rng = np.random.default_rng(seed)
        rows = n_rounds * 3
        ds = pd.DataFrame(rng.normal(0, 1, (rows, len(wf.ALL_FEATURES))), columns=wf.ALL_FEATURES)
        ds["round_ts"] = np.repeat(np.arange(n_rounds) * 300 + 1_780_000_200, 3)
        ds["coin"] = "BTC"
        ds["checkpoint"] = np.tile([180, 120, 60], n_rounds)
        ds["secs_left"] = np.tile([164, 104, 44], n_rounds)
        m = 1 / (1 + np.exp(-rng.normal(0, 1, rows)))
        ds["p_up"] = m
        logit_m = np.log(m / (1 - m))
        true = 1 / (1 + np.exp(-(logit_m + (1.5 * ds["imb1"].values if edge else 0.0))))
        ds["y"] = (rng.uniform(size=rows) < true).astype(int)
        ds["mkt_logit"] = logit_m
        return ds

    def test_harness_finds_a_real_edge(self):
        ds = self._synthetic(edge=True)
        ev = wf.evaluate(wf.walk_forward(ds, fold_days=3, min_train_days=6, holdout_days=4, ablation=False))
        self.assertGreater(ev["models"]["logit"]["gain_ci"][0], 0.0)
        self.assertGreater(ev["models"]["logit"]["pnl"], 0.0)

    def test_harness_does_not_invent_an_edge(self):
        ds = self._synthetic(edge=False)
        ev = wf.evaluate(wf.walk_forward(ds, fold_days=3, min_train_days=6, holdout_days=4, ablation=False))
        self.assertLessEqual(ev["models"]["logit"]["gain_ci"][0], 0.0)
        self.assertFalse(ev["pass"]["PASS"])


if __name__ == "__main__":
    unittest.main()
