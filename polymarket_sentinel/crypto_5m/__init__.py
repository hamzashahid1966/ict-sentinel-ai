"""
Polymarket 5-Minute Multi-Crypto Scalper Module (BTC, ETH, SOL, XRP).
"""

from .models import Btc5mRound, Btc5mTrade, Crypto5mRound, Crypto5mTrade
from .price_feed import MultiCryptoPriceFeed, BtcPriceFeed, SUPPORTED_COINS
from .round_analyzer import MultiCryptoRoundAnalyzer, BtcRoundAnalyzer
from .paper_scalper import MultiCryptoPaperScalper, Btc5mPaperScalper
from .session_predictor import NextSessionPredictor

__all__ = [
    "Btc5mRound",
    "Btc5mTrade",
    "Crypto5mRound",
    "Crypto5mTrade",
    "MultiCryptoPriceFeed",
    "BtcPriceFeed",
    "SUPPORTED_COINS",
    "MultiCryptoRoundAnalyzer",
    "BtcRoundAnalyzer",
    "MultiCryptoPaperScalper",
    "Btc5mPaperScalper",
    "NextSessionPredictor"
]
