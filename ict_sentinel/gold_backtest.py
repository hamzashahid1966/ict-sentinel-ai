"""
Walk-forward backtester for the Core Gold London model, driven by the PRODUCTION
signal engine (IPDAEngine.evaluate_market with asset GOLD), so what is measured is
the code that trades, not a re-implementation of it.

Fill model (deliberately conservative):
  - signals fire on a closed bar; entry is the NEXT bar's open plus adverse slippage
  - stop fills get adverse slippage; target fills get none
  - a bar that touches both the stop and the target counts as a STOP
  - a round-trip friction charge (spread + commission) is deducted from every trade
  - positions are flattened at the session exit deadline, as the live OMS does
  - one position at a time and the live 15-minute re-entry cooldown

Exit models:
  production  the live single-contract protocol: stop to breakeven+buffer at 1R, full exit at 2R
  fixed_1_6r  the Pine v1.6 model: structural stop, fixed 1.6R target, no breakeven move
  fixed_2r    structural stop, fixed 2R target, no breakeven move

Sizing is fractional (dollars-per-point units), so risk per trade is exactly
equity * risk_pct, which is what the question "what if we size at 0.5%" needs.

Usage:
  python3 -m ict_sentinel.gold_backtest --data real_data/gold/gold_5m_24m.json
"""

import argparse
import datetime
import json
import math
import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .config import NY_TZ, SESSION_WINDOWS
from .ipda_engine import IPDAEngine, AlgorithmicSignal
from .models import Candle

UTC = datetime.timezone.utc


@dataclass
class BacktestConfig:
    exit_model: str = "production"      # production | fixed_1_6r | fixed_2r
    friction_pts: float = 0.30          # round-trip spread + commission, points per unit
    slippage_pts: float = 0.10          # adverse slip on entry and on stop fills
    equity: float = 10000.0
    risk_pct: float = 0.5
    cooldown_sec: int = 900
    window: int = 180
    quarantine: bool = False            # replay the live 2-loss quarantine gate
    session_exit: bool = True
    tick_pts: float = 0.10
    fixed_units: Optional[float] = None   # e.g. 10.0 = one micro gold contract ($10/pt) regardless of equity
    max_trades_per_day: Optional[int] = None   # Pine v1.6 rule: at most 3 entries per day
    one_per_setup_per_day: bool = False        # Pine v1.6 rule: a broken level is consumed by its first entry
    gold_model_only: bool = False              # ignore the generic sweep/FVG (BISI/SIBI) signals, keep IMP/ASIA_SWEEP
    stop_mult: float = 1.0                     # widen the structural stop by this factor (risk per trade stays equity*risk_pct)
    setups: Optional[Tuple[str, ...]] = None   # allow-list of setup types, e.g. ("IMP_PULLBACK",)
    trend_filter: bool = False                 # only trade with the daily trend from COMPLETED days
    trend_ema_len: int = 20
    random_entries: Optional[float] = None     # CONTROL: probability per eligible London bar of a random entry instead of the engine
    seed: int = 1


@dataclass
class TradeResult:
    direction: str
    session: str
    setup_type: str
    signal_time: datetime.datetime
    entry_time: datetime.datetime
    entry_price: float
    exit_time: datetime.datetime
    exit_price: float
    outcome: str
    risk_pts: float
    pnl_pts: float
    dollar_pnl: float
    r_multiple: float
    units: float
    bars_held: int
    equity_after: float = 0.0


# ── regime gate: in-memory twin of MemoryEngine._update_regime_weights / evaluate_setup_viability ──

