# Lab: pm_cheap_momentum (full run)

Run 2026-11-24 05:24:01 UTC. Research only: no orders are placed.

Hypothesis: With two minutes left, if the USD price (Coinbase) is already 0.05% past the start price, the market
underprices that side when it still costs under 70c.

## Verdict: FAIL

| criterion | result | detail |
|---|---|---|
| net result > 0 | NO | -11.26 on 9528 bets of $1 (-0.12% per bet) |
| beats 95th pct of coin-flip-side controls | yes | -11.26 vs -358.49 (better than 100%) |
| last third > 0 | NO | -110.78 on 2944 bets |
| bootstrap 95% CI of mean bet > 0 (whole days resampled) | NO | (-3.52%, +3.46%) |
| >= 60% of months positive | NO | 4/7 (need 5) |
| >= 100 bets | yes | 9528 |

## Detail

Kind: polymarket | decision 120s before the close | coins BTC, ETH, SOL, XRP | 2026-05-24 .. 2026-11-23 | 208098 rounds
Params: {"min_move": 0.0005, "max_price": 0.7} | file research/strategies/pm_cheap_momentum.py @ 0e917d1008ab
Bet: $1 at the market Up/Down price + 0.01 spread, taker fee 0.07*p*(1-p) per share, held to the outcome

| | bets | win rate | avg price paid | P&L | per bet |
|---|---|---|---|---|---|
| all | 9528 | 63.1% | 0.621 | -11.26 | -0.12% |
| first two thirds | 6584 | 64.4% | 0.625 | +99.52 | +1.51% |
| last third | 2944 | 60.3% | 0.612 | -110.78 | -3.76% |

Bet on 4.6% of rounds | UP 4556 / DOWN 4972 | win rate 63.1%
Coin-flip-side controls (200): median -495.10, 95th pct -358.49

Months: 2026-05 +22.69  2026-06 -181.67  2026-07 -39.89  2026-08 +132.84  2026-09 +127.43  2026-10 -75.27  2026-11 +2.60

By coin: BTC +23.00 (1439)  ETH +16.24 (2097)  SOL -12.29 (3212)  XRP -38.20 (2780)

## How many tries

Full runs of 'pm_cheap_momentum' with distinct code/params/coins: 2. Distinct variants of all ideas run in the lab: 4.
Every extra variant is another lottery ticket: if you try enough worthless ideas, some will pass by luck. Treat a pass found after many tries as a lead for a forward paper test, not as proof.
