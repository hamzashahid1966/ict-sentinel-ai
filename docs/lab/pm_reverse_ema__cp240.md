# Lab: pm_reverse_ema (full run)

Run 2026-11-24 06:56:34 UTC. Research only: no orders are placed.

Hypothesis: After a high-volume, high-volatility EMA9/21 cross that leaves price more than one ATR
beyond EMA50, the next 5-minute candle reverses more often than the ~50c Polymarket price implies,
by more than the spread and fee.

## Verdict: FAIL

| criterion | result | detail |
|---|---|---|
| net result > 0 | yes | +2.33 on 257 bets of $1 (+0.90% per bet) |
| beats 95th pct of coin-flip-side controls | NO | +2.33 vs +9.32 (better than 90%) |
| last third > 0 | yes | +9.54 on 82 bets |
| bootstrap 95% CI of mean bet > 0 (whole days resampled) | NO | (-12.43%, +14.11%) |
| >= 60% of months positive | NO | 2/7 (need 5) |
| >= 100 bets | yes | 257 |

## Detail

Kind: polymarket | decision 240s before the close | coins BTC | 2026-05-24 .. 2026-11-23 | 52149 rounds
Params: {} | file research/strategies/pm_reverse_ema.py @ 67e2d3a9ceb1
Bet: $1 at the market Up/Down price + 0.01 spread, taker fee 0.07*p*(1-p) per share, held to the outcome

| | bets | win rate | avg price paid | P&L | per bet |
|---|---|---|---|---|---|
| all | 257 | 53.7% | 0.513 | +2.33 | +0.90% |
| first two thirds | 175 | 51.4% | 0.521 | -7.21 | -4.12% |
| last third | 82 | 58.5% | 0.497 | +9.54 | +11.63% |

Bet on 0.5% of rounds | UP 118 / DOWN 139 | win rate 53.7%
Coin-flip-side controls (200): median -17.70, 95th pct +9.32

Months: 2026-05 -2.62  2026-06 -3.49  2026-07 -7.50  2026-08 -6.01  2026-09 +14.99  2026-10 +7.94  2026-11 -0.98

By coin: BTC +2.33 (257)

## How many tries

Full runs of 'pm_reverse_ema' with distinct code/params/coins: 1. Distinct variants of all ideas run in the lab: 17.
Every extra variant is another lottery ticket: if you try enough worthless ideas, some will pass by luck. Treat a pass found after many tries as a lead for a forward paper test, not as proof.
