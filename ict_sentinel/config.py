"""
ICT Sentinel AI - Configuration & Constants
Codifies the 52-Lecture ICT 2024 Mentorship parameters.
"""

import os
import datetime
from zoneinfo import ZoneInfo

# Exchange Pinned Timezones (DST-Aware)
NY_TZ = ZoneInfo("America/New_York")
LON_TZ = ZoneInfo("Europe/London")

# Base Directory & Storage Path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("SENTINEL_DB_PATH", os.path.join(BASE_DIR, "sentinel.db"))

# Account Starting Parameters
INITIAL_CAPITAL = 500.0
MAX_DAILY_DRAWDOWN_PCT = 10.0  # Max $50 risk per day
MAX_SINGLE_TRADE_RISK_PCT = 5.0 # Max $25 risk per trade

# Portfolio Correlation & Exposure Safeguards
MAX_CONCURRENT_USD_EXPOSURE = 1  # Block stacking same-direction USD risk (e.g. Long Gold + Long GBPUSD)
SINGLE_CONTRACT_TARGET_R = 2.0   # CME Futures discrete single-contract full-target protocol (100% exit at 2.0R, BE at 1.0R)

# Institutional Quantitative Goals (Benchmark Criteria)
INSTITUTIONAL_GOALS = {
    'target_sharpe_ratio': 1.50,
    'target_profit_factor': 2.00,
    'target_win_rate_pct': 65.0,
    'max_daily_drawdown_dollars': 50.0,
    'monthly_return_target_pct': 25.0
}

# Asset Specifications
ASSET_SPECS = {
    'GOLD': {
        'symbol': 'GC=F',
        'display_name': 'Micro Gold Futures (MGC)',
        'point_value': 10.0,       # $10 per full point
        'tick_size': 0.10,          # 1 tick = 0.10 = $1.00
        'min_risk_pts': 2.0,        # Minimum stop: 2.0 pts ($20)
        'max_risk_pts': 5.0,        # Maximum stop: 5.0 pts ($50)
        'commission': 1.25,         # Round turn per micro
        'slippage_ticks': 1.0,
        'min_pre_range': 4.0,
        'is_futures': True,         # CME Futures: discrete contract indivisibility
        'usd_relation': 'INVERSE',  # Long Gold = Short USD
    },
    'SILVER': {
        'symbol': 'SI=F',
        'display_name': 'Micro Silver Futures (SIL)',
        'point_value': 1000.0,      # $1.00 move = $1000 per micro (1000 oz)
        'tick_size': 0.005,         # 1 tick = $5.00
        'min_risk_pts': 0.030,      # 3 cents ($30)
        'max_risk_pts': 0.075,      # 7.5 cents ($75)
        'commission': 1.25,
        'slippage_ticks': 1.0,
        'min_pre_range': 0.15,
        'is_futures': True,         # CME Futures
        'usd_relation': 'INVERSE',  # Long Silver = Short USD
    },
    'NASDAQ': {
        'symbol': 'NQ=F',
        'display_name': 'Micro Nasdaq-100 Futures (MNQ)',
        'point_value': 2.0,         # $2 per full point
        'tick_size': 0.25,          # 1 tick = $0.50
        'min_risk_pts': 6.0,        # 6 pts ($12)
        'max_risk_pts': 25.0,       # 25 pts ($50)
        'commission': 0.62,
        'slippage_ticks': 1.0,
        'min_pre_range': 25.0,
        'is_futures': True,         # CME Futures
        'usd_relation': 'NEUTRAL',  # Equity index beta
    },
    'GBPUSD': {
        'symbol': 'GBPUSD=X',
        'display_name': 'British Pound Forex (0.10 Mini Lot)',
        'point_value': 10000.0,     # $1.00 per pip
        'tick_size': 0.0001,        # 1 pip
        'min_risk_pts': 0.0006,     # 6 pips ($6)
        'max_risk_pts': 0.0030,     # 30 pips ($30)
        'commission': 0.60,
        'slippage_ticks': 0.5,
        'min_pre_range': 0.0015,
        'is_futures': False,        # Forex: divisible into fractional lots
        'usd_relation': 'INVERSE',  # Long GBP = Short USD
    },
    'EURUSD': {
        'symbol': 'EURUSD=X',
        'display_name': 'Euro Forex (0.10 Mini Lot)',
        'point_value': 10000.0,     # $1.00 per pip
        'tick_size': 0.0001,        # 1 pip
        'min_risk_pts': 0.0006,     # 6 pips ($6)
        'max_risk_pts': 0.0025,     # 25 pips ($25)
        'commission': 0.60,
        'slippage_ticks': 0.5,
        'min_pre_range': 0.0012,
        'is_futures': False,        # Forex: divisible into fractional lots
        'usd_relation': 'INVERSE',  # Long EUR = Short USD
    }
}

# Algorithmic Time Windows (All times Eastern Time / EST)
SESSION_WINDOWS = {
    'LONDON': {
        'ref_start': datetime.time(20, 0),
        'ref_end': datetime.time(2, 0),
        'exec_start': datetime.time(2, 0),
        'exec_end': datetime.time(4, 30),
        'exit_time': datetime.time(6, 0),
    },
    'LONDON_CORE': {
        'ref_start': datetime.time(20, 0),
        'ref_end': datetime.time(2, 0),
        'exec_start': datetime.time(4, 30),
        'exec_end': datetime.time(7, 0),
        'exit_time': datetime.time(7, 15),
    },
    'NEW_YORK_AM': {
        'ref_start': datetime.time(0, 0),
        'ref_end': datetime.time(8, 0),
        'exec_start': datetime.time(8, 0),
        'exec_end': datetime.time(10, 30),
        'exit_time': datetime.time(11, 45),
    },
    'ASIAN_MACRO': {
        'ref_start': datetime.time(15, 0),
        'ref_end': datetime.time(18, 0),
        'exec_start': datetime.time(18, 50),
        'exec_end': datetime.time(20, 15),
        'exit_time': datetime.time(22, 0),
    }
}

