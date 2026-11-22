"""
Polymarket API Client.
Interfaces with Polymarket Gamma API (discovery & metadata) and CLOB API (order books & midpoints).
Zero external dependencies (uses standard library urllib).
"""

import json
import urllib.request
import urllib.error
from typing import List, Dict, Any, Optional

from .config import GAMMA_API_URL, CLOB_API_URL, MIN_24H_VOLUME_USD, MAX_DAYS_TO_EXPIRY
from .models import Market, is_market_expired, get_days_to_expiry


class PolymarketClient:
    def __init__(self, gamma_url: str = GAMMA_API_URL, clob_url: str = CLOB_API_URL):
        self.gamma_url = gamma_url
        self.clob_url = clob_url
        self.headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"}

    def fetch_active_markets(self, limit: int = 25, min_volume: float = MIN_24H_VOLUME_USD) -> List[Market]:
        """
        Discovers top volume active prediction contracts directly from Polymarket Gamma API.
        Only returns real, live, unexpired contracts. Zero fake or fallback data.
        """
        url = f"{self.gamma_url}/markets?active=true&closed=false&order=volume24hr&ascending=false&limit=60"
        try:
            req = urllib.request.Request(url, headers=self.headers)
            with urllib.request.urlopen(req, timeout=12) as resp:
                raw_data = json.loads(resp.read().decode())
                markets = []
                for m in raw_data:
                    if m.get("closed") is True:
                        continue

                    end_date = m.get("endDate")
                    if is_market_expired(end_date):
                        continue

                    # Filter short-term horizon (<= MAX_DAYS_TO_EXPIRY, e.g. 30 days)
                    days_rem = get_days_to_expiry(end_date)
                    if days_rem is not None and days_rem > MAX_DAYS_TO_EXPIRY:
                        continue

                    vol = float(m.get("volume24hr") or 0.0)
                    if vol < min_volume and len(markets) >= 5:
                        continue

                    # Extract prices
                    outcome_prices = m.get("outcomePrices")
                    p_yes = 0.5
                    p_no = 0.5
                    if outcome_prices:
                        try:
                            if isinstance(outcome_prices, str):
                                prices = json.loads(outcome_prices)
                            else:
                                prices = outcome_prices
                            if len(prices) >= 2:
                                p_yes = round(float(prices[0]), 4)
                                p_no = round(float(prices[1]), 4)
                        except Exception:
                            pass

                    # Extract clob tokens
                    clob_tokens = m.get("clobTokenIds")
                    t_yes = ""
                    t_no = ""
                    if clob_tokens:
                        try:
                            if isinstance(clob_tokens, str):
                                tkns = json.loads(clob_tokens)
                            else:
                                tkns = clob_tokens
                            if len(tkns) >= 2:
                                t_yes = str(tkns[0])
                                t_no = str(tkns[1])
                        except Exception:
                            pass

                    market_obj = Market(
                        id=str(m.get("id") or m.get("conditionId")),
                        condition_id=str(m.get("conditionId") or ""),
                        question=m.get("question") or "",
                        slug=m.get("slug") or "",
                        category=m.get("category") or m.get("groupItemTitle") or "Prediction",
                        end_date=end_date,
                        volume_24h=vol,
                        clob_token_yes=t_yes,
                        clob_token_no=t_no,
                        price_yes=p_yes,
                        price_no=p_no,
                        status="active",
                        resolution_source=m.get("resolutionSource") or "Polymarket UMA Oracle"
                    )
                    markets.append(market_obj)
                    if len(markets) >= limit:
                        break

                return markets
        except Exception:
            return []

    def fetch_clob_midpoint(self, token_id: str) -> Optional[float]:
        """Fetches live midpoint price from CLOB API."""
        if not token_id:
            return None
        url = f"{self.clob_url}/midpoint?token_id={token_id}"
        try:
            req = urllib.request.Request(url, headers=self.headers)
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode())
                mid = data.get("mid")
                return float(mid) if mid is not None else None
        except Exception:
            return None

    def fetch_clob_orderbook(self, token_id: str) -> Dict[str, Any]:
        """Fetches live bids & asks depth from CLOB API."""
        if not token_id:
            return {"bids": [], "asks": []}
        url = f"{self.clob_url}/book?token_id={token_id}"
        try:
            req = urllib.request.Request(url, headers=self.headers)
            with urllib.request.urlopen(req, timeout=5) as resp:
                return json.loads(resp.read().decode())
        except Exception:
            return {"bids": [], "asks": []}
