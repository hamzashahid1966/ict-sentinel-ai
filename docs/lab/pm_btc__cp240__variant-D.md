# Lab: pm_btc (full run)

Run 2026-11-24 05:28:58 UTC. Research only: no orders are placed.

Hypothesis: Short-term 1-minute indicator signals predict the direction of the next BTC 5-minute
round better than the ~50c market price implies, by more than the 1c spread and the fee.

## Verdict: FAIL

| criterion | result | detail |
|---|---|---|
| net result > 0 | NO | -2828.78 on 45441 bets of $1 (-6.23% per bet) |
| beats 95th pct of coin-flip-side controls | NO | -2828.78 vs -2240.52 (better than 18%) |
| last third > 0 | NO | -999.17 on 14929 bets |
| bootstrap 95% CI of mean bet > 0 (whole days resampled) | NO | (-7.10%, -5.41%) |
| >= 60% of months positive | NO | 0/7 (need 5) |
| >= 100 bets | yes | 45441 |

## Detail

Kind: polymarket | decision 240s before the close | coins BTC | 2026-05-24 .. 2026-11-23 | 52149 rounds
Params: {"variant": "D"} | file research/strategies/pm_btc_variants.py @ 6be54da8e92b
Bet: $1 at the market Up/Down price + 0.01 spread, taker fee 0.07*p*(1-p) per share, held to the outcome

| | bets | win rate | avg price paid | P&L | per bet |
|---|---|---|---|---|---|
| all | 45441 | 49.5% | 0.508 | -2828.78 | -6.23% |
| first two thirds | 30512 | 49.1% | 0.503 | -1829.61 | -6.00% |
| last third | 14929 | 50.3% | 0.517 | -999.17 | -6.69% |

Bet on 87.1% of rounds | UP 22578 / DOWN 22863 | win rate 49.5%
Coin-flip-side controls (200): median -2602.99, 95th pct -2240.52

Months: 2026-05 -74.43  2026-06 -471.98  2026-07 -374.91  2026-08 -550.57  2026-09 -453.33  2026-10 -505.01  2026-11 -398.55

By coin: BTC -2828.78 (45441)

## How many tries

Full runs of 'pm_btc' with distinct code/params/coins: 8. Distinct variants of all ideas run in the lab: 16.
Every extra variant is another lottery ticket: if you try enough worthless ideas, some will pass by luck. Treat a pass found after many tries as a lead for a forward paper test, not as proof.
