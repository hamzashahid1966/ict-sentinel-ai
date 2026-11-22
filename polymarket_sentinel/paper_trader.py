"""
Polymarket Sentinel Paper Trading Engine.
Simulates order execution, Dual-Engine strategy allocation, dynamic active exits (Take-Profit & Stop-Loss),
P&L mark-to-market, and edge-based trade signals.
Zero real crypto/Polygon funds involved.
"""

from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

from .config import (
    INITIAL_PAPER_CAPITAL,
    MIN_EDGE_THRESHOLD, SLIPPAGE_ESTIMATE,
    MAX_DAYS_TO_EXPIRY, MIN_24H_VOLUME_USD,
    MIN_EVIDENCE_FOR_ENTRY, MIN_EVIDENCE_CREDIBILITY,
    REQUIRE_NEWS_SENTIMENT_ALIGNMENT,
    ASYMMETRIC_MIN_PRICE, ASYMMETRIC_MAX_PRICE,
    ASYMMETRIC_MAX_POSITION_PCT, ASYMMETRIC_TAKE_PROFIT_PCT, ASYMMETRIC_STOP_LOSS_PCT,
    HIGH_PROB_MIN_PRICE, HIGH_PROB_MAX_PRICE,
    HIGH_PROB_MAX_POSITION_PCT, HIGH_PROB_TAKE_PROFIT_PCT, HIGH_PROB_STOP_LOSS_PCT,
    HIGH_PROB_BLACK_SWAN_KEYWORDS, DEFAULT_STRATEGY_MODE
)
from .storage import PolymarketStorage
from .models import PaperPosition, PaperTrade, is_market_expired, get_days_to_expiry


