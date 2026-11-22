"""
Crypto Sentinel AI - Portfolio Risk Engine
Enforces 0.25% equity risk, Meme Coin Risk Collars, 1% daily drawdown lock,
maximum 2 concurrent positions, and BTC/ETH correlation protection.
"""

import time
from typing import Tuple, Optional, List
from crypto_sentinel.config import (
    DEFAULT_RISK_PER_TRADE_PCT, MEME_RISK_PER_TRADE_PCT,
    MAX_DAILY_DRAWDOWN_PCT, MAX_CONCURRENT_POSITIONS, STRATEGY_PROFILES,
    BTC_REGIME_FILTER_ENABLED, FAST_SCALPER_MAX_DOLLAR_RISK,
    TRADE_ENTRY_PACING_SECONDS, MIN_CONVICTION_SCORE, MIN_TARGET_MOVE_PCT
)
from crypto_sentinel.models import CryptoAccount, CryptoPosition, AnalysisOpportunity

class CryptoRiskEngine:
    def __init__(self):
        pass

    def approve_trade(
        self,
        account: CryptoAccount,
        opportunity: AnalysisOpportunity,
        open_positions: List[CryptoPosition],
        sector: str = "MAJOR",
        btc_trend: Optional[str] = None,
        last_trade_time: Optional[float] = None,
        is_quarantined: bool = False,
        quarantine_reason: str = ""
    ) -> Tuple[bool, float, str]:
        """
        Validates risk parameters according to the selected strategy profile.
        Returns: (is_approved: bool, position_quantity: float, reason: str)
        """
        profile_key = getattr(account, "strategy_profile", "MODERATE_GROWTH") or "MODERATE_GROWTH"
        profile = STRATEGY_PROFILES.get(profile_key, STRATEGY_PROFILES["MODERATE_GROWTH"])
        max_dd = profile.get("max_daily_drawdown_pct", MAX_DAILY_DRAWDOWN_PCT)

        # 0. AI Behavioral Auto-Quarantine Circuit Breaker
        if is_quarantined:
            return False, 0.0, f"REJECTED: Auto-Quarantine active on {opportunity.symbol}. {quarantine_reason or 'Benched for 24h to protect capital.'}"

        # 1. Daily Drawdown Lock Check
        if account.is_locked or account.daily_drawdown_pct >= max_dd:
            return False, 0.0, f"REJECTED: Daily drawdown limit reached ({account.daily_drawdown_pct:.2f}% >= {max_dd}%). Trading locked."

        # 2. Concurrent Positions Check
        if len(open_positions) >= MAX_CONCURRENT_POSITIONS:
            return False, 0.0, f"REJECTED: Max concurrent positions ({MAX_CONCURRENT_POSITIONS}) already reached."

        # 3. Duplicate Symbol Check
        for p in open_positions:
            if p.symbol == opportunity.symbol:
                return False, 0.0, f"REJECTED: Active position already exists on {opportunity.symbol}."

        # 4. Entry Pacing Cooldown (Stagger entries to prevent simultaneous correlation dumps)
        now_ts = time.time()
        if last_trade_time and last_trade_time > 0:
            elapsed = now_ts - last_trade_time
            if elapsed < TRADE_ENTRY_PACING_SECONDS:
                rem_sec = int(TRADE_ENTRY_PACING_SECONDS - elapsed)
                return False, 0.0, f"REJECTED: Entry pacing cooldown active ({rem_sec}s remaining). Staggering entries to prevent correlation dump."

        # 5. Minimum Conviction Threshold
        if getattr(opportunity, "confidence_score", 0.0) < MIN_CONVICTION_SCORE:
            return False, 0.0, f"REJECTED: Conviction score ({opportunity.confidence_score*100:.0f}%) below minimum required threshold ({MIN_CONVICTION_SCORE*100:.0f}%)."

        # 6. Correlation Protection (BTC and ETH cannot be stacked in the same direction)
        if opportunity.symbol in ("BTCUSDT", "ETHUSDT"):
            other_sym = "ETHUSDT" if opportunity.symbol == "BTCUSDT" else "BTCUSDT"
            for p in open_positions:
                if p.symbol == other_sym and p.direction == opportunity.direction:
                    return False, 0.0, f"REJECTED: Correlation safeguard active. Cannot stack {opportunity.direction} on both BTC and ETH simultaneously."

        # 7. BTC Macro Trend Shield
        if BTC_REGIME_FILTER_ENABLED and btc_trend and btc_trend != "NEUTRAL":
            if opportunity.symbol != "BTCUSDT":
                if opportunity.direction == "LONG" and btc_trend == "BEARISH":
                    return False, 0.0, f"REJECTED: BTC Market Shield active. Cannot open LONG on {opportunity.symbol} while BTC is dumping (M5 Bearish)."
                elif opportunity.direction == "SHORT" and btc_trend == "BULLISH":
                    return False, 0.0, f"REJECTED: BTC Market Shield active. Cannot open SHORT on {opportunity.symbol} while BTC is pumping (M5 Bullish)."

        # 8. Minimum Target Spread Filter (Protects against fee erosion on ultra-micro wicks)
        target_dist_pct = abs(opportunity.target_1 - opportunity.current_price) / opportunity.current_price if opportunity.current_price > 0 else 0.0
        if target_dist_pct < MIN_TARGET_MOVE_PCT:
            return False, 0.0, f"REJECTED: Target 1 move too small ({target_dist_pct*100:.2f}% < {MIN_TARGET_MOVE_PCT*100:.2f}%). Filtered to guarantee fee-positive profit."

        # 9. Position Sizing
        base_risk = profile.get("risk_per_trade_pct", DEFAULT_RISK_PER_TRADE_PCT)
        meme_risk = profile.get("meme_risk_pct", MEME_RISK_PER_TRADE_PCT)
        risk_pct = meme_risk if sector == "MEME" else base_risk
        risk_dollars = account.balance * (risk_pct / 100.0)

        # Enforce strict Dollar Risk Cap so single stop loss never wipes out multiple scalps
        max_cap = profile.get("max_dollar_risk", FAST_SCALPER_MAX_DOLLAR_RISK if profile_key == "FAST_SCALPER" else None)
        if max_cap and risk_dollars > max_cap:
            risk_dollars = max_cap

        stop_dist = abs(opportunity.current_price - opportunity.stop_loss)
        if stop_dist <= 0:
            return False, 0.0, "REJECTED: Invalid stop distance."

        # Quantity = Risk $ / Stop distance
        qty = risk_dollars / stop_dist
        
        # Round quantity safely
        if opportunity.current_price > 1000:
            qty = round(qty, 4)
        elif opportunity.current_price > 10:
            qty = round(qty, 2)
        elif opportunity.current_price > 1:
            qty = round(qty, 1)
        else:
            qty = round(qty, 0)

        if qty <= 0:
            qty = 0.001 if opportunity.current_price > 1000 else 1.0

        notional = qty * opportunity.current_price
        reason = f"APPROVED: Risk ${risk_dollars:.2f} (Capped at ${max_cap or risk_dollars:.2f}) | Notional: ${notional:.2f} | Size: {qty} {opportunity.symbol}"
        return True, qty, reason
