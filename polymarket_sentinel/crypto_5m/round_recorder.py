"""
Polymarket 5-Minute Round Recorder.

Continuously records, once per second, the series that matter for a 5m Up/Down
round and prints one comparison line per round as it closes:

  chainlink_spot / chainlink_twap  Chainlink <coin>/USD, the series Polymarket resolves on
  binance                          Binance <coin>USDT (Tether-quoted, ~0.15% above USD)
  coinbase                         Coinbase <coin>-USD (closest public proxy for
                                   TradingView's "CRYPTO:BTCUSD" index)
  clob_up                          Polymarket Up price from the Gamma API

Everything is persisted to SQLite so the differences can be studied later.

Usage:
  python3 -m polymarket_sentinel.crypto_5m.round_recorder               # record BTC
  python3 -m polymarket_sentinel.crypto_5m.round_recorder --coins BTC,ETH
  python3 -m polymarket_sentinel.crypto_5m.round_recorder --report      # summarise recorded rounds
"""

import argparse
import json
import os
import sqlite3
import ssl
import threading
import time
import urllib.parse
import urllib.request
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


# ── live recorder ────────────────────────────────────────────────────────────

class RoundRecorder:
    def __init__(self, coins=("BTC",), db_path: str = DEFAULT_DB, pending_every: int = 60, gamma_every: float = 5.0):
        self.coins = [c.upper() for c in coins]
        self.db_path = db_path
        self.pending_every = pending_every
        self.gamma_every = gamma_every
        self.lock = threading.RLock()
        self.series: Dict[str, Dict[str, Series]] = {c: {k: [] for k in ("chainlink_spot", "chainlink_twap", "binance", "coinbase", "clob_up", "gamma_up")} for c in self.coins}
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
                    "closed": bool(m.get("closed")), "outcome": outcome}
        except Exception:
            return {"found": False}

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


def main(argv=None):
    ap = argparse.ArgumentParser(description="Record Chainlink vs exchange vs Polymarket per 5m round")
    ap.add_argument("--coins", default="BTC", help="comma-separated, e.g. BTC,ETH")
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--pending-every", type=int, default=60, help="seconds between PENDING status lines")
    ap.add_argument("--report", action="store_true", help="print recorded rounds and aggregate stats, then exit")
    args = ap.parse_args(argv)
    if args.report:
        print_report(args.db)
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