class PolymarketPaperTrader:
    def __init__(self, storage: PolymarketStorage):
        self.storage = storage

    def evaluate_and_trade(
        self,
        market_id: str,
        question: str,
        price_yes: float,
        price_no: float,
        forecast_p: float,
        reason: str = "",
        end_date: Optional[str] = None,
        volume_24h: float = 0.0,
        evidence_list: Optional[List[Dict[str, Any]]] = None,
        category: str = ""
    ) -> Optional[Dict[str, Any]]:
        """
        Evaluates discrepancy between AI Forecast Probability and Market Price.
        Enforces 4 strict gates:
        1. Expiration Gate: Rejects closed or expired markets.
        2. Horizon Gate: Capped at short-term contracts (<= MAX_DAYS_TO_EXPIRY).
        3. Liquidity Gate: Requires liquid volume (>= MIN_24H_VOLUME_USD).
        4. Evidence Gate: Requires >= MIN_EVIDENCE_FOR_ENTRY verified news articles
           with sentiment confirming the trade thesis.

        Routes into:
        - Engine A (Asymmetric Edge Hunter): 5¢ - 65¢, 5% max position, 35% TP, 20% SL.
        - Engine B (High-Probability Yield Harvester): 80¢ - 96¢, 15% max position, 8% TP, 6% SL,
          with strict Black-Swan Veto on war/geopolitical/rumor bets.
        """
        # GATE 1: Strictly reject expired/resolved markets
        if is_market_expired(end_date):
            return None

        # GATE 2: Short-Term Horizon Check
        days_rem = get_days_to_expiry(end_date)
        if days_rem is not None and days_rem > MAX_DAYS_TO_EXPIRY:
            self.storage.add_activity(
                category="AI_GATE",
                title=f"Trade Filtered (Long-Term): {question[:28]}...",
                details=f"Resolution is in {days_rem} days (limit is {MAX_DAYS_TO_EXPIRY}d). Priority kept on short-term high-velocity contracts.",
                level="info"
            )
            return None

        # GATE 3: High Liquidity Check
        if volume_24h > 0 and volume_24h < MIN_24H_VOLUME_USD:
            self.storage.add_activity(
                category="AI_GATE",
                title=f"Trade Filtered (Low Volume): {question[:28]}...",
                details=f"24h volume is ${volume_24h:,.0f} (threshold: ${MIN_24H_VOLUME_USD:,.0f}). Passed to prevent illiquid slippage.",
                level="info"
            )
            return None

        # Edge on YES outcome: Forecast YES - Market Price YES
        edge_yes = forecast_p - price_yes
        # Edge on NO outcome: (1 - Forecast YES) - Market Price NO
        edge_no = (1.0 - forecast_p) - price_no

        if edge_yes < MIN_EDGE_THRESHOLD and edge_no < MIN_EDGE_THRESHOLD:
            return None

        # Determine target outcome & target price
        if edge_yes >= MIN_EDGE_THRESHOLD and (edge_yes >= edge_no or edge_no < MIN_EDGE_THRESHOLD):
            target_outcome = "YES"
            target_market_px = price_yes
            target_edge = edge_yes
            forecast_target = forecast_p
        else:
            target_outcome = "NO"
            target_market_px = price_no
            target_edge = edge_no
            forecast_target = 1.0 - forecast_p

        # GATE 4: Strong News Evidence Gate
        ev_list = evidence_list or []
        verified_ev = [e for e in ev_list if e.get("credibility_score", 0.0) >= MIN_EVIDENCE_CREDIBILITY]

        if len(verified_ev) < MIN_EVIDENCE_FOR_ENTRY:
            self.storage.add_activity(
                category="AI_GATE",
                title=f"Trade Blocked (No News Catalyst): {question[:28]}...",
                details=f"Calculated edge exists, but only {len(verified_ev)}/{MIN_EVIDENCE_FOR_ENTRY} verified news articles exist. Entry held.",
                level="warning"
            )
            return None

        net_news_sentiment = sum(e.get("sentiment_impact", 0.0) for e in verified_ev) / len(verified_ev)

        # Check existing open position for this market
        open_positions = self.storage.get_open_positions()
        existing = next((p for p in open_positions if p["market_id"] == market_id), None)
        if existing:
            return None  # Already holding a position

        acct = self.storage.get_account_state()
        cash = acct.get("balance", INITIAL_PAPER_CAPITAL)
        if cash < 5.0:
            return None  # Insufficient bankroll

        # ── DUAL-ENGINE STRATEGY CLASSIFICATION ──────────────────────────
        is_high_prob_candidate = (HIGH_PROB_MIN_PRICE <= target_market_px <= HIGH_PROB_MAX_PRICE)

        if is_high_prob_candidate:
            # Enforce Black-Swan Tail-Risk Veto
            full_text = f"{question} {category}".lower()
            matched_kw = next((kw for kw in HIGH_PROB_BLACK_SWAN_KEYWORDS if kw in full_text), None)
            if matched_kw:
                self.storage.add_activity(
                    category="BLACK_SWAN_VETO",
                    title=f"High-Prob Trade Vetoed: {question[:28]}...",
                    details=f"Priced at {target_market_px*100:.1f}¢, but contract triggered tail-risk veto keyword ('{matched_kw}'). High-probability yield harvesting is strictly forbidden on unpredictable geopolitical/war/rumor events to protect capital against sudden 100% loss.",
                    level="warning"
                )
                return None

            strategy_type = "HIGH_PROBABILITY_YIELD"
            alloc_pct = HIGH_PROB_MAX_POSITION_PCT  # Max 15% ($75 cap)
            max_alloc = min(cash * alloc_pct, 75.0, cash)
            tp_pct = HIGH_PROB_TAKE_PROFIT_PCT      # +8% quick gain
            sl_pct = HIGH_PROB_STOP_LOSS_PCT        # -6% defensive stop
        else:
            strategy_type = "ASYMMETRIC_EDGE"
            alloc_pct = ASYMMETRIC_MAX_POSITION_PCT  # Max 5% ($25 cap)
            max_alloc = min(cash * alloc_pct, 25.0, cash)
            tp_pct = ASYMMETRIC_TAKE_PROFIT_PCT      # +35% runner
            sl_pct = ASYMMETRIC_STOP_LOSS_PCT        # -20% stop
            if max_alloc < 2.0:
                return None

        # Check Strategy Mode filter
        if DEFAULT_STRATEGY_MODE == "ASYMMETRIC_ONLY" and strategy_type != "ASYMMETRIC_EDGE":
            return None
        if DEFAULT_STRATEGY_MODE == "HIGH_PROBABILITY_ONLY" and strategy_type != "HIGH_PROBABILITY_YIELD":
            return None

        # News Sentiment Direction Check
        if target_outcome == "YES" and REQUIRE_NEWS_SENTIMENT_ALIGNMENT and net_news_sentiment < -0.05:
            self.storage.add_activity(
                category="AI_GATE",
                title=f"Trade Vetoed by AI News Sentiment: {question[:28]}...",
                details=f"Math indicated BUY YES (+{target_edge*100:.1f}%), but news sentiment ({net_news_sentiment:+.2f}) is negative. Vetoed.",
                level="warning"
            )
            return None
        elif target_outcome == "NO" and REQUIRE_NEWS_SENTIMENT_ALIGNMENT and net_news_sentiment > 0.05:
            self.storage.add_activity(
                category="AI_GATE",
                title=f"Trade Vetoed by AI News Sentiment: {question[:28]}...",
                details=f"Math indicated BUY NO (+{target_edge*100:.1f}%), but news sentiment ({net_news_sentiment:+.2f}) is positive. Vetoed.",
                level="warning"
            )
            return None

        # Sizing and Execution
        execution_px = min(0.99, target_market_px + SLIPPAGE_ESTIMATE)
        shares = round(max_alloc / execution_px, 1)
        cost = round(shares * execution_px, 2)
        if cost < 1.0:
            return None

        # Active Dynamic Exit Targets
        take_profit_px = min(0.99, round(execution_px * (1.0 + tp_pct), 3))
        stop_loss_px = round(execution_px * (1.0 - sl_pct), 3)

        top_headlines = "; ".join([e.get("title", "")[:45] for e in verified_ev[:2]])

        if strategy_type == "HIGH_PROBABILITY_YIELD":
            plain_reason = (
                f"[💎 HIGH-PROBABILITY YIELD] Market priced {target_outcome} at {target_market_px*100:.1f}¢ "
                f"({forecast_target*100:.1f}% AI true prob). Confirmed by {len(verified_ev)} primary news sources ({top_headlines}). "
                f"Active Exits: Auto TP @ ${take_profit_px:.3f} (+{tp_pct*100:.0f}%), Fast Defensive SL @ ${stop_loss_px:.3f} (-{sl_pct*100:.0f}%)."
            )
        else:
            plain_reason = (
                f"[🎯 ASYMMETRIC EDGE] Market priced {target_outcome} at {target_market_px*100:.1f}¢ with calculated true prob "
                f"of {forecast_target*100:.1f}% (+{target_edge*100:.1f}% edge). Backed by {len(verified_ev)} verified news reports "
                f"({top_headlines}). Active Exits: Auto TP @ ${take_profit_px:.3f} (+{tp_pct*100:.0f}%), Defensive SL @ ${stop_loss_px:.3f} (-{sl_pct*100:.0f}%)."
            )

        if reason:
            plain_reason += f" Thesis: {reason[:120]}"

        pos = PaperPosition(
            id=None,
            market_id=market_id,
            outcome=target_outcome,
            shares=shares,
            avg_entry_price=execution_px,
            cost_basis=cost,
            current_price=target_market_px,
            current_value=round(shares * target_market_px, 2),
            unrealized_pnl=round(shares * target_market_px - cost, 2),
            status="OPEN",
            created_at=datetime.now(timezone.utc).isoformat(),
            reason=plain_reason,
            strategy_type=strategy_type,
            take_profit_px=take_profit_px,
            stop_loss_px=stop_loss_px
        )
        pos_id = self.storage.save_paper_position(pos)
        self.storage.update_account_balance(balance_delta=-cost)

        trade = PaperTrade(
            id=None,
            market_id=market_id,
            position_id=pos_id,
            action="BUY",
            outcome=target_outcome,
            shares=shares,
            price=execution_px,
            dollar_value=cost,
            realized_pnl=0.0,
            timestamp=datetime.now(timezone.utc).isoformat(),
            reason=plain_reason,
            strategy_type=strategy_type,
            exit_trigger="ENTRY"
        )
        self.storage.record_paper_trade(trade)

        strat_badge = "💎 HIGH-PROB YIELD" if strategy_type == "HIGH_PROBABILITY_YIELD" else "🎯 ASYMMETRIC EDGE"
        self.storage.add_activity(
            category="PAPER_ORDER",
            title=f"Paper Buy {target_outcome} [{strat_badge}]: {question[:26]}...",
            details=f"Entry: {shares} shares @ ${execution_px:.3f} (Outlay: ${cost:.2f}) | TP: ${take_profit_px:.3f} | SL: ${stop_loss_px:.3f}",
            level="accent"
        )
        return {
            "action": "BUY",
            "outcome": target_outcome,
            "shares": shares,
            "price": execution_px,
            "cost": cost,
            "reason": plain_reason,
            "strategy_type": strategy_type,
            "take_profit_px": take_profit_px,
            "stop_loss_px": stop_loss_px
        }

    def settle_expired_positions(self):
        """
        Scans all open positions. If a market has reached its end_date,
        it is closed/settled so it is automatically removed from active open bets.
        """
        open_positions = self.storage.get_open_positions()
        for p in open_positions:
            end_date = p.get("end_date")
            if is_market_expired(end_date):
                pos_id = p["id"]
                pnl = p.get("unrealized_pnl", 0.0)
                cur_val = p.get("current_value", 0.0)

                # Return residual value back to cash balance, book realized P&L
                self.storage.update_account_balance(balance_delta=cur_val, realized_delta=pnl)

                # Mark position as CLOSED
                with self.storage.lock:
                    conn = self.storage._get_connection()
                    conn.execute("UPDATE pm_paper_positions SET status = 'CLOSED' WHERE id = ?;", (pos_id,))
                    conn.commit()
                    conn.close()

                # Also mark market as closed in pm_markets
                with self.storage.lock:
                    conn = self.storage._get_connection()
                    conn.execute("UPDATE pm_markets SET status = 'closed' WHERE id = ?;", (p["market_id"],))
                    conn.commit()
                    conn.close()

                # Record settlement trade in ledger
                trade = PaperTrade(
                    id=None,
                    market_id=p["market_id"],
                    position_id=pos_id,
                    action="SETTLE",
                    outcome=p["outcome"],
                    shares=p["shares"],
                    price=p.get("current_price", 0.0),
                    dollar_value=cur_val,
                    realized_pnl=pnl,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    reason=f"Market resolution date reached ({end_date}). Position automatically settled and closed.",
                    strategy_type=p.get("strategy_type", "ASYMMETRIC_EDGE"),
                    exit_trigger="EXPIRATION"
                )
                self.storage.record_paper_trade(trade)
                self.storage.add_activity(
                    category="SETTLEMENT",
                    title=f"Position Settled: {p.get('question', p['market_id'])[:32]}...",
                    details=f"Market reached end date ({end_date}). Closed position with P&L: {'+' if pnl>=0 else ''}${pnl:.2f}",
                    level="info"
                )

    def update_portfolio_mark_to_market(self, live_market_prices: Dict[str, Dict[str, float]]):
        """
        Updates unrealized P&L for all open positions based on current market quotes.
        Monitors active dynamic exits:
        - Auto Take-Profit: Sells when current_price >= take_profit_px
        - Auto Stop-Loss: Sells when current_price <= stop_loss_px
        """
        self.settle_expired_positions()
        open_positions = self.storage.get_open_positions()
        for p in open_positions:
            m_id = p["market_id"]
            if m_id in live_market_prices:
                px_data = live_market_prices[m_id]
                cur_px = px_data.get("price_yes", 0.5) if p["outcome"] == "YES" else px_data.get("price_no", 0.5)
                cur_val = round(p["shares"] * cur_px, 2)
                pnl = round(cur_val - p["cost_basis"], 2)

                # Update row
                with self.storage.lock:
                    conn = self.storage._get_connection()
                    conn.execute("""
                    UPDATE pm_paper_positions
                    SET current_price = ?, current_value = ?, unrealized_pnl = ?
                    WHERE id = ?;
                    """, (cur_px, cur_val, pnl, p["id"]))
                    conn.commit()
                    conn.close()

                # ── ACTIVE DYNAMIC EXIT CHECK ──
                tp_px = p.get("take_profit_px", 0.0) or 0.0
                sl_px = p.get("stop_loss_px", 0.0) or 0.0

                # 1. Take-Profit Check
                if tp_px > 0.0 and cur_px >= tp_px:
                    gain_pct = round(((cur_px / p["avg_entry_price"]) - 1.0) * 100, 1)
                    self.close_single_position(
                        pos_id=p["id"],
                        reason=f"Dynamic Exit: Take-Profit Hit (+{gain_pct}%). Target: ${tp_px:.3f}, Current: ${cur_px:.3f}.",
                        exit_trigger="TAKE_PROFIT"
                    )
                    continue

                # 2. Emergency Stop-Loss Check
                if sl_px > 0.0 and cur_px <= sl_px:
                    loss_pct = round(((cur_px / p["avg_entry_price"]) - 1.0) * 100, 1)
                    self.close_single_position(
                        pos_id=p["id"],
                        reason=f"Emergency Dynamic Exit: Stop-Loss Hit ({loss_pct}%). Level: ${sl_px:.3f}, Current: ${cur_px:.3f}. Capital salvaged.",
                        exit_trigger="STOP_LOSS"
                    )
                    continue

    def get_portfolio_summary(self) -> Dict[str, Any]:
        self.settle_expired_positions()
        acct = self.storage.get_account_state()
        open_pos = self.storage.get_open_positions()
        trades = self.storage.get_recent_paper_trades(limit=50)

        unrealized_pnl = sum(p.get("unrealized_pnl", 0.0) for p in open_pos)
        invested = sum(p.get("cost_basis", 0.0) for p in open_pos)
        equity = acct.get("balance", INITIAL_PAPER_CAPITAL) + sum(p.get("current_value", 0.0) for p in open_pos)

        return {
            "cash": round(acct.get("balance", INITIAL_PAPER_CAPITAL), 2),
            "invested": round(invested, 2),
            "equity": round(equity, 2),
            "realized_pnl": round(acct.get("realized_pnl", 0.0), 2),
            "unrealized_pnl": round(unrealized_pnl, 2),
            "total_pnl": round(acct.get("realized_pnl", 0.0) + unrealized_pnl, 2),
            "open_positions": open_pos,
            "recent_trades": trades
        }

    def close_single_position(
        self,
        pos_id: int,
        reason: str = "Manual Sell / Early Liquidation from Dashboard.",
        exit_trigger: str = "MANUAL"
    ) -> Optional[Dict[str, Any]]:
        """Liquidates an open paper position at current market price."""
        open_pos = [p for p in self.storage.get_open_positions() if p["id"] == pos_id]
        if not open_pos:
            return None
        p = open_pos[0]
        cur_px = p.get("current_price", 0.5)
        proceeds = round(p["shares"] * cur_px, 2)
        realized_pnl = round(proceeds - p["cost_basis"], 2)

        with self.storage.lock:
            conn = self.storage._get_connection()
            try:
                conn.execute("UPDATE pm_paper_positions SET status = 'CLOSED' WHERE id = ?;", (pos_id,))
                conn.commit()
            finally:
                conn.close()

        self.storage.update_account_balance(balance_delta=proceeds, realized_delta=realized_pnl)

        trade = PaperTrade(
            id=None,
            market_id=p["market_id"],
            position_id=pos_id,
            action="SELL",
            outcome=p["outcome"],
            shares=p["shares"],
            price=cur_px,
            dollar_value=proceeds,
            realized_pnl=realized_pnl,
            timestamp=datetime.now(timezone.utc).isoformat(),
            reason=reason,
            strategy_type=p.get("strategy_type", "ASYMMETRIC_EDGE"),
            exit_trigger=exit_trigger
        )
        self.storage.record_paper_trade(trade)

        icon = "🎯" if exit_trigger == "TAKE_PROFIT" else ("🛡️" if exit_trigger == "STOP_LOSS" else "💰")
        level = "accent" if realized_pnl > 0 else ("warning" if exit_trigger == "STOP_LOSS" else "info")
        self.storage.add_activity(
            category="ACTIVE_EXIT" if exit_trigger in ["TAKE_PROFIT", "STOP_LOSS"] else "PAPER_ORDER",
            title=f"{icon} Position Sold (#{pos_id}) [{exit_trigger}]",
            details=f"Liquidated {p['shares']} shares of '{p.get('question', p['market_id'])[:28]}' @ ${cur_px:.3f}. Proceeds: ${proceeds:.2f} (Net P&L: {'+' if realized_pnl>=0 else ''}${realized_pnl:.2f}). Reason: {reason}",
            level=level
        )
        return {"pos_id": pos_id, "proceeds": proceeds, "realized_pnl": realized_pnl, "exit_trigger": exit_trigger}

    def flatten_all_positions(self) -> List[Dict[str, Any]]:
        """Liquidates all active open paper bets at current market prices."""
        open_pos = self.storage.get_open_positions()
        results = []
        for p in open_pos:
            res = self.close_single_position(p["id"], reason="Portfolio Flatten All triggered by user.", exit_trigger="MANUAL_FLATTEN")
            if res:
                results.append(res)
        return results
