"""
Polymarket Sentinel: Agent 01 - Resolution Analyst.
Analyzes contractual resolution conditions, UMA oracle rules, ambiguity traps,
and formalizes exact criteria for YES vs NO determination.
"""

import json
from typing import Dict, Any, Optional


class ResolutionAnalystAgent:
    def __init__(self, ai_gateway=None):
        self.ai_gateway = ai_gateway

    def analyze_resolution_criteria(
        self,
        question: str,
        category: str,
        resolution_source: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Produces a structured contract specification defining unambiguous resolution conditions.
        """
        # Deterministic rule parsing
        q_low = question.lower()
        res_src = resolution_source or "Polymarket UMA Oracle"

        yes_condition = "Event occurs and is verified by designated primary oracle before expiration."
        no_condition = "Event does not occur or is not verified before expiration deadline."
        ambiguity_risk = "LOW"
        effective_vs_announced = "Effective completion required"
        dispute_traps = []

        if "ipo" in q_low:
            yes_condition = "Company S-1 prospectus takes effect AND shares actively trade on a recognized exchange (e.g. NASDAQ/NYSE) at or before specified cutoff."
            no_condition = "Company remains private, merely files confidentially, or delays debut past the deadline date."
            effective_vs_announced = "Effective public trading required (formal pricing/listing, not merely press leak)"
            dispute_traps.append("Direct listing vs traditional IPO distinction under UMA rules.")
            dispute_traps.append("Confidential draft registration does not count as completed IPO.")

        elif "fed" in q_low or "interest rate" in q_low:
            yes_condition = "Federal Open Market Committee (FOMC) official post-meeting statement announces target federal funds rate adjustment meeting the exact basis-point threshold."
            no_condition = "FOMC leaves target range unchanged or adjustment does not meet specified basis-point cutoff."
            res_src = "Federal Reserve Board Official Release"
            effective_vs_announced = "Official post-meeting press release statement"
            dispute_traps.append("Inter-meeting emergency rate actions vs scheduled meeting resolutions.")

        elif "reach" in q_low or "market cap" in q_low:
            yes_condition = "Official intraday or market-close market capitalization reaches or exceeds specified dollar threshold as reported by designated financial benchmarks."
            no_condition = "Market cap fails to touch or close at designated threshold prior to final trading session."
            effective_vs_announced = "Verified official exchange closing quote / market cap data"
            dispute_traps.append("Intraday touch vs official 4:00 PM EST market close price.")

        elif "resign" in q_low or "step down" in q_low or "leave" in q_low:
            yes_condition = "Executive formally vacates the office or official corporate 8-K filing confirms departure."
            no_condition = "Executive remains in post, transitions to Executive Chair without resigning, or announcement sets future departure date beyond contract window."
            ambiguity_risk = "MEDIUM"
            dispute_traps.append("Transition to Executive Chairman vs complete resignation.")

        # If AI gateway is active, enrich with LLM analysis
        if self.ai_gateway:
            prompt = f"""You are a Market Resolution Analyst specializing in prediction market contracts and UMA oracle disputes.

CONTRACT QUESTION: "{question}"
CATEGORY: {category}
DESIGNATED SOURCE: {res_src}
END DATE: {end_date or 'Not specified'}

Analyze the resolution rules:
1. Exact YES trigger:
2. Exact NO trigger:
3. Does an announcement suffice or is effective execution required?
4. Identify any semantic edge cases or potential UMA dispute traps.

Output valid JSON matching:
{{
  "yes_condition": "string",
  "no_condition": "string",
  "effective_vs_announced": "string",
  "authoritative_source": "string",
  "ambiguity_risk": "LOW" | "MEDIUM" | "HIGH",
  "dispute_traps": ["string"]
}}
"""
            res = self.ai_gateway._call_ollama(prompt) or self.ai_gateway._call_openrouter(prompt)
            if res and isinstance(res, dict) and "reasoning" in res:
                try:
                    parsed = json.loads(res["reasoning"])
                    return {
                        "question": question,
                        "yes_condition": parsed.get("yes_condition", yes_condition),
                        "no_condition": parsed.get("no_condition", no_condition),
                        "effective_vs_announced": parsed.get("effective_vs_announced", effective_vs_announced),
                        "authoritative_source": parsed.get("authoritative_source", res_src),
                        "ambiguity_risk": parsed.get("ambiguity_risk", ambiguity_risk),
                        "dispute_traps": parsed.get("dispute_traps", dispute_traps)
                    }
                except Exception:
                    pass

        return {
            "question": question,
            "yes_condition": yes_condition,
            "no_condition": no_condition,
            "effective_vs_announced": effective_vs_announced,
            "authoritative_source": res_src,
            "ambiguity_risk": ambiguity_risk,
            "dispute_traps": dispute_traps
        }
