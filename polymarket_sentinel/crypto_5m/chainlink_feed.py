"""
Chainlink Oracle Feed for Polymarket 5-Minute Up/Down markets.

Polymarket resolves these markets on Chainlink's <coin>/USD 60-second TWAP
(see each market's rules: "price according to the TWAP Chainlink data stream").
Binance BTCUSDT is quoted in Tether and sits roughly 0.15% above the USD
reference, so the exchange tape must never be used as the resolution series.

Polymarket's legacy real-time data service (RTDS) still relays the Chainlink
spot and 60-second TWAP series publicly, one point per second per symbol:

    wss://ws-live-data.polymarket.com
    {"action":"subscribe","subscriptions":[
        {"topic":"crypto_prices_chainlink","type":"*"},
        {"topic":"crypto_prices_twap_sixty","type":"*"}]}

Each new subscription first replays the preceding minute as a snapshot frame
(payload.data = [{timestamp, value}, ...]) and then streams update frames
(payload = {symbol, timestamp, value, full_accuracy_value}).

Polymarket has announced this endpoint will be retired in favour of PolyBolt
(wss://ws-live-v2.polymarket.com/ws), which requires CLOB API credentials plus
a Chainlink API key. When that happens this feed goes cold and the analyzer
falls back to the exchange tape with the strike guard still in force.
"""

import json
import ssl
import threading
import time
from collections import deque
from typing import Deque, Dict, List, Optional, Tuple

RTDS_URL = "wss://ws-live-data.polymarket.com"
TOPIC_SPOT = "crypto_prices_chainlink"
TOPIC_TWAP = "crypto_prices_twap_sixty"
DEFAULT_COINS = ("BTC", "ETH", "SOL", "XRP")
SYMBOL_MAP = {"btc/usd": "BTC", "eth/usd": "ETH", "sol/usd": "SOL", "xrp/usd": "XRP"}
HISTORY_SECONDS = 300.0

Point = Tuple[str, str, float, float]  # (topic, coin, unix_ts, value)


def _normalise_symbol(raw: object) -> str:
    sym = str(raw or "").strip().lower()
    if sym in SYMBOL_MAP:
        return SYMBOL_MAP[sym]
    return sym.split("/")[0].replace("usdt", "").replace("usd", "").upper()


def _to_unix_seconds(ts: object) -> Optional[float]:
    try:
        v = float(ts)
    except (TypeError, ValueError):
        return None
    return v / 1000.0 if v > 1e11 else v


def parse_rtds_frame(message: str) -> List[Point]:
    """
    Parses one RTDS text frame into (topic, coin, unix_ts, value) points.
    Snapshot frames expand to one point per sample; update frames yield one
    point; anything else (PONG, errors, acks) yields an empty list.
    """
    if not message or not message.strip().startswith("{"):
        return []
    try:
        frame = json.loads(message)
    except ValueError:
        return []
    topic = frame.get("topic")
    payload = frame.get("payload")
    if not topic or not isinstance(payload, dict):
        return []
    coin = _normalise_symbol(payload.get("symbol"))
    if not coin:
        return []

    points: List[Point] = []
    data = payload.get("data")
    if isinstance(data, list):
        for sample in data:
            if not isinstance(sample, dict):
                continue
            ts = _to_unix_seconds(sample.get("timestamp"))
            if ts is None or sample.get("value") is None:
                continue
            points.append((topic, coin, ts, float(sample["value"])))
        return points

    if payload.get("value") is not None:
        ts = _to_unix_seconds(payload.get("timestamp") if payload.get("timestamp") is not None else frame.get("timestamp"))
        if ts is None:
            ts = time.time()
        points.append((topic, coin, ts, float(payload["value"])))
    return points


