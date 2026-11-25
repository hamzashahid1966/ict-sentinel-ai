> **Market: gold (XAU/USDT perp).** Costs here are a retail forex/gold broker's, not crypto's: 0.01% per fill and 0.005% slippage, minimum stop 0.04% of price (see `research/other_markets.py`). Where the text below says 0.05% / 0.02% / 0.25%, read these values instead. Forex weekend hours removed.

# The Trading Channel two-time-frame pullback: backtest

Generated 2026-11-25 10:50 UTC. Coins: XAU.
Rules pre-registered in `research/tc_pullback.py` (2026-11-25) before any run. R = amount risked per trade. Net = after 0.05% fee per fill and 0.02% slippage. Equity = 1% risk per trade, compounding. Funding not charged.

| HTF -> entry | data | trades | win % | target (median R) | avg R gross | avg R net | 95% CI | coin-flip 95th | last third avg R | months + | 1% risk equity | max drop | Sharpe | PASS |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 15m-5m | 2025-12 to 2026-10 | 16 | 25% | 3.5 | +0.074 | -0.209 | -0.957 to +0.783 | +0.298 | -1.294 (4) | 18% of 11 | -3.6% | -6.5% | -0.55 | no |
| 1h-15m | 2025-12 to 2026-10 | 12 | 17% | 2.8 | +0.230 | +0.118 | -1.106 to +1.048 | +1.032 | +0.605 (4) | 22% of 9 | +1.0% | -5.2% | 0.13 | no |
| 4h-1h | 2025-12 to 2026-10 | 2 | 0% | 2.6 | -0.997 | -1.016 | -1.024 to -1.009 | +0.842 | +0.000 (0) | 0% of 2 | -2.0% | -2.0% | -3.21 | no |
| 1D-4h | 2025-12 to 2026-10 | 0 | | | | | | | | | | | | no |

## How many setups survive each step

| HTF -> entry | trend (2 BOS) + zone | pulled back into zone | double bottom/top + rejection candle | failed 2R / stop-width | trades |
|---|---|---|---|---|---|
| 15m-5m | 725 | 686 | 77 | 61 | 16 |
| 1h-15m | 192 | 174 | 36 | 24 | 12 |
| 4h-1h | 47 | 41 | 8 | 6 | 2 |
| 1D-4h | 12 | 12 | 2 | 2 | 0 |

## 15m-5m

Median time in a trade: 1 hours. Coin-flip direction average: -0.235 R.

| year | trades | avg net R |
|---|---|---|
| 2025 | 1 | +3.173 |
| 2026 | 15 | -0.434 |

## 1h-15m

Median time in a trade: 7 hours. Coin-flip direction average: +0.148 R.

| year | trades | avg net R |
|---|---|---|
| 2025 | 1 | -1.067 |
| 2026 | 11 | +0.226 |

## 4h-1h

Median time in a trade: 48 hours. Coin-flip direction average: -0.459 R.

| year | trades | avg net R |
|---|---|---|
| 2026 | 2 | -1.016 |
