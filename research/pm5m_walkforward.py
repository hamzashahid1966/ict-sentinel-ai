"""
Walk-forward test: can market features predict Polymarket 5-minute Up/Down rounds
BETTER THAN THE POLYMARKET PRICE ITSELF?

Why this framing: on 34,508 official rounds the Polymarket price was calibrated to within
~1 point at every price band (a side priced X won ~X% of the time). A model is only worth
trading if its probability beats the market's at the moment of the decision, after the
spread and the fee.

PRE-REGISTERED DESIGN (fixed 2026-11-23, before any model was fitted on this data)
  Rows       one per (coin, round, checkpoint). Checkpoints: the Polymarket price point nearest
             180s, 120s and 60s before close (within +/-30s). Decision time t = that point's
             timestamp; the market probability m = its Up price. Label = official outcome.
  No look-ahead  features use only 1-minute candles that CLOSED at or before t
             (row index = floor(t/60)*60 - 60). The round's strike reference is the open of
             the round's first minute.
  Features   (groups; all from Binance USDT-M 1m candles incl. taker-buy volume, plus Coinbase
             USD 1m as the closest public proxy for the Chainlink settlement price)
               price_position  dist_bn, dist_cb (move since round open), z_cb (dist / vol-scaled time left)
               momentum        mom1, mom3, mom5 (vol-normalised log returns)
               trend           ema_gap (EMA20-EMA50), slope15
               volatility      log rv15, rv60, rv240
               candle          body, upper/lower wick ratios, 1m engulfing
               structure       15-min breakout, sweep-and-reclaim
               order_flow      taker imbalance over 1/3/5 minutes and since round open
               timing          seconds left
               regime          UTC hour (sin/cos), vol regime, volume regime
             plus mkt_logit = logit(m) in every model. The Polymarket book group (depth, spread)
             has no history yet; it comes from the round recorder.
  Models     PRIMARY: L2 logistic regression (standardised features + mkt_logit).
             Secondary: gradient boosting (HistGradientBoosting, depth 3). Control: logistic on
             mkt_logit only (recalibration, no new information).
  Walk-forward  expanding window. Train on all data before a fold, test on the fold. The last
             `holdout_days` are a final holdout. Rounds are never shuffled across time.
  Trading    per (coin, round), the first checkpoint where expected value per $1 >= 2% after
             costs: buy that side at its price + 1c (spread allowance), Polymarket fee
             0.07*p*(1-p) per share, hold to settlement. One bet per round per coin.
  PASS       (1) out-of-sample log-loss below the market's, 95% cluster-bootstrap CI (clusters =
             round time, so the 4 coins and 3 checkpoints of one 5-minute window count once)
             entirely above zero; (2) trading P&L positive in the holdout AND in a majority of
             dev folds; (3) total out-of-sample P&L positive.
Research only: reads the local history store, places no orders.

Usage:
  python3 -m research.pm5m_walkforward                      # full run, pre-registered folds
  python3 -m research.pm5m_walkforward --fold-days 10 --min-train-days 20 --holdout-days 15   # smoke run
"""

import argparse
import json
import math
import os
import sqlite3
import time
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB = os.environ.get("MARKET_HISTORY_DB", os.path.join(ROOT, "real_data", "market_history.db"))
COINS = ("BTC", "ETH", "SOL", "XRP")
CHECKPOINTS = (180, 120, 60)
CHECKPOINT_TOL = 30
SPREAD = 0.01
EV_THRESHOLD = 0.02

GROUPS: Dict[str, List[str]] = {
    "price_position": ["dist_bn", "dist_cb", "z_cb"],
    "momentum": ["mom1", "mom3", "mom5"],
    "trend": ["ema_gap", "slope15"],
    "volatility": ["lrv15", "lrv60", "lrv240"],
    "candle": ["body", "upw", "loww", "engulf"],
    "structure": ["brk", "sweep"],
    "order_flow": ["imb1", "imb3", "imb5", "imb_round"],
    "timing": ["secs_left_n"],
    "regime": ["hour_sin", "hour_cos", "vol_regime", "volu_regime"],
}
ALL_FEATURES = [f for g in GROUPS.values() for f in g]


