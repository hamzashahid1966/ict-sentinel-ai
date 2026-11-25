> **Market: gold (XAU/USDT perp).** Costs here are a retail forex/gold broker's, not crypto's: 0.01% per fill and 0.005% slippage, minimum stop 0.04% of price (see `research/other_markets.py`). Where the text below says 0.05% / 0.02% / 0.25%, read these values instead. Forex weekend hours removed.

# 4-hour range + 5-minute re-entry: backtest

Generated 2026-11-25 10:50 UTC. 5-minute candles, 2025-12 to 2026-10. Coins: XAU.
Rules pre-registered in `research/range_reentry.py` (2026-11-25) before any run. R = amount risked per trade. Net = after 0.05% fee per fill and 0.02% slippage. Equity = 1% risk per trade, compounding.

| variant | trades | win % | avg R gross | avg R net | 95% CI | coin-flip 95th | last third avg R | months + | 1% risk equity | max drop | Sharpe | PASS |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| all-day | 500 | 31.8% | -0.115 | -0.248 | -0.354 to -0.160 | -0.073 | -0.112 (164) | 0% of 11 | -72.2% | -72.4% | -4.83 | no |
| skip-open | 484 | 32.9% | -0.076 | -0.217 | -0.320 to -0.130 | -0.060 | -0.144 (160) | 0% of 11 | -66.4% | -67.0% | -4.14 | no |
| after-10 | 249 | 35.7% | -0.083 | -0.180 | -0.306 to -0.075 | -0.046 | -0.099 (85) | 18% of 11 | -37.1% | -37.4% | -2.73 | no |
| off-hours | 400 | 32.8% | -0.067 | -0.230 | -0.342 to -0.135 | -0.002 | -0.161 (135) | 9% of 11 | -61.5% | -61.5% | -4.05 | no |

## All-day trades by New York hour of the trigger

| NY hour | trades | win % | avg net R |
|---|---|---|---|
| 04:00 | 68 | 37% | -0.092 |
| 05:00 | 42 | 31% | -0.245 |
| 06:00 | 48 | 35% | -0.091 |
| 07:00 | 41 | 20% | -0.561 |
| 08:00 | 60 | 25% | -0.367 |
| 09:00 | 49 | 27% | -0.325 |
| 10:00 | 49 | 33% | -0.269 |
| 11:00 | 22 | 50% | +0.115 |
| 12:00 | 22 | 27% | -0.278 |
| 13:00 | 16 | 6% | -0.920 |
| 14:00 | 11 | 27% | -0.548 |
| 15:00 | 8 | 25% | -0.247 |
| 16:00 | 4 | 25% | -0.609 |
| 17:00 | 2 | 0% | -0.952 |
| 18:00 | 5 | 80% | +0.572 |
| 19:00 | 12 | 50% | +0.101 |
| 20:00 | 11 | 55% | -0.056 |
| 21:00 | 17 | 35% | -0.215 |
| 22:00 | 11 | 45% | +0.152 |
| 23:00 | 2 | 50% | +0.096 |

## All-day: years and coins

| year | trades | avg net R |
|---|---|---|
| 2025 | 30 | -0.556 |
| 2026 | 470 | -0.228 |

| coin | trades | avg net R |
|---|---|---|
| XAU | 500 | -0.248 |

All-day exits: 107 target, 292 stop, 101 at the day's end. Coin-flip direction average: -0.142 R.
