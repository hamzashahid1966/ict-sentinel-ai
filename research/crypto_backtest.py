"""
Crypto Sentinel backtest: the live bot's strategy on 6 months of REAL Binance USDT-M 1-minute data.

Reuses the bot's own code where it decides: the three signal engines (A ICT, B momentum,
C liquidation), the signal arbitration, and CryptoRiskEngine.approve_trade (every gate and the
position size). Replicates the parts that live in the controller/order manager loop: the
screener ordering and regime, the BTC trend shield input, the Double Tap exits (Target 1 half at
0.4R -> stop to entry + 5% R, Target 2 at 0.8R), the 45-minute stagnation break-even, the
opportunity swap, fees, and the per-coin auto-quarantine.

PRE-REGISTERED DESIGN (fixed 2026-11-23 before the first full run)
  Universe   the 12 real-paper coins; Fast Scalper profile; $1,000 start; risk 0.35% (memes 0.20%),
             $4 cap; max 3 positions; 180s entry pacing (as configured).
  Decisions  at every 5-minute close. Engines see the last 30 CLOSED 5m bars, and 15m / 1h bars
             with the current forming bar built from the minutes so far (Binance klines include
             the forming bar). Live evaluates every ~5s on forming candles: not modelled.
  Entries    next 1-minute open, crossing the spread: +0.02% slippage (DEFAULT_SLIPPAGE_PCT) for
             longs, -0.02% for shorts. Skipped if the fill is already through the stop (as live).
  Exits      on 1-minute bars, PESSIMISTIC inside a bar: the stop is checked before any target;
             after Target 1 in a bar, the moved stop counts as hit if that bar reached it. A bar
             opening beyond a level fills at the open. Exit fills -0.02% adverse slippage.
  Costs      0.05% taker fee per side on every fill. Funding not modelled (holds are mostly < 8h).
  Drawdown   the 3% daily lock resets at 00:00 UTC (intended behaviour). The deployed paper bot
             never resets it; that variant is reported separately.
  Control    20 random-direction runs: the same entries (time, coin, stop width, size) with the
             direction chosen by coin flip, exits simulated identically.
  PASS       all of: (1) net P&L after fees > 0; (2) at least 4 of 6 calendar months positive;
             (3) net P&L above the 95th percentile of the 20 random-direction controls.
Research only: reads the local history store, places no orders.

Usage:
  python3 -m research.crypto_backtest                     # 12 coins, 183 days
  python3 -m research.crypto_backtest --coins BTC,ETH --days 30
"""

import argparse
import math
import os
import random
import sqlite3
import statistics
import sys
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("CRYPTO_EXECUTION_MODE", "REAL_DATA_PAPER")
DEFAULT_DB = os.environ.get("MARKET_HISTORY_DB", os.path.join(ROOT, "real_data", "market_history.db"))

from crypto_sentinel import risk_engine as risk_mod  # noqa: E402
from crypto_sentinel.config import (  # noqa: E402
    STRATEGY_PROFILES, TAKER_FEE_PCT, DEFAULT_SLIPPAGE_PCT, STAGNATION_TIMEOUT_SECONDS, TRUE_FEE_BUFFER_PCT,
    OPPORTUNITY_SWAP_MIN_SCORE, AUTO_SWAP_ENABLED, MAX_CONCURRENT_POSITIONS, TOP_50_UNIVERSE, REAL_PRIME_SYMBOLS,
    AUTO_QUARANTINE_CONSECUTIVE_LOSSES, AUTO_QUARANTINE_MAX_NET_LOSS, AUTO_QUARANTINE_DURATION_HOURS, INITIAL_CAPITAL,
)
from crypto_sentinel.models import CryptoAccount, CryptoCandle, CryptoPosition  # noqa: E402
from crypto_sentinel.engines.ict_engine import ICTLiquidityEngine  # noqa: E402
from crypto_sentinel.engines.momentum_engine import MomentumEngine  # noqa: E402
from crypto_sentinel.engines.liquidation_engine import LiquidationEngine  # noqa: E402
from crypto_sentinel.arbitration import SignalArbitrationEngine  # noqa: E402

