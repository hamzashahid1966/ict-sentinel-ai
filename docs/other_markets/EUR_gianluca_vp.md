> **Market: EUR/USD (EUR/USDT).** Costs here are a retail forex/gold broker's, not crypto's: 0.01% per fill and 0.005% slippage, minimum stop 0.04% of price (see `research/other_markets.py`). Where the text below says 0.05% / 0.02% / 0.25%, read these values instead. Forex weekend hours removed.

# Gian Luca statistical volume-profile strategy: backtest

Generated 2026-11-25 10:50 UTC. 15-minute candles, New York session, 2020-01 to 2026-10. Coins: EUR.
Rules pre-registered in `research/gianluca_vp.py` (2026-11-25) before any run. R = amount risked per trade. Net = after 0.05% fee per fill and 0.02% slippage. Funding not charged (trades last hours).

| measure | result |
|---|---|
| trades | 212 (106 long, 106 short) |
| win rate | 36.8% (2R target needs about 34% to break even before costs) |
| avg R gross / net | +0.015 / -0.165 |
| 95% CI of avg net R | -0.269 to -0.060 |
| coin-flip direction (avg, 95th pct) | -0.211, -0.145 |
| in-sample avg net R | -0.206 (156 trades) |
| out-of-sample avg net R | -0.050 (56 trades) |
| months positive | 38% of 71 |
| exits | 14 target, 48 stop, 150 session close |
| flat 1% risk: equity, max drop, Sharpe | -30.0%, -31.5%, -1.11 |
| meta-label + fractional Kelly: equity, max drop, Sharpe | -16.2%, -17.1%, -1.09 |
| PASS (CI > 0, beats coin flip, out-of-sample > 0, months >= 55%) | no (no, no, no, no) |

## Does the 5-point meta-label pick better trades?

Useful only if score 4-5 beats score 2-3 in both halves: **no**.

| period | trades score 2-3 | avg net R | trades score 4-5 | avg net R |
|---|---|---|---|---|
| in-sample (first 2/3) | 89 | -0.150 | 67 | -0.281 |
| out-of-sample (last 1/3) | 27 | -0.038 | 29 | -0.062 |

| score | trades | avg net R |
|---|---|---|
| 2 | 0 | +nan |
| 3 | 116 | -0.124 |
| 4 | 79 | -0.211 |
| 5 | 17 | -0.232 |
| ATR percentile 51-75: yes / no | 58 / 154 | -0.114 / -0.184 |
| fresh regime: yes / no | 212 / 0 | -0.165 / +nan |

| year | trades | avg net R | total R |
|---|---|---|---|
| 2020 | 41 | -0.177 | -7.3 |
| 2021 | 23 | -0.426 | -9.8 |
| 2022 | 26 | -0.186 | -4.8 |
| 2023 | 45 | -0.020 | -0.9 |
| 2024 | 38 | -0.232 | -8.8 |
| 2025 | 23 | -0.195 | -4.5 |
| 2026 | 16 | +0.073 | +1.2 |

| coin | trades | avg net R |
|---|---|---|
| EUR | 212 | -0.165 |
