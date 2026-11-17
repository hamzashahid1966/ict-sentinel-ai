#!/usr/bin/env python3
"""
Downloads and compiles continuous 5m Gold (PAXGUSDT / XAUUSD) data from Binance Public Archives.
"""
import os
import io
import csv
import json
import zipfile
import urllib.request
from datetime import datetime, timezone

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "gold")
os.makedirs(DATA_DIR, exist_ok=True)

MONTHS = ['2026-05', '2026-06', '2026-07', '2026-08', '2026-09', '2026-10']

def download_monthly_archives():
    all_bars = []
    
    for m in MONTHS:
        zip_path = os.path.join(DATA_DIR, f"PAXGUSDT-5m-{m}.zip")
        csv_path = os.path.join(DATA_DIR, f"PAXGUSDT-5m-{m}.csv")
        
        if not os.path.exists(csv_path):
            url = f"https://data.binance.vision/data/spot/monthly/klines/PAXGUSDT/5m/PAXGUSDT-5m-{m}.zip"
            print(f"Downloading {m} archive from {url}...")
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            try:
                data = urllib.request.urlopen(req).read()
                with open(zip_path, 'wb') as f:
                    f.write(data)
                
                with zipfile.ZipFile(io.BytesIO(data)) as z:
                    for name in z.namelist():
                        if name.endswith('.csv'):
                            with z.open(name) as src, open(csv_path, 'wb') as dst:
                                dst.write(src.read())
                print(f"  Extracted {csv_path}")
            except Exception as e:
                print(f"  Error downloading {m}: {e}")
        else:
            print(f"Using cached {csv_path}")

        # Parse CSV
        if os.path.exists(csv_path):
            with open(csv_path, 'r') as f:
                reader = csv.reader(f)
                for row in reader:
                    # Binance monthly kline CSV: [open_time, open, high, low, close, volume, close_time, ...]
                    try:
                        ot = int(row[0])
                        # Handle microsecond vs millisecond timestamps if any
                        if ot > 10**14:
                            ot = ot // 1000
                        o = float(row[1])
                        h = float(row[2])
                        l = float(row[3])
                        c = float(row[4])
                        v = float(row[5])
                        all_bars.append({
                            'time': ot,
                            'open': o,
                            'high': h,
                            'low': l,
                            'close': c,
                            'volume': v
                        })
                    except (ValueError, IndexError):
                        continue

    print(f"Loaded {len(all_bars)} bars from monthly archives.")
    
    # Also fetch November 2026 data up to now via public REST API
    print("Fetching November 2026 live bars via REST API...")
    if all_bars:
        last_time = all_bars[-1]['time']
    else:
        last_time = int(datetime(2026, 11, 1, tzinfo=timezone.utc).timestamp() * 1000)
        
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    curr_start = last_time + 1
    
    added_nov = 0
    while curr_start < now_ms:
        url = f"https://api.binance.com/api/v3/klines?symbol=PAXGUSDT&interval=5m&startTime={curr_start}&limit=1000"
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            res = urllib.request.urlopen(req)
            batch = json.loads(res.read())
            if not batch:
                break
            for b in batch:
                all_bars.append({
                    'time': int(b[0]),
                    'open': float(b[1]),
                    'high': float(b[2]),
                    'low': float(b[3]),
                    'close': float(b[4]),
                    'volume': float(b[5])
                })
                added_nov += 1
            curr_start = int(batch[-1][0]) + (5 * 60 * 1000)
            if len(batch) < 1000:
                break
        except Exception as e:
            print(f"Error fetching live batch: {e}")
            break
            
    print(f"Added {added_nov} bars for November 2026.")
    
    # Sort and deduplicate by timestamp
    all_bars.sort(key=lambda x: x['time'])
    unique_bars = []
    seen = set()
    for b in all_bars:
        if b['time'] not in seen:
            seen.add(b['time'])
            unique_bars.append(b)
            
    compiled_path = os.path.join(DATA_DIR, "gold_5m_may_nov_2026.json")
    with open(compiled_path, 'w') as f:
        json.dump(unique_bars, f)
        
    start_dt = datetime.fromtimestamp(unique_bars[0]['time'] / 1000, tz=timezone.utc).strftime('%Y-%m-%d %H:%M')
    end_dt = datetime.fromtimestamp(unique_bars[-1]['time'] / 1000, tz=timezone.utc).strftime('%Y-%m-%d %H:%M')
    print(f"\nSuccessfully compiled {len(unique_bars)} bars.")
    print(f"Date range: {start_dt} to {end_dt} UTC.")
    print(f"Saved to {compiled_path}")

if __name__ == "__main__":
    download_monthly_archives()

