"""
Test package bootstrap: point the KnowledgeEngine at a throwaway copy of the
mentorship knowledge base so test trades never append to the real
ict_mentorship_knowledge/04_adaptive_learning_log.json ledger.
"""

import json
import os
import shutil
import tempfile

_REAL_KNOWLEDGE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ict_mentorship_knowledge")

if "ICT_KNOWLEDGE_DIR" not in os.environ and os.path.isdir(_REAL_KNOWLEDGE_DIR):
    _tmp = tempfile.mkdtemp(prefix="ict_knowledge_test_")
    for _name in os.listdir(_REAL_KNOWLEDGE_DIR):
        if _name.endswith(".json") and not _name.startswith("04_"):
            shutil.copy(os.path.join(_REAL_KNOWLEDGE_DIR, _name), _tmp)
    with open(os.path.join(_tmp, "04_adaptive_learning_log.json"), "w", encoding="utf-8") as _f:
        json.dump({"system": "ICT Sentinel test ledger", "version": "1.0", "episodes": [], "current_regime_weights": {}}, _f)
    os.environ["ICT_KNOWLEDGE_DIR"] = _tmp

# Crypto Sentinel reads CRYPTO_EXECUTION_MODE / CRYPTO_DB_PATH from .env at import time.
# Pin both so the suite never inherits the live mode (e.g. REAL_DATA_PAPER) and never opens
# a live account database: tests run in testnet mode against a throwaway file.
os.environ["CRYPTO_EXECUTION_MODE"] = "BINANCE_TESTNET"
os.environ["CRYPTO_DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="crypto_test_db_"), "crypto_test.db")
