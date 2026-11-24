# Lab: pm_btc (full run)

Run 2026-11-24 05:28:57 UTC. Research only: no orders are placed.

Hypothesis: Short-term 1-minute indicator signals predict the direction of the next BTC 5-minute
round better than the ~50c market price implies, by more than the 1c spread and the fee.

## Verdict: FAIL

| criterion | result | detail |
|---|---|---|
| net result > 0 | NO | -2210.11 on 35112 bets of $1 (-6.29% per bet) |
| beats 95th pct of coin-flip-side controls | NO | -2210.11 vs -1693.83 (better than 16%) |
| last third > 0 | NO | -845.67 on 11326 bets |
| bootstrap 95% CI of mean bet > 0 (whole days resampled) | NO | (-7.25%, -5.38%) |
| >= 60% of months positive | NO | 0/7 (need 5) |
| >= 100 bets | yes | 35112 |

## Detail

Kind: polymarket | decision 240s before the close | coins BTC | 2026-05-24 .. 2026-11-23 | 52149 rounds
Params: {"variant": "G"} | file research/strategies/pm_btc_variants.py @ 6be54da8e92b
Bet: $1 at the market Up/Down price + 0.01 spread, taker fee 0.07*p*(1-p) per share, held to the outcome

| | bets | win rate | avg price paid | P&L | per bet |
|---|---|---|---|---|---|
| all | 35112 | 49.2% | 0.504 | -2210.11 | -6.29% |
| first two thirds | 23786 | 49.1% | 0.501 | -1364.44 | -5.74% |
| last third | 11326 | 49.5% | 0.511 | -845.67 | -7.47% |

Bet on 67.3% of rounds | UP 17405 / DOWN 17707 | win rate 49.2%
Coin-flip-side controls (200): median -2003.96, 95th pct -1693.83

Months: 2026-05 -84.69  2026-06 -345.24  2026-07 -250.20  2026-08 -414.51  2026-09 -358.90  2026-10 -384.37  2026-11 -372.20

By coin: BTC -2210.11 (35112)

## How many tries

Full runs of 'pm_btc' with distinct code/params/coins: 2. Distinct variants of all ideas run in the lab: 10.
Every extra variant is another lottery ticket: if you try enough worthless ideas, some will pass by luck. Treat a pass found after many tries as a lead for a forward paper test, not as proof.
