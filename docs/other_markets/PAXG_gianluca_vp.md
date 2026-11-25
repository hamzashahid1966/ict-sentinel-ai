> **Market: gold (PAXG/USDT).** Costs here are a retail forex/gold broker's, not crypto's: 0.01% per fill and 0.005% slippage, minimum stop 0.04% of price (see `research/other_markets.py`). Where the text below says 0.05% / 0.02% / 0.25%, read these values instead. Forex weekend hours removed.

# Gian Luca statistical volume-profile strategy: backtest

Generated 2026-11-25 10:49 UTC. 15-minute candles, New York session, 2020-09 to 2026-10. Coins: PAXG.
Rules pre-registered in `research/gianluca_vp.py` (2026-11-25) before any run. R = amount risked per trade. Net = after 0.05% fee per fill and 0.02% slippage. Funding not charged (trades last hours).

| measure | result |
|---|---|
| trades | 165 (82 long, 83 short) |
| win rate | 40.6% (2R target needs about 34% to break even before costs) |
| avg R gross / net | -0.015 / -0.117 |
| 95% CI of avg net R | -0.238 to +0.010 |
| coin-flip direction (avg, 95th pct) | -0.126, -0.063 |
| in-sample avg net R | -0.121 (110 trades) |
| out-of-sample avg net R | -0.110 (55 trades) |
| months positive | 37% of 67 |
| exits | 13 target, 44 stop, 108 session close |
| flat 1% risk: equity, max drop, Sharpe | -18.1%, -20.6%, -0.73 |
| meta-label + fractional Kelly: equity, max drop, Sharpe | -9.3%, -10.7%, -0.72 |
| PASS (CI > 0, beats coin flip, out-of-sample > 0, months >= 55%) | no (no, no, no, no) |

## Does the 5-point meta-label pick better trades?

Useful only if score 4-5 beats score 2-3 in both halves: **yes**.

| period | trades score 2-3 | avg net R | trades score 4-5 | avg net R |
|---|---|---|---|---|
| in-sample (first 2/3) | 55 | -0.225 | 55 | -0.016 |
| out-of-sample (last 1/3) | 30 | -0.159 | 25 | -0.050 |

| score | trades | avg net R |
|---|---|---|
| 2 | 1 | +1.079 |
| 3 | 84 | -0.217 |
| 4 | 66 | -0.055 |
| 5 | 14 | +0.105 |
| ATR percentile 51-75: yes / no | 54 / 111 | -0.105 / -0.123 |
| fresh regime: yes / no | 164 / 1 | -0.124 / +1.079 |

| year | trades | avg net R | total R |
|---|---|---|---|
| 2020 | 11 | -0.056 | -0.6 |
| 2021 | 26 | -0.158 | -4.1 |
| 2022 | 34 | -0.023 | -0.8 |
| 2023 | 28 | -0.279 | -7.8 |
| 2024 | 15 | +0.132 | +2.0 |
| 2025 | 29 | -0.178 | -5.2 |
| 2026 | 22 | -0.128 | -2.8 |

| coin | trades | avg net R |
|---|---|---|
| PAXG | 165 | -0.117 |
