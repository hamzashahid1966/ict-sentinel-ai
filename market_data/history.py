"""
Local market-history store: real Binance, Coinbase and Polymarket data in one SQLite file,
so any strategy idea can be backtested offline against what actually happened.

Tables (real_data/market_history.db by default, or $MARKET_HISTORY_DB):
  binance_1m   symbol, t, o, h, l, c, volume, quote_volume, trades, taker_buy_base, taker_buy_quote
               (taker_buy_* = buyer-initiated volume: historical order flow; sell side = total - buy)
  coinbase_1m  product, t, o, h, l, c, volume       (Coinbase USD: closest public proxy for Chainlink)
  pm_rounds    coin, round_ts, slug, condition_id, up_token, down_token, outcome, price_to_beat,
               final_price, volume, closed
               price_to_beat / final_price are Polymarket's official Chainlink start/end prices:
               a free 5-minute Chainlink series. outcome is the official resolution.
  pm_prices    coin, round_ts, t, p_up             (Polymarket Up-token price history, 1-minute points,
                                                    from 2 minutes before the open to the close)
  pm_price_done coin, round_ts, points              (bookkeeping for resumable price downloads)

Usage (every command is resumable; rerun it to continue or to top up recent data):
  python3 -m market_data.history status
  python3 -m market_data.history binance  --days 183
  python3 -m market_data.history coinbase --days 183
  python3 -m market_data.history pm-rounds --days 183
  python3 -m market_data.history pm-prices
  python3 -m market_data.history all --days 183
Read-only public APIs; nothing here places orders.
"""

import argparse
import json
import os
import sqlite3
import ssl
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB = os.environ.get("MARKET_HISTORY_DB", os.path.join(ROOT, "real_data", "market_history.db"))
COINS = ("BTC", "ETH", "SOL", "XRP")
BINANCE = {c: f"{c}USDT" for c in COINS}
COINBASE = {c: f"{c}-USD" for c in COINS}
ROUND = 300

_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=ssl.create_default_context()))


def _get(url: str, tries: int = 5, timeout: float = 20.0):
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (market-history)"})
            return json.loads(_OPENER.open(req, timeout=timeout).read())
        except urllib.error.HTTPError as e:
            if e.code in (429, 418) or e.code >= 500:
                time.sleep(2.0 * (k + 1))
                continue
            raise
        except Exception:
            if k == tries - 1:
                raise
            time.sleep(1.5 * (k + 1))
    raise RuntimeError(f"gave up on {url}")


# ── parsers (pure) ───────────────────────────────────────────────────────────

def parse_binance_kline(symbol: str, row: Sequence) -> Tuple:
    return (symbol, int(row[0]) // 1000, float(row[1]), float(row[2]), float(row[3]), float(row[4]), float(row[5]),
            float(row[7]), int(row[8]), float(row[9]), float(row[10]))


def parse_coinbase_candle(product: str, row: Sequence) -> Tuple:
    # Coinbase Exchange candles are [time, low, high, open, close, volume].
    t, low, high, opn, close, vol = row[:6]
    return (product, int(t), float(opn), float(high), float(low), float(close), float(vol))


def parse_gamma_event(coin: str, ev: Dict) -> Optional[Dict]:
    try:
        round_ts = int(str(ev["slug"]).rsplit("-", 1)[-1])
        m = (ev.get("markets") or [])[0]
        toks = m.get("clobTokenIds")
        toks = json.loads(toks) if isinstance(toks, str) else toks
        prices = m.get("outcomePrices")
        prices = json.loads(prices) if isinstance(prices, str) else prices
        up = float(prices[0]) if prices else None
        closed = bool(m.get("closed") or ev.get("closed"))
        outcome = None
        if up is not None and closed and (up >= 0.99 or up <= 0.01):
            outcome = "UP" if up >= 0.5 else "DOWN"
        meta = ev.get("eventMetadata") or {}
        vol = m.get("volumeNum", ev.get("volume"))
        return {
            "coin": coin.upper(), "round_ts": round_ts, "slug": ev["slug"], "condition_id": m.get("conditionId"),
            "up_token": toks[0] if toks else None, "down_token": toks[1] if toks and len(toks) > 1 else None,
            "outcome": outcome,
            "price_to_beat": float(meta["priceToBeat"]) if meta.get("priceToBeat") is not None else None,
            "final_price": float(meta["finalPrice"]) if meta.get("finalPrice") is not None else None,
            "volume": float(vol) if vol is not None else None, "closed": 1 if closed else 0,
        }
    except (KeyError, IndexError, ValueError, TypeError):
        return None


