> **Market: EUR/USD (EUR/USDT).** Costs here are a retail forex/gold broker's, not crypto's: 0.01% per fill and 0.005% slippage, minimum stop 0.04% of price (see `research/other_markets.py`). Where the text below says 0.05% / 0.02% / 0.25%, read these values instead. Forex weekend hours removed.

# Trader Mayne ICT framework: backtest

Generated 2026-11-25 10:50 UTC. Coins: EUR.
Rules pre-registered in `research/ict_mayne.py` (2026-11-25) from the pre-trade checklist, before any run.
R = the amount risked on a trade (entry to stop). Net = after 0.05% fees per fill and 0.02% slippage.
Equity = risking 1% of the account per trade, compounding. Funding is not charged.

| variant | data | trades | win % | avg R gross | avg R net | 95% CI | coin-flip 95th | holdout avg R | months + | 1% risk equity | max drop | PASS |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| W-D market | 2020-01 to 2026-10 | 0 | | | | | | | | | | no |
| W-D breaker | 2020-01 to 2026-10 | 0 | | | | | | | | | | no |
| D-1h market | 2020-01 to 2026-10 | 8 | 12% | -0.228 | -0.375 | -1.197 to +1.135 | +1.223 | -1.170 (4) | 12% of 8 | -3.1% | -6.6% | no |
| D-1h breaker | 2020-01 to 2026-10 | 9 | 11% | -0.142 | -0.230 | -1.083 to +1.455 | +0.622 | -1.091 (4) | 11% of 9 | -2.3% | -6.3% | no |
| 4h-15m market | 2020-01 to 2026-10 | 32 | 44% | +0.338 | +0.110 | -0.420 to +0.696 | -0.009 | +0.441 (11) | 44% of 25 | +3.1% | -9.8% | no |
| 4h-15m breaker | 2020-01 to 2026-10 | 38 | 29% | +0.079 | -0.140 | -0.663 to +0.464 | +0.148 | -0.344 (14) | 30% of 30 | -5.8% | -10.2% | no |

## How many setups survive each checklist step

| variant | HTF trend + MSB | valid POI in discount/premium | price tapped POI | LTF sweep + MSS | failed 2R / stop-width check | breaker retest missed | trades |
|---|---|---|---|---|---|---|---|
| W-D market | 18 | 9 | 7 | 2 | 2 | 0 | 0 |
| W-D breaker | 18 | 9 | 7 | 1 | 0 | 1 | 0 |
| D-1h market | 94 | 50 | 33 | 32 | 24 | 0 | 8 |
| D-1h breaker | 92 | 49 | 32 | 27 | 18 | 0 | 9 |
| 4h-15m market | 428 | 265 | 194 | 102 | 70 | 0 | 32 |
| 4h-15m breaker | 429 | 267 | 196 | 95 | 40 | 17 | 38 |

## D-1h market

- Exits: 1 reached the target, 7 stopped (some after taking half at 2R), 0 still open at the end.
- Longs: 4 trades, avg +0.404 R. Shorts: 4 trades, avg -1.155 R.
- Median time in a trade: 16 hours. Coin-flip direction average: +0.270 R.
- Checks (CI > 0, beats coin flip, holdout > 0, months >= 55%): no, no, no, no

| year | trades | net R |
|---|---|---|
| 2021 | 1 | -1.1 |
| 2023 | 1 | +4.8 |
| 2024 | 3 | -3.2 |
| 2025 | 1 | -1.1 |
| 2026 | 2 | -2.5 |

| coin | trades | net R |
|---|---|---|
| EUR | 8 | -3.0 |

## D-1h breaker

- Exits: 1 reached the target, 8 stopped (some after taking half at 2R), 0 still open at the end.
- Longs: 4 trades, avg +0.820 R. Shorts: 5 trades, avg -1.070 R.
- Median time in a trade: 18 hours. Coin-flip direction average: -0.086 R.
- Checks (CI > 0, beats coin flip, holdout > 0, months >= 55%): no, no, no, no

| year | trades | net R |
|---|---|---|
| 2020 | 1 | -1.0 |
| 2021 | 1 | -1.1 |
| 2023 | 1 | +6.5 |
| 2024 | 3 | -3.2 |
| 2025 | 1 | -1.1 |
| 2026 | 2 | -2.2 |

| coin | trades | net R |
|---|---|---|
| EUR | 9 | -2.1 |

## 4h-15m market

- Exits: 9 reached the target, 23 stopped (some after taking half at 2R), 0 still open at the end.
- Longs: 18 trades, avg +0.457 R. Shorts: 14 trades, avg -0.337 R.
- Median time in a trade: 6 hours. Coin-flip direction average: -0.276 R.
- Checks (CI > 0, beats coin flip, holdout > 0, months >= 55%): no, yes, yes, no

| year | trades | net R |
|---|---|---|
| 2020 | 5 | -0.4 |
| 2021 | 3 | -0.3 |
| 2022 | 5 | -4.5 |
| 2023 | 4 | -1.3 |
| 2024 | 7 | +9.3 |
| 2025 | 4 | -3.3 |
| 2026 | 4 | +4.1 |

| coin | trades | net R |
|---|---|---|
| EUR | 32 | +3.5 |

## 4h-15m breaker

- Exits: 7 reached the target, 31 stopped (some after taking half at 2R), 0 still open at the end.
- Longs: 21 trades, avg +0.097 R. Shorts: 17 trades, avg -0.432 R.
- Median time in a trade: 3 hours. Coin-flip direction average: -0.212 R.
- Checks (CI > 0, beats coin flip, holdout > 0, months >= 55%): no, no, no, no

| year | trades | net R |
|---|---|---|
| 2020 | 7 | -1.4 |
| 2021 | 3 | -2.4 |
| 2022 | 6 | +0.5 |
| 2023 | 6 | +0.4 |
| 2024 | 5 | +4.0 |
| 2025 | 7 | -7.2 |
| 2026 | 4 | +0.9 |

| coin | trades | net R |
|---|---|---|
| EUR | 38 | -5.3 |
