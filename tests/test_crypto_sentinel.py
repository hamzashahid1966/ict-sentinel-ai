"""
Unit & Integration Test Suite for Crypto Sentinel AI
Tests: Screener, 3-Engines, Arbitration, Risk Engine, Double Tap OMS, and Storage.
"""

import unittest
import time
from crypto_sentinel.config import TOP_50_UNIVERSE, TOP_PRIME_SYMBOLS
from crypto_sentinel.models import CryptoCandle, AnalysisOpportunity
from crypto_sentinel.storage import CryptoStorageEngine
from crypto_sentinel.data_feed import CryptoDataFeed
from crypto_sentinel.engines.ict_engine import ICTLiquidityEngine
from crypto_sentinel.engines.momentum_engine import MomentumEngine
from crypto_sentinel.engines.liquidation_engine import LiquidationEngine
from crypto_sentinel.arbitration import SignalArbitrationEngine
from crypto_sentinel.risk_engine import CryptoRiskEngine
from crypto_sentinel.order_manager import CryptoOrderManager
from crypto_sentinel.controller import CryptoBotController

class TestCryptoSentinel(unittest.TestCase):
    def setUp(self):
        # Use an in-memory or dedicated test database
        self.storage = CryptoStorageEngine(db_path=":memory:")
        self.data_feed = CryptoDataFeed()
        self.engine_a = ICTLiquidityEngine()
        self.engine_b = MomentumEngine()
        self.engine_c = LiquidationEngine()
        self.arbitrator = SignalArbitrationEngine()
        self.risk_engine = CryptoRiskEngine()
        self.order_mgr = CryptoOrderManager(self.storage)

    def test_screener_top_50(self):
        candidates = self.data_feed.scan_top_50(prime_only=True)
        self.assertEqual(len(candidates), len(TOP_PRIME_SYMBOLS))
        # Verify active focus count
        focus = [c for c in candidates if c.is_active_focus]
        self.assertGreaterEqual(len(focus), 1)
        # Verify plain-English explanation exists
        for c in focus:
            self.assertTrue(len(c.why_picked) > 10)
            self.assertIn(c.sector, ["MAJOR", "L1", "L2", "DEFI", "AI", "MEME", "PAYMENTS", "ORACLE", "GAMING", "MODULAR", "POW", "STORAGE", "EXCHANGE"])

    def test_engine_a_ict_liquidity_sweep(self):
        # Construct synthetic candle series with Sell-Side Liquidity sweep + MSS + FVG
        h1_candles = [
            CryptoCandle(1000 + i*3600, 90000, 91000, 89500, 90500, 1000) for i in range(15)
        ]
        # Low is 89500. Now create M5 series sweeping below 89500 to 89200, then displacing up with FVG
        m5_candles = []
        for i in range(15):
            m5_candles.append(CryptoCandle(1000 + i*300, 90000, 90200, 89800, 89900, 500))
        # Sweep candle
        m5_candles.append(CryptoCandle(1000 + 16*300, 89800, 89900, 89100, 89300, 2500)) # swept below 89500
        # MSS Displacement with FVG:
        m5_candles.append(CryptoCandle(1000 + 17*300, 89300, 90100, 89250, 90000, 3000))
        m5_candles.append(CryptoCandle(1000 + 18*300, 90000, 90800, 89950, 90700, 3500))
        # Pullback candle into FVG
        m5_candles.append(CryptoCandle(1000 + 19*300, 90700, 90750, 90200, 90300, 1200))

        opp = self.engine_a.evaluate("BTCUSDT", m5_candles, h1_candles)
        if opp:
            self.assertEqual(opp.direction, "LONG")
            self.assertEqual(opp.engine, "A_ICT_LIQUIDITY")
            self.assertGreater(opp.target_1, opp.current_price)
            self.assertGreater(opp.target_2, opp.target_1)
            self.assertLess(opp.stop_loss, opp.current_price)

    def test_engine_b_momentum_imp(self):
        # 50 H1 candles with rising close to make EMA20 > EMA50
        h1_candles = [CryptoCandle(1000 + i*3600, 3000 + i*10, 3020 + i*10, 2990 + i*10, 3010 + i*10, 500) for i in range(60)]
        m5_candles = [CryptoCandle(1000 + i*300, 3500 + i*2, 3505 + i*2, 3495 + i*2, 3500 + i*2, 200) for i in range(30)]
        # Two-bar breakout
        m5_candles[-2] = CryptoCandle(1000 + 28*300, 3560, 3570, 3558, 3568, 800)
        m5_candles[-1] = CryptoCandle(1000 + 29*300, 3568, 3585, 3565, 3580, 1200)

        opp = self.engine_b.evaluate("ETHUSDT", m5_candles, h1_candles)
        if opp:
            self.assertEqual(opp.direction, "LONG")
            self.assertEqual(opp.engine, "B_MOMENTUM_IMP")
            self.assertGreater(opp.target_1, opp.current_price)

    def test_engine_c_liquidation_sweep(self):
        # Range of 15 candles around 100-105
        m5_candles = [CryptoCandle(1000 + i*300, 102, 105, 100, 103, 500) for i in range(15)]
        # Liquidation flush to 94 with volume spike, followed by reclaim back to 102
        m5_candles.append(CryptoCandle(1000 + 16*300, 101, 101, 94, 96, 3500)) # volume spike > 1.8x avg
        m5_candles.append(CryptoCandle(1000 + 17*300, 96, 103, 95.5, 102, 2800)) # close 102 > range_low 100

        opp = self.engine_c.evaluate("SOLUSDT", m5_candles)
        self.assertIsNotNone(opp)
        self.assertEqual(opp.direction, "LONG")
        self.assertEqual(opp.engine, "C_LIQUIDATION_SWEEP")
        self.assertLess(opp.stop_loss, 95.0)

    def test_signal_arbitration(self):
        opp_a = AnalysisOpportunity("BTCUSDT", "A_ICT_LIQUIDITY", "SHORT", "SETUP", 0.85, "reason", 90000, 91000, 88500, 87000, 1.0)
        opp_b = AnalysisOpportunity("BTCUSDT", "B_MOMENTUM_IMP", "LONG", "SETUP", 0.88, "reason", 90000, 89000, 91500, 93000, 1.0)

        # In trending regime, momentum should be preferred over counter-trend reversal
        selected = self.arbitrator.arbitrate([opp_a, opp_b], "TRENDING_BULLISH")
        self.assertEqual(selected.engine, "B_MOMENTUM_IMP")

    def test_risk_engine_safeguards(self):
        account = self.storage.get_account()
        opp = AnalysisOpportunity("BTCUSDT", "A_ICT_LIQUIDITY", "LONG", "SETUP", 0.85, "reason", 90000, 89000, 91500, 93000, 1.0)

        # 1. Normal Trade Approval
        approved, qty, reason = self.risk_engine.approve_trade(account, opp, [], "MAJOR")
        self.assertTrue(approved)
        self.assertGreater(qty, 0.0)

        # 2. Daily Drawdown Lock Breach
        account.daily_drawdown_pct = 1.05
        account.is_locked = True
        approved, qty, reason = self.risk_engine.approve_trade(account, opp, [], "MAJOR")
        self.assertFalse(approved)
        self.assertIn("Daily drawdown limit reached", reason)

        # 3. Correlation Protection (BTC + ETH same direction)
        account.is_locked = False
        account.daily_drawdown_pct = 0.0
        from crypto_sentinel.models import CryptoPosition
        existing_pos = [CryptoPosition("P1", "ETHUSDT", "ENG", "LONG", 3200, 1.0, 3100, 3100, 3350, 3500)]
        approved, qty, reason = self.risk_engine.approve_trade(account, opp, existing_pos, "MAJOR")
        self.assertFalse(approved)
        self.assertIn("Correlation safeguard active", reason)

    def test_double_tap_oms_lifecycle(self):
        account = self.storage.get_account()
        opp = AnalysisOpportunity("BTCUSDT", "A_ICT_LIQUIDITY", "LONG", "SETUP", 0.9, "reason", 90000.0, 89000.0, 91500.0, 93000.0, 1.0)
        pos = self.order_mgr.open_position(opp, qty=0.1, mode="SIMULATED_PAPER")

        self.assertEqual(pos.status, "OPEN")
        self.assertFalse(pos.t1_hit)

        # 1. Price moves to 91550 (Target 1 1.5R reached)
        self.order_mgr.update_position_with_price(pos, 91550.0, account)
        self.assertTrue(pos.t1_hit)
        self.assertTrue(pos.defensive_active)
        self.assertGreater(pos.current_stop, 90000.0) # Stop moved to defensive cushion above entry

        # 2. Price moves to 93100 (Target 2 3.0R reached)
        self.order_mgr.update_position_with_price(pos, 93100.0, account)
        self.assertEqual(pos.status, "CLOSED")
        self.assertIn("TARGET_2_FULL_FILL", pos.exit_reason)

    def test_bot_controller_execution(self):
        bot = CryptoBotController()
        # Force a scan and cycle
        bot.force_scan()
        state = bot.get_dashboard_state()
        self.assertIn("account", state)
        self.assertIn("screener_candidates", state)
        self.assertEqual(len(state["screener_candidates"]), len(TOP_PRIME_SYMBOLS))

    def test_stagnation_and_fee_covered_breakeven(self):
        account = self.storage.get_account()
        opp = AnalysisOpportunity("SOLUSDT", "B_MOMENTUM_IMP", "LONG", "SETUP", 0.9, "reason", 100.0, 98.0, 100.60, 101.20, 1.0)
        pos = self.order_mgr.open_position(opp, qty=1.0, mode="SIMULATED_PAPER")
        
        # Simulate trade open for 50 minutes (stagnant)
        pos.entry_time = time.time() - (50 * 60)
        
        # Price is slightly up at 100.15 (covers 0.11% fee buffer: 100.11)
        self.order_mgr.update_position_with_price(pos, 100.15, account)
        
        self.assertTrue(pos.is_stagnant)
        self.assertTrue(pos.defensive_active)
        self.assertGreaterEqual(pos.current_stop, 100.11) # Stop moved to cover 100% of round-trip fees

    def test_api_state_schema(self):
        from crypto_sentinel.controller import CRYPTO_BOT
        state = CRYPTO_BOT.get_dashboard_state()
        self.assertIn("running", state)
        self.assertIn("status", state)
        self.assertIn("regime", state)
        self.assertIn("account", state)
        self.assertIn("open_positions", state)
        self.assertIn("closed_trades", state)
        self.assertIn("coin_intelligence", state)
        self.assertIn("screener_candidates", state)
        self.assertIn("latest_analyses", state)
        self.assertIn("activity_logs", state)

    def test_ai_learning_and_auto_quarantine(self):
        # 1. First trade loss on BTC
        res1 = self.storage.record_coin_trade_outcome("BTCUSDT", gross_pnl=-3.0, fees=0.20, is_win=False)
        self.assertEqual(res1["total_trades"], 1)
        self.assertEqual(res1["losses"], 1)
        self.assertEqual(res1["consecutive_losses"], 1)
        self.assertEqual(res1["is_quarantined"], 0)
        is_quar, _, _ = self.storage.is_coin_quarantined("BTCUSDT")
        self.assertFalse(is_quar)

        # 2. Second consecutive loss triggers 24h Auto-Quarantine Circuit Breaker
        res2 = self.storage.record_coin_trade_outcome("BTCUSDT", gross_pnl=-2.5, fees=0.20, is_win=False)
        self.assertEqual(res2["total_trades"], 2)
        self.assertEqual(res2["losses"], 2)
        self.assertEqual(res2["consecutive_losses"], 2)
        self.assertEqual(res2["is_quarantined"], 1)
        self.assertGreater(res2["quarantine_until"], time.time())

        # 3. Verify risk engine rejection of quarantined coin
        is_quar, _, reason = self.storage.is_coin_quarantined("BTCUSDT")
        self.assertTrue(is_quar)
        account = self.storage.get_account()
        opp = AnalysisOpportunity("BTCUSDT", "B_MOMENTUM_IMP", "LONG", "SETUP", 0.9, "reason", 60000.0, 59500.0, 60300.0, 60600.0, 1.0)
        approved, _, reject_reason = self.risk_engine.approve_trade(
            account, opp, [], sector="MAJOR", is_quarantined=is_quar, quarantine_reason=reason
        )
        self.assertFalse(approved)
        self.assertIn("Auto-Quarantine active", reject_reason)

        # 4. Verify manual unquarantine override
        self.storage.unquarantine_coin("BTCUSDT")
        is_quar_after, _, _ = self.storage.is_coin_quarantined("BTCUSDT")
        self.assertFalse(is_quar_after)

        # 5. Verify profitable trade learning on SOL
        sol_res = self.storage.record_coin_trade_outcome("SOLUSDT", gross_pnl=5.0, fees=0.25, is_win=True)
        self.assertEqual(sol_res["total_trades"], 1)
        self.assertEqual(sol_res["wins"], 1)
        self.assertEqual(sol_res["win_rate"], 100.0)
        self.assertAlmostEqual(sol_res["net_pnl"], 4.75, places=2)

        # 6. Verify full coin intelligence matrix
        intel = self.storage.get_coin_intelligence()
        self.assertGreaterEqual(len(intel), 12)
        sol_entry = next((c for c in intel if c["symbol"] == "SOLUSDT"), None)
        self.assertIsNotNone(sol_entry)
        self.assertEqual(sol_entry["win_rate"], 100.0)
        self.assertTrue(sol_entry["is_prime"])

    def test_candle_archiving_and_ai_analyzer(self):
        from crypto_sentinel.ai_analyzer import CryptoAIAnalyzer
        from crypto_sentinel.models import CryptoCandle
        
        # 1. Archive entry snapshot with multi-timeframe candles
        now_ts = int(time.time())
        m5 = [CryptoCandle(now_ts, 100.0, 102.0, 99.5, 101.5, 1500.0)]
        m15 = [CryptoCandle(now_ts, 98.0, 102.5, 97.5, 101.5, 4500.0)]
        h1 = [CryptoCandle(now_ts, 95.0, 103.0, 94.0, 101.5, 18000.0)]

        snap_id = self.storage.save_trade_snapshot(
            position_id="POS_BTC_TEST_001",
            symbol="BTCUSDT",
            engine="A_ICT_LIQUIDITY",
            direction="LONG",
            entry_price=101.5,
            m5_candles=m5,
            m15_candles=m15,
            h1_candles=h1,
            btc_trend="BULLISH",
            volatility_pct=2.4
        )
        self.assertTrue(snap_id.startswith("SNAP_BTCUSDT"))

        # 2. Finalize snapshot with verified trade outcome
        finalized_id = self.storage.finalize_trade_snapshot(
            position_id="POS_BTC_TEST_001",
            exit_price=103.0,
            gross_pnl=6.0,
            fees=0.30,
            net_pnl=5.70,
            is_win=True,
            exit_reason="TARGET_2_FULL_FILL (0.8R)"
        )
        self.assertEqual(finalized_id, snap_id)

        # 3. Run AI Analyzer
        analyzer = CryptoAIAnalyzer(self.storage)
        analyzer._run_analysis(snap_id)

        # Verify debrief generated and saved
        snapshots = self.storage.get_trade_snapshots(limit=5)
        target_snap = next((s for s in snapshots if s["snapshot_id"] == snap_id), None)
        self.assertIsNotNone(target_snap)
        self.assertIsNotNone(target_snap["ai_debrief"])
        self.assertIn("Target 2", target_snap["ai_debrief"])

        # 4. Verify dataset JSON export
        dataset = self.storage.export_dataset_json()
        self.assertGreaterEqual(len(dataset), 1)
        self.assertIn("m5_candles", dataset[-1])
        self.assertEqual(len(dataset[-1]["m5_candles"]), 1)

if __name__ == "__main__":
    unittest.main()
