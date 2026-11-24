# Lab: pm_btc (full run)

Run 2026-11-24 05:28:57 UTC. Research only: no orders are placed.

Hypothesis: Short-term 1-minute indicator signals predict the direction of the next BTC 5-minute
round better than the ~50c market price implies, by more than the 1c spread and the fee.

## Verdict: FAIL

| criterion | result | detail |
|---|---|---|
| net result > 0 | NO | -3207.29 on 52107 bets of $1 (-6.16% per bet) |
| beats 95th pct of coin-flip-side controls | NO | -3207.29 vs -2613.62 (better than 12%) |
| last third > 0 | NO | -1146.36 on 17153 bets |
| bootstrap 95% CI of mean bet > 0 (whole days resampled) | NO | (-6.98%, -5.37%) |
| >= 60% of months positive | NO | 0/7 (need 5) |
| >= 100 bets | yes | 52107 |

## Detail

Kind: polymarket | decision 240s before the close | coins BTC | 2026-05-24 .. 2026-11-23 | 52149 rounds
Params: {"variant": "B"} | file research/strategies/pm_btc_variants.py @ 6be54da8e92b
Bet: $1 at the market Up/Down price + 0.01 spread, taker fee 0.07*p*(1-p) per share, held to the outcome

| | bets | win rate | avg price paid | P&L | per bet |
|---|---|---|---|---|---|
| all | 52107 | 49.2% | 0.503 | -3207.29 | -6.16% |
| first two thirds | 34954 | 49.0% | 0.502 | -2060.93 | -5.90% |
| last third | 17153 | 49.4% | 0.507 | -1146.36 | -6.68% |

Bet on 99.9% of rounds | UP 25862 / DOWN 26245 | win rate 49.2%
Coin-flip-side controls (200): median -2980.83, 95th pct -2613.62

Months: 2026-05 -79.67  2026-06 -495.23  2026-07 -430.44  2026-08 -615.88  2026-09 -556.19  2026-10 -556.88  2026-11 -473.00

By coin: BTC -3207.29 (52107)

## How many tries

Full runs of 'pm_btc' with distinct code/params/coins: 4. Distinct variants of all ideas run in the lab: 12.
Every extra variant is another lottery ticket: if you try enough worthless ideas, some will pass by luck. Treat a pass found after many tries as a lead for a forward paper test, not as proof.
