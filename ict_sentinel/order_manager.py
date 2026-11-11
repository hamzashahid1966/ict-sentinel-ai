"""
ICT Sentinel AI - Double Tap Virtual Order Management System (OMS)
Manages the two-stage execution architecture, defensive trailing stops, and profit extraction.
"""

import uuid
import datetime
from typing import List, Optional, Dict, Any
from .config import ASSET_SPECS
from .models import Position, TradeRecord, Candle
from .ipda_engine import AlgorithmicSignal
from .storage import StorageEngine
from .ai_advisor import AIAdvisor

class OrderManager:
    def __init__(self, storage: StorageEngine, advisor: AIAdvisor, memory_engine: Optional[Any] = None):
        self.storage = storage
        self.advisor = advisor
        self.memory_engine = memory_engine
        self._positions_cache: Optional[List[Position]] = None

    def _get_active_positions(self) -> List[Position]:
        if self._positions_cache is None:
            self._positions_cache = self.storage.load_open_positions()
        return self._positions_cache

    def _sync_position(self, pos: Position):
        self.storage.save_position(pos)
        cache = self._get_active_positions()
        idx = next((i for i, p in enumerate(cache) if p.position_id == pos.position_id), None)
        if idx is not None:
            cache[idx] = pos
        else:
            cache.append(pos)

    def _remove_position(self, pos_id: str):
        self._positions_cache = [p for p in self._get_active_positions() if p.position_id != pos_id]

    def open_position_from_signal(self, sig: AlgorithmicSignal, current_time: datetime.datetime) -> Optional[Position]:
        open_positions = self._get_active_positions()
        # Avoid duplicate positions on the same asset
        if any(p.asset == sig.asset for p in open_positions):
            return None

        # Position Sizing: 1 micro contract or 0.10 mini lot for $500 balance
        pos_id = str(uuid.uuid4())[:8]
        pos = Position(
            position_id=pos_id,
            asset=sig.asset,
            direction=sig.direction,
            quantity=1,
            entry_price=sig.entry_price,
            entry_time=current_time,
            initial_stop_loss=sig.stop_loss,
            active_trailing_stop=sig.stop_loss,
            target_center_mass=sig.target_center_mass,
            target_head_shot=sig.target_head_shot,
            center_mass_filled=False,
            head_shot_filled=False,
            realized_pnl=0.0,
            status='OPEN',
            defensive_shields=['Initial Institutional Stop'],
            defending_fvg_ce=sig.pd_array.consequent_encroachment if sig.pd_array else None,
            target_liquidity_pool=sig.ai_rationale,
            session_origin=sig.session
        )
        self._sync_position(pos)

        # Log AI Thought
        log_entry = self.advisor.explain_trade_entry(
            asset=sig.asset,
            session=sig.session,
            direction=sig.direction,
            entry_price=sig.entry_price,
            risk_pts=sig.risk_pts,
            pd_array=sig.pd_array,
            rationale=sig.ai_rationale
        )
        self.storage.log_ai_thought(log_entry)
        return pos

    def update_positions_with_bar(self, asset: str, current_bar: Candle) -> List[TradeRecord]:
        """
        Evaluates open positions against the latest bar (high, low, close).
        Executes Center Mass partials, trails defensive stops, and manages exits.
        """
        open_positions = [p for p in self._get_active_positions() if p.asset == asset]
        if not open_positions:
            return []

        closed_trades: List[TradeRecord] = []
        spec = ASSET_SPECS[asset]
        friction = spec['commission'] + (spec['slippage_ticks'] * spec['tick_size'] * spec['point_value'])

        for pos in open_positions:
            is_long = pos.direction == 'LONG'
            risk_pts = abs(pos.entry_price - pos.initial_stop_loss)

            # ---------------- STAGE 0: CHECK EARLY SCRATCH INVALIDATION (FVG 50% CE) ----------------
            if not pos.center_mass_filled and pos.defending_fvg_ce is not None:
                ce_breached = (current_bar.close < pos.defending_fvg_ce) if is_long else (current_bar.close > pos.defending_fvg_ce)
                if ce_breached:
                    exit_price = current_bar.close
                    outcome = 'EARLY_SCRATCH'
                    pos.invalidation_reason = '50_PCT_CE_BREACH'
                    pnl_pts = (exit_price - pos.entry_price) if is_long else (pos.entry_price - exit_price)
                    dollar_pnl = (pnl_pts * spec['point_value']) - friction
                    
                    self.storage.update_account_balance(dollar_pnl)
                    tr = TradeRecord(
                        trade_id=pos.position_id,
                        asset=pos.asset,
                        session=pos.session_origin or "LIVE",
                        direction=pos.direction,
                        entry_time=pos.entry_time.strftime('%Y-%m-%d %H:%M:%S'),
                        entry_price=pos.entry_price,
                        exit_time=current_bar.timestamp_et.strftime('%Y-%m-%d %H:%M:%S'),
                        exit_price=exit_price,
                        risk_pts=risk_pts,
                        pnl_pts=pnl_pts,
                        dollar_pnl=dollar_pnl,
                        outcome=outcome,
                        ai_reasoning=f"Early scratch triggered: 50% CE breached ({pos.defending_fvg_ce:.2f}). Capital protected.",
                        target_tp1_price=pos.target_center_mass,
                        target_tp2_price=pos.target_head_shot,
                        invalidation_reason=pos.invalidation_reason,
                        target_liquidity_pool=pos.target_liquidity_pool
                    )
                    self.storage.record_closed_trade(tr)
                    scratch_log = self.advisor.explain_early_scratch(pos, exit_price, pnl_pts, dollar_pnl, pos.invalidation_reason)
                    self.storage.log_ai_thought(scratch_log)
                    self._remove_position(pos.position_id)
                    if self.memory_engine:
                        self.memory_engine.process_trade_completion(tr, pos, current_bar)
                    closed_trades.append(tr)
                    continue

            # ---------------- STAGE 0B: CHECK SESSION EXIT DEADLINE ----------------
            from .config import SESSION_WINDOWS
            session_expired = False
            if pos.session_origin and pos.session_origin in SESSION_WINDOWS:
                deadline = SESSION_WINDOWS[pos.session_origin].get('exit_time')
                if deadline and current_bar.timestamp_et.time() >= deadline:
                    session_expired = True

            if session_expired:
                exit_price = current_bar.close
                outcome = 'SESSION_EXPIRATION'
                pos.invalidation_reason = 'SESSION_DEADLINE_REACHED'
                pts = (exit_price - pos.entry_price) if is_long else (pos.entry_price - exit_price)
                if pos.center_mass_filled:
                    dollar_pnl = pos.realized_pnl + (0.5 * pts * spec['point_value']) - (0.5 * friction)
                else:
                    dollar_pnl = (pts * spec['point_value']) - friction
                pnl_pts = dollar_pnl / spec['point_value']

                self.storage.update_account_balance(dollar_pnl)
                tr = TradeRecord(
                    trade_id=pos.position_id,
                    asset=pos.asset,
                    session=pos.session_origin or "LIVE",
                    direction=pos.direction,
                    entry_time=pos.entry_time.strftime('%Y-%m-%d %H:%M:%S'),
                    entry_price=pos.entry_price,
                    exit_time=current_bar.timestamp_et.strftime('%Y-%m-%d %H:%M:%S'),
                    exit_price=exit_price,
                    risk_pts=risk_pts,
                    pnl_pts=pnl_pts,
                    dollar_pnl=dollar_pnl,
                    outcome=outcome,
                    ai_reasoning="Session exit deadline reached. Closed at market to avoid dead zone chop.",
                    target_tp1_price=pos.target_center_mass,
                    target_tp2_price=pos.target_head_shot,
                    invalidation_reason=pos.invalidation_reason,
                    target_liquidity_pool=pos.target_liquidity_pool
                )
                self.storage.record_closed_trade(tr)
                close_log = self.advisor.explain_trade_closure(pos, exit_price, pnl_pts, dollar_pnl, outcome)
                self.storage.log_ai_thought(close_log)
                self._remove_position(pos.position_id)
                if self.memory_engine:
                    self.memory_engine.process_trade_completion(tr, pos, current_bar)
                closed_trades.append(tr)
                continue

            # ---------------- STAGE 1: CHECK CENTER MASS (1.5R) ----------------
            if not pos.center_mass_filled:
                hit_center_mass = (current_bar.high >= pos.target_center_mass) if is_long else (current_bar.low <= pos.target_center_mass)
                if hit_center_mass:
                    pos.center_mass_filled = True
                    pos.status = 'PARTIAL'
                    # Realize 50% position profit
                    pts_cm = abs(pos.target_center_mass - pos.entry_price)
                    pos.realized_pnl = (0.5 * pts_cm * spec['point_value']) - (0.5 * friction)

                    # ADVANCE TO DEFENSIVE SHIELD: Breakeven + 2 ticks buffer (Lecture 52)
                    new_stop = (pos.entry_price + (2 * spec['tick_size'])) if is_long else (pos.entry_price - (2 * spec['tick_size']))
                    pos.active_trailing_stop = new_stop
                    pos.defensive_shields.append('Shield #1: Consequent Encroachment / Breakeven Buffer')

                    self._sync_position(pos)
                    trail_log = self.advisor.explain_defensive_trail(
                        pos=pos,
                        new_trail_price=new_stop,
                        shield_name='Breakeven + 2 Ticks Cushion'
                    )
                    self.storage.log_ai_thought(trail_log)

            # ---------------- STAGE 2: CHECK TRAILING STOP LOSS ----------------
            hit_stop = (current_bar.low <= pos.active_trailing_stop) if is_long else (current_bar.high >= pos.active_trailing_stop)
            if hit_stop:
                exit_price = pos.active_trailing_stop
                if not pos.center_mass_filled:
                    # Full initial loss
                    outcome = 'LOSS'
                    pnl_pts = (exit_price - pos.entry_price) if is_long else (pos.entry_price - exit_price)
                    dollar_pnl = (pnl_pts * spec['point_value']) - friction
                else:
                    # Defensive stop hit with Center Mass already banked!
                    outcome = 'DEFENSIVE_STOP'
                    pnl_runner_pts = (exit_price - pos.entry_price) if is_long else (pos.entry_price - exit_price)
                    pnl_runner_dollar = (0.5 * pnl_runner_pts * spec['point_value']) - (0.5 * friction)
                    dollar_pnl = pos.realized_pnl + pnl_runner_dollar
                    pnl_pts = dollar_pnl / spec['point_value']

                self.storage.update_account_balance(dollar_pnl)
                pos.invalidation_reason = 'HARD_STOP_BREACH' if not pos.center_mass_filled else 'DEFENSIVE_TRAILING_STOP'
                tr = TradeRecord(
                    trade_id=pos.position_id,
                    asset=pos.asset,
                    session=pos.session_origin or "LIVE",
                    direction=pos.direction,
                    entry_time=pos.entry_time.strftime('%Y-%m-%d %H:%M:%S'),
                    entry_price=pos.entry_price,
                    exit_time=current_bar.timestamp_et.strftime('%Y-%m-%d %H:%M:%S'),
                    exit_price=exit_price,
                    risk_pts=risk_pts,
                    pnl_pts=pnl_pts,
                    dollar_pnl=dollar_pnl,
                    outcome=outcome,
                    ai_reasoning=f"Closed on Stop trigger @ {exit_price:.2f}. Outcome: {outcome}",
                    target_tp1_price=pos.target_center_mass,
                    target_tp2_price=pos.target_head_shot,
                    invalidation_reason=pos.invalidation_reason,
                    target_liquidity_pool=pos.target_liquidity_pool
                )
                self.storage.record_closed_trade(tr)
                close_log = self.advisor.explain_trade_closure(pos, exit_price, pnl_pts, dollar_pnl, outcome)
                self.storage.log_ai_thought(close_log)
                self._remove_position(pos.position_id)
                if self.memory_engine:
                    self.memory_engine.process_trade_completion(tr, pos, current_bar)
                closed_trades.append(tr)
                continue

            # ---------------- STAGE 3: CHECK HEAD SHOT TERMINUS (3.0R) ----------------
            if pos.center_mass_filled:
                hit_head_shot = (current_bar.high >= pos.target_head_shot) if is_long else (current_bar.low <= pos.target_head_shot)
                if hit_head_shot:
                    exit_price = pos.target_head_shot
                    outcome = 'FULL_WIN'
                    pnl_runner_pts = abs(exit_price - pos.entry_price)
                    pnl_runner_dollar = (0.5 * pnl_runner_pts * spec['point_value']) - (0.5 * friction)
                    dollar_pnl = pos.realized_pnl + pnl_runner_dollar
                    pnl_pts = dollar_pnl / spec['point_value']

                    self.storage.update_account_balance(dollar_pnl)
                    tr = TradeRecord(
                        trade_id=pos.position_id,
                        asset=pos.asset,
                        session=pos.session_origin or "LIVE",
                        direction=pos.direction,
                        entry_time=pos.entry_time.strftime('%Y-%m-%d %H:%M:%S'),
                        entry_price=pos.entry_price,
                        exit_time=current_bar.timestamp_et.strftime('%Y-%m-%d %H:%M:%S'),
                        exit_price=exit_price,
                        risk_pts=risk_pts,
                        pnl_pts=pnl_pts,
                        dollar_pnl=dollar_pnl,
                        outcome=outcome,
                        ai_reasoning="Full algorithmic objective reached at Head Shot terminus (3.0R).",
                        target_tp1_price=pos.target_center_mass,
                        target_tp2_price=pos.target_head_shot,
                        invalidation_reason="TARGET_COMPLETED",
                        target_liquidity_pool=pos.target_liquidity_pool
                    )
                    self.storage.record_closed_trade(tr)
                    close_log = self.advisor.explain_trade_closure(pos, exit_price, pnl_pts, dollar_pnl, outcome)
                    self.storage.log_ai_thought(close_log)
                    self._remove_position(pos.position_id)
                    if self.memory_engine:
                        self.memory_engine.process_trade_completion(tr, pos, current_bar)
                    closed_trades.append(tr)

        return closed_trades

    def flatten_all_positions(self, current_prices: Dict[str, float]) -> List[TradeRecord]:
        """Liquidates all open positions at market price on demand."""
        open_positions = self.storage.load_open_positions()
        closed_records = []
        for pos in open_positions:
            px = current_prices.get(pos.asset, pos.entry_price)
            tr = self.close_single_position(pos.position_id, px, reason="Emergency Flatten")
            if tr:
                closed_records.append(tr)
        return closed_records

    def close_single_position(self, pos_id: str, exit_price: float, reason: str = "Manual Close") -> Optional[TradeRecord]:
        """Liquidates a single open position at specified exit price."""
        open_positions = [p for p in self.storage.load_open_positions() if p.position_id == pos_id]
        if not open_positions:
            return None
        pos = open_positions[0]
        spec = ASSET_SPECS[pos.asset]
        friction = spec['commission'] + (spec['slippage_ticks'] * spec['tick_size'] * spec['point_value'])
        is_long = pos.direction == 'LONG'
        pts = (exit_price - pos.entry_price) if is_long else (pos.entry_price - exit_price)
        dollar_pnl = (pts * spec['point_value']) - friction
        outcome = "MANUAL_EXIT" if abs(dollar_pnl) < 1e-4 else ("WIN" if dollar_pnl > 0 else "LOSS")
        self.storage.update_account_balance(dollar_pnl)
        now_str = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
        tr = TradeRecord(
            trade_id=pos.position_id,
            asset=pos.asset,
            session="MANUAL",
            direction=pos.direction,
            entry_time=pos.entry_time.strftime('%Y-%m-%d %H:%M:%S'),
            entry_price=pos.entry_price,
            exit_time=now_str,
            exit_price=exit_price,
            risk_pts=abs(pos.entry_price - pos.initial_stop_loss),
            pnl_pts=pts,
            dollar_pnl=dollar_pnl,
            outcome=outcome,
            ai_reasoning=f"Position liquidated on demand via Dashboard ({reason})."
        )
        self.storage.record_closed_trade(tr)
        self._remove_position(pos.position_id)
        close_log = self.advisor.explain_trade_closure(pos, exit_price, pts, dollar_pnl, outcome)
        self.storage.log_ai_thought(close_log)
        return tr