# ── minute data and per-minute features (no look-ahead: row k uses bars <= k) ────────────

def decision_row(t_decision: float) -> int:
    """Open time of the last 1-minute candle that has CLOSED at or before t_decision."""
    return int(t_decision // 60) * 60 - 60


def load_minutes(db: str, coin: str) -> pd.DataFrame:
    with sqlite3.connect(db) as c:
        bn = pd.read_sql("SELECT t, o, h, l, c, quote_volume AS qv, taker_buy_quote AS tbq FROM binance_1m WHERE symbol=? ORDER BY t",
                         c, params=(f"{coin}USDT",))
        cb = pd.read_sql("SELECT t, c AS cb_c, o AS cb_o FROM coinbase_1m WHERE product=? ORDER BY t", c, params=(f"{coin}-USD",))
    if bn.empty:
        return pd.DataFrame()
    grid = np.arange(int(bn.t.min()), int(bn.t.max()) + 60, 60)
    df = bn.set_index("t").reindex(grid)
    if not cb.empty:
        cbi = cb.set_index("t").reindex(grid)
        df["cb_c"] = cbi["cb_c"].ffill()
        df["cb_o"] = cbi["cb_o"].fillna(df["cb_c"].shift(1)).fillna(df["cb_c"])
    else:
        df["cb_c"] = np.nan
        df["cb_o"] = np.nan
    df.index.name = "t"
    return df


def minute_features(df: pd.DataFrame) -> pd.DataFrame:
    """Per-minute features computed only from that minute and earlier ones."""
    out = pd.DataFrame(index=df.index)
    c, o, h, l = df["c"], df["o"], df["h"], df["l"]
    r = np.log(c).diff()
    rv15 = r.rolling(15, min_periods=10).std()
    rv60 = r.rolling(60, min_periods=40).std()
    rv240 = r.rolling(240, min_periods=160).std()
    rv1440 = r.rolling(1440, min_periods=900).std()
    out["rv15"] = rv15
    out["lrv15"], out["lrv60"], out["lrv240"] = np.log(rv15), np.log(rv60), np.log(rv240)
    out["mom1"] = r / rv15
    out["mom3"] = np.log(c / c.shift(3)) / (rv15 * math.sqrt(3))
    out["mom5"] = np.log(c / c.shift(5)) / (rv15 * math.sqrt(5))
    ema20, ema50 = c.ewm(span=20, adjust=False).mean(), c.ewm(span=50, adjust=False).mean()
    out["ema_gap"] = np.log(ema20 / ema50) / rv60
    x = np.arange(15) - 7.0
    out["slope15"] = np.log(c).rolling(15).apply(lambda w: float(np.dot(x, w - w.mean()) / np.dot(x, x)), raw=True) / rv15
    rng = (h - l).replace(0, np.nan)
    out["body"] = ((c - o) / rng).fillna(0.0)
    out["upw"] = ((h - np.maximum(o, c)) / rng).fillna(0.0)
    out["loww"] = ((np.minimum(o, c) - l) / rng).fillna(0.0)
    po, pc = o.shift(1), c.shift(1)
    bull = (pc < po) & (c > o) & (o <= pc) & (c >= po)
    bear = (pc > po) & (c < o) & (o >= pc) & (c <= po)
    out["engulf"] = bull.astype(float) - bear.astype(float)
    hi15, lo15 = h.shift(1).rolling(15).max(), l.shift(1).rolling(15).min()
    out["brk"] = (c > hi15).astype(float) - (c < lo15).astype(float)
    out["sweep"] = ((l < lo15) & (c > lo15)).astype(float) - ((h > hi15) & (c < hi15)).astype(float)
    qv, tbq = df["qv"], df["tbq"]
    out["imb1"] = (2 * tbq / qv - 1).where(qv > 0)
    out["imb3"] = (2 * tbq.rolling(3).sum() / qv.rolling(3).sum() - 1)
    out["imb5"] = (2 * tbq.rolling(5).sum() / qv.rolling(5).sum() - 1)
    out["volu_regime"] = np.log(qv.rolling(5).sum() / (qv.rolling(240, min_periods=160).mean() * 5))
    out["vol_regime"] = np.log(rv60 / rv1440)
    hours = (df.index.values // 3600) % 24
    out["hour_sin"], out["hour_cos"] = np.sin(2 * np.pi * hours / 24), np.cos(2 * np.pi * hours / 24)
    out["c"], out["cb_c"], out["o"], out["cb_o"], out["qv"], out["tbq"] = c, df["cb_c"], o, df["cb_o"], qv, tbq
    return out


def round_features(mf: pd.DataFrame, round_ts: int, t_decision: float) -> Optional[Dict[str, float]]:
    """Features for one decision. None if the needed minutes are missing."""
    k = decision_row(t_decision)
    if k not in mf.index or round_ts not in mf.index or k < round_ts - 60:
        return None
    row = mf.loc[k]
    start = mf.loc[round_ts]
    secs_left = round_ts + 300 - t_decision
    o_bn = start["o"]
    o_cb = start["cb_o"] if pd.notna(start["cb_o"]) else np.nan
    dist_bn = (row["c"] - o_bn) / o_bn if o_bn else np.nan
    dist_cb = (row["cb_c"] - o_cb) / o_cb if pd.notna(o_cb) and o_cb and pd.notna(row["cb_c"]) else dist_bn
    rv = row["rv15"]
    z = dist_cb / (rv * math.sqrt(max(secs_left, 1) / 60.0)) if rv and rv > 0 else np.nan
    if k >= round_ts:
        seg = mf.loc[round_ts:k]
        imb_round = float(2 * seg["tbq"].sum() / seg["qv"].sum() - 1) if seg["qv"].sum() > 0 else 0.0
    else:
        imb_round = 0.0
    f = {name: float(row[name]) for name in ALL_FEATURES if name in row.index}
    f.update({"dist_bn": float(dist_bn), "dist_cb": float(dist_cb), "z_cb": float(np.clip(z, -10, 10)) if pd.notna(z) else np.nan,
              "imb_round": imb_round, "secs_left_n": secs_left / 300.0})
    return f


# ── dataset ──────────────────────────────────────────────────────────────────

def market_points(db: str, coins: Sequence[str]) -> pd.DataFrame:
    """Rounds with an official outcome and the Polymarket Up price nearest each checkpoint."""
    with sqlite3.connect(db) as c:
        rounds = pd.read_sql(f"SELECT coin, round_ts, outcome FROM pm_rounds WHERE outcome IS NOT NULL AND coin IN ({','.join('?' * len(coins))})",
                             c, params=tuple(coins))
        prices = pd.read_sql(f"SELECT coin, round_ts, t, p_up FROM pm_prices WHERE coin IN ({','.join('?' * len(coins))})", c, params=tuple(coins))
    if rounds.empty or prices.empty:
        return pd.DataFrame()
    prices = prices.merge(rounds, on=["coin", "round_ts"])
    prices["secs_left"] = prices["round_ts"] + 300 - prices["t"]
    rows = []
    for cp in CHECKPOINTS:
        sel = prices[(prices.secs_left - cp).abs() <= CHECKPOINT_TOL].copy()
        sel["d"] = (sel.secs_left - cp).abs()
        sel = sel.sort_values("d").drop_duplicates(["coin", "round_ts"])
        sel["checkpoint"] = cp
        rows.append(sel)
    pts = pd.concat(rows, ignore_index=True)
    pts = pts[(pts.p_up > 0.0) & (pts.p_up < 1.0)]
    pts["y"] = (pts.outcome == "UP").astype(int)
    return pts[["coin", "round_ts", "t", "secs_left", "checkpoint", "p_up", "y"]]


def build_dataset(db: str = DEFAULT_DB, coins: Sequence[str] = COINS, verbose: bool = True) -> pd.DataFrame:
    pts = market_points(db, coins)
    if pts.empty:
        return pts
    out = []
    for coin in coins:
        cp = pts[pts.coin == coin]
        if cp.empty:
            continue
        t0 = time.time()
        mf = minute_features(load_minutes(db, coin))
        feats = []
        for r in cp.itertuples(index=False):
            f = round_features(mf, int(r.round_ts), float(r.t))
            feats.append(f if f else {})
        fdf = pd.DataFrame(feats, index=cp.index)
        out.append(pd.concat([cp, fdf], axis=1))
        if verbose:
            print(f"  features {coin}: {len(cp)} decisions in {time.time() - t0:.0f}s", flush=True)
    ds = pd.concat(out).replace([np.inf, -np.inf], np.nan)
    ds = ds.dropna(subset=ALL_FEATURES)
    ds["mkt_logit"] = np.log(ds.p_up.clip(0.01, 0.99) / (1 - ds.p_up.clip(0.01, 0.99)))
    return ds.sort_values(["round_ts", "coin", "checkpoint"]).reset_index(drop=True)


# ── walk-forward ─────────────────────────────────────────────────────────────

def make_folds(ts: np.ndarray, fold_days: int, min_train_days: int, holdout_days: int) -> List[Tuple[str, int, int]]:
    """[(label, test_start, test_end)] with train = everything before test_start. Last fold = holdout."""
    t_min, t_max = int(ts.min()), int(ts.max()) + 1
    hold_start = t_max - holdout_days * 86400
    folds = []
    cur = t_min + min_train_days * 86400
    i = 1
    while cur + 86400 <= hold_start:
        end = min(cur + fold_days * 86400, hold_start)
        folds.append((f"dev{i}", cur, end))
        cur, i = end, i + 1
    folds.append(("holdout", hold_start, t_max))
    return folds


def _logloss(y: np.ndarray, p: np.ndarray) -> np.ndarray:
    p = np.clip(p, 1e-4, 1 - 1e-4)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def _fit_predict(kind: str, train: pd.DataFrame, test: pd.DataFrame, features: List[str]) -> np.ndarray:
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import make_pipeline
    cols = ["mkt_logit"] + features
    if kind == "logit":
        model = make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=2000))
    elif kind == "gbm":
        from sklearn.ensemble import HistGradientBoostingClassifier
        model = HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=300, l2_regularization=1.0,
                                               early_stopping=False, random_state=0)
    else:
        raise ValueError(kind)
    model.fit(train[cols].values, train["y"].values)
    return model.predict_proba(test[cols].values)[:, 1]


