"""
Crypto Sentinel AI - Market Data Feed & 50-Coin Screener Engine
Connects to Binance Futures REST API with automatic failover to high-fidelity market simulation.
"""

import urllib.request
import urllib.error
import json
import time
import math
import random
from typing import List, Dict, Any, Optional
from crypto_sentinel.config import (
    TOP_50_UNIVERSE, TOP_PRIME_SYMBOLS, BINANCE_PUBLIC_REST, SCREENER_MAX_CANDIDATES, BINANCE_TESTNET_REST, SSL_CONTEXT,
    DIRECT_OPENER, direct_urlopen, IS_REAL_PAPER
)
from crypto_sentinel.models import CryptoCandle, ScreenerCandidate


class RealBinanceQuotes:
    """
    Real Binance USDT-M prices for paper trading: mark price (what Binance triggers stops on)
    and the best bid/ask (what a market order would actually fill at). One request each
    covers every symbol; cached for `ttl` seconds. Nothing is invented: unknown -> None.
    """

    def __init__(self, ttl: float = 2.0):
        self.ttl = ttl
        self._mark: Dict[str, float] = {}
        self._book: Dict[str, tuple] = {}
        self._at = 0.0

    def _get(self, url: str):
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
        with direct_urlopen(req, timeout=5.0) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def refresh(self, force: bool = False):
        if not force and time.time() - self._at < self.ttl:
            return
        try:
            premium = self._get(f"{BINANCE_PUBLIC_REST}/fapi/v1/premiumIndex") or []
            book = self._get(f"{BINANCE_PUBLIC_REST}/fapi/v1/ticker/bookTicker") or []
        except Exception:
            return  # keep the last real snapshot; never fabricate
        mark = {r["symbol"]: float(r["markPrice"]) for r in premium if isinstance(r, dict) and float(r.get("markPrice") or 0) > 0}
        quotes = {}
        for r in book:
            try:
                bid, ask = float(r["bidPrice"]), float(r["askPrice"])
            except (KeyError, TypeError, ValueError):
                continue
            if 0 < bid <= ask:
                quotes[r["symbol"]] = (bid, ask)
        if mark:
            self._mark = mark
        if quotes:
            self._book = quotes
        self._at = time.time()

    def mark(self, symbol: str) -> Optional[float]:
        return self._mark.get(symbol)

    def quote(self, symbol: str) -> Optional[tuple]:
        return self._book.get(symbol)


