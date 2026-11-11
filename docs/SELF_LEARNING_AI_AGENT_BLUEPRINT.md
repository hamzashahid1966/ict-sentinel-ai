# ICT Sentinel AI: Self-Learning Autonomous Agent Architecture

---

## 1. Vision & Overview

The goal of **ICT Sentinel AI** is not merely to execute a rigid ruleset, but to operate as an **autonomous, self-learning AI trading agent**. 

An institutional human trader improves by:
1. Observing thousands of hours of live tape.
2. Formulating hypotheses during market sessions.
3. Conducting rigorous post-mortems on winning and losing trades.
4. Adapting risk allocations based on changing market regimes (e.g. high volatility news cycles vs summer low-liquidity consolidations).

ICT Sentinel AI replicates this cognitive architecture systematically through a 5-stage loop:
```
                      ┌────────────────────────────┐
                      │    1. Continuous Intake    │
                      │   (Tape Reading & Feeds)   │
                      └─────────────┬──────────────┘
                                    │
                                    ▼
                      ┌────────────────────────────┐
                      │   2. Knowledge Retrieval   │
                      │ (Lectures 1–52 & Checklists)│
                      └─────────────┬──────────────┘
                                    │
                                    ▼
                      ┌────────────────────────────┐
                      │   3. Cognitive Decision    │
                      │  (Invariants vs Confluence)│
                      └─────────────┬──────────────┘
                                    │
                                    ▼
                      ┌────────────────────────────┐
                      │   4. Double Tap Execution  │
                      │ (Risk Bracket + BE Shield) │
                      └─────────────┬──────────────┘
                                    │
                                    ▼
                      ┌────────────────────────────┐
                      │  5. Post-Mortem Reflection │
                      │  (Bayesian Update & Log)   │
                      └────────────────────────────┘
```

---

## 2. The 5 Cognitive Stages

### Stage 1: Continuous Tape Perception (24/7 Monitoring)
* The agent never turns off. It operates around the clock on cloud infrastructure.
* It ingests 5-minute OHLCV candles across multiple correlated asset classes (`EUR/USD`, `GBP/USD`, `GOLD`, `NASDAQ`, `SILVER`).
* During off-hours and Asian accumulation, it monitors price discovery and measures reference range boundaries.

### Stage 2: Dynamic Knowledge Retrieval
* The bot contains a native `KnowledgeEngine` that reads directly from `ict_mentorship_knowledge/`:
  * `01_foundational_concepts.json`: IPDA Time Theory, AMD Cycle, Liquidity Pools.
  * `02_execution_rules.json`: 10 AM Gate, Candle Body MSS, 50% Consequent Encroachment, Quadrant Filters.
  * `03_lecture_catalog.json`: Detailed 52-lecture index.
  * `04_adaptive_learning_log.json`: Historical episodic memory.
  * `05_chat_discussions_and_decisions.json`: Technical and design decisions.
* When evaluating an asset, the agent queries the knowledge base to cross-examine current tape against Michael Huddleston's doctrine.

### Stage 3: Hypothesis Testing & Shadow Tracking
* **Live Setup:** When all 5 conditions (Hard Invariants + Soft Confluence) align, an order is submitted to the OMS.
* **Shadow Setup (Self-Learning):** If a setup meets 4 out of 5 conditions (e.g. FVG present, Killzone active, but candle body closed exactly at swing level without clearing it):
  * The agent records a **Shadow Observation**.
  * It monitors whether price respected the level or collapsed into a stop-hunt.
  * This allows the agent to learn statistical boundaries over time without risking capital.

### Stage 4: Double Tap Order Execution
* Governed by Lecture 52:
  * **Stage 1:** Initial stop placed 2 ticks beyond reference high/low. Risk strictly capped at $25 (5% of $500).
  * **Stage 2:** At +1.5R, 50% of position is banked. Stop moves to Breakeven + 2 ticks buffer.
  * **Stage 3:** Remaining 50% trails behind 5m FVG Consequent Encroachments until the 3.0R Head Shot completes.

### Stage 5: Bayesian Learning & Reflection Ledger
* When a trade closes (Win, Loss, or Breakeven Scratch):
  * **Deconstruction:** The agent records entry precision, maximum adverse excursion (MAE), and exit efficiency.
  * **Bayesian Quality Score (BQS):** Updates using a Beta(2,2) conjugate prior:
    $$\text{BQS} = \frac{\alpha + \text{Wins}}{\alpha + \beta + \text{Total Episodes}} - (\text{Consecutive Losses} \times 0.15)$$
  * **Circuit Breaker:** If consecutive losses exceed 1, the asset/session pair enters **`QUARANTINE`** status. Risk is reduced to 0 until market behavior normalizes.
  * **Persistent Logging:** Writes to SQLite `trade_episodes` table and appends to `ict_mentorship_knowledge/04_adaptive_learning_log.json`.

---

## 3. Extensibility: How the Agent Continues Learning in the Future

As new market observations, mentorship transcripts, or custom user rules are added:
1. **Adding New Rules:** Simply add a new rule object to `ict_mentorship_knowledge/02_execution_rules.json`. The `KnowledgeEngine` automatically reloads and evaluates it on the next market tick.
2. **Reviewing Lessons:** The user or agent can inspect `ict_mentorship_knowledge/04_adaptive_learning_log.json` to review why specific trades succeeded or failed.
3. **Autonomous Growth:** With continuous cloud runtime and keepalive pings, the agent accumulates real-world trade reflections, continuously refining its edge over months and years of market cycles.