def fee(shares: float, p: float) -> float:
    return shares * 0.07 * p * (1 - p)


def simulate_trades(test: pd.DataFrame, q: np.ndarray, ev_threshold: float = EV_THRESHOLD, spread: float = SPREAD) -> pd.DataFrame:
    """First qualifying checkpoint per (coin, round): $1 on the side with EV >= threshold, held to settlement."""
    df = test.assign(q=q).sort_values(["coin", "round_ts", "secs_left"], ascending=[True, True, False])
    bets = []
    for (coin, rts), g in df.groupby(["coin", "round_ts"], sort=False):
        for r in g.itertuples(index=False):
            best = None
            for side, prob, price in (("UP", r.q, r.p_up + spread), ("DOWN", 1 - r.q, (1 - r.p_up) + spread)):
                if not (0.0 < price < 0.99):
                    continue
                sh = 1.0 / price
                ev = prob * sh - 1.0 - fee(sh, price)
                if ev >= ev_threshold and (best is None or ev > best[1]):
                    best = (side, ev, price, sh)
            if best:
                side, ev, price, sh = best
                won = (r.y == 1) == (side == "UP")
                bets.append({"coin": coin, "round_ts": rts, "secs_left": r.secs_left, "side": side, "price": price, "ev": ev,
                             "won": won, "pnl": (sh if won else 0.0) - 1.0 - fee(sh, price)})
                break
    return pd.DataFrame(bets, columns=["coin", "round_ts", "secs_left", "side", "price", "ev", "won", "pnl"])


