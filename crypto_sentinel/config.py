"""
Crypto Sentinel AI - Configuration & Parameters
Adapted from the Crypto Sentinel Technical Blueprint & Core Gold/Forex models.
"""

import os
import ssl

def _create_ssl_context():
    try:
        ctx = ssl._create_unverified_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    except Exception:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx

SSL_CONTEXT = _create_ssl_context()

# Force direct connection for Binance APIs, bypassing any IDE/sandbox proxy (127.0.0.1:60060)
import urllib.request
DIRECT_OPENER = urllib.request.build_opener(
    urllib.request.ProxyHandler({}),
    urllib.request.HTTPSHandler(context=SSL_CONTEXT)
)
urllib.request.install_opener(DIRECT_OPENER)

def direct_urlopen(url_or_req, timeout: float = 5.0):
    """
    Direct network request that bypasses any local HTTP_PROXY / HTTPS_PROXY
    and uses the unverified SSL context for reliable Binance Testnet connectivity.
    """
    return DIRECT_OPENER.open(url_or_req, timeout=timeout)

# Strip local sandbox proxy from environment for Python subprocesses
for proxy_var in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"):
    if proxy_var in os.environ and "127.0.0.1" in os.environ[proxy_var]:
        del os.environ[proxy_var]
os.environ["NO_PROXY"] = "*"
os.environ["no_proxy"] = "*"

# Automatically load .env if present
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(ROOT_DIR, ".env")
if os.path.exists(ENV_PATH):
    try:
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip().strip("'\"")
                    if k not in os.environ:
                        os.environ[k] = v
    except Exception:
        pass

# Base Directory & Database
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CRYPTO_DB_PATH = os.environ.get("CRYPTO_DB_PATH", os.path.join(BASE_DIR, "crypto_sentinel.db"))

# Binance Futures Endpoints
BINANCE_PUBLIC_REST = "https://fapi.binance.com"
BINANCE_TESTNET_REST = "https://testnet.binancefuture.com"
BINANCE_TESTNET_API_KEY = os.environ.get("BINANCE_TESTNET_API_KEY", "")
BINANCE_TESTNET_API_SECRET = os.environ.get("BINANCE_TESTNET_API_SECRET", "")

# Execution Modes: "SIMULATED_PAPER" or "BINANCE_TESTNET"
DEFAULT_EXECUTION_MODE = os.environ.get("CRYPTO_EXECUTION_MODE", "BINANCE_TESTNET" if BINANCE_TESTNET_API_KEY else "SIMULATED_PAPER")

# Account & Risk Parameters
INITIAL_CAPITAL = 1000.0          # Starting paper equity ($)
DEFAULT_RISK_PER_TRADE_PCT = 0.25 # 0.25% of account equity per trade (as per spec)
MEME_RISK_PER_TRADE_PCT = 0.10    # Reduced risk collar for high-volatility meme coins
MAX_DAILY_DRAWDOWN_PCT = 1.0      # 1% maximum daily drawdown lock
MAX_COMBINED_OPEN_RISK_PCT = 0.75 # Max combined open risk across all 3 positions
MAX_CONCURRENT_POSITIONS = 3      # Maximum 3 concurrent open positions
DEFAULT_LEVERAGE = 1              # 1x leverage initially for spot/perp paper testing

# Fees & Execution Assumptions
MAKER_FEE_PCT = 0.02              # 0.02% maker fee
TAKER_FEE_PCT = 0.05              # 0.05% taker fee
DEFAULT_SLIPPAGE_PCT = 0.02       # 0.02% base slippage for majors

# Double Tap Order Management System (OMS)
TARGET_1_R = 0.40                 # First target: 0.40R (closes 50% for ~$2.50 net after fees)
TARGET_2_R = 0.80                 # Second target: 0.80R (closes remaining 50% for ~$5.00 net after fees)
DEFENSIVE_STOP_ATR_BUFFER = 0.1   # Offset buffer when moving stop to defensive after Target 1

# Stagnation & Opportunity Swap Protocol (Option A: Fee-Guaranteed Breakeven)
STAGNATION_TIMEOUT_SECONDS = 45 * 60       # 45 minutes stagnation timeout
TRUE_FEE_BUFFER_PCT = 0.0011               # 0.11% price move required to guarantee 100% round-trip fee coverage
OPPORTUNITY_SWAP_MIN_SCORE = 88.0          # Minimum conviction score required to trigger an opportunity swap
AUTO_SWAP_ENABLED = True                   # Enable auto-swap of stagnant fee-paid trades for A+ setups

