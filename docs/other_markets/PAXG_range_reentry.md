> **Market: gold (PAXG/USDT).** Costs here are a retail forex/gold broker's, not crypto's: 0.01% per fill and 0.005% slippage, minimum stop 0.04% of price (see `research/other_markets.py`). Where the text below says 0.05% / 0.02% / 0.25%, read these values instead. Forex weekend hours removed.

# 4-hour range + 5-minute re-entry: backtest

Generated 2026-11-25 10:50 UTC. 5-minute candles, 2020-09 to 2026-10. Coins: PAXG.
Rules pre-registered in `research/range_reentry.py` (2026-11-25) before any run. R = amount risked per trade. Net = after 0.05% fee per fill and 0.02% slippage. Equity = 1% risk per trade, compounding.

| variant | trades | win % | avg R gross | avg R net | 95% CI | coin-flip 95th | last third avg R | months + | 1% risk equity | max drop | Sharpe | PASS |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| all-day | 3908 | 27.4% | -0.212 | -0.392 | -0.439 to -0.342 | -0.317 | -0.220 (1098) | 4% of 74 | -100.0% | -100.0% | -6.95 | no |
| skip-open | 3789 | 27.3% | -0.208 | -0.392 | -0.440 to -0.345 | -0.326 | -0.209 (1058) | 9% of 74 | -100.0% | -100.0% | -6.87 | no |
| after-10 | 2128 | 29.1% | -0.203 | -0.354 | -0.415 to -0.287 | -0.247 | -0.156 (567) | 15% of 74 | -100.0% | -100.0% | -4.91 | no |
| off-hours | 3133 | 26.1% | -0.225 | -0.428 | -0.482 to -0.373 | -0.354 | -0.231 (885) | 8% of 74 | -100.0% | -100.0% | -6.73 | no |

## All-day trades by New York hour of the trigger

| NY hour | trades | win % | avg net R |
|---|---|---|---|
| 04:00 | 385 | 28% | -0.368 |
| 05:00 | 399 | 22% | -0.552 |
| 06:00 | 366 | 27% | -0.423 |
| 07:00 | 367 | 23% | -0.502 |
| 08:00 | 401 | 31% | -0.263 |
| 09:00 | 379 | 27% | -0.394 |
| 10:00 | 321 | 35% | -0.210 |
| 11:00 | 213 | 32% | -0.255 |
| 12:00 | 168 | 24% | -0.526 |
| 13:00 | 129 | 24% | -0.481 |
| 14:00 | 110 | 30% | -0.379 |
| 15:00 | 105 | 23% | -0.468 |
| 16:00 | 75 | 24% | -0.482 |
| 17:00 | 70 | 19% | -0.630 |
| 18:00 | 75 | 35% | -0.275 |
| 19:00 | 67 | 27% | -0.311 |
| 20:00 | 77 | 31% | -0.368 |
| 21:00 | 90 | 31% | -0.234 |
| 22:00 | 61 | 36% | -0.284 |
| 23:00 | 50 | 18% | -0.486 |

## All-day: years and coins

| year | trades | avg net R |
|---|---|---|
| 2020 | 256 | -0.413 |
| 2021 | 715 | -0.468 |
| 2022 | 585 | -0.350 |
| 2023 | 662 | -0.538 |
| 2024 | 722 | -0.485 |
| 2025 | 512 | -0.212 |
| 2026 | 456 | -0.158 |

| coin | trades | avg net R |
|---|---|---|
| PAXG | 3908 | -0.392 |

All-day exits: 731 target, 2491 stop, 686 at the day's end. Coin-flip direction average: -0.334 R.
