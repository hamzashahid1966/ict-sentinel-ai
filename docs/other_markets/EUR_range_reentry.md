> **Market: EUR/USD (EUR/USDT).** Costs here are a retail forex/gold broker's, not crypto's: 0.01% per fill and 0.005% slippage, minimum stop 0.04% of price (see `research/other_markets.py`). Where the text below says 0.05% / 0.02% / 0.25%, read these values instead. Forex weekend hours removed.

# 4-hour range + 5-minute re-entry: backtest

Generated 2026-11-25 10:50 UTC. 5-minute candles, 2020-01 to 2026-10. Coins: EUR.
Rules pre-registered in `research/range_reentry.py` (2026-11-25) before any run. R = amount risked per trade. Net = after 0.05% fee per fill and 0.02% slippage. Equity = 1% risk per trade, compounding.

| variant | trades | win % | avg R gross | avg R net | 95% CI | coin-flip 95th | last third avg R | months + | 1% risk equity | max drop | Sharpe | PASS |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| all-day | 3742 | 26.9% | -0.219 | -0.476 | -0.545 to -0.401 | -0.324 | -0.385 (1054) | 4% of 82 | -100.0% | -100.0% | -6.71 | no |
| skip-open | 3620 | 26.9% | -0.213 | -0.477 | -0.549 to -0.398 | -0.329 | -0.394 (1007) | 7% of 82 | -100.0% | -100.0% | -6.57 | no |
| after-10 | 1960 | 29.8% | -0.182 | -0.407 | -0.485 to -0.324 | -0.299 | -0.294 (518) | 16% of 82 | -100.0% | -100.0% | -4.46 | no |
| off-hours | 2914 | 24.4% | -0.256 | -0.541 | -0.617 to -0.453 | -0.372 | -0.446 (790) | 7% of 82 | -100.0% | -100.0% | -6.73 | no |

## All-day trades by New York hour of the trigger

| NY hour | trades | win % | avg net R |
|---|---|---|---|
| 04:00 | 449 | 24% | -0.590 |
| 05:00 | 413 | 24% | -0.552 |
| 06:00 | 356 | 23% | -0.570 |
| 07:00 | 361 | 24% | -0.586 |
| 08:00 | 396 | 29% | -0.400 |
| 09:00 | 336 | 31% | -0.351 |
| 10:00 | 314 | 30% | -0.376 |
| 11:00 | 195 | 31% | -0.369 |
| 12:00 | 157 | 32% | -0.385 |
| 13:00 | 135 | 32% | -0.405 |
| 14:00 | 114 | 30% | -0.373 |
| 15:00 | 103 | 31% | -0.320 |
| 16:00 | 72 | 26% | -0.410 |
| 17:00 | 46 | 20% | -0.694 |
| 18:00 | 57 | 21% | -0.581 |
| 19:00 | 54 | 26% | -0.446 |
| 20:00 | 66 | 23% | -0.521 |
| 21:00 | 47 | 26% | -0.463 |
| 22:00 | 36 | 17% | -0.642 |
| 23:00 | 35 | 26% | -0.529 |

## All-day: years and coins

| year | trades | avg net R |
|---|---|---|
| 2020 | 800 | -0.554 |
| 2021 | 637 | -0.689 |
| 2022 | 626 | -0.523 |
| 2023 | 433 | -0.302 |
| 2024 | 426 | -0.264 |
| 2025 | 479 | -0.372 |
| 2026 | 341 | -0.438 |

| coin | trades | avg net R |
|---|---|---|
| EUR | 3742 | -0.476 |

All-day exits: 615 target, 2372 stop, 755 at the day's end. Coin-flip direction average: -0.355 R.
