> **Market: EUR/USD (EUR/USDT).** Costs here are a retail forex/gold broker's, not crypto's: 0.01% per fill and 0.005% slippage, minimum stop 0.04% of price (see `research/other_markets.py`). Where the text below says 0.05% / 0.02% / 0.25%, read these values instead. Forex weekend hours removed.

# The Trading Channel two-time-frame pullback: backtest

Generated 2026-11-25 10:50 UTC. Coins: EUR.
Rules pre-registered in `research/tc_pullback.py` (2026-11-25) before any run. R = amount risked per trade. Net = after 0.05% fee per fill and 0.02% slippage. Equity = 1% risk per trade, compounding. Funding not charged.

| HTF -> entry | data | trades | win % | target (median R) | avg R gross | avg R net | 95% CI | coin-flip 95th | last third avg R | months + | 1% risk equity | max drop | Sharpe | PASS |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 15m-5m | 2020-01 to 2026-10 | 19 | 5% | 3.0 | -0.395 | -0.737 | -1.342 to +0.514 | -0.737 | -1.299 (8) | 6% of 16 | -13.5% | -13.5% | -0.57 | no |
| 1h-15m | 2020-01 to 2026-10 | 22 | 18% | 3.1 | -0.225 | -0.554 | -1.139 to +0.277 | -0.048 | -0.290 (11) | 21% of 19 | -11.7% | -13.8% | -0.63 | no |
| 4h-1h | 2020-01 to 2026-10 | 14 | 21% | 2.7 | +0.002 | -0.162 | -1.138 to +0.871 | -0.254 | -1.200 (5) | 25% of 12 | -2.5% | -5.9% | -0.14 | no |
| 1D-4h | 2020-01 to 2026-10 | 5 | 0% | 3.8 | -0.978 | -1.112 | -1.200 to -1.056 | -0.435 | -1.081 (2) | 0% of 5 | -5.4% | -5.4% | -0.97 | no |

## How many setups survive each step

| HTF -> entry | trend (2 BOS) + zone | pulled back into zone | double bottom/top + rejection candle | failed 2R / stop-width | trades |
|---|---|---|---|---|---|
| 15m-5m | 2716 | 2584 | 89 | 70 | 19 |
| 1h-15m | 950 | 905 | 72 | 50 | 22 |
| 4h-1h | 340 | 321 | 47 | 33 | 14 |
| 1D-4h | 82 | 80 | 12 | 7 | 5 |

## 15m-5m

Median time in a trade: 1 hours. Coin-flip direction average: -1.038 R.

| year | trades | avg net R |
|---|---|---|
| 2020 | 2 | -1.172 |
| 2021 | 3 | -1.313 |
| 2022 | 5 | -1.329 |
| 2023 | 1 | +9.322 |
| 2024 | 1 | -1.324 |
| 2025 | 6 | -1.311 |
| 2026 | 1 | -1.198 |

## 1h-15m

Median time in a trade: 2 hours. Coin-flip direction average: -0.567 R.

| year | trades | avg net R |
|---|---|---|
| 2020 | 2 | +1.244 |
| 2021 | 2 | -1.210 |
| 2022 | 4 | -1.216 |
| 2023 | 3 | -1.399 |
| 2024 | 2 | -1.286 |
| 2025 | 4 | +0.653 |
| 2026 | 5 | -0.645 |

## 4h-1h

Median time in a trade: 2 hours. Coin-flip direction average: -0.531 R.

| year | trades | avg net R |
|---|---|---|
| 2020 | 3 | +0.658 |
| 2021 | 1 | -1.073 |
| 2022 | 4 | +0.059 |
| 2023 | 1 | +2.591 |
| 2025 | 1 | -1.108 |
| 2026 | 4 | -1.223 |

## 1D-4h

Median time in a trade: 12 hours. Coin-flip direction average: -0.739 R.

| year | trades | avg net R |
|---|---|---|
| 2020 | 1 | -1.070 |
| 2022 | 1 | -1.040 |
| 2023 | 1 | -1.285 |
| 2025 | 1 | -1.057 |
| 2026 | 1 | -1.106 |
