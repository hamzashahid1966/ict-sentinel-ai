"""
ICT Sentinel AI - Models & Domain Entities
"""

import datetime
from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class Candle:
    timestamp: datetime.datetime
    timestamp_et: datetime.datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    @property
    def body_top(self) -> float:
        return max(self.open, self.close)

    @property
    def body_bottom(self) -> float:
        return min(self.open, self.close)

    @property
    def is_bullish(self) -> bool:
        return self.close > self.open

    @property
    def is_bearish(self) -> bool:
        return self.close < self.open

@dataclass
class PDArray:
    array_type: str  # 'SIBI', 'BISI', 'IFVG', 'VOLUME_IMBALANCE'
    high: float
    low: float
    consequent_encroachment: float
    formation_time: datetime.datetime
    mitigated: bool = False
    reclaimed: bool = False

@dataclass
class Position:
    position_id: str
    asset: str
    direction: str          # 'LONG' or 'SHORT'
    quantity: int
    entry_price: float
    entry_time: datetime.datetime
    initial_stop_loss: float
    active_trailing_stop: float
    target_center_mass: float # 1.5R (50% scale-out)
    target_head_shot: float   # 3.0R (runner terminus)
    center_mass_filled: bool = False
    head_shot_filled: bool = False
    realized_pnl: float = 0.0
    status: str = 'OPEN'      # 'OPEN', 'PARTIAL', 'CLOSED'
    defensive_shields: List[str] = field(default_factory=list)

@dataclass
class TradeRecord:
    trade_id: str
    asset: str
    session: str
    direction: str
    entry_time: str
    entry_price: float
    exit_time: str
    exit_price: float
    risk_pts: float
    pnl_pts: float
    dollar_pnl: float
    outcome: str            # 'FULL_WIN', 'DEFENSIVE_STOP', 'LOSS', 'TIME_EXIT'
    ai_reasoning: str

@dataclass
class AccountState:
    balance: float
    peak_balance: float
    realized_pnl: float
    unrealized_pnl: float
    max_drawdown_dollars: float
    max_drawdown_pct: float
    open_positions_count: int

@dataclass
class AILogEntry:
    timestamp: str
    asset: str
    session: str
    category: str           # 'IPDA_ANALYSIS', 'ORDER_EXECUTION', 'DEFENSIVE_SHIELD', 'RISK_GATE'
    message: str
    reasoning: str

