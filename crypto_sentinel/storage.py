"""
Crypto Sentinel AI - SQLite Storage Engine
Thread-safe persistence for Crypto positions, trades, screener candidates, analysis, and activity logs.
"""

import sqlite3
import threading
import time
import json
from typing import List, Optional, Dict, Any, Tuple
from crypto_sentinel.config import (
    CRYPTO_DB_PATH, INITIAL_CAPITAL, DEFAULT_EXECUTION_MODE,
    MAX_DAILY_DRAWDOWN_PCT, STRATEGY_PROFILES, DEFAULT_STRATEGY_PROFILE,
    TOP_PRIME_SYMBOLS, AUTO_QUARANTINE_CONSECUTIVE_LOSSES,
    AUTO_QUARANTINE_MAX_NET_LOSS, AUTO_QUARANTINE_DURATION_HOURS
)
from crypto_sentinel.models import (
    CryptoPosition, CryptoAccount, ScreenerCandidate, AnalysisOpportunity, ActivityLog
)

class CryptoStorageEngine:
    def __init__(self, db_path: str = CRYPTO_DB_PATH):
        self.db_path = db_path
        self._shared_mem_uri = f"file:mem_db_{id(self)}?mode=memory&cache=shared"
        self._persistent_conn = None
        if self.db_path == ":memory:":
            self._persistent_conn = sqlite3.connect(self._shared_mem_uri, timeout=15.0, uri=True)
        self._lock = threading.Lock()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        if self.db_path == ":memory:":
            conn = sqlite3.connect(self._shared_mem_uri, timeout=15.0, uri=True)
        else:
            conn = sqlite3.connect(self.db_path, timeout=15.0)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA synchronous = NORMAL;")
        except sqlite3.OperationalError:
            pass
        return conn

    def _init_db(self):
        with self._lock, self._get_connection() as conn:
            # 1. Account State
            conn.execute("""
                CREATE TABLE IF NOT EXISTS crypto_account (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    balance REAL NOT NULL,
                    peak_balance REAL NOT NULL,
                    realized_pnl REAL NOT NULL,
                    daily_starting_equity REAL NOT NULL,
                    daily_drawdown_pct REAL NOT NULL,
                    is_locked INTEGER NOT NULL DEFAULT 0,
                    mode TEXT NOT NULL DEFAULT 'SIMULATED_PAPER',
                    strategy_profile TEXT NOT NULL DEFAULT 'MODERATE_GROWTH',
                    updated_at REAL NOT NULL
                );
            """)
            try:
                conn.execute("ALTER TABLE crypto_account ADD COLUMN strategy_profile TEXT NOT NULL DEFAULT 'MODERATE_GROWTH';")
            except sqlite3.OperationalError:
                pass

            # 2. Positions Table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS crypto_positions (
                    position_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    engine TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    entry_price REAL NOT NULL,
                    quantity REAL NOT NULL,
                    initial_stop REAL NOT NULL,
                    current_stop REAL NOT NULL,
                    target_1 REAL NOT NULL,
                    target_2 REAL NOT NULL,
                    t1_hit INTEGER NOT NULL DEFAULT 0,
                    defensive_active INTEGER NOT NULL DEFAULT 0,
                    unrealized_pnl REAL NOT NULL DEFAULT 0.0,
                    unrealized_r REAL NOT NULL DEFAULT 0.0,
                    entry_time REAL NOT NULL,
                    status TEXT NOT NULL DEFAULT 'OPEN',
                    exit_price REAL,
                    exit_reason TEXT,
                    exit_time REAL,
                    fees_paid REAL NOT NULL DEFAULT 0.0,
                    is_stagnant INTEGER NOT NULL DEFAULT 0,
                    stagnant_at REAL
                );
            """)
            try:
                conn.execute("ALTER TABLE crypto_positions ADD COLUMN is_stagnant INTEGER NOT NULL DEFAULT 0;")
            except sqlite3.OperationalError:
                pass
            try:
                conn.execute("ALTER TABLE crypto_positions ADD COLUMN stagnant_at REAL;")
            except sqlite3.OperationalError:
                pass

            # 3. Screener Candidates
            conn.execute("""
                CREATE TABLE IF NOT EXISTS crypto_screener (
                    symbol TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    price REAL NOT NULL,
                    change_24h REAL NOT NULL,
                    volume_24h REAL NOT NULL,
                    sector TEXT NOT NULL,
                    why_picked TEXT NOT NULL,
                    score REAL NOT NULL,
                    h1_trend TEXT NOT NULL,
                    volatility_pct REAL NOT NULL,
                    is_active_focus INTEGER NOT NULL DEFAULT 0,
                    updated_at REAL NOT NULL
                );
            """)

            # 4. Analysis Opportunities
            conn.execute("""
                CREATE TABLE IF NOT EXISTS crypto_analysis (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    engine TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    status TEXT NOT NULL,
                    confidence_score REAL NOT NULL,
                    reason TEXT NOT NULL,
                    current_price REAL NOT NULL,
                    stop_loss REAL NOT NULL,
                    target_1 REAL NOT NULL,
                    target_2 REAL NOT NULL,
                    risk_r REAL NOT NULL,
                    sweep_level REAL,
                    fvg_bounds TEXT,
                    timestamp REAL NOT NULL
                );
            """)

            # 5. Activity Logs (Real-time bot explanation feed)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS crypto_activity_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    action TEXT NOT NULL,
                    coin TEXT NOT NULL,
                    detail TEXT NOT NULL,
                    level TEXT NOT NULL DEFAULT 'INFO'
                );
            """)

            # 6. AI Asset Intelligence & Behavioral Memory
            conn.execute("""
                CREATE TABLE IF NOT EXISTS crypto_coin_stats (
                    symbol TEXT PRIMARY KEY,
                    total_trades INTEGER NOT NULL DEFAULT 0,
                    wins INTEGER NOT NULL DEFAULT 0,
                    losses INTEGER NOT NULL DEFAULT 0,
                    win_rate REAL NOT NULL DEFAULT 0.0,
                    gross_pnl REAL NOT NULL DEFAULT 0.0,
                    total_fees REAL NOT NULL DEFAULT 0.0,
                    net_pnl REAL NOT NULL DEFAULT 0.0,
                    consecutive_losses INTEGER NOT NULL DEFAULT 0,
                    is_quarantined INTEGER NOT NULL DEFAULT 0,
                    quarantine_until REAL NOT NULL DEFAULT 0.0,
                    last_trade_at REAL NOT NULL DEFAULT 0.0,
                    debrief TEXT NOT NULL DEFAULT ''
                );
            """)

            # 7. Multi-Timeframe Trade Snapshots & ML Dataset Archive
            conn.execute("""
                CREATE TABLE IF NOT EXISTS crypto_trade_snapshots (
                    snapshot_id TEXT PRIMARY KEY,
                    position_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    engine TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    entry_price REAL NOT NULL,
                    exit_price REAL,
                    gross_pnl REAL DEFAULT 0.0,
                    fees REAL DEFAULT 0.0,
                    net_pnl REAL DEFAULT 0.0,
                    is_win INTEGER DEFAULT 0,
                    exit_reason TEXT,
                    m5_candles_json TEXT,
                    m15_candles_json TEXT,
                    h1_candles_json TEXT,
                    btc_trend TEXT,
                    volatility_pct REAL,
                    ai_debrief TEXT,
                    created_at REAL NOT NULL,
                    closed_at REAL
                );
            """)

            # Seed Account if empty
            cur = conn.cursor()
            cur.execute("SELECT id FROM crypto_account WHERE id = 1;")
            if not cur.fetchone():
                conn.execute("""
                    INSERT INTO crypto_account 
                    (id, balance, peak_balance, realized_pnl, daily_starting_equity, daily_drawdown_pct, is_locked, mode, updated_at)
                    VALUES (1, ?, ?, 0.0, ?, 0.0, 0, ?, ?);
                """, (INITIAL_CAPITAL, INITIAL_CAPITAL, INITIAL_CAPITAL, DEFAULT_EXECUTION_MODE, time.time()))
            conn.commit()

    # --- Account Methods ---
    def get_account(self) -> CryptoAccount:
        with self._lock, self._get_connection() as conn:
            row = conn.execute("SELECT * FROM crypto_account WHERE id = 1;").fetchone()
            # Calculate win rate, gross pnl, fees paid, and net pnl from closed positions
            stats = conn.execute("""
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN (exit_price - entry_price) * (CASE WHEN direction = 'LONG' THEN 1 ELSE -1 END) * quantity > 0 THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN (exit_price - entry_price) * (CASE WHEN direction = 'LONG' THEN 1 ELSE -1 END) * quantity <= 0 THEN 1 ELSE 0 END) as losses,
                    COALESCE(SUM((exit_price - entry_price) * (CASE WHEN direction = 'LONG' THEN 1 ELSE -1 END) * quantity), 0.0) as gross_pnl,
                    COALESCE(SUM(fees_paid), 0.0) as total_fees
                FROM crypto_positions WHERE status = 'CLOSED';
            """).fetchone()

            total = stats['total'] or 0
            wins = stats['wins'] or 0
            losses = stats['losses'] or 0
            win_rate = (wins / total * 100.0) if total > 0 else 0.0
            gross_pnl = round(stats['gross_pnl'] or 0.0, 2)
            total_fees = round(stats['total_fees'] or 0.0, 2)
            net_pnl = round(gross_pnl - total_fees, 2)

            profile = "MODERATE_GROWTH"
            try:
                if 'strategy_profile' in row.keys() and row['strategy_profile']:
                    profile = row['strategy_profile']
            except Exception:
                pass

            return CryptoAccount(
                balance=row['balance'],
                peak_balance=row['peak_balance'],
                realized_pnl=net_pnl,
                daily_starting_equity=row['daily_starting_equity'],
                daily_drawdown_pct=row['daily_drawdown_pct'],
                is_locked=bool(row['is_locked']),
                mode=row['mode'],
                strategy_profile=profile,
                total_trades=total,
                wins=wins,
                losses=losses,
                win_rate_pct=round(win_rate, 1),
                gross_pnl=gross_pnl,
                total_fees=total_fees,
                net_pnl=net_pnl
            )

    def update_account(self, balance: float, realized_pnl_delta: float, mode: Optional[str] = None):
        with self._lock, self._get_connection() as conn:
            row = conn.execute("SELECT * FROM crypto_account WHERE id = 1;").fetchone()
            new_balance = balance
            new_peak = max(row['peak_balance'], new_balance)
            new_realized = row['realized_pnl'] + realized_pnl_delta
            starting_equity = row['daily_starting_equity']
            drawdown_pct = max(0.0, ((starting_equity - new_balance) / starting_equity) * 100.0) if starting_equity > 0 else 0.0

            # Determine max allowed daily drawdown from active profile
            profile_name = row['strategy_profile'] if 'strategy_profile' in row.keys() and row['strategy_profile'] else DEFAULT_STRATEGY_PROFILE
            profile = STRATEGY_PROFILES.get(profile_name, STRATEGY_PROFILES.get(DEFAULT_STRATEGY_PROFILE, {}))
            max_dd = profile.get("max_daily_drawdown_pct", MAX_DAILY_DRAWDOWN_PCT)

            is_locked = 1 if drawdown_pct >= max_dd else 0
            new_mode = mode or row['mode']

            conn.execute("""
                UPDATE crypto_account SET
                    balance = ?, peak_balance = ?, realized_pnl = ?,
                    daily_drawdown_pct = ?, is_locked = ?, mode = ?, updated_at = ?
                WHERE id = 1;
            """, (new_balance, new_peak, new_realized, drawdown_pct, is_locked, new_mode, time.time()))
            conn.commit()

    def sync_testnet_account(self, testnet_balance: float, available_balance: float):
        """
        Synchronizes live Binance Testnet wallet balance with SQLite storage.
        Ensures daily_starting_equity accurately reflects real testnet capital.
        """
        with self._lock, self._get_connection() as conn:
            row = conn.execute("SELECT * FROM crypto_account WHERE id = 1;").fetchone()
            if not row:
                return

            new_balance = round(testnet_balance, 2)
            new_peak = max(row['peak_balance'], new_balance)
            starting_equity = row['daily_starting_equity']

            # If starting equity is default simulated $1,000 or missing, align to real testnet capital
            if starting_equity <= 1000.0 and new_balance > 1000.0:
                starting_equity = new_balance

            drawdown_pct = max(0.0, ((starting_equity - new_balance) / starting_equity) * 100.0) if starting_equity > 0 else 0.0
            profile_name = row['strategy_profile'] if 'strategy_profile' in row.keys() and row['strategy_profile'] else DEFAULT_STRATEGY_PROFILE
            profile = STRATEGY_PROFILES.get(profile_name, STRATEGY_PROFILES.get(DEFAULT_STRATEGY_PROFILE, {}))
            max_dd = profile.get("max_daily_drawdown_pct", MAX_DAILY_DRAWDOWN_PCT)
            is_locked = 1 if drawdown_pct >= max_dd else 0

            conn.execute("""
                UPDATE crypto_account SET
                    balance = ?, peak_balance = ?, daily_starting_equity = ?,
                    daily_drawdown_pct = ?, is_locked = ?, mode = 'BINANCE_TESTNET', updated_at = ?
                WHERE id = 1;
            """, (new_balance, new_peak, starting_equity, drawdown_pct, is_locked, time.time()))
            conn.commit()

    def set_mode(self, mode: str):
        with self._lock, self._get_connection() as conn:
            conn.execute("UPDATE crypto_account SET mode = ?, updated_at = ? WHERE id = 1;", (mode, time.time()))
            conn.commit()

    def set_strategy_profile(self, profile: str):
        with self._lock, self._get_connection() as conn:
            conn.execute("UPDATE crypto_account SET strategy_profile = ?, updated_at = ? WHERE id = 1;", (profile, time.time()))
            conn.commit()

    # --- Position Methods ---
    def save_position(self, pos: CryptoPosition):
        with self._lock, self._get_connection() as conn:
            is_stagnant = 1 if getattr(pos, 'is_stagnant', False) else 0
            stagnant_at = getattr(pos, 'stagnant_at', None)
            conn.execute("""
                INSERT OR REPLACE INTO crypto_positions (
                    position_id, symbol, engine, direction, entry_price, quantity,
                    initial_stop, current_stop, target_1, target_2, t1_hit, defensive_active,
                    unrealized_pnl, unrealized_r, entry_time, status, exit_price, exit_reason, exit_time, fees_paid,
                    is_stagnant, stagnant_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                pos.position_id, pos.symbol, pos.engine, pos.direction, pos.entry_price, pos.quantity,
                pos.initial_stop, pos.current_stop, pos.target_1, pos.target_2, int(pos.t1_hit), int(pos.defensive_active),
                pos.unrealized_pnl, pos.unrealized_r, pos.entry_time, pos.status, pos.exit_price, pos.exit_reason, pos.exit_time, pos.fees_paid,
                is_stagnant, stagnant_at
            ))
            conn.commit()

    def get_open_positions(self) -> List[CryptoPosition]:
        with self._lock, self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM crypto_positions WHERE status IN ('OPEN', 'T1_HIT') ORDER BY entry_time DESC;").fetchall()
            return [self._row_to_position(r) for r in rows]

    def get_closed_positions(self, limit: int = 20) -> List[CryptoPosition]:
        with self._lock, self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM crypto_positions WHERE status = 'CLOSED' ORDER BY exit_time DESC LIMIT ?;", (limit,)).fetchall()
            return [self._row_to_position(r) for r in rows]

    def _row_to_position(self, r: sqlite3.Row) -> CryptoPosition:
        is_stagnant = False
        stagnant_at = None
        try:
            if 'is_stagnant' in r.keys():
                is_stagnant = bool(r['is_stagnant'])
            if 'stagnant_at' in r.keys():
                stagnant_at = r['stagnant_at']
        except Exception:
            pass

        return CryptoPosition(
            position_id=r['position_id'],
            symbol=r['symbol'],
            engine=r['engine'],
            direction=r['direction'],
            entry_price=r['entry_price'],
            quantity=r['quantity'],
            initial_stop=r['initial_stop'],
            current_stop=r['current_stop'],
            target_1=r['target_1'],
            target_2=r['target_2'],
            t1_hit=bool(r['t1_hit']),
            defensive_active=bool(r['defensive_active']),
            unrealized_pnl=r['unrealized_pnl'],
            unrealized_r=r['unrealized_r'],
            entry_time=r['entry_time'],
            status=r['status'],
            exit_price=r['exit_price'],
            exit_reason=r['exit_reason'],
            exit_time=r['exit_time'],
            fees_paid=r['fees_paid'],
            is_stagnant=is_stagnant,
            stagnant_at=stagnant_at
        )

    # --- Screener Methods ---
    def save_screener_candidates(self, candidates: List[ScreenerCandidate]):
        with self._lock, self._get_connection() as conn:
            conn.execute("DELETE FROM crypto_screener;")
            now = time.time()
            for c in candidates:
                conn.execute("""
                    INSERT INTO crypto_screener (
                        symbol, name, price, change_24h, volume_24h, sector, why_picked,
                        score, h1_trend, volatility_pct, is_active_focus, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """, (
                    c.symbol, c.name, c.price, c.change_24h, c.volume_24h, c.sector,
                    c.why_picked, c.score, c.h1_trend, c.volatility_pct, int(c.is_active_focus), now
                ))
            conn.commit()

    def get_screener_candidates(self) -> List[ScreenerCandidate]:
        with self._lock, self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM crypto_screener ORDER BY score DESC;").fetchall()
            return [
                ScreenerCandidate(
                    symbol=r['symbol'],
                    name=r['name'],
                    price=r['price'],
                    change_24h=r['change_24h'],
                    volume_24h=r['volume_24h'],
                    sector=r['sector'],
                    why_picked=r['why_picked'],
                    score=r['score'],
                    h1_trend=r['h1_trend'],
                    volatility_pct=r['volatility_pct'],
                    is_active_focus=bool(r['is_active_focus'])
                ) for r in rows
            ]

    # --- Analysis Opportunity Methods ---
    def save_analysis(self, opp: AnalysisOpportunity):
        with self._lock, self._get_connection() as conn:
            conn.execute("""
                INSERT INTO crypto_analysis (
                    symbol, engine, direction, status, confidence_score, reason,
                    current_price, stop_loss, target_1, target_2, risk_r, sweep_level, fvg_bounds, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                opp.symbol, opp.engine, opp.direction, opp.status, opp.confidence_score, opp.reason,
                opp.current_price, opp.stop_loss, opp.target_1, opp.target_2, opp.risk_r, opp.sweep_level, opp.fvg_bounds, opp.timestamp
            ))
            # Keep only the latest 50 analysis records
            conn.execute("DELETE FROM crypto_analysis WHERE id NOT IN (SELECT id FROM crypto_analysis ORDER BY id DESC LIMIT 50);")
            conn.commit()

    def get_latest_analyses(self, limit: int = 5) -> List[AnalysisOpportunity]:
        with self._lock, self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM crypto_analysis ORDER BY timestamp DESC LIMIT ?;", (limit,)).fetchall()
            return [
                AnalysisOpportunity(
                    symbol=r['symbol'],
                    engine=r['engine'],
                    direction=r['direction'],
                    status=r['status'],
                    confidence_score=r['confidence_score'],
                    reason=r['reason'],
                    current_price=r['current_price'],
                    stop_loss=r['stop_loss'],
                    target_1=r['target_1'],
                    target_2=r['target_2'],
                    risk_r=r['risk_r'],
                    sweep_level=r['sweep_level'],
                    fvg_bounds=r['fvg_bounds'],
                    timestamp=r['timestamp']
                ) for r in rows
            ]

    # --- Activity Log Methods ---
    def log_activity(self, action: str, coin: str, detail: str, level: str = "INFO"):
        with self._lock, self._get_connection() as conn:
            conn.execute("""
                INSERT INTO crypto_activity_logs (timestamp, action, coin, detail, level)
                VALUES (?, ?, ?, ?, ?);
            """, (time.time(), action, coin, detail, level))
            # Keep latest 100 logs
            conn.execute("DELETE FROM crypto_activity_logs WHERE id NOT IN (SELECT id FROM crypto_activity_logs ORDER BY id DESC LIMIT 100);")
            conn.commit()

    def get_activity_logs(self, limit: int = 15) -> List[ActivityLog]:
        with self._lock, self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM crypto_activity_logs ORDER BY timestamp DESC LIMIT ?;", (limit,)).fetchall()
            return [
                ActivityLog(
                    timestamp=r['timestamp'],
                    action=r['action'],
                    coin=r['coin'],
                    detail=r['detail'],
                    level=r['level']
                ) for r in rows
            ]

    def reset_system(self, new_balance: Optional[float] = None):
        with self._lock, self._get_connection() as conn:
            row = conn.execute("SELECT * FROM crypto_account WHERE id = 1;").fetchone()
            cur_bal = new_balance or (row['balance'] if row and row['balance'] > 1000.0 else INITIAL_CAPITAL)
            conn.execute("DELETE FROM crypto_positions;")
            conn.execute("DELETE FROM crypto_screener;")
            conn.execute("DELETE FROM crypto_analysis;")
            conn.execute("DELETE FROM crypto_activity_logs;")
            conn.execute("""
                UPDATE crypto_account SET
                    balance = ?, peak_balance = ?, realized_pnl = 0.0,
                    daily_starting_equity = ?, daily_drawdown_pct = 0.0, is_locked = 0, updated_at = ?
                WHERE id = 1;
            """, (cur_bal, cur_bal, cur_bal, time.time()))
            conn.commit()

    # --- AI Asset Intelligence & Behavioral Memory Methods ---
    def record_coin_trade_outcome(
        self,
        symbol: str,
        gross_pnl: float,
        fees: float,
        is_win: bool,
        reason: str = ""
    ) -> Dict[str, Any]:
        """
        Records the outcome of a closed trade for this coin.
        Updates cumulative stats and triggers the 24h Auto-Quarantine Circuit Breaker
        if 2 consecutive losses or excessive negative net PnL occur.
        """
        now = time.time()
        net_trade_pnl = round(gross_pnl - fees, 4)

        with self._lock, self._get_connection() as conn:
            row = conn.execute("SELECT * FROM crypto_coin_stats WHERE symbol = ?;", (symbol,)).fetchone()
            if row:
                tot_trades = row['total_trades'] + 1
                wins = row['wins'] + (1 if is_win else 0)
                losses = row['losses'] + (0 if is_win else 1)
                cum_gross = round(row['gross_pnl'] + gross_pnl, 4)
                cum_fees = round(row['total_fees'] + fees, 4)
                cum_net = round(row['net_pnl'] + net_trade_pnl, 4)
                consec_losses = 0 if is_win else (row['consecutive_losses'] + 1)
                is_quar = row['is_quarantined']
                quar_until = row['quarantine_until']
            else:
                tot_trades = 1
                wins = 1 if is_win else 0
                losses = 0 if is_win else 1
                cum_gross = round(gross_pnl, 4)
                cum_fees = round(fees, 4)
                cum_net = net_trade_pnl
                consec_losses = 0 if is_win else 1
                is_quar = 0
                quar_until = 0.0

            win_rate = round((wins / tot_trades) * 100.0, 1) if tot_trades > 0 else 0.0

            # Evaluate Auto-Quarantine Circuit Breaker
            should_quarantine = (
                consec_losses >= AUTO_QUARANTINE_CONSECUTIVE_LOSSES or
                (tot_trades >= 2 and cum_net <= AUTO_QUARANTINE_MAX_NET_LOSS)
            )

            if should_quarantine:
                is_quar = 1
                quar_until = now + (AUTO_QUARANTINE_DURATION_HOURS * 3600)
                debrief = f"⚠️ QUARANTINED (24h): {consec_losses} consecutive losses / net loss ${cum_net:.2f}. Benched to protect capital from adverse market spread."
                conn.execute("""
                    INSERT INTO crypto_activity_logs (timestamp, action, coin, detail, level)
                    VALUES (?, 'AUTO_QUARANTINE', ?, ?, 'DANGER');
                """, (now, symbol, f"🔴 {symbol} auto-quarantined for 24h. Reason: {consec_losses} consecutive losses. Net: ${cum_net:.2f}."))
            elif is_win:
                is_quar = 0
                quar_until = 0.0
                debrief = f"🟢 PRIME PERFORMER: Profitable win (+${net_trade_pnl:.2f} net). Clean technical structure."
            else:
                debrief = f"🟡 ACTIVE WATCH: Single loss (-${abs(net_trade_pnl):.2f}). Controlled risk within stop collar."

            conn.execute("""
                INSERT INTO crypto_coin_stats
                (symbol, total_trades, wins, losses, win_rate, gross_pnl, total_fees, net_pnl,
                 consecutive_losses, is_quarantined, quarantine_until, last_trade_at, debrief)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol) DO UPDATE SET
                    total_trades = excluded.total_trades,
                    wins = excluded.wins,
                    losses = excluded.losses,
                    win_rate = excluded.win_rate,
                    gross_pnl = excluded.gross_pnl,
                    total_fees = excluded.total_fees,
                    net_pnl = excluded.net_pnl,
                    consecutive_losses = excluded.consecutive_losses,
                    is_quarantined = excluded.is_quarantined,
                    quarantine_until = excluded.quarantine_until,
                    last_trade_at = excluded.last_trade_at,
                    debrief = excluded.debrief;
            """, (symbol, tot_trades, wins, losses, win_rate, cum_gross, cum_fees, cum_net,
                  consec_losses, is_quar, quar_until, now, debrief))
            conn.commit()

            return {
                "symbol": symbol,
                "total_trades": tot_trades,
                "wins": wins,
                "losses": losses,
                "win_rate": win_rate,
                "gross_pnl": cum_gross,
                "total_fees": cum_fees,
                "net_pnl": cum_net,
                "consecutive_losses": consec_losses,
                "is_quarantined": is_quar,
                "quarantine_until": quar_until,
                "debrief": debrief
            }

    def is_coin_quarantined(self, symbol: str) -> Tuple[bool, float, str]:
        """
        Checks if symbol is currently quarantined.
        Returns: (is_quarantined: bool, remaining_seconds: float, reason: str)
        Automatically lifts quarantine if timer has elapsed.
        """
        now = time.time()
        with self._lock, self._get_connection() as conn:
            row = conn.execute("SELECT * FROM crypto_coin_stats WHERE symbol = ?;", (symbol,)).fetchone()
            if not row or not row['is_quarantined']:
                return False, 0.0, ""

            quar_until = row['quarantine_until']
            if now >= quar_until:
                # Timer expired! Automatically unquarantine
                conn.execute("""
                    UPDATE crypto_coin_stats SET
                        is_quarantined = 0,
                        consecutive_losses = 0,
                        debrief = '🟢 REHABILITATED: 24h quarantine expired. Restored to Prime monitoring.'
                    WHERE symbol = ?;
                """, (symbol,))
                conn.commit()
                return False, 0.0, ""

            remaining = quar_until - now
            hours_rem = max(1, int(remaining // 3600))
            return True, remaining, f"Coin in AI Quarantine ({hours_rem}h remaining) due to consecutive losses or fee drag."

    def unquarantine_coin(self, symbol: str) -> bool:
        """Manual operator override to unquarantine a coin."""
        with self._lock, self._get_connection() as conn:
            conn.execute("""
                UPDATE crypto_coin_stats SET
                    is_quarantined = 0,
                    quarantine_until = 0.0,
                    consecutive_losses = 0,
                    debrief = '🟢 MANUAL RESTORE: Quarantine lifted by operator.'
                WHERE symbol = ?;
            """, (symbol,))
            conn.commit()
            return True

    def get_coin_intelligence(self) -> List[Dict[str, Any]]:
        """
        Returns full intelligence matrix across all traded and Top 12 Prime coins.
        Sorted by net_pnl descending, then win_rate descending.
        """
        now = time.time()
        with self._lock, self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM crypto_coin_stats;").fetchall()
            stats_by_sym = {r['symbol']: dict(r) for r in rows}

            # Ensure all Top 12 Prime Universe coins are represented
            for sym in TOP_PRIME_SYMBOLS:
                if sym not in stats_by_sym:
                    stats_by_sym[sym] = {
                        "symbol": sym,
                        "total_trades": 0,
                        "wins": 0,
                        "losses": 0,
                        "win_rate": 0.0,
                        "gross_pnl": 0.0,
                        "total_fees": 0.0,
                        "net_pnl": 0.0,
                        "consecutive_losses": 0,
                        "is_quarantined": 0,
                        "quarantine_until": 0.0,
                        "last_trade_at": 0.0,
                        "debrief": "🟢 PRIME UNIVERSE: Institutional grade liquidity (<0.01% spread). Ready for screening."
                    }

            result = []
            for sym, s in stats_by_sym.items():
                is_quar = s["is_quarantined"]
                quar_until = s["quarantine_until"]
                rem_sec = max(0.0, quar_until - now) if is_quar else 0.0
                
                # Auto lift if expired
                if is_quar and now >= quar_until:
                    is_quar = 0
                    rem_sec = 0.0

                status_label = f"🔴 QUARANTINED ({int(rem_sec//3600)}h left)" if is_quar else ("🟢 PRIME (ACTIVE)" if sym in TOP_PRIME_SYMBOLS else "⚪ ALTCOIN")
                
                result.append({
                    "symbol": sym,
                    "is_prime": sym in TOP_PRIME_SYMBOLS,
                    "total_trades": s["total_trades"],
                    "wins": s["wins"],
                    "losses": s["losses"],
                    "win_rate": s["win_rate"],
                    "gross_pnl": round(s["gross_pnl"], 2),
                    "total_fees": round(s["total_fees"], 2),
                    "net_pnl": round(s["net_pnl"], 2),
                    "consecutive_losses": s["consecutive_losses"],
                    "is_quarantined": bool(is_quar),
                    "quarantine_remaining_hours": round(rem_sec / 3600.0, 1),
                    "status_label": status_label,
                    "debrief": s["debrief"]
                })

            # Sort: Active Prime and non-quarantined first, then by net_pnl descending
            result.sort(key=lambda x: (not x["is_quarantined"], x["is_prime"], x["net_pnl"], x["win_rate"]), reverse=True)
            return result

    # --- Multi-Timeframe Trade Snapshots & Dataset Archiver ---
    def save_trade_snapshot(
        self,
        position_id: str,
        symbol: str,
        engine: str,
        direction: str,
        entry_price: float,
        m5_candles: Any = None,
        m15_candles: Any = None,
        h1_candles: Any = None,
        btc_trend: Optional[str] = None,
        volatility_pct: float = 0.0
    ) -> str:
        """Saves entry state and historical candle sequence for ML dataset building."""
        snapshot_id = f"SNAP_{symbol}_{int(time.time())}"
        
        # Serialize candles safely
        m5_json = json.dumps([c.__dict__ if hasattr(c, "__dict__") else c for c in (m5_candles or [])])
        m15_json = json.dumps([c.__dict__ if hasattr(c, "__dict__") else c for c in (m15_candles or [])])
        h1_json = json.dumps([c.__dict__ if hasattr(c, "__dict__") else c for c in (h1_candles or [])])
        
        with self._lock, self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO crypto_trade_snapshots
                (snapshot_id, position_id, symbol, engine, direction, entry_price,
                 m5_candles_json, m15_candles_json, h1_candles_json, btc_trend,
                 volatility_pct, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (snapshot_id, position_id, symbol, engine, direction, entry_price,
                  m5_json, m15_json, h1_json, btc_trend or "NEUTRAL", volatility_pct, time.time()))
            conn.commit()
        return snapshot_id

    def finalize_trade_snapshot(
        self,
        position_id: str,
        exit_price: float,
        gross_pnl: float,
        fees: float,
        net_pnl: float,
        is_win: bool,
        exit_reason: str
    ) -> Optional[str]:
        """Finalizes snapshot on position exit with verified trade outcome."""
        now = time.time()
        with self._lock, self._get_connection() as conn:
            row = conn.execute("SELECT snapshot_id FROM crypto_trade_snapshots WHERE position_id = ? ORDER BY created_at DESC LIMIT 1;", (position_id,)).fetchone()
            if not row:
                return None
            snapshot_id = row['snapshot_id']
            conn.execute("""
                UPDATE crypto_trade_snapshots SET
                    exit_price = ?, gross_pnl = ?, fees = ?, net_pnl = ?,
                    is_win = ?, exit_reason = ?, closed_at = ?
                WHERE snapshot_id = ?;
            """, (exit_price, gross_pnl, fees, net_pnl, 1 if is_win else 0, exit_reason, now, snapshot_id))
            conn.commit()
            return snapshot_id

    def update_snapshot_ai_debrief(self, snapshot_id: str, ai_debrief: str):
        """Updates AI forensic analysis on a trade snapshot."""
        with self._lock, self._get_connection() as conn:
            conn.execute("""
                UPDATE crypto_trade_snapshots SET ai_debrief = ? WHERE snapshot_id = ?;
            """, (ai_debrief, snapshot_id))
            conn.commit()

    def get_trade_snapshots(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Returns recent trade snapshots for dataset inspection."""
        with self._lock, self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM crypto_trade_snapshots ORDER BY created_at DESC LIMIT ?;", (limit,)).fetchall()
            return [dict(r) for r in rows]

    def export_dataset_json(self) -> List[Dict[str, Any]]:
        """Exports full training dataset containing multi-timeframe candles and outcomes."""
        with self._lock, self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM crypto_trade_snapshots WHERE closed_at IS NOT NULL ORDER BY created_at ASC;").fetchall()
            res = []
            for r in rows:
                item = dict(r)
                try:
                    item['m5_candles'] = json.loads(item['m5_candles_json'] or '[]')
                    item['m15_candles'] = json.loads(item['m15_candles_json'] or '[]')
                    item['h1_candles'] = json.loads(item['h1_candles_json'] or '[]')
                except Exception:
                    pass
                res.append(item)
            return res
