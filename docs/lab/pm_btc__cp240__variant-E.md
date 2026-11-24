# Lab: pm_btc (full run)

Run 2026-11-24 05:28:58 UTC. Research only: no orders are placed.

Hypothesis: Short-term 1-minute indicator signals predict the direction of the next BTC 5-minute
round better than the ~50c market price implies, by more than the 1c spread and the fee.

## Verdict: FAIL

| criterion | result | detail |
|---|---|---|
| net result > 0 | NO | -2409.18 on 35940 bets of $1 (-6.70% per bet) |
| beats 95th pct of coin-flip-side controls | NO | -2409.18 vs -1679.66 (better than 0%) |
| last third > 0 | NO | -852.99 on 11852 bets |
| bootstrap 95% CI of mean bet > 0 (whole days resampled) | NO | (-7.74%, -5.70%) |
| >= 60% of months positive | NO | 0/7 (need 5) |
| >= 100 bets | yes | 35940 |

## Detail

Kind: polymarket | decision 240s before the close | coins BTC | 2026-05-24 .. 2026-11-23 | 52149 rounds
Params: {"variant": "E"} | file research/strategies/pm_btc_variants.py @ 6be54da8e92b
Bet: $1 at the market Up/Down price + 0.01 spread, taker fee 0.07*p*(1-p) per share, held to the outcome

| | bets | win rate | avg price paid | P&L | per bet |
|---|---|---|---|---|---|
| all | 35940 | 48.7% | 0.502 | -2409.18 | -6.70% |
| first two thirds | 24088 | 48.5% | 0.499 | -1556.19 | -6.46% |
| last third | 11852 | 49.0% | 0.507 | -852.99 | -7.20% |

Bet on 68.9% of rounds | UP 18049 / DOWN 17891 | win rate 48.7%
Coin-flip-side controls (200): median -2001.56, 95th pct -1679.66

Months: 2026-05 -53.13  2026-06 -382.72  2026-07 -332.77  2026-08 -419.51  2026-09 -468.23  2026-10 -443.66  2026-11 -309.16

By coin: BTC -2409.18 (35940)

## How many tries

Full runs of 'pm_btc' with distinct code/params/coins: 5. Distinct variants of all ideas run in the lab: 13.
Every extra variant is another lottery ticket: if you try enough worthless ideas, some will pass by luck. Treat a pass found after many tries as a lead for a forward paper test, not as proof.
