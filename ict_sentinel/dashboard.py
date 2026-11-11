"""
ICT Sentinel AI - Real-Time Terminal Telemetry Dashboard
"""

import os
import datetime
from typing import List, Dict, Any, Optional
from .models import AccountState, Position, TradeRecord, AILogEntry
from .config import ASSET_SPECS, INITIAL_CAPITAL

class DashboardRenderer:
    def __init__(self):
        pass

    @staticmethod
    def render(
        account: AccountState,
        open_positions: List[Position],
        trades: List[TradeRecord],
        recent_logs: List[AILogEntry],
        prices: Dict[str, float],
        active_session: str,
        adaptive_weights: Optional[List[Dict[str, Any]]] = None,
        reflections: Optional[List[Dict[str, Any]]] = None
    ):
        now_utc = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        wins = [t for t in trades if t.dollar_pnl > 0]
        losses = [t for t in trades if t.dollar_pnl < 0]
        total_trades = len(trades)
        win_rate = (len(wins) / total_trades * 100.0) if total_trades > 0 else 0.0

        gross_profit = sum(t.dollar_pnl for t in wins)
        gross_loss = abs(sum(t.dollar_pnl for t in losses))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0)

        # Build ASCII UI
        lines = []
        lines.append("=" * 102)
        lines.append(f"  ICT SENTINEL AI — AUTONOMOUS 52-LECTURE INSTITUTIONAL TRADING AGENT")
        lines.append(f"  Time: {now_utc}  |  Active Session: {active_session:<14}  |  Starting Capital: ${INITIAL_CAPITAL:.2f}")
        lines.append("=" * 102)

        # 1. Account Summary
        lines.append(f"\n[ PORTFOLIO TELEMETRY ]")
        lines.append(f"  Current Balance: ${account.balance:9.2f}  |  Peak Balance: ${account.peak_balance:9.2f}  |  Net PnL: ${account.realized_pnl:+9.2f}")
        lines.append(f"  Win Rate:        {win_rate:6.1f}%     |  Profit Factor: {profit_factor:6.2f}      |  Max Drawdown: ${account.max_drawdown_dollars:6.2f} ({account.max_drawdown_pct:.1f}%)")
        lines.append(f"  Total Trades:    {total_trades:<6}      |  Wins: {len(wins):<4} | Losses: {len(losses):<4}  |  Open Positions: {len(open_positions)}")
        lines.append("-" * 102)

        # 2. Monitored Markets Telemetry
        lines.append(f"\n[ MONITORED ASSET STREAMS ]")
        lines.append(f"  {'ASSET':<10} | {'SYMBOL':<10} | {'DISPLAY NAME':<34} | {'LATEST PRICE':<14} | {'STATUS':<15}")
        lines.append(f"  {'-'*96}")
        for asset, spec in ASSET_SPECS.items():
            px = prices.get(asset, 0.0)
            px_str = f"{px:12.4f}" if asset in ['GBPUSD', 'EURUSD'] else f"{px:12.2f}"
            has_pos = any(p.asset == asset for p in open_positions)
            status_str = "IN POSITION" if has_pos else "MONITORING TAPE"
            lines.append(f"  {asset:<10} | {spec['symbol']:<10} | {spec['display_name']:<34} | {px_str:<14} | {status_str:<15}")
        lines.append("-" * 102)

        # 3. Active Positions
        lines.append(f"\n[ ACTIVE OPEN POSITIONS (DOUBLE TAP ARCHITECTURE) ]")
        if not open_positions:
            lines.append("  (No active open positions. Watching for session liquidity sweeps and candle body MSS...)")
        else:
            lines.append(f"  {'POS ID':<8} | {'ASSET':<8} | {'DIR':<5} | {'ENTRY':<10} | {'STOP LOSS':<10} | {'CENTER MASS (1.5R)':<18} | {'HEAD SHOT (3.0R)':<16} | {'STATUS'}")
            lines.append(f"  {'-'*96}")
            for p in open_positions:
                lines.append(f"  {p.position_id:<8} | {p.asset:<8} | {p.direction:<5} | {p.entry_price:<10.2f} | {p.active_trailing_stop:<10.2f} | {p.target_center_mass:<18.2f} | {p.target_head_shot:<16.2f} | {p.status}")
        lines.append("-" * 102)

        # 4. Recent AI Institutional Thoughts
        lines.append(f"\n[ RECENT AI INSTITUTIONAL AUDIT LOGS ]")
        if not recent_logs:
            lines.append("  (Awaiting first algorithmic session trigger...)")
        else:
            for log in recent_logs[:3]:
                lines.append(f"  [{log.timestamp}] [{log.asset} - {log.category}] {log.message}")
                for rline in log.reasoning.split('\n'):
                    lines.append(f"    └─ {rline}")
        lines.append("-" * 102)

        # 5. Adaptive Memory Telemetry
        lines.append(f"\n[ ADAPTIVE MEMORY & SELF-LEARNING TELEMETRY ]")
        if adaptive_weights:
            lines.append(f"  {'REGIME':<20} | {'RECORD':<10} | {'BAYESIAN SCORE':<16} | {'REGIME STATUS':<16} | {'STREAK'}")
            lines.append(f"  {'-'*80}")
            for w in adaptive_weights[:6]:
                rec_str = f"{w['wins']}W / {w['losses']}L"
                status_color = w['status']
                streak_str = f"{w['consecutive_losses']} loss streak" if w['consecutive_losses'] > 0 else "Clean"
                lines.append(f"  {w['key_pair']:<20} | {rec_str:<10} | {w['quality_score']*100:13.1f}% | {status_color:<16} | {streak_str}")
        else:
            lines.append("  (Memory Engine initialized. Accumulating empirical trade episodes...)")

        if reflections:
            lines.append(f"\n  Latest Self-Learning Reflection:")
            r = reflections[0]
            lines.append(f"  [{r['timestamp']}] [{r['asset']}::{r['session']}] Type: {r['reflection_type']}")
            lines.append(f"    └─ Lesson: {r['lesson']}")
            lines.append(f"    └─ Action: {r['action_taken']}")
        lines.append("=" * 102)

        print("\n".join(lines))

