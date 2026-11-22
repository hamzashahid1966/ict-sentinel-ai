"""
Polymarket Sentinel: Agent 06 - Final Forecast Analyst.
Receives independent forecast, counterarguments, resolution spec, and only NOW examines the market price.
Produces final synthesized calibrated probability, uncertainty intervals, and actionable edge.
"""

from typing import Dict, Any, Optional


class FinalForecastAnalystAgent:
    def __init__(self, ai_gateway=None):
        self.ai_gateway = ai_gateway

    def synthesize_final_assessment(
        self,
        question: str,
        category: str,
        current_market_prob: float,
        resolution_spec: Dict[str, Any],
        evidence_dossier: Dict[str, Any],
        independent_forecast: Dict[str, Any],
        counterargument_critique: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Synthesizes the complete adversarial intelligence dossier and compares against live market price.
        """
        base_rate = independent_forecast.get("base_rate", 0.30)
        p_indep = independent_forecast.get("independent_probability", 0.50)
        conf = independent_forecast.get("confidence_score", 0.75)
        ev_quality = evidence_dossier.get("evidence_quality", 0.50)

        recommend_abstain = counterargument_critique.get("recommend_abstain", False)
        abstain_reason = counterargument_critique.get("abstain_reason")

        # Pull back slightly toward base rate if counterargument identified high overconfidence
        overconf = counterargument_critique.get("overconfidence_risk", "LOW")
        dampener = 0.85 if overconf == "HIGH" else 0.95

        # Bayesian synthesis: weight between independent forecast and base rate
        final_p = round(base_rate * (1 - dampener) + p_indep * dampener, 3)

        # Calculate uncertainty range based on evidence quality
        spread = round((1.0 - ev_quality) * 0.15 + (1.0 - conf) * 0.10, 3)
        p_low = round(max(0.01, final_p - spread), 3)
        p_high = round(min(0.99, final_p + spread), 3)

        # Statistical Edge against current Polymarket price
        edge = round(final_p - current_market_prob, 3)

        # Determine actionable stance
        if recommend_abstain:
            action = "ABSTAIN"
            status_desc = f"Abstain: {abstain_reason or 'Risk/Ambiguity high'}"
        elif edge >= 0.06 and p_low >= (current_market_prob - 0.02):
            action = "BUY YES"
            status_desc = f"High-conviction Mispricing: Model {final_p*100:.1f}% vs Market {current_market_prob*100:.1f}% (+{edge*100:.1f}% Edge)"
        elif edge <= -0.06 and p_high <= (current_market_prob + 0.02):
            action = "BUY NO"
            status_desc = f"Overpriced Contract: Model {final_p*100:.1f}% vs Market {current_market_prob*100:.1f}% ({edge*100:.1f}% Edge)"
        else:
            action = "HOLD / PASS"
            status_desc = f"Fair Value / Insufficient Edge: Discrepancy ({edge*100:+.1f}%) inside uncertainty band [{p_low*100:.0f}%–{p_high*100:.0f}%]"

        synthesis_markdown = (
            f"**Superforecasting Synthesis ({category})**\n\n"
            f"- **Base Rate Prior:** {base_rate*100:.1f}%\n"
            f"- **Independent Blind Forecast:** {p_indep*100:.1f}% (Confidence: {conf*100:.0f}%)\n"
            f"- **Counterargument Critique:** {counterargument_critique.get('critique')}\n"
            f"- **Final Calibrated Probability:** **{final_p*100:.1f}%** (Uncertainty Range: {p_low*100:.0f}% – {p_high*100:.0f}%)\n"
            f"- **Polymarket Live Price:** {current_market_prob*100:.1f}%\n"
            f"- **Net Edge:** **{edge*100:+.1f}%** | **Recommended Stance:** `{action}`"
        )

        return {
            "base_rate": base_rate,
            "independent_probability": p_indep,
            "final_probability": final_p,
            "uncertainty_range": [p_low, p_high],
            "evidence_quality": ev_quality,
            "edge": edge,
            "action": action,
            "status_desc": status_desc,
            "recommend_abstain": recommend_abstain,
            "abstain_reason": abstain_reason,
            "counterarguments": counterargument_critique.get("counterarguments", []),
            "synthesis_markdown": synthesis_markdown
        }
