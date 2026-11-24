"""
Tests for the EMA + market structure strategy: swings are only used once confirmed, and
higher-high/higher-low reads as bullish, lower-high/lower-low as bearish.
"""

import unittest

import numpy as np

import tests  # noqa: F401
from research.strategies.ema_structure import structure


def zigzag(points, step=10):
    """Piecewise-linear path through the given turning points, `step` candles per leg."""
    out = []
    for a, b in zip(points[:-1], points[1:]):
        out += list(np.linspace(a, b, step, endpoint=False))
    return np.array(out + [points[-1]], float)


class TestStructure(unittest.TestCase):
    def test_rising_zigzag_is_bullish_falling_is_bearish(self):
        up = zigzag([100, 120, 110, 130, 120, 140, 130, 150])
        self.assertEqual(structure(up + 0.5, up - 0.5, 3)[-1], 1)
        down = zigzag([150, 130, 140, 120, 130, 110, 120, 100])
        self.assertEqual(structure(down + 0.5, down - 0.5, 3)[-1], -1)

    def test_no_look_ahead(self):
        x = zigzag([100, 120, 110, 130, 120, 140, 125, 150, 135, 120, 128, 105])
        full = structure(x + 0.5, x - 0.5, 3)
        for cut in range(20, len(x)):
            part = structure(x[:cut] + 0.5, x[:cut] - 0.5, 3)
            np.testing.assert_array_equal(part, full[:cut])


if __name__ == "__main__":
    unittest.main()
