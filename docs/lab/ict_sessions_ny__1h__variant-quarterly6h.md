# Lab: ict_sessions_ny (full run)

Run 2026-11-24 07:50:48 UTC. Research only: no orders are placed.

Hypothesis: The closure signature of a session candle (6-hour quarter, or London vs Asia on the
4-hour cycle) predicts the direction of the next session candle well enough to beat costs and
random timing.

## Verdict: FAIL

| criterion | result | detail |
|---|---|---|
| no look-ahead | yes | signal unchanged when later data is removed |
| net result > 0 | NO | -52.2% |
| beats 95th pct of random-timing controls | NO | -52.2% vs -23.8% (better than 6% of 200) |
| last third > 0 | NO | -28.7% |
| bootstrap 95% CI of mean daily return > 0 | NO | (-243.9%, -27.2%) a year |
| >= 60% of months positive | NO | 1/7 (need 5) |
| >= 20 entries | yes | 4085 |

## Detail

Kind: position | timeframe 1h | coins BTC, ETH, SOL, XRP, BNB, DOGE, ZEC, HYPE, NEAR, SUI, ADA, LINK | 2026-05-24 .. 2026-11-23 (184 days)
Params: {"variant": "quarterly6h"} | file research/strategies/ict_sessions_ny.py @ 77a859aca0bf
Costs: 0.07% per side on every change, funding charged | weight 1/12 per coin, no leverage

| | net | CAGR | Sharpe | max DD | days |
|---|---|---|---|---|---|
| whole period | -52.2% | -76.9% | -4.36 | -53.5% | 184 |
| first two thirds | -33.0% | -69.8% | -3.68 | -45.1% | 122 |
| last third | -28.7% | -86.3% | -5.61 | -27.7% | 62 |

Entries 4085 | time in market 79% | costs paid +47.66% of capital | buy-and-hold of the same coins -17.5%
Random-timing controls (200): median -38.6%, 95th pct -23.8%

Months: 2026-05 +1.3%  2026-06 -29.7%  2026-07 -11.3%  2026-08 -1.9%  2026-09 -5.0%  2026-10 -2.5%  2026-11 -16.7%

By coin (sum of net contributions): BTC -10.06%  ETH -9.12%  SOL -5.75%  XRP -5.79%  BNB -4.72%  DOGE -8.97%  ZEC +4.50%  HYPE -5.38%  NEAR -6.64%  SUI -6.08%  ADA -2.16%  LINK -10.32%

## How many tries

Full runs of 'ict_sessions_ny' with distinct code/params/coins: 1. Distinct variants of all ideas run in the lab: 24.
Every extra variant is another lottery ticket: if you try enough worthless ideas, some will pass by luck. Treat a pass found after many tries as a lead for a forward paper test, not as proof.
