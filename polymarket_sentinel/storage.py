"""
Polymarket Sentinel Storage Engine.
Thread-safe SQLite storage for market states, historical memory, evidence, forecasts, and paper trading.
"""

import sqlite3
import threading
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

from .config import DB_PATH, INITIAL_PAPER_CAPITAL
from .models import (
    Market, MarketSnapshot, Entity, EntityFact, Evidence,
    Prediction, PaperPosition, PaperTrade, GatewayLog, is_market_expired
)


class PolymarketStorage:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self.lock = threading.Lock()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA busy_timeout = 30000;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        return conn

    def _init_db(self):
        with self.lock:
            conn = self._get_connection()
            cur = conn.cursor()

            # 1. Markets
            cur.execute("""
            CREATE TABLE IF NOT EXISTS pm_markets (
                id TEXT PRIMARY KEY,
                condition_id TEXT,
                question TEXT NOT NULL,
                slug TEXT,
                category TEXT,
                end_date TEXT,
                volume_24h REAL DEFAULT 0.0,
                clob_token_yes TEXT,
                clob_token_no TEXT,
                price_yes REAL DEFAULT 0.5,
                price_no REAL DEFAULT 0.5,
                status TEXT DEFAULT 'active',
                resolution_source TEXT,
                created_at TEXT
            );
            """)

            # 2. Market Snapshots
            cur.execute("""
            CREATE TABLE IF NOT EXISTS pm_market_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                market_id TEXT,
                price_yes REAL,
                price_no REAL,
                volume_24h REAL,
                timestamp TEXT,
                FOREIGN KEY (market_id) REFERENCES pm_markets(id)
            );
            """)

            # 3. Entities
            cur.execute("""
            CREATE TABLE IF NOT EXISTS pm_entities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                entity_type TEXT NOT NULL,
                summary TEXT,
                updated_at TEXT
            );
            """)

            # 4. Entity Facts (Long-term Entity Memory)
            cur.execute("""
            CREATE TABLE IF NOT EXISTS pm_entity_facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_id INTEGER,
                fact_key TEXT NOT NULL,
                fact_value TEXT NOT NULL,
                source TEXT,
                updated_at TEXT,
                FOREIGN KEY (entity_id) REFERENCES pm_entities(id)
            );
            """)

            # 5. Evidence (Articles, filings, sources)
            cur.execute("""
            CREATE TABLE IF NOT EXISTS pm_evidence (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_url TEXT,
                source_name TEXT,
                title TEXT,
                published_at TEXT,
                summary TEXT,
                credibility_score REAL DEFAULT 0.8,
                content_hash TEXT UNIQUE
            );
            """)

            # 6. Market Evidence Association
            cur.execute("""
            CREATE TABLE IF NOT EXISTS pm_market_evidence_link (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                market_id TEXT,
                evidence_id INTEGER,
                relevance_score REAL DEFAULT 1.0,
                sentiment_impact REAL DEFAULT 0.0,
                created_at TEXT,
                FOREIGN KEY (market_id) REFERENCES pm_markets(id),
                FOREIGN KEY (evidence_id) REFERENCES pm_evidence(id),
                UNIQUE(market_id, evidence_id)
            );
            """)

            # 7. Predictions (Immutable Forecast Revision History)
            cur.execute("""
            CREATE TABLE IF NOT EXISTS pm_predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                market_id TEXT,
                forecast_probability REAL NOT NULL,
                market_probability REAL NOT NULL,
                edge REAL NOT NULL,
                confidence_score REAL DEFAULT 0.7,
                reasoning TEXT,
                model_used TEXT,
                created_at TEXT,
                FOREIGN KEY (market_id) REFERENCES pm_markets(id)
            );
            """)

            # 8. Paper Trading Account
            cur.execute("""
            CREATE TABLE IF NOT EXISTS pm_paper_account (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                balance REAL DEFAULT 500.0,
                peak_balance REAL DEFAULT 500.0,
                realized_pnl REAL DEFAULT 0.0,
                updated_at TEXT
            );
            """)

            # Seed account if empty
            cur.execute("SELECT COUNT(*) FROM pm_paper_account;")
            if cur.fetchone()[0] == 0:
                now_iso = datetime.now(timezone.utc).isoformat()
                cur.execute(
                    "INSERT INTO pm_paper_account (balance, peak_balance, realized_pnl, updated_at) VALUES (?, ?, 0.0, ?);",
                    (INITIAL_PAPER_CAPITAL, INITIAL_PAPER_CAPITAL, now_iso)
                )

            # 9. Paper Positions
            cur.execute("""
            CREATE TABLE IF NOT EXISTS pm_paper_positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                market_id TEXT,
                outcome TEXT NOT NULL,
                shares REAL NOT NULL,
                avg_entry_price REAL NOT NULL,
                cost_basis REAL NOT NULL,
                current_price REAL NOT NULL,
                current_value REAL NOT NULL,
                unrealized_pnl REAL DEFAULT 0.0,
                status TEXT DEFAULT 'OPEN',
                reason TEXT DEFAULT '',
                created_at TEXT,
                FOREIGN KEY (market_id) REFERENCES pm_markets(id)
            );
            """)

            # 10. Paper Trades
            cur.execute("""
            CREATE TABLE IF NOT EXISTS pm_paper_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                market_id TEXT,
                position_id INTEGER,
                action TEXT NOT NULL,
                outcome TEXT NOT NULL,
                shares REAL NOT NULL,
                price REAL NOT NULL,
                dollar_value REAL NOT NULL,
                realized_pnl REAL DEFAULT 0.0,
                reason TEXT DEFAULT '',
                timestamp TEXT
            );
            """)

            # Dynamic migration safety for columns added across versions
            for col_sql in [
                "ALTER TABLE pm_paper_positions ADD COLUMN reason TEXT DEFAULT '';",
                "ALTER TABLE pm_paper_trades ADD COLUMN reason TEXT DEFAULT '';",
                "ALTER TABLE pm_markets ADD COLUMN end_date TEXT;"
            ]:
                try:
                    cur.execute(col_sql)
                except sqlite3.OperationalError:
                    pass

            # 11. AI Gateway Usage Logs
            cur.execute("""
            CREATE TABLE IF NOT EXISTS pm_gateway_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider TEXT,
                model TEXT,
                prompt_tokens INTEGER DEFAULT 0,
                completion_tokens INTEGER DEFAULT 0,
                latency_ms REAL DEFAULT 0.0,
                success INTEGER DEFAULT 1,
                error_message TEXT,
                created_at TEXT
            );
            """)

            # 12. Real-time Activity Log
            cur.execute("""
            CREATE TABLE IF NOT EXISTS pm_bot_activity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT,
                title TEXT,
                details TEXT,
                level TEXT,
                timestamp TEXT
            );
            """)

            # Migrations for v2 Intelligence Engine
            def _safe_add(tbl, col, def_val):
                try:
                    cur.execute(f"ALTER TABLE {tbl} ADD COLUMN {col} {def_val};")
                except sqlite3.OperationalError:
                    pass

            _safe_add("pm_markets", "qualification_score", "REAL DEFAULT 70.0")
            _safe_add("pm_markets", "qualification_tier", "TEXT DEFAULT 'MONITOR'")
            _safe_add("pm_markets", "resolution_spec", "TEXT DEFAULT ''")
            _safe_add("pm_predictions", "independent_probability", "REAL DEFAULT 0.5")
            _safe_add("pm_predictions", "base_rate", "REAL DEFAULT 0.3")
            _safe_add("pm_predictions", "counterarguments", "TEXT DEFAULT ''")
            _safe_add("pm_predictions", "uncertainty_range_low", "REAL DEFAULT 0.4")
            _safe_add("pm_predictions", "uncertainty_range_high", "REAL DEFAULT 0.6")
            _safe_add("pm_predictions", "recommend_abstain", "INTEGER DEFAULT 0")
            _safe_add("pm_evidence", "source_tier", "INTEGER DEFAULT 3")
            _safe_add("pm_evidence", "is_primary", "INTEGER DEFAULT 0")

            # Dual-Engine & Active Exit Strategy fields
            _safe_add("pm_paper_positions", "strategy_type", "TEXT DEFAULT 'ASYMMETRIC_EDGE'")
            _safe_add("pm_paper_positions", "take_profit_px", "REAL DEFAULT 0.0")
            _safe_add("pm_paper_positions", "stop_loss_px", "REAL DEFAULT 0.0")
            _safe_add("pm_paper_trades", "strategy_type", "TEXT DEFAULT 'ASYMMETRIC_EDGE'")
            _safe_add("pm_paper_trades", "exit_trigger", "TEXT DEFAULT ''")

            conn.commit()
            conn.close()

    # ── Market Operations ─────────────────────────────────────────────
    def upsert_market(self, market: Market):
        with self.lock:
            conn = self._get_connection()
            cur = conn.cursor()
            now_iso = datetime.now(timezone.utc).isoformat()
            effective_status = "closed" if is_market_expired(market.end_date) else market.status
            q_score = getattr(market, 'qualification_score', 70.0)
            q_tier = getattr(market, 'qualification_tier', 'MONITOR')
            r_spec = getattr(market, 'resolution_spec', '')
            cur.execute("""
            INSERT INTO pm_markets (
                id, condition_id, question, slug, category, end_date,
                volume_24h, clob_token_yes, clob_token_no, price_yes, price_no,
                status, resolution_source, created_at,
                qualification_score, qualification_tier, resolution_spec
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                price_yes = excluded.price_yes,
                price_no = excluded.price_no,
                volume_24h = excluded.volume_24h,
                status = excluded.status,
                qualification_score = excluded.qualification_score,
                qualification_tier = excluded.qualification_tier,
                resolution_spec = CASE WHEN excluded.resolution_spec != '' THEN excluded.resolution_spec ELSE pm_markets.resolution_spec END;
            """, (
                market.id, market.condition_id, market.question, market.slug,
                market.category, market.end_date, market.volume_24h,
                market.clob_token_yes, market.clob_token_no, market.price_yes,
                market.price_no, effective_status, market.resolution_source,
                market.created_at or now_iso, q_score, q_tier, r_spec
            ))

            # Record snapshot
            cur.execute("""
            INSERT INTO pm_market_snapshots (market_id, price_yes, price_no, volume_24h, timestamp)
            VALUES (?, ?, ?, ?, ?);
            """, (market.id, market.price_yes, market.price_no, market.volume_24h, now_iso))

            conn.commit()
            conn.close()

    def get_markets(self, limit: int = 50, active_only: bool = True) -> List[Dict[str, Any]]:
        with self.lock:
            conn = self._get_connection()
            cur = conn.cursor()
            now_iso = datetime.now(timezone.utc).isoformat()
            if active_only:
                query = "SELECT * FROM pm_markets WHERE status = 'active' AND (end_date IS NULL OR end_date > ?) ORDER BY volume_24h DESC LIMIT ?"
                cur.execute(query, (now_iso, limit))
            else:
                query = "SELECT * FROM pm_markets ORDER BY volume_24h DESC LIMIT ?"
                cur.execute(query, (limit,))
            rows = [dict(r) for r in cur.fetchall()]
            conn.close()
            return rows

    def get_market_by_id(self, market_id: str) -> Optional[Dict[str, Any]]:
        with self.lock:
            conn = self._get_connection()
            cur = conn.cursor()
            cur.execute("SELECT * FROM pm_markets WHERE id = ? OR condition_id = ? OR slug = ?", (market_id, market_id, market_id))
            row = cur.fetchone()
            conn.close()
            return dict(row) if row else None

    # ── Prediction & Forecast Timeline ────────────────────────────────
    def add_prediction(self, pred: Prediction):
        with self.lock:
            conn = self._get_connection()
            cur = conn.cursor()
            now_iso = datetime.now(timezone.utc).isoformat()
            cur.execute("""
            INSERT INTO pm_predictions (
                market_id, forecast_probability, market_probability,
                edge, confidence_score, reasoning, model_used, created_at,
                independent_probability, base_rate, counterarguments,
                uncertainty_range_low, uncertainty_range_high, recommend_abstain
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                pred.market_id, pred.forecast_probability, pred.market_probability,
                pred.edge, pred.confidence_score, pred.reasoning,
                pred.model_used, pred.created_at or now_iso,
                getattr(pred, 'independent_probability', 0.5),
                getattr(pred, 'base_rate', 0.3),
                getattr(pred, 'counterarguments', ''),
                getattr(pred, 'uncertainty_range_low', 0.4),
                getattr(pred, 'uncertainty_range_high', 0.6),
                1 if getattr(pred, 'recommend_abstain', False) else 0
            ))
            conn.commit()
            conn.close()

    def get_market_prediction_timeline(self, market_id: str) -> List[Dict[str, Any]]:
        with self.lock:
            conn = self._get_connection()
            cur = conn.cursor()
            cur.execute("""
            SELECT * FROM pm_predictions
            WHERE market_id = ?
            ORDER BY id ASC;
            """, (market_id,))
            rows = [dict(r) for r in cur.fetchall()]
            conn.close()
            return rows

    def get_latest_prediction(self, market_id: str) -> Optional[Dict[str, Any]]:
        with self.lock:
            conn = self._get_connection()
            cur = conn.cursor()
            cur.execute("""
            SELECT * FROM pm_predictions
            WHERE market_id = ?
            ORDER BY id DESC LIMIT 1;
            """, (market_id,))
            row = cur.fetchone()
            conn.close()
            return dict(row) if row else None

    # ── Evidence & Memory Storage ─────────────────────────────────────
    def add_evidence(self, ev: Evidence) -> int:
        with self.lock:
            conn = self._get_connection()
            cur = conn.cursor()
            try:
                cur.execute("""
                INSERT INTO pm_evidence (source_url, source_name, title, published_at, summary, credibility_score, content_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?);
                """, (ev.source_url, ev.source_name, ev.title, ev.published_at, ev.summary, ev.credibility_score, ev.content_hash))
                ev_id = cur.lastrowid
                conn.commit()
            except sqlite3.IntegrityError:
                # Content already exists (deduplication)
                cur.execute("SELECT id FROM pm_evidence WHERE content_hash = ?", (ev.content_hash,))
                row = cur.fetchone()
                ev_id = row[0] if row else -1
            conn.close()
            return ev_id

    def link_market_evidence(self, market_id: str, evidence_id: int, relevance: float = 1.0, sentiment: float = 0.0):
        with self.lock:
            conn = self._get_connection()
            cur = conn.cursor()
            now_iso = datetime.now(timezone.utc).isoformat()
            cur.execute("""
            INSERT OR IGNORE INTO pm_market_evidence_link (market_id, evidence_id, relevance_score, sentiment_impact, created_at)
            VALUES (?, ?, ?, ?, ?);
            """, (market_id, evidence_id, relevance, sentiment, now_iso))
            conn.commit()
            conn.close()

    def get_market_evidence(self, market_id: str) -> List[Dict[str, Any]]:
        with self.lock:
            conn = self._get_connection()
            cur = conn.cursor()
            cur.execute("""
            SELECT e.*, l.relevance_score, l.sentiment_impact
            FROM pm_evidence e
            JOIN pm_market_evidence_link l ON e.id = l.evidence_id
            WHERE l.market_id = ?
            ORDER BY e.id DESC;
            """, (market_id,))
            rows = [dict(r) for r in cur.fetchall()]
            conn.close()
            return rows

    def get_all_recent_evidence(self, limit: int = 25) -> List[Dict[str, Any]]:
        with self.lock:
            conn = self._get_connection()
            cur = conn.cursor()
            cur.execute("""
            SELECT e.*, l.market_id, l.relevance_score, l.sentiment_impact,
                   m.question as market_question, m.category as market_category
            FROM pm_evidence e
            LEFT JOIN pm_market_evidence_link l ON e.id = l.evidence_id
            LEFT JOIN pm_markets m ON l.market_id = m.id
            ORDER BY e.id DESC LIMIT ?;
            """, (limit,))
            rows = [dict(r) for r in cur.fetchall()]
            conn.close()
            return rows

    # ── Entity Knowledge Base ─────────────────────────────────────────
    def upsert_entity(self, name: str, entity_type: str, summary: str) -> int:
        with self.lock:
            conn = self._get_connection()
            cur = conn.cursor()
            now_iso = datetime.now(timezone.utc).isoformat()
            cur.execute("""
            INSERT INTO pm_entities (name, entity_type, summary, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                summary = excluded.summary,
                updated_at = excluded.updated_at;
            """, (name, entity_type, summary, now_iso))
            conn.commit()
            cur.execute("SELECT id FROM pm_entities WHERE name = ?", (name,))
            ent_id = cur.fetchone()[0]
            conn.close()
            return ent_id

    def add_entity_fact(self, entity_id: int, fact_key: str, fact_value: str, source: str):
        with self.lock:
            conn = self._get_connection()
            cur = conn.cursor()
            now_iso = datetime.now(timezone.utc).isoformat()
            cur.execute("""
            INSERT INTO pm_entity_facts (entity_id, fact_key, fact_value, source, updated_at)
            VALUES (?, ?, ?, ?, ?);
            """, (entity_id, fact_key, fact_value, source, now_iso))
            conn.commit()
            conn.close()

    def get_entity_facts(self, entity_name: str) -> List[Dict[str, Any]]:
        with self.lock:
            conn = self._get_connection()
            cur = conn.cursor()
            cur.execute("""
            SELECT f.*, e.name as entity_name, e.entity_type
            FROM pm_entity_facts f
            JOIN pm_entities e ON f.entity_id = e.id
            WHERE e.name LIKE ?
            ORDER BY f.id DESC;
            """, (f"%{entity_name}%",))
            rows = [dict(r) for r in cur.fetchall()]
            conn.close()
            return rows

    # ── Paper Trading Portfolio ───────────────────────────────────────
    def get_account_state(self) -> Dict[str, Any]:
        with self.lock:
            conn = self._get_connection()
            cur = conn.cursor()
            cur.execute("SELECT * FROM pm_paper_account ORDER BY id ASC LIMIT 1;")
            row = cur.fetchone()
            conn.close()
            if row:
                return dict(row)
            return {"balance": INITIAL_PAPER_CAPITAL, "peak_balance": INITIAL_PAPER_CAPITAL, "realized_pnl": 0.0}

    def update_account_balance(self, balance_delta: float, realized_delta: float = 0.0):
        with self.lock:
            conn = self._get_connection()
            cur = conn.cursor()
            now_iso = datetime.now(timezone.utc).isoformat()
            cur.execute("SELECT balance, peak_balance, realized_pnl FROM pm_paper_account ORDER BY id ASC LIMIT 1;")
            row = cur.fetchone()
            if row:
                new_bal = row["balance"] + balance_delta
                new_peak = max(row["peak_balance"], new_bal)
                new_realized = row["realized_pnl"] + realized_delta
                cur.execute("""
                UPDATE pm_paper_account SET balance = ?, peak_balance = ?, realized_pnl = ?, updated_at = ?
                WHERE id = 1;
                """, (new_bal, new_peak, new_realized, now_iso))
            conn.commit()
            conn.close()

    def save_paper_position(self, pos: PaperPosition) -> int:
        with self.lock:
            conn = self._get_connection()
            cur = conn.cursor()
            now_iso = datetime.now(timezone.utc).isoformat()
            strategy_type = getattr(pos, 'strategy_type', 'ASYMMETRIC_EDGE')
            tp_px = getattr(pos, 'take_profit_px', 0.0)
            sl_px = getattr(pos, 'stop_loss_px', 0.0)
            cur.execute("""
            INSERT INTO pm_paper_positions (
                market_id, outcome, shares, avg_entry_price, cost_basis,
                current_price, current_value, unrealized_pnl, status, reason, created_at,
                strategy_type, take_profit_px, stop_loss_px
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                pos.market_id, pos.outcome, pos.shares, pos.avg_entry_price, pos.cost_basis,
                pos.current_price, pos.current_value, pos.unrealized_pnl, pos.status, pos.reason, pos.created_at or now_iso,
                strategy_type, tp_px, sl_px
            ))
            pos_id = cur.lastrowid
            conn.commit()
            conn.close()
            return pos_id

    def get_open_positions(self) -> List[Dict[str, Any]]:
        with self.lock:
            conn = self._get_connection()
            cur = conn.cursor()
            cur.execute("""
            SELECT p.*, m.question, m.slug, m.category, m.end_date, m.resolution_source
            FROM pm_paper_positions p
            JOIN pm_markets m ON p.market_id = m.id
            WHERE p.status = 'OPEN'
            ORDER BY p.id DESC;
            """)
            rows = [dict(r) for r in cur.fetchall()]
            conn.close()
            return rows

    def record_paper_trade(self, trade: PaperTrade):
        with self.lock:
            conn = self._get_connection()
            cur = conn.cursor()
            now_iso = datetime.now(timezone.utc).isoformat()
            strategy_type = getattr(trade, 'strategy_type', 'ASYMMETRIC_EDGE')
            exit_trigger = getattr(trade, 'exit_trigger', '')
            cur.execute("""
            INSERT INTO pm_paper_trades (
                market_id, position_id, action, outcome, shares, price, dollar_value, realized_pnl, reason, timestamp,
                strategy_type, exit_trigger
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                trade.market_id, trade.position_id, trade.action, trade.outcome,
                trade.shares, trade.price, trade.dollar_value, trade.realized_pnl, trade.reason,
                trade.timestamp or now_iso, strategy_type, exit_trigger
            ))
            conn.commit()
            conn.close()

    def get_recent_paper_trades(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self.lock:
            conn = self._get_connection()
            cur = conn.cursor()
            cur.execute("""
            SELECT t.*, m.question, m.end_date
            FROM pm_paper_trades t
            JOIN pm_markets m ON t.market_id = m.id
            ORDER BY t.id DESC LIMIT ?;
            """, (limit,))
            rows = [dict(r) for r in cur.fetchall()]
            conn.close()
            return rows

    def reset_paper_account(self):
        with self.lock:
            conn = self._get_connection()
            cur = conn.cursor()
            now_iso = datetime.now(timezone.utc).isoformat()
            cur.execute("UPDATE pm_paper_account SET balance = ?, peak_balance = ?, realized_pnl = 0.0, updated_at = ?;",
                        (INITIAL_PAPER_CAPITAL, INITIAL_PAPER_CAPITAL, now_iso))
            cur.execute("DELETE FROM pm_paper_positions;")
            cur.execute("DELETE FROM pm_paper_trades;")
            conn.commit()
            conn.close()

    def reset_all_data(self):
        with self.lock:
            conn = self._get_connection()
            try:
                cur = conn.cursor()
                now_iso = datetime.now(timezone.utc).isoformat()
                cur.execute("UPDATE pm_paper_account SET balance = ?, peak_balance = ?, realized_pnl = 0.0, updated_at = ?;",
                            (INITIAL_PAPER_CAPITAL, INITIAL_PAPER_CAPITAL, now_iso))
                cur.execute("DELETE FROM pm_paper_positions;")
                cur.execute("DELETE FROM pm_paper_trades;")
                cur.execute("DELETE FROM pm_evidence;")
                cur.execute("DELETE FROM pm_market_evidence_link;")
                cur.execute("DELETE FROM pm_predictions;")
                cur.execute("DELETE FROM pm_market_snapshots;")
                cur.execute("DELETE FROM pm_bot_activity;")
                conn.commit()
            finally:
                conn.close()

    # ── Gateway Logs & Bot Activity ───────────────────────────────────
    def log_gateway_call(self, log: GatewayLog):
        with self.lock:
            conn = self._get_connection()
            cur = conn.cursor()
            now_iso = datetime.now(timezone.utc).isoformat()
            cur.execute("""
            INSERT INTO pm_gateway_logs (provider, model, prompt_tokens, completion_tokens, latency_ms, success, error_message, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """, (log.provider, log.model, log.prompt_tokens, log.completion_tokens, log.latency_ms, 1 if log.success else 0, log.error_message, log.created_at or now_iso))
            conn.commit()
            conn.close()

    def get_gateway_stats(self) -> Dict[str, Any]:
        with self.lock:
            conn = self._get_connection()
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) as total_calls, SUM(success) as success_calls, AVG(latency_ms) as avg_latency FROM pm_gateway_logs;")
            row = cur.fetchone()
            conn.close()
            if row:
                return {
                    "total_calls": row["total_calls"] or 0,
                    "success_calls": row["success_calls"] or 0,
                    "avg_latency_ms": round(row["avg_latency"] or 0.0, 1)
                }
            return {"total_calls": 0, "success_calls": 0, "avg_latency_ms": 0.0}

    def add_activity(self, category: str, title: str, details: str, level: str = "info"):
        with self.lock:
            conn = self._get_connection()
            cur = conn.cursor()
            now_iso = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
            cur.execute("""
            INSERT INTO pm_bot_activity (category, title, details, level, timestamp)
            VALUES (?, ?, ?, ?, ?);
            """, (category, title, details, level, now_iso))
            conn.commit()
            conn.close()

    def get_recent_activity(self, limit: int = 40) -> List[Dict[str, Any]]:
        with self.lock:
            conn = self._get_connection()
            cur = conn.cursor()
            cur.execute("SELECT * FROM pm_bot_activity ORDER BY id DESC LIMIT ?;", (limit,))
            rows = [dict(r) for r in cur.fetchall()]
            conn.close()
            return rows
