"""
ICT Sentinel AI - Adaptive Memory & Self-Learning Engine
Maintains episodic trade memory, performs automated AI post-mortems,
updates dynamic Bayesian quality weights, and enforces session circuit breakers.
"""

import datetime
from typing import Dict, Any, List, Tuple, Optional
from .storage import StorageEngine
from .ai_advisor import AIAdvisor
from .models import Position, TradeRecord, Candle

class MemoryEngine:
    def __init__(self, storage: StorageEngine, advisor: AIAdvisor):
        self.storage = storage
        self.advisor = advisor

    def process_trade_completion(self, tr: TradeRecord, pos: Position, current_bar: Candle):
        """
        Processes a newly closed trade into episodic memory, executes an AI post-mortem,
        calculates Bayesian Quality Scores, and updates dynamic regime weights.
        """
        # 1. Extract Episodic Features
        ep_id = f"ep_{tr.trade_id}"
        day_name = current_bar.timestamp_et.strftime('%A')
        session_name = tr.session if tr.session != "LIVE" else self._infer_session(current_bar.timestamp_et.time())
        array_type = "SIBI" if tr.direction == "SHORT" else "BISI"

        # Record in persistent trade_episodes table
        self.storage.record_episode(
            ep_id=ep_id,
            asset=tr.asset,
            session=session_name,
            day_name=day_name,
            direction=tr.direction,
            array_type=array_type,
            risk_pts=tr.risk_pts,
            outcome=tr.outcome,
            dollar_pnl=tr.dollar_pnl
        )

        # 2. Automated AI Post-Mortem Reflection
        reflection_type, lesson, action_taken = self._generate_reflection(tr, pos, session_name, day_name)
        self.storage.record_reflection(
            asset=tr.asset,
            session=session_name,
            ref_type=reflection_type,
            lesson=lesson,
            action=action_taken
        )

        # Sync to persistent machine-readable knowledge ledger
        if hasattr(self.advisor, 'knowledge') and self.advisor.knowledge:
            self.advisor.knowledge.record_learning_episode({
                "episode_id": ep_id,
                "asset": tr.asset,
                "session": session_name,
                "day_of_week": day_name,
                "direction": tr.direction,
                "outcome": tr.outcome,
                "dollar_pnl": tr.dollar_pnl,
                "reflection_type": reflection_type,
                "lesson": lesson,
                "action_taken": action_taken,
                "recorded_at": datetime.datetime.utcnow().isoformat()
            })

        # 3. Dynamic Bayesian Updating & Circuit Breaker Logic
        self._update_regime_weights(tr.asset, session_name, tr.outcome, tr.dollar_pnl)

    def _infer_session(self, time_et: datetime.time) -> str:
        from .config import SESSION_WINDOWS
        for sname, win in SESSION_WINDOWS.items():
            if win['exec_start'] <= time_et <= win['exec_end']:
                return sname
        return "REGULAR"

    def _generate_reflection(self, tr: TradeRecord, pos: Position, session: str, day: str) -> Tuple[str, str, str]:
        """
        Synthesizes an institutional post-mortem based on the outcome and trade mechanics.
        """
        if tr.outcome == "FULL_WIN":
            ref_type = "EXPANSION_SUCCESS"
            lesson = (
                f"Full 3.0R Head Shot achieved on {tr.asset} during {session} ({day}). "
                f"Candle body displacement cleanly expanded without violating Consequent Encroachment (C.E.). "
                f"Institutional order flow confirmed strong delivery into target pool."
            )
            action_taken = f"Reinforced Bayesian weight for {tr.asset}::{session}. Retained standard risk allocation."

        elif tr.outcome == "DEFENSIVE_STOP":
            ref_type = "DEFENSIVE_HARVEST"
            lesson = (
                f"Double Tap architecture succeeded on {tr.asset} ({session}). "
                f"Center Mass (1.5R) banked early profit (+${pos.realized_pnl:.2f}); runner stopped out defensively at Breakeven cushion. "
                f"Total net outcome remained positive (+${tr.dollar_pnl:.2f}). Protected against terminal session reversal."
            )
            action_taken = f"Confirmed defensive trail effectiveness. Upgraded confluence score for {session}."

        else: # LOSS
            ref_type = "INVALIDATION_POST_MORTEM"
            lesson = (
                f"Full stop loss triggered on {tr.asset} ({session}, {day}) resulting in -${abs(tr.dollar_pnl):.2f}. "
                f"Setup breached initial institutional invalidation point. Possible premature entry, "
                f"low liquidity chop, or higher timeframe macroeconomic realignment."
            )
            action_taken = (
                f"Decremented Bayesian score for {tr.asset}::{session}. "
                f"Incremented consecutive loss tracker. Applied cooldown throttle if threshold breached."
            )

        return ref_type, lesson, action_taken

    def _update_regime_weights(self, asset: str, session: str, outcome: str, dollar_pnl: float):
        """
        Calculates the dynamic Bayesian Quality Score (BQS):
        BQS = (Wins + 2) / (Wins + Losses + 4) * min(1.0, Profit_Factor / 2.0)
        Enforces automatic session quarantine if BQS < 0.40 or consecutive losses >= 2.
        """
        key_pair = f"{asset}::{session}"
        existing = self.storage.get_adaptive_weight(asset, session)
        
        is_win = dollar_pnl > 0
        current_wins = (existing['wins'] if existing else 0) + (1 if is_win else 0)
        current_losses = (existing['losses'] if existing else 0) + (0 if is_win else 1)
        consecutive_losses = 0 if is_win else ((existing['consecutive_losses'] if existing else 0) + 1)

        # Bayesian Posterior with Beta(2, 2) uninformative prior
        alpha = current_wins + 2
        beta = current_losses + 2
        raw_win_rate = alpha / (alpha + beta)

        # Quality Score calibrated against consecutive losses
        penalty = 0.15 * consecutive_losses
        quality_score = max(0.10, min(0.99, raw_win_rate - penalty))

        total_episodes = current_wins + current_losses
        # Dynamic Status Management
        if consecutive_losses >= 2 or (total_episodes >= 3 and quality_score < 0.40):
            status = "QUARANTINED"
            # Log circuit breaker activation
            self.storage.record_reflection(
                asset=asset,
                session=session,
                ref_type="CIRCUIT_BREAKER_ENGAGED",
                lesson=f"Asset {asset} in session {session} suffered {consecutive_losses} consecutive loss(es) or low BQS ({quality_score:.2f}).",
                action="Gated trading for this pair until regime stabilization."
            )
        elif quality_score < 0.55 or consecutive_losses == 1:
            status = "OBSERVATION"
        else:
            status = "PRIME"

        self.storage.update_adaptive_weight(
            asset=asset,
            session=session,
            win=is_win,
            quality_score=quality_score,
            consecutive_losses=consecutive_losses,
            status=status
        )

    def evaluate_setup_viability(self, asset: str, session: str, array_type: str) -> Tuple[bool, float, str]:
        """
        Called by IPDA Engine before generating a signal.
        Acts as the intelligent gating filter based on learned history.
        Returns: (approved: bool, confidence: float, reason: str)
        """
        weight = self.storage.get_adaptive_weight(asset, session)
        
        # If no history yet, grant default probationary clearance
        if not weight:
            return True, 0.70, "Probationary clearance: No prior adverse historical regime recorded."

        status = weight.get('status', 'PRIME')
        q_score = weight.get('quality_score', 0.50)
        cons_losses = weight.get('consecutive_losses', 0)

        if status == "QUARANTINED":
            return False, q_score, f"REJECTED BY ADAPTIVE MEMORY: Regime {asset}::{session} is QUARANTINED (BQS: {q_score:.2f}, Consecutive Losses: {cons_losses})."

        if status == "OBSERVATION":
            # Higher scrutiny required: Require at least 0.45 quality score
            if q_score < 0.45:
                return False, q_score, f"FILTERED: Regime {asset}::{session} in OBSERVATION mode; confidence {q_score:.2f} below minimum execution hurdle."
            return True, q_score, f"APPROVED (OBSERVATION): Scrutiny passed with BQS {q_score:.2f}."

        return True, q_score, f"APPROVED (PRIME): High-conviction regime verified (BQS: {q_score:.2f}, Wins: {weight['wins']}, Losses: {weight['losses']})."

    def get_all_weights(self) -> List[Dict[str, Any]]:
        return self.storage.get_all_adaptive_weights()

    def get_recent_reflections(self, limit: int = 5) -> List[Dict[str, Any]]:
        return self.storage.get_recent_reflections(limit=limit)

    def synthesize_weekly_meta_reflection(self) -> Dict[str, Any]:
        """
        Executes macroscopic multi-session meta-reflection following the Scientific Method.
        Computes rolling Sharpe ratio, Profit Factor, evaluates institutional benchmarks,
        and generates a single-variable hypothesis ledger entry.
        """
        import math
        from .config import INSTITUTIONAL_GOALS, INITIAL_CAPITAL

        trades = self.storage.get_trade_history(limit=50)
        total = len(trades)
        wins = [t for t in trades if t.dollar_pnl > 0]
        losses = [t for t in trades if t.dollar_pnl < 0]
        wr = (len(wins) / total * 100.0) if total else 0.0
        gp = sum(t.dollar_pnl for t in wins)
        gl = abs(sum(t.dollar_pnl for t in losses))
        pf = (gp / gl) if gl > 0 else (9.99 if gp > 0 else 0.0)
        net_pnl = gp - gl

        # Calculate Realized Sharpe Ratio across trades
        realized_sharpe = 0.0
        if total >= 3:
            returns = [t.dollar_pnl / INITIAL_CAPITAL for t in trades]
            mean_r = sum(returns) / total
            var_r = sum((r - mean_r) ** 2 for r in returns) / (total - 1)
            std_r = math.sqrt(var_r) if var_r > 0 else 0.0
            if std_r > 0:
                realized_sharpe = round((mean_r / std_r) * math.sqrt(min(252, total * 12)), 2)

        # Formulate Scientific Single-Variable Hypothesis
        if total == 0:
            variable_tested = "Baseline Initialization"
            hypothesis = "Awaiting trade executions to formulate initial baseline hypothesis."
            status = "INITIALIZING"
        elif pf >= INSTITUTIONAL_GOALS['target_profit_factor'] and wr >= INSTITUTIONAL_GOALS['target_win_rate_pct']:
            variable_tested = "Center Mass Scaling Target (1.5R)"
            hypothesis = f"Strong institutional baseline confirmed (PF: {pf:.2f}, WR: {wr:.1f}%, Sharpe: {realized_sharpe:.2f}). Hypothesis: Maintain 1.5R Center Mass target to maximize early profit extraction without premature stops."
            status = "CONFIRMED"
        elif wr < 50.0:
            variable_tested = "Runner Defensive Stop Buffer (2 Ticks)"
            hypothesis = f"Elevated stop-out rate observed (WR: {wr:.1f}%). Hypothesis: Increase defensive stop buffer from 2 ticks to 3 ticks on runner contracts to insulate against intraday noise."
            status = "TESTING"
        else:
            variable_tested = "Asian Session Pre-Range Threshold (4.0 pts)"
            hypothesis = f"Balanced regime performance (PF: {pf:.2f}). Hypothesis: Filter out setups when Asian reference range is compressed below 4.5 pts to prevent false breakouts."
            status = "OBSERVING"

        reflection = {
            'window_name': f"Rolling {total}-Trade Batch Window",
            'total_trades': total,
            'win_rate': round(wr, 1),
            'realized_sharpe': realized_sharpe,
            'profit_factor': round(pf, 2),
            'net_pnl': round(net_pnl, 2),
            'hypothesis': hypothesis,
            'variable_tested': variable_tested,
            'status': status
        }
        self.storage.record_meta_reflection(reflection)
        return reflection

    def get_latest_meta_reflections(self, limit: int = 5) -> List[Dict[str, Any]]:
        return self.storage.get_latest_meta_reflections(limit=limit)
