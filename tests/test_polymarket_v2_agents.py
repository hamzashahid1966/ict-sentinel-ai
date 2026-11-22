"""
Unit Tests for Polymarket Sentinel v2 Adversarial Multi-Agent Pipeline.
"""

import unittest
from polymarket_sentinel.intelligence.market_qualification import MarketQualificationEngine
from polymarket_sentinel.agents.resolution_analyst import ResolutionAnalystAgent
from polymarket_sentinel.agents.evidence_verifier import EvidenceVerifierAgent
from polymarket_sentinel.agents.independent_forecaster import IndependentForecasterAgent
from polymarket_sentinel.agents.counterargument import CounterargumentAgent
from polymarket_sentinel.agents.final_analyst import FinalForecastAnalystAgent


class TestPolymarketV2Agents(unittest.TestCase):

    def test_market_qualification_scoring(self):
        market = {
            "question": "Will the Fed decrease interest rates by 25 bps at next FOMC?",
            "category": "Economy",
            "resolution_source": "Federal Reserve Board Official Release",
            "volume_24h": 450000.0,
            "end_date": "2026-12-25T20:00:00Z"
        }
        score, tier, breakdown = MarketQualificationEngine.qualify_market(market)
        self.assertGreaterEqual(score, 65.0)
        self.assertIn(tier, ["DEEP_RESEARCH", "MONITOR"])
        self.assertIn("evidence", breakdown)
        self.assertIn("clarity", breakdown)

    def test_resolution_analyst_uma_rules(self):
        agent = ResolutionAnalystAgent()
        spec = agent.analyze_resolution_criteria(
            question="Will Anthropic IPO in 2026?",
            category="Tech & AI",
            resolution_source="SEC S-1 Prospectus"
        )
        self.assertIn("yes_condition", spec)
        self.assertIn("effective_vs_announced", spec)
        self.assertTrue(len(spec["dispute_traps"]) > 0)

    def test_evidence_verifier_source_tiers(self):
        agent = EvidenceVerifierAgent()
        raw = [
            {"source_name": "SEC.gov Filings", "source_url": "https://sec.gov/edgar", "title": "S-1 Notice", "summary": "Registered", "sentiment_impact": 0.4},
            {"source_name": "Reuters Wire", "source_url": "https://reuters.com", "title": "Debate Update", "summary": "Trading report", "sentiment_impact": 0.2},
            {"source_name": "Twitter Post", "source_url": "https://x.com/user", "title": "Rumor", "summary": "Unconfirmed post", "sentiment_impact": -0.8}
        ]
        dossier = agent.verify_and_weight_evidence(raw)
        self.assertIn("evidence_quality", dossier)
        self.assertEqual(dossier["tier_counts"][1], 1)  # SEC is Tier 1
        self.assertEqual(dossier["tier_counts"][2], 1)  # Reuters is Tier 2
        self.assertEqual(dossier["tier_counts"][4], 1)  # Twitter is Tier 4
        self.assertEqual(dossier["verified_evidence"][0]["credibility_weight"], 1.0)
        self.assertEqual(dossier["verified_evidence"][2]["credibility_weight"], 0.20)

    def test_blind_independent_forecaster(self):
        agent = IndependentForecasterAgent()
        res_spec = {"yes_condition": "Official Fed rate cut statement", "no_condition": "No rate cut"}
        evidence = [{"source_name": "BLS", "tier": 1, "credibility_weight": 1.0, "sentiment_impact": 0.5, "title": "CPI low", "summary": "Inflation cooled"}]
        facts = [{"entity_name": "Fed", "fact_key": "Precedent", "fact_value": "Cuts when CPI cools"}]

        # Agent 4 is called WITHOUT any market price argument
        forecast = agent.forecast_independently(
            question="Will Fed decrease interest rates by 25 bps?",
            category="Economy",
            resolution_spec=res_spec,
            verified_evidence=evidence,
            entity_facts=facts
        )
        self.assertIn("independent_probability", forecast)
        self.assertIn("base_rate", forecast)
        self.assertGreater(forecast["independent_probability"], 0.01)
        self.assertLess(forecast["independent_probability"], 0.99)

    def test_counterargument_devil_advocate(self):
        agent = CounterargumentAgent()
        res_spec = {"ambiguity_risk": "HIGH", "effective_vs_announced": "Effective completion required"}
        critique = agent.critique_forecast(
            question="Will obscure token reach $1B market cap?",
            independent_probability=0.88,
            base_rate=0.10,
            resolution_spec=res_spec,
            verified_evidence=[],
            evidence_quality=0.30
        )
        self.assertTrue(critique["recommend_abstain"])  # High ambiguity must trigger ABSTAIN
        self.assertEqual(critique["overconfidence_risk"], "HIGH")

    def test_final_synthesis_edge_calculation(self):
        agent = FinalForecastAnalystAgent()
        res_spec = {"yes_condition": "Fed cut", "no_condition": "No cut"}
        evidence_dossier = {"evidence_quality": 0.85}
        indep_forecast = {"base_rate": 0.35, "independent_probability": 0.65, "confidence_score": 0.80}
        counter_critique = {"recommend_abstain": False, "overconfidence_risk": "LOW", "critique": "Risks priced in", "counterarguments": []}

        # Current Polymarket price is 0.40 (40 cents)
        synthesis = agent.synthesize_final_assessment(
            question="Will Fed cut rates?",
            category="Economy",
            current_market_prob=0.40,
            resolution_spec=res_spec,
            evidence_dossier=evidence_dossier,
            independent_forecast=indep_forecast,
            counterargument_critique=counter_critique
        )
        self.assertGreaterEqual(synthesis["edge"], 0.15)
        self.assertEqual(synthesis["action"], "BUY YES")
        self.assertIn("uncertainty_range", synthesis)


if __name__ == "__main__":
    unittest.main()
