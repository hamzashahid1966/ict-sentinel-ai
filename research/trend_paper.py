"""
Forward paper test of the daily trend strategy on real Binance USDT-M perp prices. No orders are
ever sent; prices come from public endpoints only (no API key).

PRE-REGISTERED FORWARD TEST (fixed on 2026-11-23, before the first position; rules never change)
-----------------------------------------------------------------------------------------------
Accounts (each starts with 1,000 paper dollars):
    T2_SMA50_LS    50-day average, long above / short below   PRIMARY
    T4_SMA50_LONG  50-day average, long above / flat below    secondary
    BUY_HOLD       equal-weight long every coin               benchmark
    T2_TOP5        T2's rule on BTC ETH SOL XRP BNB only       added 2026-11-24 at the user's request;
                   informational, not judged (backtest 2020..2026: +1245% vs T2's +2182%)
    ES_LONG        EMA50 + market structure, long only         added 2026-11-24 at the user's request;
                   informational, not judged. Long a coin when its close is above EMA50 AND its
                   daily swing structure is higher-high + higher-low (swings = 5 candles each side,
                   used once confirmed); otherwise cash. Rules: research/strategies/ema_structure.py
                   (lab 2019..2026: +793%, worst drop -31%, Sharpe 1.27). Same equal weight,
                   execution, fees and funding as the others.
    ES_LS          the same EMA + structure rule, long AND short: short a coin when its close is
                   below EMA50 AND its structure is lower-high + lower-low; otherwise as ES_LONG.
                   Added 2026-11-24 at the user's request; informational, not judged
                   (lab 2019..2026: +679%, worst drop -34%, Sharpe 1.03).
Rules are the backtest's (research/slow_strategies.py): the signal uses daily closes up to the
latest complete UTC day, equal weight across the coins with at least 60 daily bars, gross
leverage 1, rebalanced daily.
Execution: on the run after a daily close, buy at the real best ask and sell at the real best bid
(bookTicker) plus 0.05% taker fee. Trades under 5 dollars of notional are skipped (Binance's
minimum); closing a position always trades. If runs were missed, the skipped days are booked at
their closes +/- 0.02% slippage and marked "catchup". Funding is charged on every real settlement
at its mark price: a long pays a positive rate, a short receives it.

Pass marks, judged once at 180 days (2027-05-22) on T2:
    1. net return > 0
    2. max drawdown of daily equity <= 35%
    3. execution check: the paper return is within 3 percentage points of the backtest replay of
       the same days (the replay fills at the closes)
    Six months is a weak test of a trend strategy; a PASS only justifies discussing small real
    size, a FAIL stops it.

Run:   python -m research.trend_paper --once      (idempotent: books each daily close once)
       python -m research.trend_paper --status
"""

import argparse
import json
import os
import sqlite3
import time
import urllib.request

import numpy as np

from research.slow_strategies import COINS, LISTING_DAYS, trend_signal

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.environ.get("TREND_PAPER_DB") or os.path.join(ROOT, "real_data", "trend_paper.db")
SEED_PATH = os.path.join(ROOT, "research", "seed", "trend_paper_seed.db")   # accounts carried over to a new server
DAY = 86400
FEE = 0.0005
CATCHUP_SLIP = 0.0002
MIN_NOTIONAL = 5.0
CAPITAL = 1000.0
TOP5 = ("BTC", "ETH", "SOL", "XRP", "BNB")
# rule = (SMA/EMA days or None for buy-and-hold, long_only[, coin subset or None[, kind]])
# kind "sma" (default): sign of close - SMA; "ema_structure": EMA + swing structure (needs daily OHLC)
VARIANTS = {"T2_SMA50_LS": (50, False), "T4_SMA50_LONG": (50, True), "BUY_HOLD": (None, True),
            "T2_TOP5": (50, False, TOP5), "ES_LONG": (50, True, None, "ema_structure"),
            "ES_LS": (50, False, None, "ema_structure")}
OHLC_DAYS = 400


def _rule_coins(rule, closes):
    """The closes this rule trades: its coin subset if it has one, else every coin."""
    return {c: closes[c] for c in rule[2] if c in closes} if len(rule) > 2 and rule[2] else closes


def _rule_kind(rule):
    return rule[3] if len(rule) > 3 else "sma"


