"""
Strategy lab: test any trading idea on the saved real market data with one fixed, honest
procedure. You write a short strategy file; the lab loads the data, runs it, charges costs,
compares it with random controls, checks it for look-ahead, and writes a report.

DATA (all local, nothing is downloaded during a test)
  real_data/market_history.db  Binance 1m candles for 12 coins (with buyer-initiated volume),
                               Polymarket 5m rounds and Up-price history (BTC ETH SOL XRP)
  real_data/slow/              daily perp closes and every funding settlement since 2019
  Refresh both with:  python3 -m research.lab update

TWO KINDS OF STRATEGY (copy research/strategies/TEMPLATE_position.py or TEMPLATE_polymarket.py)
  position    signal(df) -> target position per bar in [-1, +1] for one coin
              (+1 fully long, -1 fully short, 0 flat). Runs on every coin in COINS, equal weight
              1/N per coin, no leverage. TIMEFRAME 1m 5m 15m 1h 4h 1d; HISTORY = "long" with
              1d uses the daily closes back to 2019 instead of the 6 months of 1m data.
  polymarket  decide(ctx) -> "UP" / "DOWN" / None for each 5-minute round, CHECKPOINT seconds
              before the close. Bets $1 at the market price + 1c spread + the taker fee.

FIXED PROCEDURE (the same for every strategy; it is not tuned per idea)
  Execution   a position decided at the close of bar i earns bar i+1's return. Costs 0.07% of
              notional per side (0.05% taker + 0.02% slippage) on every change, including the
              final close. Funding: every settlement is charged to the position held over it
              (a long pays positive funding).
  Polymarket  the saved Up-price points are about one per minute, so the price at CHECKPOINT is
              the latest point at or before it (on average ~48 s older). The decision is made AT
              THAT POINT'S TIME: the strategy sees only candles that closed by then. (Giving it
              candles up to the checkpoint instead lets it bet at a stale price with newer
              information: a fake +20% per bet, found while building the lab.)
              Bet price = that Up price + 0.01, fee 0.07 * p * (1 - p) per share, held to the
              official outcome.
  Look-ahead  position signals are recomputed on data cut at 50% and 75%; any change in the
              earlier values means the signal peeks at the future -> automatic FAIL.
              Polymarket ctx only contains candles that closed by the time of the price used.
  Controls    position: 200 runs with each coin's signal rotated in time by a random offset
              (same trades, same exposure, wrong timing). Polymarket: 200 runs with the same
              bets on a coin-flip side.
  Holdout     the last third of the period is reported on its own.
  PASS        all of:
                1. net result after all costs > 0
                2. above the 95th percentile of the 200 controls
                3. the last third (holdout) is also > 0
                4. 95% bootstrap interval of the mean daily return (position, 5-day blocks) or
                   of the mean bet (polymarket, resampling whole days) is above 0
                5. at least 60% of calendar months positive
                6. enough activity: >= 20 entries (position) or >= 100 bets (polymarket)
  Ledger      every full run is appended to docs/lab/ledger.jsonl. Testing many ideas makes a
              lucky pass likely, so the report says how many variants have been tried.

WORKFLOW
  1. copy a template into research/strategies/, write the hypothesis first
  2. iterate on the first two thirds only:  python3 -m research.lab run my_idea --part dev
  3. when it is final, run once on everything:  python3 -m research.lab run my_idea
     (only this run judges it; the last third was never used while iterating)
  Other: python3 -m research.lab data | update | ledger
         python3 -m research.lab run my_idea --set n=50 --coins BTC,ETH

Research only: reads local files, places no orders.
"""

import argparse
import ast
import hashlib
import importlib.util
import json
import math
import os
import sqlite3
import sys
import time
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HISTORY_DB = os.environ.get("MARKET_HISTORY_DB", os.path.join(ROOT, "real_data", "market_history.db"))
SLOW_DIR = os.path.join(ROOT, "real_data", "slow")
STRATEGY_DIR = os.path.join(ROOT, "research", "strategies")
REPORT_DIR = os.path.join(ROOT, "docs", "lab")
LEDGER = os.path.join(REPORT_DIR, "ledger.jsonl")

ALL_COINS = ["BTC", "ETH", "SOL", "XRP", "BNB", "DOGE", "ZEC", "HYPE", "NEAR", "SUI", "ADA", "LINK"]
PM_COINS = ["BTC", "ETH", "SOL", "XRP"]
TF_SECONDS = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}
DAY = 86400
COST = 0.0007
PM_SPREAD = 0.01
PM_LOOKBACK = 240
N_CONTROLS = 200
LOOKAHEAD_CUTS = (0.5, 0.75)
MIN_ENTRIES = 20
MIN_BETS = 100
MONTHS_POSITIVE = 0.6


# ============================================================== data

def _ffill2d(a: np.ndarray) -> np.ndarray:
    """Forward-fill NaNs down each column."""
    out = a.copy()
    for j in range(out.shape[1]):
        col = out[:, j]
        ok = ~np.isnan(col)
        if not ok.any():
            continue
        idx = np.where(ok, np.arange(len(col)), 0)
        np.maximum.accumulate(idx, out=idx)
        filled = col[idx]
        filled[: np.argmax(ok)] = np.nan
        out[:, j] = filled
    return out