class RegimeGate:
    def __init__(self):
        self.w: Dict[str, Dict[str, Any]] = {}

    def record(self, asset: str, session: str, dollar_pnl: float):
        key = f"{asset}::{session}"
        e = self.w.get(key, {"wins": 0, "losses": 0, "consecutive_losses": 0})
        is_win = dollar_pnl > 0
        wins = e["wins"] + (1 if is_win else 0)
        losses = e["losses"] + (0 if is_win else 1)
        consec = 0 if is_win else e["consecutive_losses"] + 1
        alpha, beta = wins + 2, losses + 2
        q = max(0.10, min(0.99, alpha / (alpha + beta) - 0.15 * consec))
        total = wins + losses
        if consec >= 2 or (total >= 3 and q < 0.40):
            status = "QUARANTINED"
        elif q < 0.55 or consec == 1:
            status = "OBSERVATION"
        else:
            status = "PRIME"
        self.w[key] = {"wins": wins, "losses": losses, "consecutive_losses": consec, "quality_score": q, "status": status}

    def evaluate_setup_viability(self, asset: str, session: str, array_type: str) -> Tuple[bool, float, str]:
        e = self.w.get(f"{asset}::{session}")
        if not e:
            return True, 0.70, "Probationary clearance"
        if e["status"] == "QUARANTINED":
            return False, e["quality_score"], f"REJECTED: {asset}::{session} is QUARANTINED"
        if e["status"] == "OBSERVATION" and e["quality_score"] < 0.45:
            return False, e["quality_score"], "FILTERED: observation"
        return True, e["quality_score"], "APPROVED"


# ── fill / exit simulator ──────────────────────────────────────────────────────

def _exit_deadline(session: str) -> Optional[datetime.time]:
    win = SESSION_WINDOWS.get(session)
    return win.get("exit_time") if win else None


def simulate_trade(sig: AlgorithmicSignal, bars: List[Candle], cfg: BacktestConfig, units: float) -> Optional[TradeResult]:
    """bars[0] is the signal bar; the fill happens on bars[1]."""
    if len(bars) < 2:
        return None
    is_long = sig.direction == "LONG"
    d = 1.0 if is_long else -1.0
    entry = bars[1].open + d * cfg.slippage_pts
    base_risk = float(sig.risk_pts)
    risk = base_risk * cfg.stop_mult
    stop = float(sig.stop_loss) - d * (cfg.stop_mult - 1.0) * base_risk
    if cfg.exit_model in ("production", "fixed_2r"):
        target = entry + d * 2.0 * risk
    elif cfg.exit_model == "time_exit":
        target = None   # hold to the session deadline, stop only
    else:
        target = entry + d * 1.6 * risk
    r1 = entry + d * risk
    shield_px = entry + d * (cfg.friction_pts + cfg.tick_pts)
    shield_on = False
    deadline = _exit_deadline(sig.session) if cfg.session_exit else None
    setup_type = getattr(sig.pd_array, "array_type", "DIRECT") if sig.pd_array else "DIRECT"

    def finish(i: int, px: float, outcome: str) -> TradeResult:
        pnl_pts = (px - entry) * d - cfg.friction_pts
        return TradeResult(direction=sig.direction, session=sig.session, setup_type=setup_type,
                           signal_time=bars[0].timestamp, entry_time=bars[1].timestamp, entry_price=entry,
                           exit_time=bars[i].timestamp, exit_price=px, outcome=outcome, risk_pts=risk,
                           pnl_pts=pnl_pts, dollar_pnl=pnl_pts * units, r_multiple=pnl_pts / risk if risk else 0.0,
                           units=units, bars_held=i)

    for i in range(1, len(bars)):
        b = bars[i]
        if deadline is not None and b.timestamp_et.time() >= deadline:
            return finish(i, b.close, "SESSION_EXPIRATION")
        hit_stop = (b.low <= stop) if is_long else (b.high >= stop)
        hit_target = False if target is None else ((b.high >= target) if is_long else (b.low <= target))

        if cfg.exit_model == "production":
            just_trailed = False
            hit_r1 = (b.high >= r1) if is_long else (b.low <= r1)
            if not shield_on and hit_r1:
                shield_on, stop, just_trailed = True, shield_px, True
                hit_stop = False  # live OMS skips the stop check on the bar the shield is set
            if hit_stop:
                return finish(i, stop - d * cfg.slippage_pts, "DEFENSIVE_STOP" if shield_on and not just_trailed else "STOP")
            if hit_target:
                return finish(i, target, "TARGET")
        else:
            if hit_stop:
                return finish(i, stop - d * cfg.slippage_pts, "STOP")
            if hit_target:
                return finish(i, target, "TARGET")
    return finish(len(bars) - 1, bars[-1].close, "END_OF_DATA")


