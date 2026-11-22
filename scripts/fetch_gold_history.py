#!/usr/bin/env python3
"""
Downloads N months of continuous 5m PAXGUSDT (tokenised gold, tracks XAU/USD) bars
from Binance public archives plus the current month via REST, and compiles them to
one JSON list of {time, open, high, low, close, volume} sorted by time.

Usage: python3 scripts/fetch_gold_history.py --months 24 --out real_data/gold/gold_5m_24m.json
"""
import argparse
import csv
import io
import json
import os
import ssl
import urllib.request
import zipfile
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARCHIVE_DIR = os.path.join(ROOT, "real_data", "gold", "archive")
HEADERS = {"User-Agent": "Mozilla/5.0"}
CTX = ssl.create_default_context()
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=CTX))


def month_list(n: int):
    now = datetime.now(timezone.utc)
    y, m = now.year, now.month
    out = []
    for _ in range(n):
        m -= 1
        if m == 0:
            y -= 1
            m = 12
        out.append(f"{y:04d}-{m:02d}")
    return sorted(out)


def parse_rows(rows):
    bars = []
    for row in rows:
        try:
            ot = int(row[0])
            if ot > 10 ** 14:
                ot //= 1000
            bars.append({"time": ot, "open": float(row[1]), "high": float(row[2]), "low": float(row[3]),
                         "close": float(row[4]), "volume": float(row[5])})
        except (ValueError, IndexError):
            continue
    return bars


def fetch_month(month: str):
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    csv_path = os.path.join(ARCHIVE_DIR, f"PAXGUSDT-5m-{month}.csv")
    if not os.path.exists(csv_path):
        url = f"https://data.binance.vision/data/spot/monthly/klines/PAXGUSDT/5m/PAXGUSDT-5m-{month}.zip"
        print(f"downloading {month} ...", flush=True)
        data = OPENER.open(urllib.request.Request(url, headers=HEADERS), timeout=60).read()
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            name = [n for n in z.namelist() if n.endswith(".csv")][0]
            with z.open(name) as src, open(csv_path, "wb") as dst:
                dst.write(src.read())
    with open(csv_path, newline="") as f:
        return parse_rows(csv.reader(f))


def fetch_rest_since(start_ms: int):
    bars = []
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    cur = start_ms
    while cur < now_ms:
        url = f"https://api.binance.com/api/v3/klines?symbol=PAXGUSDT&interval=5m&startTime={cur}&limit=1000"
        batch = json.loads(OPENER.open(urllib.request.Request(url, headers=HEADERS), timeout=20).read())
        if not batch:
            break
        bars += [{"time": int(b[0]), "open": float(b[1]), "high": float(b[2]), "low": float(b[3]),
                  "close": float(b[4]), "volume": float(b[5])} for b in batch]
        cur = int(batch[-1][0]) + 300_000
        if len(batch) < 1000:
            break
    return bars


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", type=int, default=24)
    ap.add_argument("--out", default=os.path.join(ROOT, "real_data", "gold", "gold_5m_24m.json"))
    args = ap.parse_args()

    all_bars = []
    for month in month_list(args.months):
        try:
            got = fetch_month(month)
            print(f"  {month}: {len(got)} bars", flush=True)
            all_bars += got
        except Exception as e:
            print(f"  {month}: FAILED {type(e).__name__}: {str(e)[:80]}", flush=True)
    last = all_bars[-1]["time"] if all_bars else int(datetime(2026, 11, 1, tzinfo=timezone.utc).timestamp() * 1000)
    rest = fetch_rest_since(last + 1)
    print(f"  current month via REST: {len(rest)} bars", flush=True)
    all_bars += rest

    seen, uniq = set(), []
    for b in sorted(all_bars, key=lambda x: x["time"]):
        if b["time"] not in seen:
            seen.add(b["time"])
            uniq.append(b)
    with open(args.out, "w") as f:
        json.dump(uniq, f)
    s = datetime.fromtimestamp(uniq[0]["time"] / 1000, tz=timezone.utc)
    e = datetime.fromtimestamp(uniq[-1]["time"] / 1000, tz=timezone.utc)
    print(f"compiled {len(uniq)} bars  {s:%Y-%m-%d} .. {e:%Y-%m-%d}  -> {args.out}", flush=True)


if __name__ == "__main__":
    main()
