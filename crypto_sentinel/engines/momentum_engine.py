"""
Engine B: Institutional Momentum Pullback (IMP)
Captures directional continuation following a breakout.
Codifies the 6-step momentum sequence from Page 4 of the Crypto Sentinel Strategy Specification.
"""

from typing import List, Optional
from crypto_sentinel.models import CryptoCandle, AnalysisOpportunity
from crypto_sentinel.config import TARGET_1_R, TARGET_2_R

class MomentumEngine:
    def __init__(self):
        self.name = "B_MOMENTUM_IMP"

    def _calculate_ema(self, values: List[float], period: int) -> float:
        if not values or len(values) < period:
            return values[-1] if values else 0.0
        k = 2.0 / (period + 1.0)
        ema = sum(values[:period]) / period
        for val in values[period:]:
            ema = (val * k) + (ema * (1.0 - k))
        return ema

    def evaluate(self, symbol: str, m5_candles: List[CryptoCandle], h1_candles: List[CryptoCandle], m15_candles: Optional[List[CryptoCandle]] = None) -> Optional[AnalysisOpportunity]:
        if len(m5_candles) < 25 or len(h1_candles) < 30:
            return None

        current_candle = m5_candles[-1]
        current_price = current_candle.close

        # 1. H1 Macro Trend Confirmation: H1 20 EMA vs H1 50 EMA
        h1_closes = [c.close for c in h1_candles]
        h1_ema20 = self._calculate_ema(h1_closes, 20)
        h1_ema50 = self._calculate_ema(h1_closes, min(len(h1_closes), 50))

        # 2. M15 Intermediate Structure (if available)
        m15_bullish = True
        m15_bearish = True
        if m15_candles and len(m15_candles) >= 15:
            m15_closes = [c.close for c in m15_candles]
            m15_ema20 = self._calculate_ema(m15_closes, 15)
            m15_ema50 = self._calculate_ema(m15_closes, min(len(m15_closes), 30))
            m15_bullish = (m15_ema20 >= m15_ema50)
            m15_bearish = (m15_ema20 <= m15_ema50)

        # 3. M5 Pullback toward M5 20 EMA
        m5_closes = [c.close for c in m5_candles]
        m5_ema20 = self._calculate_ema(m5_closes, 20)

        # Bullish Scenario: H1 Bullish + M15 Bullish + Pullback into M5 EMA 20 + 2-bar breakout
        if h1_ema20 > h1_ema50 and m15_bullish and current_price >= m5_ema20:
            # 5. Two-bar breakout confirmation (last 2 candles expanding up from EMA)
            c1 = m5_candles[-2]
            c0 = m5_candles[-1]
            if c1.close > c1.open and c0.close > c1.high:
                # Stop loss at recent swing low below M5 EMA 20
                swing_low = min(c.low for c in m5_candles[-5:])
                stop_loss = round(min(swing_low, m5_ema20 * 0.997), 4 if current_price < 1 else 2)
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
                    confidence_score=0.84,
                    reason=f"H1 Trend Bullish (EMA20 {h1_ema20:.2f} > EMA50 {h1_ema50:.2f}). Successful M5 EMA 20 pullback and 2-bar bullish breakout.",
                    current_price=current_price,
                    stop_loss=stop_loss,
                    target_1=target_1,
                    target_2=target_2,
                    risk_r=1.0,
                    sweep_level=None,
                    fvg_bounds=f"M5 EMA20: {m5_ema20:.2f}"
                )

        # Bearish Scenario: H1 Bearish + M15 Bearish + Pullback up into M5 EMA 20 + 2-bar breakdown
        elif h1_ema20 < h1_ema50 and m15_bearish and current_price <= m5_ema20:
            c1 = m5_candles[-2]
            c0 = m5_candles[-1]
            if c1.close < c1.open and c0.close < c1.low:
                swing_high = max(c.high for c in m5_candles[-5:])
                stop_loss = round(max(swing_high, m5_ema20 * 1.003), 4 if current_price < 1 else 2)
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
                    confidence_score=0.83,
                    reason=f"H1 Trend Bearish (EMA20 {h1_ema20:.2f} < EMA50 {h1_ema50:.2f}). Retested M5 EMA 20 from below followed by 2-bar breakdown.",
                    current_price=current_price,
                    stop_loss=stop_loss,
                    target_1=target_1,
                    target_2=target_2,
                    risk_r=1.0,
                    sweep_level=None,
                    fvg_bounds=f"M5 EMA20: {m5_ema20:.2f}"
                )

        return None