def es_target_weights(ohlc, day, ema, long_only, k=5):
    """Equal-weight targets for the EMA + structure rule from daily candles with open time <= day."""
    import pandas as pd
    from research.strategies.ema_structure import signal as es_signal
    sig, eligible = {}, []
    for coin, rows in ohlc.items():
        rr = [r for r in rows if r[0] <= day]
        if len(rr) >= LISTING_DAYS and rr and rr[-1][0] == day:
            eligible.append(coin)
            a = np.array(rr, dtype=float)
            df = pd.DataFrame({"o": a[:, 1], "h": a[:, 2], "l": a[:, 3], "c": a[:, 4]})
            sig[coin] = float(es_signal(df, "both", ema, k, int(long_only))[-1])
        else:
            sig[coin] = 0.0
    N = max(len(eligible), 1)
    return {c: (sig[c] / N if c in eligible else 0.0) for c in ohlc}
START_DAY = "2026-11-23"
JUDGE_DAY = "2027-05-22"


# ---------------------------------------------------------------- market

class BinanceMarket:
    def _get(self, url):
        req = urllib.request.Request(url, headers={"User-Agent": "research-paper"})
        for attempt in range(4):
            try:
                with urllib.request.urlopen(req, timeout=20) as r:
                    return json.loads(r.read())
            except Exception:
                if attempt == 3:
                    raise
                time.sleep(2 * (attempt + 1))

    def daily(self, coin, limit=200):
        rows = self._get(f"https://fapi.binance.com/fapi/v1/klines?symbol={coin}USDT&interval=1d&limit={limit}")
        return [(int(r[0]) // 1000, float(r[4])) for r in rows]

    def daily_ohlc(self, coin, limit=OHLC_DAYS):
        rows = self._get(f"https://fapi.binance.com/fapi/v1/klines?symbol={coin}USDT&interval=1d&limit={limit}")
        return [(int(r[0]) // 1000, float(r[1]), float(r[2]), float(r[3]), float(r[4])) for r in rows]

    def funding(self, coin, since_ts):
        rows = self._get(f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={coin}USDT"
                         f"&startTime={(int(since_ts) + 1) * 1000}&limit=1000")
        out = []
        for r in rows:
            mark = float(r["markPrice"]) if r.get("markPrice") else 0.0
            out.append((int(r["fundingTime"]) // 1000, float(r["fundingRate"]), mark))
        return [r for r in out if r[0] > since_ts]

    def quote(self, coin):
        r = self._get(f"https://fapi.binance.com/fapi/v1/ticker/bookTicker?symbol={coin}USDT")
        return float(r["bidPrice"]), float(r["askPrice"])

    def book_tickers(self):
        """Best bid and ask of every USDT-M perp in one request: {coin: (bid, ask)}."""
        out = {}
        for r in self._get("https://fapi.binance.com/fapi/v1/ticker/bookTicker"):
            sym = r.get("symbol", "")
            if sym.endswith("USDT"):
                out[sym[:-4]] = (float(r["bidPrice"]), float(r["askPrice"]))
        return out

    def mids(self):
        """Mid price of every USDT-M perp in one request: {coin: mid}."""
        return {c: (b + a) / 2 for c, (b, a) in self.book_tickers().items()}


# ---------------------------------------------------------------- book

class PaperBook:
    def __init__(self, path=DB_PATH):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS accounts (variant TEXT PRIMARY KEY, cash REAL, last_day INTEGER,
                last_funding_ts INTEGER, created_ts INTEGER);
            CREATE TABLE IF NOT EXISTS positions (variant TEXT, coin TEXT, qty REAL, PRIMARY KEY (variant, coin));
            CREATE TABLE IF NOT EXISTS fills (id INTEGER PRIMARY KEY, variant TEXT, day INTEGER, ts INTEGER,
                coin TEXT, qty REAL, price REAL, fee REAL, mode TEXT, ref_close REAL);
            CREATE TABLE IF NOT EXISTS days (variant TEXT, day INTEGER, equity_close REAL, cash REAL,
                gross REAL, mode TEXT, lateness_min REAL, PRIMARY KEY (variant, day));
            CREATE TABLE IF NOT EXISTS funding (variant TEXT, coin TEXT, ts INTEGER, qty REAL, rate REAL,
                mark REAL, amount REAL, PRIMARY KEY (variant, coin, ts));
        """)

    def account(self, variant):
        r = self.db.execute("SELECT * FROM accounts WHERE variant=?", (variant,)).fetchone()
        return dict(r) if r else None

    def create(self, variant, capital, now):
        self.db.execute("INSERT INTO accounts VALUES (?,?,?,?,?)", (variant, capital, None, int(now), int(now)))
        self.db.commit()

    def cash(self, variant):
        return self.account(variant)["cash"]

    def positions(self, variant):
        return {r["coin"]: r["qty"] for r in
                self.db.execute("SELECT coin, qty FROM positions WHERE variant=? AND qty != 0", (variant,))}

    def fills(self, variant):
        return [dict(r) for r in self.db.execute("SELECT * FROM fills WHERE variant=? ORDER BY id", (variant,))]

    def days(self, variant):
        return [dict(r) for r in self.db.execute("SELECT * FROM days WHERE variant=? ORDER BY day", (variant,))]

    def funding_rows(self, variant):
        return [dict(r) for r in self.db.execute("SELECT * FROM funding WHERE variant=? ORDER BY ts", (variant,))]


# ---------------------------------------------------------------- rules

def target_weights(closes, day, n, long_only):
    """Equal-weight targets from daily closes with open time <= day (nothing later is used)."""
    sig, eligible = {}, []
    for coin, rows in closes.items():
        px = [p for t, p in rows if t <= day]
        if len(px) >= LISTING_DAYS and (not rows or any(t == day for t, _ in rows)):
            eligible.append(coin)
            sig[coin] = 1.0 if n is None else float(trend_signal(np.array(px), n, long_only)[-1])
        else:
            sig[coin] = 0.0
    N = max(len(eligible), 1)
    return {c: (sig[c] / N if c in eligible else 0.0) for c in closes}


def _apply_funding(book, market_funding, variant, cutoff, closes):
    acct = book.account(variant)
    pos = book.positions(variant)
    last = acct["last_funding_ts"]
    paid = 0.0
    for coin, qty in pos.items():
        for ts, rate, mark in market_funding.get(coin, []):
            if last < ts <= cutoff:
                if mark <= 0:
                    prior = [p for t, p in closes[coin] if t + DAY <= ts]
                    mark = prior[-1] if prior else closes[coin][-1][1]
                amount = -qty * rate * mark
                book.db.execute("INSERT OR IGNORE INTO funding VALUES (?,?,?,?,?,?,?)",
                                (variant, coin, ts, qty, rate, mark, amount))
                paid += amount
    book.db.execute("UPDATE accounts SET cash = cash + ?, last_funding_ts = ? WHERE variant=?",
                    (paid, int(max(last, cutoff)), variant))


def _process_day(book, market, variant, rule, day, live, now, closes, fund, ohlc=None):
    n, long_only = rule[0], rule[1]
    cutoff = now if live else day + DAY
    _apply_funding(book, fund, variant, cutoff, closes)
    close_of = {c: dict(rows).get(day) for c, rows in closes.items()}
    pos = book.positions(variant)
    cash = book.cash(variant)
    eq_close = cash + sum(q * close_of[c] for c, q in pos.items() if close_of.get(c))
    gross = sum(abs(q * close_of[c]) for c, q in pos.items() if close_of.get(c))
    lateness = (now - (day + DAY)) / 60.0 if live else None
    book.db.execute("INSERT OR REPLACE INTO days VALUES (?,?,?,?,?,?,?)",
                    (variant, day, eq_close, cash, gross, "live" if live else "catchup", lateness))

    if _rule_kind(rule) == "ema_structure":
        tgt = es_target_weights(_rule_coins(rule, ohlc), day, n, long_only)
    else:
        tgt = target_weights(_rule_coins(rule, closes), day, n, long_only)
    quotes = {}
    if live:
        for c in set(tgt) | set(pos):
            if tgt.get(c) or pos.get(c):
                quotes[c] = market.quote(c)
        mid = {c: (b + a) / 2 for c, (b, a) in quotes.items()}
        equity = cash + sum(q * mid[c] for c, q in pos.items())
    else:
        mid = {c: close_of[c] for c in tgt if close_of.get(c)}
        equity = eq_close

    for c in sorted(set(tgt) | set(pos)):
        if c not in mid:
            continue
        cur = pos.get(c, 0.0)
        want = tgt.get(c, 0.0) * equity / mid[c]
        delta = want - cur
        if abs(delta) < 1e-12:
            continue
        closing = want == 0.0
        if not closing and abs(delta) * mid[c] < MIN_NOTIONAL:
            continue
        if live:
            bid, ask = quotes[c]
            price = ask if delta > 0 else bid
        else:
            price = close_of[c] * (1 + CATCHUP_SLIP if delta > 0 else 1 - CATCHUP_SLIP)
        fee = abs(delta) * price * FEE
        book.db.execute("INSERT INTO fills (variant, day, ts, coin, qty, price, fee, mode, ref_close) "
                        "VALUES (?,?,?,?,?,?,?,?,?)",
                        (variant, day, int(now if live else day + DAY), c, delta, price, fee,
                         "live" if live else "catchup", close_of.get(c)))
        book.db.execute("INSERT INTO positions VALUES (?,?,?) ON CONFLICT(variant, coin) DO UPDATE SET qty=?",
                        (variant, c, want, want))
        book.db.execute("UPDATE accounts SET cash = cash - ? WHERE variant=?", (delta * price + fee, variant))
    book.db.execute("UPDATE accounts SET last_day=? WHERE variant=?", (day, variant))
    book.db.commit()


def run_once(book, market, now=None, variants=VARIANTS, coins=COINS, capital=CAPITAL):
    now = int(now if now is not None else time.time())
    closes = {}
    for c in coins:
        rows = market.daily(c, 200)
        closes[c] = [(t, p) for t, p in rows if t + DAY <= now]          # complete days only
    latest = min(rows[-1][0] for rows in closes.values() if rows)
    ohlc = None
    if any(_rule_kind(r) == "ema_structure" for r in variants.values()):
        ohlc = {c: [r for r in market.daily_ohlc(c, OHLC_DAYS) if r[0] + DAY <= now] for c in coins}
    for v in variants:
        if book.account(v) is None:
            book.create(v, capital, now)
    since = min(book.account(v)["last_funding_ts"] for v in variants)
    fund = {c: market.funding(c, since) for c in coins}
    log = []
    for v, rule in variants.items():
        last = book.account(v)["last_day"]
        if last is None:
            pending = [latest]
        else:
            pending = list(range(int(last) + DAY, latest + 1, DAY))
        for i, day in enumerate(pending):
            live = i == len(pending) - 1
            _process_day(book, market, v, rule, day, live, now, closes, fund, ohlc)
            log.append(f"{v} {time.strftime('%Y-%m-%d', time.gmtime(day))} {'live' if live else 'catchup'}")
    return log


# ---------------------------------------------------------------- execution check

def replay_return(closes, fund, rule, days, cost=0.0007):
    """Backtest of the same rule over the same days, filled at the closes (the execution check)."""
    n, long_only = rule[0], rule[1]
    closes = _rule_coins(rule, closes)
    eq, drift = 1.0, {}
    for d, d1 in zip(days[:-1], days[1:]):
        w = target_weights(closes, d, n, long_only)
        turn = sum(abs(w.get(c, 0.0) - drift.get(c, 0.0)) for c in set(w) | set(drift))
        gross, fpaid, r = 0.0, 0.0, {}
        for c, wc in w.items():
            px = dict(closes[c])
            if wc == 0.0 or d not in px or d1 not in px:
                r[c] = 0.0
                continue
            r[c] = px[d1] / px[d] - 1
            gross += wc * r[c]
            fpaid += wc * sum(rate for ts, rate, _ in fund.get(c, []) if d + DAY < ts <= d1 + DAY)
        eq *= 1 + gross - fpaid - cost * turn
        drift = {c: w[c] * (1 + r[c]) / (1 + gross) for c in w}
    return eq - 1


def execution_check(book, market, variant, coins=COINS):
    days = [d["day"] for d in book.days(variant)]
    if len(days) < 2:
        return None
    rule = VARIANTS.get(variant)
    closes = {c: market.daily(c, 400) for c in coins}
    first = book.account(variant)["created_ts"]
    fund = {c: market.funding(c, first - 1) for c in coins}
    paper = book.days(variant)[-1]["equity_close"] / CAPITAL - 1
    return paper, replay_return(closes, fund, rule, days)


# ---------------------------------------------------------------- status

def status(book, market):
    out = []
    for v in VARIANTS:
        acct = book.account(v)
        if not acct:
            out.append(f"{v}: not started")
            continue
        pos = book.positions(v)
        mids = {c: sum(market.quote(c)) / 2 for c in pos}
        eq = acct["cash"] + sum(q * mids[c] for c, q in pos.items())
        days = book.days(v)
        curve = np.array([d["equity_close"] for d in days] + [eq])
        dd = float((1 - curve / np.maximum.accumulate(curve)).max()) if len(curve) else 0.0
        fills = book.fills(v)
        fees = sum(f["fee"] for f in fills)
        fund = sum(r["amount"] for r in book.funding_rows(v))
        live = sum(d["mode"] == "live" for d in days)
        longs = sum(1 for q in pos.values() if q > 0)
        shorts = sum(1 for q in pos.values() if q < 0)
        out.append(f"{v:14s} equity {eq:9.2f} ({100 * (eq / CAPITAL - 1):+.2f}%)  max DD {100 * dd:.1f}%  "
                   f"long {longs} short {shorts}  days booked {len(days)} (live {live})  fills {len(fills)}  "
                   f"fees {fees:.2f}  funding {fund:+.2f}")
    chk = execution_check(book, market, "T2_SMA50_LS")
    if chk:
        p, r = chk
        out.append(f"execution check T2 (to the last booked close): paper {100 * p:+.2f}% vs replay {100 * r:+.2f}% "
                   f"-> gap {100 * (p - r):+.2f} pp (pass mark: within 3 pp at 180 days)")
    return out


def position_book(fills):
    """Replay fills (oldest first) per coin: open qty, average entry price, when the current trade
    opened, profit locked in by closed (or reduced) trades, and how many trades were closed.
    Fees are not included here (they are reported separately)."""
    out = {}
    for f in fills:
        c = out.setdefault(f["coin"], {"qty": 0.0, "entry": 0.0, "opened_ts": None, "realized": 0.0, "closed": 0,
                                       "fees_open": 0.0})
        q, d, px, fee = c["qty"], f["qty"], f["price"], f.get("fee", 0.0) or 0.0
        if q == 0 or (q > 0) == (d > 0):                         # open or add on the same side
            c["entry"] = (c["entry"] * abs(q) + px * abs(d)) / (abs(q) + abs(d))
            if q == 0:
                c["opened_ts"], c["fees_open"] = f["ts"], 0.0
            c["qty"] = q + d
            c["fees_open"] += fee                                # fees paid by the trade still open
            continue
        shut = min(abs(d), abs(q))                               # reduce, close or flip
        c["realized"] += shut * (px - c["entry"]) * (1 if q > 0 else -1)
        new = q + d
        if abs(new) < 1e-12:
            c["qty"], c["entry"], c["opened_ts"], c["fees_open"] = 0.0, 0.0, None, 0.0
            c["closed"] += 1
        elif (new > 0) != (q > 0):                               # flipped: a new trade at this price
            c["qty"], c["entry"], c["opened_ts"] = new, px, f["ts"]
            c["fees_open"] = fee * abs(new) / abs(d)             # the new trade's share of this fill's fee
            c["closed"] += 1
        else:
            c["qty"] = new
            c["fees_open"] += fee                                # trimming the open trade
    return out


def last_run(log_path=None):
    """Time of the last hourly check, from the job's log (UTC string) or None."""
    path = log_path or os.path.join(os.path.dirname(DB_PATH), "trend_paper.log")
    try:
        with open(path) as f:
            lines = [ln for ln in f.read().splitlines() if ln.startswith("[20")]
        return lines[-1][1:20] if lines else None
    except OSError:
        return None


def ensure_db(path=None, seed=None):
    """On a new server: start the database from the seed snapshot (the accounts as they were on the
    machine that ran the test before), so the test continues instead of restarting. True if copied."""
    import shutil
    path, seed = path or DB_PATH, seed or SEED_PATH
    if os.path.exists(path) or not os.path.exists(seed):
        return False
    os.makedirs(os.path.dirname(path), exist_ok=True)
    shutil.copyfile(seed, path)
    return True


def scheduled_check(path=None, market=None, now=None):
    """One hourly check, as the launchd job does: run, then append the result line to the log next to
    the database (read by last_run). Errors are logged on a line that last_run does not count."""
    path = path or DB_PATH
    log_path = os.path.join(os.path.dirname(path), "trend_paper.log")
    stamp = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(now))
    try:
        book = PaperBook(path)
        log = run_once(book, market or BinanceMarket(), now=now)
        line = f"[{stamp}] " + ("; ".join(log) if log else "nothing to do")
    except Exception as e:                                   # network trouble: try again next hour
        line = f"! [{stamp}] error: {type(e).__name__}: {e}"
    with open(log_path, "a") as f:
        f.write(line + "\n")
    return line


def last_check_problem(log_path=None):
    """The latest hourly check's error line if the most recent attempt failed, else None."""
    path = log_path or os.path.join(os.path.dirname(DB_PATH), "trend_paper.log")
    try:
        with open(path) as f:
            lines = [ln for ln in f.read().splitlines() if ln.startswith(("[20", "! [20"))]
    except OSError:
        return None
    return lines[-1][2:] if lines and lines[-1].startswith("!") else None


def market_watch(ohlc, mids=None, holdings=None, n=50):
    """Per coin, from complete daily candles (t, o, h, l, c): where the price stands against the
    rules and the daily close that would flip them.
      SMA50 (T2, T4, T2_TOP5): tomorrow's signal uses SMA50 including tonight's close x, so it flips
        to bullish when x > mean(last 49 closes) (and to bearish when x is below it).
      EMA50 (ES accounts): flips when tonight's close is above / below the current EMA50.
      structure: higher high + higher low / lower high + lower low (5-candle swings, confirmed).
    `holdings` = {coin: [(account, "L"/"S"), ...]}."""
    from research.strategies.ema_structure import structure
    rows = []
    for coin, cand in ohlc.items():
        if len(cand) < n + 30:
            continue
        a = np.array(cand, dtype=float)
        c = a[:, 4]
        last = c[-1]
        price = (mids or {}).get(coin) or last
        sma = c[-n:].mean()
        flip_sma = c[-(n - 1):].mean()
        alpha = 2 / (n + 1)
        ema = c[0]
        for x in c[1:]:
            ema = alpha * x + (1 - alpha) * ema
        st = structure(a[:, 2], a[:, 3], 5)[-1]
        rows.append({
            "coin": coin, "price": price, "last_close": last, "last_day": time.strftime("%Y-%m-%d", time.gmtime(a[-1, 0])),
            "chg_7d": 100 * (price / c[-8] - 1), "chg_30d": 100 * (price / c[-31] - 1),
            "sma50": sma, "sma_side": "UP" if last > sma else "DOWN", "sma_flip": flip_sma,
            "sma_flip_pct": 100 * (flip_sma / price - 1),
            "ema50": ema, "ema_side": "UP" if last > ema else "DOWN", "ema_flip_pct": 100 * (ema / price - 1),
            "structure": "UP" if st > 0 else ("DOWN" if st < 0 else "MIXED"),
            "held": (holdings or {}).get(coin, []),
        })
    return rows


def dashboard_state(book, mids=None, variants=None, quotes=None):
    """Read-only snapshot for the web dashboard. `mids` = {coin: mid price}; when it is missing or
    lacks a coin, that position is valued at its last fill price instead. `quotes` = {coin: (bid,
    ask)} adds "close_value": the account if every position were closed now with market orders
    (longs sold at the bid, shorts bought back at the ask) paying the taker fee.
    Without quotes, the close value uses the mid (no spread) plus the fee."""
    accounts = {}
    for v in (variants or VARIANTS):
        acct = book.account(v)
        if not acct:
            accounts[v] = None
            continue
        pos = book.positions(v)
        days = book.days(v)
        last_eq = days[-1]["equity_close"] if days else CAPITAL
        ref = {}
        for f in book.fills(v):          # last fill price per coin, fallback valuation
            ref[f["coin"]] = f["price"]
        priced = {c: (mids or {}).get(c) or ref.get(c) for c in pos}
        live = all((mids or {}).get(c) for c in pos)
        eq = acct["cash"] + sum(q * priced[c] for c, q in pos.items() if priced[c])
        if not pos:
            eq = acct["cash"]
        curve = [d["equity_close"] for d in days] + [eq]
        peak, dd = CAPITAL, 0.0
        for x in [CAPITAL] + curve:
            peak = max(peak, x)
            dd = max(dd, 1 - x / peak)
        fills = book.fills(v)
        pb = position_book(fills)
        open_trades = []
        for c, q in sorted(pos.items()):
            e = pb.get(c, {}).get("entry") or ref.get(c)
            now_px = priced[c]
            pnl = q * (now_px - e) if (now_px and e) else 0.0
            bid, ask = (quotes or {}).get(c, (now_px, now_px)) if now_px else (0.0, 0.0)
            exit_px = (bid if q > 0 else ask) if now_px else 0.0
            fee_in = pb.get(c, {}).get("fees_open", 0.0)
            fee_out = abs(q) * exit_px * FEE
            spread_out = abs(q * (now_px - exit_px)) if now_px else 0.0
            open_trades.append({"coin": c, "side": "LONG" if q > 0 else "SHORT", "size_usd": abs(q * e) if e else 0.0,
                                "entry": e, "now": now_px, "pnl": pnl, "fee_in": fee_in, "fee_out": fee_out,
                                "spread_out": spread_out, "net": pnl - fee_in - fee_out - spread_out,
                                "pnl_pct": 100 * (now_px / e - 1) * (1 if q > 0 else -1) if (now_px and e) else 0.0,
                                "opened": time.strftime("%Y-%m-%d %H:%M", time.gmtime(pb[c]["opened_ts"]))
                                if pb.get(c, {}).get("opened_ts") else None})
        closed_n = sum(x["closed"] for x in pb.values())
        locked_in = sum(x["realized"] for x in pb.values())
        close_value = acct["cash"]
        for c, q in pos.items():
            if not priced[c]:
                continue
            bid, ask = (quotes or {}).get(c, (priced[c], priced[c]))
            px = bid if q > 0 else ask
            close_value += q * px - abs(q) * px * FEE
        accounts[v] = {
            "close_value": close_value, "close_cost": eq - close_value,
            "close_return_pct": 100 * (close_value / CAPITAL - 1),
            "equity": eq, "return_pct": 100 * (eq / CAPITAL - 1), "max_dd_pct": 100 * dd, "live_prices": live,
            "last_close_equity": last_eq, "days_booked": len(days), "fills": len(fills),
            "fees": sum(f["fee"] for f in fills), "funding": sum(r["amount"] for r in book.funding_rows(v)),
            "longs": sorted(c for c, q in pos.items() if q > 0), "shorts": sorted(c for c, q in pos.items() if q < 0),
            "curve": [{"day": time.strftime("%Y-%m-%d", time.gmtime(d["day"])), "equity": d["equity_close"]} for d in days],
            "open_trades": open_trades, "closed_trades": closed_n, "locked_in": locked_in,
        }
    now = time.time()
    start = time.mktime(time.strptime(START_DAY, "%Y-%m-%d")) - time.timezone
    judge = time.mktime(time.strptime(JUDGE_DAY, "%Y-%m-%d")) - time.timezone
    return {"start_day": START_DAY, "judge_day": JUDGE_DAY, "capital": CAPITAL, "last_run": last_run(), "last_problem": last_check_problem(),
            "days_elapsed": max(0, int((now - start) // DAY)), "days_left": max(0, int((judge - now) // DAY) + 1),
            "primary": "T2_SMA50_LS", "accounts": accounts,
            "pass_marks": ["net return > 0", "max drawdown of daily equity <= 35%",
                           "paper return within 3 percentage points of the backtest replay"]}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--db", default=DB_PATH)
    a = ap.parse_args(argv)
    book = PaperBook(a.db)
    m = BinanceMarket()
    if a.once:
        stamp = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
        log = run_once(book, m)
        print(f"[{stamp}] " + ("; ".join(log) if log else "nothing to do"))
    if a.status or not a.once:
        print(f"Trend paper test (started {START_DAY}, judged {JUDGE_DAY})")
        for line in status(book, m):
            print("  " + line)


if __name__ == "__main__":
    main()
