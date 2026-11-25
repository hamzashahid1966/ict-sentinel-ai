"""
Run the four checklist strategies (ict_mayne, gianluca_vp, range_reentry, tc_pullback) on gold and EUR/USD.

PRE-REGISTERED 2026-11-25, before any run.
  Data       Binance's public archive (data.binance.vision), 5-minute candles:
               PAXG  PAXG/USDT spot (gold-backed token), since 2020-09
               EUR   EUR/USDT spot, since 2020-01
               XAU   XAU/USDT perpetual (gold), since 2025-12 (about one year only)
             Prices track gold and EUR/USD; volume is Binance's, not the real market's (this matters for the
             volume-profile strategy). Data runs to the end of October 2026.
  Hours      forex-like week: candles from Friday 21:00 UTC to Sunday 22:00 UTC are dropped (the real
             markets are closed then; these Binance pairs keep trading thinly).
  Timeframes 15m, 1h and 1d candles are built from the 5m candles.
  Costs      a typical retail broker on these markets instead of crypto fees: 0.01% per fill (spread +
             commission) and 0.005% slippage on market fills. The minimum stop width scales with costs to
             0.04% of price (same cost-to-risk ratio as 0.25% with crypto costs). Gross R (no costs) is
             reported too. Everything else is exactly as pre-registered in each strategy's module.
  PASS       each strategy's own PASS rule, per market.
Research only: reads public archives, places no orders.

Usage:
  python3 -m research.other_markets            # download (once) and run everything
  python3 -m research.other_markets --no-download
"""

import argparse
import csv
import io
import json
import os
import time
import urllib.request
import zipfile

import numpy as np

from research import gianluca_vp, ict_mayne, range_reentry, tc_pullback
from research.lab import SLOW_DIR

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "docs", "other_markets")
MARKETS = {"PAXG": ("spot", "PAXGUSDT", (2020, 9)), "EUR": ("spot", "EURUSDT", (2020, 1)),
           "XAU": ("futures/um", "XAUUSDT", (2025, 12))}
NAMES = {"PAXG": "gold (PAXG/USDT)", "EUR": "EUR/USD (EUR/USDT)", "XAU": "gold (XAU/USDT perp)"}
LAST = (2026, 10)
FEE, SLIP, MIN_WIDTH = 0.0001, 0.00005, 0.0004


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "research-lab"})
    for k in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(2 * (k + 1))
        except Exception:
            time.sleep(2 * (k + 1))
    return None


def forex_open(t):
    """False from Friday 21:00 UTC to Sunday 22:00 UTC."""
    wd = ((t // 86400) + 3) % 7                      # 0 = Monday (1970-01-01 was a Thursday)
    hr = (t % 86400) // 3600
    return ~((wd == 4) & (hr >= 21) | (wd == 5) | (wd == 6) & (hr < 22))


def resample(a, step):
    key = a[:, 0].astype(np.int64) // step
    _, start = np.unique(key, return_index=True)
    end = np.r_[start[1:], len(a)]
    return np.column_stack([key[start] * step, a[start, 1], np.maximum.reduceat(a[:, 2], start),
                            np.minimum.reduceat(a[:, 3], start), a[end - 1, 4],
                            np.add.reduceat(a[:, 5], start), np.add.reduceat(a[:, 6], start)])


def build(coin):
    market, sym, (y0, m0) = MARKETS[coin]
    rows = []
    y, m = y0, m0
    while (y, m) <= LAST:
        blob = _get(f"https://data.binance.vision/data/{market}/monthly/klines/{sym}/5m/{sym}-5m-{y}-{m:02d}.zip")
        if blob:
            with zipfile.ZipFile(io.BytesIO(blob)) as z:
                text = z.read(z.namelist()[0]).decode()
            for r in csv.reader(io.StringIO(text)):
                if r and r[0].isdigit():
                    t = int(r[0])
                    t = t // 1000 if t < 10 ** 14 else t // 1_000_000
                    rows.append([t, float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5]), float(r[9])])
        m += 1
        if m == 13:
            y, m = y + 1, 1
    a = np.array(sorted({r[0]: r for r in rows}.values()), dtype=float)
    a = a[forex_open(a[:, 0].astype(np.int64))]
    for name, step in (("ohlc5m", 300), ("ohlc15m", 900), ("ohlc1h", 3600), ("ohlc", 86400)):
        b = a if step == 300 else resample(a, step)
        if step == 86400:                                # drop the 2-hour Sunday-evening stubs
            per_day = np.bincount((a[:, 0] // 86400).astype(np.int64) - int(a[0, 0] // 86400))
            b = b[per_day[(b[:, 0] // 86400).astype(np.int64) - int(a[0, 0] // 86400)] >= 144]
        with open(os.path.join(SLOW_DIR, f"{name}_{coin}USDT.json"), "w") as f:
            json.dump(b.tolist(), f)
    print(coin, len(a), "5m candles", time.strftime("%Y-%m-%d", time.gmtime(a[0, 0])), "to",
          time.strftime("%Y-%m-%d", time.gmtime(a[-1, 0])), flush=True)


def set_costs():
    ict_mayne.FEE, ict_mayne.SLIP, ict_mayne.MIN_WIDTH = FEE, SLIP, MIN_WIDTH
    gianluca_vp.FEE, gianluca_vp.SLIP, gianluca_vp.MIN_WIDTH = FEE, SLIP, MIN_WIDTH
    range_reentry.SLIP, range_reentry.MIN_WIDTH = SLIP, MIN_WIDTH
    tc_pullback.SLIP, tc_pullback.MIN_WIDTH = SLIP, MIN_WIDTH


NOTE = ("> **Market: {name}.** Costs here are a retail forex/gold broker's, not crypto's: 0.01% per fill and "
        "0.005% slippage, minimum stop 0.04% of price (see `research/other_markets.py`). Where the text "
        "below says 0.05% / 0.02% / 0.25%, read these values instead. Forex weekend hours removed.\n\n")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-download", action="store_true")
    ap.add_argument("--coins", default=",".join(MARKETS))
    a = ap.parse_args(argv)
    coins = [c.strip().upper() for c in a.coins.split(",")]
    if not a.no_download:
        for c in coins:
            build(c)
    set_costs()
    os.makedirs(OUT_DIR, exist_ok=True)
    for c in coins:
        for mod, tag in ((ict_mayne, "ict_mayne"), (gianluca_vp, "gianluca_vp"), (range_reentry, "range_reentry"),
                         (tc_pullback, "tc_pullback")):
            path = os.path.join(OUT_DIR, f"{c}_{tag}.md")
            print(f"== {c} {tag}", flush=True)
            try:
                mod.main(["--coins", c, "--out", path])
            except Exception as e:                       # e.g. too little data for a weekly pair
                print(f"   skipped: {type(e).__name__}: {e}", flush=True)
                continue
            with open(path) as f:
                text = f.read()
            with open(path, "w") as f:
                f.write(NOTE.format(name=NAMES[c]) + text)


if __name__ == "__main__":
    main()
