"""
Polymarket 5-Minute Multi-Crypto Round Analyzer (BTC, ETH, SOL, XRP).
Analyzes intra-candle displacement, Z-score probabilities, and selects highest-edge coin at 2-minute mark.
Calculates Spot Price vs Chainlink 60s TWAP Oracle Price, Oracle Lag, and Projected Settlement.
"""

import time
import math
import ssl
import json
import socket
import urllib.request
import threading
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

# Global 3.0s timeout prevents any hung network reads from stalling the surveillance ticker
socket.setdefaulttimeout(3.0)

from .models import Btc5mRound
from .price_feed import MultiCryptoPriceFeed, SUPPORTED_COINS
from .session_predictor import NextSessionPredictor


MIN_DELTA_THRESHOLD = {
    "BTC": 25.00,
    "ETH": 1.80,
    "SOL": 0.30,
    "XRP": 0.0040
}

CLEAN_MOVE_THRESHOLD = {
    "BTC": 35.00,
    "ETH": 2.50,
    "SOL": 0.45,
    "XRP": 0.0060
}

CLOB_BOOK_TTL_SECONDS = 2.0
CLOB_HOST = "https://clob.polymarket.com"


def best_levels(book: Dict[str, Any]):
    """(best_bid, best_ask) from a CLOB order book payload; None where that side is empty."""
    bids = [float(b["price"]) for b in (book or {}).get("bids", []) if float(b.get("price", 0)) > 0]
    asks = [float(a["price"]) for a in (book or {}).get("asks", []) if float(a.get("price", 0)) > 0]
    return (max(bids) if bids else None, min(asks) if asks else None)


DOMINANT_LEAD_THRESHOLD = {
    "BTC": 50.00,
    "ETH": 3.20,
    "SOL": 0.50,
    "XRP": 0.0070
}


