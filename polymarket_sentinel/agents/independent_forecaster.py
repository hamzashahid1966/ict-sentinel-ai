"""
Polymarket Sentinel: Agent 04 - Blind Independent Forecaster.
Produces unanchored probability forecasts WITHOUT seeing current Polymarket market prices.
Evaluates historical base rates, evidence weights, and structural conditions.
"""

import json
from typing import Dict, Any, List, Optional


class IndependentForecasterAgent:
    def __init__(self, ai_gateway=None):
        self.ai_gateway = ai_gateway

    def forecast_independently(
        self,
        question: str,
        category: str,
        resolution_spec: Dict[str, Any],
        verified_evidence: List[Dict[str, Any]],
        entity_facts: List[Dict[str, Any]],
        end_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        CRITICAL ARCHITECTURAL GUARANTEE:
        This agent is intentionally blind to the current Polymarket trading price.
        """
        # 1. Calculate historical category base rate
        base_rate = self._estimate_historical_base_rate(question, category)

        # 2. Build verified evidence text block
        evidence_lines = []
        for e in verified_evidence[:6]:
            tier_lbl = f"Tier {e.get('tier', 3)} (Weight: {e.get('credibility_weight', 0.5):.2f})"
            evidence_lines.append(f"- [{e.get('source_name')}] ({tier_lbl}): {e.get('title')} — {e.get('summary')}")
        evidence_text = "\n".join(evidence_lines) if evidence_lines else "No recent external evidence."

        facts_lines = [f"- {f.get('entity_name')}: {f.get('fact_key')} = {f.get('fact_value')}" for f in entity_facts[:5]]
        facts_text = "\n".join(facts_lines) if facts_lines else "No prior entity knowledge."

        prompt = f"""You are an Independent Superforecaster operating with BLIND EVALUATION.
You DO NOT know the market trading price. You must compute the true fundamental probability based strictly on base rates, required causal steps, and verified evidence.

CONTRACT QUESTION: "{question}"
CATEGORY: {category}
RESOLUTION CONDITIONS:
- YES Trigger: {resolution_spec.get('yes_condition')}
- NO Trigger: {resolution_spec.get('no_condition')}
- Standard: {resolution_spec.get('effective_vs_announced')}

HISTORICAL BASE RATE: {base_rate * 100:.1f}%

PRIOR ENTITY KNOWLEDGE:
{facts_text}

VERIFIED EVIDENCE DOSSIER (TIERED BY RELIABILITY):
{evidence_text}

TASK:
1. Start from the historical base rate ({base_rate * 100:.1f}%).
2. Perform Bayesian updating based ONLY on Tier 1 and Tier 2 verified evidence.
3. Determine an unanchored probability for YES between 0.01 and 0.99.
4. Provide structured reasoning.

Output strictly valid JSON:
{{
  "independent_probability": 0.45,
  "confidence_score": 0.80,
  "thesis": "Concise justification explaining how evidence shifted probability from the historical base rate."
}}
"""
        # Try LLM via AI Gateway
        if self.ai_gateway:
            res = self.ai_gateway._call_ollama(prompt) or self.ai_gateway._call_openrouter(prompt)
            if res and isinstance(res, dict) and "reasoning" in res:
                try:
                    parsed = json.loads(res["reasoning"])
                    p = float(parsed.get("independent_probability", base_rate))
                    c = float(parsed.get("confidence_score", 0.75))
                    thesis = parsed.get("thesis", "Synthesized via blind independent LLM inference.")
                    return {
                        "base_rate": base_rate,
                        "independent_probability": max(0.01, min(0.99, p)),
                        "confidence_score": max(0.1, min(1.0, c)),
                        "thesis": thesis,
                        "method": "LLM_INDEPENDENT_BLIND"
                    }
                except Exception:
                    pass

        # Deterministic Bayesian Heuristic Forecaster
        return self._heuristic_blind_forecast(base_rate, verified_evidence, question)

    @staticmethod
    def _estimate_historical_base_rate(question: str, category: str) -> float:
        """Returns empirical historical base rates for recurring event classes."""
        q_low = question.lower()
        if "interest rate" in q_low or "fed" in q_low:
            if "50+ bps" in q_low:
                return 0.08  # Jumbo cuts are historically rare
            elif "25 bps" in q_low or "decrease" in q_low:
                return 0.38  # Standard cycle frequency
            return 0.35
        elif "ipo" in q_low:
            return 0.22  # High historical postponement frequency
        elif "reach" in q_low or "trillion" in q_low:
            return 0.45  # Large cap momentum base rate
        elif "resign" in q_low or "step down" in q_low:
            return 0.12  # Unscheduled CEO departure baseline
        elif "recession" in q_low:
            return 0.15  # US quarterly contraction baseline
        return 0.30

    def _heuristic_blind_forecast(
        self,
        base_rate: float,
        evidence: List[Dict[str, Any]],
        question: str
    ) -> Dict[str, Any]:
        """Calculates evidence-weighted bayesian update from historical prior."""
        total_delta = 0.0
        citations = []

        for e in evidence:
            weight = e.get("credibility_weight", 0.5)
            impact = e.get("sentiment_impact", 0.0)
            # Tier 1/2 heavily weighted; Tier 4 has negligible impact
            total_delta += (impact * weight * 0.12)
            citations.append(f"{e.get('source_name')} ({impact:+.2f})")

        updated_p = round(max(0.02, min(0.98, base_rate + total_delta)), 3)
        cites_summary = ", ".join(citations[:3]) if citations else "Base rate prior"

        thesis = (
            f"Blind Bayesian Assessment: Prior base rate established at {base_rate * 100:.1f}%. "
            f"Updated by {len(evidence)} verified evidence sources ({cites_summary}). "
            f"Net independent forecast: {updated_p * 100:.1f}%."
        )

        return {
            "base_rate": base_rate,
            "independent_probability": updated_p,
            "confidence_score": 0.82 if evidence else 0.65,
            "thesis": thesis,
            "method": "HEURISTIC_INDEPENDENT_BLIND"
        }
