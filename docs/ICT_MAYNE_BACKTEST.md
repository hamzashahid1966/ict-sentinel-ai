# Trader Mayne ICT framework: backtest

Generated 2026-11-25 10:17 UTC. Coins: BTC, ETH, SOL, XRP, BNB, DOGE, ZEC, HYPE, NEAR, SUI, ADA, LINK.
Rules pre-registered in `research/ict_mayne.py` (2026-11-25) from the pre-trade checklist, before any run.
R = the amount risked on a trade (entry to stop). Net = after 0.05% fees per fill and 0.02% slippage.
Equity = risking 1% of the account per trade, compounding. Funding is not charged.

| variant | data | trades | win % | avg R gross | avg R net | 95% CI | coin-flip 95th | holdout avg R | months + | 1% risk equity | max drop | PASS |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| W-D market | 2019-09 to 2026-11 | 3 | 33% | +0.105 | +0.096 | -1.007 to +2.300 | +1.693 | -1.007 (1) | 33% of 3 | +0.3% | -1.0% | no |
| W-D breaker | 2019-09 to 2026-11 | 8 | 38% | +0.324 | +0.308 | -0.833 to +1.864 | +0.319 | +0.254 (4) | 29% of 7 | +2.3% | -2.6% | no |
| D-1h market | 2019-09 to 2026-11 | 189 | 38% | +0.094 | +0.042 | -0.167 to +0.270 | -0.033 | -0.088 (78) | 46% of 74 | +5.8% | -19.7% | no |
| D-1h breaker | 2019-09 to 2026-11 | 191 | 37% | +0.098 | +0.039 | -0.221 to +0.316 | +0.012 | -0.073 (76) | 44% of 73 | +4.7% | -32.1% | no |
| 4h-15m market | 2019-09 to 2026-11 | 692 | 31% | -0.066 | -0.177 | -0.294 to -0.065 | -0.009 | -0.257 (288) | 33% of 83 | -72.9% | -74.0% | no |
| 4h-15m breaker | 2019-09 to 2026-11 | 819 | 31% | -0.098 | -0.224 | -0.329 to -0.117 | -0.143 | -0.315 (342) | 31% of 84 | -85.6% | -86.0% | no |

## How many setups survive each checklist step

| variant | HTF trend + MSB | valid POI in discount/premium | price tapped POI | LTF sweep + MSS | failed 2R / stop-width check | breaker retest missed | trades |
|---|---|---|---|---|---|---|---|
| W-D market | 147 | 97 | 56 | 25 | 22 | 0 | 3 |
| W-D breaker | 146 | 97 | 56 | 20 | 6 | 6 | 8 |
| D-1h market | 1150 | 779 | 534 | 434 | 245 | 0 | 189 |
| D-1h breaker | 1152 | 782 | 537 | 442 | 157 | 94 | 191 |
| 4h-15m market | 7022 | 4651 | 3149 | 2273 | 1581 | 0 | 692 |
| 4h-15m breaker | 7042 | 4663 | 3154 | 2150 | 950 | 381 | 819 |

## W-D market

- Exits: 1 reached the target, 2 stopped (some after taking half at 2R), 0 still open at the end.
- Longs: 3 trades, avg +0.096 R. Shorts: 0 trades, avg +0.000 R.
- Median time in a trade: 288 hours. Coin-flip direction average: +0.053 R.
- Checks (CI > 0, beats coin flip, holdout > 0, months >= 55%): no, no, no, no

| year | trades | net R |
|---|---|---|
| 2022 | 1 | -1.0 |
| 2024 | 1 | +2.3 |
| 2025 | 1 | -1.0 |

| coin | trades | net R |
|---|---|---|
| DOGE | 2 | +1.3 |
| NEAR | 1 | -1.0 |

## W-D breaker

- Exits: 2 reached the target, 6 stopped (some after taking half at 2R), 0 still open at the end.
- Longs: 7 trades, avg -0.012 R. Shorts: 1 trades, avg +2.555 R.
- Median time in a trade: 372 hours. Coin-flip direction average: -0.287 R.
- Checks (CI > 0, beats coin flip, holdout > 0, months >= 55%): no, no, yes, no

| year | trades | net R |
|---|---|---|
| 2020 | 1 | -1.0 |
| 2022 | 1 | -1.0 |
| 2024 | 2 | +3.5 |
| 2025 | 3 | +2.0 |
| 2026 | 1 | -1.0 |

| coin | trades | net R |
|---|---|---|
| DOGE | 3 | +4.0 |
| ETH | 1 | -1.0 |
| NEAR | 1 | -1.0 |
| XRP | 1 | +2.6 |
| ZEC | 2 | -2.0 |

## D-1h market

- Exits: 46 reached the target, 142 stopped (some after taking half at 2R), 1 still open at the end.
- Longs: 88 trades, avg +0.115 R. Shorts: 101 trades, avg -0.022 R.
- Median time in a trade: 52 hours. Coin-flip direction average: -0.129 R.
- Checks (CI > 0, beats coin flip, holdout > 0, months >= 55%): no, yes, no, no