PROFILE = STRATEGY_PROFILES["FAST_SCALPER"]
FEE = TAKER_FEE_PCT / 100.0
SLIP = DEFAULT_SLIPPAGE_PCT / 100.0
SECTOR = {u["symbol"]: u["sector"] for u in TOP_50_UNIVERSE}


# ── market data ──────────────────────────────────────────────────────────────

class CoinData:
    """1-minute bars on a full grid plus closed 5m/15m/1h bars as CryptoCandle lists."""

    def __init__(self, symbol: str, t: np.ndarray, o, h, l, c, qv):
        self.symbol = symbol
        self.t, self.o, self.h, self.l, self.c, self.qv = t, o, h, l, c, qv
        self.t0 = int(t[0])
        self.bars = {tf: self._aggregate(tf) for tf in (300, 900, 3600)}
        self.bar_index = {tf: {int(b.timestamp): i for i, b in enumerate(bs)} for tf, bs in self.bars.items()}

    def idx(self, ts: int) -> Optional[int]:
        i = (ts - self.t0) // 60
        return int(i) if 0 <= i < len(self.t) and not np.isnan(self.c[i]) else None

    def _aggregate(self, tf: int) -> List[CryptoCandle]:
        out = []
        k = tf // 60
        start = self.t0 + (-(self.t0 % tf)) % tf
        i0 = (start - self.t0) // 60
        for i in range(i0, len(self.t) - k + 1, k):
            seg = slice(i, i + k)
            if np.isnan(self.c[seg]).any():
                continue
            out.append(CryptoCandle(int(self.t[i]), float(self.o[i]), float(np.max(self.h[seg])), float(np.min(self.l[seg])),
                                    float(self.c[i + k - 1]), float(np.sum(self.qv[seg]))))
        return out

    def closed(self, tf: int, end_ts: int, n: int) -> List[CryptoCandle]:
        """Last n bars of timeframe tf that CLOSED at or before end_ts."""
        last_open = end_ts - tf
        last_open -= last_open % tf
        i = self.bar_index[tf].get(last_open)
        if i is None:
            return []
        return self.bars[tf][max(0, i - n + 1):i + 1]

    def forming(self, tf: int, end_ts: int) -> Optional[CryptoCandle]:
        """The tf bar that is still forming at end_ts, built from the minutes before end_ts."""
        start = end_ts - (end_ts % tf)
        if start == end_ts:
            return None
        a, b = self.idx(start), self.idx(end_ts - 60)
        if a is None or b is None:
            return None
        seg = slice(a, b + 1)
        return CryptoCandle(start, float(self.o[a]), float(np.nanmax(self.h[seg])), float(np.nanmin(self.l[seg])),
                            float(self.c[b]), float(np.nansum(self.qv[seg])))

    def with_forming(self, tf: int, end_ts: int, n: int) -> List[CryptoCandle]:
        f = self.forming(tf, end_ts)
        closed = self.closed(tf, end_ts, n - 1 if f else n)
        return closed + ([f] if f else [])

    def stats_24h(self, end_ts: int) -> Optional[Tuple[float, float, float]]:
        """(change %, high-low range %, quote volume) over the 24h ending at end_ts."""
        a, b = self.idx(end_ts - 86400), self.idx(end_ts - 60)
        if a is None or b is None:
            return None
        seg = slice(a, b + 1)
        hi, lo = float(np.nanmax(self.h[seg])), float(np.nanmin(self.l[seg]))
        chg = (float(self.c[b]) / float(self.o[a]) - 1) * 100
        return round(chg, 2), round((hi - lo) / lo * 100, 2) if lo > 0 else 0.0, float(np.nansum(self.qv[seg]))


