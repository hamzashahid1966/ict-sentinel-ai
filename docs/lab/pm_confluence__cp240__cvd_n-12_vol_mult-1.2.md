# Lab: pm_confluence (full run)

Run 2026-11-24 05:26:24 UTC. Research only: no orders are placed.

Hypothesis: At the start of a round, when the 1-minute momentum, trend, VWAP side, order flow,
candle close, volume and volatility all agree, that side wins more often than its ~50c price
implies, by more than the spread and fee.

## Verdict: FAIL

| criterion | result | detail |
|---|---|---|
| net result > 0 | NO | -919.62 on 9353 bets of $1 (-9.83% per bet) |
| beats 95th pct of coin-flip-side controls | NO | -919.62 vs -295.05 (better than 0%) |
| last third > 0 | NO | -304.45 on 2948 bets |
| bootstrap 95% CI of mean bet > 0 (whole days resampled) | NO | (-11.96%, -7.67%) |
| >= 60% of months positive | NO | 0/7 (need 5) |
| >= 100 bets | yes | 9353 |

## Detail

Kind: polymarket | decision 240s before the close | coins BTC, ETH, SOL, XRP | 2026-05-24 .. 2026-11-23 | 208586 rounds
Params: {"cvd_n": 12, "vol_mult": 1.2} | file research/strategies/pm_confluence.py @ 259511c6ccd1
Bet: $1 at the market Up/Down price + 0.01 spread, taker fee 0.07*p*(1-p) per share, held to the outcome

| | bets | win rate | avg price paid | P&L | per bet |
|---|---|---|---|---|---|
| all | 9353 | 51.4% | 0.551 | -919.62 | -9.83% |
| first two thirds | 6405 | 49.4% | 0.527 | -615.17 | -9.60% |
| last third | 2948 | 55.8% | 0.603 | -304.45 | -10.33% |

Bet on 4.5% of rounds | UP 4517 / DOWN 4836 | win rate 51.4%
Coin-flip-side controls (200): median -440.54, 95th pct -295.05

Months: 2026-05 -31.05  2026-06 -171.51  2026-07 -125.09  2026-08 -171.65  2026-09 -187.19  2026-10 -185.21  2026-11 -47.92

By coin: BTC -199.22 (2565)  ETH -284.28 (2559)  SOL -253.17 (2280)  XRP -182.94 (1949)

## How many tries

Full runs of 'pm_confluence' with distinct code/params/coins: 1. Distinct variants of all ideas run in the lab: 8.
Every extra variant is another lottery ticket: if you try enough worthless ideas, some will pass by luck. Treat a pass found after many tries as a lead for a forward paper test, not as proof.
