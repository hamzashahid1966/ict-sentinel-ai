"""
Polymarket Sentinel: Agent 05 - Counterargument Agent (Devil's Advocate).
Actively challenges and attempts to disprove the independent forecast.
Identifies unpriced risks, unsupported assumptions, and has full authority to recommend ABSTAIN.
"""

import json
from typing import Dict, Any, List


class CounterargumentAgent:
    def __init__(self, ai_gateway=None):
        self.ai_gateway = ai_gateway

    def critique_forecast(
        self,
        question: str,
        independent_probability: float,
        base_rate: float,
        resolution_spec: Dict[str, Any],
        verified_evidence: List[Dict[str, Any]],
        evidence_quality: float
    ) -> Dict[str, Any]:
        """
        Adversarially attacks the independent forecast thesis.
        Evaluates whether the system should abstain completely.
        """
        critique_points = []
        recommend_abstain = False
        abstain_reason = None
        overconfidence_risk = "LOW"

        # 1. Check for extreme probability with weak evidence
        if (independent_probability > 0.80 or independent_probability < 0.20) and evidence_quality < 0.60:
            critique_points.append("Extreme probability assigned despite low evidence quality (< 0.60).")
            overconfidence_risk = "HIGH"

        # 2. Check for resolution ambiguity
        ambiguity = resolution_spec.get("ambiguity_risk", "LOW")
        if ambiguity in ("MEDIUM", "HIGH"):
            critique_points.append(f"Resolution ambiguity is {ambiguity}: {resolution_spec.get('effective_vs_announced')}.")
            if ambiguity == "HIGH":
                recommend_abstain = True
                abstain_reason = "High UMA contractual resolution ambiguity."

        # 3. Check for priced-in momentum / base rate deviation
        delta_from_base = abs(independent_probability - base_rate)
        if delta_from_base > 0.35:
            critique_points.append(
                f"Severe deviation ({delta_from_base*100:+.1f}%) from historical base rate ({base_rate*100:.1f}%) without primary Tier 1 confirmation."
            )

        # 4. Check for contradictory evidence
        tier_counts = {e.get("tier", 3) for e in verified_evidence}
        if 1 not in tier_counts and 2 not in tier_counts and verified_evidence:
            critique_points.append("Evidence relies entirely on secondary/specialist reporting; lacks primary source confirmation.")

        # Default critique if points empty
        if not critique_points:
            critique_points.append("Key risk: Macro headlines may already be fully absorbed into the current order book.")
            critique_points.append("Timing risk: Resolution criteria strictly requires verification before deadline date.")

        critique_text = " · ".join(critique_points)

        # Optional LLM deep critique
        if self.ai_gateway and independent_probability not in (base_rate, 0.5):
            prompt = f"""You are the Counterargument Devil's Advocate for a prediction market trading desk.
Your mandate is to challenge the following forecast thesis and look for reasons NOT to bet.

QUESTION: "{question}"
INDEPENDENT FORECAST: {independent_probability * 100:.1f}% (Base rate: {base_rate * 100:.1f}%)
RESOLUTION SPEC: {resolution_spec.get('yes_condition')}

Task:
1. What assumptions might be flawed?
2. What alternative scenario is being underestimated?
3. Should the trading desk ABSTAIN due to uncertainty or pricing efficiency?

Output JSON:
{{
  "critique": "2-3 sentences challenging the thesis",
  "recommend_abstain": true | false,
  "abstain_reason": "string or null"
}}
"""
            res = self.ai_gateway._call_ollama(prompt) or self.ai_gateway._call_openrouter(prompt)
            if res and isinstance(res, dict) and "reasoning" in res:
                try:
                    parsed = json.loads(res["reasoning"])
                    return {
                        "counterarguments": critique_points,
                        "overconfidence_risk": overconfidence_risk,
                        "recommend_abstain": bool(parsed.get("recommend_abstain", recommend_abstain)),
                        "abstain_reason": parsed.get("abstain_reason") or abstain_reason,
                        "critique": parsed.get("critique", critique_text)
                    }
                except Exception:
                    pass

        return {
            "counterarguments": critique_points,
            "overconfidence_risk": overconfidence_risk,
            "recommend_abstain": recommend_abstain,
            "abstain_reason": abstain_reason,
            "critique": critique_text
        }
