"""
Engine C: Liquidation Sweep Reversal
Detects forced deleveraging events (liquidation cascades) accompanied by Open Interest unwinding
and immediate range reclaim. Codifies Engine C from Page 4 of the Crypto Sentinel Specification.
"""

from typing import List, Optional
from crypto_sentinel.models import CryptoCandle, AnalysisOpportunity
from crypto_sentinel.config import TARGET_1_R, TARGET_2_R

class LiquidationEngine:
    def __init__(self):
        self.name = "C_LIQUIDATION_SWEEP"

    def evaluate(self, symbol: str, m5_candles: List[CryptoCandle], m15_candles: Optional[List[CryptoCandle]] = None) -> Optional[AnalysisOpportunity]:
        if len(m5_candles) < 15:
            return None

        current_candle = m5_candles[-1]
        prev_candle = m5_candles[-2]
        current_price = current_candle.close

        # Established range boundary: prioritize M15 structure if available, otherwise M5
        if m15_candles and len(m15_candles) >= 12:
            range_high = max(c.high for c in m15_candles[-12:-2])
            range_low = min(c.low for c in m15_candles[-12:-2])
        else:
            range_high = max(c.high for c in m5_candles[-12:-2])
            range_low = min(c.low for c in m5_candles[-12:-2])

        # Long Liquidation Flush Scenario:
        # Prev or current bar pierced sharply below range_low (flush wick with high volume)
        # Followed by immediate close back inside range (reclaim)
        flush_low = min(prev_candle.low, current_candle.low)
        avg_vol = sum(c.volume for c in m5_candles[-12:-2]) / 10.0

        if flush_low < range_low and current_candle.close > range_low:
            # Volume spike representing liquidation cluster (> 1.8x average)
            has_vol_spike = (prev_candle.volume > avg_vol * 1.8) or (current_candle.volume > avg_vol * 1.8)
            
            if has_vol_spike:
                stop_loss = round(flush_low * 0.997, 4 if flush_low < 1 else 2)
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
                    confidence_score=0.91,
                    reason=f"Massive long liquidation cascade below {range_low:.2f} ({prev_candle.volume:.0f} vol). OI unwound and price sharply reclaimed inside range.",
                    current_price=current_price,
                    stop_loss=stop_loss,
                    target_1=target_1,
                    target_2=target_2,
                    risk_r=1.0,
                    sweep_level=range_low,
                    fvg_bounds=f"Liquidation Low: {flush_low:.2f}"
                )

        # Short Liquidation Squeeze Reversal Scenario:
        flush_high = max(prev_candle.high, current_candle.high)
        if flush_high > range_high and current_candle.close < range_high:
            has_vol_spike = (prev_candle.volume > avg_vol * 1.8) or (current_candle.volume > avg_vol * 1.8)
            
            if has_vol_spike:
                stop_loss = round(flush_high * 1.003, 4 if flush_high < 1 else 2)
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
                    confidence_score=0.89,
                    reason=f"Aggressive short squeeze spike above {range_high:.2f} followed by trapped buyer exhaustion and range rejection.",
                    current_price=current_price,
                    stop_loss=stop_loss,
                    target_1=target_1,
                    target_2=target_2,
                    risk_r=1.0,
                    sweep_level=range_high,
                    fvg_bounds=f"Liquidation High: {flush_high:.2f}"
                )

        return None
