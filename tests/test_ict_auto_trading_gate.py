"""
The ICT engine's live auto-trading is gated by ICT_AUTO_TRADING_ENABLED (default off)
after the 24-month validation in docs/GOLD_LONDON_MODEL_VALIDATION.md found no edge.
Position management, diagnostics and the demo replay keep working; only NEW live
entries are suppressed.
"""

import datetime
import unittest
from unittest.mock import MagicMock, patch

import tests  # noqa: F401
from ict_sentinel.config import NY_TZ
from ict_sentinel.models import Candle


def _fresh_candles(n=30):
    now = datetime.datetime.now(datetime.timezone.utc).replace(second=0, microsecond=0)
    out = []
    for i in range(n):
        ts = now - datetime.timedelta(minutes=5 * (n - 1 - i))
        out.append(Candle(timestamp=ts, timestamp_et=ts.astimezone(NY_TZ), open=3000.0, high=3001.0, low=2999.0, close=3000.5, volume=1.0))
    return out


class TestAutoTradingGate(unittest.TestCase):
    def _bot(self):
        import ict_sentinel.web_server as ws
        with patch.object(ws, "StorageEngine"), patch.object(ws, "DataFeedEngine"), patch.object(ws, "MemoryEngine"), \
             patch.object(ws, "OrderManager"), patch.object(ws, "AIAdvisor"):
            bot = ws.BotController()
        bot.data_feed.fetch_recent_bars = MagicMock(return_value=_fresh_candles())
        bot.data_feed.candle_cache = {}
        bot.order_mgr.update_positions_with_bar = MagicMock(return_value=[])
        bot.order_mgr.open_position_from_signal = MagicMock(return_value=object())
        bot.ipda = MagicMock()
        bot.ipda.get_current_session.return_value = "LONDON_CORE"
        bot.ipda.bars_are_fresh.return_value = True
        bot.ipda.evaluate_market.return_value = MagicMock(direction="LONG", asset="GOLD", entry_price=1.0, stop_loss=0.5, target_head_shot=2.0)
        bot.broadcast_state = MagicMock()
        return bot

    def test_disabled_gate_blocks_new_entries_but_still_manages_positions(self):
        bot = self._bot()
        bot.auto_trading_enabled = False
        bot._execute_cycle()
        bot.order_mgr.update_positions_with_bar.assert_called()
        bot.order_mgr.open_position_from_signal.assert_not_called()
        self.assertTrue(any("DISABLED" in e["title"].upper() for e in bot.activity_events))

    def test_enabled_gate_lets_entries_through(self):
        bot = self._bot()
        bot.auto_trading_enabled = True
        bot._execute_cycle()
        bot.order_mgr.open_position_from_signal.assert_called()

    def test_default_comes_from_config_and_is_off(self):
        from ict_sentinel.config import AUTO_TRADING_ENABLED
        self.assertFalse(AUTO_TRADING_ENABLED)


if __name__ == "__main__":
    unittest.main()
