"""
Polymarket 5-Minute Round Recorder.

Continuously records, once per second, the series that matter for a 5m Up/Down
round and prints one comparison line per round as it closes:

  chainlink_spot / chainlink_twap  Chainlink <coin>/USD, the series Polymarket resolves on
  binance                          Binance <coin>USDT (Tether-quoted, ~0.15% above USD)
  coinbase                         Coinbase <coin>-USD (closest public proxy for
                                   TradingView's "CRYPTO:BTCUSD" index)
  clob_up                          Polymarket Up price from the Gamma API

Order flow (own 1-second thread, so it never delays the price loop):
  bn_buy_usd / bn_sell_usd         Binance taker-buy / taker-sell notional (USDT) since the last poll
  bn_book_imb / bn_spread_bps      Binance top-20 book imbalance (bid-ask)/(bid+ask) and spread
  pm_up_bid / pm_up_ask            Polymarket Up-token best bid / ask from the CLOB book
  pm_bid_depth / pm_ask_depth      Up-token size within 5c of the best bid / ask
  pm_book_imb                      (bid depth - ask depth)/(bid depth + ask depth)

Everything is persisted to SQLite so the differences can be studied later.

Usage:
  python3 -m polymarket_sentinel.crypto_5m.round_recorder               # record BTC
  python3 -m polymarket_sentinel.crypto_5m.round_recorder --coins BTC,ETH
  python3 -m polymarket_sentinel.crypto_5m.round_recorder --report      # summarise recorded rounds
  python3 -m polymarket_sentinel.crypto_5m.round_recorder --report-flow # does flow beat the market price?
"""

import argparse
import json
import math
import os
import sqlite3
import ssl
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, asdict
from statistics import mean
from typing import Dict, List, Optional, Tuple

Series = List[Tuple[float, float]]

ROUND_SECONDS = 300
DEFAULT_DB = os.environ.get(
    "ROUND_RECORDER_DB",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "round_recorder.db"),
)
BINANCE_SYMBOLS = {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "SOL": "SOLUSDT", "XRP": "XRPUSDT"}
PRICE_SOURCES = ("chainlink_spot", "chainlink_twap", "binance", "coinbase", "clob_up", "gamma_up")
FLOW_SOURCES = ("bn_buy_usd", "bn_sell_usd", "bn_book_imb", "bn_spread_bps",
                "pm_up_bid", "pm_up_ask", "pm_bid_depth", "pm_ask_depth", "pm_book_imb")
AGG_PAGE = 1000
AGG_MAX_PAGES = 5


# ── pure summary math ────────────────────────────────────────────────────────

def value_at(series: Series, ts: float, tolerance: float = 2.0) -> Optional[float]:
    """Nearest sample to `ts` within `tolerance` seconds, else None."""
    best = None
    for t, v in series:
        d = abs(t - ts)
        if d <= tolerance and (best is None or d < best[0]):
            best = (d, v)
    return None if best is None else best[1]


def _sub(a: Optional[float], b: Optional[float]) -> Optional[float]:
    return None if a is None or b is None else round(a - b, 4)


@dataclass
class RoundSummary:
    coin: str
    round_ts: int
    chainlink_twap_open: Optional[float]
    chainlink_spot_open: Optional[float]
    binance_open: Optional[float]
    coinbase_open: Optional[float]
    chainlink_twap_close: Optional[float]
    chainlink_spot_close: Optional[float]
    binance_close: Optional[float]
    coinbase_close: Optional[float]
    price_to_beat_official: Optional[float]
    outcome_from_twap: Optional[str]
    outcome_official: Optional[str]
    clob_up_open: Optional[float]
    clob_up_mid: Optional[float]
    clob_up_close: Optional[float]

    @property
    def binance_minus_chainlink_open(self): return _sub(self.binance_open, self.chainlink_twap_open)
    @property
    def coinbase_minus_chainlink_open(self): return _sub(self.coinbase_open, self.chainlink_twap_open)
    @property
    def binance_minus_chainlink_close(self): return _sub(self.binance_close, self.chainlink_twap_close)
    @property
    def coinbase_minus_chainlink_close(self): return _sub(self.coinbase_close, self.chainlink_twap_close)
    @property
    def official_minus_our_strike(self): return _sub(self.price_to_beat_official, self.chainlink_twap_open)
    @property
    def twap_move(self): return _sub(self.chainlink_twap_close, self.chainlink_twap_open)
    @property
    def binance_move(self): return _sub(self.binance_close, self.binance_open)
    @property
    def coinbase_move(self): return _sub(self.coinbase_close, self.coinbase_open)

    def to_dict(self) -> Dict:
        d = asdict(self)
        for k in ("binance_minus_chainlink_open", "coinbase_minus_chainlink_open", "binance_minus_chainlink_close",
                  "coinbase_minus_chainlink_close", "official_minus_our_strike", "twap_move", "binance_move", "coinbase_move"):
            d[k] = getattr(self, k)
        return d