class DailyTrend:
    """Daily close EMA read from COMPLETED days only; the in-progress day never leaks in."""

    def __init__(self, ema_len: int = 20):
        self.ema_len = ema_len
        self.closes: Dict[datetime.date, float] = {}

    def observe(self, day: datetime.date, close: float):
        self.closes[day] = close

    def direction(self, day: datetime.date) -> Optional[str]:
        done = [self.closes[k] for k in sorted(self.closes) if k < day]
        if len(done) < 2:
            return None
        k = 2.0 / (self.ema_len + 1.0)
        ema = done[0]
        for c in done[1:]:
            ema = c * k + ema * (1.0 - k)
        return "UP" if done[-1] > ema else "DOWN"


def random_signal(window: List[Candle], session: str, rng: random.Random) -> AlgorithmicSignal:
    """
    Control signal: a coin-flip direction at the current close with a structural-looking
    stop (1.5x the average 14-bar range, clipped to the gold model's 1.5..15 point bounds).
    Same exits, costs, cooldown and deadline as the engine; only the entry decision is random.
    """
    curr = window[-1]
    recent = window[-15:-1] if len(window) >= 15 else window[:-1] or [curr]
    avg_range = sum(c.high - c.low for c in recent) / len(recent)
    risk = max(1.5, min(15.0, round(avg_range * 1.5, 2)))
    direction = "LONG" if rng.random() < 0.5 else "SHORT"
    entry = curr.close
    stop = entry - risk if direction == "LONG" else entry + risk
    from .models import PDArray
    return AlgorithmicSignal(asset="GOLD", session=session, direction=direction, entry_price=entry, stop_loss=stop,
                             risk_pts=risk, target_center_mass=entry + (1.6 * risk if direction == "LONG" else -1.6 * risk),
                             target_head_shot=entry + (2.5 * risk if direction == "LONG" else -2.5 * risk),
                             pd_array=PDArray("RANDOM", curr.high, curr.low, None, curr.timestamp_et), ai_rationale="random control")


def signal_allowed(cfg: BacktestConfig, setup: str, direction: str, trend: Optional[str]) -> bool:
    if cfg.setups is not None and setup not in cfg.setups:
        return False
    if cfg.trend_filter:
        if trend is None:
            return False
        if (direction == "LONG") != (trend == "UP"):
            return False
    return True


# ── data ────────────────────────────────────────────────────────────────────────

def load_bars(path: str) -> List[Candle]:
    with open(path) as f:
        raw = json.load(f)
    out = []
    for b in raw:
        ts = datetime.datetime.fromtimestamp(b["time"] / 1000.0, tz=UTC)
        out.append(Candle(timestamp=ts, timestamp_et=ts.astimezone(NY_TZ), open=float(b["open"]), high=float(b["high"]),
                          low=float(b["low"]), close=float(b["close"]), volume=float(b.get("volume", 0.0))))
    out.sort(key=lambda c: c.timestamp)
    return out


# ── walk-forward run ────────────────────────────────────────────────────────────

