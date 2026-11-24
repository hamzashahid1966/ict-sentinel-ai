# Lab: pm_btc (full run)

Run 2026-11-24 05:28:58 UTC. Research only: no orders are placed.

Hypothesis: Short-term 1-minute indicator signals predict the direction of the next BTC 5-minute
round better than the ~50c market price implies, by more than the 1c spread and the fee.

## Verdict: FAIL

| criterion | result | detail |
|---|---|---|
| net result > 0 | NO | -2967.52 on 46083 bets of $1 (-6.44% per bet) |
| beats 95th pct of coin-flip-side controls | NO | -2967.52 vs -2293.32 (better than 6%) |
| last third > 0 | NO | -1050.43 on 15168 bets |
| bootstrap 95% CI of mean bet > 0 (whole days resampled) | NO | (-7.35%, -5.61%) |
| >= 60% of months positive | NO | 0/7 (need 5) |
| >= 100 bets | yes | 46083 |

## Detail

Kind: polymarket | decision 240s before the close | coins BTC | 2026-05-24 .. 2026-11-23 | 52149 rounds
Params: {"variant": "C"} | file research/strategies/pm_btc_variants.py @ 6be54da8e92b
Bet: $1 at the market Up/Down price + 0.01 spread, taker fee 0.07*p*(1-p) per share, held to the outcome

| | bets | win rate | avg price paid | P&L | per bet |
|---|---|---|---|---|---|
| all | 46083 | 49.2% | 0.506 | -2967.52 | -6.44% |
| first two thirds | 30915 | 48.9% | 0.502 | -1917.09 | -6.20% |
| last third | 15168 | 49.8% | 0.513 | -1050.43 | -6.93% |

Bet on 88.4% of rounds | UP 22920 / DOWN 23163 | win rate 49.2%
Coin-flip-side controls (200): median -2633.55, 95th pct -2293.32

Months: 2026-05 -71.33  2026-06 -472.07  2026-07 -392.35  2026-08 -577.67  2026-09 -523.53  2026-10 -518.23  2026-11 -412.33

By coin: BTC -2967.52 (46083)

## How many tries

Full runs of 'pm_btc' with distinct code/params/coins: 6. Distinct variants of all ideas run in the lab: 14.
Every extra variant is another lottery ticket: if you try enough worthless ideas, some will pass by luck. Treat a pass found after many tries as a lead for a forward paper test, not as proof.
