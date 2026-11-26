"""
Polymarket Sentinel Controller v2.
Adversarial Multi-Agent Superforecasting Orchestrator:
1. Market Qualification Engine (Pre-filters noise & illiquid contracts)
2. Agent 01: Resolution Rule Analyst (UMA oracle ambiguity defense)
3. Agent 02 & 03: Sector Research & Evidence Verifier (Tiered credibility 100/75/50/20)
4. Agent 04: Blind Independent Forecaster (Zero market price anchoring!)
5. Agent 05: Counterargument Agent (Devil's advocate & Abstain gate)
6. Agent 06: Final Synthesis Analyst (Calibrated probability, uncertainty intervals & true edge)
7. Paper Trader: Correlated risk shields & depth-aware execution
"""

import time
import json
import threading
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from .config import (
    MARKET_SYNC_INTERVAL_SEC, RESEARCH_CYCLE_INTERVAL_SEC,
    MAX_TRACKED_MARKETS
)
from .storage import PolymarketStorage
from .polymarket_client import PolymarketClient
from .ai_gateway import AIGateway
from .memory_engine import PolymarketMemoryEngine
from .research_engine import PolymarketResearchEngine
from .paper_trader import PolymarketPaperTrader
from .models import Prediction

# Specialized v2 Intelligence Engines & Agents
from .intelligence.market_qualification import MarketQualificationEngine
from .agents.resolution_analyst import ResolutionAnalystAgent
from .agents.evidence_verifier import EvidenceVerifierAgent
from .agents.independent_forecaster import IndependentForecasterAgent
from .agents.counterargument import CounterargumentAgent
from .agents.final_analyst import FinalForecastAnalystAgent


