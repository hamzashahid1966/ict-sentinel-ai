"""
Data Models for Polymarket Sentinel.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone


def is_market_expired(end_date_str: Optional[str]) -> bool:
    """Checks whether a market's resolution end_date has already passed in UTC."""
    if not end_date_str:
        return False
    try:
        s = str(end_date_str).strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt <= datetime.now(timezone.utc)
    except Exception:
        return False


def get_days_to_expiry(end_date_str: Optional[str]) -> Optional[int]:
    """Returns number of days remaining until market resolution date in UTC."""
    if not end_date_str:
        return None
    try:
        s = str(end_date_str).strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        diff = dt - datetime.now(timezone.utc)
        return max(0, diff.days)
    except Exception:
        return None


@dataclass
class Market:
    id: str  # Polymarket internal market ID or condition_id
    condition_id: str
    question: str
    slug: str
    category: str
    end_date: Optional[str]
    volume_24h: float
    clob_token_yes: str
    clob_token_no: str
    price_yes: float
    price_no: float
    status: str = "active"  # "active", "resolved", "closed"
    resolution_source: Optional[str] = None
    created_at: Optional[str] = None
    qualification_score: float = 70.0
    qualification_tier: str = "MONITOR"
    resolution_spec: str = ""


@dataclass
class MarketSnapshot:
    market_id: str
    price_yes: float
    price_no: float
    volume_24h: float
    timestamp: str


@dataclass
class Entity:
    id: Optional[int]
    name: str
    entity_type: str  # "company", "person", "government", "protocol", "topic"
    summary: str
    updated_at: str


@dataclass
class EntityFact:
    id: Optional[int]
    entity_id: int
    fact_key: str
    fact_value: str
    source: str
    updated_at: str


@dataclass
class Evidence:
    id: Optional[int]
    source_url: str
    source_name: str
    title: str
    published_at: str
    summary: str
    credibility_score: float  # 0.0 to 1.0
    content_hash: str


@dataclass
class Prediction:
    id: Optional[int]
    market_id: str
    forecast_probability: float  # e.g., 0.65 for 65% YES
    market_probability: float    # e.g., 0.42 for 42% YES
    edge: float                  # forecast - market
    confidence_score: float      # 0.0 to 1.0
    reasoning: str
    model_used: str
    created_at: str
    independent_probability: float = 0.5
    base_rate: float = 0.3
    counterarguments: str = ""
    uncertainty_range_low: float = 0.4
    uncertainty_range_high: float = 0.6
    recommend_abstain: bool = False


@dataclass
class PaperPosition:
    id: Optional[int]
    market_id: str
    outcome: str  # "YES" or "NO"
    shares: float
    avg_entry_price: float
    cost_basis: float
    current_price: float
    current_value: float
    unrealized_pnl: float
    status: str  # "OPEN", "CLOSED"
    created_at: str
    reason: str = ""
    strategy_type: str = "ASYMMETRIC_EDGE"  # "ASYMMETRIC_EDGE" or "HIGH_PROBABILITY_YIELD"
    take_profit_px: float = 0.0
    stop_loss_px: float = 0.0


@dataclass
class PaperTrade:
    id: Optional[int]
    market_id: str
    position_id: Optional[int]
    action: str  # "BUY", "SELL", "SETTLE"
    outcome: str  # "YES", "NO"
    shares: float
    price: float
    dollar_value: float
    realized_pnl: float
    timestamp: str
    reason: str = ""
    strategy_type: str = "ASYMMETRIC_EDGE"
    exit_trigger: str = ""  # "TAKE_PROFIT", "STOP_LOSS", "EXPIRATION", "MANUAL"


@dataclass
class GatewayLog:
    id: Optional[int]
    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: float
    success: bool
    error_message: Optional[str]
    created_at: str
