"""
Real-time Multi-Crypto Price Feed (BTC, ETH, SOL, XRP).
Dual-source streaming from Binance batch ticker and Coinbase spot API with sub-second caching.
Calculates Instantaneous Spot Price, Chainlink 60s TWAP Oracle Price, Oracle Lag, and Projected Price.
"""

import time
import ssl
import json
import socket
import urllib.request
import urllib.parse
import threading
from typing import Dict, List, Tuple, Any

# Enforce strict 3.0s global socket timeout to prevent any thread from hanging indefinitely
socket.setdefaulttimeout(3.0)


SUPPORTED_COINS = ["BTC", "ETH", "SOL", "XRP"]

BINANCE_SYMBOL_MAP = {
    "BTC": "BTCUSDT",
    "ETH": "ETHUSDT",
    "SOL": "SOLUSDT",
    "XRP": "XRPUSDT"
}

DEFAULT_VOLATILITY = {
    "BTC": 15.0,    # USD per 1m
    "ETH": 1.20,    # USD per 1m
    "SOL": 0.15,    # USD per 1m
    "XRP": 0.0025   # USD per 1m
}

DEFAULT_FALLBACK_PRICES = {
    "BTC": 59080.0,
    "ETH": 1625.0,
    "SOL": 68.80,
    "XRP": 0.9120
}


# A Chainlink point older than this is treated as stale and the exchange tape is used instead.
CHAINLINK_MAX_AGE_SECONDS = 5.0