def run_backtest(bars: List[Candle], cfg: BacktestConfig, start: Optional[datetime.datetime] = None,
                 end: Optional[datetime.datetime] = None) -> Dict[str, Any]:
    engine = IPDAEngine()
    gate = RegimeGate() if cfg.quarantine else None
    equity = cfg.equity
    trades: List[TradeResult] = []
    rejected_by_gate = 0
    cooldown_until: Optional[datetime.datetime] = None
    per_day: Dict[str, int] = {}
    taken = set()
    trend = DailyTrend(cfg.trend_ema_len)
    rng = random.Random(cfg.seed)
    for b0 in bars[:cfg.window]:
        trend.observe(b0.timestamp_et.date(), b0.close)
    i = cfg.window
    n = len(bars)
    while i < n - 1:
        c = bars[i]
        trend.observe(c.timestamp_et.date(), c.close)
        if (start and c.timestamp < start) or (end and c.timestamp > end):
            i += 1
            continue
        t_et = c.timestamp_et.time()
        if IPDAEngine.get_current_session(t_et) not in ("LONDON", "LONDON_CORE"):
            i += 1
            continue
        if cooldown_until and c.timestamp < cooldown_until:
            i += 1
            continue
        window = bars[i - cfg.window + 1:i + 1]
        if cfg.random_entries is not None:
            sig = random_signal(window, IPDAEngine.get_current_session(t_et), rng) if rng.random() < cfg.random_entries else None
        elif gate is not None:
            sig = engine.evaluate_market("GOLD", window, memory_engine=gate)
            if sig is None:
                probe = engine.evaluate_market("GOLD", window, memory_engine=None)
                if probe is not None:
                    rejected_by_gate += 1
        else:
            sig = engine.evaluate_market("GOLD", window, memory_engine=None)
        if sig is None:
            i += 1
            continue
        setup = getattr(sig.pd_array, "array_type", "DIRECT") if sig.pd_array else "DIRECT"
        day_key = c.timestamp_et.date().isoformat()
        if cfg.gold_model_only and setup not in ("IMP_PULLBACK", "ASIA_SWEEP"):
            i += 1
            continue
        if not signal_allowed(cfg, setup, sig.direction, trend.direction(c.timestamp_et.date())):
            i += 1
            continue
        if cfg.max_trades_per_day is not None and per_day.get(day_key, 0) >= cfg.max_trades_per_day:
            i += 1
            continue
        if cfg.one_per_setup_per_day and (day_key, setup, sig.direction) in taken:
            i += 1
            continue
        per_day[day_key] = per_day.get(day_key, 0) + 1
        taken.add((day_key, setup, sig.direction))
        units = cfg.fixed_units if cfg.fixed_units else (equity * cfg.risk_pct / 100.0) / (sig.risk_pts * cfg.stop_mult)
        res = simulate_trade(sig, bars[i:i + 400], cfg, units)
        if res is None:
            break
        equity += res.dollar_pnl
        res.equity_after = equity
        trades.append(res)
        if gate is not None:
            gate.record("GOLD", sig.session, res.dollar_pnl)
        cooldown_until = res.exit_time + datetime.timedelta(seconds=cfg.cooldown_sec)
        i += max(1, res.bars_held)
    return {"config": cfg, "trades": trades, "final_equity": equity, "rejected_by_gate": rejected_by_gate,
            "metrics": compute_metrics(trades, cfg.equity, start or bars[0].timestamp, end or bars[-1].timestamp)}


# ── metrics ─────────────────────────────────────────────────────────────────────

