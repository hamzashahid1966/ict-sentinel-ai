import os
import tempfile
import time
import unittest
from unittest import mock

from crypto_sentinel.storage import CryptoStorageEngine


class TestDailyDrawdownReset(unittest.TestCase):
    """The daily-loss lock must be measured from each UTC day's starting balance and lift at 00:00 UTC."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.st = CryptoStorageEngine(os.path.join(self.dir.name, "c.db"))
        self.day0 = (int(time.time()) // 86400) * 86400 + 3600        # 01:00 UTC today

    def tearDown(self):
        self.dir.cleanup()

    def at(self, t):
        return mock.patch("crypto_sentinel.storage.time.time", return_value=t)

    def test_lock_lifts_next_day_and_measures_from_new_start(self):
        with self.at(self.day0):
            start = self.st.get_account().balance
            self.st.update_account(balance=start * 0.96, realized_pnl_delta=-start * 0.04)   # lose 4% today
            acc = self.st.get_account()
            self.assertTrue(acc.is_locked)
            self.assertAlmostEqual(acc.daily_drawdown_pct, 4.0, places=6)
        with self.at(self.day0 + 86400):                                  # next day
            acc = self.st.get_account()
            self.assertFalse(acc.is_locked)
            self.assertAlmostEqual(acc.daily_drawdown_pct, 0.0)
            self.assertAlmostEqual(acc.daily_starting_equity, start * 0.96)
            self.st.update_account(balance=start * 0.96 * 0.99, realized_pnl_delta=-start * 0.0096)
            acc = self.st.get_account()
            self.assertAlmostEqual(acc.daily_drawdown_pct, 1.0, places=6)  # 1% of today's start, not 4.96%
            self.assertFalse(acc.is_locked)

    def test_same_day_lock_stays(self):
        with self.at(self.day0):
            start = self.st.get_account().balance
            self.st.update_account(balance=start * 0.95, realized_pnl_delta=-start * 0.05)
        with self.at(self.day0 + 3 * 3600):
            self.assertTrue(self.st.get_account().is_locked)


if __name__ == "__main__":
    unittest.main()
