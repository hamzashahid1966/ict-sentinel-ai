"""
Crypto Sentinel AI - Domain Models & Data Structures
"""

import time
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any

@dataclass
class CryptoCandle:
    timestamp: int          # Unix millisecond or second
    open: float
    high: float
    low: float
    close: float
    volume: float

    @property
    def body_high(self) -> float:
        return max(self.open, self.close)

    @property
    def body_low(self) -> float:
        return min(self.open, self.close)

    @property
    def is_bullish(self) -> bool:
        return self.close >= self.open

@dataclass
class ScreenerCandidate:
    symbol: str
    name: str
    price: float
    change_24h: float
    volume_24h: float
    sector: str              # MAJOR, L1, DEFI, AI, MEME
    why_picked: str          # Clear plain-English explanation of why this coin was selected
    score: float             # Opportunity/momentum score (0-100)
    h1_trend: str            # BULLISH, BEARISH, NEUTRAL
    volatility_pct: float    # 24h high-low range %
    is_active_focus: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class AnalysisOpportunity:
    symbol: str
    engine: str              # "A_ICT_LIQUIDITY", "B_MOMENTUM_IMP", "C_LIQUIDATION_SWEEP"
    direction: str           # "LONG" or "SHORT"
    status: str              # "SETUP_DETECTED", "WAITING_CONFIRMATION", "OPPORTUNITY_CONFIRMED"
    confidence_score: float  # 0.0 to 1.0
    reason: str              # What the engine analyzed and why opportunity exists
    current_price: float
    stop_loss: float
    target_1: float          # 1.5R
    target_2: float          # 3.0R
    risk_r: float
    sweep_level: Optional[float] = None
    fvg_bounds: Optional[str] = None
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class CryptoPosition:
    position_id: str
    symbol: str
    engine: str
    direction: str           # "LONG" or "SHORT"
    entry_price: float
    quantity: float
    initial_stop: float
    current_stop: float
    target_1: float          # 1.5R
    target_2: float          # 3.0R
    current_price: Optional[float] = None
    t1_hit: bool = False
    defensive_active: bool = False
    unrealized_pnl: float = 0.0
    unrealized_r: float = 0.0
    entry_time: float = field(default_factory=time.time)
    status: str = "OPEN"     # "OPEN", "T1_HIT", "CLOSED"
    exit_price: Optional[float] = None
    exit_reason: Optional[str] = None
    exit_time: Optional[float] = None
    fees_paid: float = 0.0
    is_stagnant: bool = False
    stagnant_at: Optional[float] = None
    funding_paid: float = 0.0              # net funding paid (+) / received (-), REAL_DATA_PAPER
    last_funding_ts: Optional[float] = None  # latest funding settlement already booked (unix s)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class CryptoAccount:
    balance: float
    peak_balance: float
    realized_pnl: float
    daily_starting_equity: float
    daily_drawdown_pct: float
    is_locked: bool
    mode: str                # "SIMULATED_PAPER" or "BINANCE_TESTNET"
    strategy_profile: str = "MODERATE_GROWTH"
    auto_swap_enabled: bool = True
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    win_rate_pct: float = 0.0
    gross_pnl: float = 0.0
    total_fees: float = 0.0
    net_pnl: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class ActivityLog:
    timestamp: float
    action: str              # e.g., "SCAN", "ANALYSIS", "ORDER", "MANAGE", "RISK"
    coin: str
    detail: str
    level: str = "INFO"      # INFO, SUCCESS, WARNING, DANGER

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
