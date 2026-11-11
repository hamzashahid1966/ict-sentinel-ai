"""
ICT Sentinel AI - Persistent SQLite Storage Engine (With Adaptive Memory)
Ensures atomic state recovery, trade logging, episodic memory, and learned weights.
"""

import os
import sqlite3
import datetime
import json
import threading
from typing import List, Optional, Dict, Any
from .config import DB_PATH, INITIAL_CAPITAL
from .models import Position, TradeRecord, AccountState, AILogEntry

class StorageEngine:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = os.path.abspath(db_path)
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._local = threading.local()
        self._lock = threading.Lock()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Returns a thread-local persistent connection with WAL mode and high busy timeout."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(
                self.db_path,
                timeout=30.0,
                check_same_thread=False
            )
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA synchronous = NORMAL;")
            conn.execute("PRAGMA busy_timeout = 30000;")
            self._local.conn = conn
        return self._local.conn

    def _init_db(self):
        with self._lock:
            conn = self._get_connection()
            with conn:
                cursor = conn.cursor()
                # 1. Account Table
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS account (
                    account_id TEXT PRIMARY KEY,
                    balance REAL,
                    peak_balance REAL,
                    realized_pnl REAL,
                    max_drawdown_dollars REAL,
                    max_drawdown_pct REAL,
                    updated_at TEXT
                )
                """)

                # 2. Open Positions Table
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS positions (
                    position_id TEXT PRIMARY KEY,
                    asset TEXT,
                    direction TEXT,
                    quantity INTEGER,
                    entry_price REAL,
                    entry_time TEXT,
                    initial_stop_loss REAL,
                    active_trailing_stop REAL,
                    target_center_mass REAL,
                    target_head_shot REAL,
                    center_mass_filled INTEGER,
                    head_shot_filled INTEGER,
                    realized_pnl REAL,
                    status TEXT,
                    defensive_shields TEXT
                )
                """)

                # 3. Trade History Table
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS trade_history (
                    trade_id TEXT PRIMARY KEY,
                    asset TEXT,
                    session TEXT,
                    direction TEXT,
                    entry_time TEXT,
                    entry_price REAL,
                    exit_time TEXT,
                    exit_price REAL,
                    risk_pts REAL,
                    pnl_pts REAL,
                    dollar_pnl REAL,
                    outcome TEXT,
                    ai_reasoning TEXT
                )
                """)

                # 4. AI Reasoning Log Table
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS ai_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    asset TEXT,
                    session TEXT,
                    category TEXT,
                    message TEXT,
                    reasoning TEXT
                )
                """)

                # 5. Adaptive Memory: Trade Episodes Table
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS trade_episodes (
                    episode_id TEXT PRIMARY KEY,
                    asset TEXT,
                    session TEXT,
                    day_of_week TEXT,
                    direction TEXT,
                    array_type TEXT,
                    risk_pts REAL,
                    outcome TEXT,
                    dollar_pnl REAL,
                    created_at TEXT
                )
                """)

                # 6. Adaptive Memory: Learned Reflections Table
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS memory_reflections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    asset TEXT,
                    session TEXT,
                    reflection_type TEXT,
                    lesson TEXT,
                    action_taken TEXT
                )
                """)

                # 7. Adaptive Memory: Dynamic Weights Table
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS adaptive_weights (
                    key_pair TEXT PRIMARY KEY,
                    asset TEXT,
                    session TEXT,
                    wins INTEGER,
                    losses INTEGER,
                    quality_score REAL,
                    status TEXT,
                    consecutive_losses INTEGER,
                    updated_at TEXT
                )
                """)

                # 8. Cross-Session Debriefs Table
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS session_debriefs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_name TEXT,
                    date TEXT,
                    session_high REAL,
                    session_low REAL,
                    asian_sweep_type TEXT,
                    trades_taken INTEGER,
                    net_dollar_pnl REAL,
                    cross_session_bias TEXT,
                    ai_debrief_summary TEXT,
                    created_at TEXT,
                    UNIQUE(session_name, date)
                )
                """)

                # Defensive migrations for active position and history extensions
                for col_sql in [
                    "ALTER TABLE positions ADD COLUMN defending_fvg_ce REAL",
                    "ALTER TABLE positions ADD COLUMN target_liquidity_pool TEXT",
                    "ALTER TABLE positions ADD COLUMN invalidation_reason TEXT",
                    "ALTER TABLE positions ADD COLUMN session_origin TEXT",
                    "ALTER TABLE trade_history ADD COLUMN target_tp1_price REAL",
                    "ALTER TABLE trade_history ADD COLUMN target_tp2_price REAL",
                    "ALTER TABLE trade_history ADD COLUMN invalidation_reason TEXT",
                    "ALTER TABLE trade_history ADD COLUMN target_liquidity_pool TEXT"
                ]:
                    try:
                        cursor.execute(col_sql)
                    except sqlite3.OperationalError:
                        pass

                # Seed default account if empty
                cursor.execute("SELECT COUNT(*) as count FROM account WHERE account_id = 'primary'")
                row = cursor.fetchone()
                if row['count'] == 0:
                    now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
                    cursor.execute("""
                    INSERT INTO account (account_id, balance, peak_balance, realized_pnl, max_drawdown_dollars, max_drawdown_pct, updated_at)
                    VALUES ('primary', ?, ?, 0.0, 0.0, 0.0, ?)
                    """, (INITIAL_CAPITAL, INITIAL_CAPITAL, now_str))

    def close(self):
        """Closes thread-local connection and releases lock files."""
        with self._lock:
            if hasattr(self._local, "conn") and self._local.conn is not None:
                try:
                    self._local.conn.close()
                except Exception:
                    pass
                self._local.conn = None

    def get_account_state(self) -> AccountState:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM account WHERE account_id = 'primary'")
            acc = cursor.fetchone()
            cursor.execute("SELECT COUNT(*) as count FROM positions WHERE status IN ('OPEN', 'PARTIAL')")
            pos_count = cursor.fetchone()['count']

            return AccountState(
                balance=acc['balance'],
                peak_balance=acc['peak_balance'],
                realized_pnl=acc['realized_pnl'],
                unrealized_pnl=0.0,
                max_drawdown_dollars=acc['max_drawdown_dollars'],
                max_drawdown_pct=acc['max_drawdown_pct'],
                open_positions_count=pos_count
            )

    def update_account_balance(self, dollar_pnl: float):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT balance, peak_balance, realized_pnl, max_drawdown_dollars FROM account WHERE account_id = 'primary'")
            acc = cursor.fetchone()

            new_balance = acc['balance'] + dollar_pnl
            new_peak = max(acc['peak_balance'], new_balance)
            new_realized = acc['realized_pnl'] + dollar_pnl
            current_dd = new_peak - new_balance
            new_max_dd = max(acc['max_drawdown_dollars'], current_dd)
            new_max_dd_pct = (new_max_dd / new_peak) * 100.0 if new_peak > 0 else 0.0
            now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()

            cursor.execute("""
            UPDATE account
            SET balance = ?, peak_balance = ?, realized_pnl = ?, max_drawdown_dollars = ?, max_drawdown_pct = ?, updated_at = ?
            WHERE account_id = 'primary'
            """, (new_balance, new_peak, new_realized, new_max_dd, new_max_dd_pct, now_str))
            conn.commit()

    def save_position(self, pos: Position):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            shields_json = json.dumps(pos.defensive_shields)
            cursor.execute("""
            INSERT OR REPLACE INTO positions (
                position_id, asset, direction, quantity, entry_price, entry_time,
                initial_stop_loss, active_trailing_stop, target_center_mass, target_head_shot,
                center_mass_filled, head_shot_filled, realized_pnl, status, defensive_shields,
                defending_fvg_ce, target_liquidity_pool, invalidation_reason, session_origin
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                pos.position_id, pos.asset, pos.direction, pos.quantity, pos.entry_price,
                pos.entry_time.isoformat(), pos.initial_stop_loss, pos.active_trailing_stop,
                pos.target_center_mass, pos.target_head_shot, 1 if pos.center_mass_filled else 0,
                1 if pos.head_shot_filled else 0, pos.realized_pnl, pos.status, shields_json,
                pos.defending_fvg_ce, pos.target_liquidity_pool, pos.invalidation_reason, pos.session_origin
            ))
            conn.commit()

    def load_open_positions(self) -> List[Position]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM positions WHERE status IN ('OPEN', 'PARTIAL')")
            rows = cursor.fetchall()
            positions = []
            for r in rows:
                shields = json.loads(r['defensive_shields']) if r['defensive_shields'] else []
                pos = Position(
                    position_id=r['position_id'],
                    asset=r['asset'],
                    direction=r['direction'],
                    quantity=r['quantity'],
                    entry_price=r['entry_price'],
                    entry_time=datetime.datetime.fromisoformat(r['entry_time']),
                    initial_stop_loss=r['initial_stop_loss'],
                    active_trailing_stop=r['active_trailing_stop'],
                    target_center_mass=r['target_center_mass'],
                    target_head_shot=r['target_head_shot'],
                    center_mass_filled=bool(r['center_mass_filled']),
                    head_shot_filled=bool(r['head_shot_filled']),
                    realized_pnl=r['realized_pnl'],
                    status=r['status'],
                    defensive_shields=shields,
                    defending_fvg_ce=r['defending_fvg_ce'] if 'defending_fvg_ce' in r.keys() else None,
                    target_liquidity_pool=r['target_liquidity_pool'] if 'target_liquidity_pool' in r.keys() else None,
                    invalidation_reason=r['invalidation_reason'] if 'invalidation_reason' in r.keys() else None,
                    session_origin=r['session_origin'] if 'session_origin' in r.keys() else None
                )
                positions.append(pos)
            return positions

    def record_closed_trade(self, tr: TradeRecord):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT OR REPLACE INTO trade_history (
                trade_id, asset, session, direction, entry_time, entry_price,
                exit_time, exit_price, risk_pts, pnl_pts, dollar_pnl, outcome, ai_reasoning,
                target_tp1_price, target_tp2_price, invalidation_reason, target_liquidity_pool
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                tr.trade_id, tr.asset, tr.session, tr.direction, tr.entry_time,
                tr.entry_price, tr.exit_time, tr.exit_price, tr.risk_pts,
                tr.pnl_pts, tr.dollar_pnl, tr.outcome, tr.ai_reasoning,
                tr.target_tp1_price, tr.target_tp2_price, tr.invalidation_reason, tr.target_liquidity_pool
            ))
            cursor.execute("UPDATE positions SET status = 'CLOSED' WHERE position_id = ?", (tr.trade_id,))
            conn.commit()

    def record_session_debrief(self, debrief):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT OR REPLACE INTO session_debriefs (
                session_name, date, session_high, session_low, asian_sweep_type,
                trades_taken, net_dollar_pnl, cross_session_bias, ai_debrief_summary, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                debrief.session_name, debrief.date, debrief.session_high, debrief.session_low,
                debrief.asian_sweep_type, debrief.trades_taken, debrief.net_dollar_pnl,
                debrief.cross_session_bias, debrief.ai_debrief_summary, debrief.created_at
            ))
            conn.commit()

    def get_latest_session_debriefs(self, limit: int = 10) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM session_debriefs ORDER BY id DESC LIMIT ?", (limit,))
            return [dict(r) for r in cursor.fetchall()]

    def get_latest_session_debrief(self, session_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if session_name:
                cursor.execute("SELECT * FROM session_debriefs WHERE session_name = ? ORDER BY id DESC LIMIT 1", (session_name,))
            else:
                cursor.execute("SELECT * FROM session_debriefs ORDER BY id DESC LIMIT 1")
            row = cursor.fetchone()
            return dict(row) if row else None

    def log_ai_thought(self, entry: AILogEntry):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO ai_logs (timestamp, asset, session, category, message, reasoning)
            VALUES (?, ?, ?, ?, ?, ?)
            """, (entry.timestamp, entry.asset, entry.session, entry.category, entry.message, entry.reasoning))
            conn.commit()

    def get_recent_ai_logs(self, limit: int = 10) -> List[AILogEntry]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM ai_logs ORDER BY id DESC LIMIT ?", (limit,))
            rows = cursor.fetchall()
            logs = []
            for r in rows:
                logs.append(AILogEntry(
                    timestamp=r['timestamp'],
                    asset=r['asset'],
                    session=r['session'],
                    category=r['category'],
                    message=r['message'],
                    reasoning=r['reasoning']
                ))
            return logs

    def get_trade_history(self, limit: int = 50) -> List[TradeRecord]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM trade_history ORDER BY rowid DESC LIMIT ?", (limit,))
            rows = cursor.fetchall()
            trades = []
            for r in rows:
                trades.append(TradeRecord(
                    trade_id=r['trade_id'],
                    asset=r['asset'],
                    session=r['session'],
                    direction=r['direction'],
                    entry_time=r['entry_time'],
                    entry_price=r['entry_price'],
                    exit_time=r['exit_time'],
                    exit_price=r['exit_price'],
                    risk_pts=r['risk_pts'],
                    pnl_pts=r['pnl_pts'],
                    dollar_pnl=r['dollar_pnl'],
                    outcome=r['outcome'],
                    ai_reasoning=r['ai_reasoning'],
                    target_tp1_price=r['target_tp1_price'] if 'target_tp1_price' in r.keys() else None,
                    target_tp2_price=r['target_tp2_price'] if 'target_tp2_price' in r.keys() else None,
                    invalidation_reason=r['invalidation_reason'] if 'invalidation_reason' in r.keys() else None,
                    target_liquidity_pool=r['target_liquidity_pool'] if 'target_liquidity_pool' in r.keys() else None
                ))
            return trades

    # ---------------- ADAPTIVE MEMORY METHODS ----------------
    def record_episode(self, ep_id: str, asset: str, session: str, day_name: str, direction: str, array_type: str, risk_pts: float, outcome: str, dollar_pnl: float):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
            cursor.execute("""
            INSERT OR REPLACE INTO trade_episodes (
                episode_id, asset, session, day_of_week, direction, array_type, risk_pts, outcome, dollar_pnl, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (ep_id, asset, session, day_name, direction, array_type, risk_pts, outcome, dollar_pnl, now_str))
            conn.commit()

    def record_reflection(self, asset: str, session: str, ref_type: str, lesson: str, action: str):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            now_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            cursor.execute("""
            INSERT INTO memory_reflections (timestamp, asset, session, reflection_type, lesson, action_taken)
            VALUES (?, ?, ?, ?, ?, ?)
            """, (now_str, asset, session, ref_type, lesson, action))
            conn.commit()

    def get_recent_reflections(self, limit: int = 5) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM memory_reflections ORDER BY id DESC LIMIT ?", (limit,))
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    def update_adaptive_weight(self, asset: str, session: str, win: bool, quality_score: float, consecutive_losses: int, status: str):
        key_pair = f"{asset}::{session}"
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT wins, losses FROM adaptive_weights WHERE key_pair = ?", (key_pair,))
            row = cursor.fetchone()
            wins = (row['wins'] + (1 if win else 0)) if row else (1 if win else 0)
            losses = (row['losses'] + (0 if win else 1)) if row else (0 if win else 1)
            now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()

            cursor.execute("""
            INSERT OR REPLACE INTO adaptive_weights (
                key_pair, asset, session, wins, losses, quality_score, status, consecutive_losses, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (key_pair, asset, session, wins, losses, quality_score, status, consecutive_losses, now_str))
            conn.commit()

    def reset_account(self, initial_capital: float = INITIAL_CAPITAL):
        """Resets the account to initial seed capital and clears all positions and logs."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
            cursor.execute("""
            UPDATE account 
            SET balance = ?, peak_balance = ?, realized_pnl = 0.0, max_drawdown_dollars = 0.0, max_drawdown_pct = 0.0, updated_at = ?
            WHERE account_id = 'primary'
            """, (initial_capital, initial_capital, now_str))
            cursor.execute("DELETE FROM positions")
            cursor.execute("DELETE FROM trade_history")
            cursor.execute("DELETE FROM ai_logs")
            cursor.execute("DELETE FROM trade_episodes")
            cursor.execute("DELETE FROM memory_reflections")
            cursor.execute("DELETE FROM adaptive_weights")
            conn.commit()

    def get_adaptive_weight(self, asset: str, session: str) -> Optional[Dict[str, Any]]:
        key_pair = f"{asset}::{session}"
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM adaptive_weights WHERE key_pair = ?", (key_pair,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_all_adaptive_weights(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM adaptive_weights ORDER BY quality_score DESC")
            return [dict(r) for r in cursor.fetchall()]
