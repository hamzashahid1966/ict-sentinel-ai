> **Market: gold (PAXG/USDT).** Costs here are a retail forex/gold broker's, not crypto's: 0.01% per fill and 0.005% slippage, minimum stop 0.04% of price (see `research/other_markets.py`). Where the text below says 0.05% / 0.02% / 0.25%, read these values instead. Forex weekend hours removed.

# The Trading Channel two-time-frame pullback: backtest

Generated 2026-11-25 10:50 UTC. Coins: PAXG.
Rules pre-registered in `research/tc_pullback.py` (2026-11-25) before any run. R = amount risked per trade. Net = after 0.05% fee per fill and 0.02% slippage. Equity = 1% risk per trade, compounding. Funding not charged.

| HTF -> entry | data | trades | win % | target (median R) | avg R gross | avg R net | 95% CI | coin-flip 95th | last third avg R | months + | 1% risk equity | max drop | Sharpe | PASS |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 15m-5m | 2020-09 to 2026-10 | 70 | 17% | 3.2 | -0.250 | -0.523 | -0.917 to -0.075 | -0.162 | -0.214 (36) | 21% of 43 | -31.3% | -35.1% | -1.09 | no |
| 1h-15m | 2020-09 to 2026-10 | 33 | 30% | 3.2 | +0.271 | +0.133 | -0.444 to +0.715 | +0.385 | +0.482 (23) | 40% of 25 | +3.7% | -9.7% | 0.13 | no |
| 4h-1h | 2020-09 to 2026-10 | 11 | 18% | 2.8 | -0.365 | -0.429 | -1.072 to +0.266 | +0.332 | -1.046 (4) | 20% of 10 | -4.7% | -7.2% | -0.44 | no |
| 1D-4h | 2020-09 to 2026-10 | 2 | 0% | 5.2 | -0.994 | -1.031 | -1.035 to -1.027 | +1.672 | -1.031 (2) | 0% of 2 | -2.1% | -2.1% | -1.86 | no |

## How many setups survive each step

| HTF -> entry | trend (2 BOS) + zone | pulled back into zone | double bottom/top + rejection candle | failed 2R / stop-width | trades |
|---|---|---|---|---|---|
| 15m-5m | 3127 | 2993 | 210 | 140 | 70 |
| 1h-15m | 924 | 875 | 97 | 64 | 33 |
| 4h-1h | 271 | 255 | 36 | 25 | 11 |
| 1D-4h | 72 | 71 | 11 | 9 | 2 |

## 15m-5m

Median time in a trade: 1 hours. Coin-flip direction average: -0.505 R.

| year | trades | avg net R |
|---|---|---|
| 2020 | 1 | +2.231 |
| 2021 | 15 | -0.949 |
| 2022 | 7 | -1.264 |
| 2023 | 6 | -0.373 |
| 2024 | 5 | -1.160 |
| 2025 | 16 | -0.225 |
| 2026 | 20 | -0.206 |

## 1h-15m

Median time in a trade: 3 hours. Coin-flip direction average: +0.021 R.

| year | trades | avg net R |
|---|---|---|
| 2020 | 1 | -1.073 |
| 2021 | 2 | -1.091 |
| 2022 | 2 | -1.181 |
| 2023 | 2 | -1.171 |
| 2024 | 3 | +0.423 |
| 2025 | 12 | -0.015 |
| 2026 | 11 | +1.024 |

## 4h-1h

Median time in a trade: 24 hours. Coin-flip direction average: -0.384 R.

| year | trades | avg net R |
|---|---|---|
| 2020 | 1 | -1.055 |
| 2021 | 2 | +0.607 |
| 2022 | 1 | +2.595 |
| 2023 | 1 | -1.138 |
| 2024 | 2 | -1.076 |
| 2025 | 3 | -1.052 |
| 2026 | 1 | -1.027 |

## 1D-4h

Median time in a trade: 16 hours. Coin-flip direction average: +0.861 R.

| year | trades | avg net R |
|---|---|---|
| 2024 | 1 | -1.035 |
| 2025 | 1 | -1.027 |