| year | trades | net R |
|---|---|---|
| 2019 | 2 | +0.9 |
| 2020 | 14 | -0.3 |
| 2021 | 26 | +11.0 |
| 2022 | 20 | +2.2 |
| 2023 | 25 | -3.9 |
| 2024 | 36 | +1.3 |
| 2025 | 45 | +0.3 |
| 2026 | 21 | -3.6 |

| coin | trades | net R |
|---|---|---|
| ADA | 15 | +16.4 |
| BNB | 16 | -0.1 |
| BTC | 14 | -0.4 |
| DOGE | 20 | +2.6 |
| ETH | 11 | +3.0 |
| HYPE | 3 | +0.0 |
| LINK | 21 | +1.3 |
| NEAR | 18 | +5.2 |
| SOL | 19 | -0.7 |
| SUI | 12 | -8.8 |
| XRP | 23 | -3.6 |
| ZEC | 17 | -7.0 |

## D-1h breaker

- Exits: 41 reached the target, 149 stopped (some after taking half at 2R), 1 still open at the end.
- Longs: 95 trades, avg +0.120 R. Shorts: 96 trades, avg -0.042 R.
- Median time in a trade: 25 hours. Coin-flip direction average: -0.173 R.
- Checks (CI > 0, beats coin flip, holdout > 0, months >= 55%): no, yes, no, no

| year | trades | net R |
|---|---|---|
| 2019 | 2 | +1.2 |
| 2020 | 17 | -8.9 |
| 2021 | 32 | +27.2 |
| 2022 | 21 | +6.8 |
| 2023 | 23 | -11.2 |
| 2024 | 33 | -13.2 |
| 2025 | 42 | +5.7 |
| 2026 | 21 | -0.1 |

| coin | trades | net R |
|---|---|---|
| ADA | 16 | +22.2 |
| BNB | 18 | -7.7 |
| BTC | 15 | -3.1 |
| DOGE | 18 | +5.3 |
| ETH | 9 | -3.6 |
| HYPE | 3 | +0.2 |
| LINK | 16 | -1.6 |
| NEAR | 19 | +10.0 |
| SOL | 20 | +1.5 |
| SUI | 12 | -6.9 |
| XRP | 23 | -6.9 |
| ZEC | 22 | -2.0 |

## 4h-15m market

- Exits: 147 reached the target, 545 stopped (some after taking half at 2R), 0 still open at the end.
- Longs: 301 trades, avg -0.175 R. Shorts: 391 trades, avg -0.179 R.
- Median time in a trade: 6 hours. Coin-flip direction average: -0.094 R.
- Checks (CI > 0, beats coin flip, holdout > 0, months >= 55%): no, no, no, no

| year | trades | net R |
|---|---|---|
| 2020 | 76 | -3.9 |
| 2021 | 115 | -22.0 |
| 2022 | 74 | +9.6 |
| 2023 | 90 | -24.4 |
| 2024 | 116 | -3.3 |
| 2025 | 125 | -55.0 |
| 2026 | 96 | -23.8 |

| coin | trades | net R |
|---|---|---|
| ADA | 74 | -15.9 |
| BNB | 74 | -5.5 |
| BTC | 51 | -9.0 |
| DOGE | 70 | -10.5 |
| ETH | 67 | -20.4 |
| HYPE | 6 | -2.8 |
| LINK | 57 | -3.5 |
| NEAR | 60 | -22.8 |
| SOL | 68 | -0.7 |
| SUI | 33 | -10.6 |
| XRP | 67 | -17.2 |
| ZEC | 65 | -4.0 |

## 4h-15m breaker

- Exits: 142 reached the target, 677 stopped (some after taking half at 2R), 0 still open at the end.
- Longs: 382 trades, avg -0.114 R. Shorts: 437 trades, avg -0.320 R.
- Median time in a trade: 4 hours. Coin-flip direction average: -0.226 R.
- Checks (CI > 0, beats coin flip, holdout > 0, months >= 55%): no, no, no, no

| year | trades | net R |
|---|---|---|
| 2019 | 1 | -1.1 |
| 2020 | 97 | -14.4 |
| 2021 | 134 | -22.7 |
| 2022 | 88 | +2.7 |
| 2023 | 100 | -44.9 |
| 2024 | 130 | +1.6 |
| 2025 | 147 | -72.4 |
| 2026 | 122 | -32.4 |

| coin | trades | net R |
|---|---|---|
| ADA | 83 | -37.9 |
| BNB | 87 | +10.2 |
| BTC | 60 | -21.7 |
| DOGE | 87 | -14.4 |
| ETH | 89 | -19.3 |
| HYPE | 9 | -4.7 |
| LINK | 66 | -17.3 |
| NEAR | 75 | -19.5 |
| SOL | 72 | -18.0 |
| SUI | 35 | -10.9 |
| XRP | 77 | -21.1 |
| ZEC | 79 | -8.9 |