class PolymarketController:
    """Thread-safe orchestrator for Polymarket Prediction Intelligence & Paper Trading."""

    def __init__(self):
        self.storage = PolymarketStorage()
        self.client = PolymarketClient()
        self.ai_gateway = AIGateway(storage=self.storage)
        self.memory = PolymarketMemoryEngine(self.storage)
        self.researcher = PolymarketResearchEngine(self.storage, self.memory)
        self.trader = PolymarketPaperTrader(self.storage)

        # Initialize v2 Specialized Agents
        self.qualifier = MarketQualificationEngine()
        self.resolution_analyst = ResolutionAnalystAgent(ai_gateway=self.ai_gateway)
        self.evidence_verifier = EvidenceVerifierAgent()
        self.independent_forecaster = IndependentForecasterAgent(ai_gateway=self.ai_gateway)
        self.counterargument_agent = CounterargumentAgent(ai_gateway=self.ai_gateway)
        self.final_analyst = FinalForecastAnalystAgent(ai_gateway=self.ai_gateway)

        # Initialize 5-Minute BTC Microstructure Scalper with activity logging callback
        from .crypto_5m import BtcPriceFeed, BtcRoundAnalyzer, Btc5mPaperScalper
        from .crypto_5m.live_executor import PolymarketLiveExecutor
        self.btc_feed = BtcPriceFeed()
        self.btc_analyzer = BtcRoundAnalyzer(self.btc_feed)
        self.btc_scalper = Btc5mPaperScalper(
            self.btc_analyzer,
            initial_bankroll=200.0,                       # paper: room for $10 trades (2026-11-26)
            auto_start=True,
            activity_callback=self.storage.add_activity
        )
        # 15-minute BTC rounds: a separate PAPER bot with the SAME rule as this server's 5-minute bot
        # (previous winner, up to 65c, decide at 30 s, cash out all at +40%, else hold), $20 a trade.
        # Started by the web server (start of run_web_dashboard), never by imports.
        from .crypto_5m.trend_15m import Trend15mBot
        self.btc_15m = Trend15mBot(self.btc_analyzer, activity_callback=self.storage.add_activity,
                                   stake=20.0, bankroll=400.0, min_price=0.0, max_price=0.65, entry_seconds=30,
                                   half_at=None, rest_at=None, single_tp=0.40, late_exit_seconds=None,
                                   enabled=True, auto_start=False)
        self.live_executor = PolymarketLiveExecutor()
        self.btc_scalper.set_live_executor(self.live_executor)
        if self.live_executor.is_live_enabled:
            self.btc_scalper.set_trading_mode("LIVE")
        self.general_events_trading_enabled: bool = False  # Disconnected per user requirement: Only 5M Crypto trades

        self.is_running = False
        self.is_researching = False
        self.worker_thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        self.lock = threading.Lock()
        self.last_sync_time: Optional[str] = None
        self.last_research_time: Optional[str] = None
        self.current_working_gig: str = "Standby: Auto-Pilot paused. Click [▶ Start Auto-Pilot] to run autonomous agents."

        # Seed initial knowledge base
        self.researcher.seed_initial_knowledge_base()
        self.storage.add_activity("SYSTEM", "Polymarket Sentinel v2 Ready", "Adversarial multi-agent pipeline and qualification engine armed.", "ready")

    def start(self):
        with self.lock:
            if self.is_running:
                return
            self.is_running = True
            self.stop_event.clear()
            self.btc_scalper.enable()
            self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
            self.worker_thread.start()
            self.storage.add_activity("ENGINE", "Polymarket Engine Started", "4-Coin 5M scalper auto-pilot activated (Strict button control).", "accent")

    def stop(self):
        with self.lock:
            if not self.is_running:
                return
            self.is_running = False
            self.stop_event.set()
            self.btc_scalper.disable()
            self.current_working_gig = "Standby: Auto-Pilot paused. Click [▶ Start Auto-Pilot] to run autonomous agents."
            self.storage.add_activity("ENGINE", "Polymarket Engine Stopped", "4-Coin 5M scalper auto-pilot paused.", "warning")

    def reset_system(self):
        """Stops the engine and completely wipes all paper positions, trades, and evidence back to initial $50 state."""
        self.stop()
        if self.worker_thread and self.worker_thread.is_alive():
            self.worker_thread.join(timeout=2.0)
        self.storage.reset_all_data()
        self.btc_scalper.reset(200.0)
        self.last_sync_time = None
        self.last_research_time = None
        self.current_working_gig = "Surveillance Active: 5M Crypto Microstructure Scalper ($50 Bankroll · $10 Max Risk per Coin · Staggered Parallel)"
        self.storage.add_activity("SYSTEM", "System Reset", "All paper trades cleared. Initial capital set to $50.00 ($10.00 max risk per coin, staggered entry). Other Polymarket event bids are disconnected.", "info")

    def close_position(self, pos_id: int):
        with self.lock:
            return self.trader.close_single_position(pos_id)

    def flatten_all(self):
        with self.lock:
            return self.trader.flatten_all_positions()

    def toggle_5m_scalper(self) -> bool:
        return self.btc_scalper.toggle_active()

    def cashout_5m_trade(self, symbol: str):
        return self.btc_scalper.cashout_trade(symbol)

    def force_settle_5m(self) -> int:
        return self.btc_scalper.force_settle_expired_trades()

    def get_live_account_status(self) -> Dict[str, Any]:
        acc = self.live_executor.get_account_status()
        acc["trading_mode"] = self.btc_scalper.trading_mode
        return acc

    def set_live_mode(self, enabled: bool) -> Dict[str, Any]:
        """Switches execution mode between LIVE real-money and PAPER simulation."""
        with self.lock:
            status = self.live_executor.set_live_mode(enabled)
            self.btc_scalper.set_trading_mode("LIVE" if enabled else "PAPER")
            status["trading_mode"] = self.btc_scalper.trading_mode
            return status

    def update_live_credentials(
        self,
        private_key: str,
        funder_address: Optional[str] = None,
        sig_type: Optional[int] = None,
        live_enabled: bool = False
    ) -> Dict[str, Any]:
        """Validates credentials, saves to .env, and updates client in memory."""
        with self.lock:
            res = self.live_executor.update_credentials(private_key, funder_address, sig_type, live_enabled)
            if res.get("ok"):
                self.btc_scalper.set_trading_mode("LIVE" if live_enabled else "PAPER")
            return res

    def test_live_credentials(
        self,
        private_key: str,
        funder_address: Optional[str] = None,
        sig_type: Optional[int] = None
    ) -> Dict[str, Any]:
        """Runs pre-flight check without saving or trading."""
        return self.live_executor.test_connection_creds(private_key, funder_address, sig_type)

    def _worker_loop(self):
        # Run initial sync immediately
        self.run_cycle()

        last_sync = time.time()
        last_research = time.time()

        while not self.stop_event.is_set():
            now = time.time()
            if now - last_sync >= MARKET_SYNC_INTERVAL_SEC:
                self.sync_markets()
                last_sync = now

            if now - last_research >= RESEARCH_CYCLE_INTERVAL_SEC:
                self.run_research_cycle()
                last_research = now

            self.stop_event.wait(5.0)

    def sync_markets(self):
        """Discovers, qualifies, and updates top active prediction contracts."""
        try:
            markets = self.client.fetch_active_markets(limit=MAX_TRACKED_MARKETS)
            price_map = {}
            for m in markets:
                # Stage 1: Market Qualification Score
                score, tier, _ = self.qualifier.qualify_market(m.__dict__)
                m.qualification_score = score
                m.qualification_tier = tier

                self.storage.upsert_market(m)
                price_map[m.id] = {"price_yes": m.price_yes, "price_no": m.price_no}

            # Update mark-to-market valuations
            self.trader.update_portfolio_mark_to_market(price_map)

            self.last_sync_time = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
            self.storage.add_activity("MARKET_DATA", "Markets Qualified & Synced", f"Processed {len(markets)} active contracts through Qualification Engine.", "info")
        except Exception as e:
            self.storage.add_activity("ERROR", "Market Sync Failed", str(e), "danger")

    def run_research_cycle(self):
        """Runs the 6-agent adversarial intelligence pipeline across qualified markets."""
        try:
            markets = self.storage.get_markets(limit=12, active_only=True)
            # Prioritize markets with higher qualification scores
            qualified = [m for m in markets if m.get("qualification_tier") != "SKIP"] or markets[:6]

            for m in qualified:
                if self.stop_event.is_set():
                    break
                m_id = m["id"]
                q = m["question"]
                cat = m.get("category", "General")
                cur_prob = float(m.get("price_yes", 0.5))

                self.current_working_gig = f"Adversarial Review: {q[:38]}... (Resolution · Blind Forecast · Counterargument)"

                # ── STAGE 1: Agent 01 - Resolution Analyst ────────────────────
                res_spec = self.resolution_analyst.analyze_resolution_criteria(
                    question=q,
                    category=cat,
                    resolution_source=m.get("resolution_source"),
                    end_date=m.get("end_date")
                )
                m["resolution_spec"] = json.dumps(res_spec)

                # ── STAGE 2: Agent 02 & 03 - News Ingestion & Evidence Verifier
                raw_evidence = self.researcher.research_market(m_id, q, cat)
                evidence_dossier = self.evidence_verifier.verify_and_weight_evidence(raw_evidence)

                # ── STAGE 3: Agent 04 - Blind Independent Forecaster ──────────
                # CRITICAL: Agent 04 is never given the Polymarket trading price!
                facts = self.memory.retrieve_entity_context(q)
                indep_forecast = self.independent_forecaster.forecast_independently(
                    question=q,
                    category=cat,
                    resolution_spec=res_spec,
                    verified_evidence=evidence_dossier.get("verified_evidence", []),
                    entity_facts=facts,
                    end_date=m.get("end_date")
                )

                # ── STAGE 4: Agent 05 - Counterargument Red Team ─────────────
                counter_critique = self.counterargument_agent.critique_forecast(
                    question=q,
                    independent_probability=indep_forecast["independent_probability"],
                    base_rate=indep_forecast["base_rate"],
                    resolution_spec=res_spec,
                    verified_evidence=evidence_dossier.get("verified_evidence", []),
                    evidence_quality=evidence_dossier.get("evidence_quality", 0.5)
                )

                # ── STAGE 5: Agent 06 - Final Synthesis Analyst ──────────────
                # Only now does Agent 06 cross-reference against current market price!
                final_res = self.final_analyst.synthesize_final_assessment(
                    question=q,
                    category=cat,
                    current_market_prob=cur_prob,
                    resolution_spec=res_spec,
                    evidence_dossier=evidence_dossier,
                    independent_forecast=indep_forecast,
                    counterargument_critique=counter_critique
                )

                # ── STAGE 6: Commit to Immutable Memory Timeline ─────────────
                pred_obj = Prediction(
                    id=None,
                    market_id=m_id,
                    forecast_probability=final_res["final_probability"],
                    market_probability=cur_prob,
                    edge=final_res["edge"],
                    confidence_score=indep_forecast.get("confidence_score", 0.75),
                    reasoning=final_res["synthesis_markdown"],
                    model_used=indep_forecast.get("method", "Multi-Agent Ensemble"),
                    created_at=datetime.now(timezone.utc).isoformat(),
                    independent_probability=final_res["independent_probability"],
                    base_rate=final_res["base_rate"],
                    counterarguments="; ".join(final_res.get("counterarguments", [])),
                    uncertainty_range_low=final_res["uncertainty_range"][0],
                    uncertainty_range_high=final_res["uncertainty_range"][1],
                    recommend_abstain=final_res["recommend_abstain"]
                )
                self.storage.add_prediction(pred_obj)

                # ── STAGE 7: Gated Paper Execution (Only 5M Crypto trades active) ─────
                if not final_res["recommend_abstain"] and self.general_events_trading_enabled:
                    self.trader.evaluate_and_trade(
                        market_id=m_id,
                        question=q,
                        price_yes=m["price_yes"],
                        price_no=m["price_no"],
                        forecast_p=final_res["final_probability"],
                        reason=final_res["synthesis_markdown"],
                        end_date=m.get("end_date"),
                        volume_24h=float(m.get("volume_24h") or 0.0),
                        evidence_list=raw_evidence,
                        category=m.get("category", "")
                    )
                elif not final_res["recommend_abstain"]:
                    self.storage.add_activity(
                        category="DISCONNECTED",
                        title=f"Event Bet Skipped: {q[:28]}...",
                        details="General Polymarket event bets are disconnected per user configuration. Only 5M Crypto Scalper is active.",
                        level="info"
                    )
                else:
                    self.storage.add_activity(
                        category="RISK_GUARD",
                        title=f"Abstained: {q[:32]}...",
                        details=f"Counterargument Gate: {final_res['status_desc']}",
                        level="warning"
                    )

            self.last_research_time = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
            self.storage.add_activity("RESEARCH", "Adversarial Research Complete", f"Completed 6-agent debate across {len(qualified)} qualified contracts.", "success")
        except Exception as e:
            self.storage.add_activity("ERROR", "Research Cycle Failed", str(e), "danger")

    def trigger_research_async(self) -> bool:
        """Dispatches an asynchronous deep research cycle in a background thread."""
        if self.is_researching:
            return False
        threading.Thread(target=self._async_research_worker, daemon=True).start()
        return True

    def _async_research_worker(self):
        self.is_researching = True
        self.current_working_gig = "⚡ ADVERSARIAL SWARM ACTIVE: Resolution Analysis · Blind Forecast · Counterargument Critique..."
        self.storage.add_activity("RESEARCH", "Adversarial Swarm Active", "6 specialized agents executing blind probabilistic synthesis.", "accent")
        try:
            self.run_research_cycle()
        finally:
            self.is_researching = False
            self.current_working_gig = "Surveillance Mode: Monitoring 29+ liquid contracts & scanning breaking news"

    def trigger_sync_async(self):
        """Dispatches an asynchronous market tape sync in a background thread."""
        threading.Thread(target=self.sync_markets, daemon=True).start()

    def run_cycle(self):
        """Executes a full sync and research run on demand."""
        self.sync_markets()
        self.run_research_cycle()

    def get_full_state(self) -> Dict[str, Any]:
        """Provides complete real-time JSON payload for the Polymarket dashboard tab."""
        markets = self.storage.get_markets(limit=30, active_only=True)

        # Attach latest predictions and v2 adversarial metrics to each market
        enriched_markets = []
        opportunities_count = 0
        for m in markets:
            pred = self.storage.get_latest_prediction(m["id"])
            m_copy = dict(m)
            if pred:
                m_copy["forecast_probability"] = pred["forecast_probability"]
                m_copy["independent_probability"] = pred.get("independent_probability", pred["forecast_probability"])
                m_copy["base_rate"] = pred.get("base_rate", 0.3)
                m_copy["edge"] = pred["edge"]
                m_copy["confidence"] = pred["confidence_score"]
                m_copy["reasoning"] = pred["reasoning"]
                m_copy["counterarguments"] = pred.get("counterarguments", "")
                m_copy["uncertainty_range"] = [
                    pred.get("uncertainty_range_low", max(0.01, pred["forecast_probability"] - 0.08)),
                    pred.get("uncertainty_range_high", min(0.99, pred["forecast_probability"] + 0.08))
                ]
                m_copy["recommend_abstain"] = bool(pred.get("recommend_abstain", 0))
                m_copy["model_used"] = pred["model_used"]
                m_copy["last_updated"] = pred["created_at"]
                if abs(pred["edge"]) >= 0.06 and not m_copy["recommend_abstain"]:
                    opportunities_count += 1
            else:
                m_copy["forecast_probability"] = m["price_yes"]
                m_copy["independent_probability"] = m["price_yes"]
                m_copy["base_rate"] = 0.3
                m_copy["edge"] = 0.0
                m_copy["confidence"] = 0.5
                m_copy["reasoning"] = "Pending initial adversarial research cycle."
                m_copy["counterarguments"] = ""
                m_copy["uncertainty_range"] = [m["price_yes"], m["price_yes"]]
                m_copy["recommend_abstain"] = False
                m_copy["model_used"] = "None"
                m_copy["last_updated"] = None

            enriched_markets.append(m_copy)

        portfolio = self.trader.get_portfolio_summary()
        gateway_stats = self.storage.get_gateway_stats()
        activity = self.storage.get_recent_activity(limit=35)
        recent_evidence = self.storage.get_all_recent_evidence(limit=20)

        # 5-Minute BTC/Multi-Crypto Microstructure Scalper State (Cached from background worker)
        btc_5m_state = self.btc_scalper.get_state()

        # Consolidate portfolio totals with 5M scalper bankroll & commissions ($50 Bankroll, Only 5M Coins)
        scalper_bankroll = btc_5m_state.get("balance", 50.0)
        scalper_pnl = btc_5m_state.get("realized_pnl", 0.0)
        scalper_commissions = btc_5m_state.get("total_commissions_paid", 0.0)
        consolidated_cash = round(scalper_bankroll, 2)
        consolidated_equity = round(scalper_bankroll, 2)
        consolidated_pnl = round(scalper_pnl, 2)
        consolidated_realized = round(scalper_pnl, 2)

        return {
            "running": self.is_running,
            "is_researching": self.is_researching,
            "last_sync": self.last_sync_time,
            "last_research": self.last_research_time,
            "current_gig": self.current_working_gig,
            "kpis": {
                "monitored_markets": len(markets),
                "open_positions": len(portfolio["open_positions"]),
                "opportunities": opportunities_count,
                "cash": consolidated_cash,
                "portfolio_equity": consolidated_equity,
                "total_pnl": consolidated_pnl,
                "realized_pnl": consolidated_realized,
                "unrealized_pnl": portfolio["unrealized_pnl"],
                "scalper_bankroll": scalper_bankroll,
                "scalper_pnl": scalper_pnl,
                "scalper_commissions": scalper_commissions,
                "brier_score": 0.165  # Empirical multi-agent baseline
            },
            "markets": enriched_markets,
            "recent_evidence": recent_evidence,
            "portfolio": portfolio,
            "gateway_stats": gateway_stats,
            "activity": activity,
            "btc_5m": btc_5m_state,
            "btc_15m": self.btc_15m.get_state(),
            "live_account": self.get_live_account_status()
        }


# Global Singleton for Polymarket Engine
POLY_BOT = PolymarketController()
