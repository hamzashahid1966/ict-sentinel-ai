"""
Unit tests for Polymarket Live Mode Integration, Manual Start Safety, and Credentials Management.
"""

import unittest
from unittest.mock import MagicMock, patch
from polymarket_sentinel.crypto_5m.live_executor import PolymarketLiveExecutor
from polymarket_sentinel.crypto_5m.paper_scalper import Btc5mPaperScalper
from polymarket_sentinel.controller import PolymarketController


class TestPolymarketLive(unittest.TestCase):
    def setUp(self):
        self.executor = PolymarketLiveExecutor()
        self.mock_analyzer = MagicMock()
        self.scalper = Btc5mPaperScalper(analyzer=self.mock_analyzer, initial_bankroll=50.0)
        self.scalper.set_live_executor(self.executor)

    def test_default_safe_paper_mode(self):
        """Verifies that the scalper starts in safe PAPER mode and PAUSED by default."""
        self.assertEqual(self.scalper.trading_mode, "PAPER")
        self.assertFalse(self.scalper.is_enabled)
        state = self.scalper.get_state()
        self.assertEqual(state["trading_mode"], "PAPER")
        self.assertFalse(state["is_enabled"])

    def test_mode_toggle(self):
        """Verifies switching between PAPER and LIVE modes."""
        self.scalper.set_trading_mode("LIVE")
        self.assertEqual(self.scalper.trading_mode, "LIVE")
        self.assertEqual(self.scalper.get_state()["trading_mode"], "LIVE")

        self.scalper.set_trading_mode("PAPER")
        self.assertEqual(self.scalper.trading_mode, "PAPER")

    def test_manual_start_only(self):
        """Verifies that changing mode to LIVE does NOT start or arm the scalper automatically."""
        self.scalper.set_trading_mode("LIVE")
        self.assertFalse(self.scalper.is_enabled)

        # Requires explicit manual toggle
        self.scalper.toggle_active()
        self.assertTrue(self.scalper.is_enabled)

    def test_live_executor_status_when_unconfigured(self):
        """Verifies get_account_status when no private key is supplied."""
        executor = PolymarketLiveExecutor()
        executor.client = None
        executor.private_key = None
        status = executor.get_account_status()
        self.assertFalse(status["connected"])
        self.assertIn("Missing", status.get("reason", ""))

    def test_test_connection_creds_validation(self):
        """Verifies pre-flight credentials testing rejects empty or invalid key safely without crashing."""
        res = self.executor.test_connection_creds("", "", 0)
        self.assertFalse(res["connected"])
        self.assertIn("No private key", res["reason"])

        res2 = self.executor.test_connection_creds("invalid_key", "", 0)
        self.assertFalse(res2["connected"])


if __name__ == "__main__":
    unittest.main()
