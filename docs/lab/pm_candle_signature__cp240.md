# Lab: pm_candle_signature (full run)

Run 2026-11-24 07:51:00 UTC. Research only: no orders are placed.

Hypothesis: The closure signature of the 5-minute candle that just closed predicts the next
5-minute round better than the ~50c Polymarket price implies, by more than the spread and fee.

## Verdict: FAIL

| criterion | result | detail |
|---|---|---|
| net result > 0 | NO | -10595.33 on 167890 bets of $1 (-6.31% per bet) |
| beats 95th pct of coin-flip-side controls | NO | -10595.33 vs -8349.66 (better than 0%) |
| last third > 0 | NO | -3587.67 on 55462 bets |
| bootstrap 95% CI of mean bet > 0 (whole days resampled) | NO | (-6.96%, -5.70%) |
| >= 60% of months positive | NO | 0/7 (need 5) |
| >= 100 bets | yes | 167890 |

## Detail

Kind: polymarket | decision 240s before the close | coins BTC, ETH, SOL, XRP | 2026-05-24 .. 2026-11-23 | 208586 rounds
Params: {} | file research/strategies/pm_candle_signature.py @ d286a5730832
Bet: $1 at the market Up/Down price + 0.01 spread, taker fee 0.07*p*(1-p) per share, held to the outcome

| | bets | win rate | avg price paid | P&L | per bet |
|---|---|---|---|---|---|
| all | 167890 | 51.1% | 0.526 | -10595.33 | -6.31% |
| first two thirds | 112428 | 50.2% | 0.517 | -7007.66 | -6.23% |
| last third | 55462 | 52.9% | 0.545 | -3587.67 | -6.47% |

Bet on 80.5% of rounds | UP 80623 / DOWN 87267 | win rate 51.1%
Coin-flip-side controls (200): median -9080.56, 95th pct -8349.66

Months: 2026-05 -304.34  2026-06 -2147.62  2026-07 -1901.41  2026-08 -1670.53  2026-09 -1349.15  2026-10 -2014.32  2026-11 -1207.95

By coin: BTC -2417.31 (43020)  ETH -3149.90 (42949)  SOL -2394.29 (40615)  XRP -2633.83 (41306)

## How many tries

Full runs of 'pm_candle_signature' with distinct code/params/coins: 1. Distinct variants of all ideas run in the lab: 26.
Every extra variant is another lottery ticket: if you try enough worthless ideas, some will pass by luck. Treat a pass found after many tries as a lead for a forward paper test, not as proof.
