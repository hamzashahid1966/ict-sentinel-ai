"""
ICT Sentinel AI - Institutional Tape Reading Advisor
Provides deep algorithmic reasoning and generates human-readable audit commentary.
"""

import datetime
from typing import Dict, List, Optional
from .models import Candle, Position, PDArray, AILogEntry
from .config import ASSET_SPECS
from .knowledge_engine import KnowledgeEngine

class AIAdvisor:
    def __init__(self, knowledge: Optional[KnowledgeEngine] = None):
        self.knowledge = knowledge or KnowledgeEngine()

    def create_system_log(self, category: str, message: str, asset: str = "GLOBAL", session: str = "RISK_ENGINE") -> AILogEntry:
        timestamp_str = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        return AILogEntry(
            timestamp=timestamp_str,
            asset=asset,
            session=session,
            category=category,
            message=message,
            reasoning=message
        )

    def explain_trade_entry(self, asset: str, session: str, direction: str, entry_price: float, risk_pts: float, pd_array: PDArray, rationale: str) -> AILogEntry:
        timestamp_str = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        spec = ASSET_SPECS[asset]
        dollar_risk = risk_pts * spec['point_value']
        ce_citation = self.knowledge.format_citation("RULE_CONSEQUENT_ENCROACHMENT")

        msg = f"ORDER ENTRY: {direction} {spec['display_name']} @ {entry_price:.2f}"
        ce_str = f"{pd_array.consequent_encroachment:.2f}" if (pd_array and pd_array.consequent_encroachment is not None) else "N/A"
        arr_type = pd_array.array_type if pd_array else 'DIRECT'
        f_time = pd_array.formation_time.strftime('%H:%M:%S EST') if pd_array else 'N/A'
        arr_high = pd_array.high if pd_array else 0.0
        arr_low = pd_array.low if pd_array else 0.0
        reasoning = (
            f"Institutional Setup Triggered in {session} {ce_citation}.\n"
            f"• Array Type: {arr_type} (Formed: {f_time})\n"
            f"• Array High: {arr_high:.2f} | Low: {arr_low:.2f} | 50% CE: {ce_str}\n"
            f"• Capital Allocation: Risk = {risk_pts:.2f} pts (${dollar_risk:.2f}). Max risk strictly bounded.\n"
            f"• Core Thesis: {rationale}"
        )
        return AILogEntry(
            timestamp=timestamp_str,
            asset=asset,
            session=session,
            category='ORDER_EXECUTION',
            message=msg,
            reasoning=reasoning
        )

    def explain_defensive_trail(self, pos: Position, new_trail_price: float, shield_name: str) -> AILogEntry:
        timestamp_str = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        oms_citation = self.knowledge.format_citation("RULE_DOUBLE_TAP_OMS")
        msg = f"DEFENSIVE SHIELD ADVANCED: {pos.asset} Trailing Stop moved to {new_trail_price:.2f}"
        reasoning = (
            f"Center Mass (1.5R) was banked successfully. In accordance with {oms_citation}, "
            f"stop loss is migrated to Defensive Shield: {shield_name}. "
            f"This insulates accumulated profits and prevents a winning trade from becoming a loss."
        )
        return AILogEntry(
            timestamp=timestamp_str,
            asset=pos.asset,
            session="LIVE_MANAGEMENT",
            category='DEFENSIVE_SHIELD',
            message=msg,
            reasoning=reasoning
        )

    def explain_early_scratch(self, pos: Position, exit_price: float, pnl_pts: float, dollar_pnl: float, reason: str) -> AILogEntry:
        timestamp_str = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        ce_cit = self.knowledge.format_citation("RULE_CONSEQUENT_ENCROACHMENT")
        body_cit = self.knowledge.format_citation("RULE_CANDLE_BODY_MSS")
        
        msg = f"EARLY SCRATCH EXIT: {pos.asset} closed at {exit_price:.2f} ({pnl_pts:+.2f} pts, ${dollar_pnl:+.2f})"
        if reason == "50_PCT_CE_BREACH":
            explanation = (
                f"Defending Fair Value Gap 50% Consequent Encroachment ({pos.defending_fvg_ce:.2f}) was breached by candle body close {ce_cit}.\n"
                f"Institutional order flow failed to protect the discount/premium imbalance. "
                f"Exited early to truncate loss and preserve capital (prevented full -1.0R loss)."
            )
        elif reason == "OPPOSING_MSS":
            explanation = (
                f"Opposing 5-minute Market Structure Shift occurred against active position {body_cit}.\n"
                f"Energetic displacement reversed order flow momentum. Exited immediately."
            )
        else:
            explanation = f"Position invalidated by active tape monitor: {reason}."

        reasoning = (
            f"INSTITUTIONAL EARLY SCRATCH PROTOCOL:\n"
            f"• Position: {pos.direction} {pos.asset} (Entry: {pos.entry_price:.2f})\n"
            f"• Invalidation Factor: {explanation}\n"
            f"• Net Saved Capital: Capped risk at ${abs(dollar_pnl):.2f} vs maximum full stop."
        )
        return AILogEntry(
            timestamp=timestamp_str,
            asset=pos.asset,
            session="RISK_GATE",
            category='RISK_GATE',
            message=msg,
            reasoning=reasoning
        )

    def explain_session_debrief(self, debrief) -> AILogEntry:
        timestamp_str = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        msg = f"SESSION TRANSITION DEBRIEF: {debrief.session_name} Closed"
        reasoning = (
            f"INTER-SESSION LIQUIDITY & DELIVERY SYNTHESIS:\n"
            f"• Session Range: Low {debrief.session_low:.2f} ──► High {debrief.session_high:.2f}\n"
            f"• Asian Liquidity Raids: {debrief.asian_sweep_type}\n"
            f"• Session PnL: ${debrief.net_dollar_pnl:+.2f} ({debrief.trades_taken} trades taken)\n"
            f"• Next Session Bias: {debrief.cross_session_bias}\n"
            f"• Strategic Directive: {debrief.ai_debrief_summary}"
        )
        return AILogEntry(
            timestamp=timestamp_str,
            asset="GLOBAL",
            session=debrief.session_name,
            category='IPDA_ANALYSIS',
            message=msg,
            reasoning=reasoning
        )

    def explain_trade_closure(self, pos: Position, exit_price: float, pnl_pts: float, dollar_pnl: float, outcome: str) -> AILogEntry:
        timestamp_str = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        status_word = "PROFITABLE EXIT" if dollar_pnl > 0 else ("EARLY SCRATCH" if outcome == 'EARLY_SCRATCH' else "CONTROLLED RISK STOP")
        msg = f"TRADE CLOSED [{outcome}]: {pos.asset} @ {exit_price:.2f} (Net: ${dollar_pnl:+.2f})"

        target_info = (
            f"• Target 1 (Center Mass 1.5R): {pos.target_center_mass:.2f} {'[FILLED]' if pos.center_mass_filled else '[MISSED]'}\n"
            f"• Target 2 (Head Shot 3.0R): {pos.target_head_shot:.2f} {'[FILLED]' if pos.head_shot_filled else '[MISSED]'}\n"
        )
        if pos.target_liquidity_pool:
            target_info += f"• Targeted Liquidity Pool: {pos.target_liquidity_pool}\n"

        if outcome == 'FULL_WIN':
            details = "Both Center Mass (1.5R) and Head Shot Terminus (3.0R) were delivered cleanly by IPDA."
        elif outcome == 'DEFENSIVE_STOP':
            details = "Center Mass was banked (+1.5R). Retracement hit defensive trailing shield, locking in positive net profit."
        elif outcome == 'EARLY_SCRATCH':
            details = f"Early scratch triggered: {pos.invalidation_reason or 'Order flow breakdown'}. Capital preserved."
        elif outcome == 'SESSION_EXPIRATION':
            details = "Session exit deadline reached. Closed at market to avoid holding through dead zone chop."
        elif outcome == 'LOSS':
            details = "Initial stop triggered. Risk was capped within mandatory institutional threshold."
        else:
            details = "Session duration threshold reached; position closed at market close."

        reasoning = (
            f"{status_word}.\n"
            f"• Entry: {pos.entry_price:.2f} ──► Exit: {exit_price:.2f}\n"
            f"• Points: {pnl_pts:+.2f} pts | Dollar PnL: ${dollar_pnl:+.2f}\n"
            f"{target_info}"
            f"• Institutional Analysis: {details}"
        )
        return AILogEntry(
            timestamp=timestamp_str,
            asset=pos.asset,
            session="EXIT_MANAGEMENT",
            category='ORDER_EXECUTION',
            message=msg,
            reasoning=reasoning
        )

