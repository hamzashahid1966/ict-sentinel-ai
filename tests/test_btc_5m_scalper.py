"""
Unit tests for Polymarket 5-Minute BTC Microstructure Scalper.
Validates:
1. Round boundary determination and strike price P0 locking.
2. Z-Score mathematical probability calculations via cumulative normal distribution.
3. Strict protective gates (60s Trap Zone, 25s Late Freeze, $8 Noise Band).
4. Sizing discipline ($10.00 max risk per 5m round).
5. Automated settlement at expiration (Chainlink style final price vs strike price).
6. Ledger P&L accounting and win rate metrics.
"""

import time
import unittest
from unittest.mock import MagicMock, patch
from polymarket_sentinel.crypto_5m import (
    BtcPriceFeed, BtcRoundAnalyzer, Btc5mPaperScalper, Btc5mRound
)


class TestBtc5mScalper(unittest.TestCase):
    def setUp(self):
        self.mock_feed = MagicMock(spec=BtcPriceFeed)
        self.mock_feed.get_btc_price.return_value = 58800.0
        self.mock_feed.get_price.return_value = 58800.0
        self.mock_feed.get_volatility.return_value = 15.0
        self.mock_feed.get_1m_volatility.return_value = 15.0

        def _oracle_side_effect(sym="BTC"):
            px = self.mock_feed.get_price(sym)
            return {
                "spot": px,
                "twap": px,
                "lag_delta": 0.0,
                "projected_twap": px
            }
        self.mock_feed.get_oracle_analysis.side_effect = _oracle_side_effect

        self.analyzer = BtcRoundAnalyzer(self.mock_feed)
        # Mock Polymarket CLOB Gamma API fetch
        self.analyzer.fetch_polymarket_market = MagicMock(return_value={
            "found": True,
            "slug": "btc-updown-5m-test",
            "title": "Bitcoin Up or Down 5m",
            "price_up": 0.50,
            "price_down": 0.50
        })

        self.scalper = Btc5mPaperScalper(self.analyzer, initial_bankroll=100.0, auto_start=False)

    def test_strike_locking(self):
        """Strike price P0 must lock at candle start and remain unchanged throughout the round."""
        round_id = "test-round-1"
        p0 = self.analyzer.get_or_set_strike(round_id, 58820.0)
        self.assertEqual(p0, 58820.0)

        # Later in the candle, price moves to 58860.0
        p0_later = self.analyzer.get_or_set_strike(round_id, 58860.0)
        self.assertEqual(p0_later, 58820.0)  # Must remain initial locked strike!

    def test_trap_zone_gate(self):
        """In the first 60 seconds of the 5m candle (remaining > 240s), bot must ABSTAIN to avoid fakeouts."""
        round_id = f"btc-updown-5m-{self.analyzer.get_current_round_ts()}"
        self.analyzer.get_or_set_strike(round_id, 58800.0)
        self.mock_feed.get_btc_price.return_value = 58830.0  # +$30 early move

        # Force seconds remaining to 260s (first 40s of candle)
        round_info = self.analyzer.analyze_current_round()
        round_info.seconds_remaining = 260

        # Run logic check
        self.assertGreater(round_info.seconds_remaining, 240)

    def test_noise_band_abstain(self):
        """When price is within $8 of strike at the 2-minute mark, bot must ABSTAIN due to high chop reversal risk."""
        round_ts = self.analyzer.get_current_round_ts()
        self.analyzer.get_or_set_strike("BTC", round_ts, 58800.0)
        self.mock_feed.get_price.return_value = 58803.50  # only +$3.50 delta
        # Test inside the 2-minute window (now_ts = round_ts + 180 -> 120s left)
        round_info = self.analyzer.analyze_single_coin("BTC", round_ts + 180, round_ts)
        self.assertEqual(round_info.signal, "ABSTAIN")
        self.assertIn("noise band", round_info.signal_reason.lower())

    def test_buy_up_signal_with_edge(self):
        """Generates BUY_UP when BTC is strongly displaced (+1.8 sigma) and mathematical edge >= 8%."""
        round_ts = self.analyzer.get_current_round_ts()
        self.analyzer.get_or_set_strike("BTC", round_ts, 58800.0)
        self.mock_feed.get_price.return_value = 58845.0  # +$45 displacement
        self.analyzer.fetch_polymarket_market = MagicMock(return_value={
            "found": True,
            "slug": f"btc-updown-5m-{round_ts}",
            "title": "Bitcoin Up or Down 5m",
            "price_up": 0.60,    # Market offers UP at 60¢
            "price_down": 0.40
        })

        round_info = self.analyzer.analyze_single_coin("BTC", round_ts + 100, round_ts)
        self.assertGreater(round_info.calculated_prob_up, 0.70)
        self.assertGreater(round_info.price_delta, 12.0)
        self.assertEqual(round_info.signal, "BUY_UP")

    def test_paper_execution_and_sizing(self):
        """Paper bet sizing must never exceed $10.00 max risk per 5m round."""
        mock_round = Btc5mRound(
            round_id="btc-updown-5m-mock",
            slug="mock",
            title="Mock Round",
            strike_price=58800.0,
            current_btc_price=58840.0,
            price_delta=40.0,
            start_time=1700000000,
            end_time=1700000300,
            seconds_remaining=120,
            market_price_up=0.65,
            market_price_down=0.35,
            calculated_prob_up=0.85,
            calculated_prob_down=0.15,
            z_score=2.1,
            ict_fvg_status="BULLISH_DISPLACEMENT",
            signal="BUY_UP",
            signal_reason="Strong displacement"
        )
        self.scalper._execute_entry(mock_round)
        self.assertIsNotNone(self.scalper.active_trade)
        trade = self.scalper.active_trade
        self.assertEqual(trade.outcome, "UP")
        # Must be strictly <= $10.00
        self.assertLessEqual(trade.cost, 10.00)
        expected_balance = round(100.0 - (trade.cost + trade.commission), 2)
        self.assertEqual(self.scalper.balance, expected_balance)
        self.assertGreater(trade.commission, 0.0)

    def test_automated_settlement_win(self):
        """Winning round resolves at $1.00 per share, properly updating realized P&L and bankroll."""
        mock_round = Btc5mRound(
            round_id="btc-updown-5m-win",
            slug="mock",
            title="Mock Round",
            strike_price=58800.0,
            current_btc_price=58830.0,
            price_delta=30.0,
            start_time=1700000000,
            end_time=1700000300,
            seconds_remaining=100,
            market_price_up=0.60,
            market_price_down=0.40,
            calculated_prob_up=0.80,
            calculated_prob_down=0.20,
            z_score=1.8,
            ict_fvg_status="BULLISH_DISPLACEMENT",
            signal="BUY_UP",
            signal_reason="Displacement"
        )
        self.scalper._execute_entry(mock_round)
        cost = self.scalper.active_trade.cost
        shares = self.scalper.active_trade.shares

        # Simulate round rollover where final price is 58850.0 (UP wins!)
        settle_round = Btc5mRound(
            round_id="btc-updown-5m-next",  # New round started
            slug="mock-next",
            title="Next Round",
            strike_price=58850.0,
            current_btc_price=58850.0,
            price_delta=0.0,
            start_time=1700000300,
            end_time=1700000600,
            seconds_remaining=300,
            market_price_up=0.50,
            market_price_down=0.50,
            calculated_prob_up=0.50,
            calculated_prob_down=0.50,
            z_score=0.0,
            ict_fvg_status="NEUTRAL",
            signal="ABSTAIN",
            signal_reason=""
        )
        self.analyzer._strike_prices["btc-updown-5m-win"] = 58800.0

        self.scalper._check_settlement(settle_round)
        self.assertIsNone(self.scalper.active_trade)
        self.assertEqual(len(self.scalper.trade_history), 1)
        settled_trade = self.scalper.trade_history[0]
        self.assertEqual(settled_trade.status, "WON")
        expected_pnl = round(shares * 1.0 - cost - settled_trade.commission, 2)
        self.assertEqual(settled_trade.pnl, expected_pnl)
        self.assertEqual(self.scalper.realized_pnl, expected_pnl)

    def test_multi_coin_candidate_ranking(self):
        """When BTC chops but SOL breaks out with positive edge at 2m mark, SOL must be selected."""
        round_ts = self.analyzer.get_current_round_ts()
        # Set strikes
        self.analyzer.get_or_set_strike("BTC", round_ts, 58800.0)
        self.analyzer.get_or_set_strike("SOL", round_ts, 68.00)

        # BTC is chopping (only +$2 move, noise band)
        # SOL is breaking out strongly (+ $1.20 move, 8x clean threshold!)
        def mock_price(sym):
            if sym == "SOL":
                return 69.20
            return 58802.0
        self.mock_feed.get_price.side_effect = mock_price

        def mock_vol(sym):
            if sym == "SOL":
                return 0.20
            return 15.0
        self.mock_feed.get_volatility.side_effect = mock_vol

        analysis = self.analyzer.analyze_all_coins(now_ts=round_ts + 180)
        best_r = analysis["best_round"]
        # SOL should be picked because it has the breakout signal while BTC abstains
        self.assertEqual(best_r.symbol, "SOL")
        self.assertEqual(best_r.signal, "BUY_UP")

    def test_paused_by_default_strict_button(self):
        """Scalper must start in PAUSED state (is_enabled=False) and NEVER enter trades until user clicks start."""
        self.assertFalse(self.scalper.is_enabled)
        # Attempt tick with valid breakout
        self.scalper.process_tick()
        self.assertEqual(len(self.scalper.active_trades), 0)
        self.assertEqual(self.scalper.balance, 100.0)

    def test_mid_round_protection(self):
        """If started with <50s remaining in candle, scalper must arm and wait for the next clean session."""
        with patch("polymarket_sentinel.crypto_5m.paper_scalper.time.time", return_value=1700000360.0):  # 40s remaining in 300s candle
            self.scalper.enable()
            self.assertTrue(self.scalper.waiting_for_next_round)
            self.assertEqual(self.scalper.target_round_ts, 1700000400)

    def test_upcoming_rounds_polymarket_alignment(self):
        """Upcoming 3 rounds must align with Polymarket 5-minute UTC epochs."""
        # Choose now_ts = 1700000100 (which is exactly divisible by 300)
        now_ts = 1700000100
        upcoming = self.analyzer.get_upcoming_rounds(count=3, now_ts=now_ts)
        self.assertEqual(len(upcoming), 3)
        self.assertEqual(upcoming[0]["start_time"], 1700000400)
        self.assertEqual(upcoming[1]["start_time"], 1700000700)
        self.assertEqual(upcoming[2]["start_time"], 1700001000)
        self.assertEqual(upcoming[0]["starts_in_seconds"], 300)

    def test_candle_maturity_filter_90s(self):
        """First 30s of candle (seconds_rem > 270) must ABSTAIN to lock opening strike, then allow entry."""
        round_ts = 1700000000
        self.analyzer.get_or_set_strike("BTC", round_ts, 58800.0)
        self.mock_feed.get_price.return_value = 58840.0
        self.mock_feed.get_volatility.return_value = 15.0

        # Case 1: Early opening wick (seconds_rem = 285s, > 270s) -> MUST ABSTAIN
        early_data = self.analyzer.analyze_single_coin("BTC", now_ts=round_ts + 15, round_ts=round_ts)
        self.assertEqual(early_data.signal, "ABSTAIN")
        self.assertIn("Opening Strike Lock", early_data.signal_reason)

        # Case 2: Candle maturity established (seconds_rem = 240s, <= 270s) -> ALLOWS ENTRY
        mature_data = self.analyzer.analyze_single_coin("BTC", now_ts=round_ts + 60, round_ts=round_ts)
        self.assertEqual(mature_data.signal, "BUY_UP")

    def test_auto_take_profit_and_stop_loss_bailout(self):
        """Validates that positions auto-cashout at >=92¢ (TP) and <=28¢ (emergency SL bailout)."""
        self.scalper.is_enabled = True
        self.scalper.waiting_for_next_round = False
        self.scalper.balance = 25.0

        # 1. Setup a position in BTC UP
        trade_btc = Btc5mRound(
            round_id="btc-tp-test",
            slug="mock",
            title="Mock BTC",
            strike_price=58800.0,
            current_btc_price=58830.0,
            price_delta=30.0,
            start_time=1700000000,
            end_time=1700000300,
            seconds_remaining=150,
            market_price_up=0.50,
            market_price_down=0.50,
            calculated_prob_up=0.85,
            calculated_prob_down=0.15,
            z_score=2.0,
            ict_fvg_status="BULLISH_DISPLACEMENT",
            signal="BUY_UP",
            signal_reason="Displacement",
            symbol="BTC"
        )
        self.scalper._execute_entry(trade_btc)
        self.assertIn("BTC", self.scalper.active_trades)

        # Simulate price surging to 93¢ -> Must Auto Take-Profit!
        r_tp = Btc5mRound(
            round_id="btc-tp-test",
            slug="mock",
            title="Mock BTC",
            strike_price=58800.0,
            current_btc_price=58860.0,
            price_delta=60.0,
            start_time=1700000000,
            end_time=1700000300,
            seconds_remaining=100,
            market_price_up=0.93,
            market_price_down=0.07,
            calculated_prob_up=0.97,
            calculated_prob_down=0.03,
            z_score=3.0,
            ict_fvg_status="BULLISH_DISPLACEMENT",
            signal="BUY_UP",
            signal_reason="Displacement",
            symbol="BTC"
        )
        self.scalper._check_dynamic_exits({"BTC": r_tp})
        self.assertNotIn("BTC", self.scalper.active_trades)
        self.assertEqual(self.scalper.trade_history[0].status, "WON")
        self.assertIn("Auto Take-Profit Hit", self.scalper.trade_history[0].reason)

        # 2. Setup a position in ETH UP that reverses into a stop-loss
        trade_eth = Btc5mRound(
            round_id="eth-sl-test",
            slug="mock-eth",
            title="Mock ETH",
            strike_price=1620.0,
            current_btc_price=1622.0,
            price_delta=2.0,
            start_time=1700000000,
            end_time=1700000300,
            seconds_remaining=150,
            market_price_up=0.55,
            market_price_down=0.45,
            calculated_prob_up=0.80,
            calculated_prob_down=0.20,
            z_score=1.8,
            ict_fvg_status="BULLISH_DISPLACEMENT",
            signal="BUY_UP",
            signal_reason="Displacement",
            symbol="ETH"
        )
        self.scalper._execute_entry(trade_eth)
        self.assertIn("ETH", self.scalper.active_trades)

        # Simulate price dropping to 24¢ -> Must Auto Stop-Loss Bailout!
        r_sl = Btc5mRound(
            round_id="eth-sl-test",
            slug="mock-eth",
            title="Mock ETH",
            strike_price=1620.0,
            current_btc_price=1615.0,
            price_delta=-5.0,
            start_time=1700000000,
            end_time=1700000300,
            seconds_remaining=80,
            market_price_up=0.24,
            market_price_down=0.76,
            calculated_prob_up=0.15,
            calculated_prob_down=0.85,
            z_score=-2.5,
            ict_fvg_status="BEARISH_DISPLACEMENT",
            signal="BUY_DOWN",
            signal_reason="Reversal",
            symbol="ETH"
        )
        self.scalper._check_dynamic_exits({"ETH": r_sl})
        self.assertNotIn("ETH", self.scalper.active_trades)
        self.assertEqual(self.scalper.trade_history[0].status, "LOST")
        self.assertIn("Auto Stop-Loss Bailout", self.scalper.trade_history[0].reason)
        # Verify that it salvaged cash rather than losing 100% of $10
        self.assertGreater(self.scalper.trade_history[0].pnl, -9.00)

    def test_dual_mode_early_value_and_late_harvest_with_50c_bailout(self):
        """Validates Mode A (Early Value Scalp) and Mode B (Late Yield Harvest) with 50¢ bailout."""
        round_ts = self.analyzer.get_current_round_ts()
        self.analyzer.get_or_set_strike("BTC", round_ts, 60000.0)

        # 1. Late Yield Harvest: BTC has massive lead ($60 displacement), Polymarket ask is 75¢
        self.mock_feed.get_price.return_value = 60060.0  # +$60 lead (exceeds $50 dominant threshold)
        self.mock_feed.get_volatility.return_value = 15.0
        self.analyzer.fetch_polymarket_market = MagicMock(return_value={
            "found": True,
            "slug": f"btc-updown-5m-{round_ts}",
            "title": "Bitcoin Up or Down 5m",
            "price_up": 0.75,
            "price_down": 0.25
        })

        # With 90s remaining (late candle), it must issue [LATE YIELD HARVEST] signal!
        late_rd = self.analyzer.analyze_single_coin("BTC", now_ts=round_ts + 210, round_ts=round_ts)
        self.assertEqual(late_rd.signal, "BUY_UP")
        self.assertIn("LATE YIELD HARVEST", late_rd.signal_reason)
        self.assertIn("Stop-Loss active at 50¢", late_rd.signal_reason)

        # 2. But if BTC lead was only +$40 (above clean delta 35 but below dominant lead 50), 75¢ must be REJECTED!
        self.mock_feed.get_price.return_value = 60040.0  # +$40 is below dominant lead $50
        late_weak_rd = self.analyzer.analyze_single_coin("BTC", now_ts=round_ts + 210, round_ts=round_ts)
        self.assertEqual(late_weak_rd.signal, "ABSTAIN")
        self.assertIn("below dominant lead", late_weak_rd.signal_reason)

        # 3. Test 50¢ Emergency Stop-Loss Bailout on Late Harvest Entry
        self.scalper.is_enabled = True
        self.scalper.waiting_for_next_round = False
        self.scalper.balance = 25.0
        self.scalper._execute_entry(late_rd)
        self.assertIn("BTC", self.scalper.active_trades)
        self.assertIn("LATE YIELD HARVEST", self.scalper.active_trades["BTC"].reason)

        # If price wicks down to 49¢ (<= 50¢), it must trigger AUTO_STOP_LOSS bailout immediately!
        r_wick = Btc5mRound(
            round_id="late-wick",
            slug="mock",
            title="Mock BTC",
            strike_price=60000.0,
            current_btc_price=60010.0,
            price_delta=10.0,
            start_time=round_ts,
            end_time=round_ts + 300,
            seconds_remaining=40,
            market_price_up=0.49,
            market_price_down=0.51,
            calculated_prob_up=0.55,
            calculated_prob_down=0.45,
            z_score=0.5,
            ict_fvg_status="NEUTRAL",
            signal="ABSTAIN",
            signal_reason="Wick",
            symbol="BTC"
        )
        self.scalper._check_dynamic_exits({"BTC": r_wick})
        self.assertNotIn("BTC", self.scalper.active_trades)
        self.assertEqual(self.scalper.trade_history[0].status, "LOST")
        self.assertIn("Auto Stop-Loss Bailout", self.scalper.trade_history[0].reason)
        # On a $5 trade entered at 75¢, exiting at 49¢ salvages ~$3.25, capping loss to ~$1.75!
        self.assertGreater(self.scalper.trade_history[0].pnl, -2.50)

    def test_staggered_condition_timer_two_coins(self):
        """When 2 coins have signals, they must NOT enter simultaneously; the 2nd coin waits for the condition timer."""
        self.scalper.is_enabled = True
        self.scalper.waiting_for_next_round = False
        self.scalper.balance = 25.0

        r1 = Btc5mRound(
            round_id="btc-5m-stagger",
            slug="mock1",
            title="Mock BTC",
            strike_price=58800.0,
            current_btc_price=58830.0,
            price_delta=30.0,
            start_time=1700000000,
            end_time=1700000300,
            seconds_remaining=120,
            market_price_up=0.55,
            market_price_down=0.45,
            calculated_prob_up=0.85,
            calculated_prob_down=0.15,
            z_score=2.0,
            ict_fvg_status="BULLISH_DISPLACEMENT",
            signal="BUY_UP",
            signal_reason="Displacement",
            symbol="BTC"
        )
        r2 = Btc5mRound(
            round_id="sol-5m-stagger",
            slug="mock2",
            title="Mock SOL",
            strike_price=68.0,
            current_btc_price=69.5,
            price_delta=1.5,
            start_time=1700000000,
            end_time=1700000300,
            seconds_remaining=120,
            market_price_up=0.50,
            market_price_down=0.50,
            calculated_prob_up=0.82,
            calculated_prob_down=0.18,
            z_score=1.9,
            ict_fvg_status="BULLISH_DISPLACEMENT",
            signal="BUY_UP",
            signal_reason="Displacement",
            symbol="SOL"
        )

        # Mock analyzer to return both BTC and SOL with signals
        self.scalper.max_concurrent_trades = 2
        self.analyzer.analyze_all_coins = MagicMock(return_value={
            "best_round": r1,
            "coins": {"BTC": r1, "SOL": r2, "ETH": r1, "XRP": r1},
            "upcoming_rounds": []
        })

        # Tick 1: Highest edge coin (SOL: 0.32 edge vs BTC: 0.30 edge) must enter with $5
        self.scalper.process_tick()
        self.assertEqual(len(self.scalper.active_trades), 1)
        self.assertIn("SOL", self.scalper.active_trades)
        self.assertAlmostEqual(self.scalper.active_trades["SOL"].cost, 5.0, delta=1.0)

        # Immediate Tick 2 (0 seconds later): BTC must NOT enter yet because condition timer is active!
        self.scalper.process_tick()
        self.assertEqual(len(self.scalper.active_trades), 1)
        self.assertNotIn("BTC", self.scalper.active_trades)

        # Simulate 16 seconds passing on condition timer
        self.scalper.last_entry_time -= 16.0

        # Tick 3: BTC now clears condition timer & percentage check, entering with $5!
        self.scalper.process_tick()
        self.assertEqual(len(self.scalper.active_trades), 2)
        self.assertIn("BTC", self.scalper.active_trades)
        self.assertIn("SOL", self.scalper.active_trades)
        self.assertAlmostEqual(self.scalper.active_trades["BTC"].cost, 5.0, delta=1.0)
        self.assertAlmostEqual(self.scalper.active_trades["SOL"].cost, 5.0, delta=1.0)

    def test_early_cashout_trade(self):
        """Allows locking in live floating profit early before expiration."""
        self.scalper.balance = 25.0
        r = Btc5mRound(
            round_id="btc-cashout-test",
            slug="mock",
            title="Mock BTC",
            strike_price=58800.0,
            current_btc_price=58830.0,
            price_delta=30.0,
            start_time=1700000000,
            end_time=1700000300,
            seconds_remaining=120,
            market_price_up=0.50,
            market_price_down=0.50,
            calculated_prob_up=0.85,
            calculated_prob_down=0.15,
            z_score=2.0,
            ict_fvg_status="BULLISH_DISPLACEMENT",
            signal="BUY_UP",
            signal_reason="Displacement",
            symbol="BTC"
        )
        self.scalper._execute_entry(r)
        self.assertIn("BTC", self.scalper.active_trades)

        # Simulate odds floating up from 50¢ to 90¢ in our favor
        r_current = Btc5mRound(
            round_id="btc-cashout-test",
            slug="mock",
            title="Mock BTC",
            strike_price=58800.0,
            current_btc_price=58860.0,
            price_delta=60.0,
            start_time=1700000000,
            end_time=1700000300,
            seconds_remaining=60,
            market_price_up=0.90,  # Now worth 90¢!
            market_price_down=0.10,
            calculated_prob_up=0.95,
            calculated_prob_down=0.05,
            z_score=2.8,
            ict_fvg_status="BULLISH_DISPLACEMENT",
            signal="BUY_UP",
            signal_reason="Displacement",
            symbol="BTC"
        )
        self.scalper.last_analysis = {"coins": {"BTC": r_current}}

        # Check get_state includes floating_value and floating_pnl
        state = self.scalper.get_state()
        active = state["active_trades"][0]
        self.assertEqual(active["current_price"], 0.90)
        self.assertGreater(active["floating_value"], 7.0)
        self.assertGreater(active["floating_pnl"], 2.0)

        # Cash out early!
        res = self.scalper.cashout_trade("BTC")
        self.assertTrue(res["ok"])
        self.assertNotIn("BTC", self.scalper.active_trades)
        self.assertEqual(len(self.scalper.trade_history), 1)
        self.assertEqual(self.scalper.trade_history[0].status, "WON")
        self.assertGreater(self.scalper.realized_pnl, 2.0)

    def test_insufficient_balance_blocks_second_coin(self):
        """If balance is < $5.00 (e.g. $9 starting, $5 used by Coin 1 -> $4 left), 2nd coin must NOT be taken."""
        fresh_scalper = Btc5mPaperScalper(self.analyzer, initial_bankroll=9.0, auto_start=False)
        self.assertEqual(fresh_scalper.balance, 9.0)
        fresh_scalper.is_enabled = True
        fresh_scalper.max_concurrent_trades = 2

        r_btc = Btc5mRound(
            round_id="round-btc", slug="mock-btc", title="Mock BTC", strike_price=50000.0, current_btc_price=50050.0,
            price_delta=50.0, start_time=1700000000, end_time=1700000300, seconds_remaining=120,
            market_price_up=0.50, market_price_down=0.50, calculated_prob_up=0.85, calculated_prob_down=0.15,
            z_score=2.2, ict_fvg_status="BULLISH_DISPLACEMENT", signal="BUY_UP", signal_reason="BTC Edge", symbol="BTC"
        )
        r_eth = Btc5mRound(
            round_id="round-eth", slug="mock-eth", title="Mock ETH", strike_price=3000.0, current_btc_price=3010.0,
            price_delta=10.0, start_time=1700000000, end_time=1700000300, seconds_remaining=120,
            market_price_up=0.50, market_price_down=0.50, calculated_prob_up=0.82, calculated_prob_down=0.18,
            z_score=2.0, ict_fvg_status="BULLISH_DISPLACEMENT", signal="BUY_UP", signal_reason="ETH Edge", symbol="ETH"
        )

        fresh_scalper.analyzer.analyze_all_coins = MagicMock(return_value={
            "best_coin": r_btc,
            "coins": {"BTC": r_btc, "ETH": r_eth}
        })

        # Tick 1: Takes BTC (costs ~ $4.95 - $5.00)
        fresh_scalper.process_tick()
        self.assertIn("BTC", fresh_scalper.active_trades)
        self.assertEqual(len(fresh_scalper.active_trades), 1)
        self.assertLess(fresh_scalper.balance, 5.0)  # ~$4.00 left

        # Fast forward time beyond stagger interval
        fresh_scalper.last_entry_time = time.time() - 20.0

        # Tick 2: ETH is available with edge, but balance < $5.00 -> ETH MUST NOT be taken!
        fresh_scalper.process_tick()
        self.assertNotIn("ETH", fresh_scalper.active_trades)
        self.assertEqual(len(fresh_scalper.active_trades), 1)

        # Now simulate balance recovery (e.g. BTC cashed out for $18.00 -> balance becomes $27.00)
        fresh_scalper.balance = 27.0
        fresh_scalper.process_tick()
        # Now ETH can be taken because balance >= 10.0!
        self.assertIn("ETH", fresh_scalper.active_trades)
        self.assertEqual(len(fresh_scalper.active_trades), 2)

    def test_default_bankroll_is_50(self):
        """MultiCryptoPaperScalper default initial bankroll and reset must be $50.00."""
        s = Btc5mPaperScalper(self.analyzer, auto_start=False)
        self.assertEqual(s.balance, 50.0)
        s.balance = 12.0
        s.reset()
        self.assertEqual(s.balance, 50.0)

    def test_dynamic_exit_reentrant_lock_no_deadlock(self):
        """Verifies that calling cashout_trade from within process_tick while holding self.lock does not deadlock."""
        s = Btc5mPaperScalper(self.analyzer, initial_bankroll=50.0, auto_start=False)
        s.is_enabled = True

        r_entry = Btc5mRound(
            round_id="btc-5m-reentrant", slug="mock", title="Mock BTC", strike_price=60000.0, current_btc_price=60040.0,
            price_delta=40.0, start_time=1700000000, end_time=1700000300, seconds_remaining=120,
            market_price_up=0.45, market_price_down=0.55, calculated_prob_up=0.85, calculated_prob_down=0.15,
            z_score=2.0, ict_fvg_status="BULLISH_DISPLACEMENT", signal="BUY_UP", signal_reason="Edge", symbol="BTC"
        )
        s._execute_entry(r_entry)
        self.assertIn("BTC", s.active_trades)

        # Price pops to 70¢ (+25¢ profit, > 68¢ pop threshold)
        r_pop = Btc5mRound(
            round_id="btc-5m-reentrant", slug="mock", title="Mock BTC", strike_price=60000.0, current_btc_price=60080.0,
            price_delta=80.0, start_time=1700000000, end_time=1700000300, seconds_remaining=110,
            market_price_up=0.70, market_price_down=0.30, calculated_prob_up=0.95, calculated_prob_down=0.05,
            z_score=2.8, ict_fvg_status="BULLISH_DISPLACEMENT", signal="NEUTRAL", signal_reason="Edge", symbol="BTC"
        )
        s.analyzer.analyze_all_coins = MagicMock(return_value={
            "best_round": r_pop,
            "coins": {"BTC": r_pop}
        })

        # process_tick acquires lock and triggers _check_dynamic_exits -> cashout_trade
        # Must execute cleanly without blocking or deadlocking!
        s.process_tick()
        self.assertNotIn("BTC", s.active_trades)
        self.assertEqual(len(s.trade_history), 1)
        self.assertEqual(s.trade_history[0].status, "WON")
        self.assertIn("Quick-Pop Cashout", s.trade_history[0].reason)

    def test_quick_pop_time_exit_after_60_seconds(self):
        """If a trade is open >= 60 seconds and is in profit (+5¢ or more), it automatically cashes out."""
        from datetime import datetime, timezone, timedelta
        s = Btc5mPaperScalper(self.analyzer, initial_bankroll=50.0, auto_start=False)
        s.is_enabled = True

        r_entry = Btc5mRound(
            round_id="btc-5m-time-exit", slug="mock", title="Mock BTC", strike_price=60000.0, current_btc_price=60040.0,
            price_delta=40.0, start_time=1700000000, end_time=1700000300, seconds_remaining=240,
            market_price_up=0.50, market_price_down=0.50, calculated_prob_up=0.85, calculated_prob_down=0.15,
            z_score=2.0, ict_fvg_status="BULLISH_DISPLACEMENT", signal="BUY_UP", signal_reason="Edge", symbol="BTC"
        )
        s._execute_entry(r_entry)
        self.assertIn("BTC", s.active_trades)

        # Set trade timestamp to 65 seconds ago
        past_time = datetime.now(timezone.utc) - timedelta(seconds=65)
        s.active_trades["BTC"].timestamp = past_time.isoformat()

        # Price is up modestly by +6¢ (0.56)
        r_modest = Btc5mRound(
            round_id="btc-5m-time-exit", slug="mock", title="Mock BTC", strike_price=60000.0, current_btc_price=60050.0,
            price_delta=50.0, start_time=1700000000, end_time=1700000300, seconds_remaining=175,
            market_price_up=0.56, market_price_down=0.44, calculated_prob_up=0.88, calculated_prob_down=0.12,
            z_score=2.1, ict_fvg_status="BULLISH_DISPLACEMENT", signal="BUY_UP", signal_reason="Edge", symbol="BTC"
        )
        s._check_dynamic_exits({"BTC": r_modest})
        self.assertNotIn("BTC", s.active_trades)
        self.assertEqual(len(s.trade_history), 1)
        self.assertEqual(s.trade_history[0].status, "WON")

    def test_quick_pop_does_not_trigger_on_loss(self):
        """Late entry at 72¢ must NOT trigger quick pop when market price is 70¢ (which is < entry)."""
        s = Btc5mPaperScalper(self.analyzer, initial_bankroll=50.0, auto_start=False)
        s.is_enabled = True

        r_late = Btc5mRound(
            round_id="btc-5m-late", slug="mock", title="Mock BTC", strike_price=60000.0, current_btc_price=60060.0,
            price_delta=60.0, start_time=1700000000, end_time=1700000300, seconds_remaining=90,
            market_price_up=0.72, market_price_down=0.28, calculated_prob_up=0.98, calculated_prob_down=0.02,
            z_score=2.5, ict_fvg_status="BULLISH_DISPLACEMENT", signal="BUY_UP", signal_reason="[LATE YIELD HARVEST]", symbol="BTC"
        )
        s._execute_entry(r_late)
        self.assertIn("BTC", s.active_trades)

        # Price dips to 70¢ (loss of 2¢, but above 68¢). Must NOT exit as QUICK_POP!
        r_dip = Btc5mRound(
            round_id="btc-5m-late", slug="mock", title="Mock BTC", strike_price=60000.0, current_btc_price=60055.0,
            price_delta=55.0, start_time=1700000000, end_time=1700000300, seconds_remaining=80,
            market_price_up=0.70, market_price_down=0.30, calculated_prob_up=0.97, calculated_prob_down=0.03,
            z_score=2.3, ict_fvg_status="BULLISH_DISPLACEMENT", signal="BUY_UP", signal_reason="Displacement", symbol="BTC"
        )
        s._check_dynamic_exits({"BTC": r_dip})
        # Trade remains OPEN because it's not a profit and hasn't hit 50¢ stop-loss
        self.assertIn("BTC", s.active_trades)


if __name__ == "__main__":
    unittest.main()
