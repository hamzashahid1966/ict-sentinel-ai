# ICT Sentinel AI — Autonomous Institutional Paper Trading System

An autonomous, 24/7 real-time paper trading engine and AI advisor codifying the complete **ICT 2024 Mentorship (Lectures 1–52)** across CME Futures (`Gold`, `Silver`, `Nasdaq`) and Interbank Forex (`EUR/USD`, `GBP/USD`).

---

## ⚡ Core Features

* **52-Lecture IPDA Rules Engine:** Codifies the 10:00 AM Gate Filter, Candle Body MSS validation (eliminating wick traps), 50% Consequent Encroachment (C.E.) respect, and Premium/Discount quadrant filters.
* **Double Tap OMS:** 50% partial at Center Mass (1.5R) with automatic defensive stop adjustment (Breakeven + 2 ticks buffer), trailing the remaining 50% runner to Head Shot (3.0R).
* **Adaptive Memory & Self-Learning Intelligence:** Dynamic Bayesian Quality Scores (BQS) using a Beta(2,2) conjugate prior. Enforces automatic regime quarantines on 2 consecutive losses.
* **Live Command Center:** Event-driven Server-Sent Events (SSE) streaming at `http://localhost:8080` (local) and `https://ict-sentinel-ai.onrender.com` (cloud).
* **AI Market Diagnostics Radar:** Real-time multi-asset market condition scoring, reference levels, 5-point setup checklists, and live plain-English executive reasoning.

---

## 🚀 Quick Start

### 1. Local Run
```bash
# Navigate to project folder
cd /Users/hamzashahid/Documents/Per/Projects/ict_sentinel_ai

# Check account status & open positions
python3 main.py --status

# Launch interactive Browser Command Center
python3 main.py --web
```
Open **`http://localhost:8080`** in your browser.

### 2. Cloud Instance (24/7)
* **Public URL:** [https://ict-sentinel-ai.onrender.com](https://ict-sentinel-ai.onrender.com)
* **Hosted on:** Render (Docker Web Service with 10-minute keep-alive ping)

---

## 📚 Documentation & Research Archive

* **[Master Mentorship Compendium](docs/ICT_2024_MENTORSHIP_COMPENDIUM.md):** Complete mathematical and algorithmic breakdown of all 52 lectures, execution models, and Bayesian scoring formulas.
* **[Raw Transcripts & Research](docs/transcripts_and_research/):** Permanent repository of original video transcripts, SRT subtitle files, OCR captures, and forum research.
