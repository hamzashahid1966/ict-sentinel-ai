"""
Boot Safety Tests for the Web Command Center.
Verifies that starting the web server never forces the Polymarket 5M scalper
into LIVE real-money mode or arms it without an explicit operator action.
"""

import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from polymarket_sentinel.crypto_5m.live_executor import PolymarketLiveExecutor
from polymarket_sentinel.crypto_5m.paper_scalper import Btc5mPaperScalper


class TestWebBootSafety(unittest.TestCase):
    def _make_poly_bot(self):
        executor = PolymarketLiveExecutor()
        scalper = Btc5mPaperScalper(analyzer=MagicMock(), initial_bankroll=50.0, auto_start=False)
        scalper.set_live_executor(executor)
        return SimpleNamespace(btc_scalper=scalper, live_executor=executor)

    def test_boot_leaves_scalper_in_paper_mode_and_unarmed(self):
        """With POLYMARKET_LIVE_ENABLED unset, boot must not switch the scalper to LIVE or arm it."""
        from ict_sentinel.web_server import arm_engines_on_boot

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("POLYMARKET_LIVE_ENABLED", None)
            poly_bot = self._make_poly_bot()
            crypto_bot = MagicMock()

            arm_engines_on_boot(poly_bot=poly_bot, crypto_bot=crypto_bot)

            self.assertEqual(poly_bot.btc_scalper.trading_mode, "PAPER")
            self.assertFalse(poly_bot.btc_scalper.is_enabled)
            crypto_bot.start.assert_called_once()


if __name__ == "__main__":
    unittest.main()