def compute_metrics(trades: List[TradeResult], equity0: float, t_start: datetime.datetime, t_end: datetime.datetime) -> Dict[str, Any]:
    n = len(trades)
    if n == 0:
        return {"trades": 0}
    pnls = [t.dollar_pnl for t in trades]
    rs = [t.r_multiple for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    gp, gl = sum(wins), -sum(losses)
    pf = gp / gl if gl > 0 else float("inf")
    peak, max_dd, eq = equity0, 0.0, equity0
    for t in trades:
        eq = t.equity_after
        peak = max(peak, eq)
        max_dd = max(max_dd, (peak - eq) / peak * 100.0)
    years = max((t_end - t_start).days / 365.25, 1e-9)
    mean_r = sum(rs) / n
    sd_r = math.sqrt(sum((r - mean_r) ** 2 for r in rs) / (n - 1)) if n > 1 else 0.0
    sharpe = (mean_r / sd_r) * math.sqrt(n / years) if sd_r > 0 else 0.0

    def group(keyf):
        g: Dict[str, List[TradeResult]] = {}
        for t in trades:
            g.setdefault(keyf(t), []).append(t)
        return {k: {"n": len(v), "wr": round(100 * sum(1 for x in v if x.dollar_pnl > 0) / len(v), 1),
                    "net": round(sum(x.dollar_pnl for x in v), 2), "avg_r": round(sum(x.r_multiple for x in v) / len(v), 3)}
                for k, v in sorted(g.items())}

    return {
        "trades": n, "trades_per_year": round(n / years, 1),
        "win_rate_pct": round(100 * len(wins) / n, 1),
        "profit_factor": round(pf, 3) if pf != float("inf") else None,
        "net_pnl": round(sum(pnls), 2), "return_pct": round(100 * sum(pnls) / equity0, 2),
        "expectancy_usd": round(sum(pnls) / n, 2), "expectancy_r": round(mean_r, 3),
        "avg_win": round(gp / len(wins), 2) if wins else 0.0, "avg_loss": round(-gl / len(losses), 2) if losses else 0.0,
        "max_drawdown_pct": round(max_dd, 2), "sharpe_annualised": round(sharpe, 2),
        "scratches_abs_r_lt_0_25": sum(1 for r in rs if abs(r) < 0.25),
        "by_year": group(lambda t: t.entry_time.strftime("%Y")),
        "by_setup": group(lambda t: t.setup_type),
        "by_direction": group(lambda t: t.direction),
        "by_outcome": group(lambda t: t.outcome),
    }


def format_report(name: str, result: Dict[str, Any]) -> str:
    m = result["metrics"]
    if m.get("trades", 0) == 0:
        return f"== {name}: no trades"
    lines = [f"== {name} ==",
             f"  trades {m['trades']} ({m['trades_per_year']}/yr) | win {m['win_rate_pct']}% | PF {m['profit_factor']} | "
             f"exp {m['expectancy_usd']:+.2f}$ ({m['expectancy_r']:+.3f}R) | net {m['net_pnl']:+,.2f} ({m['return_pct']:+.2f}%) | "
             f"maxDD {m['max_drawdown_pct']}% | sharpe {m['sharpe_annualised']} | scratches {m['scratches_abs_r_lt_0_25']}"]
    if result.get("rejected_by_gate"):
        lines.append(f"  signals rejected by quarantine gate: {result['rejected_by_gate']}")
    for key in ("by_year", "by_setup", "by_direction", "by_outcome"):
        lines.append(f"  {key}: " + ", ".join(f"{k}: n={v['n']} wr={v['wr']}% net={v['net']:+.0f} avgR={v['avg_r']:+.2f}" for k, v in m[key].items()))
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--equity", type=float, default=10000.0)
    ap.add_argument("--risk", type=float, default=0.5)
    ap.add_argument("--friction", type=float, default=0.30)
    ap.add_argument("--variants", default="production,fixed_1_6r,fixed_2r,production+quarantine")
    ap.add_argument("--json-out", default=None)
    ap.add_argument("--fixed-units", type=float, default=None, help="trade a fixed $/pt size, e.g. 10 for one micro contract")
    ap.add_argument("--start", default=None, help="YYYY-MM-DD")
    ap.add_argument("--max-per-day", type=int, default=None)
    ap.add_argument("--one-per-setup", action="store_true")
    ap.add_argument("--gold-only", action="store_true")
    ap.add_argument("--stop-mult", type=float, default=1.0)
    ap.add_argument("--trend-filter", action="store_true")
    ap.add_argument("--setups", default=None, help="comma-separated allow-list, e.g. IMP_PULLBACK")
    ap.add_argument("--label", default="")
    ap.add_argument("--random", type=float, default=None, help="CONTROL: probability per London bar of a random entry")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--end", default=None, help="YYYY-MM-DD")
    args = ap.parse_args(argv)
    bars = load_bars(args.data)
    print(f"bars {len(bars)}  {bars[0].timestamp:%Y-%m-%d} .. {bars[-1].timestamp:%Y-%m-%d}  equity {args.equity:,.0f}  risk {args.risk}%  friction {args.friction} pts")
    out = {}
    for v in args.variants.split(","):
        quarantine = v.endswith("+quarantine")
        model = v.replace("+quarantine", "")
        cfg = BacktestConfig(exit_model=model, equity=args.equity, risk_pct=args.risk, friction_pts=args.friction, quarantine=quarantine, fixed_units=args.fixed_units,
                             max_trades_per_day=args.max_per_day, one_per_setup_per_day=args.one_per_setup, gold_model_only=args.gold_only,
                             stop_mult=args.stop_mult, trend_filter=args.trend_filter, random_entries=args.random, seed=args.seed,
                             setups=tuple(x.strip() for x in args.setups.split(",")) if args.setups else None)
        start = datetime.datetime.fromisoformat(args.start).replace(tzinfo=UTC) if args.start else None
        end = datetime.datetime.fromisoformat(args.end).replace(tzinfo=UTC) if args.end else None
        res = run_backtest(bars, cfg, start=start, end=end)
        print(format_report((args.label + " " if args.label else "") + v, res), flush=True)
        out[v] = {"metrics": res["metrics"], "rejected_by_gate": res["rejected_by_gate"], "final_equity": res["final_equity"]}
    if args.json_out:
        with open(args.json_out, "w") as f:
            json.dump(out, f, indent=2, default=str)


if __name__ == "__main__":
    main()