def resample(t: np.ndarray, o, h, l, c, v, bv, tf_sec: int) -> pd.DataFrame:
    """1-minute candles (open times in seconds) -> tf candles. Candles with a missing minute are dropped."""
    df = pd.DataFrame({"o": o, "h": h, "l": l, "c": c, "volume": v, "buy_volume": bv}, index=np.asarray(t, dtype=np.int64))
    if tf_sec == 60:
        out = df
    else:
        g = df.groupby(df.index // tf_sec * tf_sec)
        out = pd.DataFrame({"o": g.o.first(), "h": g.h.max(), "l": g.l.min(), "c": g.c.last(),
                            "volume": g.volume.sum(), "buy_volume": g.buy_volume.sum()})
        out = out[g.size() == tf_sec // 60]
    out.index.name = "t"
    return out


def funding_for_bars(bar_t: np.ndarray, tf_sec: int, f_t: np.ndarray, f_r: np.ndarray) -> np.ndarray:
    """Sum of the funding settlements in (bar open, bar open + tf] for each bar."""
    bar_t = np.asarray(bar_t, dtype=np.int64)
    out = np.zeros(len(bar_t))
    if len(f_t) == 0 or len(bar_t) == 0:
        return out
    f_t = np.asarray(f_t, dtype=np.int64)
    idx = np.searchsorted(bar_t, f_t, side="left") - 1
    ok = (idx >= 0) & (f_t <= bar_t[np.clip(idx, 0, None)] + tf_sec)
    np.add.at(out, idx[ok], np.asarray(f_r, dtype=float)[ok])
    return out


def _slow(kind: str, coin: str) -> np.ndarray:
    path = os.path.join(SLOW_DIR, f"{kind}_{coin}USDT.json")
    if not os.path.exists(path):
        return np.zeros((0, 2))
    with open(path) as f:
        return np.array(json.load(f), dtype=float).reshape(-1, 2)


@lru_cache(maxsize=64)
def _bars_cached(coin: str, timeframe: str, long: bool) -> pd.DataFrame:
    tf = TF_SECONDS[timeframe]
    fund = _slow("funding", coin)
    if long:
        if timeframe != "1d":
            raise ValueError('HISTORY = "long" exists only for TIMEFRAME = "1d"')
        perp = _slow("perp", coin)
        t, c = perp[:, 0].astype(np.int64), perp[:, 1]
        keep = t + DAY <= time.time()
        df = pd.DataFrame({"o": np.nan, "h": np.nan, "l": np.nan, "c": c[keep], "volume": np.nan, "buy_volume": np.nan},
                          index=pd.Index(t[keep], name="t"))
    else:
        with sqlite3.connect(HISTORY_DB) as conn:
            rows = conn.execute("SELECT t, o, h, l, c, volume, taker_buy_base FROM binance_1m WHERE symbol=? ORDER BY t",
                                (f"{coin}USDT",)).fetchall()
        if not rows:
            return pd.DataFrame()
        a = np.array(rows, dtype=float)
        df = resample(a[:, 0].astype(np.int64), a[:, 1], a[:, 2], a[:, 3], a[:, 4], a[:, 5], a[:, 6], tf)
    df["funding"] = funding_for_bars(df.index.values, tf, fund[:, 0], fund[:, 1])
    df.index = pd.to_datetime(df.index.values, unit="s", utc=True)
    df.index.name = "time"
    return df


def bars(coin: str, timeframe: str = "1h", long: bool = False) -> pd.DataFrame:
    """Candles for one coin: columns o h l c volume buy_volume funding, UTC open-time index.
    buy_volume = buyer-initiated (taker buy) volume; sell volume = volume - buy_volume."""
    return _bars_cached(coin, timeframe, long).copy()


@dataclass
class PMData:
    rounds: pd.DataFrame                 # coin, round_ts, outcome, price_to_beat, t_point, p_up
    minutes: Dict[str, Tuple[np.ndarray, ...]]   # coin -> (t, o, h, l, c, volume, buy_volume[, coinbase close])


def load_pm(coins: Sequence[str], checkpoint: int) -> PMData:
    """Resolved rounds with the Up price at the decision time (the latest point at or before it,
    at most 90 s old) and the Binance minutes for each coin."""
    marks = ",".join("?" * len(coins))
    with sqlite3.connect(HISTORY_DB) as conn:
        rounds = pd.read_sql(f"SELECT coin, round_ts, outcome, price_to_beat FROM pm_rounds "
                             f"WHERE outcome IN ('UP','DOWN') AND coin IN ({marks})", conn, params=tuple(coins))
        pts = pd.read_sql(f"SELECT coin, round_ts, MAX(t) AS t_point, p_up FROM pm_prices "
                          f"WHERE coin IN ({marks}) AND t <= round_ts + ? AND t > round_ts + ? GROUP BY coin, round_ts",
                          conn, params=tuple(coins) + (300 - checkpoint, 300 - checkpoint - 90))
        minutes = {}
        for coin in coins:
            a = np.array(conn.execute("SELECT t, o, h, l, c, volume, taker_buy_base FROM binance_1m WHERE symbol=? ORDER BY t",
                                      (f"{coin}USDT",)).fetchall(), dtype=float)
            if not len(a):
                minutes[coin] = tuple(np.zeros(0) for _ in range(8))
                continue
            cb = np.array(conn.execute("SELECT t, c FROM coinbase_1m WHERE product=? ORDER BY t", (f"{coin}-USD",)).fetchall(),
                          dtype=float).reshape(-1, 2)
            cb_close = np.full(len(a), np.nan)
            if len(cb):          # Coinbase close of the same minute; a missing minute keeps the previous close
                j = np.searchsorted(cb[:, 0], a[:, 0], side="right") - 1
                ok = j >= 0
                cb_close[ok] = cb[j[ok], 1]
            minutes[coin] = tuple(a[:, k] for k in range(7)) + (cb_close,)
    df = rounds.merge(pts, on=["coin", "round_ts"])
    df = df[(df.p_up > 0) & (df.p_up < 1)].sort_values(["round_ts", "coin"]).reset_index(drop=True)
    return PMData(df, minutes)


def closed_minutes_end(minute_t: np.ndarray, t_decision: float) -> int:
    """Index one past the last 1m candle that has closed by t_decision (open time + 60 <= t_decision)."""
    return int(np.searchsorted(minute_t, t_decision - 60, side="right"))


# ============================================================== position engine

@dataclass
class PosResult:
    t_close: np.ndarray        # bar close times (s)
    ret: np.ndarray            # portfolio return per bar, after costs and funding
    by_coin: np.ndarray        # net contribution per coin (sum over bars)
    entries: int
    exposure: float            # average share of bars with a position, over active bars
    cost_paid: float


def run_positions(t_open: np.ndarray, tf_sec: int, closes: np.ndarray, signals: np.ndarray, funding: np.ndarray,
                  active: np.ndarray, cost: float = COST) -> PosResult:
    """closes/signals/funding/active: T x N. signals[i] is the position taken at the close of bar i
    (held over bar i+1). Each coin has weight 1/N."""
    T, N = closes.shape
    w = 1.0 / N
    c = _ffill2d(closes)
    R = np.zeros((T, N))
    R[1:] = c[1:] / c[:-1] - 1
    R = np.where(active & np.vstack([np.zeros((1, N), bool), active[:-1]]), np.nan_to_num(R), 0.0)
    S = np.where(active, np.clip(np.nan_to_num(signals), -1, 1), 0.0)
    held = np.vstack([np.zeros((1, N)), S[:-1]])
    gross = w * held * (R - np.nan_to_num(funding))
    prev = np.vstack([np.zeros((1, N)), S[:-1]])
    costs = w * cost * np.abs(S - prev)
    costs[-1] += w * cost * np.abs(S[-1])
    net = gross - costs
    sgn, psgn = np.sign(S), np.sign(prev)
    entries = int(((sgn != 0) & (sgn != psgn)).sum())
    act = active.sum()
    exposure = float((np.abs(held) > 0).sum() / act) if act else 0.0
    return PosResult(np.asarray(t_open, np.int64) + tf_sec, net.sum(axis=1), net.sum(axis=0), entries, exposure,
                     float(costs.sum()))


def rotate_signals(signals: np.ndarray, active: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Control: rotate each coin's signal inside its active span by a random 10%..90% offset."""
    out = np.zeros_like(signals)
    for j in range(signals.shape[1]):
        idx = np.flatnonzero(active[:, j])
        if len(idx) < 10:
            continue
        k = int(rng.integers(max(1, len(idx) // 10), max(2, len(idx) * 9 // 10)))
        out[idx, j] = np.roll(signals[idx, j], k)
    return out


def _as_signal(raw: Any, df: pd.DataFrame) -> np.ndarray:
    if isinstance(raw, pd.Series):
        raw = raw.reindex(df.index).values
    arr = np.asarray(raw, dtype=float).reshape(-1)
    if len(arr) != len(df):
        raise ValueError(f"signal() returned {len(arr)} values for {len(df)} bars")
    return arr


def lookahead_check(signal_fn: Callable, df: pd.DataFrame, params: Dict) -> Optional[str]:
    """Recompute the signal on truncated data; earlier values must not change."""
    full = _as_signal(signal_fn(df.copy(), **params), df)
    for frac in LOOKAHEAD_CUTS:
        k = int(len(df) * frac)
        if k < 50:
            continue
        part = _as_signal(signal_fn(df.iloc[:k].copy(), **params), df.iloc[:k])
        a, b = np.nan_to_num(full[:k], nan=-9e9), np.nan_to_num(part, nan=-9e9)
        bad = np.flatnonzero(~np.isclose(a, b, atol=1e-9))
        if len(bad):
            return f"signal at {df.index[bad[0]]} changes when later data is removed (cut at {frac:.0%})"
    return None


# ============================================================== stats

def daily_returns(t_close: np.ndarray, ret: np.ndarray) -> pd.Series:
    day = (np.asarray(t_close, np.int64) - 1) // DAY * DAY
    s = pd.Series(np.log1p(ret)).groupby(day).sum()
    out = np.expm1(s)
    out.index = pd.to_datetime(out.index.values, unit="s", utc=True)
    return out


def month_table(daily: pd.Series) -> Dict[str, float]:
    g = (1 + daily).groupby(daily.index.strftime("%Y-%m")).prod() - 1
    return {k: float(v) for k, v in g.items()}


def block_bootstrap_mean(x: np.ndarray, block: int = 5, n_boot: int = 2000, seed: int = 0) -> Tuple[float, float]:
    x = np.asarray(x, float)
    n = len(x)
    if n < 2 * block:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    nb = math.ceil(n / block)
    starts = rng.integers(0, n - block + 1, size=(n_boot, nb))
    idx = (starts[:, :, None] + np.arange(block)).reshape(n_boot, -1)[:, :n]
    means = x[idx].mean(axis=1)
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def cluster_bootstrap_mean(x: np.ndarray, clusters: np.ndarray, n_boot: int = 2000, seed: int = 0) -> Tuple[float, float]:
    g = pd.DataFrame({"x": x, "c": clusters}).groupby("c")["x"].agg(["sum", "count"])
    s, n = g["sum"].values, g["count"].values
    if len(s) < 5:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(s), size=(n_boot, len(s)))
    m = s[idx].sum(axis=1) / n[idx].sum(axis=1)
    return float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))


def perf(daily: pd.Series) -> Dict[str, float]:
    r = daily.values
    if len(r) == 0:
        return dict(total=0.0, cagr=0.0, sharpe=0.0, dd=0.0, days=0)
    eq = np.cumprod(1 + r)
    yrs = len(r) / 365.0
    sd = r.std()
    return dict(total=float(eq[-1] - 1), cagr=float(eq[-1] ** (1 / yrs) - 1) if eq[-1] > 0 else -1.0,
                sharpe=float(r.mean() / sd * math.sqrt(365)) if sd > 0 else 0.0,
                dd=float((1 - eq / np.maximum.accumulate(eq)).max()), days=len(r))


def pct(x: float, d: int = 1) -> str:
    return "n/a" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{100 * x:+.{d}f}%"


# ============================================================== strategy loading

@dataclass
class Strategy:
    module: Any
    path: str
    name: str
    kind: str
    params: Dict[str, Any]
    sha1: str


def load_strategy(ref: str, overrides: Dict[str, Any]) -> Strategy:
    path = ref
    if not os.path.exists(path):
        path = os.path.join(STRATEGY_DIR, ref if ref.endswith(".py") else ref + ".py")
    if not os.path.exists(path):
        raise SystemExit(f"strategy not found: {ref}")
    spec = importlib.util.spec_from_file_location(f"lab_strategy_{os.path.basename(path)[:-3]}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    kind = getattr(mod, "KIND", "position")
    if kind not in ("position", "polymarket"):
        raise SystemExit(f"KIND must be 'position' or 'polymarket', got {kind!r}")
    fn = "signal" if kind == "position" else "decide"
    if not callable(getattr(mod, fn, None)):
        raise SystemExit(f"a {kind} strategy must define {fn}()")
    params = dict(getattr(mod, "PARAMS", {}))
    unknown = set(overrides) - set(params)
    if unknown:
        raise SystemExit(f"--set names not in PARAMS: {sorted(unknown)}")
    params.update(overrides)
    with open(path, "rb") as f:
        sha = hashlib.sha1(f.read()).hexdigest()[:12]
    name = getattr(mod, "NAME", os.path.basename(path)[:-3])
    return Strategy(mod, path, name, kind, params, sha)


# ============================================================== runs

@dataclass
class Report:
    title: str
    lines: List[str] = field(default_factory=list)
    criteria: List[Tuple[str, bool, str]] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return bool(self.criteria) and all(ok for _, ok, _ in self.criteria)


def _split(t_close: np.ndarray) -> float:
    """Start of the holdout (last third) in seconds."""
    t0, t1 = float(t_close.min()), float(t_close.max())
    return t0 + (t1 - t0) * 2 / 3


def run_position_strategy(st: Strategy, coins: Sequence[str], part: str, n_controls: int = N_CONTROLS,
                          data: Optional[Dict[str, pd.DataFrame]] = None) -> Report:
    mod = st.module
    timeframe = getattr(mod, "TIMEFRAME", "1h")
    long = getattr(mod, "HISTORY", "") == "long"
    tf = TF_SECONDS[timeframe]
    frames = data if data is not None else {c: bars(c, timeframe, long) for c in coins}
    frames = {c: df for c, df in frames.items() if len(df) > 0}
    if not frames:
        raise SystemExit("no data for these coins")
    if part == "dev":
        t_all = np.concatenate([df.index.asi8 // 10**9 for df in frames.values()])
        cut = t_all.min() + (t_all.max() - t_all.min()) * 2 / 3
        frames = {c: df[df.index.asi8 // 10**9 < cut] for c, df in frames.items()}

    warning = lookahead_check(mod.signal, next(iter(frames.values())), st.params)
    sigs = {c: _as_signal(mod.signal(df.copy(), **st.params), df) for c, df in frames.items()}

    grid = np.unique(np.concatenate([df.index.asi8 // 10**9 for df in frames.values()]))
    names = list(frames)
    T, N = len(grid), len(names)
    closes, signals, funding = np.full((T, N), np.nan), np.full((T, N), np.nan), np.zeros((T, N))
    active = np.zeros((T, N), bool)
    for j, c in enumerate(names):
        df = frames[c]
        pos = np.searchsorted(grid, df.index.asi8 // 10**9)
        closes[pos, j] = df.c.values
        signals[pos, j] = sigs[c]
        funding[pos, j] = df.funding.values
        active[pos[0]:pos[-1] + 1, j] = True
    signals = np.where(active, _ffill2d(signals), 0.0)

    res = run_positions(grid, tf, closes, signals, funding, active)
    daily = daily_returns(res.t_close, res.ret)
    hold_start = _split(res.t_close)
    hold_mask = daily.index.asi8 // 10**9 >= int(hold_start) // DAY * DAY
    full, dev, hold = perf(daily), perf(daily[~hold_mask]), perf(daily[hold_mask])
    months = month_table(daily)
    lo, hi = block_bootstrap_mean(daily.values)

    rng = np.random.default_rng(7)
    ctrl = []
    for _ in range(n_controls):
        r = run_positions(grid, tf, closes, rotate_signals(signals, active, rng), funding, active)
        ctrl.append(float(np.prod(1 + r.ret) - 1))
    ctrl = np.array(ctrl)
    p95 = float(np.percentile(ctrl, 95)) if len(ctrl) else float("nan")
    rank = float((ctrl < full["total"]).mean()) if len(ctrl) else float("nan")
    bh = run_positions(grid, tf, closes, active.astype(float), funding, active)
    bh_total = float(np.prod(1 + bh.ret) - 1)

    span = f"{pd.to_datetime(grid[0], unit='s'):%Y-%m-%d} .. {pd.to_datetime(res.t_close[-1], unit='s'):%Y-%m-%d}"
    rep = Report(f"{st.name} ({'dev: first two thirds only' if part == 'dev' else 'full run'})")
    pos_months = sum(v > 0 for v in months.values())
    need = math.ceil(MONTHS_POSITIVE * len(months))
    rep.criteria = [
        ("no look-ahead", warning is None, warning or "signal unchanged when later data is removed"),
        ("net result > 0", full["total"] > 0, pct(full["total"])),
        ("beats 95th pct of random-timing controls", n_controls > 0 and full["total"] > p95,
         f"{pct(full['total'])} vs {pct(p95)} (better than {rank:.0%} of {n_controls})"),
        ("last third > 0" if part == "full" else "last third of dev span > 0", hold["total"] > 0, pct(hold["total"])),
        ("bootstrap 95% CI of mean daily return > 0", not math.isnan(lo) and lo > 0,
         f"({pct(lo * 365)}, {pct(hi * 365)}) a year"),
        (f">= {MONTHS_POSITIVE:.0%} of months positive", pos_months >= need, f"{pos_months}/{len(months)} (need {need})"),
        (f">= {MIN_ENTRIES} entries", res.entries >= MIN_ENTRIES, str(res.entries)),
    ]
    L = rep.lines
    L += [f"Kind: position | timeframe {timeframe}{' (long daily history)' if long else ''} | coins {', '.join(names)} | "
          f"{span} ({full['days']} days)",
          f"Params: {json.dumps(st.params)} | file {os.path.relpath(st.path, ROOT)} @ {st.sha1}",
          f"Costs: {COST:.2%} per side on every change, funding charged | weight 1/{N} per coin, no leverage", ""]
    L += ["| | net | CAGR | Sharpe | max DD | days |", "|---|---|---|---|---|---|"]
    for label, p in (("whole period", full), ("first two thirds", dev), ("last third", hold)):
        L.append(f"| {label} | {pct(p['total'])} | {pct(p['cagr'])} | {p['sharpe']:.2f} | {pct(-p['dd'])} | {p['days']} |")
    L += ["", f"Entries {res.entries} | time in market {res.exposure:.0%} | costs paid {pct(res.cost_paid, 2)} of capital | "
          f"buy-and-hold of the same coins {pct(bh_total)}",
          f"Random-timing controls ({n_controls}): median {pct(float(np.median(ctrl)) if len(ctrl) else float('nan'))}, "
          f"95th pct {pct(p95)}", "",
          "Months: " + "  ".join(f"{k} {pct(v)}" for k, v in months.items()), "",
          "By coin (sum of net contributions): " + "  ".join(f"{c} {pct(x, 2)}" for c, x in zip(names, res.by_coin))]
    rep.summary = dict(net=full["total"], sharpe=full["sharpe"], dd=full["dd"], holdout=hold["total"], entries=res.entries,
                       control_p95=p95, buy_hold=bh_total)
    return rep


class Ctx:
    """What a Polymarket strategy sees at the decision time (= the time of the price it trades at).
    Arrays run oldest -> newest and hold the last LOOKBACK (default PM_LOOKBACK) Binance 1m candles that
    CLOSED by then; `t` holds their open times (s)."""
    __slots__ = ("coin", "round_ts", "t_decision", "secs_left", "p_up", "price_to_beat", "t",
                 "open", "high", "low", "close", "volume", "buy_volume", "cb_close", "hour", "weekday")

    def __repr__(self):
        return f"Ctx({self.coin} round {self.round_ts} p_up={self.p_up:.3f} candles={len(self.close)})"


def pm_bet_pnl(side: str, p_up: float, outcome_up: bool, spread: float = PM_SPREAD) -> Optional[float]:
    """$1 on `side` at the market price + spread, taker fee, held to the outcome. None if unbuyable."""
    price = (p_up if side == "UP" else 1 - p_up) + spread
    if not (0.01 < price < 0.99):
        return None
    shares = 1.0 / price
    won = outcome_up == (side == "UP")
    return shares * won - 1.0 - shares * 0.07 * price * (1 - price)


def run_polymarket_strategy(st: Strategy, coins: Sequence[str], part: str, n_controls: int = N_CONTROLS,
                            data: Optional[PMData] = None) -> Report:
    mod = st.module
    cp = int(getattr(mod, "CHECKPOINT", 120))
    if not 30 <= cp <= 280:
        raise SystemExit("CHECKPOINT must be between 30 and 280 seconds before the close")
    lookback = int(getattr(mod, "LOOKBACK", PM_LOOKBACK))     # 1m candles handed to decide()
    pm = data if data is not None else load_pm(coins, cp)
    df = pm.rounds
    if part == "dev":
        cut = df.round_ts.min() + (df.round_ts.max() - df.round_ts.min()) * 2 / 3
        df = df[df.round_ts < cut]
    bets = []
    ctx = Ctx()
    for r in df.itertuples(index=False):
        mt = pm.minutes.get(r.coin)
        t_dec = int(r.t_point)          # decide when the traded price was observed, never later
        k = closed_minutes_end(mt[0], t_dec) if mt is not None and len(mt[0]) else 0
        a = max(0, k - lookback)
        ctx.coin, ctx.round_ts, ctx.t_decision, ctx.secs_left = r.coin, int(r.round_ts), t_dec, int(r.round_ts) + 300 - t_dec
        ctx.p_up, ctx.price_to_beat = float(r.p_up), float(r.price_to_beat) if r.price_to_beat is not None else float("nan")
        if mt is not None and len(mt[0]):
            ctx.t = mt[0][a:k]
            ctx.open, ctx.high, ctx.low, ctx.close, ctx.volume, ctx.buy_volume = (x[a:k] for x in mt[1:7])
            ctx.cb_close = mt[7][a:k] if len(mt) > 7 else np.full(k - a, np.nan)
        else:
            ctx.t = ctx.open = ctx.high = ctx.low = ctx.close = ctx.volume = ctx.buy_volume = ctx.cb_close = np.zeros(0)
        tm = time.gmtime(t_dec)
        ctx.hour, ctx.weekday = tm.tm_hour, tm.tm_wday
        side = mod.decide(ctx, **st.params)
        if side not in ("UP", "DOWN"):
            continue
        up = r.outcome == "UP"
        pnl = pm_bet_pnl(side, r.p_up, up)
        if pnl is None:
            continue
        alt = pm_bet_pnl("DOWN" if side == "UP" else "UP", r.p_up, up)
        bets.append((r.coin, int(r.round_ts), side, float(r.p_up), up, pnl, alt))
    b = pd.DataFrame(bets, columns=["coin", "round_ts", "side", "p_up", "up", "pnl", "alt"])
    rep = Report(f"{st.name} ({'dev: first two thirds only' if part == 'dev' else 'full run'})")
    L = rep.lines
    span = f"{pd.to_datetime(df.round_ts.min(), unit='s'):%Y-%m-%d} .. {pd.to_datetime(df.round_ts.max(), unit='s'):%Y-%m-%d}"
    L += [f"Kind: polymarket | decision {cp}s before the close | coins {', '.join(coins)} | {span} | {len(df)} rounds",
          f"Params: {json.dumps(st.params)} | file {os.path.relpath(st.path, ROOT)} @ {st.sha1}",
          f"Bet: $1 at the market Up/Down price + {PM_SPREAD:.2f} spread, taker fee 0.07*p*(1-p) per share, held to the outcome", ""]
    if b.empty:
        rep.criteria = [(f">= {MIN_BETS} bets", False, "0")]
        L.append("No bets were placed.")
        rep.summary = dict(net=0.0, bets=0)
        return rep
    n = len(b)
    total = float(b.pnl.sum())
    day = (b.round_ts // DAY).values
    lo, hi = cluster_bootstrap_mean(b.pnl.values, day)
    cut = df.round_ts.min() + (df.round_ts.max() - df.round_ts.min()) * 2 / 3
    hold = b[b.round_ts >= cut]
    first = b[b.round_ts < cut]
    months = b.groupby(pd.to_datetime(b.round_ts, unit="s").dt.strftime("%Y-%m")).pnl.sum()
    rng = np.random.default_rng(7)
    alt = b.alt.fillna(0.0).values
    flip = rng.random((n_controls, n)) < 0.5
    ctrl = np.where(flip, alt[None, :], b.pnl.values[None, :]).sum(axis=1)
    p95 = float(np.percentile(ctrl, 95))
    rank = float((ctrl < total).mean())
    pos_months = int((months > 0).sum())
    need = math.ceil(MONTHS_POSITIVE * len(months))
    rep.criteria = [
        ("net result > 0", total > 0, f"{total:+.2f} on {n} bets of $1 ({total / n:+.2%} per bet)"),
        ("beats 95th pct of coin-flip-side controls", total > p95, f"{total:+.2f} vs {p95:+.2f} (better than {rank:.0%})"),
        ("last third > 0", hold.pnl.sum() > 0, f"{hold.pnl.sum():+.2f} on {len(hold)} bets"),
        ("bootstrap 95% CI of mean bet > 0 (whole days resampled)", not math.isnan(lo) and lo > 0, f"({lo:+.2%}, {hi:+.2%})"),
        (f">= {MONTHS_POSITIVE:.0%} of months positive", pos_months >= need, f"{pos_months}/{len(months)} (need {need})"),
        (f">= {MIN_BETS} bets", n >= MIN_BETS, str(n)),
    ]
    wins = b.pnl > 0
    L += ["| | bets | win rate | avg price paid | P&L | per bet |", "|---|---|---|---|---|---|"]
    for label, g in (("all", b), ("first two thirds", first), ("last third", hold)):
        if len(g):
            paid = np.where(g.side == "UP", g.p_up, 1 - g.p_up) + PM_SPREAD
            L.append(f"| {label} | {len(g)} | {(g.pnl > 0).mean():.1%} | {paid.mean():.3f} | {g.pnl.sum():+.2f} | {g.pnl.mean():+.2%} |")
    L += ["", f"Bet on {n / len(df):.1%} of rounds | UP {int((b.side == 'UP').sum())} / DOWN {int((b.side == 'DOWN').sum())} | "
          f"win rate {wins.mean():.1%}",
          f"Coin-flip-side controls ({n_controls}): median {float(np.median(ctrl)):+.2f}, 95th pct {p95:+.2f}", "",
          "Months: " + "  ".join(f"{k} {v:+.2f}" for k, v in months.items()), "",
          "By coin: " + "  ".join(f"{c} {g.pnl.sum():+.2f} ({len(g)})" for c, g in b.groupby("coin"))]
    rep.summary = dict(net=total, bets=n, per_bet=total / n, holdout=float(hold.pnl.sum()), control_p95=p95)
    return rep


# ============================================================== ledger & output

def ledger_rows() -> List[Dict]:
    if not os.path.exists(LEDGER):
        return []
    with open(LEDGER) as f:
        return [json.loads(x) for x in f if x.strip()]


def write_outputs(st: Strategy, rep: Report, part: str, coins: Sequence[str]) -> Tuple[str, str]:
    os.makedirs(REPORT_DIR, exist_ok=True)
    prior = ledger_rows()
    tf_label = getattr(st.module, "TIMEFRAME", "1h") if st.kind == "position" else f"cp{getattr(st.module, 'CHECKPOINT', 120)}"
    entry = dict(time=time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()), name=st.name, kind=st.kind, timeframe=tf_label,
                 file=os.path.relpath(st.path, ROOT), sha1=st.sha1, params=st.params, coins=list(coins), part=part,
                 passed=rep.passed, **{k: (round(v, 6) if isinstance(v, float) else v) for k, v in rep.summary.items()})
    if part == "full":
        with open(LEDGER, "a") as f:
            f.write(json.dumps(entry) + "\n")
    full_runs = [r for r in prior if r.get("part") == "full"] + ([entry] if part == "full" else [])
    variants = {(r["name"], r["sha1"], json.dumps(r["params"], sort_keys=True), tuple(r["coins"]), r.get("timeframe"))
                for r in full_runs}
    same = {v for v in variants if v[0] == st.name}
    out = [f"# Lab: {rep.title}", "", f"Run {entry['time']}. Research only: no orders are placed.", ""]
    hyp = getattr(st.module, "HYPOTHESIS", "").strip()
    if hyp:
        out += [f"Hypothesis: {hyp}", ""]
    out += [f"## Verdict: {'PASS' if rep.passed else 'FAIL'}", "", "| criterion | result | detail |", "|---|---|---|"]
    out += [f"| {name} | {'yes' if ok else 'NO'} | {detail} |" for name, ok, detail in rep.criteria]
    out += ["", "## Detail", ""] + rep.lines + [""]
    if part == "full":
        out += ["## How many tries", "",
                f"Full runs of '{st.name}' with distinct code/params/coins: {len(same)}. Distinct variants of all ideas "
                f"run in the lab: {len(variants)}.",
                "Every extra variant is another lottery ticket: if you try enough worthless ideas, some will pass by luck. "
                "Treat a pass found after many tries as a lead for a forward paper test, not as proof.", ""]
    else:
        out += ["Dev run: the last third of the data was not used. Not recorded in the ledger. When the idea is final, "
                "run it once without --part dev to judge it.", ""]
    text = "\n".join(out)
    suffix = f"__{tf_label}" + ("" if not st.params else "__" + "_".join(f"{k}-{v}" for k, v in sorted(st.params.items())))
    path = os.path.join(REPORT_DIR, f"{st.name}{suffix}{'__dev' if part == 'dev' else ''}.md".replace("/", "-").replace(" ", ""))
    with open(path, "w") as f:
        f.write(text)
    return text, path


def data_summary() -> str:
    lines = ["Saved data available to the lab:"]
    if os.path.exists(HISTORY_DB):
        with sqlite3.connect(HISTORY_DB) as c:
            for sym, n, a, b in c.execute("SELECT symbol, COUNT(*), MIN(t), MAX(t) FROM binance_1m GROUP BY symbol"):
                lines.append(f"  1m candles   {sym:<9} {n:>7}  {time.strftime('%Y-%m-%d', time.gmtime(a))} .. "
                             f"{time.strftime('%Y-%m-%d %H:%M', time.gmtime(b))}")
            for coin, n, a, b in c.execute("SELECT coin, COUNT(*), MIN(round_ts), MAX(round_ts) FROM pm_rounds "
                                           "WHERE outcome IS NOT NULL GROUP BY coin"):
                lines.append(f"  PM rounds    {coin:<9} {n:>7}  {time.strftime('%Y-%m-%d', time.gmtime(a))} .. "
                             f"{time.strftime('%Y-%m-%d %H:%M', time.gmtime(b))}")
    for coin in ALL_COINS:
        p = _slow("perp", coin)
        if len(p):
            lines.append(f"  daily (long) {coin + 'USDT':<9} {len(p):>7}  {time.strftime('%Y-%m-%d', time.gmtime(p[0, 0]))} .. "
                         f"{time.strftime('%Y-%m-%d', time.gmtime(p[-1, 0]))}")
    return "\n".join(lines)


def _parse_set(items: Sequence[str]) -> Dict[str, Any]:
    out = {}
    for it in items or []:
        k, _, v = it.partition("=")
        try:
            out[k.strip()] = ast.literal_eval(v.strip())
        except (ValueError, SyntaxError):
            out[k.strip()] = v.strip()
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python3 -m research.lab", description="Test a strategy on the saved real data.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="run a strategy file")
    r.add_argument("strategy", help="path, or a name in research/strategies/")
    r.add_argument("--part", choices=("full", "dev"), default="full", help="dev = first two thirds only (for iterating)")
    r.add_argument("--coins", help="comma list, overrides the strategy's COINS")
    r.add_argument("--set", nargs="*", metavar="NAME=VALUE", help="override PARAMS")
    r.add_argument("--controls", type=int, default=N_CONTROLS)
    r.add_argument("--timeframe", choices=sorted(TF_SECONDS, key=TF_SECONDS.get), help="position strategies: override TIMEFRAME")
    sub.add_parser("data", help="show the saved data")
    sub.add_parser("ledger", help="list every full run so far")
    sub.add_parser("update", help="top up the saved data from the public APIs")
    args = ap.parse_args(argv)

    if args.cmd == "data":
        print(data_summary())
        return 0
    if args.cmd == "ledger":
        rows = ledger_rows()
        if not rows:
            print("No full runs yet.")
        for x in rows:
            res = (f"{x.get('net', 0.0):+.2f} on {x.get('bets', 0)} bets" if x.get("kind") == "polymarket"
                   else pct(x.get("net", 0.0)))
            print(f"{x['time']}  {'PASS' if x['passed'] else 'fail'}  {x['name']:<28} {x.get('timeframe', ''):<6} net {res}  "
                  f"params {json.dumps(x['params'])}  coins {','.join(x['coins'])}")
        return 0
    if args.cmd == "update":
        from market_data import history
        from research import slow_strategies as ss
        history.main(["all", "--days", "183"])
        for coin in ALL_COINS:
            ss.load(coin, refresh=True)
            print(f"daily + funding refreshed: {coin}")
        _bars_cached.cache_clear()
        return 0

    st = load_strategy(args.strategy, _parse_set(args.set))
    default = ALL_COINS if st.kind == "position" else PM_COINS
    coins = [c.strip().upper() for c in args.coins.split(",")] if args.coins else list(getattr(st.module, "COINS", default))
    if st.kind == "polymarket" and set(coins) - set(PM_COINS):
        raise SystemExit(f"Polymarket data exists for {PM_COINS} only")
    t0 = time.time()
    if args.timeframe:
        if st.kind != "position":
            raise SystemExit("--timeframe applies to position strategies only")
        st.module.TIMEFRAME = args.timeframe
        if args.timeframe != "1d":
            st.module.HISTORY = ""          # the long history exists only for daily candles
    rep = (run_position_strategy if st.kind == "position" else run_polymarket_strategy)(st, coins, args.part, args.controls)
    text, path = write_outputs(st, rep, args.part, coins)
    print(text)
    print(f"Report: {os.path.relpath(path, ROOT)}  ({time.time() - t0:.0f}s)")
    return 0 if rep.passed else 1


if __name__ == "__main__":
    sys.exit(main())
