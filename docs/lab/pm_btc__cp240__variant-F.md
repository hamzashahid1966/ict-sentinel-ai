# Lab: pm_btc (full run)

Run 2026-11-24 05:28:58 UTC. Research only: no orders are placed.

Hypothesis: Short-term 1-minute indicator signals predict the direction of the next BTC 5-minute
round better than the ~50c market price implies, by more than the 1c spread and the fee.

## Verdict: FAIL

| criterion | result | detail |
|---|---|---|
| net result > 0 | NO | -937.70 on 13825 bets of $1 (-6.78% per bet) |
| beats 95th pct of coin-flip-side controls | NO | -937.70 vs -564.82 (better than 7%) |
| last third > 0 | NO | -329.63 on 4563 bets |
| bootstrap 95% CI of mean bet > 0 (whole days resampled) | NO | (-8.51%, -5.12%) |
| >= 60% of months positive | NO | 0/7 (need 5) |
| >= 100 bets | yes | 13825 |

## Detail

Kind: polymarket | decision 240s before the close | coins BTC | 2026-05-24 .. 2026-11-23 | 52149 rounds
Params: {"variant": "F"} | file research/strategies/pm_btc_variants.py @ 6be54da8e92b
Bet: $1 at the market Up/Down price + 0.01 spread, taker fee 0.07*p*(1-p) per share, held to the outcome

| | bets | win rate | avg price paid | P&L | per bet |
|---|---|---|---|---|---|
| all | 13825 | 48.2% | 0.498 | -937.70 | -6.78% |
| first two thirds | 9262 | 47.9% | 0.494 | -608.08 | -6.57% |
| last third | 4563 | 48.7% | 0.505 | -329.63 | -7.22% |

Bet on 26.5% of rounds | UP 6602 / DOWN 7223 | win rate 48.2%
Coin-flip-side controls (200): median -779.21, 95th pct -564.82

Months: 2026-05 -24.10  2026-06 -143.67  2026-07 -101.58  2026-08 -216.76  2026-09 -195.72  2026-10 -166.18  2026-11 -89.69

By coin: BTC -937.70 (13825)

## How many tries

Full runs of 'pm_btc' with distinct code/params/coins: 7. Distinct variants of all ideas run in the lab: 15.
Every extra variant is another lottery ticket: if you try enough worthless ideas, some will pass by luck. Treat a pass found after many tries as a lead for a forward paper test, not as proof.
