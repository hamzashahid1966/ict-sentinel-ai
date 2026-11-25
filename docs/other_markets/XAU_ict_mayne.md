> **Market: gold (XAU/USDT perp).** Costs here are a retail forex/gold broker's, not crypto's: 0.01% per fill and 0.005% slippage, minimum stop 0.04% of price (see `research/other_markets.py`). Where the text below says 0.05% / 0.02% / 0.25%, read these values instead. Forex weekend hours removed.

# Trader Mayne ICT framework: backtest

Generated 2026-11-25 10:50 UTC. Coins: XAU.
Rules pre-registered in `research/ict_mayne.py` (2026-11-25) from the pre-trade checklist, before any run.
R = the amount risked on a trade (entry to stop). Net = after 0.05% fees per fill and 0.02% slippage.
Equity = risking 1% of the account per trade, compounding. Funding is not charged.

| variant | data | trades | win % | avg R gross | avg R net | 95% CI | coin-flip 95th | holdout avg R | months + | 1% risk equity | max drop | PASS |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| W-D market | 2025-12 to 2026-10 | 0 | | | | | | | | | | no |
| W-D breaker | 2025-12 to 2026-10 | 0 | | | | | | | | | | no |
| D-1h market | 2025-12 to 2026-10 | 3 | 33% | +0.134 | +0.116 | -1.016 to +0.681 | +0.116 | -1.016 (1) | 50% of 2 | +0.3% | -1.0% | no |
| D-1h breaker | 2025-12 to 2026-10 | 2 | 0% | -1.000 | -1.026 | -1.032 to -1.020 | -0.274 | -1.020 (1) | 0% of 2 | -2.0% | -2.0% | no |
| 4h-15m market | 2025-12 to 2026-10 | 4 | 0% | -0.984 | -1.081 | -1.164 to -1.047 | +0.531 | +0.000 (0) | 0% of 3 | -4.3% | -4.3% | no |
| 4h-15m breaker | 2025-12 to 2026-10 | 6 | 33% | -0.243 | -0.309 | -1.098 to +0.086 | -0.309 | +0.000 (0) | 25% of 4 | -1.9% | -4.3% | no |

## How many setups survive each checklist step

| variant | HTF trend + MSB | valid POI in discount/premium | price tapped POI | LTF sweep + MSS | failed 2R / stop-width check | breaker retest missed | trades |
|---|---|---|---|---|---|---|---|
| W-D market | 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| W-D breaker | 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| D-1h market | 11 | 8 | 6 | 3 | 0 | 0 | 3 |
| D-1h breaker | 11 | 8 | 6 | 5 | 1 | 2 | 2 |
| 4h-15m market | 73 | 41 | 17 | 12 | 8 | 0 | 4 |
| 4h-15m breaker | 73 | 41 | 17 | 9 | 3 | 0 | 6 |

## D-1h market

- Exits: 1 reached the target, 2 stopped (some after taking half at 2R), 0 still open at the end.
- Longs: 1 trades, avg +2.369 R. Shorts: 2 trades, avg -1.011 R.
- Median time in a trade: 136 hours. Coin-flip direction average: -0.507 R.
- Checks (CI > 0, beats coin flip, holdout > 0, months >= 55%): no, no, no, no

| year | trades | net R |
|---|---|---|
| 2026 | 3 | +0.3 |

| coin | trades | net R |
|---|---|---|
| XAU | 3 | +0.3 |

## D-1h breaker

- Exits: 0 reached the target, 2 stopped (some after taking half at 2R), 0 still open at the end.
- Longs: 0 trades, avg +0.000 R. Shorts: 2 trades, avg -1.026 R.
- Median time in a trade: 76 hours. Coin-flip direction average: -0.462 R.
- Checks (CI > 0, beats coin flip, holdout > 0, months >= 55%): no, no, no, no

| year | trades | net R |
|---|---|---|
| 2026 | 2 | -2.1 |

| coin | trades | net R |
|---|---|---|
| XAU | 2 | -2.1 |

## 4h-15m market

- Exits: 0 reached the target, 4 stopped (some after taking half at 2R), 0 still open at the end.
- Longs: 1 trades, avg -1.044 R. Shorts: 3 trades, avg -1.093 R.
- Median time in a trade: 3 hours. Coin-flip direction average: -0.042 R.
- Checks (CI > 0, beats coin flip, holdout > 0, months >= 55%): no, no, no, no

| year | trades | net R |
|---|---|---|
| 2026 | 4 | -4.3 |

| coin | trades | net R |
|---|---|---|
| XAU | 4 | -4.3 |

## 4h-15m breaker

- Exits: 1 reached the target, 5 stopped (some after taking half at 2R), 0 still open at the end.
- Longs: 3 trades, avg +0.474 R. Shorts: 3 trades, avg -1.092 R.
- Median time in a trade: 8 hours. Coin-flip direction average: -0.651 R.
- Checks (CI > 0, beats coin flip, holdout > 0, months >= 55%): no, no, no, no

| year | trades | net R |
|---|---|---|
| 2026 | 6 | -1.9 |

| coin | trades | net R |
|---|---|---|
| XAU | 6 | -1.9 |
