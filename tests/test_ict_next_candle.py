"""
Tests for the "predict the next candle" strategies: the classifier follows the document's code,
and the New York session version holds positions only through 09:00-13:00 NY.
"""

import unittest

import numpy as np
import pandas as pd

import tests  # noqa: F401
from research.strategies.ict_candle_signature import classify
from research.strategies import ict_sessions_ny as S


class TestClassify(unittest.TestCase):
    def one(self, ph, pl, h, l, c):
        return classify(np.array([ph]), np.array([pl]), np.array([h]), np.array([l]), np.array([c]))[0]

    def test_document_cases(self):
        self.assertEqual(self.one(10, 5, 11, 6, 9), -1)     # took high, closed back inside -> bearish reversal
        self.assertEqual(self.one(10, 5, 9, 4, 6), 1)       # took low, closed back inside -> bullish reversal
        self.assertEqual(self.one(10, 5, 12, 6, 11), 1)     # closed above the high -> bullish continuation
        self.assertEqual(self.one(10, 5, 9, 3, 4), -1)      # closed below the low -> bearish continuation
        self.assertEqual(self.one(10, 5, 9, 6, 7), 0)       # inside candle -> no trade
        self.assertEqual(self.one(10, 5, 11, 3, 4), -1)     # outside, closes below low: the code's order says reversal


class TestSessions(unittest.TestCase):
    def test_novo3_holds_only_through_new_york_morning(self):
        idx = pd.date_range("2026-07-01 00:00", periods=24 * 5, freq="h", tz="UTC")
        rng = np.random.default_rng(0)
        c = 100 + np.cumsum(rng.normal(0, 1, len(idx)))
        df = pd.DataFrame({"o": c, "h": c + 1, "l": c - 1, "c": c, "volume": 1.0, "buy_volume": 0.5, "funding": 0.0},
                          index=idx)
        s = S.signal(df, "novo3")
        ny = idx.tz_convert("America/New_York")
        earned = ny[1:][s[:-1] != 0].hour            # s[i] earns bar i+1
        self.assertTrue(len(earned) > 0)
        self.assertTrue(set(earned) <= {9, 10, 11, 12})


if __name__ == "__main__":
    unittest.main()
