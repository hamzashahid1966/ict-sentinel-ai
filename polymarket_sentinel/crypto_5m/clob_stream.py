"""
Live Polymarket order book over WebSocket, for the 5-minute bot's prices.

The analyzer used to ask the CLOB REST API for each token's book about once a second (cached 2 s), so the
prices it acted on were 1-3 s old. This keeps one WebSocket open to the public market channel and holds
the latest best bid / best ask for every token the analyzer asks about (pushed within ~0.1 s of a change).

The analyzer reads it through `top(token_id)`. It answers only while the stream is healthy and has a book
for that token; otherwise it returns None and the analyzer falls back to the REST book exactly as before.
Nothing here places orders.
"""

import asyncio
import json
import threading
import time
from typing import Dict, Optional, Tuple

CLOB_WS = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
HEALTHY_SECONDS = 20.0      # stream counts as healthy if any message arrived this recently
FORGET_SECONDS = 900.0      # unsubscribe tokens nobody asked about for 15 minutes


class ClobBookStream:
    def __init__(self, url: str = CLOB_WS):
        self.url = url
        self._lock = threading.Lock()
        self._top: Dict[str, Tuple[float, float, float]] = {}     # token -> (bid, ask, updated_at)
        self._wanted: Dict[str, float] = {}                      # token -> last asked
        self._pending = set()                                    # tokens to subscribe on the open socket
        self._last_msg = 0.0
        self._connected = False
        self._thread: Optional[threading.Thread] = None
        self.messages = 0

    # ---------------------------------------------------------------- reader API (any thread)
    def start(self) -> "ClobBookStream":
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="clob-book-stream", daemon=True)
            self._thread.start()
        return self

    def healthy(self) -> bool:
        return self._connected and time.time() - self._last_msg < HEALTHY_SECONDS

    def top(self, token_id: str) -> Optional[Tuple[float, float]]:
        """Latest (best_bid, best_ask) for token_id from the stream, or None (then use REST)."""
        token_id = str(token_id)
        with self._lock:
            if token_id not in self._wanted:
                self._pending.add(token_id)
            self._wanted[token_id] = time.time()
            hit = self._top.get(token_id)
        if hit is None or not self.healthy():
            return None
        return hit[0], hit[1]

    # ---------------------------------------------------------------- stream (own thread)
    def _set(self, token, bid, ask):
        if bid is None or ask is None:
            return
        with self._lock:
            self._top[str(token)] = (float(bid), float(ask), time.time())

    def handle(self, msg) -> None:
        """Apply one decoded market-channel message (public for tests)."""
        self._last_msg = time.time()
        self.messages += 1
        for m in (msg if isinstance(msg, list) else [msg]):
            if not isinstance(m, dict):
                continue
            et = m.get("event_type")
            if et == "best_bid_ask":
                self._set(m.get("asset_id"), m.get("best_bid"), m.get("best_ask"))
            elif et == "book":
                bids = [float(x["price"]) for x in m.get("bids", []) if float(x.get("size", 1)) > 0]
                asks = [float(x["price"]) for x in m.get("asks", []) if float(x.get("size", 1)) > 0]
                if bids and asks:
                    self._set(m.get("asset_id"), max(bids), min(asks))
            elif et == "price_change":
                for ch in m.get("price_changes", []):
                    self._set(ch.get("asset_id"), ch.get("best_bid"), ch.get("best_ask"))

    def _run(self):
        asyncio.run(self._loop())

    async def _loop(self):
        import websockets
        backoff = 1.0
        while True:
            while not self._wanted:                      # an empty subscription can mean "everything"
                await asyncio.sleep(0.5)
            try:
                async with websockets.connect(self.url, ping_interval=None, max_size=2 ** 22) as ws:
                    with self._lock:
                        tokens = list(self._wanted)
                        self._pending.clear()
                    await ws.send(json.dumps({"assets_ids": tokens, "type": "market", "custom_feature_enabled": True}))
                    self._connected, backoff = True, 1.0
                    self._last_msg = time.time()
                    last_ping = last_tidy = time.time()
                    while True:
                        try:
                            raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                            if raw and raw not in ("PONG", "pong"):
                                try:
                                    self.handle(json.loads(raw))
                                except ValueError:
                                    pass
                            elif raw:
                                self._last_msg = time.time()
                        except asyncio.TimeoutError:
                            pass
                        with self._lock:
                            new = list(self._pending)
                            self._pending.clear()
                        if new:
                            await ws.send(json.dumps({"assets_ids": new, "operation": "subscribe"}))
                        now = time.time()
                        if now - last_ping >= 10:
                            await ws.send("PING")
                            last_ping = now
                        if now - last_tidy >= 60:
                            with self._lock:
                                old = [t for t, ts in self._wanted.items() if now - ts > FORGET_SECONDS]
                                for t in old:
                                    self._wanted.pop(t, None)
                                    self._top.pop(t, None)
                            if old:
                                await ws.send(json.dumps({"assets_ids": old, "operation": "unsubscribe"}))
                            last_tidy = now
            except Exception:
                pass
            self._connected = False
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30.0)