def cluster_bootstrap_ci(delta: np.ndarray, clusters: np.ndarray, n_boot: int = 1000, seed: int = 0) -> Tuple[float, float, float]:
    """Mean per-row improvement and 95% CI, resampling whole clusters."""
    dfc = pd.DataFrame({"d": delta, "c": clusters}).groupby("c")["d"].agg(["sum", "count"])
    s, n = dfc["sum"].values, dfc["count"].values
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(s), size=(n_boot, len(s)))
    boots = s[idx].sum(axis=1) / n[idx].sum(axis=1)
    return float(s.sum() / n.sum()), float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))


def walk_forward(ds: pd.DataFrame, fold_days: int, min_train_days: int, holdout_days: int, ablation: bool = True) -> Dict:
    folds = make_folds(ds.round_ts.values, fold_days, min_train_days, holdout_days)
    oos = []
    fold_rows = []
    for label, a, b in folds:
        train, test = ds[ds.round_ts < a], ds[(ds.round_ts >= a) & (ds.round_ts < b)]
        if len(train) < 1000 or test.empty:
            continue
        preds = {"market": test.p_up.values,
                 "recal": _fit_predict("logit", train, test, []),
                 "logit": _fit_predict("logit", train, test, ALL_FEATURES),
                 "gbm": _fit_predict("gbm", train, test, ALL_FEATURES)}
        part = test[["coin", "round_ts", "checkpoint", "secs_left", "p_up", "y"]].copy()
        part["fold"] = label
        for k, v in preds.items():
            part[f"q_{k}"] = v
        if ablation:
            for g, cols in GROUPS.items():
                keep = [f for f in ALL_FEATURES if f not in cols]
                part[f"q_drop_{g}"] = _fit_predict("logit", train, test, keep)
        oos.append(part)
        fold_rows.append({"fold": label, "train_rows": len(train), "test_rows": len(test),
                          "test_from": time.strftime("%Y-%m-%d", time.gmtime(a)), "test_to": time.strftime("%Y-%m-%d", time.gmtime(b - 1))})
    return {"folds": fold_rows, "oos": pd.concat(oos, ignore_index=True) if oos else pd.DataFrame()}


