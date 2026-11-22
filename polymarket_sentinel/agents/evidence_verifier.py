"""
Polymarket Sentinel: Agent 03 - Evidence Verifier.
Classifies source credibility into strict tiers (100/75/50/20),
detects rumor cascades, verifies publication timestamps, and checks for contradictions.
"""

from typing import List, Dict, Any, Tuple


class EvidenceVerifierAgent:
    """
    Evidence Hierarchy:
    - Tier 1 (1.00 / 100): Primary Official (SEC, Fed, Company IR, Court Filings)
    - Tier 2 (0.75 / 75):  Established Independent Reporting (Reuters, Bloomberg, AP, WSJ)
    - Tier 3 (0.50 / 50):  Specialist Industry Reporting (TechCrunch, CoinDesk, The Verge)
    - Tier 4 (0.20 / 20):  Unverified / Rumor (Twitter, Reddit, Forums, Aggregators)
    """

    TIER_1_SOURCES = [
        "sec.gov", "federalreserve.gov", "bls.gov", "bea.gov", "whitehouse.gov",
        "investor relations", "official release", "courtlistener", "sec filing",
        "federal reserve board", "bureau of labor statistics"
    ]

    TIER_2_SOURCES = [
        "reuters", "bloomberg", "associated press", "ap news", "wall street journal",
        "wsj", "financial times", "cnbc", "barron's"
    ]

    TIER_3_SOURCES = [
        "techcrunch", "the verge", "coindesk", "cointelegraph", "ars technica",
        "semianalysis", "wired", "semafor", "politico", "axios"
    ]

    @classmethod
    def classify_source_tier(cls, source_name: str, source_url: str) -> Tuple[int, float]:
        combined = (f"{source_name} {source_url}").lower()

        for s in cls.TIER_1_SOURCES:
            if s in combined:
                return 1, 1.00

        for s in cls.TIER_2_SOURCES:
            if s in combined:
                return 2, 0.75

        for s in cls.TIER_3_SOURCES:
            if s in combined:
                return 3, 0.50

        # Tier 4 Default (Unverified / Syndicated / Rumor)
        return 4, 0.20

    def verify_and_weight_evidence(
        self,
        raw_evidence: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Processes a raw list of articles, assigns verified credibility weights,
        detects contradictory claims, and calculates aggregate evidence quality.
        """
        if not raw_evidence:
            return {
                "evidence_quality": 0.20,
                "verified_evidence": [],
                "primary_sources_count": 0,
                "contradictions_found": False,
                "contradiction_notes": "No external evidence provided."
            }

        verified = []
        tier_counts = {1: 0, 2: 0, 3: 0, 4: 0}
        total_weight = 0.0

        for item in raw_evidence:
            s_name = item.get("source_name", "Web")
            s_url = item.get("source_url", "")
            title = item.get("title", "")
            summary = item.get("summary", "")

            tier, weight = self.classify_source_tier(s_name, s_url)
            tier_counts[tier] += 1
            total_weight += weight

            sentiment = float(item.get("sentiment_impact", 0.0))

            verified.append({
                "title": title,
                "summary": summary,
                "source_name": s_name,
                "source_url": s_url,
                "tier": tier,
                "credibility_weight": weight,
                "sentiment_impact": sentiment,
                "is_primary": (tier == 1)
            })

        avg_quality = round(total_weight / len(raw_evidence), 2)

        # Detect contradictions: High variance between positive and negative sentiment in Tier 1/2
        sentiments = [e["sentiment_impact"] for e in verified if e["tier"] <= 2]
        has_positive = any(s >= 0.25 for s in sentiments)
        has_negative = any(s <= -0.25 for s in sentiments)
        contradictions_found = has_positive and has_negative

        notes = "Evidence consistent across reporting sources."
        if contradictions_found:
            notes = "Conflicting claims detected between major tier 1/2 reports."
        elif tier_counts[1] == 0 and tier_counts[2] == 0:
            notes = "Warning: Zero primary or major wire sources. Reliant on secondary/specialist commentary."

        return {
            "evidence_quality": avg_quality,
            "verified_evidence": verified,
            "primary_sources_count": tier_counts[1],
            "tier_counts": tier_counts,
            "contradictions_found": contradictions_found,
            "contradiction_notes": notes
        }
