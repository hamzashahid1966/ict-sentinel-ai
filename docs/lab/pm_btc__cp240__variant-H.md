# Lab: pm_btc (full run)

Run 2026-11-24 05:28:57 UTC. Research only: no orders are placed.

Hypothesis: Short-term 1-minute indicator signals predict the direction of the next BTC 5-minute
round better than the ~50c market price implies, by more than the 1c spread and the fee.

## Verdict: FAIL

| criterion | result | detail |
|---|---|---|
| net result > 0 | NO | -88.55 on 1696 bets of $1 (-5.22% per bet) |
| beats 95th pct of coin-flip-side controls | NO | -88.55 vs -31.63 (better than 54%) |
| last third > 0 | NO | -22.88 on 567 bets |
| bootstrap 95% CI of mean bet > 0 (whole days resampled) | NO | (-9.95%, -0.84%) |
| >= 60% of months positive | NO | 2/7 (need 5) |
| >= 100 bets | yes | 1696 |

## Detail

Kind: polymarket | decision 240s before the close | coins BTC | 2026-05-24 .. 2026-11-23 | 52149 rounds
Params: {"variant": "H"} | file research/strategies/pm_btc_variants.py @ 6be54da8e92b
Bet: $1 at the market Up/Down price + 0.01 spread, taker fee 0.07*p*(1-p) per share, held to the outcome

| | bets | win rate | avg price paid | P&L | per bet |
|---|---|---|---|---|---|
| all | 1696 | 54.8% | 0.557 | -88.55 | -5.22% |
| first two thirds | 1129 | 53.1% | 0.543 | -65.67 | -5.82% |
| last third | 567 | 58.2% | 0.587 | -22.88 | -4.04% |

Bet on 3.3% of rounds | UP 920 / DOWN 776 | win rate 54.8%
Coin-flip-side controls (200): median -94.32, 95th pct -31.63

Months: 2026-05 +0.25  2026-06 -15.09  2026-07 -14.70  2026-08 -23.05  2026-09 -7.68  2026-10 -29.38  2026-11 +1.09

By coin: BTC -88.55 (1696)

## How many tries

Full runs of 'pm_btc' with distinct code/params/coins: 1. Distinct variants of all ideas run in the lab: 9.
Every extra variant is another lottery ticket: if you try enough worthless ideas, some will pass by luck. Treat a pass found after many tries as a lead for a forward paper test, not as proof.