class MultiCryptoPriceFeed:
    def __init__(self, start_background: bool = True, use_chainlink: bool = True):
        self.lock = threading.RLock()
        # DEFAULT_FALLBACK_PRICES are display placeholders only. They never enter the
        # tick history and a coin is not "warm" until a real exchange print replaces them.
        self._prices: Dict[str, float] = dict(DEFAULT_FALLBACK_PRICES)
        self._anchor_prices: Dict[str, float] = dict(DEFAULT_FALLBACK_PRICES)
        self._warm: Dict[str, bool] = {c: False for c in SUPPORTED_COINS}
        self._last_update_ts: float = 0.0
        self._tick_history: Dict[str, List[Tuple[float, float]]] = {c: [] for c in SUPPORTED_COINS}
        self._ssl_ctx = ssl._create_unverified_context()
        self._headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}

        # Chainlink <coin>/USD spot + 60s TWAP: the series Polymarket actually resolves on.
        self.chainlink = None
        if use_chainlink:
            try:
                from .chainlink_feed import ChainlinkOracleFeed
                self.chainlink = ChainlinkOracleFeed(coins=SUPPORTED_COINS, start=start_background)
            except Exception:
                self.chainlink = None

        # Dedicated background poller thread for the exchange tape (Binance, Coinbase fallback)
        self._bg_thread = None
        if start_background:
            self._bg_thread = threading.Thread(target=self._background_poller, daemon=True)
            self._bg_thread.start()

    def is_warm(self, symbol: str = "BTC") -> bool:
        """True once at least one real exchange print has been received for the coin."""
        with self.lock:
            return bool(self._warm.get(symbol.upper(), False))

    def _background_poller(self):
        """Continuously streams live ticks from Binance / Coinbase in background."""
        while True:
            try:
                self._refresh_prices()
            except Exception:
                pass
            time.sleep(0.9)

    def get_price(self, symbol: str = "BTC") -> float:
        """Returns the current spot price of the requested coin instantaneously from cache."""
        symbol = symbol.upper()
        with self.lock:
            return self._prices.get(symbol, DEFAULT_FALLBACK_PRICES.get(symbol, 1.0))

    def get_btc_price(self) -> float:
        """Backwards compatibility helper."""
        return self.get_price("BTC")

    def get_all_prices(self) -> Dict[str, float]:
        """Returns instantaneous cached prices for BTC, ETH, SOL, XRP (<0.1ms)."""
        with self.lock:
            return dict(self._prices)

    def _refresh_prices(self):
        """Executed by background thread only — non-blocking to consumers."""
        now = time.time()
        fresh = self._fetch_binance_batch()

        if not fresh or len(fresh) < len(SUPPORTED_COINS):
            cb_fresh = self._fetch_coinbase()
            if cb_fresh:
                if not fresh:
                    fresh = cb_fresh
                else:
                    for k, v in cb_fresh.items():
                        if k not in fresh:
                            fresh[k] = v

        if not fresh:
            # Offline or rate-limited: leave the tape untouched. Fabricating ticks here
            # would pollute the TWAP and could lock a round strike on an invented price.
            return

        with self.lock:
            self._anchor_prices.update(fresh)
            self._prices.update(fresh)
            self._last_update_ts = now
            for coin, px in fresh.items():
                if coin not in self._tick_history:
                    continue
                self._warm[coin] = True
                self._tick_history[coin].append((now, px))
                cutoff = now - 300.0
                self._tick_history[coin] = [t for t in self._tick_history[coin] if t[0] >= cutoff]

    def _binance_batch_url(self) -> str:
        """
        Builds the multi-symbol ticker URL. Binance validates the `symbols` array
        against a strict pattern and returns HTTP 400 on any whitespace, so the
        JSON must be serialised without the default ", " separator.
        """
        symbols_json = json.dumps([BINANCE_SYMBOL_MAP[c] for c in SUPPORTED_COINS], separators=(",", ":"))
        return f"https://api.binance.com/api/v3/ticker/price?symbols={urllib.parse.quote(symbols_json, safe=',')}"

    def _fetch_binance_batch(self) -> Dict[str, float]:
        """Fetches all 4 coins in a single HTTP request from Binance."""
        try:
            url = self._binance_batch_url()
            req = urllib.request.Request(url, headers=self._headers)
            with urllib.request.urlopen(req, context=self._ssl_ctx, timeout=2.0) as res:
                items = json.loads(res.read())
                rev_map = {v: k for k, v in BINANCE_SYMBOL_MAP.items()}
                results = {}
                for it in items:
                    sym = rev_map.get(it["symbol"])
                    if sym:
                        results[sym] = float(it["price"])
                return results
        except Exception:
            return {}

    def _fetch_coinbase(self) -> Dict[str, float]:
        """Fallback spot price query via Coinbase public API."""
        results = {}
        for coin in ["BTC", "ETH", "SOL"]:
            try:
                url = f"https://api.coinbase.com/v2/prices/{coin}-USD/spot"
                req = urllib.request.Request(url, headers=self._headers)
                with urllib.request.urlopen(req, context=self._ssl_ctx, timeout=1.5) as res:
                    data = json.loads(res.read())
                    amt = float(data["data"]["amount"])
                    results[coin] = amt
            except Exception:
                pass
        return results

    def get_twap_price(self, symbol: str = "BTC", window_sec: float = 60.0) -> float:
        """
        Calculates 60-second Time-Weighted Average Price (TWAP) matching Chainlink data streams.
        Averages sampled prices over the rolling window.
        """
        sym = symbol.upper()
        now = time.time()
        with self.lock:
            history = self._tick_history.get(sym, [])
            recent = [p[1] for p in history if p[0] >= (now - window_sec)]
            if len(recent) >= 2:
                return round(sum(recent) / len(recent), 4 if sym == "XRP" else 2)
            # Fallback to current spot
            return self._prices.get(sym, DEFAULT_FALLBACK_PRICES.get(sym, 1.0))

    def get_oracle_analysis(self, symbol: str = "BTC") -> Dict[str, Any]:
        """
        Computes the Oracle Basis Discrepancy on the series Polymarket resolves on:
        - spot / twap: Chainlink <coin>/USD spot and 60s TWAP when fresh, else the
          exchange tape and a 60s average of it (source = "chainlink" | "binance")
        - exchange_spot: the Binance/Coinbase print, kept separately as a leading
          indicator (it runs ~2s ahead of Chainlink and ~0.15% above it in USDT terms)
        - lag_delta: spot - twap (spot leads TWAP)
        - projected_twap: where the TWAP is heading as spot is absorbed
        """
        sym = symbol.upper()
        exchange_spot = self.get_price(sym)
        source = "binance"
        spot = exchange_spot
        twap = self.get_twap_price(sym, window_sec=60.0)

        cl = self.chainlink
        if cl is not None:
            try:
                cl_spot, spot_age = cl.get_spot(sym)
                cl_twap, twap_age = cl.get_twap(sym)
            except Exception:
                cl_spot = cl_twap = None
                spot_age = twap_age = float("inf")
            if (cl_spot is not None and cl_twap is not None
                    and spot_age <= CHAINLINK_MAX_AGE_SECONDS and twap_age <= CHAINLINK_MAX_AGE_SECONDS):
                source = "chainlink"
                spot = float(cl_spot)
                twap = float(cl_twap)

        nd = 4 if sym == "XRP" else 2
        lag_delta = round(spot - twap, nd)
        projected = round((spot * 0.65) + (twap * 0.35), nd)
        return {
            "spot": spot,
            "twap": twap,
            "lag_delta": lag_delta,
            "projected_twap": projected,
            "source": source,
            "exchange_spot": exchange_spot,
        }

    def get_volatility(self, symbol: str = "BTC") -> float:
        """Calculates 1-minute standard deviation / volatility for the asset."""
        sym = symbol.upper()
        with self.lock:
            history = self._tick_history.get(sym, [])
            default_vol = DEFAULT_VOLATILITY.get(sym, 1.0)
            if len(history) < 5:
                return default_vol

            prices = [p[1] for p in history[-60:]]
            if len(prices) < 2:
                return default_vol

            deltas = [abs(prices[i] - prices[i-1]) for i in range(1, len(prices))]
            avg_delta = sum(deltas) / len(deltas)
            return max(default_vol * 0.5, avg_delta * (60 ** 0.5))

    def get_1m_volatility(self) -> float:
        """Backwards compatibility helper."""
        return self.get_volatility("BTC")


# Backwards compatibility alias
BtcPriceFeed = MultiCryptoPriceFeed