class ChainlinkOracleFeed:
    """
    Background subscriber for Chainlink spot and 60s TWAP via Polymarket RTDS.
    Thread-safe readers return (value, age_seconds); value is None until the
    first real point for that coin has arrived.
    """

    def __init__(self, coins=DEFAULT_COINS, start: bool = True, ping_interval: float = 5.0):
        self.coins = tuple(c.upper() for c in coins)
        self.ping_interval = ping_interval
        self.lock = threading.RLock()
        # coin -> (feed_ts, value, received_at)
        self._spot: Dict[str, Tuple[float, float, float]] = {}
        self._twap: Dict[str, Tuple[float, float, float]] = {}
        self._spot_history: Dict[str, Deque[Tuple[float, float]]] = {c: deque() for c in self.coins}
        self._twap_history: Dict[str, Deque[Tuple[float, float]]] = {c: deque() for c in self.coins}
        self.connected = False
        self.last_message_at: float = 0.0
        self.last_error: str = ""
        self.unavailable_reason: str = ""
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        if start:
            self.start()

    # ── lifecycle ──────────────────────────────────────────────────────
    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run_forever, name="ChainlinkOracleFeed", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    # ── ingestion ──────────────────────────────────────────────────────
    def ingest(self, points: List[Point], received_at: Optional[float] = None):
        now = received_at if received_at is not None else time.time()
        with self.lock:
            for topic, coin, ts, value in points:
                if coin not in self.coins:
                    continue
                if topic == TOPIC_SPOT:
                    store, hist = self._spot, self._spot_history[coin]
                elif topic == TOPIC_TWAP:
                    store, hist = self._twap, self._twap_history[coin]
                else:
                    continue
                prev = store.get(coin)
                if prev is None or ts >= prev[0]:
                    store[coin] = (ts, value, now)
                hist.append((ts, value))
                cutoff = ts - HISTORY_SECONDS
                while hist and hist[0][0] < cutoff:
                    hist.popleft()
            if points:
                self.last_message_at = now

    # ── readers ────────────────────────────────────────────────────────
    def _read(self, store: Dict[str, Tuple[float, float, float]], coin: str) -> Tuple[Optional[float], float]:
        with self.lock:
            entry = store.get(coin.upper())
        if entry is None:
            return None, float("inf")
        return entry[1], max(0.0, time.time() - entry[2])

    def get_spot(self, coin: str = "BTC") -> Tuple[Optional[float], float]:
        return self._read(self._spot, coin)

    def get_twap(self, coin: str = "BTC") -> Tuple[Optional[float], float]:
        return self._read(self._twap, coin)

    def is_fresh(self, coin: str = "BTC", max_age: float = 5.0) -> bool:
        s, sa = self.get_spot(coin)
        t, ta = self.get_twap(coin)
        return s is not None and t is not None and sa <= max_age and ta <= max_age

    def get_twap_history(self, coin: str = "BTC") -> List[Tuple[float, float]]:
        with self.lock:
            return list(self._twap_history.get(coin.upper(), ()))

    def status(self) -> Dict[str, object]:
        with self.lock:
            return {
                "connected": self.connected,
                "last_message_age": (time.time() - self.last_message_at) if self.last_message_at else None,
                "last_error": self.last_error,
                "unavailable_reason": self.unavailable_reason,
                "coins_with_data": sorted(set(self._spot) & set(self._twap)),
            }

    # ── websocket loop ─────────────────────────────────────────────────
    def _run_forever(self):
        try:
            import asyncio
            import websockets  # noqa: F401
        except ImportError as e:
            self.unavailable_reason = f"websockets package missing ({e}); Chainlink feed disabled."
            return
        asyncio.run(self._loop())

    async def _loop(self):
        import asyncio
        import websockets

        backoff = 2.0
        verify_tls = True
        subscribe_frame = json.dumps({
            "action": "subscribe",
            "subscriptions": [{"topic": TOPIC_SPOT, "type": "*"}, {"topic": TOPIC_TWAP, "type": "*"}],
        })
        while not self._stop.is_set():
            ctx = ssl.create_default_context() if verify_tls else ssl._create_unverified_context()
            try:
                try:
                    conn = websockets.connect(RTDS_URL, ssl=ctx, open_timeout=10, proxy=None)
                except TypeError:  # older websockets without the proxy kwarg
                    conn = websockets.connect(RTDS_URL, ssl=ctx, open_timeout=10)
                async with conn as ws:
                    await ws.send(subscribe_frame)
                    self.connected = True
                    backoff = 2.0
                    last_ping = time.time()
                    while not self._stop.is_set():
                        if time.time() - last_ping >= self.ping_interval:
                            await ws.send("PING")
                            last_ping = time.time()
                        try:
                            msg = await asyncio.wait_for(ws.recv(), timeout=self.ping_interval)
                        except asyncio.TimeoutError:
                            if self.last_message_at and time.time() - self.last_message_at > 30:
                                raise ConnectionError("no RTDS data for 30s; reconnecting")
                            continue
                        if isinstance(msg, bytes):
                            msg = msg.decode("utf-8", "replace")
                        self.ingest(parse_rtds_frame(msg))
            except ssl.SSLError as e:
                self.last_error = f"TLS: {e}"
                verify_tls = False
            except Exception as e:  # network errors, server closes, policy closes
                self.last_error = f"{type(e).__name__}: {str(e)[:120]}"
            finally:
                self.connected = False
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30.0)
