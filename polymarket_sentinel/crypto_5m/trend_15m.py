"""
PAPER bot for Polymarket's BTC 15-minute Up/Down rounds, running the same trend rule as the 5-minute bot.

It never places real orders. Every second it reads the current 15-minute round from Polymarket (through the
same analyzer the 5-minute bot uses, so the local install gets live WebSocket prices), and:
  ENTRY   `entry_seconds` into a round, take the side that won the previous 15-minute round and buy `stake`
          dollars at its best ask, only if that price is between `min_price` and `max_price`.
  EXITS   either in two parts (sell half at +`half_at`, the rest at +`rest_at`), or all at once at
          +`single_tp` when that is set; plus, if `late_exit_seconds` is set, sell what is left in the last
          `late_exit_seconds` when the bid is under `late_exit_price`. Otherwise hold to the result.
  COSTS   Polymarket's taker fee 0.07 * p * (1 - p) per share on every buy and sell; sales at the best bid.
The rule's numbers are passed in by the caller, so the local install and the online server can each run the
15-minute bot with the same rule as their own 5-minute bot.
"""

import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

ROUND = 900


def fee(shares: float, price: float) -> float:
    return shares * 0.07 * price * (1 - price)


class Trend15mBot:
    def __init__(self, analyzer, activity_callback=None, *, stake: float = 20.0, bankroll: float = 400.0,
                 min_price: float = 0.50, max_price: float = 0.85, entry_seconds: int = 10,
                 half_at: Optional[float] = 0.30, rest_at: Optional[float] = 0.45, single_tp: Optional[float] = None,
                 late_exit_seconds: Optional[int] = 60, late_exit_price: float = 0.30,
                 enabled: bool = True, auto_start: bool = True):
        self.analyzer = analyzer
        self.activity_callback = activity_callback
        self.stake, self.min_price, self.max_price = stake, min_price, max_price
        self.entry_seconds = entry_seconds
        self.half_at, self.rest_at, self.single_tp = half_at, rest_at, single_tp
        self.late_exit_seconds, self.late_exit_price = late_exit_seconds, late_exit_price
        self.starting_balance = bankroll
        self.balance = bankroll
        self.realized_pnl = 0.0
        self.is_enabled = enabled
        self.active: Optional[Dict[str, Any]] = None
        self.history: List[Dict[str, Any]] = []
        self.decided_rounds = set()
        self._winner_cache: Dict[int, str] = {}
        self.lock = threading.RLock()
        self.last_tick = 0.0
        self._thread = None
        if auto_start:
            self.start()

    def start(self):
        """Start the once-a-second loop (the web server does this; tests and scripts never do)."""
        if self._thread is None:
            self._thread = threading.Thread(target=self._loop, name="trend-15m", daemon=True)
            self._thread.start()
        return self

    # ---------------------------------------------------------------- helpers
    def _log(self, title: str, details: str = "", level: str = "info"):
        if self.activity_callback:
            try:
                self.activity_callback("15M_TREND", title, details, level)
            except Exception:
                pass

    def _market(self, round_ts: int) -> Dict[str, Any]:
        try:
            return self.analyzer.fetch_polymarket_market("BTC", round_ts, timeframe="15m") or {}
        except Exception:
            return {}

    def _winner(self, round_ts: int) -> Optional[str]:
        if round_ts in self._winner_cache:
            return self._winner_cache[round_ts]
        m = self._market(round_ts)
        if not m.get("found"):
            return None
        w = m.get("winning_outcome")
        if not w:
            up = m.get("price_up")
            if up is None or 0.1 < float(up) < 0.9:
                return None
            w = "UP" if float(up) >= 0.5 else "DOWN"
        self._winner_cache[round_ts] = w
        if len(self._winner_cache) > 30:
            self._winner_cache.pop(min(self._winner_cache))
        return w

    def toggle(self) -> bool:
        with self.lock:
            self.is_enabled = not self.is_enabled
        self._log("15M bot " + ("started" if self.is_enabled else "paused"))
        return self.is_enabled

    # ---------------------------------------------------------------- one tick
    def _loop(self):
        while True:
            try:
                self.tick()
            except Exception:
                pass
            time.sleep(1.0)

    def tick(self, now: Optional[float] = None):
        now = time.time() if now is None else now
        self.last_tick = now
        with self.lock:
            if self.active is not None:
                self._manage(now)
            if self.active is None and self.is_enabled:
                self._maybe_enter(now)

    def _maybe_enter(self, now: float):
        r = int(now) // ROUND * ROUND
        if r in self.decided_rounds or now < r + self.entry_seconds or now > r + ROUND - 120:
            return
        prev = self._winner(r - ROUND)
        if prev is None:
            return                                           # not known yet: try again next second
        m = self._market(r)
        if not m.get("found") or m.get("price_source") != "clob":
            return
        px = round(float(m["price_up"] if prev == "UP" else m["price_down"]), 3)
        self.decided_rounds.add(r)
        if len(self.decided_rounds) > 50:
            self.decided_rounds.discard(min(self.decided_rounds))
        if not self.min_price <= px <= self.max_price:
            self._log(f"15M: skip round ({prev} costs {px * 100:.0f}c)",
                      f"Previous 15-minute round won by {prev}; outside {self.min_price * 100:.0f}-{self.max_price * 100:.0f}c.")
            return
        shares = self.stake / px
        commission = fee(shares, px)
        if self.stake + commission > self.balance:
            self._log("15M: not enough paper balance", f"Need ${self.stake + commission:.2f}, have ${self.balance:.2f}.", "warning")
            return
        self.balance -= self.stake + commission
        self.active = {"round_ts": r, "side": prev, "entry": px, "shares": shares, "cost": self.stake,
                       "commission": commission, "half_sold": False, "banked": 0.0,
                       "opened": datetime.now(timezone.utc).isoformat(), "notes": []}
        self._log(f"15M: BUY {prev} @ {px * 100:.0f}c (${self.stake:g})",
                  f"Previous 15-minute round won by {prev}; {shares:.2f} shares, fee ${commission:.3f}.", "accent")

    def _sell(self, shares: float, bid: float, note: str) -> float:
        """Sell part of the open trade at the bid; returns that part's profit (already booked)."""
        t = self.active
        frac = shares / t["shares"]
        part_cost, part_comm = t["cost"] * frac, t["commission"] * frac
        proceeds = shares * bid - fee(shares, bid)
        pnl = proceeds - part_cost - part_comm
        t["shares"] -= shares
        t["cost"] -= part_cost
        t["commission"] -= part_comm
        t["banked"] += pnl
        self.balance += proceeds
        self.realized_pnl += pnl
        t["notes"].append(f"{note} at {bid * 100:.0f}c ({pnl:+.2f}$)")
        return pnl

    def _close(self, result: str, settle_price: float):
        t = self.active
        self.history.insert(0, {"round_ts": t["round_ts"], "side": t["side"], "entry": t["entry"],
                                "stake": self.stake, "pnl": round(t["banked"], 2),
                                "status": "WON" if t["banked"] >= 0 else "LOST", "result": result,
                                "notes": t["notes"], "opened": t["opened"], "settle_price": settle_price})
        del self.history[200:]
        self._log(f"15M: closed {t['side']} ({t['banked']:+.2f}$)", "; ".join(t["notes"]) or result,
                  "success" if t["banked"] >= 0 else "warning")
        self.active = None

    def _manage(self, now: float):
        t = self.active
        r_end = t["round_ts"] + ROUND
        if now >= r_end:                                      # round over: settle what is left at the result
            w = self._winner(t["round_ts"])
            if w is None:
                return
            if t["shares"] > 1e-9:
                payout = t["shares"] * (1.0 if w == t["side"] else 0.0)
                pnl = payout - t["cost"] - t["commission"]
                t["banked"] += pnl
                self.balance += payout
                self.realized_pnl += pnl
                t["notes"].append(f"held to the result: {w} won ({pnl:+.2f}$)")
            self._close(f"{w} won", 1.0 if w == t["side"] else 0.0)
            return
        m = self._market(t["round_ts"])
        if not m.get("found") or m.get("price_source") != "clob":
            return
        bid = float(m["bid_up"] if t["side"] == "UP" else m["bid_down"])
        if bid <= 0:
            return
        held_cost = t["cost"] + t["commission"]
        gain = (t["shares"] * bid - fee(t["shares"], bid) - held_cost) / t["cost"] if t["cost"] > 0 else 0.0
        if self.single_tp is not None:
            if gain >= self.single_tp:
                self._sell(t["shares"], bid, f"cashed out (+{self.single_tp * 100:.0f}%)")
                self._close("cashed out", bid)
                return
        else:
            if not t["half_sold"] and self.half_at is not None and gain >= self.half_at:
                self._sell(t["shares"] / 2, bid, f"sold half (+{self.half_at * 100:.0f}%)")
                t["half_sold"] = True
                self._log(f"15M: sold half at {bid * 100:.0f}c", "The other half waits for the next target.", "success")
                return
            if t["half_sold"] and self.rest_at is not None and gain >= self.rest_at:
                self._sell(t["shares"], bid, f"sold the rest (+{self.rest_at * 100:.0f}%)")
                self._close("cashed out", bid)
                return
        if self.late_exit_seconds is not None and r_end - now <= self.late_exit_seconds and bid < self.late_exit_price:
            self._sell(t["shares"], bid, "sold in the last minute (under 30c)")
            self._close("late exit", bid)

    # ---------------------------------------------------------------- dashboard
    def get_state(self) -> Dict[str, Any]:
        with self.lock:
            won = sum(1 for h in self.history if h["status"] == "WON")
            return {"is_enabled": self.is_enabled, "trading_mode": "PAPER", "timeframe": "15m",
                    "stake": self.stake, "balance": round(self.balance, 2), "starting_balance": self.starting_balance,
                    "realized_pnl": round(self.realized_pnl, 2), "total_trades": len(self.history),
                    "total_won": won, "total_lost": len(self.history) - won,
                    "rule": {"min_price": self.min_price, "max_price": self.max_price, "entry_seconds": self.entry_seconds,
                             "half_at": self.half_at, "rest_at": self.rest_at, "single_tp": self.single_tp,
                             "late_exit_seconds": self.late_exit_seconds},
                    "active_trade": dict(self.active) if self.active else None,
                    "history": self.history[:20], "last_tick": self.last_tick}