# ── store ────────────────────────────────────────────────────────────────────

class HistoryStore:
    def __init__(self, path: str = DEFAULT_DB):
        self.path = path
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with self._c() as c:
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("""CREATE TABLE IF NOT EXISTS binance_1m (symbol TEXT, t INTEGER, o REAL, h REAL, l REAL, c REAL,
                         volume REAL, quote_volume REAL, trades INTEGER, taker_buy_base REAL, taker_buy_quote REAL,
                         PRIMARY KEY (symbol, t))""")
            c.execute("""CREATE TABLE IF NOT EXISTS coinbase_1m (product TEXT, t INTEGER, o REAL, h REAL, l REAL, c REAL,
                         volume REAL, PRIMARY KEY (product, t))""")
            c.execute("""CREATE TABLE IF NOT EXISTS pm_rounds (coin TEXT, round_ts INTEGER, slug TEXT, condition_id TEXT,
                         up_token TEXT, down_token TEXT, outcome TEXT, price_to_beat REAL, final_price REAL,
                         volume REAL, closed INTEGER, PRIMARY KEY (coin, round_ts))""")
            c.execute("""CREATE TABLE IF NOT EXISTS pm_prices (coin TEXT, round_ts INTEGER, t INTEGER, p_up REAL,
                         PRIMARY KEY (coin, round_ts, t))""")
            c.execute("CREATE TABLE IF NOT EXISTS pm_price_done (coin TEXT, round_ts INTEGER, points INTEGER, PRIMARY KEY (coin, round_ts))")

    def _c(self):
        return sqlite3.connect(self.path, timeout=60)

    def put_binance(self, rows: Iterable[Tuple]):
        with self._c() as c:
            c.executemany("INSERT OR REPLACE INTO binance_1m VALUES (?,?,?,?,?,?,?,?,?,?,?)", list(rows))

    def put_coinbase(self, rows: Iterable[Tuple]):
        with self._c() as c:
            c.executemany("INSERT OR REPLACE INTO coinbase_1m VALUES (?,?,?,?,?,?,?)", list(rows))

    def put_rounds(self, rounds: Iterable[Dict]):
        cols = ("coin", "round_ts", "slug", "condition_id", "up_token", "down_token", "outcome", "price_to_beat",
                "final_price", "volume", "closed")
        with self._c() as c:
            c.executemany(f"INSERT OR REPLACE INTO pm_rounds VALUES ({','.join('?' * len(cols))})",
                          [tuple(r.get(k) for k in cols) for r in rounds])

    def put_prices(self, rows: Iterable[Tuple]):
        with self._c() as c:
            c.executemany("INSERT OR REPLACE INTO pm_prices VALUES (?,?,?,?)", list(rows))

    def mark_prices_done(self, coin: str, round_ts: int, points: int = 0):
        with self._c() as c:
            c.execute("INSERT OR REPLACE INTO pm_price_done VALUES (?,?,?)", (coin, round_ts, points))

    def last_binance_t(self, symbol: str) -> Optional[int]:
        with self._c() as c:
            return c.execute("SELECT max(t) FROM binance_1m WHERE symbol=?", (symbol,)).fetchone()[0]

    def first_binance_t(self, symbol: str) -> Optional[int]:
        with self._c() as c:
            return c.execute("SELECT min(t) FROM binance_1m WHERE symbol=?", (symbol,)).fetchone()[0]

    def coinbase_ts(self, product: str) -> Set[int]:
        with self._c() as c:
            return {r[0] for r in c.execute("SELECT t FROM coinbase_1m WHERE product=?", (product,))}

    def known_round_ts(self, coin: str, resolved_only: bool = False) -> Set[int]:
        q = "SELECT round_ts FROM pm_rounds WHERE coin=?" + (" AND outcome IS NOT NULL" if resolved_only else "")
        with self._c() as c:
            return {r[0] for r in c.execute(q, (coin,))}

    def rounds_needing_prices(self) -> List[Tuple[str, int, str]]:
        with self._c() as c:
            return [tuple(r) for r in c.execute(
                """SELECT r.coin, r.round_ts, r.up_token FROM pm_rounds r
                   LEFT JOIN pm_price_done d ON d.coin = r.coin AND d.round_ts = r.round_ts
                   WHERE d.coin IS NULL AND r.up_token IS NOT NULL AND r.outcome IS NOT NULL
                   ORDER BY r.round_ts, r.coin""")]


