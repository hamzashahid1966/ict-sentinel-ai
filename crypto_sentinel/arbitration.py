"""
Crypto Sentinel AI - Signal Arbitration & Market Regime Engine
Resolves conflicting signals between Engine A (ICT Mean Reversion),
Engine B (Momentum Breakout), and Engine C (Liquidation Reversal).
"""

from typing import List, Optional
from crypto_sentinel.models import AnalysisOpportunity

class SignalArbitrationEngine:
    def __init__(self):
        pass

    def classify_regime(self, change_24h: float, volatility_pct: float) -> str:
        """
        Classifies current regime based on momentum and volatility:
        - TRENDING_BULLISH
        - TRENDING_BEARISH
        - HIGH_VOLATILITY_SQUEEZE
        - RANGING_CHOP
        """
        if volatility_pct > 7.0:
            return "HIGH_VOLATILITY_SQUEEZE"
        elif change_24h > 3.0:
            return "TRENDING_BULLISH"
        elif change_24h < -3.0:
            return "TRENDING_BEARISH"
        else:
            return "RANGING_CHOP"

    def arbitrate(self, opportunities: List[AnalysisOpportunity], regime: str) -> Optional[AnalysisOpportunity]:
        """
        Selects the single best opportunity, suppressing conflicting signals:
        1. In strong trends, Engine B (Momentum) takes precedence over counter-trend reversals.
        2. In High Volatility Squeezes, Engine C (Liquidation Sweep) takes top priority.
        3. In Ranging Chop, Engine A (ICT 50% CE) takes precedence.
        """
        if not opportunities:
            return None

        # Sort by confidence
        sorted_opps = sorted(opportunities, key=lambda o: o.confidence_score, reverse=True)

        if regime == "HIGH_VOLATILITY_SQUEEZE":
            # Prefer Engine C if present
            for o in sorted_opps:
                if o.engine == "C_LIQUIDATION_SWEEP":
                    return o

        elif "TRENDING" in regime:
            # Prefer Engine B if direction matches trend
            for o in sorted_opps:
                if o.engine == "B_MOMENTUM_IMP":
                    return o

        elif regime == "RANGING_CHOP":
            # Prefer Engine A
            for o in sorted_opps:
                if o.engine == "A_ICT_LIQUIDITY":
                    return o

        # Default fallback to highest confidence
        return sorted_opps[0]
