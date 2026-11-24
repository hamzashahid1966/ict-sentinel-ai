# Lab: pm_btc (full run)

Run 2026-11-24 05:28:57 UTC. Research only: no orders are placed.

Hypothesis: Short-term 1-minute indicator signals predict the direction of the next BTC 5-minute
round better than the ~50c market price implies, by more than the 1c spread and the fee.

## Verdict: FAIL

| criterion | result | detail |
|---|---|---|
| net result > 0 | NO | -3150.22 on 52107 bets of $1 (-6.05% per bet) |
| beats 95th pct of coin-flip-side controls | NO | -3150.22 vs -2608.83 (better than 27%) |
| last third > 0 | NO | -1186.71 on 17153 bets |
| bootstrap 95% CI of mean bet > 0 (whole days resampled) | NO | (-6.84%, -5.23%) |
| >= 60% of months positive | NO | 0/7 (need 5) |
| >= 100 bets | yes | 52107 |

## Detail

Kind: polymarket | decision 240s before the close | coins BTC | 2026-05-24 .. 2026-11-23 | 52149 rounds
Params: {"variant": "A"} | file research/strategies/pm_btc_variants.py @ 6be54da8e92b
Bet: $1 at the market Up/Down price + 0.01 spread, taker fee 0.07*p*(1-p) per share, held to the outcome

| | bets | win rate | avg price paid | P&L | per bet |
|---|---|---|---|---|---|
| all | 52107 | 49.5% | 0.507 | -3150.22 | -6.05% |
| first two thirds | 34954 | 49.4% | 0.504 | -1963.51 | -5.62% |
| last third | 17153 | 49.9% | 0.513 | -1186.71 | -6.92% |

Bet on 99.9% of rounds | UP 25783 / DOWN 26324 | win rate 49.5%
Coin-flip-side controls (200): median -3001.18, 95th pct -2608.83

Months: 2026-05 -54.39  2026-06 -443.71  2026-07 -462.65  2026-08 -554.10  2026-09 -589.26  2026-10 -602.57  2026-11 -443.54

By coin: BTC -3150.22 (52107)

## How many tries

Full runs of 'pm_btc' with distinct code/params/coins: 3. Distinct variants of all ideas run in the lab: 11.
Every extra variant is another lottery ticket: if you try enough worthless ideas, some will pass by luck. Treat a pass found after many tries as a lead for a forward paper test, not as proof.