# Market Directional Shield & Risk Collar
BTC_REGIME_FILTER_ENABLED = True           # Shield: Altcoins must align with BTC M5 direction
FAST_SCALPER_MAX_DOLLAR_RISK = 4.00        # $4.00 maximum stop-loss dollar risk on Fast Scalper
TRADE_ENTRY_PACING_SECONDS = 180           # 3 minutes cooldown between opening new trades
MIN_CONVICTION_SCORE = 0.82                # 82% minimum conviction score for trade entry
MIN_TARGET_MOVE_PCT = 0.0035               # 0.35% minimum price distance to Target 1 (filters out fee-eating micro wicks)

# Dynamic Strategy & Risk Profiles
STRATEGY_PROFILES = {
    "FAST_SCALPER": {
        "id": "FAST_SCALPER",
        "name": "Fast Scalper Mode",
        "badge": "ACTIVE · SWEET-SPOT (0.4R / 0.8R)",
        "risk_per_trade_pct": 0.35,
        "max_dollar_risk": 4.00,
        "meme_risk_pct": 0.20,
        "max_daily_drawdown_pct": 3.0,
        "target_1_r": 0.40,
        "target_2_r": 0.80,
        "speed": "Rapid Scalp (15–30 mins)",
        "tp1_desc": "0.40R (~+$2.50 Net Banked)",
        "tp2_desc": "0.80R (~+$5.00 Net Full Exit)",
        "description": "Sweet-Spot Scalper with 0.35% minimum target spread & $4 max SL cap. Target 1 at 0.40R banks ~+$2.50 net after fees in 15–20 mins and moves stop to Breakeven. Target 2 at 0.80R completes the trade with ~+$5.00 net."
    },
    "OPTIMAL_GROWTH": {
        "id": "OPTIMAL_GROWTH",
        "name": "Optimal Growth",
        "badge": "RECOMMENDED (1.0R / 2.0R)",
        "risk_per_trade_pct": 1.00,
        "meme_risk_pct": 0.50,
        "max_daily_drawdown_pct": 3.0,
        "target_1_r": 1.0,
        "target_2_r": 2.0,
        "speed": "Balanced Swing (1–2h)",
        "tp1_desc": "1.0R (50% Partial Exit)",
        "tp2_desc": "2.0R (Remaining 50%)",
        "description": "Optimal risk-to-reward. 1.00% risk with easily achievable 1.0R / 2.0R targets. Banks 50% profit fast and moves stop to breakeven."
    },
    "ULTRA_SAFE": {
        "id": "ULTRA_SAFE",
        "name": "Ultra-Safe Prop Firm",
        "badge": "CONSERVATIVE (1.0R / 2.0R)",
        "risk_per_trade_pct": 0.25,
        "meme_risk_pct": 0.10,
        "max_daily_drawdown_pct": 1.0,
        "target_1_r": 1.0,
        "target_2_r": 2.0,
        "speed": "Conservative Swing (1–3h)",
        "tp1_desc": "1.0R (50% Partial Exit)",
        "tp2_desc": "2.0R (Remaining 50%)",
        "description": "Prop-firm standard. 0.25% risk per trade (Meme 0.10%), 1% daily max loss lock. Preserves capital with micro-exposure (~$10–$20 profit)."
    },
    "AGGRESSIVE_GROWTH": {
        "id": "AGGRESSIVE_GROWTH",
        "name": "Aggressive Growth",
        "badge": "HIGH YIELD (1.0R / 2.0R)",
        "risk_per_trade_pct": 2.00,
        "meme_risk_pct": 1.00,
        "max_daily_drawdown_pct": 5.0,
        "target_1_r": 1.0,
        "target_2_r": 2.0,
        "speed": "High-Yield Momentum (1–2h)",
        "tp1_desc": "1.0R (50% Partial Exit)",
        "tp2_desc": "2.0R (Remaining 50%)",
        "description": "Accelerated compounder. 2.00% equity risk per trade with 1.0R / 2.0R targets. Maximizes profit velocity on high-conviction momentum (~$38–$76 profit)."
    },
    "MODERATE_GROWTH": {
        "id": "MODERATE_GROWTH",
        "name": "Moderate Growth (Legacy)",
        "badge": "BALANCED",
        "risk_per_trade_pct": 1.00,
        "meme_risk_pct": 0.50,
        "max_daily_drawdown_pct": 3.0,
        "target_1_r": 1.0,
        "target_2_r": 2.0,
        "speed": "Balanced Swing (1–2h)",
        "tp1_desc": "1.0R (50% Partial Exit)",
        "tp2_desc": "2.0R (Remaining 50%)",
        "description": "Balanced retail growth. 1.00% risk with 1.0R / 2.0R targets."
    }
}
DEFAULT_STRATEGY_PROFILE = "FAST_SCALPER"

