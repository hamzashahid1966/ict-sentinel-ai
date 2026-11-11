"""
ICT Sentinel AI - Configuration & Constants
Codifies the 52-Lecture ICT 2024 Mentorship parameters.
"""

import os
import datetime

# Base Directory & Storage Path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("SENTINEL_DB_PATH", os.path.join(BASE_DIR, "sentinel.db"))

# Account Starting Parameters
INITIAL_CAPITAL = 500.0
MAX_DAILY_DRAWDOWN_PCT = 10.0  # Max $50 risk per day
MAX_SINGLE_TRADE_RISK_PCT = 5.0 # Max $25 risk per trade

# Asset Specifications
ASSET_SPECS = {
    'GOLD': {
        'symbol': 'GC=F',
        'display_name': 'Micro Gold Futures (MGC)',
        'point_value': 10.0,       # $10 per full point
        'tick_size': 0.10,          # 1 tick = 0.10 = $1.00
        'min_risk_pts': 2.0,        # Minimum stop: 2.0 pts ($20)
        'max_risk_pts': 3.5,        # Maximum stop: 3.5 pts ($35)
        'commission': 1.25,         # Round turn per micro
        'slippage_ticks': 1.0,
        'min_pre_range': 4.0,
    },
    'SILVER': {
        'symbol': 'SI=F',
        'display_name': 'Micro Silver Futures (SIL)',
        'point_value': 1000.0,      # $1.00 move = $1000 per micro (1000 oz)
        'tick_size': 0.005,         # 1 tick = $5.00
        'min_risk_pts': 0.030,      # 3 cents ($30)
        'max_risk_pts': 0.040,      # 4 cents ($40)
        'commission': 1.25,
        'slippage_ticks': 1.0,
        'min_pre_range': 0.15,
    },
    'NASDAQ': {
        'symbol': 'NQ=F',
        'display_name': 'Micro Nasdaq-100 Futures (MNQ)',
        'point_value': 2.0,         # $2 per full point
        'tick_size': 0.25,          # 1 tick = $0.50
        'min_risk_pts': 6.0,        # 6 pts ($12)
        'max_risk_pts': 15.0,       # 15 pts ($30)
        'commission': 0.62,
        'slippage_ticks': 1.0,
        'min_pre_range': 25.0,
    },
    'GBPUSD': {
        'symbol': 'GBPUSD=X',
        'display_name': 'British Pound Forex (0.10 Mini Lot)',
        'point_value': 10000.0,     # $1.00 per pip
        'tick_size': 0.0001,        # 1 pip
        'min_risk_pts': 0.0008,     # 8 pips ($8)
        'max_risk_pts': 0.0025,     # 25 pips ($25)
        'commission': 0.60,
        'slippage_ticks': 0.5,
        'min_pre_range': 0.0015,
    },
    'EURUSD': {
        'symbol': 'EURUSD=X',
        'display_name': 'Euro Forex (0.10 Mini Lot)',
        'point_value': 10000.0,     # $1.00 per pip
        'tick_size': 0.0001,        # 1 pip
        'min_risk_pts': 0.0006,     # 6 pips ($6)
        'max_risk_pts': 0.0020,     # 20 pips ($20)
        'commission': 0.60,
        'slippage_ticks': 0.5,
        'min_pre_range': 0.0012,
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