def load_coin(db: str, symbol: str, start_ts: int, end_ts: int) -> Optional[CoinData]:
    with sqlite3.connect(db) as c:
        rows = c.execute("SELECT t, o, h, l, c, quote_volume FROM binance_1m WHERE symbol=? AND t>=? AND t<? ORDER BY t",
                         (symbol, start_ts, end_ts)).fetchall()
    if not rows:
        return None
    a = np.array(rows, dtype=float)
    t0, t1 = int(a[0, 0]), int(a[-1, 0])
    grid = np.arange(t0, t1 + 60, 60)
    pos = ((a[:, 0] - t0) // 60).astype(int)
    cols = []
    for j in range(1, 6):
        col = np.full(len(grid), np.nan)
        col[pos] = a[:, j]
        cols.append(col)
    return CoinData(symbol, grid, *cols)


def btc_trend(m5_closes: Sequence[float], h1_closes: Sequence[float]) -> str:
    """Same rule as CryptoDataFeed.get_btc_trend."""
    if len(m5_closes) < 5:
        return "NEUTRAL"
    avg_m5 = sum(m5_closes[-5:]) / 5.0
    last_c = m5_closes[-1]
    ratio = (last_c - avg_m5) / avg_m5
    bias = 0
    if len(h1_closes) >= 10:
        avg_h1 = sum(h1_closes[-10:]) / 10.0
        bias = 1 if last_c > avg_h1 else (-1 if last_c < avg_h1 else 0)
    if ratio > 0.0010 and bias >= 0:
        return "BULLISH"
    if ratio < -0.0010 and bias <= 0:
        return "BEARISH"
    return "NEUTRAL"


# ── positions and exits ──────────────────────────────────────────────────────

@dataclass
class SimPosition:
    symbol: str
    engine: str
    direction: str
    entry: float
    qty: float
    stop0: float
    stop: float
    t1: float
    t2: float
    entry_time: int
    risk_dollars: float
    t1_hit: bool = False
    defensive: bool = False
    stagnant: bool = False
    gross: float = 0.0
    fees: float = 0.0
    exit_price: Optional[float] = None
    exit_time: Optional[int] = None
    reason: str = ""

    @property
    def open_qty(self) -> float:
        return self.qty / 2.0 if self.t1_hit else self.qty

    def as_position(self) -> CryptoPosition:
        return CryptoPosition(position_id=f"{self.symbol}_{self.entry_time}", symbol=self.symbol, engine=self.engine,
                              direction=self.direction, entry_price=self.entry, quantity=self.qty, initial_stop=self.stop0,
                              current_stop=self.stop, target_1=self.t1, target_2=self.t2, t1_hit=self.t1_hit,
                              entry_time=self.entry_time)


def _round_px(entry: float, x: float) -> float:
    return round(x, 6 if entry < 1 else 2)


def open_sim_position(symbol, engine, direction, fill, stop, qty, ts, risk_dollars) -> SimPosition:
    r = abs(fill - stop)
    sgn = 1 if direction == "LONG" else -1
    t1 = _round_px(fill, fill + sgn * r * PROFILE["target_1_r"])
    t2 = _round_px(fill, fill + sgn * r * PROFILE["target_2_r"])
    p = SimPosition(symbol, engine, direction, fill, qty, stop, stop, t1, t2, ts, risk_dollars)
    p.fees += qty * fill * FEE
    return p


def _exit_fill(p: SimPosition, level: float) -> float:
    return level * (1 - SLIP) if p.direction == "LONG" else level * (1 + SLIP)


def _book(p: SimPosition, qty: float, fill: float):
    move = (fill - p.entry) if p.direction == "LONG" else (p.entry - fill)
    p.gross += move * qty
    p.fees += qty * fill * FEE


def process_bar(p: SimPosition, o: float, h: float, l: float, c: float, bar_end: int) -> Tuple[float, bool]:
    """
    Advance one 1-minute bar. Returns (realised cash change from this bar, closed?).
    Pessimistic ordering: stop before targets; after Target 1 in a bar, the moved stop is hit
    if the bar reached it.
    """
    long = p.direction == "LONG"
    adverse_hit = (lambda lvl: l <= lvl) if long else (lambda lvl: h >= lvl)
    fav_hit = (lambda lvl: h >= lvl) if long else (lambda lvl: l <= lvl)
    gap_worse = (lambda lvl: min(o, lvl)) if long else (lambda lvl: max(o, lvl))
    gap_better = (lambda lvl: max(o, lvl)) if long else (lambda lvl: min(o, lvl))
    before_g, before_f = p.gross, p.fees

    def close_all(level_px: float, reason: str):
        fill = _exit_fill(p, level_px)
        _book(p, p.open_qty, fill)
        p.exit_price, p.exit_time, p.reason = fill, bar_end, reason

    if adverse_hit(p.stop):
        close_all(gap_worse(p.stop), "DEFENSIVE_STOP_OUT" if p.defensive else "INITIAL_STOP_LOSS")
        return (p.gross - before_g) - (p.fees - before_f), True
    if not p.t1_hit and fav_hit(p.t1):
        half = p.qty / 2.0
        _book(p, half, _exit_fill(p, gap_better(p.t1)))
        p.t1_hit = True
        r = abs(p.entry - p.stop0)
        p.stop = _round_px(p.entry, p.entry + (0.05 * r if long else -0.05 * r))
        p.defensive = True
        if adverse_hit(p.stop):
            close_all(p.stop, "DEFENSIVE_STOP_OUT")
            return (p.gross - before_g) - (p.fees - before_f), True
    if fav_hit(p.t2):
        close_all(gap_better(p.t2), "TARGET_2_FULL_FILL")
        return (p.gross - before_g) - (p.fees - before_f), True
    if not p.t1_hit and not p.stagnant and bar_end - p.entry_time >= STAGNATION_TIMEOUT_SECONDS:
        p.stagnant = True
        cover = _round_px(p.entry, p.entry * (1 + TRUE_FEE_BUFFER_PCT if long else 1 - TRUE_FEE_BUFFER_PCT))
        if ((c >= cover) if long else (c <= cover)) and ((cover > p.stop) if long else (cover < p.stop)):
            p.stop, p.defensive = cover, True
    return (p.gross - before_g) - (p.fees - before_f), False


# ── account and quarantine (mirror storage.update_account / record_coin_trade_outcome) ──

class Account:
    def __init__(self, balance: float = INITIAL_CAPITAL, daily_reset: bool = True):
        self.balance = balance
        self.peak = balance
        self.day_start = balance
        self.day = None
        self.daily_reset = daily_reset
        self.max_dd = PROFILE["max_daily_drawdown_pct"]

    def new_time(self, ts: int):
        d = ts // 86400
        if self.day is None:
            self.day = d
        elif d != self.day and self.daily_reset:
            self.day, self.day_start = d, self.balance

    def add(self, cash: float):
        self.balance += cash
        self.peak = max(self.peak, self.balance)

    @property
    def dd_pct(self) -> float:
        return max(0.0, (self.day_start - self.balance) / self.day_start * 100.0) if self.day_start > 0 else 0.0

    def as_account(self) -> CryptoAccount:
        dd = self.dd_pct
        return CryptoAccount(balance=self.balance, peak_balance=self.peak, realized_pnl=self.balance - INITIAL_CAPITAL,
                             daily_starting_equity=self.day_start, daily_drawdown_pct=dd, is_locked=dd >= self.max_dd,
                             mode="REAL_DATA_PAPER", strategy_profile="FAST_SCALPER")


class Quarantine:
    def __init__(self):
        self.s: Dict[str, Dict] = {}

    def record(self, symbol: str, net: float, now: int):
        st = self.s.setdefault(symbol, {"trades": 0, "net": 0.0, "consec": 0, "until": 0.0, "on": False})
        win = net > 0
        st["trades"] += 1
        st["net"] = round(st["net"] + net, 4)
        st["consec"] = 0 if win else st["consec"] + 1
        if st["consec"] >= AUTO_QUARANTINE_CONSECUTIVE_LOSSES or (st["trades"] >= 2 and st["net"] <= AUTO_QUARANTINE_MAX_NET_LOSS):
            st["on"], st["until"] = True, now + AUTO_QUARANTINE_DURATION_HOURS * 3600
        elif win:
            st["on"], st["until"] = False, 0.0

    def active(self, symbol: str, now: int) -> bool:
        st = self.s.get(symbol)
        if not st or not st["on"]:
            return False
        if now >= st["until"]:
            st["on"], st["consec"] = False, 0
            return False
        return True


# ── the backtest ─────────────────────────────────────────────────────────────

class _Clock:
    def __init__(self):
        self.now = 0.0

    def time(self):
        return self.now


@dataclass
class Result:
    trades: List[SimPosition] = field(default_factory=list)
    equity: List[Tuple[int, float]] = field(default_factory=list)
    signals: int = 0
    rejections: Dict[str, int] = field(default_factory=dict)
    locked_steps: int = 0


def run_backtest(data: Dict[str, CoinData], start_ts: int, end_ts: int, daily_reset: bool = True,
                 verbose: bool = True) -> Result:
    engines = {"A": ICTLiquidityEngine(), "B": MomentumEngine(), "C": LiquidationEngine()}
    arb = SignalArbitrationEngine()
    risk = risk_mod.CryptoRiskEngine()
    clock = _Clock()
    real_time = risk_mod.time
    risk_mod.time = clock          # pacing gate reads the simulated clock
    acc, quar, res = Account(daily_reset=daily_reset), Quarantine(), Result()
    open_pos: List[SimPosition] = []
    last_open = 0.0
    symbols = [s for s in REAL_PRIME_SYMBOLS if s in data]
    t_start = max(start_ts, max(d.t0 for d in data.values()) + 86400 + 3600 * 50)
    t_start -= t_start % 300
    t0_wall = time.time()
    try:
        for m in range(t_start, end_ts, 60):
            bar_end = m + 60
            acc.new_time(m)
            # 1. manage open positions on this minute
            for p in list(open_pos):
                i = data[p.symbol].idx(m)
                if i is None:
                    continue
                d = data[p.symbol]
                cash, closed = process_bar(p, float(d.o[i]), float(d.h[i]), float(d.l[i]), float(d.c[i]), bar_end)
                acc.add(cash)
                if closed:
                    open_pos.remove(p)
                    res.trades.append(p)
                    quar.record(p.symbol, p.gross - p.fees, bar_end)
            if bar_end % 300:
                continue
            # 2. decision at the 5-minute close
            T = bar_end
            clock.now = float(T)
            res.equity.append((T, acc.balance))
            cands = []
            for s in symbols:
                st = data[s].stats_24h(T)
                if st:
                    chg, vol, qv = st
                    cands.append((min(98.0, abs(chg) * 4.5 + vol * 2.0 + min(20.0, qv / 100_000_000)), s, chg, vol))
            cands.sort(reverse=True)
            if not cands:
                continue
            regime = arb.classify_regime(cands[-1][2], cands[-1][3])  # the controller keeps the last coin's regime
            btc = data.get("BTCUSDT")
            trend = btc_trend([c.close for c in btc.closed(300, T, 15)], [c.close for c in btc.with_forming(3600, T, 20)]) if btc else "NEUTRAL"
            per_sym = []
            for _, s, chg, vol in cands:
                d = data[s]
                m5 = d.closed(300, T, 30)
                m15 = d.with_forming(900, T, 30)
                h1 = d.with_forming(3600, T, 50)
                if len(m5) < 30 or len(m15) < 20 or len(h1) < 30:
                    continue
                opps = [o for o in (engines["A"].evaluate(s, m5, h1, m15), engines["B"].evaluate(s, m5, h1, m15),
                                    engines["C"].evaluate(s, m5, m15)) if o]
                res.signals += len(opps)
                best = arb.arbitrate(opps, regime) if opps else None
                if best:
                    per_sym.append(best)
            per_sym.sort(key=lambda o: o.confidence_score, reverse=True)
            for opp in per_sym:
                if len(open_pos) >= MAX_CONCURRENT_POSITIONS:
                    if not (AUTO_SWAP_ENABLED and opp.confidence_score >= OPPORTUNITY_SWAP_MIN_SCORE / 100.0):
                        break
                    victim = None
                    for p in open_pos:
                        if p.symbol == opp.symbol or p.t1_hit or T - p.entry_time < STAGNATION_TIMEOUT_SECONDS:
                            continue
                        px = float(data[p.symbol].c[data[p.symbol].idx(T - 60)])
                        cover = p.entry * (1 + TRUE_FEE_BUFFER_PCT if p.direction == "LONG" else 1 - TRUE_FEE_BUFFER_PCT)
                        if (px >= cover) if p.direction == "LONG" else (px <= cover):
                            victim = (p, px)
                            break
                    if not victim:
                        break
                    p, px = victim
                    fill = _exit_fill(p, px)
                    before = p.gross - p.fees
                    _book(p, p.open_qty, fill)
                    p.exit_price, p.exit_time, p.reason = fill, T, "STAGNANT_SWAP"
                    acc.add((p.gross - p.fees) - before)
                    open_pos.remove(p)
                    res.trades.append(p)
                    quar.record(p.symbol, p.gross - p.fees, T)
                account = acc.as_account()
                if account.is_locked:
                    res.locked_steps += 1
                last_ts = max([last_open] + [p.entry_time for p in open_pos])
                ok, qty, reason = risk.approve_trade(account, opp, [p.as_position() for p in open_pos],
                                                     sector=SECTOR.get(opp.symbol, "MAJOR"), btc_trend=trend,
                                                     last_trade_time=last_ts, is_quarantined=quar.active(opp.symbol, T),
                                                     quarantine_reason="")
                if not ok:
                    key = reason.split("(")[0].split(".")[0][:60]
                    res.rejections[key] = res.rejections.get(key, 0) + 1
                    continue
                d = data[opp.symbol]
                i = d.idx(T)
                if i is None:
                    continue
                o_next = float(d.o[i])
                fill = o_next * (1 + SLIP) if opp.direction == "LONG" else o_next * (1 - SLIP)
                if (opp.direction == "LONG" and fill <= opp.stop_loss) or (opp.direction == "SHORT" and fill >= opp.stop_loss):
                    res.rejections["fill through stop"] = res.rejections.get("fill through stop", 0) + 1
                    continue
                risk_dollars = qty * abs(opp.current_price - opp.stop_loss)
                p = open_sim_position(opp.symbol, opp.engine, opp.direction, fill, opp.stop_loss, qty, T, risk_dollars)
                acc.add(-p.fees)
                open_pos.append(p)
                last_open = float(T)
            if verbose and (T // 300) % 2016 == 0:
                print(f"  {time.strftime('%Y-%m-%d', time.gmtime(T))}: balance {acc.balance:,.2f}, trades {len(res.trades)}, "
                      f"open {len(open_pos)} ({time.time() - t0_wall:.0f}s)", flush=True)
    finally:
        risk_mod.time = real_time
    for p in open_pos:  # mark-to-market at the end
        d = data[p.symbol]
        i = d.idx(end_ts - 60) or (len(d.c) - 1)
        fill = _exit_fill(p, float(d.c[i]))
        _book(p, p.open_qty, fill)
        p.exit_price, p.exit_time, p.reason = fill, end_ts, "END_OF_TEST"
        res.trades.append(p)
    return res


def random_control(trades: List[SimPosition], data: Dict[str, CoinData], end_ts: int, seed: int) -> float:
    """Same entries (time, coin, stop width, size), coin-flip direction, identical exit simulation."""
    rng = random.Random(seed)
    total = 0.0
    for t in trades:
        d = data[t.symbol]
        i0 = d.idx(t.entry_time)
        if i0 is None:
            continue
        direction = rng.choice(("LONG", "SHORT"))
        o_next = float(d.o[i0])
        fill = o_next * (1 + SLIP) if direction == "LONG" else o_next * (1 - SLIP)
        width = abs(t.entry - t.stop0)
        stop = fill - width if direction == "LONG" else fill + width
        p = open_sim_position(t.symbol, "RANDOM", direction, fill, stop, t.qty, t.entry_time, t.risk_dollars)
        closed = False
        for m in range(t.entry_time, end_ts, 60):
            i = d.idx(m)
            if i is None:
                continue
            _, closed = process_bar(p, float(d.o[i]), float(d.h[i]), float(d.l[i]), float(d.c[i]), m + 60)
            if closed:
                break
        if not closed:
            i = d.idx(end_ts - 60) or (len(d.c) - 1)
            _book(p, p.open_qty, _exit_fill(p, float(d.c[i])))
        total += p.gross - p.fees
    return total


# ── report ───────────────────────────────────────────────────────────────────

def summarize(trades: List[SimPosition]) -> Dict:
    nets = [t.gross - t.fees for t in trades]
    wins = [x for x in nets if x > 0]
    losses = [x for x in nets if x <= 0]
    return {"trades": len(trades), "net": sum(nets), "gross": sum(t.gross for t in trades), "fees": sum(t.fees for t in trades),
            "win_rate": len(wins) / len(nets) if nets else 0.0, "avg_win": statistics.mean(wins) if wins else 0.0,
            "avg_loss": statistics.mean(losses) if losses else 0.0,
            "profit_factor": (sum(wins) / -sum(losses)) if losses and sum(losses) < 0 else float("inf"),
            "avg_R": statistics.mean((t.gross - t.fees) / t.risk_dollars for t in trades if t.risk_dollars > 0) if trades else 0.0}


def max_drawdown(equity: List[Tuple[int, float]]) -> float:
    peak, mdd = -1e18, 0.0
    for _, v in equity:
        peak = max(peak, v)
        mdd = max(mdd, (peak - v) / peak * 100 if peak > 0 else 0.0)
    return mdd


def format_report(res: Result, deployed: Optional[Result], controls: List[float], span: str, coins: List[str]) -> Tuple[str, bool]:
    L = []
    s = summarize(res.trades)
    L.append(f"Crypto Sentinel backtest, Fast Scalper, {', '.join(c.replace('USDT','') for c in coins)} ({span})")
    L.append("=" * len(L[0]))
    L.append(f"trades {s['trades']} | net P&L {s['net']:+.2f} on $1,000 ({s['net']/10:+.2f}%) | gross {s['gross']:+.2f} | fees -{s['fees']:.2f}")
    L.append(f"win rate {s['win_rate']*100:.1f}% | avg win {s['avg_win']:+.2f} | avg loss {s['avg_loss']:+.2f} | "
             f"profit factor {s['profit_factor']:.2f} | avg net R {s['avg_R']:+.3f} | max drawdown {max_drawdown(res.equity):.2f}%")
    L.append(f"engine signals {res.signals:,} | decisions skipped while the daily lock was on: {res.locked_steps:,}")
    L.append("")

    def table(title, key):
        L.append(title)
        groups: Dict[str, List[SimPosition]] = {}
        for t in res.trades:
            groups.setdefault(key(t), []).append(t)
        for k in sorted(groups):
            g = summarize(groups[k])
            L.append(f"  {k:<20} {g['trades']:>5} trades  win {g['win_rate']*100:5.1f}%  net {g['net']:+9.2f}  "
                     f"fees {g['fees']:7.2f}  avg R {g['avg_R']:+.3f}")
    table("by coin", lambda t: t.symbol)
    table("by month", lambda t: time.strftime("%Y-%m", time.gmtime(t.entry_time)))
    table("by engine", lambda t: t.engine)
    table("by direction", lambda t: t.direction)
    table("by exit", lambda t: t.reason)
    L.append("")
    L.append("risk-gate rejections: " + ", ".join(f"{k.strip()}: {v:,}" for k, v in sorted(res.rejections.items(), key=lambda kv: -kv[1])))
    if deployed is not None:
        d = summarize(deployed.trades)
        L.append(f"as deployed (daily drawdown lock never resets): {d['trades']} trades, net {d['net']:+.2f}, "
                 f"decisions blocked by the lock {deployed.locked_steps:,}")
    months = {}
    for t in res.trades:
        months.setdefault(time.strftime("%Y-%m", time.gmtime(t.entry_time)), 0.0)
        months[time.strftime("%Y-%m", time.gmtime(t.entry_time))] += t.gross - t.fees
    full_months = {k: v for k, v in months.items()}
    pos_months = sum(1 for v in full_months.values() if v > 0)
    p95 = float(np.percentile(controls, 95)) if controls else float("nan")
    L.append(f"random-direction controls ({len(controls)}): median {statistics.median(controls):+.2f}, 95th pct {p95:+.2f}, "
             f"min {min(controls):+.2f}, max {max(controls):+.2f}" if controls else "random controls: not run")
    ok = s["net"] > 0 and pos_months >= 4 and (not controls or s["net"] > p95)
    L.append(f"PASS MARK: net > 0 {s['net'] > 0} | months positive {pos_months}/{len(full_months)} (need 4) | "
             f"beats 95th pct of random {s['net'] > p95 if controls else 'n/a'}  ==> {'PASS' if ok else 'FAIL'}")
    return "\n".join(L), ok


def main(argv=None):
    ap = argparse.ArgumentParser(description="Backtest Crypto Sentinel on real Binance 1m history")
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--coins", default=",".join(s.replace("USDT", "") for s in REAL_PRIME_SYMBOLS))
    ap.add_argument("--days", type=int, default=183)
    ap.add_argument("--controls", type=int, default=20)
    ap.add_argument("--no-deployed", action="store_true")
    ap.add_argument("--out", default=os.path.join(ROOT, "docs", "CRYPTO_BACKTEST_RESULTS.md"))
    args = ap.parse_args(argv)
    coins = [f"{c.strip().upper()}USDT" for c in args.coins.split(",") if c.strip()]
    end_ts = int(time.time() // 3600) * 3600 - 3600
    start_ts = end_ts - args.days * 86400
    data = {}
    for s in coins:
        d = load_coin(args.db, s, start_ts - 3 * 86400, end_ts)
        if d is None or len(d.t) < 10000:
            print(f"  {s}: not enough 1m data in {args.db}; skipped", flush=True)
            continue
        data[s] = d
        print(f"  loaded {s}: {len(d.t):,} minutes", flush=True)
    if "BTCUSDT" not in data:
        print("BTCUSDT data is required (trend shield).")
        return
    span = f"{time.strftime('%Y-%m-%d', time.gmtime(start_ts))}..{time.strftime('%Y-%m-%d', time.gmtime(end_ts))}"
    print("running backtest ...", flush=True)
    res = run_backtest(data, start_ts, end_ts)
    deployed = None if args.no_deployed else run_backtest(data, start_ts, end_ts, daily_reset=False, verbose=False)
    print(f"running {args.controls} random-direction controls ...", flush=True)
    controls = [random_control(res.trades, data, end_ts, seed) for seed in range(args.controls)]
    text, ok = format_report(res, deployed, controls, span, list(data))
    print("\n" + text)
    with open(args.out, "w") as f:
        f.write("```\n" + text + "\n```\n\nSee research/crypto_backtest.py for the pre-registered design.\n")
    print(f"\nreport written to {args.out}")


if __name__ == "__main__":
    main()
