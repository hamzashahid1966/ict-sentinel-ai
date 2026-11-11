"""
ICT Sentinel AI - IPDA Algorithmic Brain
Codifies the full 52-Lecture algorithmic logic into a deterministic rule engine.
"""

import datetime
from dataclasses import dataclass
from typing import List, Optional, Tuple, Dict, Any
from .config import ASSET_SPECS, SESSION_WINDOWS
from .models import Candle, PDArray

@dataclass
class AlgorithmicSignal:
    asset: str
    session: str
    direction: str          # 'LONG' or 'SHORT'
    entry_price: float
    stop_loss: float
    risk_pts: float
    target_center_mass: float
    target_head_shot: float
    pd_array: PDArray
    ai_rationale: str

class IPDAEngine:
    def __init__(self):
        pass

    @staticmethod
    def is_nfp_week(d: datetime.date) -> bool:
        first_day = datetime.date(d.year, d.month, 1)
        days_to_friday = (4 - first_day.weekday()) % 7
        first_friday = first_day + datetime.timedelta(days=days_to_friday)
        first_monday = first_friday - datetime.timedelta(days=4)
        return first_monday <= d <= first_friday

    @staticmethod
    def get_current_session(time_et: datetime.time) -> Optional[str]:
        for sname, win in SESSION_WINDOWS.items():
            if win['exec_start'] <= time_et <= win['exec_end']:
                return sname
        return None

    @staticmethod
    def check_10am_gate(candles_today: List[Candle]) -> bool:
        """
        Lecture 51 Gate:
        If 09:30 AM open is contained inside the 09:00 - 09:30 AM candle range,
        quarantine entries until 10:00:00 AM EST.
        Returns True if gate is active (must wait until 10:00 AM).
        """
        c_0900 = [c for c in candles_today if datetime.time(9, 0) <= c.timestamp_et.time() < datetime.time(9, 30)]
        c_0930 = [c for c in candles_today if c.timestamp_et.time() == datetime.time(9, 30)]

        if c_0900 and c_0930:
            h_0900 = max(c.high for c in c_0900)
            l_0900 = min(c.low for c in c_0900)
            o_0930 = c_0930[0].open
            if l_0900 < o_0930 < h_0900:
                return True # Trapped inside 09:00 range! Gate active!
        return False

    def evaluate_market(self, asset: str, candles: List[Candle], memory_engine: Optional[Any] = None) -> Optional[AlgorithmicSignal]:
        if len(candles) < 20:
            return None

        spec = ASSET_SPECS[asset]
        current_candle = candles[-1]
        now_et = current_candle.timestamp_et
        today_date = now_et.date()
        time_et = now_et.time()
        day_name = now_et.strftime('%A')

        # 1. Calendar Filter: NFP Week Quarantine (Lecture 51)
        if self.is_nfp_week(today_date) and day_name in ['Thursday', 'Friday']:
            return None # Stand down: Pre-NFP Seek & Destroy profile!

        # 2. Session Window Check
        session_name = self.get_current_session(time_et)
        if not session_name:
            return None

        win = SESSION_WINDOWS[session_name]

        # 3. Apply 10:00 AM Gate Filter for NY Session (Lecture 51)
        if session_name == 'NEW_YORK_AM' and time_et < datetime.time(10, 0):
            today_bars = [c for c in candles if c.timestamp_et.date() == today_date]
            if self.check_10am_gate(today_bars):
                return None # 10:00 AM Gate active! Avoid 09:30-10:00 morning traps.

        # 4. Extract Reference Range Bars
        today_bars = [c for c in candles if c.timestamp_et.date() == today_date]
        if win['ref_start'] < win['ref_end']:
            ref_bars = [c for c in today_bars if win['ref_start'] <= c.timestamp_et.time() < win['ref_end']]
        else:
            # Over midnight reference range
            ref_bars = [c for c in candles if (c.timestamp_et.time() >= win['ref_start']) or (c.timestamp_et.time() < win['ref_end'])]

        if len(ref_bars) < 6:
            return None

        ref_high = max(c.high for c in ref_bars)
        ref_low = min(c.low for c in ref_bars)
        ref_range = ref_high - ref_low
        if ref_range < spec['min_pre_range']:
            return None

        # 5. Check last 3 completed bars: b0, b1, b2
        b0 = candles[-3]
        b1 = candles[-2]
        b2 = candles[-1]

        # Sweep of session liquidity
        swept_high = b0.high > ref_high and b0.close < ref_high
        swept_low = b0.low < ref_low and b0.close > ref_low

        # ---------------- BEARISH SIGNAL (SHORT) ----------------
        if swept_high:
            # Bearish SIBI: b0.low > b2.high
            if b0.low > b2.high:
                fvg_high = b0.low
                fvg_low = b2.high
                fvg_ce = fvg_low + 0.5 * (fvg_high - fvg_low)

                # Rule A: Consequent Encroachment (50%) Respect (Lectures 35, 41, 51)
                # Candle bodies MUST NOT close above C.E.
                if b1.close > fvg_ce or b2.close > fvg_ce:
                    return None

                # Rule B: Candle Body MSS Validation (Lecture 48, 51)
                # Disqualifies wick sweeps! The body must close below b0.low
                if b1.body_bottom > b0.low and b2.body_bottom > b0.low:
                    return None

                # Rule C: Upper Quadrant / Premium Filter (Lecture 48)
                range_eq = ref_low + 0.50 * ref_range
                if fvg_low < range_eq:
                    return None # Shorting in discount is strictly forbidden!

                entry_price = fvg_low
                sl = ref_high + (2 * spec['tick_size'])
                risk = sl - entry_price

                if spec['min_risk_pts'] <= risk <= spec['max_risk_pts']:
                    # Self-Learning Memory Engine Gating
                    if memory_engine:
                        approved, confidence, reason = memory_engine.evaluate_setup_viability(asset, session_name, 'SIBI')
                        if not approved:
                            return None # Gated by learned history / circuit breaker!
                    else:
                        confidence = 0.85
                        reason = "Default clearance"

                    target_cm = entry_price - (risk * 1.5)
                    target_hs = entry_price - (risk * 3.0)
                    pd_array = PDArray(
                        array_type='SIBI',
                        high=fvg_high,
                        low=fvg_low,
                        consequent_encroachment=fvg_ce,
                        formation_time=b2.timestamp_et
                    )
                    rationale = (
                        f"[Adaptive Confidence: {confidence*100:.1f}%] "
                        f"Bearish SIBI confirmed following BSL sweep above {ref_high:.2f}. "
                        f"Candle bodies respected 50% CE ({fvg_ce:.2f}). "
                        f"Body MSS closure confirmed. Premium quadrant satisfied. {reason}"
                    )
                    return AlgorithmicSignal(
                        asset=asset, session=session_name, direction='SHORT',
                        entry_price=entry_price, stop_loss=sl, risk_pts=risk,
                        target_center_mass=target_cm, target_head_shot=target_hs,
                        pd_array=pd_array, ai_rationale=rationale
                    )

        # ---------------- BULLISH SIGNAL (LONG) ----------------
        elif swept_low:
            # Bullish BISI: b2.low > b0.high
            if b2.low > b0.high:
                fvg_low = b0.high
                fvg_high = b2.low
                fvg_ce = fvg_low + 0.5 * (fvg_high - fvg_low)

                # Rule A: Consequent Encroachment (50%) Respect
                if b1.close < fvg_ce or b2.close < fvg_ce:
                    return None

                # Rule B: Candle Body MSS Validation
                if b1.body_top < b0.high and b2.body_top < b0.high:
                    return None

                # Rule C: Lowest Quadrant / Discount Filter (Lecture 48)
                range_eq = ref_low + 0.50 * ref_range
                if fvg_high > range_eq:
                    return None # Buying in premium is strictly forbidden!

                entry_price = fvg_high
                sl = ref_low - (2 * spec['tick_size'])
                risk = entry_price - sl

                if spec['min_risk_pts'] <= risk <= spec['max_risk_pts']:
                    # Self-Learning Memory Engine Gating
                    if memory_engine:
                        approved, confidence, reason = memory_engine.evaluate_setup_viability(asset, session_name, 'BISI')
                        if not approved:
                            return None # Gated by learned history / circuit breaker!
                    else:
                        confidence = 0.85
                        reason = "Default clearance"

                    target_cm = entry_price + (risk * 1.5)
                    target_hs = entry_price + (risk * 3.0)
                    pd_array = PDArray(
                        array_type='BISI',
                        high=fvg_high,
                        low=fvg_low,
                        consequent_encroachment=fvg_ce,
                        formation_time=b2.timestamp_et
                    )
                    rationale = (
                        f"[Adaptive Confidence: {confidence*100:.1f}%] "
                        f"Bullish BISI confirmed following SSL sweep below {ref_low:.2f}. "
                        f"Candle bodies respected 50% CE ({fvg_ce:.2f}). "
                        f"Body MSS closure confirmed. Lowest discount quadrant satisfied. {reason}"
                    )
                    return AlgorithmicSignal(
                        asset=asset, session=session_name, direction='LONG',
                        entry_price=entry_price, stop_loss=sl, risk_pts=risk,
                        target_center_mass=target_cm, target_head_shot=target_hs,
                        pd_array=pd_array, ai_rationale=rationale
                    )

        return None

    def diagnose_market(self, asset: str, candles: List[Candle], memory_engine: Optional[Any] = None) -> Dict[str, Any]:
        """
        Performs full multi-dimensional AI diagnostic analysis of market conditions,
        calculating setup confluence, reference levels, and executive reasoning.
        """
        spec = ASSET_SPECS[asset]
        if len(candles) < 6:
            return {
                "asset": asset,
                "status": "INITIALIZING",
                "status_label": "Syncing Market Tape",
                "badge": "b-p",
                "score": 0,
                "decision": "Accumulating market bars",
                "thesis": "Waiting for at least 6 bars to compute market structure.",
                "checklist": {
                    "Calendar Filter": "PASS",
                    "Session Timing": "PENDING",
                    "Range Volatility": "PENDING",
                    "Liquidity Sweep": "NO",
                    "Candle Body MSS": "NO",
                    "50% C.E. Respect": "NO"
                }
            }

        current_candle = candles[-1]
        now_et = current_candle.timestamp_et
        today_date = now_et.date()
        time_et = now_et.time()
        day_name = now_et.strftime('%A')
        current_px = current_candle.close

        # 1. Calendar Filter Check
        is_nfp = self.is_nfp_week(today_date) and day_name in ['Thursday', 'Friday']
        session_name = self.get_current_session(time_et)

        # 2. Reference Target Session
        target_session = session_name if session_name else (
            'NEW_YORK_AM' if time_et < datetime.time(8, 0) else (
                'ASIAN_MACRO' if time_et < datetime.time(18, 50) else 'LONDON'
            )
        )
        win = SESSION_WINDOWS[target_session]

        # 3. Calculate Reference Range
        today_bars = [c for c in candles if c.timestamp_et.date() == today_date]
        if win['ref_start'] < win['ref_end']:
            ref_bars = [c for c in today_bars if win['ref_start'] <= c.timestamp_et.time() < win['ref_end']]
        else:
            ref_bars = [c for c in candles if (c.timestamp_et.time() >= win['ref_start']) or (c.timestamp_et.time() < win['ref_end'])]

        if not ref_bars:
            ref_bars = candles[-20:]

        ref_high = max(c.high for c in ref_bars)
        ref_low = min(c.low for c in ref_bars)
        ref_range = ref_high - ref_low
        eq = ref_low + 0.5 * ref_range
        quadrant = "PREMIUM (Upper 50%)" if current_px > eq else "DISCOUNT (Lower 50%)"

        # 4. Sweep Inspection
        b0 = candles[-3] if len(candles) >= 3 else candles[-1]
        b1 = candles[-2] if len(candles) >= 2 else candles[-1]
        b2 = candles[-1]

        swept_high = any(c.high > ref_high and c.close < ref_high for c in [b0, b1, b2])
        swept_low = any(c.low < ref_low and c.close > ref_low for c in [b0, b1, b2])

        # 5. Diagnostic Checklist
        is_range_valid = ref_range >= spec['min_pre_range']
        checklist = {
            "Calendar Risk": "STANDBY (Pre-NFP)" if is_nfp else "CLEAR (No NFP Risk)",
            "Session Timing": f"ACTIVE ({session_name})" if session_name else f"STANDBY (Next: {target_session})",
            "Volatility Range": f"VALID ({ref_range:.2f} pts >= {spec['min_pre_range']:.2f})" if is_range_valid else f"COMPRESSED ({ref_range:.2f} < {spec['min_pre_range']:.2f})",
            "Liquidity Sweep": "BSL SWEPT (Bearish Fuel)" if swept_high else ("SSL SWEPT (Bullish Fuel)" if swept_low else "NO (Inside Range)"),
            "Candle Body MSS": "CONFIRMED" if (swept_high and (b1.body_bottom < b0.low or b2.body_bottom < b0.low)) or (swept_low and (b1.body_top > b0.high or b2.body_top > b0.high)) else "WAITING",
            "50% C.E. Respect": "RESPECTED" if (swept_high and b2.close <= eq) or (swept_low and b2.close >= eq) else "PENDING"
        }

        # Confluence Score (0 to 100)
        score = 0
        if not is_nfp: score += 15
        if session_name: score += 25
        if is_range_valid: score += 20
        if swept_high or swept_low: score += 20
        if checklist["Candle Body MSS"] == "CONFIRMED": score += 20

        # AI Executive Decision & Market Thesis
        if not session_name:
            status = "STANDBY_INTER_SESSION"
            status_label = f"Inter-Session ({target_session} Pending)"
            badge = "b-d"
            decision = "STAND DOWN — Capital Preservation"
            thesis = (
                f"Currently off-session in the inter-session liquidity transition. "
                f"Market volume is low and institutions are rebalancing before {target_session}. "
                f"Pre-session reference range is locked between High {ref_high:.2f} and Low {ref_low:.2f} ({ref_range:.2f} pts). "
                f"Standing down to prevent chop losses until the opening bell."
            )
        elif session_name == 'NEW_YORK_AM' and time_et < datetime.time(10, 0) and self.check_10am_gate(today_bars):
            status = "10AM_GATE_QUARANTINE"
            status_label = "10:00 AM NY Gate Active"
            badge = "b-q"
            decision = "QUARANTINE ENTRIES UNTIL 10:00 AM EST"
            thesis = "Cash open was contained inside the 09:00-09:30 AM range (Lecture 51). Quarantining entries to prevent opening whipsaws."
        elif not (swept_high or swept_low):
            status = "HUNTING_SWEEP"
            status_label = f"Active {session_name} — Hunting Liquidity"
            badge = "b-p"
            decision = "MONITORING FOR LIQUIDITY SWEEP"
            thesis = (
                f"Trading inside the reference range ({ref_low:.2f} to {ref_high:.2f}) in {quadrant}. "
                f"No institutional liquidity pool has been raided yet. "
                f"Waiting for smart money to wick above {ref_high:.2f} or below {ref_low:.2f} before taking any action."
            )
        else:
            status = "EVALUATING_MSS"
            status_label = "Sweep Detected — Checking MSS"
            badge = "b-l" if swept_low else "b-s"
            decision = "CONFIRMING DISPLACEMENT & 50% C.E."
            thesis = (
                f"Liquidity pool raided! {'High swept' if swept_high else 'Low swept'}. "
                f"Evaluating 5m candle body closure against 50% Consequent Encroachment ({eq:.2f}) to confirm genuine smart money participation."
            )

        return {
            "asset": asset,
            "status": status,
            "status_label": status_label,
            "badge": badge,
            "score": score,
            "current_price": current_px,
            "ref_high": ref_high,
            "ref_low": ref_low,
            "ref_range": ref_range,
            "min_range_needed": spec['min_pre_range'],
            "quadrant": quadrant,
            "checklist": checklist,
            "decision": decision,
            "thesis": thesis
        }

