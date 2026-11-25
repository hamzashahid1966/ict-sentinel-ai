# Gian Luca statistical volume-profile strategy: backtest

Generated 2026-11-25 10:19 UTC. 15-minute candles, New York session, 2019-09 to 2026-11. Coins: BTC, ETH, SOL, XRP, BNB, DOGE, ZEC, HYPE, NEAR, SUI, ADA, LINK.
Rules pre-registered in `research/gianluca_vp.py` (2026-11-25) before any run. R = amount risked per trade. Net = after 0.05% fee per fill and 0.02% slippage. Funding not charged (trades last hours).

| measure | result |
|---|---|
| trades | 2427 (1223 long, 1204 short) |
| win rate | 40.1% (2R target needs about 34% to break even before costs) |
| avg R gross / net | +0.057 / -0.064 |
| 95% CI of avg net R | -0.113 to -0.017 |
| coin-flip direction (avg, 95th pct) | -0.110, -0.093 |
| in-sample avg net R | -0.080 (1451 trades) |
| out-of-sample avg net R | -0.041 (976 trades) |
| months positive | 33% of 87 |
| exits | 215 target, 502 stop, 1710 session close |
| flat 1% risk: equity, max drop, Sharpe | -80.7%, -81.9%, -1.12 |
| meta-label + fractional Kelly: equity, max drop, Sharpe | -54.1%, -55.6%, -1.06 |
| PASS (CI > 0, beats coin flip, out-of-sample > 0, months >= 55%) | no (no, yes, no, no) |

## Does the 5-point meta-label pick better trades?

Useful only if score 4-5 beats score 2-3 in both halves: **no**.

| period | trades score 2-3 | avg net R | trades score 4-5 | avg net R |
|---|---|---|---|---|
| in-sample (first 2/3) | 904 | -0.075 | 547 | -0.087 |
| out-of-sample (last 1/3) | 571 | -0.078 | 405 | +0.011 |

| score | trades | avg net R |
|---|---|---|
| 2 | 115 | -0.127 |
| 3 | 1360 | -0.072 |
| 4 | 821 | -0.042 |
| 5 | 131 | -0.065 |
| ATR percentile 51-75: yes / no | 596 / 1831 | -0.028 / -0.076 |
| fresh regime: yes / no | 2289 / 138 | -0.059 / -0.143 |

| year | trades | avg net R | total R |
|---|---|---|---|
| 2019 | 8 | +0.461 | +3.7 |
| 2020 | 227 | -0.118 | -26.9 |
| 2021 | 322 | -0.026 | -8.5 |
| 2022 | 303 | -0.068 | -20.6 |
| 2023 | 388 | -0.109 | -42.1 |
| 2024 | 395 | -0.062 | -24.6 |
| 2025 | 444 | +0.023 | +10.3 |
| 2026 | 340 | -0.137 | -46.7 |

| coin | trades | avg net R |
|---|---|---|
| BTC | 226 | -0.075 |
| ETH | 238 | -0.045 |
| SOL | 213 | +0.024 |
| XRP | 222 | -0.114 |
| BNB | 212 | -0.122 |
| DOGE | 207 | -0.075 |
| ZEC | 233 | -0.135 |
| HYPE | 61 | -0.022 |
| NEAR | 224 | +0.003 |
| SUI | 123 | -0.053 |
| ADA | 234 | -0.134 |
| LINK | 234 | +0.016 |
