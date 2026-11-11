# ICT 2024 Mentorship Master Compendium & Sentinel AI Knowledge Base

---

## 1. Executive Summary & Purpose

This compendium serves as the permanent institutional record of the **ICT 2024 Mentorship (Lectures 1–52)**, codifying Michael J. Huddleston’s complete algorithmic trading framework into an autonomous quantitative model implemented in **ICT Sentinel AI**.

Every design decision, mathematical parameter, risk boundary, and execution rule in the codebase directly maps to the principles documented herein.

---

## 2. Core Algorithmic Architecture: The 5 Pillars of ICT 2024

### Pillar 1: Time & Macro Windows (The Algorithm Operates on a Clock)
The Interbank Price Delivery Algorithm (IPDA) does not trade continuously. It seeks liquidity only during designated delivery windows:

| Session | Reference Window (EST) | Execution Window (EST) | Exit Deadline (EST) | Primary Role |
| :--- | :--- | :--- | :--- | :--- |
| **London Killzone** | 20:00 – 02:00 | **02:00 – 04:30** | 06:00 | **Manipulation (Judas Swing)**: Raids Asian range liquidity; sets daily high/low for FX & Gold. |
| **New York AM** | 00:00 – 08:00 | **08:00 – 10:30** | 11:45 | **Distribution / Expansion**: Prime session for Equity Index Futures (`NQ`) & Metals (`GC`, `SI`). |
| **Asian Macro** | 15:00 – 18:00 | **18:50 – 20:15** | 22:00 | **CME Re-open Macro**: CME futures re-open after 5:00–6:00 PM halt; targets initial Asian imbalance. |

#### Non-Trading "Dead Zones":
* **11:30 AM – 01:30 PM EST (New York Lunch):** Algorithm volume collapses. Market makers rebalance books. Trading is strictly forbidden due to whipsaws.
* **04:30 AM – 08:00 AM EST (Inter-Session Transition):** European morning desks wind down; US institutions have not opened. High spread risk.
* **17:00 – 18:00 EST (CME Maintenance Halt):** Exchange halted.

---

### Pillar 2: Liquidity Sweeps vs. Turtle Soups
* **Liquidity Pools:**
  * **Buy-Side Liquidity (BSL):** Resting buy stop orders clustered above swing highs and session reference highs.
  * **Sell-Side Liquidity (SSL):** Resting sell stop orders clustered below swing lows and session reference lows.
* **The Judas Swing:** A false breakout engineered by smart money to run stops and accumulate counterpart volume before the true directional move.

---

### Pillar 3: Candle Body MSS vs. Wick Fakeouts (Lecture 48, 51)
* **The Body Tells the Truth, The Wick Lies:**
  * A wick extending beyond a swing high/low represents a liquidity grab (Turtle Soup).
  * A true **Market Structure Shift (MSS)** requires the **candle body (close)** to cross the key swing level on the 5-minute timeframe.
  * If price only wicks through a level without closing inside/beyond it, the setup is **invalidated**.

---

### Pillar 4: Consequent Encroachment (50% C.E.) of Fair Value Gaps (Lectures 35, 41)
* **Fair Value Gaps (FVG):**
  * **SIBI (Sell-Side Imbalance, Buy-Side Inefficiency):** 3-candle bearish gap where `Candle[0].Low > Candle[2].High`.
  * **BISI (Buy-Side Imbalance, Sell-Side Inefficiency):** 3-candle bullish gap where `Candle[2].Low > Candle[0].High`.
* **Consequent Encroachment (C.E.):** The exact 50% midpoint of the FVG:
  $$\text{C.E.} = \text{Low} + 0.5 \times (\text{High} - \text{Low})$$
* **The Invalidation Rule:**
  * In a Bearish SIBI, candle bodies **must not close above 50% C.E.** Wicks may probe above, but body closure above C.E. signals rejection failure.
  * In a Bullish BISI, candle bodies **must not close below 50% C.E.**

---

### Pillar 5: The 10:00 AM Gate Filter (Lecture 51)
* During the New York AM session, evaluate the 09:30 AM cash open relative to the 09:00–09:30 AM opening candle range.
* **Gate Trigger:** If the 09:30 AM opening price is trapped inside the 09:00–09:30 AM range:
  * **Quarantine all executions until 10:00:00 AM EST.**
  * The market is in an opening equilibrium trap; entries before 10:00 AM suffer high failure rates.

