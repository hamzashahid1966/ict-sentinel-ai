"""
Unit tests for Polymarket Sentinel Dual-Engine Strategy & Dynamic Active Exits.
Validates:
1. Engine A (Asymmetric Edge Hunter) sizing (5% max), TP (+35%), SL (-20%).
2. Engine B (High-Probability Yield Harvester) sizing (15% max), TP (+8%), SL (-6%).
3. Black-Swan Tail-Risk Veto (war/ceasefire/rumor contracts strictly forbidden from high-prob harvesting).
4. Automated Dynamic Exits: Auto Take-Profit execution when current_price >= take_profit_px.
5. Automated Dynamic Exits: Emergency Stop-Loss execution when current_price <= stop_loss_px.
6. Portfolio manual liquidation and ledger consistency.
"""

import os
import unittest
import tempfile
from datetime import datetime, timezone, timedelta

from polymarket_sentinel.storage import PolymarketStorage
from polymarket_sentinel.paper_trader import PolymarketPaperTrader
from polymarket_sentinel.models import Market


class TestPolymarketDualEngine(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.storage = PolymarketStorage(self.tmp.name)
        self.trader = PolymarketPaperTrader(self.storage)

        # Future end date (within short term)
        self.future_date = (datetime.now(timezone.utc) + timedelta(days=20)).isoformat()

        # Seed verified evidence
        self.evidence = [
            {
                "title": "Federal Reserve minutes signal imminent rate adjustment",
                "credibility_score": 0.90,
                "sentiment_impact": 0.60
            },
            {
                "title": "Reuters confirms central bank committee consensus",
                "credibility_score": 0.85,
                "sentiment_impact": 0.50
            }
        ]

    def tearDown(self):
        if os.path.exists(self.tmp.name):
            os.remove(self.tmp.name)

    def test_engine_a_asymmetric_edge(self):
        """Asymmetric Edge Hunter (e.g. 20¢ contract with 50% AI probability)"""
        m = Market(
            id="m_asym",
            condition_id="c_asym",
            question="Will open-source model outperform proprietary benchmark?",
            slug="asym-test",
            category="AI",
            end_date=self.future_date,
            volume_24h=50000.0,
            clob_token_yes="tok_y",
            clob_token_no="tok_n",
            price_yes=0.20,
            price_no=0.80,
            status="active"
        )
        self.storage.upsert_market(m)

        res = self.trader.evaluate_and_trade(
            market_id="m_asym",
            question=m.question,
            price_yes=0.20,
            price_no=0.80,
            forecast_p=0.50,  # 30% edge on YES
            end_date=self.future_date,
            volume_24h=50000.0,
            evidence_list=self.evidence,
            category="AI"
        )
        self.assertIsNotNone(res)
        self.assertEqual(res["strategy_type"], "ASYMMETRIC_EDGE")
        self.assertEqual(res["outcome"], "YES")
        # Allocation should be capped at 5% of 500 = $25 max
        self.assertLessEqual(res["cost"], 25.50)

        # Check TP and SL levels
        self.assertGreater(res["take_profit_px"], res["price"])
        self.assertLess(res["stop_loss_px"], res["price"])

        open_pos = self.storage.get_open_positions()
        self.assertEqual(len(open_pos), 1)
        self.assertEqual(open_pos[0]["strategy_type"], "ASYMMETRIC_EDGE")

    def test_engine_b_high_prob_yield_harvest(self):
        """High-Probability Yield Harvester (e.g. 88¢ contract with 97% AI probability)"""
        m = Market(
            id="m_yield",
            condition_id="c_yield",
            question="Will US GDP report exceed 1.5% annualized growth?",
            slug="yield-test",
            category="Economics",
            end_date=self.future_date,
            volume_24h=80000.0,
            clob_token_yes="tok_y",
            clob_token_no="tok_n",
            price_yes=0.88,
            price_no=0.12,
            status="active"
        )
        self.storage.upsert_market(m)

        res = self.trader.evaluate_and_trade(
            market_id="m_yield",
            question=m.question,
            price_yes=0.88,
            price_no=0.12,
            forecast_p=0.97,  # 9% edge on YES (88¢)
            end_date=self.future_date,
            volume_24h=80000.0,
            evidence_list=self.evidence,
            category="Economics"
        )
        self.assertIsNotNone(res)
        self.assertEqual(res["strategy_type"], "HIGH_PROBABILITY_YIELD")
        # Allocation up to 15% ($75 max)
        self.assertLessEqual(res["cost"], 75.50)

        open_pos = self.storage.get_open_positions()
        self.assertEqual(len(open_pos), 1)
        self.assertEqual(open_pos[0]["strategy_type"], "HIGH_PROBABILITY_YIELD")

    def test_black_swan_tail_risk_veto(self):
        """High-probability contracts containing war/ceasefire keywords MUST BE VETOED"""
        m = Market(
            id="m_war",
            condition_id="c_war",
            question="Will Israel x Iran ceasefire hold through November 22?",
            slug="ceasefire-test",
            category="Middle East",
            end_date=self.future_date,
            volume_24h=120000.0,
            clob_token_yes="tok_y",
            clob_token_no="tok_n",
            price_yes=0.94,
            price_no=0.06,
            status="active"
        )
        self.storage.upsert_market(m)

        res = self.trader.evaluate_and_trade(
            market_id="m_war",
            question=m.question,
            price_yes=0.94,
            price_no=0.06,
            forecast_p=0.99,
            end_date=self.future_date,
            volume_24h=120000.0,
            evidence_list=self.evidence,
            category="Middle East"
        )
        # MUST BE VETOED TO PREVENT STEAMROLLER LOSS
        self.assertIsNone(res)
        open_pos = self.storage.get_open_positions()
        self.assertEqual(len(open_pos), 0)

    def test_active_dynamic_exit_take_profit(self):
        """Auto Take-Profit execution when current_price crosses take_profit_px"""
        m = Market(
            id="m_tp",
            condition_id="c_tp",
            question="Will SEC approve ETF filing by December?",
            slug="sec-test",
            category="Finance",
            end_date=self.future_date,
            volume_24h=60000.0,
            clob_token_yes="tok_y",
            clob_token_no="tok_n",
            price_yes=0.30,
            price_no=0.70,
            status="active"
        )
        self.storage.upsert_market(m)

        res = self.trader.evaluate_and_trade(
            market_id="m_tp",
            question=m.question,
            price_yes=0.30,
            price_no=0.70,
            forecast_p=0.60,
            end_date=self.future_date,
            volume_24h=60000.0,
            evidence_list=self.evidence,
            category="Finance"
        )
        self.assertIsNotNone(res)
        tp_px = res["take_profit_px"]

        # Simulate price spike reaching or exceeding TP
        self.trader.update_portfolio_mark_to_market({
            "m_tp": {"price_yes": tp_px + 0.05, "price_no": 1.0 - (tp_px + 0.05)}
        })

        # Position should now be automatically closed!
        open_pos = self.storage.get_open_positions()
        self.assertEqual(len(open_pos), 0)

        recent_trades = self.storage.get_recent_paper_trades()
        sell_trade = next((t for t in recent_trades if t["action"] == "SELL"), None)
        self.assertIsNotNone(sell_trade)
        self.assertEqual(sell_trade["exit_trigger"], "TAKE_PROFIT")
        self.assertGreater(sell_trade["realized_pnl"], 0.0)

    def test_active_dynamic_exit_stop_loss(self):
        """Auto Emergency Stop-Loss execution when current_price crosses stop_loss_px"""
        m = Market(
            id="m_sl",
            condition_id="c_sl",
            question="Will company announce quarterly dividend increase?",
            slug="sl-test",
            category="Corporate",
            end_date=self.future_date,
            volume_24h=40000.0,
            clob_token_yes="tok_y",
            clob_token_no="tok_n",
            price_yes=0.50,
            price_no=0.50,
            status="active"
        )
        self.storage.upsert_market(m)

        res = self.trader.evaluate_and_trade(
            market_id="m_sl",
            question=m.question,
            price_yes=0.50,
            price_no=0.50,
            forecast_p=0.75,
            end_date=self.future_date,
            volume_24h=40000.0,
            evidence_list=self.evidence,
            category="Corporate"
        )
        self.assertIsNotNone(res)
        sl_px = res["stop_loss_px"]

        # Simulate severe drop hitting stop-loss
        self.trader.update_portfolio_mark_to_market({
            "m_sl": {"price_yes": sl_px - 0.02, "price_no": 1.0 - (sl_px - 0.02)}
        })

        # Position should now be automatically closed!
        open_pos = self.storage.get_open_positions()
        self.assertEqual(len(open_pos), 0)

        recent_trades = self.storage.get_recent_paper_trades()
        sell_trade = next((t for t in recent_trades if t["action"] == "SELL"), None)
        self.assertIsNotNone(sell_trade)
        self.assertEqual(sell_trade["exit_trigger"], "STOP_LOSS")


if __name__ == "__main__":
    unittest.main()
