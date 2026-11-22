"""
Polymarket Sentinel Configuration Module v2.
Dual-Engine Strategy Configuration:
- Engine A: Asymmetric Edge Hunter (10¢ to 65¢)
- Engine B: High-Probability Yield Harvester (80¢ to 96¢)
- Dynamic Active Exits: Take-Profit & Stop-Loss Trailing Protections
"""

import os
from pathlib import Path

# Base Paths
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = os.environ.get("POLY_DB_PATH", str(BASE_DIR / "polymarket.db"))

# Polymarket APIs
GAMMA_API_URL = "https://gamma-api.polymarket.com"
CLOB_API_URL = "https://clob.polymarket.com"

# AI Gateway Settings
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3")

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_DEFAULT_MODEL = os.environ.get(
    "OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free"
)

# Market Discovery & Strategy Filters
MIN_24H_VOLUME_USD = 10000.0   # Active liquidity threshold: min $10,000 24h volume
MAX_DAYS_TO_EXPIRY = 90        # Short-to-medium term: within 90 days to market resolution
MAX_TRACKED_MARKETS = 25       # Core active watchlist size
DEFAULT_MARKET_LIMIT = 15      # Per discovery batch

# AI News Evidence Decision Gate
MIN_EVIDENCE_FOR_ENTRY = 1            # Must have at least 1 verified news article before entry
MIN_EVIDENCE_CREDIBILITY = 0.80       # Minimum 80% source credibility threshold
REQUIRE_NEWS_SENTIMENT_ALIGNMENT = True  # News sentiment must confirm the trade thesis

# General Bankroll Settings
INITIAL_PAPER_CAPITAL = 500.00    # $500.00 virtual USDC bankroll
MIN_EDGE_THRESHOLD = 0.05         # Min 5% probability discrepancy before trading
SLIPPAGE_ESTIMATE = 0.005         # 0.5 cent simulated spread crossing penalty
DEFAULT_STRATEGY_MODE = "ALL_STRATEGIES"  # "ALL_STRATEGIES", "ASYMMETRIC_ONLY", "HIGH_PROBABILITY_ONLY"

# ── ENGINE A: ASYMMETRIC EDGE HUNTER (10¢ - 65¢) ──────────────────────
ASYMMETRIC_MIN_PRICE = 0.05
ASYMMETRIC_MAX_PRICE = 0.65
ASYMMETRIC_MAX_POSITION_PCT = 0.05  # Max 5% bankroll ($25 max trade)
MAX_POSITION_PCT = ASYMMETRIC_MAX_POSITION_PCT  # Backwards compatibility
ASYMMETRIC_TAKE_PROFIT_PCT = 0.35   # Auto take-profit on +35% price appreciation
ASYMMETRIC_STOP_LOSS_PCT = 0.20     # Auto stop-loss if price drops 20% below entry

# ── ENGINE B: HIGH-PROBABILITY YIELD HARVESTER (80¢ - 96¢) ────────────
HIGH_PROB_MIN_PRICE = 0.80
HIGH_PROB_MAX_PRICE = 0.96
HIGH_PROB_MAX_POSITION_PCT = 0.15   # Max 15% bankroll ($75 max trade)
HIGH_PROB_TAKE_PROFIT_PCT = 0.08    # Auto take-profit on +8% gain (early cash-out)
HIGH_PROB_STOP_LOSS_PCT = 0.06      # Fast emergency stop-loss at -6% (salvages 94% capital!)

# Black-Swan Veto Keywords (Never bet high-probability on unpredictable fat-tail events)
HIGH_PROB_BLACK_SWAN_KEYWORDS = [
    "ceasefire", "war", "missile", "airstrike", "conflict", "israel", "iran",
    "hamas", "ukraine", "russia", "putin", "assassination", "tweet", "follower",
    "celebrity", "dating", "rumor"
]

# Research Frequency (in seconds)
MARKET_SYNC_INTERVAL_SEC = 300    # Poll market prices every 5 minutes
RESEARCH_CYCLE_INTERVAL_SEC = 900  # Deep research cycle every 15 minutes
