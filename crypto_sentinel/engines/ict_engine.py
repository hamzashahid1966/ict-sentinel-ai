"""
Engine A: ICT Liquidity Reversal
Detects price reversal following a sweep of reference highs/lows + MSS + FVG + 50% CE pullback.
Codifies the 6-step sequence from Page 3 of the Crypto Sentinel Strategy Specification.
"""

from typing import List, Optional
from crypto_sentinel.models import CryptoCandle, AnalysisOpportunity
from crypto_sentinel.config import TARGET_1_R, TARGET_2_R

class ICTLiquidityEngine:
    def __init__(self):
        self.name = "A_ICT_LIQUIDITY"

    def evaluate(self, symbol: str, m5_candles: List[CryptoCandle], h1_candles: List[CryptoCandle], m15_candles: Optional[List[CryptoCandle]] = None) -> Optional[AnalysisOpportunity]:
        if len(m5_candles) < 20 or len(h1_candles) < 10:
            return None

        current_candle = m5_candles[-1]
        current_price = current_candle.close

        # 1. Establish institutional reference range using M15 and H1 prior highs and lows
        ref_source = m15_candles[-16:-1] if (m15_candles and len(m15_candles) >= 16) else h1_candles[-10:-1]
        ref_high = max(c.high for c in ref_source)
        ref_low = min(c.low for c in ref_source)

        # Macro H1 trend filter
        h1_trend_bullish = h1_candles[-1].close >= h1_candles[-6].close

        # 2. Check for Bullish Setup: Sweep of Sell-Side Liquidity (SSL) below ref_low
        recent_lows = [c.low for c in m5_candles[-10:]]
        lowest_recent = min(recent_lows)
        
        # Did a wick pierce below reference low?
        if lowest_recent < ref_low:
            # 3. Market Structure Shift (MSS): Has a recent candle closed above the previous minor swing high?
            swing_high = max(c.high for c in m5_candles[-6:-2])
            last_three_bodies = [c.body_high for c in m5_candles[-3:]]
            has_mss = any(bh > swing_high for bh in last_three_bodies)

            # 4. Fair Value Gap (FVG) Detection: Candle[i-2].high < Candle[i].low (bullish gap)
            fvg_found = False
            fvg_top = 0.0
            fvg_bottom = 0.0
            fvg_ce = 0.0

            for i in range(len(m5_candles) - 4, len(m5_candles) - 1):
                c_prev = m5_candles[i - 1]
                c_disp = m5_candles[i]
                c_next = m5_candles[i + 1]

                if c_next.low > c_prev.high and c_disp.is_bullish:
                    fvg_found = True
                    fvg_top = c_next.low
                    fvg_bottom = c_prev.high
                    fvg_ce = (fvg_top + fvg_bottom) / 2.0  # 50% Consequent Encroachment
                    break

            # 5 & 6. Pullback into Discount / 50% CE
            if has_mss and fvg_found and current_price <= fvg_top:
                # Invalidation check: did a candle body close below CE in wrong direction?
                if current_candle.body_low < fvg_ce:
                    return None # Invalidated

                stop_loss = round(lowest_recent * 0.998, 4 if lowest_recent < 1 else 2)
                risk_pts = current_price - stop_loss
                if risk_pts <= 0:
                    return None

                target_1 = round(current_price + (risk_pts * TARGET_1_R), 4 if current_price < 1 else 2)
                target_2 = round(current_price + (risk_pts * TARGET_2_R), 4 if current_price < 1 else 2)

                return AnalysisOpportunity(
                    symbol=symbol,
                    engine=self.name,
                    direction="LONG",
                    status="OPPORTUNITY_CONFIRMED",
                    confidence_score=0.88,
                    reason=f"Swept Sell-Side Liquidity at {ref_low:.2f}, confirmed M5 MSS break with 3-bar FVG. Price retesting 50% CE discount.",
                    current_price=current_price,
                    stop_loss=stop_loss,
                    target_1=target_1,
                    target_2=target_2,
                    risk_r=1.0,
                    sweep_level=ref_low,
                    fvg_bounds=f"[{fvg_bottom:.2f} - {fvg_top:.2f}] (CE: {fvg_ce:.2f})"
                )

        # 2b. Check for Bearish Setup: Sweep of Buy-Side Liquidity (BSL) above ref_high
        recent_highs = [c.high for c in m5_candles[-10:]]
        highest_recent = max(recent_highs)

        if highest_recent > ref_high:
            swing_low = min(c.low for c in m5_candles[-6:-2])
            last_three_bodies = [c.body_low for c in m5_candles[-3:]]
            has_mss = any(bl < swing_low for bl in last_three_bodies)

            fvg_found = False
            fvg_top = 0.0
            fvg_bottom = 0.0
            fvg_ce = 0.0

            for i in range(len(m5_candles) - 4, len(m5_candles) - 1):
                c_prev = m5_candles[i - 1]
                c_disp = m5_candles[i]
                c_next = m5_candles[i + 1]

                if c_next.high < c_prev.low and not c_disp.is_bullish:
                    fvg_found = True
                    fvg_top = c_prev.low
                    fvg_bottom = c_next.high
                    fvg_ce = (fvg_top + fvg_bottom) / 2.0
                    break

            if has_mss and fvg_found and current_price >= fvg_bottom:
                if current_candle.body_high > fvg_ce:
                    return None

                stop_loss = round(highest_recent * 1.002, 4 if highest_recent < 1 else 2)
                risk_pts = stop_loss - current_price
                if risk_pts <= 0:
                    return None

                target_1 = round(current_price - (risk_pts * TARGET_1_R), 4 if current_price < 1 else 2)
                target_2 = round(current_price - (risk_pts * TARGET_2_R), 4 if current_price < 1 else 2)

                return AnalysisOpportunity(
                    symbol=symbol,
                    engine=self.name,
                    direction="SHORT",
                    status="OPPORTUNITY_CONFIRMED",
                    confidence_score=0.86,
                    reason=f"Swept Buy-Side Liquidity at {ref_high:.2f}, confirmed M5 MSS break with 3-bar FVG. Price retesting 50% CE premium.",
                    current_price=current_price,
                    stop_loss=stop_loss,
                    target_1=target_1,
                    target_2=target_2,
                    risk_r=1.0,
                    sweep_level=ref_high,
                    fvg_bounds=f"[{fvg_bottom:.2f} - {fvg_top:.2f}] (CE: {fvg_ce:.2f})"
                )

        return None