def evaluate(res: Dict) -> Dict:
    oos = res["oos"]
    y = oos.y.values
    ll_mkt = _logloss(y, oos.q_market.values)
    out = {"rows": int(len(oos)), "rounds": int(oos[["coin", "round_ts"]].drop_duplicates().shape[0]),
           "logloss_market": float(ll_mkt.mean()), "models": {}, "ablation": {}, "folds": res["folds"]}
    for m in ("recal", "logit", "gbm"):
        ll = _logloss(y, oos[f"q_{m}"].values)
        mean, lo, hi = cluster_bootstrap_ci(ll_mkt - ll, oos.round_ts.values)
        per_fold = {}
        for f, g in oos.groupby("fold", sort=False):
            trades = simulate_trades(g, g[f"q_{m}"].values)
            per_fold[f] = {"bets": int(len(trades)), "win": float(trades.won.mean()) if len(trades) else None,
                           "pnl": float(trades.pnl.sum()) if len(trades) else 0.0,
                           "ll_gain": float((_logloss(g.y.values, g.q_market.values) - _logloss(g.y.values, g[f"q_{m}"].values)).mean())}
        all_trades = simulate_trades(oos, oos[f"q_{m}"].values)
        out["models"][m] = {"logloss": float(ll.mean()), "gain_vs_market": mean, "gain_ci": [lo, hi],
                            "brier": float(((oos[f"q_{m}"].values - y) ** 2).mean()),
                            "brier_market": float(((oos.q_market.values - y) ** 2).mean()),
                            "per_fold": per_fold, "bets": int(len(all_trades)),
                            "win": float(all_trades.won.mean()) if len(all_trades) else None,
                            "pnl": float(all_trades.pnl.sum()) if len(all_trades) else 0.0,
                            "avg_price": float(all_trades.price.mean()) if len(all_trades) else None}
    base = _logloss(y, oos.q_logit.values)
    for g in GROUPS:
        col = f"q_drop_{g}"
        if col in oos:
            out["ablation"][g] = float((_logloss(y, oos[col].values) - base).mean())  # >0: the group helped
    lm = out["models"]["logit"]
    dev = [v for k, v in lm["per_fold"].items() if k != "holdout"]
    hold = lm["per_fold"].get("holdout", {"pnl": 0.0})
    out["pass"] = {"logloss_ci_above_zero": lm["gain_ci"][0] > 0,
                   "holdout_pnl_positive": hold["pnl"] > 0,
                   "dev_majority_positive": sum(1 for v in dev if v["pnl"] > 0) > len(dev) / 2 if dev else False,
                   "total_pnl_positive": lm["pnl"] > 0}
    out["pass"]["PASS"] = all(out["pass"].values())
    return out