# Universe Configuration - Curated Top 12 Prime Institutional Universe
TOP_PRIME_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "DOGEUSDT", "LINKUSDT",
    "XRPUSDT", "AVAXUSDT", "SUIUSDT", "INJUSDT", "NEARUSDT", "TIAUSDT"
]

# AI Behavioral Learning & Auto-Quarantine Circuit Breaker
AUTO_QUARANTINE_CONSECUTIVE_LOSSES = 2       # Quarantined after 2 consecutive losses
AUTO_QUARANTINE_MAX_NET_LOSS = -5.00          # Quarantined if net PnL is worse than -$5.00 on >=2 trades
AUTO_QUARANTINE_DURATION_HOURS = 24           # 24 hours quarantine timeout

# Universe Configuration - Top 50 USDT Perpetuals & Classification
TOP_50_UNIVERSE = [
    # Majors / Bluechips
    {"symbol": "BTCUSDT", "name": "Bitcoin", "sector": "MAJOR", "tick_size": 0.10, "min_qty": 0.001},
    {"symbol": "ETHUSDT", "name": "Ethereum", "sector": "MAJOR", "tick_size": 0.01, "min_qty": 0.01},
    {"symbol": "SOLUSDT", "name": "Solana", "sector": "L1", "tick_size": 0.01, "min_qty": 0.1},
    {"symbol": "BNBUSDT", "name": "BNB", "sector": "EXCHANGE", "tick_size": 0.01, "min_qty": 0.01},
    {"symbol": "XRPUSDT", "name": "XRP", "sector": "PAYMENTS", "tick_size": 0.0001, "min_qty": 1.0},
    {"symbol": "ADAUSDT", "name": "Cardano", "sector": "L1", "tick_size": 0.0001, "min_qty": 1.0},
    {"symbol": "AVAXUSDT", "name": "Avalanche", "sector": "L1", "tick_size": 0.01, "min_qty": 0.1},
    {"symbol": "LINKUSDT", "name": "Chainlink", "sector": "ORACLE", "tick_size": 0.001, "min_qty": 0.1},
    {"symbol": "SUIUSDT", "name": "Sui", "sector": "L1", "tick_size": 0.0001, "min_qty": 1.0},
    {"symbol": "NEARUSDT", "name": "NEAR Protocol", "sector": "L1", "tick_size": 0.001, "min_qty": 0.1},
    {"symbol": "APTUSDT", "name": "Aptos", "sector": "L1", "tick_size": 0.001, "min_qty": 0.1},
    {"symbol": "DOTUSDT", "name": "Polkadot", "sector": "L1", "tick_size": 0.001, "min_qty": 0.1},
    {"symbol": "MATICUSDT", "name": "Polygon", "sector": "L2", "tick_size": 0.0001, "min_qty": 1.0},
    {"symbol": "ARBUSDT", "name": "Arbitrum", "sector": "L2", "tick_size": 0.0001, "min_qty": 1.0},
    {"symbol": "OPUSDT", "name": "Optimism", "sector": "L2", "tick_size": 0.0001, "min_qty": 1.0},
    {"symbol": "INJUSDT", "name": "Injective", "sector": "DEFI", "tick_size": 0.001, "min_qty": 0.1},
    {"symbol": "RENDERUSDT", "name": "Render", "sector": "AI", "tick_size": 0.001, "min_qty": 0.1},
    {"symbol": "FETUSDT", "name": "Artificial Superintelligence", "sector": "AI", "tick_size": 0.0001, "min_qty": 1.0},
    {"symbol": "TAOUSDT", "name": "Bittensor", "sector": "AI", "tick_size": 0.01, "min_qty": 0.01},
    {"symbol": "AAVEUSDT", "name": "Aave", "sector": "DEFI", "tick_size": 0.01, "min_qty": 0.01},
    {"symbol": "UNIUSDT", "name": "Uniswap", "sector": "DEFI", "tick_size": 0.001, "min_qty": 0.1},
    {"symbol": "LDOUSDT", "name": "Lido DAO", "sector": "DEFI", "tick_size": 0.0001, "min_qty": 1.0},
    {"symbol": "TIAUSDT", "name": "Celestia", "sector": "MODULAR", "tick_size": 0.0001, "min_qty": 1.0},
    {"symbol": "SEIUSDT", "name": "Sei", "sector": "L1", "tick_size": 0.0001, "min_qty": 1.0},
    {"symbol": "FTMUSDT", "name": "Fantom", "sector": "L1", "tick_size": 0.0001, "min_qty": 1.0},
    {"symbol": "KASUSDT", "name": "Kaspa", "sector": "POW", "tick_size": 0.0001, "min_qty": 1.0},
    {"symbol": "STXUSDT", "name": "Stacks", "sector": "L2", "tick_size": 0.0001, "min_qty": 1.0},
    {"symbol": "RUNEUSDT", "name": "THORChain", "sector": "DEFI", "tick_size": 0.001, "min_qty": 0.1},
    {"symbol": "GALAUSDT", "name": "Gala", "sector": "GAMING", "tick_size": 0.00001, "min_qty": 10.0},
    {"symbol": "IMXUSDT", "name": "Immutable", "sector": "GAMING", "tick_size": 0.0001, "min_qty": 1.0},

    # Meme Coins (Subject to Meme Risk Collar)
    {"symbol": "DOGEUSDT", "name": "Dogecoin", "sector": "MEME", "tick_size": 0.00001, "min_qty": 1.0},
    {"symbol": "SHIBUSDT", "name": "Shiba Inu", "sector": "MEME", "tick_size": 0.000001, "min_qty": 1000.0},
    {"symbol": "PEPEUSDT", "name": "Pepe", "sector": "MEME", "tick_size": 0.0000001, "min_qty": 10000.0},
    {"symbol": "WIFUSDT", "name": "dogwifhat", "sector": "MEME", "tick_size": 0.0001, "min_qty": 1.0},
    {"symbol": "BONKUSDT", "name": "Bonk", "sector": "MEME", "tick_size": 0.000001, "min_qty": 1000.0},
    {"symbol": "FLOKIUSDT", "name": "Floki", "sector": "MEME", "tick_size": 0.000001, "min_qty": 100.0},
    {"symbol": "BOMEUSDT", "name": "Book of MEME", "sector": "MEME", "tick_size": 0.00001, "min_qty": 10.0},
    {"symbol": "POPCATUSDT", "name": "Popcat", "sector": "MEME", "tick_size": 0.0001, "min_qty": 1.0},
    {"symbol": "MEWUSDT", "name": "cat in a dogs world", "sector": "MEME", "tick_size": 0.00001, "min_qty": 10.0},
    {"symbol": "NEIROUSDT", "name": "First Neiro On Ethereum", "sector": "MEME", "tick_size": 0.00001, "min_qty": 10.0},

    # High Beta / Additional Momentum Assets
    {"symbol": "TONUSDT", "name": "Toncoin", "sector": "L1", "tick_size": 0.0001, "min_qty": 0.1},
    {"symbol": "LTCUSDT", "name": "Litecoin", "sector": "PAYMENTS", "tick_size": 0.01, "min_qty": 0.01},
    {"symbol": "ETCUSDT", "name": "Ethereum Classic", "sector": "POW", "tick_size": 0.001, "min_qty": 0.1},
    {"symbol": "BCHUSDT", "name": "Bitcoin Cash", "sector": "PAYMENTS", "tick_size": 0.01, "min_qty": 0.01},
    {"symbol": "FILUSDT", "name": "Filecoin", "sector": "STORAGE", "tick_size": 0.001, "min_qty": 0.1},
    {"symbol": "ICPUSDT", "name": "Internet Computer", "sector": "L1", "tick_size": 0.001, "min_qty": 0.01},
    {"symbol": "ATOMUSDT", "name": "Cosmos", "sector": "L1", "tick_size": 0.001, "min_qty": 0.1},
    {"symbol": "XLMUSDT", "name": "Stellar", "sector": "PAYMENTS", "tick_size": 0.00001, "min_qty": 1.0},
    {"symbol": "HBARUSDT", "name": "Hedera", "sector": "L1", "tick_size": 0.00001, "min_qty": 1.0},
    {"symbol": "ALGOUSDT", "name": "Algorand", "sector": "L1", "tick_size": 0.0001, "min_qty": 1.0}
]

# Screener Configuration
SCREENER_MAX_CANDIDATES = 5       # Focus on top 5 active coins at any moment
MIN_24H_VOLUME_USD = 20_000_000   # Minimum $20M 24h volume for liquidity safety
