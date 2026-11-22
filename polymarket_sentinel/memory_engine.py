"""
Polymarket Sentinel Memory Engine.
Centralized, persistent intelligence memory:
- Event Memory: Timeline of forecasts and probability evolution
- Entity Memory: Knowledge graph of organizations, individuals, and facts
- Evidence Memory: Deduplicated citations and credibility ratings
- Calibration & Mistake Memory: Post-mortem evaluation and Brier score tracking
"""

import hashlib
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

from .storage import PolymarketStorage
from .models import Prediction, Evidence, Entity


class PolymarketMemoryEngine:
    def __init__(self, storage: PolymarketStorage):
        self.storage = storage

    # ── Evidence Deduplication & Memory ──────────────────────────────
    @staticmethod
    def compute_content_hash(title: str, summary: str, url: str) -> str:
        payload = f"{title.strip().lower()}|{summary.strip().lower()}|{url.strip().lower()}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def record_evidence(
        self,
        market_id: str,
        source_url: str,
        source_name: str,
        title: str,
        summary: str,
        credibility_score: float = 0.8,
        sentiment_impact: float = 0.0
    ) -> int:
        c_hash = self.compute_content_hash(title, summary, source_url)
        now_iso = datetime.now(timezone.utc).isoformat()
        ev = Evidence(
            id=None,
            source_url=source_url,
            source_name=source_name,
            title=title,
            published_at=now_iso,
            summary=summary,
            credibility_score=credibility_score,
            content_hash=c_hash
        )
        ev_id = self.storage.add_evidence(ev)
        if ev_id > 0:
            self.storage.link_market_evidence(market_id, ev_id, relevance=1.0, sentiment=sentiment_impact)
        return ev_id

    # ── Entity Knowledge Management ──────────────────────────────────
    def learn_entity_fact(
        self,
        entity_name: str,
        entity_type: str,
        summary: str,
        fact_key: str,
        fact_value: str,
        source: str
    ):
        """Stores permanent facts about entities (e.g. Fed policy precedents, CEO statements)."""
        ent_id = self.storage.upsert_entity(entity_name, entity_type, summary)
        self.storage.add_entity_fact(ent_id, fact_key, fact_value, source)

    def retrieve_entity_context(self, text_keywords: str) -> List[Dict[str, Any]]:
        """Finds entity facts relevant to the search query."""
        words = text_keywords.split()
        facts = []
        for w in words:
            if len(w) >= 3:
                res = self.storage.get_entity_facts(w)
                for r in res:
                    if r not in facts:
                        facts.append(r)
        return facts[:8]

    # ── Forecast Timeline & Revision Memory ───────────────────────────
    def commit_forecast(
        self,
        market_id: str,
        forecast_probability: float,
        market_probability: float,
        confidence_score: float,
        reasoning: str,
        model_used: str
    ):
        """Records a new immutable prediction point in the market timeline."""
        edge = round(forecast_probability - market_probability, 4)
        pred = Prediction(
            id=None,
            market_id=market_id,
            forecast_probability=forecast_probability,
            market_probability=market_probability,
            edge=edge,
            confidence_score=confidence_score,
            reasoning=reasoning,
            model_used=model_used,
            created_at=datetime.now(timezone.utc).isoformat()
        )
        self.storage.add_prediction(pred)

    def get_market_timeline(self, market_id: str) -> Dict[str, Any]:
        """Returns the full historical timeline of predictions and linked evidence."""
        predictions = self.storage.get_market_prediction_timeline(market_id)
        evidence = self.storage.get_market_evidence(market_id)
        return {
            "market_id": market_id,
            "predictions_count": len(predictions),
            "timeline": predictions,
            "evidence": evidence
        }

    # ── Calibration & Brier Score Evaluation ─────────────────────────
    @staticmethod
    def calculate_brier_score(forecasts: List[float], actual_outcome: int) -> float:
        """
        Calculates Brier Score: (forecast - actual)^2.
        Lower is better (0.0 = perfect accuracy).
        """
        if not forecasts:
            return 0.25  # Uninformative baseline
        sq_errs = [(p - actual_outcome) ** 2 for p in forecasts]
        return round(sum(sq_errs) / len(sq_errs), 4)