def format_report(ev: Dict, title: str) -> str:
    L = [title, "=" * len(title)]
    L.append(f"out-of-sample decisions: {ev['rows']:,} on {ev['rounds']:,} rounds | market log-loss {ev['logloss_market']:.5f}")
    L.append("folds: " + ", ".join(f"{f['fold']} {f['test_from']}..{f['test_to']} (train {f['train_rows']:,}, test {f['test_rows']:,})" for f in ev["folds"]))
    L.append("")
    L.append(f"{'model':<8} {'log-loss':>9} {'gain vs market (95% CI)':>34} {'Brier':>8} {'mkt Brier':>9} {'bets':>6} {'win':>6} {'avg px':>7} {'P&L':>9}")
    names = {"recal": "control: market recalibrated", "logit": "PRIMARY: logistic", "gbm": "secondary: gradient boosting"}
    for m, v in ev["models"].items():
        L.append(f"{m:<8} {v['logloss']:9.5f} {v['gain_vs_market']:+12.5f} ({v['gain_ci'][0]:+.5f}, {v['gain_ci'][1]:+.5f}) "
                 f"{v['brier']:8.5f} {v['brier_market']:9.5f} {v['bets']:6d} {((v['win'] or 0)*100):5.1f}% "
                 f"{(v['avg_price'] or 0):7.3f} {v['pnl']:+9.2f}   <- {names[m]}")
    L.append("")
    L.append("per fold (primary logistic): " + " | ".join(
        f"{k}: {d['bets']} bets, P&L {d['pnl']:+.2f}, ll gain {d['ll_gain']:+.5f}" for k, d in ev["models"]["logit"]["per_fold"].items()))
    if ev["ablation"]:
        L.append("feature-group value (log-loss lost when the group is removed; >0 = the group helped):")
        for g, v in sorted(ev["ablation"].items(), key=lambda kv: -kv[1]):
            L.append(f"  {g:<15} {v:+.6f}")
    L.append("")
    p = ev["pass"]
    L.append(f"PASS MARK: log-loss CI above zero {p['logloss_ci_above_zero']} | holdout P&L > 0 {p['holdout_pnl_positive']} | "
             f"majority of dev folds P&L > 0 {p['dev_majority_positive']} | total P&L > 0 {p['total_pnl_positive']}  ==> "
             f"{'PASS' if p['PASS'] else 'FAIL'}")
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Walk-forward: do market features beat the Polymarket 5m price?")
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--coins", default=",".join(COINS))
    ap.add_argument("--fold-days", type=int, default=30)
    ap.add_argument("--min-train-days", type=int, default=60)
    ap.add_argument("--holdout-days", type=int, default=30)
    ap.add_argument("--no-ablation", action="store_true")
    ap.add_argument("--out", default=os.path.join(ROOT, "docs", "PM5M_WALKFORWARD_RESULTS.md"))
    args = ap.parse_args(argv)
    coins = [c.strip().upper() for c in args.coins.split(",") if c.strip()]
    print("building dataset ...", flush=True)
    ds = build_dataset(args.db, coins)
    if ds.empty:
        print("no rounds with Polymarket prices yet; run: python3 -m market_data.history pm-prices")
        return
    span = f"{time.strftime('%Y-%m-%d', time.gmtime(ds.round_ts.min()))}..{time.strftime('%Y-%m-%d', time.gmtime(ds.round_ts.max()))}"
    print(f"dataset: {len(ds):,} decisions, {ds[['coin','round_ts']].drop_duplicates().shape[0]:,} rounds, {span}", flush=True)
    res = walk_forward(ds, args.fold_days, args.min_train_days, args.holdout_days, ablation=not args.no_ablation)
    ev = evaluate(res)
    title = (f"Polymarket 5m walk-forward ({', '.join(coins)}, {span}; folds {args.fold_days}d, "
             f"min train {args.min_train_days}d, holdout {args.holdout_days}d)")
    text = format_report(ev, title)
    print("\n" + text)
    with open(args.out, "w") as f:
        f.write("```\n" + text + "\n```\n\nSee research/pm5m_walkforward.py for the pre-registered design.\n")
    print(f"\nreport written to {args.out}")


if __name__ == "__main__":
    main()