def summarize_round(coin: str, round_ts: int, series: Dict[str, Series], official: Optional[Dict] = None) -> RoundSummary:
    official = official or {}
    end_ts = round_ts + ROUND_SECONDS
    g = lambda name, ts, tol=2.0: value_at(series.get(name, []), ts, tol)  # noqa: E731
    twap_open, twap_close = g("chainlink_twap", round_ts), g("chainlink_twap", end_ts)
    outcome = None
    if twap_open is not None and twap_close is not None:
        outcome = "UP" if twap_close >= twap_open else "DOWN"
    ptb = official.get("price_to_beat")
    return RoundSummary(
        coin=coin.upper(), round_ts=int(round_ts),
        chainlink_twap_open=twap_open, chainlink_spot_open=g("chainlink_spot", round_ts),
        binance_open=g("binance", round_ts), coinbase_open=g("coinbase", round_ts),
        chainlink_twap_close=twap_close, chainlink_spot_close=g("chainlink_spot", end_ts),
        binance_close=g("binance", end_ts), coinbase_close=g("coinbase", end_ts),
        price_to_beat_official=float(ptb) if ptb is not None else None,
        outcome_from_twap=outcome, outcome_official=official.get("outcome"),
        clob_up_open=g("clob_up", round_ts, 6.0), clob_up_mid=g("clob_up", round_ts + ROUND_SECONDS // 2, 6.0),
        clob_up_close=g("clob_up", end_ts, 6.0),
    )


def _f(v: Optional[float], fmt: str = "{:,.2f}") -> str:
    return "n/a" if v is None else fmt.format(v)


def _s(v: Optional[float]) -> str:
    return "n/a" if v is None else f"{v:+.2f}"


def format_round_line(s: RoundSummary) -> str:
    t = time.strftime("%H:%M", time.gmtime(s.round_ts))
    off = "" if s.price_to_beat_official is None else f" official_strike {_f(s.price_to_beat_official)} (ours {_s(s.official_minus_our_strike)})"
    oo = "" if s.outcome_official is None else f"/{s.outcome_official}"
    return (
        f"[{s.coin} {t}Z CLOSED] outcome {s.outcome_from_twap or 'n/a'}{oo} | "
        f"chainlink TWAP {_f(s.chainlink_twap_open)} -> {_f(s.chainlink_twap_close)} ({_s(s.twap_move)}) | "
        f"binance {_f(s.binance_open)} -> {_f(s.binance_close)} ({_s(s.binance_move)}, vs chainlink {_s(s.binance_minus_chainlink_open)}) | "
        f"coinbase {_f(s.coinbase_open)} -> {_f(s.coinbase_close)} ({_s(s.coinbase_move)}, vs chainlink {_s(s.coinbase_minus_chainlink_open)}) | "
        f"UP price {_f(s.clob_up_open, '{:.2f}')} / {_f(s.clob_up_mid, '{:.2f}')} / {_f(s.clob_up_close, '{:.2f}')}{off}"
    )


def aggregate_report(summaries: List[RoundSummary]) -> Dict:
    def avg(vals):
        vals = [v for v in vals if v is not None]
        return round(mean(vals), 6) if vals else None
    with_official = [s for s in summaries if s.outcome_official and s.outcome_from_twap]
    agree = (sum(1 for s in with_official if s.outcome_official == s.outcome_from_twap) / len(with_official)) if with_official else None
    binance_dir_agree = [s for s in summaries if s.binance_move is not None and s.outcome_from_twap]
    bda = (sum(1 for s in binance_dir_agree if ("UP" if s.binance_move >= 0 else "DOWN") == s.outcome_from_twap) / len(binance_dir_agree)) if binance_dir_agree else None
    return {
        "rounds": len(summaries),
        "mean_binance_minus_chainlink_open": avg([s.binance_minus_chainlink_open for s in summaries]),
        "mean_coinbase_minus_chainlink_open": avg([s.coinbase_minus_chainlink_open for s in summaries]),
        "mean_binance_minus_chainlink_close": avg([s.binance_minus_chainlink_close for s in summaries]),
        "mean_coinbase_minus_chainlink_close": avg([s.coinbase_minus_chainlink_close for s in summaries]),
        "mean_abs_official_minus_our_strike": avg([abs(s.official_minus_our_strike) for s in summaries if s.official_minus_our_strike is not None]),
        "twap_vs_official_agreement": agree,
        "binance_direction_vs_outcome_agreement": bda,
        "up_share": avg([1.0 if s.outcome_from_twap == "UP" else 0.0 for s in summaries if s.outcome_from_twap]),
    }


# ── order-flow math ──────────────────────────────────────────────────────────

def taker_flow(trades: List[Dict]) -> Tuple[float, float]:
    """Binance aggTrades -> (taker-buy notional, taker-sell notional). m=True means the buyer was the maker."""
    buy = sell = 0.0
    for t in trades:
        notional = float(t["p"]) * float(t["q"])
        if t.get("m"):
            sell += notional
        else:
            buy += notional
    return buy, sell


def book_imbalance(depth: Dict) -> Tuple[Optional[float], Optional[float]]:
    """Binance depth snapshot -> ((bid-ask)/(bid+ask) notional over the given levels, spread in bps)."""
    bids = [(float(p), float(q)) for p, q in depth.get("bids") or []]
    asks = [(float(p), float(q)) for p, q in depth.get("asks") or []]
    if not bids or not asks:
        return None, None
    b = sum(p * q for p, q in bids)
    a = sum(p * q for p, q in asks)
    best_bid, best_ask = max(p for p, _ in bids), min(p for p, _ in asks)
    mid = (best_bid + best_ask) / 2
    return (b - a) / (b + a), (best_ask - best_bid) / mid * 1e4


def clob_book_levels(book: Dict, window: float = 0.05) -> Optional[Dict]:
    """Polymarket CLOB book -> best bid/ask, size within `window` of each best price, imbalance."""
    bids = [(float(x["price"]), float(x["size"])) for x in book.get("bids") or []]
    asks = [(float(x["price"]), float(x["size"])) for x in book.get("asks") or []]
    if not bids or not asks:
        return None
    bb, ba = max(p for p, _ in bids), min(p for p, _ in asks)
    bd = sum(q for p, q in bids if p >= bb - window - 1e-9)
    ad = sum(q for p, q in asks if p <= ba + window + 1e-9)
    return {"bid": bb, "ask": ba, "bid_depth": bd, "ask_depth": ad,
            "imbalance": (bd - ad) / (bd + ad) if bd + ad > 0 else 0.0}


def flow_features(series: Dict[str, Series], round_ts: int, checkpoint_s: int = 60, window_s: int = 60) -> Optional[Dict]:
    """Flow and market state `checkpoint_s` seconds before the round closes. None without a market price or flow."""
    t = round_ts + ROUND_SECONDS - checkpoint_s
    buy = sum(v for ts, v in series.get("bn_buy_usd", []) if t - window_s < ts <= t)
    sell = sum(v for ts, v in series.get("bn_sell_usd", []) if t - window_s < ts <= t)
    bid = value_at(series.get("pm_up_bid", []), t, 3.0)
    ask = value_at(series.get("pm_up_ask", []), t, 3.0)
    if bid is None or ask is None or buy + sell <= 0:
        return None
    return {"round_ts": round_ts, "checkpoint_s": checkpoint_s, "flow_imb": (buy - sell) / (buy + sell),
            "market_up": (bid + ask) / 2, "up_ask": ask, "down_ask": round(1.0 - bid, 6),
            "bn_book_imb": value_at(series.get("bn_book_imb", []), t, 3.0),
            "pm_book_imb": value_at(series.get("pm_book_imb", []), t, 3.0)}


def _poly_fee(shares: float, p: float) -> float:
    return shares * 0.07 * p * (1 - p)


def flow_report_from_rows(rows: List[Dict]) -> Dict:
    """
    rows: flow_features(...) plus outcome. Asks two questions:
      1. Calibration: when flow is most buy-heavy (top third), does Up win more often than the
         market's own price implied? (excess = up_rate - market_up; zero means no extra information.)
      2. Money: buying the side flow points to at the live ask, $1 per round, held to settlement.
    """
    rows = [r for r in rows if r and r.get("outcome") in ("UP", "DOWN")]
    out = {"n": len(rows)}
    if not rows:
        return out
    rows = sorted(rows, key=lambda r: r["flow_imb"])
    k = max(1, len(rows) // 3)

    def bucket(sel):
        ur = sum(r["outcome"] == "UP" for r in sel) / len(sel)
        mu = sum(r["market_up"] for r in sel) / len(sel)
        return {"n": len(sel), "up_rate": round(ur, 4), "market_up": round(mu, 4), "excess": round(ur - mu, 4),
                "avg_flow_imb": round(sum(r["flow_imb"] for r in sel) / len(sel), 4)}

    out["bottom_bucket"], out["middle_bucket"], out["top_bucket"] = bucket(rows[:k]), bucket(rows[k:-k] or rows[k:k + 1]), bucket(rows[-k:])
    resid = [(1.0 if r["outcome"] == "UP" else 0.0) - r["market_up"] for r in rows]
    fi = [r["flow_imb"] for r in rows]
    n = len(rows)
    mr, mf = sum(resid) / n, sum(fi) / n
    sr = math.sqrt(sum((x - mr) ** 2 for x in resid))
    sf = math.sqrt(sum((x - mf) ** 2 for x in fi))
    corr = sum((a - mr) * (b - mf) for a, b in zip(resid, fi)) / (sr * sf) if sr > 0 and sf > 0 else 0.0
    out["corr_flow_vs_market_error"] = round(corr, 4)
    out["corr_t_stat"] = round(corr * math.sqrt(max(1, n - 2)) / math.sqrt(max(1e-12, 1 - corr * corr)), 2)
    wins = bets = 0
    pnl = 0.0
    for r in rows:
        if r["flow_imb"] == 0:
            continue
        side = "UP" if r["flow_imb"] > 0 else "DOWN"
        p = r["up_ask"] if side == "UP" else r["down_ask"]
        if not (0.0 < p < 0.99):
            continue
        shares = 1.0 / p
        won = r["outcome"] == side
        bets += 1
        wins += won
        pnl += (shares if won else 0.0) - 1.0 - _poly_fee(shares, p)
    out["follow_flow"] = {"bets": bets, "wins": wins, "win_rate": round(wins / bets, 4) if bets else None,
                          "pnl": round(pnl, 2), "pnl_per_bet": round(pnl / bets, 4) if bets else None}
    return out


# ── live recorder ────────────────────────────────────────────────────────────

class RoundRecorder:
    def __init__(self, coins=("BTC",), db_path: str = DEFAULT_DB, pending_every: int = 60, gamma_every: float = 5.0):
        self.coins = [c.upper() for c in coins]
        self.db_path = db_path
        self.pending_every = pending_every
        self.gamma_every = gamma_every
        self.lock = threading.RLock()
        self.series: Dict[str, Dict[str, Series]] = {c: {k: [] for k in PRICE_SOURCES + FLOW_SOURCES} for c in self.coins}
        self._agg_last_id: Dict[str, Optional[int]] = {c: None for c in self.coins}
        self._flow_pool = ThreadPoolExecutor(max_workers=max(2, 2 * len(self.coins)))
        self.gamma: Dict[str, Dict] = {c: {} for c in self.coins}
        self._pending_finalize: List[Tuple[float, str, int]] = []
        self._ssl = ssl.create_default_context()
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=self._ssl))
        self._headers = {"User-Agent": "Mozilla/5.0"}
        self._stop = threading.Event()
        self._init_db()
        from .chainlink_feed import ChainlinkOracleFeed
        self.chainlink = ChainlinkOracleFeed(coins=self.coins, start=True)

    # storage
    def _init_db(self):
        with sqlite3.connect(self.db_path) as c:
            c.execute("CREATE TABLE IF NOT EXISTS ticks (ts REAL, coin TEXT, source TEXT, value REAL)")
            c.execute("CREATE INDEX IF NOT EXISTS ix_ticks ON ticks (coin, source, ts)")
            c.execute("CREATE TABLE IF NOT EXISTS rounds (coin TEXT, round_ts INTEGER, summary_json TEXT, PRIMARY KEY (coin, round_ts))")

    def _store_ticks(self, rows: List[Tuple[float, str, str, float]]):
        if not rows:
            return
        with sqlite3.connect(self.db_path) as c:
            c.executemany("INSERT INTO ticks VALUES (?,?,?,?)", rows)

    def _store_round(self, s: RoundSummary):
        with sqlite3.connect(self.db_path) as c:
            c.execute("INSERT OR REPLACE INTO rounds VALUES (?,?,?)", (s.coin, s.round_ts, json.dumps(s.to_dict())))

    def load_summaries(self) -> List[RoundSummary]:
        out = []
        with sqlite3.connect(self.db_path) as c:
            for coin, rts, js in c.execute("SELECT coin, round_ts, summary_json FROM rounds ORDER BY round_ts"):
                d = json.loads(js)
                out.append(RoundSummary(**{k: d.get(k) for k in RoundSummary.__dataclass_fields__}))
        return out

    # fetchers
    def _get(self, url: str, timeout: float = 4.0):
        with self._opener.open(urllib.request.Request(url, headers=self._headers), timeout=timeout) as r:
            return json.loads(r.read())

    def _fetch_binance(self) -> Dict[str, float]:
        syms = json.dumps([BINANCE_SYMBOLS[c] for c in self.coins if c in BINANCE_SYMBOLS], separators=(",", ":"))
        try:
            items = self._get("https://api.binance.com/api/v3/ticker/price?symbols=" + urllib.parse.quote(syms, safe=","))
            rev = {v: k for k, v in BINANCE_SYMBOLS.items()}
            return {rev[i["symbol"]]: float(i["price"]) for i in items if i["symbol"] in rev}
        except Exception:
            return {}

    def _fetch_coinbase(self, coin: str) -> Optional[float]:
        try:
            return float(self._get(f"https://api.coinbase.com/v2/prices/{coin}-USD/spot", timeout=3.0)["data"]["amount"])
        except Exception:
            return None

    def _fetch_gamma(self, coin: str, round_ts: int) -> Dict:
        try:
            data = self._get(f"https://gamma-api.polymarket.com/events?slug={coin.lower()}-updown-5m-{round_ts}", timeout=5.0)
            if not data:
                return {"found": False}
            ev = data[0]
            m = (ev.get("markets") or [{}])[0]
            prices = m.get("outcomePrices")
            if isinstance(prices, str):
                prices = json.loads(prices)
            up = float(prices[0]) if prices else None
            gamma_up = up
            # Gamma's outcomePrices lag the order book by minutes; prefer the live CLOB midpoint for the UP token.
            toks = m.get("clobTokenIds")
            if isinstance(toks, str):
                try:
                    toks = json.loads(toks)
                except ValueError:
                    toks = None
            if toks and not m.get("closed"):
                try:
                    mid = self._get(f"https://clob.polymarket.com/midpoint?token_id={toks[0]}", timeout=3.0).get("mid")
                    if mid is not None:
                        up = float(mid)
                except Exception:
                    pass
            ptb = (ev.get("eventMetadata") or {}).get("priceToBeat")
            outcome = None
            if up is not None and (m.get("closed") or up >= 0.95 or up <= 0.05):
                outcome = "UP" if up >= 0.5 else "DOWN"
            return {"found": True, "price_up": up, "gamma_price_up": gamma_up, "price_to_beat": float(ptb) if ptb is not None else None,
                    "closed": bool(m.get("closed")), "outcome": outcome, "up_token": toks[0] if toks else None}
        except Exception:
            return {"found": False}

    def _fetch_agg_trades(self, coin: str, from_id: Optional[int]) -> Optional[List[Dict]]:
        sym = BINANCE_SYMBOLS.get(coin)
        if not sym:
            return None
        q = f"limit=1" if from_id is None else f"fromId={from_id + 1}&limit={AGG_PAGE}"
        try:
            return self._get(f"https://api.binance.com/api/v3/aggTrades?symbol={sym}&{q}", timeout=3.0)
        except Exception:
            return None

    def _fetch_depth(self, coin: str) -> Optional[Dict]:
        sym = BINANCE_SYMBOLS.get(coin)
        if not sym:
            return None
        try:
            return self._get(f"https://api.binance.com/api/v3/depth?symbol={sym}&limit=20", timeout=3.0)
        except Exception:
            return None

    def _fetch_clob_book(self, token_id: Optional[str]) -> Optional[Dict]:
        if not token_id:
            return None
        try:
            return self._get(f"https://clob.polymarket.com/book?token_id={token_id}", timeout=3.0)
        except Exception:
            return None

    def _flow_for_coin(self, coin: str):
        """One coin's flow sample: (taker buy, taker sell) or None, depth, clob book."""
        flow = None
        last = self._agg_last_id.get(coin)
        trades: List[Dict] = []
        failed = False
        for _ in range(AGG_MAX_PAGES):
            page = self._fetch_agg_trades(coin, last)
            if page is None:
                failed = True  # network/API error: no reading, not "zero flow"
                break
            if not page:
                break
            if self._agg_last_id.get(coin) is None:
                # First poll: anchor on the newest trade id; history before now is not this second's flow.
                self._agg_last_id[coin] = max(int(t["a"]) for t in page)
                return None, self._fetch_depth(coin), self._fetch_clob_book(self.gamma.get(coin, {}).get("up_token"))
            trades += page
            last = max(int(t["a"]) for t in page)
            if len(page) < AGG_PAGE:
                break
        if trades:
            self._agg_last_id[coin] = last
            flow = taker_flow(trades) if not failed else None
        elif last is not None and not failed:
            flow = (0.0, 0.0)
        return flow, self._fetch_depth(coin), self._fetch_clob_book(self.gamma.get(coin, {}).get("up_token"))

    def _sample_flow(self, now: float):
        rows: List[Tuple[float, str, str, float]] = []
        futures = {c: self._flow_pool.submit(self._flow_for_coin, c) for c in self.coins}
        for coin, fu in futures.items():
            try:
                flow, depth, book = fu.result(timeout=5.0)
            except Exception:
                continue
            with self.lock:
                if flow is not None:
                    self._append(coin, "bn_buy_usd", now, round(flow[0], 2), rows)
                    self._append(coin, "bn_sell_usd", now, round(flow[1], 2), rows)
                if depth:
                    imb, spread = book_imbalance(depth)
                    if imb is not None:
                        self._append(coin, "bn_book_imb", now, round(imb, 5), rows)
                        self._append(coin, "bn_spread_bps", now, round(spread, 4), rows)
                lv = clob_book_levels(book) if book else None
                if lv:
                    self._append(coin, "pm_up_bid", now, lv["bid"], rows)
                    self._append(coin, "pm_up_ask", now, lv["ask"], rows)
                    self._append(coin, "pm_bid_depth", now, round(lv["bid_depth"], 2), rows)
                    self._append(coin, "pm_ask_depth", now, round(lv["ask_depth"], 2), rows)
                    self._append(coin, "pm_book_imb", now, round(lv["imbalance"], 5), rows)
        self._store_ticks(rows)

    def _flow_loop(self):
        while not self._stop.is_set():
            t0 = time.time()
            try:
                self._sample_flow(float(int(t0)))
            except Exception:
                pass
            time.sleep(max(0.05, 1.0 - (time.time() - t0)))

    # loop
    @staticmethod
    def current_round_ts(now: Optional[float] = None) -> int:
        return (int(now if now is not None else time.time()) // ROUND_SECONDS) * ROUND_SECONDS

    def _append(self, coin: str, source: str, ts: float, value: float, rows: List):
        s = self.series[coin][source]
        s.append((ts, value))
        cutoff = ts - 20 * 60
        while s and s[0][0] < cutoff:
            s.pop(0)
        rows.append((ts, coin, source, value))

    def _sample_once(self, now: float):
        rows: List[Tuple[float, str, str, float]] = []
        binance = self._fetch_binance()
        with self.lock:
            for coin in self.coins:
                sp, sa = self.chainlink.get_spot(coin)
                tw, ta = self.chainlink.get_twap(coin)
                if sp is not None and sa <= 3.0:
                    self._append(coin, "chainlink_spot", now, sp, rows)
                if tw is not None and ta <= 3.0:
                    self._append(coin, "chainlink_twap", now, tw, rows)
                if coin in binance:
                    self._append(coin, "binance", now, binance[coin], rows)
        for coin in self.coins:
            cb = self._fetch_coinbase(coin)
            if cb is not None:
                with self.lock:
                    self._append(coin, "coinbase", now, cb, rows)
        self._store_ticks(rows)

    def _poll_gamma(self, now: float, round_ts: int):
        rows: List[Tuple[float, str, str, float]] = []
        for coin in self.coins:
            g = self._fetch_gamma(coin, round_ts)
            with self.lock:
                self.gamma[coin] = g
                if g.get("found") and g.get("price_up") is not None:
                    self._append(coin, "clob_up", now, g["price_up"], rows)
                if g.get("found") and g.get("gamma_price_up") is not None:
                    self._append(coin, "gamma_up", now, g["gamma_price_up"], rows)
        self._store_ticks(rows)

    def _close_round(self, round_ts: int):
        for coin in self.coins:
            with self.lock:
                official = {"price_to_beat": self.gamma[coin].get("price_to_beat"), "outcome": self.gamma[coin].get("outcome")}
                s = summarize_round(coin, round_ts, self.series[coin], official)
            self._store_round(s)
            print(format_round_line(s), flush=True)
            self._pending_finalize.append((time.time() + 90.0, coin, round_ts))

    def _finalize_due(self, now: float):
        due = [p for p in self._pending_finalize if p[0] <= now]
        self._pending_finalize = [p for p in self._pending_finalize if p[0] > now]
        for _, coin, round_ts in due:
            g = self._fetch_gamma(coin, round_ts)
            with self.lock:
                s = summarize_round(coin, round_ts, self.series[coin], {"price_to_beat": g.get("price_to_beat"), "outcome": g.get("outcome")})
            self._store_round(s)
            t = time.strftime("%H:%M", time.gmtime(round_ts))
            agree = "AGREES" if s.outcome_official == s.outcome_from_twap else "DIFFERS"
            print(f"[{coin} {t}Z OFFICIAL] Polymarket resolved {s.outcome_official or 'pending'} ({agree} with our TWAP read {s.outcome_from_twap}) | "
                  f"official strike {_f(s.price_to_beat_official)} vs our strike {_f(s.chainlink_twap_open)} ({_s(s.official_minus_our_strike)})", flush=True)

    def _pending_line(self, now: float, round_ts: int):
        for coin in self.coins:
            with self.lock:
                sr = self.series[coin]
                twap_open = value_at(sr["chainlink_twap"], round_ts, 3.0)
                last = lambda k: sr[k][-1][1] if sr[k] else None  # noqa: E731
                tw, sp, bn, cb, up = last("chainlink_twap"), last("chainlink_spot"), last("binance"), last("coinbase"), last("clob_up")
            elapsed = int(now - round_ts)
            print(f"[{coin} {time.strftime('%H:%M', time.gmtime(round_ts))}Z PENDING +{elapsed:3d}s] strike {_f(twap_open)} | TWAP {_f(tw)} ({_s(_sub(tw, twap_open))}) "
                  f"spot {_f(sp)} | binance {_f(bn)} (vs chainlink {_s(_sub(bn, sp))}) | coinbase {_f(cb)} (vs chainlink {_s(_sub(cb, sp))}) | UP {_f(up, '{:.2f}')}", flush=True)

    def run(self):
        print(f"Recording {', '.join(self.coins)} every second -> {self.db_path}", flush=True)
        print("Legend: strike = Chainlink TWAP at round open (what Polymarket resolves on); 'vs chainlink' = exchange price minus Chainlink spot", flush=True)
        print("Order flow: Binance taker flow + book depth and Polymarket Up-token book, every second (see --report-flow)", flush=True)
        threading.Thread(target=self._flow_loop, daemon=True).start()
        last_round = self.current_round_ts()
        last_gamma = 0.0
        last_pending = time.time()
        while not self._stop.is_set():
            tick_start = time.time()
            now = float(int(tick_start))
            rts = self.current_round_ts(now)
            if rts != last_round:
                self._sample_once(now)  # capture the boundary second before summarising
                self._close_round(last_round)
                last_round = rts
                last_pending = now
            else:
                self._sample_once(now)
            if now - last_gamma >= self.gamma_every:
                self._poll_gamma(now, rts)
                last_gamma = now
            self._finalize_due(now)
            if now - last_pending >= self.pending_every:
                self._pending_line(now, rts)
                last_pending = now
            time.sleep(max(0.05, 1.0 - (time.time() - tick_start)))

    def stop(self):
        self._stop.set()
        self.chainlink.stop()
        self._flow_pool.shutdown(wait=False)


def print_report(db_path: str):
    rec_summaries = RoundRecorder.__new__(RoundRecorder)
    rec_summaries.db_path = db_path
    summaries = RoundRecorder.load_summaries(rec_summaries)
    if not summaries:
        print("No rounds recorded yet.")
        return
    for s in summaries:
        print(format_round_line(s))
    print("\nAggregate:")
    for k, v in aggregate_report(summaries).items():
        print(f"  {k}: {v}")


def print_flow_report(db_path: str, checkpoints=(120, 60, 30)):
    with sqlite3.connect(db_path) as c:
        rounds = []
        for coin, rts, js in c.execute("SELECT coin, round_ts, summary_json FROM rounds ORDER BY round_ts"):
            out = json.loads(js).get("outcome_official")
            if out in ("UP", "DOWN"):
                rounds.append((coin, rts, out))
        if not rounds:
            print("No rounds with an official outcome yet.")
            return
        series_by_coin: Dict[str, Dict[str, Series]] = {}
        need = FLOW_SOURCES
        for coin in sorted({r[0] for r in rounds}):
            lo = min(r[1] for r in rounds if r[0] == coin)
            hi = max(r[1] for r in rounds if r[0] == coin) + ROUND_SECONDS + 5
            sr: Dict[str, Series] = {k: [] for k in need}
            q = f"SELECT source, ts, value FROM ticks WHERE coin=? AND ts BETWEEN ? AND ? AND source IN ({','.join('?' * len(need))}) ORDER BY ts"
            for src, ts, v in c.execute(q, (coin, lo, hi) + tuple(need)):
                sr[src].append((ts, v))
            series_by_coin[coin] = sr
    import bisect
    print(f"Order flow vs market price on {len(rounds)} rounds with an official outcome")
    print("excess = actual Up rate - average market Up price in that bucket (0 = flow adds nothing the market did not already price)")
    for cp in checkpoints:
        rows = []
        for coin, rts, out in rounds:
            full = series_by_coin[coin]
            lo_t, hi_t = rts - 5, rts + ROUND_SECONDS + 5
            sub = {}
            for k, s in full.items():
                ts_list = [t for t, _ in s]
                i, j = bisect.bisect_left(ts_list, lo_t), bisect.bisect_right(ts_list, hi_t)
                sub[k] = s[i:j]
            f = flow_features(sub, rts, checkpoint_s=cp)
            if f:
                rows.append(dict(f, outcome=out, coin=coin))
        rep = flow_report_from_rows(rows)
        print(f"\n{cp}s before close: {rep['n']} rounds with flow and a live book")
        if rep["n"] == 0:
            continue
        for name in ("bottom_bucket", "middle_bucket", "top_bucket"):
            b = rep[name]
            print(f"  {name.split('_')[0]:<7} flow {b['avg_flow_imb']:+.3f}  n={b['n']:>4}  Up won {b['up_rate']*100:5.1f}%  market said {b['market_up']*100:5.1f}%  excess {b['excess']*100:+5.1f} pts")
        ff = rep["follow_flow"]
        print(f"  corr(flow, market error) {rep['corr_flow_vs_market_error']:+.3f} (t={rep['corr_t_stat']:+.2f})")
        print(f"  follow flow at the ask, $1/round: {ff['bets']} bets, win {((ff['win_rate'] or 0)*100):.1f}%, P&L {ff['pnl']:+.2f} ({((ff['pnl_per_bet'] or 0)*100):+.2f}%/bet)")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Record Chainlink vs exchange vs Polymarket per 5m round")
    ap.add_argument("--coins", default="BTC", help="comma-separated, e.g. BTC,ETH")
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--pending-every", type=int, default=60, help="seconds between PENDING status lines")
    ap.add_argument("--report", action="store_true", help="print recorded rounds and aggregate stats, then exit")
    ap.add_argument("--report-flow", action="store_true", help="test whether order flow beats the market price, then exit")
    args = ap.parse_args(argv)
    if args.report:
        print_report(args.db)
        return
    if args.report_flow:
        print_flow_report(args.db)
        return
    rec = RoundRecorder(coins=[c.strip() for c in args.coins.split(",") if c.strip()], db_path=args.db, pending_every=args.pending_every)
    try:
        rec.run()
    except KeyboardInterrupt:
        pass
    finally:
        rec.stop()
        print("\nStopped. Run with --report to summarise recorded rounds.", flush=True)


if __name__ == "__main__":
    main()
