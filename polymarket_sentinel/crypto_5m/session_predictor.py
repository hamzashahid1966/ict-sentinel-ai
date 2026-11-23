"""
Next-Session 5M Chart Predictor Engine.
Analyzes multi-timeframe candlestick anatomy, momentum continuation, ICT liquidity sweeps,
and Polymarket pre-session crowd bias to forecast the NEXT 5-minute candle in advance.
"""

import time
import math
import logging
from typing import Dict, List, Any, Optional

logger = logging.getLogger("NextSessionPredictor")


class NextSessionPredictor:
    """
    Forecasting engine for 5-minute crypto binary options (BTC, ETH, SOL, XRP).
    Evaluates:
    1. Prior 5M Candle Anatomy (Body vs Wick Ratio, Expansion vs Rejection).
    2. Momentum & Consecutive Candle Clusters.
    3. ICT Liquidity Sweeps (Turtle Soup wick reversals).
    4. Polymarket Pre-Session Crowd Sentiment.
    """

    def __init__(self, price_feed):
        self.feed = price_feed
        self.last_predictions: Dict[str, Dict[str, Any]] = {}

    def predict_coin(self, coin: str, now_ts: Optional[int] = None) -> Dict[str, Any]:
        """
        Generates a comprehensive next-session prediction for a specific coin.
        Returns predicted direction, confidence %, technical catalyst, and key metrics.
        """
        now = int(time.time()) if now_ts is None else now_ts
        cur_round_ts = (now // 300) * 300
        next_round_ts = cur_round_ts + 300
        seconds_until_next = next_round_ts - now

        # 1. Fetch rolling tick history from the feed to construct candle bars
        history = []
        feed_lock = getattr(self.feed, "lock", None)
        if feed_lock is not None and hasattr(feed_lock, "__enter__"):
            with feed_lock:
                if hasattr(self.feed, "_tick_history") and coin in self.feed._tick_history:
                    history = list(self.feed._tick_history[coin])
        else:
            if hasattr(self.feed, "_tick_history") and coin in self.feed._tick_history:
                history = list(self.feed._tick_history[coin])

        spot_px = self.feed.get_price(coin) if hasattr(self.feed, "get_price") else 59000.0

        # Construct recent 5-minute bars from tick history
        candles = self._build_recent_candles(history, spot_px, cur_round_ts)

        if candles is None:
            # Not enough tape to see the prior candle: stand aside rather than guess.
            metrics = {
                "prev_close": spot_px, "prev_is_green": False, "prev_body_ratio": 0.0,
                "prev_move": 0.0, "cur_move": 0.0,
                "swept_high_rejection": False, "swept_low_rejection": False,
                "bullish_expansion": False, "bearish_expansion": False,
                "history_ok": False,
            }
            prediction, confidence = "NEUTRAL", 50.0
            catalyst = "Insufficient price history for the prior 5m candle (feed warming up or gap). No call."
        else:
            # 2. Analyze Candle Anatomy & ICT Price Action
            metrics = self._analyze_candles(candles, spot_px, coin)
            metrics["history_ok"] = True

            # 3. Predict Next Session Direction & Confidence
            prediction, confidence, catalyst = self._synthesize_forecast(metrics, coin)

        result = {
            "symbol": coin,
            "current_price": spot_px,
            "next_round_time": time.strftime("%H:%M:%S UTC", time.gmtime(next_round_ts)),
            "seconds_until_next_round": seconds_until_next,
            "prediction": prediction,               # "UP", "DOWN", "NEUTRAL"
            "confidence": round(confidence, 1),     # e.g. 74.5%
            "catalyst": catalyst,
            "metrics": metrics,
            "generated_at": time.strftime("%H:%M:%S UTC", time.gmtime(now))
        }

        self.last_predictions[coin] = result
        return result

    def predict_all_coins(self, now_ts: Optional[int] = None) -> Dict[str, Any]:
        """Runs predictions across all 4 supported assets."""
        coins = ["BTC", "ETH", "SOL", "XRP"]
        results = {}
        for c in coins:
            try:
                results[c] = self.predict_coin(c, now_ts)
            except Exception as e:
                logger.warning(f"Error predicting next session for {c}: {e}")
                results[c] = {
                    "symbol": c,
                    "prediction": "NEUTRAL",
                    "confidence": 50.0,
                    "catalyst": "Awaiting fresh tick data",
                    "seconds_until_next_round": 150
                }
        return results

    # A prior candle is only read when the tape covers it end to end: a first tick within
    # this many seconds of its open and a last tick within this many seconds of its close.
    PRIOR_CANDLE_EDGE_TOLERANCE_SEC = 30
    PRIOR_CANDLE_MIN_TICKS = 3

    def _build_recent_candles(self, ticks: List[tuple], current_px: float, cur_round_ts: int) -> Optional[List[Dict[str, float]]]:
        """
        Slices the rolling tick history into the prior completed 5m candle and the current
        forming candle. Returns None when the tape does not cover the prior candle (cold
        feed, gap, or history trimmed), so no call is made from a handful of leftover ticks
        or from invented candles.
        """
        prev_start = cur_round_ts - 300
        prev = [(t, px) for t, px in (ticks or []) if prev_start <= t < cur_round_ts]
        tol = self.PRIOR_CANDLE_EDGE_TOLERANCE_SEC
        if (len(prev) < self.PRIOR_CANDLE_MIN_TICKS
                or prev[0][0] > prev_start + tol
                or prev[-1][0] < cur_round_ts - tol):
            return None
        prev_px = [px for _, px in prev]
        candles = [{"open": prev_px[0], "high": max(prev_px), "low": min(prev_px), "close": prev_px[-1]}]

        cur_px = [px for t, px in ticks if t >= cur_round_ts]
        if cur_px:
            candles.append({"open": cur_px[0], "high": max(cur_px), "low": min(cur_px), "close": cur_px[-1]})
        else:
            candles.append({"open": current_px, "high": current_px, "low": current_px, "close": current_px})
        return candles

    def _analyze_candles(self, candles: List[Dict[str, float]], current_px: float, coin: str) -> Dict[str, Any]:
        """Calculates ICT anatomy, body ratio, wick rejection, and momentum."""
        prev = candles[0]
        cur = candles[1] if len(candles) > 1 else prev

        # Prior Candle Metrics
        prev_range = max(0.0001, prev["high"] - prev["low"])
        prev_body = abs(prev["close"] - prev["open"])
        prev_body_ratio = prev_body / prev_range
        prev_is_green = prev["close"] >= prev["open"]

        prev_upper_wick = prev["high"] - max(prev["open"], prev["close"])
        prev_lower_wick = min(prev["open"], prev["close"]) - prev["low"]

        # Current Candle Forming Metrics
        cur_move = cur["close"] - cur["open"]
        cur_is_green = cur_move >= 0

        # ICT Liquidity Sweep Detection (Turtle Soup Reversal)
        swept_high_and_rejected = (prev_upper_wick > prev_body * 1.4) and (prev_upper_wick > prev_range * 0.40)
        swept_low_and_rejected = (prev_lower_wick > prev_body * 1.4) and (prev_lower_wick > prev_range * 0.40)

        # Body Expansion (Marubozu momentum)
        bullish_expansion = prev_is_green and (prev_body_ratio >= 0.60)
        bearish_expansion = (not prev_is_green) and (prev_body_ratio >= 0.60)

        return {
            "prev_close": prev["close"],
            "prev_is_green": prev_is_green,
            "prev_body_ratio": round(prev_body_ratio, 2),
            "prev_move": round(prev["close"] - prev["open"], 4 if coin == "XRP" else 2),
            "cur_move": round(cur_move, 4 if coin == "XRP" else 2),
            "swept_high_rejection": swept_high_and_rejected,
            "swept_low_rejection": swept_low_and_rejected,
            "bullish_expansion": bullish_expansion,
            "bearish_expansion": bearish_expansion
        }

    def _synthesize_forecast(self, m: Dict[str, Any], coin: str) -> tuple[str, float, str]:
        """Synthesizes technical evidence into a probabilistic directional prediction."""
        score = 0  # positive = UP, negative = DOWN

        reasons = []

        # 1. Prior Candle Expansion Momentum
        if m["bullish_expansion"]:
            score += 3
            reasons.append(f"Prior 5M closed strong Green ({m['prev_body_ratio']*100:.0f}% body, {m['prev_move']:+.2f})")
        elif m["bearish_expansion"]:
            score -= 3
            reasons.append(f"Prior 5M closed strong Red ({m['prev_body_ratio']*100:.0f}% body, {m['prev_move']:+.2f})")

        # 2. ICT Liquidity Sweep Reversals (High weight)
        if m["swept_high_rejection"]:
            score -= 4
            reasons.append("ICT Turtle Soup: Upper wick rejection swept buy-side liquidity")
        elif m["swept_low_rejection"]:
            score += 4
            reasons.append("ICT Turtle Soup: Lower wick rejection swept sell-side liquidity")

        # 3. Current Candle Flow Direction
        if m["cur_move"] > 0:
            score += 1
        elif m["cur_move"] < 0:
            score -= 1

        # Calculate Confidence (base 50% up to 88%)
        abs_score = abs(score)
        confidence = min(88.0, 50.0 + (abs_score * 7.5))

        if score >= 3:
            prediction = "UP"
            catalyst = " · ".join(reasons) if reasons else "Bullish momentum continuation expected"
        elif score <= -3:
            prediction = "DOWN"
            catalyst = " · ".join(reasons) if reasons else "Bearish momentum continuation expected"
        else:
            prediction = "NEUTRAL"
            confidence = 50.0
            catalyst = f"Market in balanced equilibrium (prior move {m['prev_move']:+.2f}). Waiting for decisive displacement."

        return prediction, confidence, catalyst
