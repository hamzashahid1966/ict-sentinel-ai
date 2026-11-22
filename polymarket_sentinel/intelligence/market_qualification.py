"""
Polymarket Sentinel: Market Qualification Engine.
Evaluates discovered prediction contracts before spending AI inference resources.
Scores markets from 0 to 100 to filter out noise, illiquid bets, and ambiguous contracts.
"""

import re
from typing import Dict, Any, Tuple
from datetime import datetime, timezone


class MarketQualificationEngine:
    """
    Evaluates discovered contracts using multi-factor criteria:
    - Evidence Availability (25%)
    - Resolution Clarity (20%)
    - Base Rate Availability (15%)
    - Event Predictability (15%)
    - Order Book Liquidity (10%)
    - Time Horizon Suitability (10%)
    - Verification Cost / Resource Requirement (5%)
    """

    OFFICIAL_ORACLES = {
        "federal reserve", "fed", "bls", "bea", "bureau of labor statistics",
        "sec", "edgar", "nasdaq", "nyse", "bloomberg", "reuters", "associated press",
        "official", "supreme court", "white house", "cbo"
    }

    HIGH_PREDICTABILITY_CATEGORIES = {
        "economy", "macroeconomics", "tech & ai", "corporate", "business", "finance"
    }

    LOW_PREDICTABILITY_PATTERNS = [
        r"tweet", r"say.*word", r"celebrity", r"dating", r"rumor", r"meme",
        r"follower.*count", r"outfit", r"alien", r"ufo"
    ]

    @classmethod
    def qualify_market(cls, market: Dict[str, Any]) -> Tuple[float, str, Dict[str, float]]:
        question = (market.get("question") or "").lower()
        category = (market.get("category") or "").lower()
        res_source = (market.get("resolution_source") or "").lower()
        vol = float(market.get("volume_24h") or 0.0)
        end_date_str = market.get("end_date")

        # 1. Evidence Availability Score (0 to 25)
        evidence_score = 12.0
        if any(corp in question for corp in ["nvidia", "anthropic", "apple", "google", "microsoft", "openai", "tesla"]):
            evidence_score += 7.0
        if any(macro in question for macro in ["fed", "rate", "cpi", "gdp", "inflation", "unemployment"]):
            evidence_score += 8.0
        evidence_score = min(25.0, evidence_score)

        # 2. Resolution Clarity Score (0 to 20)
        clarity_score = 10.0
        if any(oracle in res_source for oracle in cls.OFFICIAL_ORACLES):
            clarity_score += 7.0
        if any(term in question for term in ["before", "by", "reach", "exceed", "decrease", "increase"]):
            clarity_score += 3.0
        clarity_score = min(20.0, clarity_score)

        # 3. Base Rate Availability Score (0 to 15)
        base_rate_score = 7.0
        if category in cls.HIGH_PREDICTABILITY_CATEGORIES or "fed" in question or "ipo" in question:
            base_rate_score += 8.0
        base_rate_score = min(15.0, base_rate_score)

        # 4. Predictability Score (0 to 15)
        predictability_score = 10.0
        if any(re.search(pat, question) for pat in cls.LOW_PREDICTABILITY_PATTERNS):
            predictability_score = 2.0
        elif "ipo" in question or "fed" in question or "market cap" in question:
            predictability_score += 5.0
        predictability_score = min(15.0, predictability_score)

        # 5. Liquidity Score (0 to 10)
        if vol >= 1_000_000:
            liquidity_score = 10.0
        elif vol >= 250_000:
            liquidity_score = 8.5
        elif vol >= 50_000:
            liquidity_score = 7.0
        elif vol >= 10_000:
            liquidity_score = 5.0
        else:
            liquidity_score = 2.0

        # 6. Time Horizon Score (0 to 10)
        horizon_score = 7.0
        if end_date_str:
            try:
                # Clean ISO string
                clean_iso = end_date_str.replace("Z", "+00:00")
                end_dt = datetime.fromisoformat(clean_iso)
                days_left = (end_dt - datetime.now(timezone.utc)).total_seconds() / 86400.0
                if 7 <= days_left <= 90:
                    horizon_score = 10.0  # Optimal research window
                elif 2 <= days_left < 7 or 90 < days_left <= 180:
                    horizon_score = 6.0
                elif days_left < 2:
                    horizon_score = 3.0   # Too close to resolution
                else:
                    horizon_score = 4.0   # Over 180 days (capital lockup)
            except Exception:
                horizon_score = 6.0

        # 7. Resource Requirement (0 to 5)
        resource_score = 4.5

        total_score = round(
            evidence_score + clarity_score + base_rate_score +
            predictability_score + liquidity_score + horizon_score + resource_score,
            1
        )

        # Qualification Tier
        if total_score >= 75.0:
            tier = "DEEP_RESEARCH"
        elif total_score >= 55.0:
            tier = "MONITOR"
        else:
            tier = "SKIP"

        breakdown = {
            "evidence": evidence_score,
            "clarity": clarity_score,
            "base_rate": base_rate_score,
            "predictability": predictability_score,
            "liquidity": liquidity_score,
            "horizon": horizon_score,
            "resource": resource_score
        }

        return total_score, tier, breakdown
