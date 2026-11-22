"""
Data models for Polymarket 5-Minute Crypto Microstructure Scalper (BTC, ETH, SOL, XRP).
Tracks spot price, Chainlink 60s TWAP oracle price, oracle lag, projected price, and commissions.
"""

from dataclasses import dataclass
from typing import Optional, Any, List, Dict


@dataclass
class Btc5mRound:
    round_id: str                   # e.g. "btc-updown-5m-1795219500"
    slug: str
    title: str
    strike_price: float             # P0 (locked at open)
    current_btc_price: float        # P(t) - current coin price
    price_delta: float              # P(t) - P0
    start_time: int                 # Unix epoch
    end_time: int                   # Unix epoch
    seconds_remaining: int
    market_price_up: float          # Polymarket CLOB price (e.g. 0.35)
    market_price_down: float        # Polymarket CLOB price (e.g. 0.65)
    calculated_prob_up: float       # Mathematical Z-score probability
    calculated_prob_down: float
    z_score: float
    ict_fvg_status: str             # "BULLISH_DISPLACEMENT", "BEARISH_DISPLACEMENT", "NEUTRAL_SWEEP"
    signal: str                     # "BUY_UP", "BUY_DOWN", "ABSTAIN"
    signal_reason: str
    symbol: str = "BTC"             # "BTC", "ETH", "SOL", "XRP"
    spot_price: float = 0.0         # Live instantaneous Binance spot
    twap_price: float = 0.0         # Simulated Chainlink 60s TWAP
    oracle_lag_delta: float = 0.0   # Spot - TWAP (positive = spot is leading oracle upward)
    projected_twap: float = 0.0     # Expected TWAP over the next 60s
    resolved_outcome: Optional[str] = None  # "UP", "DOWN"
    clob_token_ids: Optional[Any] = None    # [token_id_up, token_id_down]
    oracle_source: str = "binance"          # "chainlink" (resolution series) or "binance" (exchange fallback)
    bid_up: float = 0.0                     # live CLOB best bid for UP (what a seller receives)
    bid_down: float = 0.0                   # live CLOB best bid for DOWN
    price_source: str = "gamma"             # "clob" = market_price_* are live best asks; "gamma" = stale outcomePrices; "estimate" = synthetic


@dataclass
class Btc5mTrade:
    id: Optional[int]
    round_id: str
    action: str                     # "BUY", "SETTLE"
    outcome: str                    # "UP", "DOWN"
    shares: float
    entry_price: float
    cost: float
    pnl: float
    timestamp: str
    reason: str
    symbol: str = "BTC"             # "BTC", "ETH", "SOL", "XRP"
    spot_price_at_entry: float = 0.0
    twap_price_at_entry: float = 0.0
    oracle_lag_at_entry: float = 0.0
    projected_twap: float = 0.0
    commission: float = 0.0         # Simulated Polymarket taker fee (0.2%)
    settlement_price: float = 0.0
    status: str = "OPEN"            # "OPEN", "WON", "LOST"
    order_id: Optional[str] = None   # Polymarket CLOB live order ID
    mode: str = "PAPER"              # "PAPER" or "LIVE"


# Type Aliases for multi-asset clarity
Crypto5mRound = Btc5mRound
Crypto5mTrade = Btc5mTrade