class MultiCryptoRoundAnalyzer:
    def __init__(self, price_feed: MultiCryptoPriceFeed):
        self.feed = price_feed
        self.predictor = NextSessionPredictor(price_feed)
        self.lock = threading.RLock()
        self._strike_prices: Dict[str, float] = {}  # key: f"{coin}_{round_ts}" -> P0
        self._timeline_cache: Dict[str, Any] = {}
        self._book_cache: Dict[str, Any] = {}
        self._ssl_ctx = ssl._create_unverified_context()
        self._headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}

    @staticmethod
    def get_current_round_ts() -> int:
        """Returns the unix epoch boundary of the current 5m round (rounded to 300s)."""
        return (int(time.time()) // 300) * 300

    def get_or_set_strike(self, coin_or_round: str, round_ts_or_px: Any, current_px: Optional[float] = None) -> float:
        """
        Locks the strike price P0.
        Supports both:
        - get_or_set_strike("BTC", 1700000000, 58800.0)
        - get_or_set_strike("btc-updown-5m-1700000000", 58800.0)
        """
        with self.lock:
            if current_px is None:
                key = coin_or_round
                px = float(round_ts_or_px)
            else:
                key = f"{coin_or_round.upper()}_{round_ts_or_px}"
                px = float(current_px)

            if key in self._strike_prices:
                return self._strike_prices[key]
            self._strike_prices[key] = px
            return px

    def _http_json(self, url: str, timeout: float = 2.5) -> Any:
        req = urllib.request.Request(url, headers=self._headers)
        with urllib.request.urlopen(req, context=self._ssl_ctx, timeout=timeout) as res:
            return json.loads(res.read())

    def _fetch_clob_book(self, token_id: str) -> Optional[Dict[str, Any]]:
        """Live order book for one outcome token, cached for CLOB_BOOK_TTL_SECONDS."""
        now = time.time()
        hit = self._book_cache.get(token_id)
        if hit and now - hit[0] < CLOB_BOOK_TTL_SECONDS:
            return hit[1]
        try:
            book = self._http_json(f"{CLOB_HOST}/book?token_id={token_id}", timeout=2.5)
        except Exception:
            return None
        self._book_cache[token_id] = (now, book)
        return book

    def fetch_polymarket_market(self, coin: str, round_ts: int, timeframe: str = "5m") -> Dict[str, Any]:
        """
        Fetches the round's market from Gamma and prices it from the LIVE CLOB order book.
        price_up / price_down are the best asks (what a buyer pays now); bid_up / bid_down are the
        best bids (what a seller receives). Gamma's outcomePrices lag the book by minutes and are
        kept only as gamma_price_* for reference; price_source says which one you are looking at.
        """
        coin_slug = coin.lower()
        slug = f"{coin_slug}-updown-{timeframe}-{round_ts}"
        url = f"https://gamma-api.polymarket.com/events?slug={slug}"
        try:
            data = self._http_json(url, timeout=2.5)
            if True:
                if data and len(data) > 0:
                    ev = data[0]
                    markets = ev.get("markets", [])
                    if markets:
                        m = markets[0]
                        prices = m.get("outcomePrices")
                        if isinstance(prices, str):
                            prices = json.loads(prices)
                        px_up = float(prices[0]) if prices and len(prices) > 0 else 0.50
                        px_down = float(prices[1]) if prices and len(prices) > 1 else 0.50

                        accepting_orders = m.get("acceptingOrders", True)
                        is_closed = m.get("closed", False) or ev.get("closed", False)
                        resolution_status = m.get("umaResolutionStatus", "")
                        price_to_beat = ev.get("eventMetadata", {}).get("priceToBeat")
                        end_date_iso = m.get("endDate") or ev.get("endDate")

                        winning_outcome = None
                        if is_closed or resolution_status == "resolved" or px_up >= 0.90 or px_down >= 0.90:
                            if px_up >= 0.90:
                                winning_outcome = "UP"
                            elif px_down >= 0.90:
                                winning_outcome = "DOWN"

                        clob_token_ids = m.get("clobTokenIds")
                        if isinstance(clob_token_ids, str):
                            try:
                                clob_token_ids = json.loads(clob_token_ids)
                            except Exception:
                                pass

                        gamma_up, gamma_down = px_up, px_down
                        bid_up = bid_down = 0.0
                        price_source = "gamma"
                        if clob_token_ids and len(clob_token_ids) >= 2 and not is_closed:
                            book_up = self._fetch_clob_book(str(clob_token_ids[0]))
                            book_down = self._fetch_clob_book(str(clob_token_ids[1]))
                            b_up, a_up = best_levels(book_up) if book_up else (None, None)
                            b_dn, a_dn = best_levels(book_down) if book_down else (None, None)
                            if a_up is not None and a_dn is not None:
                                px_up, px_down = a_up, a_dn
                                bid_up, bid_down = (b_up or 0.0), (b_dn or 0.0)
                                price_source = "clob"
                                accepting_orders = accepting_orders and True

                        return {
                            "found": True,
                            "slug": slug,
                            "title": ev.get("title", f"{coin} Up or Down 5m"),
                            "price_up": px_up,
                            "price_down": px_down,
                            "bid_up": bid_up,
                            "bid_down": bid_down,
                            "gamma_price_up": gamma_up,
                            "gamma_price_down": gamma_down,
                            "price_source": price_source,
                            "accepting_orders": accepting_orders,
                            "closed": is_closed,
                            "resolution_status": resolution_status,
                            "winning_outcome": winning_outcome,
                            "price_to_beat": float(price_to_beat) if price_to_beat is not None else None,
                            "end_date_iso": end_date_iso,
                            "clob_token_ids": clob_token_ids
                        }
        except Exception:
            pass

        return {
            "found": False,
            "slug": slug,
            "title": f"{coin} Up or Down 5m ({time.strftime('%H:%M', time.gmtime(round_ts))} UTC)",
            "price_up": 0.50,
            "price_down": 0.50,
            "bid_up": 0.0,
            "bid_down": 0.0,
            "gamma_price_up": None,
            "gamma_price_down": None,
            "price_source": "estimate",
            "accepting_orders": True,
            "closed": False,
            "resolution_status": "",
            "winning_outcome": None,
            "price_to_beat": None,
            "end_date_iso": None,
            "clob_token_ids": None
        }

    def fetch_polymarket_5m_market(self, round_ts: int) -> Dict[str, Any]:
        """Backwards compatibility helper."""
        return self.fetch_polymarket_market("BTC", round_ts)

    def analyze_single_coin(self, coin: str, now_ts: int, round_ts: int) -> Btc5mRound:
        """Analyzes 5m round metrics with dual Spot & Chainlink TWAP Oracle tracking, synchronized with Polymarket."""
        end_ts = round_ts + 300
        seconds_rem = max(0, end_ts - now_ts)
        round_id = f"{coin.lower()}-updown-5m-{round_ts}"

        # 1. Spot Price & Oracle TWAP Analysis
        oracle = self.feed.get_oracle_analysis(coin)
        spot_px = oracle["spot"]
        twap_px = oracle["twap"]
        lag_delta = oracle["lag_delta"]
        projected_twap = oracle["projected_twap"]

        # 2. Polymarket Orderbook Prices & Real Status
        poly_data = self.fetch_polymarket_market(coin, round_ts)
        mkt_up = poly_data["price_up"]
        mkt_down = poly_data["price_down"]

        # Parse exact seconds remaining from Polymarket contract endDate if available
        if poly_data.get("end_date_iso"):
            try:
                dt_str = poly_data["end_date_iso"].replace("Z", "+00:00")
                target_dt = datetime.fromisoformat(dt_str)
                poly_sec_rem = max(0, int(target_dt.timestamp() - now_ts))
                seconds_rem = poly_sec_rem
            except Exception:
                pass

        # 3. Strike Price P0 (Prefer Polymarket's official priceToBeat when deployed)
        # Polymarket only publishes priceToBeat after the round closes, so during live
        # trading the strike is our own TWAP at first sight of the round. That value
        # must come from a real print: a cold feed still holds the hard-coded fallback
        # price, and locking it produced four-figure phantom deltas in production.
        feed_warm = True
        try:
            feed_warm = bool(self.feed.is_warm(coin))
        except Exception:
            pass
        if not poly_data.get("price_to_beat") and not feed_warm and f"{coin.upper()}_{round_ts}" not in self._strike_prices:
            return Btc5mRound(
                round_id=round_id, slug=poly_data["slug"], title=poly_data["title"],
                strike_price=0.0, current_btc_price=twap_px, price_delta=0.0,
                start_time=round_ts, end_time=end_ts, seconds_remaining=seconds_rem,
                market_price_up=mkt_up, market_price_down=mkt_down,
                calculated_prob_up=0.5, calculated_prob_down=0.5, z_score=0.0,
                ict_fvg_status="NEUTRAL_SWEEP", signal="ABSTAIN",
                signal_reason=f"Oracle feed warming for {coin}: no real Chainlink or exchange print yet. Strike not locked.",
                symbol=coin, spot_price=spot_px, twap_price=twap_px, oracle_lag_delta=lag_delta,
                projected_twap=projected_twap, clob_token_ids=poly_data.get("clob_token_ids"),
                oracle_source=str(oracle.get("source", "binance")),
                bid_up=float(poly_data.get("bid_up") or 0.0), bid_down=float(poly_data.get("bid_down") or 0.0),
                price_source=str(poly_data.get("price_source", "gamma")),
            )
        initial_strike = poly_data.get("price_to_beat") if poly_data.get("price_to_beat") else twap_px
        strike_px = self.get_or_set_strike(coin, round_ts, initial_strike)

        # If live Gamma API event is not found:
        # Reflect live market maker pricing consensus (as seen on Polymarket CLOB order book)
        if not poly_data.get("found"):
            vol_1m = self.feed.get_volatility(coin)
            delta_spot = spot_px - strike_px
            if vol_1m > 0 and abs(delta_spot) > 0.001:
                rough_z = delta_spot / max(0.001, vol_1m * 1.6)
                est_up = round(0.50 + math.tanh(rough_z * 0.6) * 0.42, 2)
                est_up = max(0.05, min(0.95, est_up))
                mkt_up = est_up
                mkt_down = round(1.0 - est_up, 2)

        # 4. Projected Settlement Delta & Volatility Z-Score
        # Delta evaluated between Projected TWAP and Strike
        delta = round(projected_twap - strike_px, 4 if coin == "XRP" else 2)
        vol_1m = self.feed.get_volatility(coin)
        vol_rem = max(vol_1m * 0.3, vol_1m * math.sqrt(max(0.1, seconds_rem / 60.0)))
        z_score = round(delta / vol_rem, 2)

        # Probability via Cumulative Normal Distribution Phi(Z)
        prob_up = round(0.5 * (1.0 + math.erf(z_score / math.sqrt(2.0))), 3)
        prob_up = max(0.01, min(0.99, prob_up))
        prob_down = round(1.0 - prob_up, 3)

        # 5. Pattern
        if z_score >= 1.5:
            pattern = "BULLISH_DISPLACEMENT"
        elif z_score <= -1.5:
            pattern = "BEARISH_DISPLACEMENT"
        else:
            pattern = "NEUTRAL_SWEEP"

        # 6. Strategic Signal Evaluation (2-Minute Window)
        signal = "ABSTAIN"
        reason = ""
        min_delta = MIN_DELTA_THRESHOLD.get(coin, 1.0)
        clean_delta = CLEAN_MOVE_THRESHOLD.get(coin, 2.0)

        # Gate 0: Polymarket Contract Availability Gate
        if poly_data.get("closed"):
            signal = "ABSTAIN"
            reason = f"Polymarket contract ({poly_data.get('slug')}) is closed on exchange."
        elif not poly_data.get("accepting_orders", True):
            signal = "ABSTAIN"
            reason = f"Polymarket orderbook ({poly_data.get('slug')}) is not accepting orders."
        # Gate 1: Strike Lock Window (First 30s)
        # Allows entering after only 30s of candle formation (4:30 remaining), capturing early moves at 40¢ - 60¢
        elif seconds_rem > 270:
            signal = "ABSTAIN"
            reason = f"Opening Strike Lock ({seconds_rem}s left): Waiting 30s for opening strike confirmation."
        # Gate 2: Final Freeze (Last 45s)
        elif seconds_rem < 45:
            signal = "ABSTAIN"
            reason = f"Final 45s Freeze: High spread latency penalty. Entry locked."
        # Gate 3: Chop / Noise Filter
        elif abs(delta) < min_delta:
            signal = "ABSTAIN"
            reason = f"{coin} projected delta is within ${min_delta} noise band of strike (${strike_px:,.4f}). Reversal risk too high."
        else:
            edge_up = round(prob_up - mkt_up, 3)
            edge_down = round(prob_down - mkt_down, 3)
            lag_indicator = f"{oracle.get('source', 'binance').title()} Spot-TWAP Lag: {'+' if lag_delta >= 0 else ''}${lag_delta:.4f}"
            max_counter_lag = clean_delta * 0.35
            dominant_lead = DOMINANT_LEAD_THRESHOLD.get(coin, 50.0)

            # Consult Next-Session Chart Predictor
            pred_res = self.predictor.predict_coin(coin, now_ts) if hasattr(self, "predictor") else {}
            pred_dir = pred_res.get("prediction", "NEUTRAL")
            pred_conf = pred_res.get("confidence", 50.0)
            is_early_window = (165 <= seconds_rem <= 270)

            # Signal evaluation for UP
            if delta >= clean_delta and prob_up >= 0.70:
                if lag_delta < -max_counter_lag:
                    signal = "ABSTAIN"
                    reason = f"Momentum Warning: Binance spot is leading DOWN (${lag_delta:+.2f}) against TWAP oracle. High reversal risk."
                elif mkt_up <= 0.60 and edge_up >= 0.08:
                    signal = "BUY_UP"
                    reason = (
                        f"[EARLY VALUE SCALP] Edge +{edge_up*100:.1f}% on {coin}: Mathematical UP prob is {prob_up*100:.1f}% "
                        f"vs Market {mkt_up*100:.1f}¢ (2:1+ payout). Projected delta: +${delta:.4f} ({lag_indicator}) with {seconds_rem}s left."
                    )
                elif 0.60 < mkt_up <= 0.80:
                    if delta >= dominant_lead and prob_up >= 0.80:
                        signal = "BUY_UP"
                        reason = (
                            f"[LATE YIELD HARVEST] Dominant Lead +${delta:.2f} on {coin} (Prob {prob_up*100:.1f}%) "
                            f"@ Market {mkt_up*100:.1f}¢ (+${(1.0 - mkt_up)*5.0/mkt_up:.2f} yield). Stop-Loss active at 50¢. {seconds_rem}s left."
                        )
                    else:
                        signal = "ABSTAIN"
                        reason = f"{coin} UP price is {mkt_up*100:.0f}¢ but delta (+${delta:.2f}) is below dominant lead (${dominant_lead:.2f}). Late harvest unsafe."
                elif mkt_up > 0.80:
                    signal = "ABSTAIN"
                    reason = f"{coin} UP price is {mkt_up*100:.0f}¢ (exceeds 80¢ ceiling). Risk/reward poor."
                else:
                    signal = "ABSTAIN"
                    reason = f"{coin} UP statistical edge insufficient ({edge_up*100:.1f}% edge vs 8% requirement)."

            elif is_early_window and pred_dir == "UP" and pred_conf >= 68.0 and delta >= min_delta and mkt_up <= 0.52:
                if lag_delta < -max_counter_lag:
                    signal = "ABSTAIN"
                    reason = f"Momentum Warning: Binance spot is leading DOWN (${lag_delta:+.2f}). Predictive scalp deferred."
                else:
                    signal = "BUY_UP"
                    reason = (
                        f"[EARLY PREDICTIVE SCALP] Chart Forecast UP ({pred_conf:.0f}% conf): {pred_res.get('catalyst')} "
                        f"@ Market {mkt_up*100:.0f}¢ (2:1+ payout). Delta: +${delta:.2f} with {seconds_rem}s left."
                    )

            # Signal evaluation for DOWN
            elif delta <= -clean_delta and prob_down >= 0.70:
                if lag_delta > max_counter_lag:
                    signal = "ABSTAIN"
                    reason = f"Momentum Warning: Binance spot is leading UP (${lag_delta:+.2f}) against TWAP oracle. High reversal risk."
                elif mkt_down <= 0.60 and edge_down >= 0.08:
                    signal = "BUY_DOWN"
                    reason = (
                        f"[EARLY VALUE SCALP] Edge +{edge_down*100:.1f}% on {coin}: Mathematical DOWN prob is {prob_down*100:.1f}% "
                        f"vs Market {mkt_down*100:.1f}¢ (2:1+ payout). Projected delta: -${abs(delta):.4f} ({lag_indicator}) with {seconds_rem}s left."
                    )
                elif 0.60 < mkt_down <= 0.80:
                    if delta <= -dominant_lead and prob_down >= 0.80:
                        signal = "BUY_DOWN"
                        reason = (
                            f"[LATE YIELD HARVEST] Dominant Lead -${abs(delta):.2f} on {coin} (Prob {prob_down*100:.1f}%) "
                            f"@ Market {mkt_down*100:.1f}¢ (+${(1.0 - mkt_down)*5.0/mkt_down:.2f} yield). Stop-Loss active at 50¢. {seconds_rem}s left."
                        )
                    else:
                        signal = "ABSTAIN"
                        reason = f"{coin} DOWN price is {mkt_down*100:.0f}¢ but delta (-${abs(delta):.2f}) is below dominant lead (${dominant_lead:.2f}). Late harvest unsafe."
                elif mkt_down > 0.80:
                    signal = "ABSTAIN"
                    reason = f"{coin} DOWN price is {mkt_down*100:.0f}¢ (exceeds 80¢ ceiling). Risk/reward poor."
                else:
                    signal = "ABSTAIN"
                    reason = f"{coin} DOWN statistical edge insufficient ({edge_down*100:.1f}% edge vs 8% requirement)."

            elif is_early_window and pred_dir == "DOWN" and pred_conf >= 68.0 and delta <= -min_delta and mkt_down <= 0.52:
                if lag_delta > max_counter_lag:
                    signal = "ABSTAIN"
                    reason = f"Momentum Warning: Binance spot is leading UP (${lag_delta:+.2f}). Predictive scalp deferred."
                else:
                    signal = "BUY_DOWN"
                    reason = (
                        f"[EARLY PREDICTIVE SCALP] Chart Forecast DOWN ({pred_conf:.0f}% conf): {pred_res.get('catalyst')} "
                        f"@ Market {mkt_down*100:.0f}¢ (2:1+ payout). Delta: -${abs(delta):.2f} with {seconds_rem}s left."
                    )

            else:
                signal = "ABSTAIN"
                reason = f"{coin} is fairly priced on Polymarket ({mkt_up*100:.0f}¢ Up / {mkt_down*100:.0f}¢ Down). Statistical edge insufficient."

        return Btc5mRound(
            round_id=round_id,
            slug=poly_data["slug"],
            title=poly_data["title"],
            strike_price=strike_px,
            current_btc_price=twap_px,
            price_delta=delta,
            start_time=round_ts,
            end_time=end_ts,
            seconds_remaining=seconds_rem,
            market_price_up=mkt_up,
            market_price_down=mkt_down,
            calculated_prob_up=prob_up,
            calculated_prob_down=prob_down,
            z_score=z_score,
            ict_fvg_status=pattern,
            signal=signal,
            signal_reason=reason,
            symbol=coin,
            spot_price=spot_px,
            twap_price=twap_px,
            oracle_lag_delta=lag_delta,
            projected_twap=projected_twap,
            clob_token_ids=poly_data.get("clob_token_ids"),
            oracle_source=str(oracle.get("source", "binance")),
            bid_up=float(poly_data.get("bid_up") or 0.0),
            bid_down=float(poly_data.get("bid_down") or 0.0),
            price_source=str(poly_data.get("price_source", "gamma")) if poly_data.get("found") else "estimate"
        )

    def get_upcoming_rounds(self, count: int = 3, now_ts: Optional[int] = None) -> List[Dict[str, Any]]:
        """Returns the next `count` 5-minute round schedules aligned with Polymarket UTC boundaries."""
        if now_ts is None:
            now_ts = int(time.time())
        current_round_ts = (now_ts // 300) * 300

        upcoming = []
        for i in range(1, count + 1):
            target_ts = current_round_ts + (i * 300)
            end_ts = target_ts + 300
            starts_in = max(0, target_ts - now_ts)

            start_str = time.strftime('%H:%M', time.gmtime(target_ts))
            end_str = time.strftime('%H:%M', time.gmtime(end_ts))

            # Strike projections from current spot price and direct Polymarket links
            strikes = {}
            coin_urls = {}
            coin_slugs = {}
            for coin in SUPPORTED_COINS:
                strikes[coin] = self.feed.get_price(coin)
                c_slug = f"{coin.lower()}-updown-5m-{target_ts}"
                coin_slugs[coin] = c_slug
                coin_urls[coin] = f"https://polymarket.com/event/{c_slug}"

            upcoming.append({
                "round_index": i,
                "round_id": f"updown-5m-{target_ts}",
                "start_time": target_ts,
                "end_time": end_ts,
                "starts_in_seconds": starts_in,
                "time_window": f"{start_str} - {end_str} UTC",
                "estimated_strikes": strikes,
                "coin_slugs": coin_slugs,
                "coin_urls": coin_urls,
                "status": f"IN {starts_in // 60}m {starts_in % 60}s"
            })
        return upcoming

    def get_polymarket_timeline(self, coin: str = "BTC", timeframe: str = "5m", now_ts: Optional[int] = None) -> Dict[str, Any]:
        """
        Fetches live Polymarket schedule matching the real exchange timeline:
        - Past resolved rounds (🟢 UP / 🔴 DOWN)
        - Current active round with live closing countdown & price to beat
        - Upcoming scheduled epochs
        Supports 5m (300s), 15m (900s), and 1h (3600s).
        """
        coin = coin.upper() if coin else "BTC"
        if coin not in SUPPORTED_COINS:
            coin = "BTC"
        if timeframe not in ["5m", "15m", "1h"]:
            timeframe = "5m"

        interval_map = {"5m": 300, "15m": 900, "1h": 3600}
        interval = interval_map[timeframe]

        if now_ts is None:
            now_ts = int(time.time())

        # Check cache (3s cache per coin+timeframe)
        cache_key = f"{coin}_{timeframe}"
        with self.lock:
            cached = self._timeline_cache.get(cache_key)
            if cached and (now_ts - cached[0]) < 3:
                return cached[1]

        cur_ts = (now_ts // interval) * interval
        end_ts = cur_ts + interval
        sec_rem = max(0, end_ts - now_ts)

        # Helper to format ET & UTC times
        def _fmt_times(start_sec, end_sec):
            et_s = time.strftime('%I:%M', time.gmtime(start_sec - 18000))
            et_e = time.strftime('%I:%M %p ET', time.gmtime(end_sec - 18000))
            utc_s = time.strftime('%H:%M', time.gmtime(start_sec))
            utc_e = time.strftime('%H:%M UTC', time.gmtime(end_sec))
            return f"{et_s}-{et_e}", f"{utc_s}-{utc_e}", et_e

        # 1. Past 4 Resolved Rounds
        past_rounds = []
        for i in [-4, -3, -2, -1]:
            ts = cur_ts + (i * interval)
            p_end = ts + interval
            slug = f"{coin.lower()}-updown-{timeframe}-{ts}"
            et_win, utc_win, label = _fmt_times(ts, p_end)

            outcome = "PENDING"
            px_up = 0.50
            ptb = None
            try:
                poly = self.fetch_polymarket_market(coin, ts, timeframe=timeframe)
                if poly.get("found"):
                    ptb = poly.get("price_to_beat")
                    outcome = poly.get("winning_outcome") or ("UP" if poly.get("price_up", 0.5) >= 0.5 else "DOWN")
                    px_up = poly.get("price_up", 0.5)
            except Exception:
                pass

            past_rounds.append({
                "slug": slug,
                "timestamp": ts,
                "label": label,
                "time_window_et": et_win,
                "time_window_utc": utc_win,
                "outcome": outcome or "DOWN",
                "price_to_beat": ptb,
                "polymarket_url": f"https://polymarket.com/event/{slug}"
            })

        # 2. Active Round
        cur_slug = f"{coin.lower()}-updown-{timeframe}-{cur_ts}"
        act_et_win, act_utc_win, act_label = _fmt_times(cur_ts, end_ts)
        active_poly = self.fetch_polymarket_market(coin, cur_ts, timeframe=timeframe)

        active_round = {
            "slug": cur_slug,
            "timestamp": cur_ts,
            "end_timestamp": end_ts,
            "label": act_label,
            "time_window_et": act_et_win,
            "time_window_utc": act_utc_win,
            "seconds_remaining": sec_rem,
            "closes_in": f"{sec_rem // 60:02d}:{sec_rem % 60:02d}",
            "price_to_beat": active_poly.get("price_to_beat"),
            "price_up": active_poly.get("price_up", 0.50),
            "price_down": active_poly.get("price_down", 0.50),
            "accepting_orders": active_poly.get("accepting_orders", True),
            "closed": active_poly.get("closed", False),
            "polymarket_url": f"https://polymarket.com/event/{cur_slug}"
        }

        # 3. Upcoming 4 Rounds
        upcoming_rounds = []
        for i in [1, 2, 3, 4]:
            u_ts = cur_ts + (i * interval)
            u_end = u_ts + interval
            u_slug = f"{coin.lower()}-updown-{timeframe}-{u_ts}"
            u_et_win, u_utc_win, u_label = _fmt_times(u_ts, u_end)
            starts_in = max(0, u_ts - now_ts)

            upcoming_rounds.append({
                "slug": u_slug,
                "timestamp": u_ts,
                "label": u_label,
                "time_window_et": u_et_win,
                "time_window_utc": u_utc_win,
                "starts_in_seconds": starts_in,
                "status": f"in {starts_in // 60}m {starts_in % 60}s" if starts_in < 3600 else f"in {starts_in // 3600}h {(starts_in % 3600)//60}m",
                "polymarket_url": f"https://polymarket.com/event/{u_slug}"
            })

        timeline_data = {
            "coin": coin,
            "timeframe": timeframe,
            "interval_seconds": interval,
            "past_rounds": past_rounds,
            "active_round": active_round,
            "upcoming_rounds": upcoming_rounds
        }

        with self.lock:
            self._timeline_cache[cache_key] = (now_ts, timeline_data)

        return timeline_data

    def analyze_all_coins(self, now_ts: Optional[int] = None) -> Dict[str, Any]:
        """Analyzes all 4 coins (BTC, ETH, SOL, XRP) and selects the best candidate."""
        if now_ts is None:
            now_ts = int(time.time())
        round_ts = self.get_current_round_ts()

        rounds: Dict[str, Btc5mRound] = {}
        candidate_signals: List[Btc5mRound] = []

        for coin in SUPPORTED_COINS:
            r = self.analyze_single_coin(coin, now_ts, round_ts)
            rounds[coin] = r
            if r.signal in ["BUY_UP", "BUY_DOWN"]:
                candidate_signals.append(r)

        # Select highest-conviction setup
        best_round = rounds.get("BTC")
        if candidate_signals:
            def _calc_edge(rd: Btc5mRound) -> float:
                if rd.signal == "BUY_UP":
                    return rd.calculated_prob_up - rd.market_price_up
                elif rd.signal == "BUY_DOWN":
                    return rd.calculated_prob_down - rd.market_price_down
                return 0.0

            candidate_signals.sort(key=_calc_edge, reverse=True)
            best_round = candidate_signals[0]

        upcoming_rounds = self.get_upcoming_rounds(count=3, now_ts=now_ts)
        predictions = self.predictor.predict_all_coins(now_ts=now_ts)

        return {
            "best_round": best_round,
            "coins": rounds,
            "upcoming_rounds": upcoming_rounds,
            "predictions": predictions
        }

    def analyze_current_round(self) -> Btc5mRound:
        """Backwards compatibility helper."""
        return self.analyze_all_coins()["best_round"]


# Alias for backward compatibility
BtcRoundAnalyzer = MultiCryptoRoundAnalyzer