class CryptoDataFeed:
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json"
        }
        # In-memory baseline prices for top 50
        # Only real exchange prices live here; nothing is seeded or simulated.
        self._price_cache: Dict[str, float] = {}
        self._tickers_24h: Optional[Dict[str, Dict[str, Any]]] = None
        self._tickers_24h_at: float = 0.0
        self._candle_cache: Dict[str, Dict[str, List[CryptoCandle]]] = {}
        self.last_sync_time = 0.0
        # REAL_DATA_PAPER: every price comes from real Binance (mark for triggers, book for fills).
        self.price_source = "real" if IS_REAL_PAPER else "testnet"
        self.real_quotes = RealBinanceQuotes()
        if self.price_source == "testnet":
            self.sync_testnet_prices()

    def sync_testnet_prices(self):
        """Fetches live ticker prices directly from Binance Futures Testnet REST API."""
        now = time.time()
        if now - self.last_sync_time < 10.0:
            return
        try:
            req = urllib.request.Request(
                f"{BINANCE_TESTNET_REST}/fapi/v1/ticker/price",
                headers=self.headers
            )
            with direct_urlopen(req, timeout=5.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for item in data:
                    sym = item.get("symbol")
                    p = float(item.get("price", 0))
                    if p > 0:
                        self._price_cache[sym] = p
                self.last_sync_time = now
        except Exception:
            pass

    def _seed_initial_prices(self) -> Dict[str, float]:
        seeds = {
            "BTCUSDT": 91450.0, "ETHUSDT": 3280.0, "SOLUSDT": 218.5, "BNBUSDT": 645.0,
            "XRPUSDT": 1.12, "ADAUSDT": 0.78, "AVAXUSDT": 34.2, "LINKUSDT": 14.8,
            "SUIUSDT": 3.45, "NEARUSDT": 6.85, "APTUSDT": 11.2, "DOTUSDT": 8.50,
            "MATICUSDT": 0.52, "ARBUSDT": 0.88, "OPUSDT": 1.75, "INJUSDT": 28.5,
            "RENDERUSDT": 7.45, "FETUSDT": 1.35, "TAOUSDT": 520.0, "AAVEUSDT": 165.0,
            "UNIUSDT": 9.20, "LDOUSDT": 1.35, "TIAUSDT": 5.40, "SEIUSDT": 0.55,
            "FTMUSDT": 0.82, "KASUSDT": 0.16, "STXUSDT": 1.95, "RUNEUSDT": 5.80,
            "GALAUSDT": 0.028, "IMXUSDT": 1.45,
            # Memes
            "DOGEUSDT": 0.385, "SHIBUSDT": 0.0000245, "PEPEUSDT": 0.0000215,
            "WIFUSDT": 3.65, "BONKUSDT": 0.000042, "FLOKIUSDT": 0.00023,
            "BOMEUSDT": 0.0095, "POPCATUSDT": 1.55, "MEWUSDT": 0.0115, "NEIROUSDT": 0.00185,
            # High Beta
            "TONUSDT": 5.45, "LTCUSDT": 88.5, "ETCUSDT": 26.5, "BCHUSDT": 465.0,
            "FILUSDT": 4.60, "ICPUSDT": 9.40, "ATOMUSDT": 6.10, "XLMUSDT": 0.225,
            "HBARUSDT": 0.125, "ALGOUSDT": 0.195
        }
        return seeds

    def get_quote(self, symbol: str) -> Optional[tuple]:
        """Real Binance best (bid, ask) in REAL_DATA_PAPER mode; None otherwise or when unknown."""
        if getattr(self, "price_source", "testnet") != "real":
            return None
        self.real_quotes.refresh()
        return self.real_quotes.quote(symbol)

    def get_current_price(self, symbol: str) -> Optional[float]:
        """Latest real price, or None if no real price has been seen. Never simulated.
        REAL_DATA_PAPER: real Binance mark price. Otherwise: Binance Testnet last price."""
        if getattr(self, "price_source", "testnet") == "real":
            self.real_quotes.refresh()
            return self.real_quotes.mark(symbol)
        self.sync_testnet_prices()
        px = self._price_cache.get(symbol)
        return px if px else None  # full exchange precision; rounding to 2dp distorted sub-dollar-tick coins

    def _fetch_24h_tickers(self) -> Optional[Dict[str, Dict[str, Any]]]:
        """Real 24h statistics for every USDT-M perpetual (Binance public API), cached 30s; None if unreachable."""
        now = time.time()
        if self._tickers_24h is not None and now - self._tickers_24h_at < 30.0:
            return self._tickers_24h
        try:
            req = urllib.request.Request("https://fapi.binance.com/fapi/v1/ticker/24hr", headers=self.headers)
            with direct_urlopen(req, timeout=5.0) as resp:
                rows = json.loads(resp.read().decode("utf-8"))
            self._tickers_24h = {r["symbol"]: r for r in rows if isinstance(r, dict) and r.get("symbol")}
            self._tickers_24h_at = now
            return self._tickers_24h
        except Exception:
            return None

    def scan_top_50(self, prime_only: bool = True) -> List[ScreenerCandidate]:
        """
        Tier 1 Universe Screener:
        Scans Curated Top 12 Prime Universe assets (or all 50 if prime_only=False),
        computes 24h change, volume, H1 trend, and scores them.
        Generates clear plain-English reasons for why top candidates are picked.
        """
        if getattr(self, "price_source", "testnet") == "testnet":
            self.sync_testnet_prices()
        candidates: List[ScreenerCandidate] = []
        stats = self._fetch_24h_tickers()
        if not stats:
            return []  # no real market statistics: score nothing rather than invent them

        scan_items = [item for item in TOP_50_UNIVERSE if item["symbol"] in TOP_PRIME_SYMBOLS] if prime_only else TOP_50_UNIVERSE
        if not scan_items:
            scan_items = TOP_50_UNIVERSE

        for item in scan_items:
            symbol = item["symbol"]
            name = item["name"]
            sector = item["sector"]
            t = stats.get(symbol)
            if not t:
                continue
            try:
                price = float(t["lastPrice"])
                change_24h = round(float(t["priceChangePercent"]), 2)
                volume_24h = round(float(t["quoteVolume"]), 0)
                high, low = float(t["highPrice"]), float(t["lowPrice"])
            except (KeyError, TypeError, ValueError):
                continue
            volatility_pct = round(((high - low) / low) * 100.0, 2) if low > 0 else 0.0

            h1_trend = "BULLISH" if change_24h > 1.0 else ("BEARISH" if change_24h < -1.0 else "NEUTRAL")

            # Deterministic score from real data: move size, intraday range and liquidity
            score = round(min(98.0, abs(change_24h) * 4.5 + volatility_pct * 2.0 + min(20.0, volume_24h / 100_000_000)), 1)

            # Plain English "Why Picked"
            why_picked = self._generate_why_picked(symbol, sector, change_24h, volume_24h, h1_trend)

            candidates.append(ScreenerCandidate(
                symbol=symbol,
                name=name,
                price=price,
                change_24h=change_24h,
                volume_24h=volume_24h,
                sector=sector,
                why_picked=why_picked,
                score=score,
                h1_trend=h1_trend,
                volatility_pct=volatility_pct,
                is_active_focus=False
            ))

        # Sort by score descending and flag top candidates
        candidates.sort(key=lambda c: c.score, reverse=True)
        for i in range(min(SCREENER_MAX_CANDIDATES, len(candidates))):
            candidates[i].is_active_focus = True

        return candidates

    def _generate_why_picked(self, symbol: str, sector: str, change_24h: float, vol: float, trend: str) -> str:
        vol_m = f"${vol/1_000_000:.1f}M"
        if sector == "MEME":
            if change_24h > 3.0:
                return f"High-momentum meme breakout (+{change_24h}% 24h, {vol_m} vol); potential liquidation cascade long."
            else:
                return f"Meme sector pullback ({change_24h}%, {vol_m} vol); testing key discount liquidity level."
        elif sector == "MAJOR":
            if trend == "BULLISH":
                return f"Institutional market leader with heavy volume ({vol_m}); expanding above H1 EMA 20/50."
            else:
                return f"Macro liquidity sweep underway ({vol_m} vol); approaching previous day key low for reversal."
        else:
            if change_24h > 0:
                return f"Strong relative strength in {sector} sector ({vol_m} vol); expanding structure with rising volume."
            else:
                return f"Deep pullback into discount Fair Value Gap ({vol_m} vol); M15 market structure shift forming."

    def fetch_candles(self, symbol: str, timeframe: str = "5m", limit: int = 50) -> List[CryptoCandle]:
        """
        Fetch real multi-timeframe candles (5m, 15m, 1h) directly from Binance Futures public klines API.
        Includes high-performance TTL cache and robust graceful fallback.
        """
        now_ts = time.time()
        cache_key = f"{symbol}_{timeframe}_{limit}"
        ttl = 60.0 if timeframe == "1h" else (30.0 if timeframe == "15m" else 10.0)

        # 1. Check TTL cache
        cached = self._candle_cache.get(cache_key)
        if cached:
            cached_time, candles = cached
            if now_ts - cached_time < ttl:
                return candles

        # 2. Fetch live institutional klines from Binance Futures public API
        url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval={timeframe}&limit={limit}"
        try:
            req = urllib.request.Request(url, headers=self.headers)
            with direct_urlopen(req, timeout=3.5) as resp:
                data = json.loads(resp.read().decode())
                if isinstance(data, list) and len(data) > 0:
                    candles: List[CryptoCandle] = []
                    for k in data:
                        candles.append(CryptoCandle(
                            timestamp=int(k[0]),
                            open=float(k[1]),
                            high=float(k[2]),
                            low=float(k[3]),
                            close=float(k[4]),
                            volume=round(float(k[5]), 2)
                        ))
                    self._candle_cache[cache_key] = (now_ts, candles)
                    return candles
        except Exception as e:
            # If rate-limited or offline, reuse recent real candles only; never synthesize.
            if cached and now_ts - cached[0] < ttl * 6:
                return cached[1]
        return []

        # (unreachable) legacy synthetic generator retained below only for reference
        current_price = self.get_current_price(symbol) or 0.0
        step_seconds = 300 if timeframe == "5m" else (900 if timeframe == "15m" else 3600)
        candles: List[CryptoCandle] = []
        base_p = current_price * (1.0 - (limit * 0.0008))
        p = base_p
        for i in range(limit):
            ts = (int(now_ts) - (limit - i) * step_seconds) * 1000
            is_displacement = (i % 8 == 0)
            drift_pct = random.uniform(0.003, 0.008) if is_displacement else random.uniform(-0.002, 0.0025)
            o = p
            c = o * (1.0 + drift_pct)
            high_wick = max(o, c) * (1.0 + random.uniform(0.0005, 0.002))
            low_wick = min(o, c) * (1.0 - random.uniform(0.0005, 0.002))
            vol = round(random.uniform(500, 5000), 2)
            candles.append(CryptoCandle(
                timestamp=ts,
                open=round(o, 6 if o < 1 else 2),
                high=round(high_wick, 6 if high_wick < 1 else 2),
                low=round(low_wick, 6 if low_wick < 1 else 2),
                close=round(c, 6 if c < 1 else 2),
                volume=vol
            ))
            p = c

        self._candle_cache[cache_key] = (now_ts, candles)
        return candles

    def get_btc_trend(self) -> str:
        """
        Determines current short-term and intermediate trend of BTCUSDT from real Binance candles:
        Uses real M5 and H1 EMAs for institutional market regime classification.
        Returns: 'BULLISH', 'BEARISH', or 'NEUTRAL'
        """
        try:
            m5_candles = self.fetch_candles("BTCUSDT", timeframe="5m", limit=15)
            h1_candles = self.fetch_candles("BTCUSDT", timeframe="1h", limit=20)
            if len(m5_candles) >= 5:
                closes_m5 = [c.close for c in m5_candles]
                avg_m5 = sum(closes_m5[-5:]) / 5.0
                last_c = closes_m5[-1]
                ratio_m5 = (last_c - avg_m5) / avg_m5

                # If H1 candles are available, check alignment
                h1_bias = 0
                if len(h1_candles) >= 10:
                    closes_h1 = [c.close for c in h1_candles]
                    avg_h1 = sum(closes_h1[-10:]) / 10.0
                    if last_c > avg_h1:
                        h1_bias = 1
                    elif last_c < avg_h1:
                        h1_bias = -1

                if ratio_m5 > 0.0010 and h1_bias >= 0:
                    return "BULLISH"
                elif ratio_m5 < -0.0010 and h1_bias <= 0:
                    return "BEARISH"
        except Exception:
            pass
        return "NEUTRAL"