# ── downloaders ──────────────────────────────────────────────────────────────

def _now_minute() -> int:
    return int(time.time() // 60) * 60


def _fmt(ts: Optional[int]) -> str:
    return "-" if ts is None else time.strftime("%Y-%m-%d %H:%M", time.gmtime(ts))


def download_binance(store: HistoryStore, coins=COINS, days: int = 183):
    end = _now_minute() - 60
    start = end - days * 86400
    for coin in coins:
        sym = BINANCE.get(coin, f"{coin}USDT")
        first, last = store.first_binance_t(sym), store.last_binance_t(sym)
        spans = []
        if first is None:
            spans.append((start, end))
        else:
            if first > start + 60:
                spans.append((start, first - 60))
            if last < end:
                spans.append((last + 60, end))
        got = 0
        for a, b in spans:
            cur = a
            while cur <= b:
                rows = _get(f"https://api.binance.com/api/v3/klines?symbol={sym}&interval=1m&startTime={cur * 1000}"
                            f"&endTime={b * 1000 + 59999}&limit=1000")
                if not rows:
                    break
                store.put_binance(parse_binance_kline(sym, r) for r in rows)
                got += len(rows)
                cur = int(rows[-1][0]) // 1000 + 60
                time.sleep(0.12)
        print(f"[binance] {sym}: +{got} candles, now {_fmt(store.first_binance_t(sym))} .. {_fmt(store.last_binance_t(sym))}", flush=True)


def download_coinbase(store: HistoryStore, coins=COINS, days: int = 183):
    end = _now_minute() - 60
    start = end - days * 86400
    for coin in coins:
        prod = COINBASE.get(coin, f"{coin}-USD")
        have = store.coinbase_ts(prod)
        got = 0
        cur = start
        while cur <= end:
            b = min(end, cur + 299 * 60)
            # Skip windows already complete (allow a few empty minutes: Coinbase omits minutes with no trades).
            expected = (b - cur) // 60 + 1
            if sum(1 for t in range(cur, b + 1, 60) if t in have) >= expected - 3:
                cur = b + 60
                continue
            a_iso = datetime.fromtimestamp(cur, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            b_iso = datetime.fromtimestamp(b, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            rows = _get(f"https://api.exchange.coinbase.com/products/{prod}/candles?granularity=60&start={a_iso}&end={b_iso}")
            if rows:
                store.put_coinbase(parse_coinbase_candle(prod, r) for r in rows)
                got += len(rows)
            cur = b + 60
            time.sleep(0.15)
        print(f"[coinbase] {prod}: +{got} candles", flush=True)


def download_pm_rounds(store: HistoryStore, coins=COINS, days: int = 183, workers: int = 4):
    end = (int(time.time()) // ROUND) * ROUND - ROUND * 3  # leave the last few rounds to resolve
    start = end - days * 86400
    for coin in coins:
        done = store.known_round_ts(coin, resolved_only=True)
        todo = [r for r in range(start - start % ROUND, end, ROUND) if r not in done]
        batches = [todo[i:i + 20] for i in range(0, len(todo), 20)]
        print(f"[pm-rounds] {coin}: {len(todo)} rounds to fetch in {len(batches)} batches", flush=True)

        def fetch(batch):
            q = "&".join(f"slug={coin.lower()}-updown-5m-{r}" for r in batch)
            return [x for x in (parse_gamma_event(coin, ev) for ev in (_get(f"https://gamma-api.polymarket.com/events?{q}") or [])) if x]

        n_saved = 0
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = [ex.submit(fetch, b) for b in batches]
            buf: List[Dict] = []
            for i, fu in enumerate(as_completed(futs), 1):
                try:
                    buf += fu.result()
                except Exception as e:
                    print(f"  batch failed: {type(e).__name__}", flush=True)
                if len(buf) >= 500 or i == len(futs):
                    store.put_rounds(buf)
                    n_saved += len(buf)
                    buf = []
                if i % 250 == 0:
                    print(f"  {coin}: {i}/{len(batches)} batches, {n_saved} rounds saved", flush=True)
        print(f"[pm-rounds] {coin}: saved {n_saved} rounds", flush=True)


def download_pm_prices(store: HistoryStore, workers: int = 6, limit: Optional[int] = None):
    todo = store.rounds_needing_prices()
    if limit:
        todo = todo[:limit]
    print(f"[pm-prices] {len(todo)} rounds need price history", flush=True)

    def fetch(item):
        coin, rts, tok = item
        h = _get(f"https://clob.polymarket.com/prices-history?market={tok}&startTs={rts - 120}&endTs={rts + ROUND}&fidelity=1").get("history", [])
        return coin, rts, [(coin, rts, int(p["t"]), float(p["p"])) for p in h]

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(fetch, it) for it in todo]
        rows: List[Tuple] = []
        dones: List[Tuple[str, int, int]] = []
        for i, fu in enumerate(as_completed(futs), 1):
            try:
                coin, rts, pts = fu.result()
                rows += pts
                dones.append((coin, rts, len(pts)))
            except Exception:
                pass
            if len(dones) >= 500 or i == len(futs):
                store.put_prices(rows)
                with store._c() as c:
                    c.executemany("INSERT OR REPLACE INTO pm_price_done VALUES (?,?,?)", dones)
                rows, dones = [], []
            if i % 5000 == 0:
                rate = i / max(1e-9, time.time() - t0)
                print(f"  {i}/{len(todo)} rounds ({rate:.0f}/s, ~{(len(todo) - i) / max(rate, 1e-9) / 60:.0f} min left)", flush=True)
    print("[pm-prices] done", flush=True)


def status(store: HistoryStore):
    with store._c() as c:
        print(f"database: {store.path} ({os.path.getsize(store.path) / 1e6:.1f} MB)")
        for sym, n, a, b in c.execute("SELECT symbol, count(*), min(t), max(t) FROM binance_1m GROUP BY symbol"):
            print(f"  binance_1m   {sym:<8} {n:>8} candles  {_fmt(a)} .. {_fmt(b)}")
        for p, n, a, b in c.execute("SELECT product, count(*), min(t), max(t) FROM coinbase_1m GROUP BY product"):
            print(f"  coinbase_1m  {p:<8} {n:>8} candles  {_fmt(a)} .. {_fmt(b)}")
        for coin, n, res, a, b in c.execute("SELECT coin, count(*), sum(outcome IS NOT NULL), min(round_ts), max(round_ts) FROM pm_rounds GROUP BY coin"):
            done = c.execute("SELECT count(*), sum(points > 0) FROM pm_price_done WHERE coin=?", (coin,)).fetchone()
            print(f"  pm_rounds    {coin:<8} {n:>8} rounds ({res} resolved)  {_fmt(a)} .. {_fmt(b)} | price history: {done[0]} fetched, {done[1] or 0} non-empty")
        print(f"  pm_prices    {c.execute('SELECT count(*) FROM pm_prices').fetchone()[0]} points")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Download real Binance / Coinbase / Polymarket history into SQLite")
    ap.add_argument("what", choices=["status", "binance", "coinbase", "pm-rounds", "pm-prices", "all"])
    ap.add_argument("--days", type=int, default=183)
    ap.add_argument("--coins", default=",".join(COINS))
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args(argv)
    store = HistoryStore(args.db)
    coins = [c.strip().upper() for c in args.coins.split(",") if c.strip()]
    if args.what in ("binance", "all"):
        download_binance(store, coins, args.days)
    if args.what in ("coinbase", "all"):
        download_coinbase(store, coins, args.days)
    if args.what in ("pm-rounds", "all"):
        download_pm_rounds(store, coins, args.days)
    if args.what in ("pm-prices", "all"):
        download_pm_prices(store, workers=args.workers)
    status(store)


if __name__ == "__main__":
    main()
