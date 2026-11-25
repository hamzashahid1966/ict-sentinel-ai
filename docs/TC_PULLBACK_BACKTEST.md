# The Trading Channel two-time-frame pullback: backtest

Generated 2026-11-25 10:38 UTC. Coins: BTC, ETH, SOL, XRP, BNB, DOGE, ZEC, HYPE, NEAR, SUI, ADA, LINK.
Rules pre-registered in `research/tc_pullback.py` (2026-11-25) before any run. R = amount risked per trade. Net = after 0.05% fee per fill and 0.02% slippage. Equity = 1% risk per trade, compounding. Funding not charged.

| HTF -> entry | data | trades | win % | target (median R) | avg R gross | avg R net | 95% CI | coin-flip 95th | last third avg R | months + | 1% risk equity | max drop | Sharpe | PASS |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 15m-5m | 2020-01 to 2026-11 | 2285 | 24% | 2.9 | +0.010 | -0.277 | -0.347 to -0.211 | -0.232 | -0.212 (670) | 20% of 83 | -99.9% | -99.9% | -2.82 | no |
| 1h-15m | 2019-09 to 2026-11 | 1234 | 24% | 3.0 | +0.001 | -0.196 | -0.306 to -0.083 | -0.153 | -0.135 (429) | 31% of 86 | -92.7% | -93.6% | -1.36 | no |
| 4h-1h | 2019-09 to 2026-11 | 294 | 24% | 2.9 | -0.020 | -0.123 | -0.323 to +0.077 | +0.039 | -0.025 (119) | 35% of 78 | -33.6% | -40.2% | -0.48 | no |
| 1D-4h | 2019-09 to 2026-11 | 88 | 22% | 3.1 | +0.186 | +0.138 | -0.431 to +0.855 | +0.012 | +0.298 (32) | 36% of 47 | +9.7% | -19.4% | 0.15 | no |

## How many setups survive each step

| HTF -> entry | trend (2 BOS) + zone | pulled back into zone | double bottom/top + rejection candle | failed 2R / stop-width | trades |
|---|---|---|---|---|---|
| 15m-5m | 77406 | 73780 | 9032 | 6747 | 2285 |
| 1h-15m | 20542 | 19357 | 3821 | 2587 | 1234 |
| 4h-1h | 5062 | 4738 | 993 | 699 | 294 |
| 1D-4h | 831 | 775 | 241 | 153 | 88 |

## 15m-5m

Median time in a trade: 1 hours. Coin-flip direction average: -0.264 R.

| year | trades | avg net R |
|---|---|---|
| 2020 | 288 | -0.182 |
| 2021 | 386 | -0.211 |
| 2022 | 430 | -0.458 |
| 2023 | 348 | -0.296 |
| 2024 | 277 | -0.302 |
| 2025 | 273 | -0.205 |
| 2026 | 283 | -0.211 |

## 1h-15m

Median time in a trade: 2 hours. Coin-flip direction average: -0.208 R.

| year | trades | avg net R |
|---|---|---|
| 2019 | 6 | +1.768 |
| 2020 | 119 | -0.170 |
| 2021 | 192 | +0.025 |
| 2022 | 191 | -0.322 |
| 2023 | 213 | -0.509 |
| 2024 | 174 | -0.078 |
| 2025 | 155 | -0.013 |
| 2026 | 184 | -0.279 |

## 4h-1h

Median time in a trade: 8 hours. Coin-flip direction average: -0.083 R.

| year | trades | avg net R |
|---|---|---|
| 2019 | 2 | +1.152 |
| 2020 | 23 | -0.484 |
| 2021 | 30 | -0.472 |
| 2022 | 47 | -0.122 |
| 2023 | 47 | -0.139 |
| 2024 | 46 | +0.082 |
| 2025 | 48 | -0.171 |
| 2026 | 51 | +0.066 |

## 1D-4h

Median time in a trade: 24 hours. Coin-flip direction average: -0.267 R.

| year | trades | avg net R |
|---|---|---|
| 2019 | 1 | -1.035 |
| 2020 | 7 | +0.571 |
| 2021 | 14 | -0.117 |
| 2022 | 9 | +0.373 |
| 2023 | 16 | -0.188 |
| 2024 | 16 | -0.165 |
| 2025 | 16 | +1.222 |
| 2026 | 9 | -0.709 |
