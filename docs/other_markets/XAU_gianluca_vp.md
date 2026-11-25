> **Market: gold (XAU/USDT perp).** Costs here are a retail forex/gold broker's, not crypto's: 0.01% per fill and 0.005% slippage, minimum stop 0.04% of price (see `research/other_markets.py`). Where the text below says 0.05% / 0.02% / 0.25%, read these values instead. Forex weekend hours removed.

# Gian Luca statistical volume-profile strategy: backtest

Generated 2026-11-25 10:50 UTC. 15-minute candles, New York session, 2025-12 to 2026-10. Coins: XAU.
Rules pre-registered in `research/gianluca_vp.py` (2026-11-25) before any run. R = amount risked per trade. Net = after 0.05% fee per fill and 0.02% slippage. Funding not charged (trades last hours).

| measure | result |
|---|---|
| trades | 20 (10 long, 10 short) |
| win rate | 35.0% (2R target needs about 34% to break even before costs) |
| avg R gross / net | -0.267 / -0.337 |
| 95% CI of avg net R | -0.513 to -0.147 |
| coin-flip direction (avg, 95th pct) | -0.041, +0.170 |
| in-sample avg net R | -0.240 (8 trades) |
| out-of-sample avg net R | -0.402 (12 trades) |
| months positive | 30% of 10 |
| exits | 0 target, 5 stop, 15 session close |
| flat 1% risk: equity, max drop, Sharpe | -6.5%, -6.7%, -2.72 |
| meta-label + fractional Kelly: equity, max drop, Sharpe | -3.3%, -3.4%, -2.72 |
| PASS (CI > 0, beats coin flip, out-of-sample > 0, months >= 55%) | no (no, no, no, no) |

## Does the 5-point meta-label pick better trades?

Useful only if score 4-5 beats score 2-3 in both halves: **yes**.

| period | trades score 2-3 | avg net R | trades score 4-5 | avg net R |
|---|---|---|---|---|
| in-sample (first 2/3) | 4 | -0.360 | 4 | -0.119 |
| out-of-sample (last 1/3) | 6 | -0.411 | 6 | -0.392 |

| score | trades | avg net R |
|---|---|---|
| 2 | 0 | +nan |
| 3 | 10 | -0.391 |
| 4 | 8 | -0.310 |
| 5 | 2 | -0.175 |
| ATR percentile 51-75: yes / no | 6 / 14 | -0.315 / -0.346 |
| fresh regime: yes / no | 20 / 0 | -0.337 / +nan |

| year | trades | avg net R | total R |
|---|---|---|---|
| 2025 | 1 | +0.158 | +0.2 |
| 2026 | 19 | -0.363 | -6.9 |

| coin | trades | avg net R |
|---|---|---|
| XAU | 20 | -0.337 |