---

## 3. Order Management System: The Double Tap Execution Model

Designed for strict risk control on small balances ($500 starting capital):

```
Entry (Market/Limit at FVG)
  │
  ├── Stage 1: Initial Risk Bracket
  │     • Stop Loss: Placed 2 ticks beyond Reference High/Low.
  │     • Risk Budget: $25 max per trade (5% of $500 balance).
  │
  ├── Stage 2: Center Mass Target (1.5R) — 50% Position
  │     • When price hits +1.5R, 50% of the position is banked.
  │     • Shield #1 Engaged: Stop loss immediately moves to Breakeven + 2 ticks buffer.
  │     • Result: Trade is mathematically guaranteed risk-free.
  │
  └── Stage 3: Head Shot Target (3.0R) — 50% Runner
        • Trailed behind successive 5m FVG Consequent Encroachments.
        • Full 3.0R target hit = Institutional Expansion completion.
```

---

## 4. Adaptive Memory & Bayesian Self-Learning Engine

The bot does not use static, unlearning weights. It implements Bayesian inference to adapt to regime shifts:

### Bayesian Quality Score (BQS) Formula
Using a **Beta(2, 2) conjugate prior** (starting with a balanced $50\%$ expectation):

$$\text{BQS} = \frac{\alpha_{\text{prior}} + \text{Wins}}{\alpha_{\text{prior}} + \beta_{\text{prior}} + \text{Total Episodes}} - (\text{Consecutive Losses} \times 0.15)$$

### Dynamic Regime Status Lifecycle
* **`PRIME` (BQS $\ge$ 55%):** Full standard risk allocation ($25/trade).
* **`OBSERVATION` (45% $\le$ BQS < 55%):** Downsized risk ($12.50/trade); targets limited to Center Mass (1.5R).
* **`QUARANTINED` (BQS < 45% or 2 Consecutive Losses):** Trading halted on this asset/session pair. Entries blocked until paper trade proof of recovery.

### Post-Mortem Taxonomy
Every closed trade triggers an automated post-mortem reflection:
1. `EXPANSION_SUCCESS`: 3.0R Head Shot banked cleanly. Reinforces regime weight.
2. `DEFENSIVE_HARVEST`: 1.5R Center Mass banked, runner stopped at BE. Valid execution.
3. `INVALIDATION_POST_MORTEM`: Full loss. Analyzes whether failure was due to wick fakeout, C.E. violation, or inter-session spread widening.

---

## 5. Cloud Architecture & Infrastructure Guide

### Deployment Stack
* **Container:** Docker (`python:3.11-slim`) with healthcheck ping.
* **Cloud Platform:** Render Web Service (`https://ict-sentinel-ai.onrender.com`).
* **Source Repository:** GitHub (`https://github.com/hamzashahid1966/ict-sentinel-ai`).
* **Persistence:** SQLite (`sentinel.db`) with Write-Ahead Logging (`WAL` mode) and thread-local connection pooling.
* **Streaming Protocol:** Native Server-Sent Events (`/api/stream`) for zero-polling real-time updates.

### Keep-Alive Mechanism (Defeating Render 15-Minute Spin-Down)
* Render Free Tier sleeps after 15 minutes of zero HTTP traffic.
* **Solution:** External cron job configured at **cron-job.org** pinging `https://ict-sentinel-ai.onrender.com/api/state` every **10 minutes**.
* The idle timer is perpetually reset, guaranteeing uninterrupted 24/7 tape scanning.

---

## 6. Directory Index

* `ict_sentinel/ipda_engine.py` — Complete 52-lecture IPDA rules engine & market diagnostics.
* `ict_sentinel/order_manager.py` — Double Tap OMS (Center Mass, Head Shot, Defensive Shields).
* `ict_sentinel/memory_engine.py` — Bayesian Quality Score calculator & episodic memory vectors.
* `ict_sentinel/data_feed.py` — Real-time CME & Forex ingestion with smart cache throttling.
* `ict_sentinel/web_server.py` — Unified Browser Command Center with Live Radar and Diagnostics.
* `docs/transcripts_and_research/` — Raw lecture transcripts (26–45), OCR captures, and forum research.

