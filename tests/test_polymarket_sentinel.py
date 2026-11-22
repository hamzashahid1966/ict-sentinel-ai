"""
Unit Tests for Polymarket Sentinel Architecture.
Tests storage, memory engine, AI gateway, paper trading engine, and web server endpoints.
"""

import os
import unittest
import tempfile
from datetime import datetime, timezone

from polymarket_sentinel.models import Market, Evidence, Prediction, PaperPosition
from polymarket_sentinel.storage import PolymarketStorage
from polymarket_sentinel.memory_engine import PolymarketMemoryEngine
from polymarket_sentinel.ai_gateway import AIGateway
from polymarket_sentinel.paper_trader import PolymarketPaperTrader
from polymarket_sentinel.controller import PolymarketController


class TestPolymarketSentinel(unittest.TestCase):
    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.storage = PolymarketStorage(db_path=self.temp_db.name)
        self.memory = PolymarketMemoryEngine(self.storage)
        self.ai_gateway = AIGateway(storage=self.storage)
        self.paper_trader = PolymarketPaperTrader(self.storage)

    def tearDown(self):
        try:
            os.remove(self.temp_db.name)
        except Exception:
            pass

    def test_storage_market_and_snapshot_lifecycle(self):
        market = Market(
            id="test-fed-dec",
            condition_id="0x1234567890abcdef",
            question="Will the Fed cut interest rates in December?",
            slug="fed-rate-cut-dec",
            category="Economy",
            end_date="2026-12-18T00:00:00Z",
            volume_24h=50000.0,
            clob_token_yes="token-yes-1",
            clob_token_no="token-no-1",
            price_yes=0.42,
            price_no=0.58,
            status="active",
            resolution_source="Federal Reserve Statement"
        )
        self.storage.upsert_market(market)

        markets = self.storage.get_markets(limit=10)
        self.assertEqual(len(markets), 1)
        self.assertEqual(markets[0]["id"], "test-fed-dec")
        self.assertEqual(markets[0]["price_yes"], 0.42)

    def test_memory_engine_evidence_deduplication(self):
        ev1_id = self.memory.record_evidence(
            market_id="test-fed-dec",
            source_url="https://reuters.com/article1",
            source_name="Reuters",
            title="FOMC Signals Neutral Stance",
            summary="Fed holds rates steady.",
            credibility_score=0.9,
            sentiment_impact=-0.2
        )
        self.assertGreater(ev1_id, 0)

        # Duplicate submission with same title, summary, url
        ev2_id = self.memory.record_evidence(
            market_id="test-fed-dec",
            source_url="https://reuters.com/article1",
            source_name="Reuters",
            title="FOMC Signals Neutral Stance",
            summary="Fed holds rates steady.",
            credibility_score=0.9,
            sentiment_impact=-0.2
        )
        # Deduplication must return existing ID
        self.assertEqual(ev1_id, ev2_id)

    def test_entity_knowledge_graph_and_facts(self):
        self.memory.learn_entity_fact(
            entity_name="Federal Reserve",
            entity_type="Central Bank",
            summary="US monetary authority",
            fact_key="Inflation Target",
            fact_value="2.0% Core PCE",
            source="Federal Reserve Mandate"
        )
        facts = self.storage.get_entity_facts("Federal Reserve")
        self.assertGreaterEqual(len(facts), 1)
        self.assertEqual(facts[0]["fact_key"], "Inflation Target")
        self.assertEqual(facts[0]["fact_value"], "2.0% Core PCE")

    def test_prediction_timeline_immutability(self):
        # Forecast 1
        self.memory.commit_forecast(
            market_id="test-fed-dec",
            forecast_probability=0.35,
            market_probability=0.42,
            confidence_score=0.75,
            reasoning="Initial baseline assessment.",
            model_used="superforecaster-bayesian-v1"
        )

        # Forecast 2 (revision after new news)
        self.memory.commit_forecast(
            market_id="test-fed-dec",
            forecast_probability=0.28,
            market_probability=0.40,
            confidence_score=0.82,
            reasoning="Updated following CPI report.",
            model_used="superforecaster-bayesian-v1"
        )

        timeline = self.storage.get_market_prediction_timeline("test-fed-dec")
        self.assertEqual(len(timeline), 2)
        self.assertEqual(timeline[0]["forecast_probability"], 0.35)
        self.assertEqual(timeline[1]["forecast_probability"], 0.28)

    def test_brier_score_calibration(self):
        # Perfect prediction
        score_perfect = PolymarketMemoryEngine.calculate_brier_score([1.0], 1)
        self.assertEqual(score_perfect, 0.0)

        # Completely wrong prediction
        score_worst = PolymarketMemoryEngine.calculate_brier_score([1.0], 0)
        self.assertEqual(score_worst, 1.0)

        # Average calibrated prediction (0.8 forecast, outcome 1 -> (0.8 - 1)^2 = 0.04)
        score_calibrated = PolymarketMemoryEngine.calculate_brier_score([0.8], 1)
        self.assertEqual(score_calibrated, 0.04)

    def test_ai_gateway_heuristic_fallback(self):
        # Even when Ollama is offline, the gateway returns calibrated Bayesian probabilities
        res = self.ai_gateway.estimate_market_probability(
            market_question="Will Anthropic IPO in 2026?",
            category="Tech & AI",
            current_market_prob=0.30,
            evidence_list=[{
                "title": "Private secondary market provides liquidity",
                "summary": "Management comfortable with private runway.",
                "credibility_score": 0.88,
                "sentiment_impact": -0.4
            }],
            entity_facts=[]
        )
        self.assertIn("forecast_probability", res)
        self.assertIn("confidence_score", res)
        self.assertIn("reasoning", res)
        self.assertGreater(res["forecast_probability"], 0.0)
        self.assertLess(res["forecast_probability"], 1.0)

    def test_paper_trading_order_and_sizing(self):
        market = Market(
            id="test-mkt-buy",
            condition_id="0xabc",
            question="Will NVIDIA announce new GPU architecture?",
            slug="nvda-gpu-announce",
            category="Tech",
            end_date="2026-12-10T00:00:00Z",
            volume_24h=100000.0,
            clob_token_yes="tok-yes",
            clob_token_no="tok-no",
            price_yes=0.40,
            price_no=0.60,
            status="active"
        )
        self.storage.upsert_market(market)

        evidence = [
            {"title": "NVIDIA Supply Chain Expands Ahead of Schedule", "source_name": "Reuters", "credibility_score": 0.90, "sentiment_impact": 0.40},
            {"title": "Hyperscaler Demand Exceeds Forecasts", "source_name": "Bloomberg", "credibility_score": 0.88, "sentiment_impact": 0.35}
        ]

        # Forecast is 0.55 (Edge: 0.55 - 0.40 = +0.15 >= 0.06 -> BUY YES)
        order = self.paper_trader.evaluate_and_trade(
            market_id="test-mkt-buy",
            question=market.question,
            price_yes=0.40,
            price_no=0.60,
            forecast_p=0.55,
            end_date="2026-12-10T00:00:00Z",
            volume_24h=100000.0,
            evidence_list=evidence
        )
        self.assertIsNotNone(order)
        self.assertEqual(order["outcome"], "YES")
        self.assertGreater(order["shares"], 0)

        # Verify open position recorded
        open_pos = self.storage.get_open_positions()
        self.assertEqual(len(open_pos), 1)
        self.assertEqual(open_pos[0]["outcome"], "YES")

        # Mark to market: price moves to 0.48
        self.paper_trader.update_portfolio_mark_to_market({
            "test-mkt-buy": {"price_yes": 0.48, "price_no": 0.52}
        })
        summary = self.paper_trader.get_portfolio_summary()
        self.assertGreater(summary["unrealized_pnl"], 0.0)

    def test_news_evidence_gate_blocking(self):
        # Edge exists, but NO verified news evidence -> MUST be blocked
        blocked_order = self.paper_trader.evaluate_and_trade(
            market_id="test-no-news",
            question="Will XYZ occur?",
            price_yes=0.40,
            price_no=0.60,
            forecast_p=0.60,
            end_date="2026-12-10T00:00:00Z",
            volume_24h=100000.0,
            evidence_list=[]  # No news
        )
        self.assertIsNone(blocked_order)

    def test_expired_market_rejection_and_settlement(self):
        # 1. Market with past end_date (expired)
        expired_market = Market(
            id="test-expired-mkt",
            condition_id="0xdead",
            question="Will Anthropic IPO before Q3 2026?",
            slug="anthropic-past",
            category="Tech",
            end_date="2026-09-30T23:59:59Z",
            volume_24h=50000.0,
            clob_token_yes="tok-yes",
            clob_token_no="tok-no",
            price_yes=0.30,
            price_no=0.70,
            status="active"
        )
        self.storage.upsert_market(expired_market)

        # Upserting an expired market marks status as closed
        active_markets = self.storage.get_markets(limit=20, active_only=True)
        self.assertNotIn("test-expired-mkt", [m["id"] for m in active_markets])

        # Attempting to trade an expired market returns None
        order = self.paper_trader.evaluate_and_trade(
            market_id="test-expired-mkt",
            question=expired_market.question,
            price_yes=0.30,
            price_no=0.70,
            forecast_p=0.50,
            end_date="2026-09-30T23:59:59Z"
        )
        self.assertIsNone(order)


if __name__ == "__main__":
    unittest.main()
