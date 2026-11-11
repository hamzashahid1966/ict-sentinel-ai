"""
ICT Sentinel AI - Real-Time Data Streaming & Ingestion Engine
Fetches live bars and provides unified streaming to the IPDA engine.
Includes safe SQLite cache handling, warm disk pre-seeding, and network resilience.
"""

import os
import glob
import time
import datetime
import logging
import pandas as pd
import yfinance as yf
from typing import Dict, List, Optional
from .config import ASSET_SPECS, BASE_DIR
from .models import Candle

# 1. Suppress verbose yfinance loggers that spam terminal on network reconnects
logging.getLogger('yfinance').setLevel(logging.CRITICAL)

# 2. Clean orphaned SQLite WAL locks left by killed background processes
def _clean_stale_yfinance_locks():
    paths_to_clean = [
        os.path.expanduser("~/.cache/py-yfinance"),
        os.path.expanduser("~/Library/Caches/py-yfinance")
    ]
    for c_dir in paths_to_clean:
        if os.path.exists(c_dir):
            for lock_pat in ["*.db-shm", "*.db-wal"]:
                for lock_file in glob.glob(os.path.join(c_dir, lock_pat)):
                    try:
                        os.remove(lock_file)
                    except Exception:
                        pass

_clean_stale_yfinance_locks()

# Set isolated cache directory
_safe_cache = os.path.expanduser("~/.cache/py-yfinance")
os.makedirs(_safe_cache, exist_ok=True)
try:
    yf.set_tz_cache_location(_safe_cache)
except Exception:
    pass


class DataFeedEngine:
    def __init__(self, mode: str = "live"):
        self.mode = mode
        self.candle_cache: Dict[str, List[Candle]] = {asset: [] for asset in ASSET_SPECS}
        self.last_fetch_time: Dict[str, float] = {asset: 0.0 for asset in ASSET_SPECS}
        self._seed_cache_from_disk()

    def _seed_cache_from_disk(self):
        """Pre-seeds the candle cache with real market bars so the engine is immediately armed."""
        for asset in ASSET_SPECS:
            try:
                bars = self._load_fallback_bars(asset, limit=120)
                if bars:
                    self.candle_cache[asset] = bars
            except Exception:
                pass

    def _load_fallback_bars(self, asset: str, limit: int = 100) -> List[Candle]:
        """Loads historical 5m bars from local real_data storage."""
        file_map = {
            'GOLD': os.path.join(BASE_DIR, '..', 'real_data', 'GC_F_5m_60d.csv'),
            'SILVER': os.path.join(BASE_DIR, '..', 'real_data', 'SI_F_5m_60d.csv'),
            'NASDAQ': os.path.join(BASE_DIR, '..', 'real_data', 'NQ_F_5m_60d.csv'),
            'GBPUSD': os.path.join(BASE_DIR, '..', 'real_data', 'GBPUSD_5m_60d.csv'),
            'EURUSD': os.path.join(BASE_DIR, '..', 'real_data', 'EURUSD_5m_60d.csv'),
        }
        path = file_map.get(asset)
        if not path or not os.path.exists(path):
            return []

        df = pd.read_csv(path)
        dt_col = 'Datetime' if 'Datetime' in df.columns else 'Date'
        df[dt_col] = pd.to_datetime(df[dt_col], utc=True)
        df['Datetime_ET'] = df[dt_col].dt.tz_convert('US/Eastern')
        recent = df.tail(limit).reset_index(drop=True)

        candles: List[Candle] = []
        for _, row in recent.iterrows():
            candles.append(Candle(
                timestamp=row[dt_col].to_pydatetime(),
                timestamp_et=row['Datetime_ET'].to_pydatetime(),
                open=float(row['Open']),
                high=float(row['High']),
                low=float(row['Low']),
                close=float(row['Close']),
                volume=float(row.get('Volume', 0))
            ))
        return candles

    def fetch_recent_bars(self, asset: str, interval: str = "5m", limit: int = 100, period: Optional[str] = None) -> List[Candle]:
        """
        Fetches the latest bars from the live exchange feed.
        Enforces smart cache-throttling to prevent Yahoo Finance 429 rate-limits,
        and seamlessly falls back to cached/real data if network drops.
        """
        spec = ASSET_SPECS.get(asset)
        if not spec:
            return []

        # Smart Cache Throttle: 5m bars do not close faster than 300 seconds.
        # Only query network if at least 45 seconds have passed.
        now_ts = time.time()
        cached = self.candle_cache.get(asset, [])
        if (now_ts - self.last_fetch_time.get(asset, 0.0) < 45.0) and len(cached) >= 20:
            return cached

        symbol = spec['symbol']
        try:
            if not period:
                period = "5d" if interval == "5m" else "1d"

            df = yf.download(symbol, period=period, interval=interval, progress=False)
            if df is None or df.empty:
                if cached:
                    return cached
                return self._load_fallback_bars(asset, limit=limit)

            if hasattr(df.columns, 'levels') and len(df.columns.levels) > 1:
                df.columns = df.columns.get_level_values(0)

            df.reset_index(inplace=True)
            dt_col = 'Datetime' if 'Datetime' in df.columns else 'Date'
            df[dt_col] = pd.to_datetime(df[dt_col], utc=True)
            df['Datetime_ET'] = df[dt_col].dt.tz_convert('US/Eastern')

            candles: List[Candle] = []
            for _, row in df.tail(limit).iterrows():
                candles.append(Candle(
                    timestamp=row[dt_col].to_pydatetime(),
                    timestamp_et=row['Datetime_ET'].to_pydatetime(),
                    open=float(row['Open']),
                    high=float(row['High']),
                    low=float(row['Low']),
                    close=float(row['Close']),
                    volume=float(row.get('Volume', 0))
                ))

            self.candle_cache[asset] = candles
            self.last_fetch_time[asset] = now_ts
            return candles

        except Exception:
            # On transient network/rate-limit error, use cached candles or warm fallback
            if cached:
                return cached
            return self._load_fallback_bars(asset, limit=limit)

    def get_latest_price(self, asset: str) -> Optional[float]:
        candles = self.candle_cache.get(asset)
        if candles:
            return candles[-1].close
        candles = self.fetch_recent_bars(asset, limit=1)
        return candles[-1].close if candles else None

    def fetch_live_simulation_bars(self, asset: str, limit: int = 1500) -> List[Candle]:
        """
        Fetches live historical market data over the network for simulation.
        Falls back to local cache if network is unavailable.
        """
        try:
            live_bars = self.fetch_recent_bars(asset, interval="5m", limit=limit, period="30d")
            if len(live_bars) >= 200:
                return live_bars
        except Exception:
            pass

        return self._load_fallback_bars(asset, limit=limit)
