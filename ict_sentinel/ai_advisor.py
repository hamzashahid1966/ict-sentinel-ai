"""
ICT Sentinel AI - Institutional Tape Reading Advisor
Provides deep algorithmic reasoning and generates human-readable audit commentary.
"""

import datetime
from typing import Dict, List, Optional
from .models import Candle, Position, PDArray, AILogEntry
from .config import ASSET_SPECS

class AIAdvisor:
    def __init__(self):
        pass

    def explain_trade_entry(self, asset: str, session: str, direction: str, entry_price: float, risk_pts: float, pd_array: PDArray, rationale: str) -> AILogEntry:
        timestamp_str = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        spec = ASSET_SPECS[asset]
        dollar_risk = risk_pts * spec['point_value']

        msg = f"ORDER ENTRY: {direction} {spec['display_name']} @ {entry_price:.2f}"
        reasoning = (
            f"Institutional Setup Triggered in {session}.\n"
            f"• Array Type: {pd_array.array_type} (Formed: {pd_array.formation_time.strftime('%H:%M:%S EST')})\n"
            f"• Array High: {pd_array.high:.2f} | Low: {pd_array.low:.2f} | 50% CE: {pd_array.consequent_encroachment:.2f}\n"
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
        msg = f"DEFENSIVE SHIELD ADVANCED: {pos.asset} Trailing Stop moved to {new_trail_price:.2f}"
        reasoning = (
            f"Center Mass (1.5R) was banked successfully. In accordance with Lecture 52, "
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

    def explain_trade_closure(self, pos: Position, exit_price: float, pnl_pts: float, dollar_pnl: float, outcome: str) -> AILogEntry:
        timestamp_str = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        status_word = "PROFITABLE EXIT" if dollar_pnl > 0 else "CONTROLLED RISK STOP"
        msg = f"TRADE CLOSED [{outcome}]: {pos.asset} @ {exit_price:.2f} (Net: ${dollar_pnl:+.2f})"

        if outcome == 'FULL_WIN':
            details = "Both Center Mass (1.5R) and Head Shot Terminus (3.0R) were delivered cleanly by IPDA."
        elif outcome == 'DEFENSIVE_STOP':
            details = "Center Mass was banked (+1.5R). Retracement hit defensive trailing shield, locking in positive net profit."
        elif outcome == 'LOSS':
            details = "Initial stop triggered. Risk was capped within mandatory institutional threshold."
        else:
            details = "Session duration threshold reached; position closed at market close."

        reasoning = (
            f"{status_word}.\n"
            f"• Entry: {pos.entry_price:.2f} ──► Exit: {exit_price:.2f}\n"
            f"• Points: {pnl_pts:+.2f} pts | Dollar PnL: ${dollar_pnl:+.2f}\n"
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

