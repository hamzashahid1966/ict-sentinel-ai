> **Market: gold (PAXG/USDT).** Costs here are a retail forex/gold broker's, not crypto's: 0.01% per fill and 0.005% slippage, minimum stop 0.04% of price (see `research/other_markets.py`). Where the text below says 0.05% / 0.02% / 0.25%, read these values instead. Forex weekend hours removed.

# Trader Mayne ICT framework: backtest

Generated 2026-11-25 10:49 UTC. Coins: PAXG.
Rules pre-registered in `research/ict_mayne.py` (2026-11-25) from the pre-trade checklist, before any run.
R = the amount risked on a trade (entry to stop). Net = after 0.05% fees per fill and 0.02% slippage.
Equity = risking 1% of the account per trade, compounding. Funding is not charged.

| variant | data | trades | win % | avg R gross | avg R net | 95% CI | coin-flip 95th | holdout avg R | months + | 1% risk equity | max drop | PASS |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| W-D market | 2020-09 to 2026-10 | 0 | | | | | | | | | | no |
| W-D breaker | 2020-09 to 2026-10 | 1 | 0% | -1.000 | -1.005 | -1.005 to -1.005 | -1.005 | -1.005 (1) | 0% of 1 | -1.0% | -1.0% | no |
| D-1h market | 2020-09 to 2026-10 | 9 | 33% | -0.107 | -0.152 | -0.877 to +0.571 | +0.513 | -0.207 (4) | 38% of 8 | -1.4% | -4.6% | no |
| D-1h breaker | 2020-09 to 2026-10 | 11 | 55% | +0.434 | +0.379 | -0.484 to +1.248 | +0.751 | -0.275 (4) | 55% of 11 | +4.1% | -3.2% | no |
| 4h-15m market | 2020-09 to 2026-10 | 23 | 43% | +0.406 | +0.309 | -0.456 to +1.063 | +0.926 | +0.434 (13) | 45% of 20 | +7.0% | -6.5% | no |
| 4h-15m breaker | 2020-09 to 2026-10 | 35 | 43% | +0.510 | +0.408 | -0.248 to +1.190 | +0.545 | +0.285 (22) | 42% of 26 | +14.5% | -6.7% | no |

## How many setups survive each checklist step

| variant | HTF trend + MSB | valid POI in discount/premium | price tapped POI | LTF sweep + MSS | failed 2R / stop-width check | breaker retest missed | trades |
|---|---|---|---|---|---|---|---|
| W-D market | 15 | 12 | 8 | 1 | 1 | 0 | 0 |
| W-D breaker | 15 | 12 | 8 | 1 | 0 | 0 | 1 |
| D-1h market | 92 | 62 | 41 | 23 | 14 | 0 | 9 |
| D-1h breaker | 91 | 61 | 40 | 26 | 11 | 4 | 11 |
| 4h-15m market | 375 | 233 | 158 | 95 | 72 | 0 | 23 |
| 4h-15m breaker | 374 | 232 | 157 | 83 | 36 | 12 | 35 |

## W-D breaker

- Exits: 0 reached the target, 1 stopped (some after taking half at 2R), 0 still open at the end.
- Longs: 1 trades, avg -1.005 R. Shorts: 0 trades, avg +0.000 R.
- Median time in a trade: 384 hours. Coin-flip direction average: -1.005 R.
- Checks (CI > 0, beats coin flip, holdout > 0, months >= 55%): no, no, no, no

| year | trades | net R |
|---|---|---|
| 2026 | 1 | -1.0 |

| coin | trades | net R |
|---|---|---|
| PAXG | 1 | -1.0 |

## D-1h market

- Exits: 2 reached the target, 7 stopped (some after taking half at 2R), 0 still open at the end.
- Longs: 3 trades, avg +0.064 R. Shorts: 6 trades, avg -0.260 R.
- Median time in a trade: 29 hours. Coin-flip direction average: -0.131 R.
- Checks (CI > 0, beats coin flip, holdout > 0, months >= 55%): no, no, no, no

| year | trades | net R |
|---|---|---|
| 2022 | 3 | +0.1 |
| 2023 | 2 | -0.6 |
| 2024 | 1 | -1.0 |
| 2026 | 3 | +0.2 |

| coin | trades | net R |
|---|---|---|
| PAXG | 9 | -1.4 |

## D-1h breaker

- Exits: 4 reached the target, 7 stopped (some after taking half at 2R), 0 still open at the end.
- Longs: 5 trades, avg +0.503 R. Shorts: 6 trades, avg +0.275 R.
- Median time in a trade: 24 hours. Coin-flip direction average: -0.022 R.
- Checks (CI > 0, beats coin flip, holdout > 0, months >= 55%): no, no, no, no

| year | trades | net R |
|---|---|---|
| 2021 | 1 | +2.1 |
| 2022 | 3 | +4.8 |
| 2023 | 2 | -0.6 |
| 2024 | 2 | -2.1 |
| 2025 | 1 | +2.2 |
| 2026 | 2 | -2.2 |

| coin | trades | net R |
|---|---|---|
| PAXG | 11 | +4.2 |

## 4h-15m market

- Exits: 8 reached the target, 15 stopped (some after taking half at 2R), 0 still open at the end.
- Longs: 14 trades, avg +0.585 R. Shorts: 9 trades, avg -0.120 R.
- Median time in a trade: 5 hours. Coin-flip direction average: +0.355 R.
- Checks (CI > 0, beats coin flip, holdout > 0, months >= 55%): no, no, yes, no

| year | trades | net R |
|---|---|---|
| 2021 | 3 | +7.7 |
| 2022 | 5 | -3.9 |
| 2023 | 1 | -1.2 |
| 2024 | 1 | -1.0 |
| 2025 | 9 | +6.4 |
| 2026 | 4 | -0.7 |

| coin | trades | net R |
|---|---|---|
| PAXG | 23 | +7.1 |

## 4h-15m breaker

- Exits: 12 reached the target, 23 stopped (some after taking half at 2R), 0 still open at the end.
- Longs: 18 trades, avg +0.823 R. Shorts: 17 trades, avg -0.033 R.
- Median time in a trade: 4 hours. Coin-flip direction average: +0.064 R.
- Checks (CI > 0, beats coin flip, holdout > 0, months >= 55%): no, no, yes, no

| year | trades | net R |
|---|---|---|
| 2021 | 6 | +14.4 |
| 2022 | 3 | -1.7 |
| 2023 | 3 | -3.7 |
| 2024 | 1 | -1.1 |
| 2025 | 14 | +4.9 |
| 2026 | 8 | +1.4 |

| coin | trades | net R |
|---|---|---|
| PAXG | 35 | +14.3 |
