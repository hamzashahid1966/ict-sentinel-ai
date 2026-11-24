# Lab: ict_sessions_ny (full run)

Run 2026-11-24 07:50:51 UTC. Research only: no orders are placed.

Hypothesis: The closure signature of a session candle (6-hour quarter, or London vs Asia on the
4-hour cycle) predicts the direction of the next session candle well enough to beat costs and
random timing.

## Verdict: FAIL

| criterion | result | detail |
|---|---|---|
| no look-ahead | yes | signal unchanged when later data is removed |
| net result > 0 | yes | +5.3% |
| beats 95th pct of random-timing controls | yes | +5.3% vs -11.7% (better than 100% of 200) |
| last third > 0 | yes | +11.2% |
| bootstrap 95% CI of mean daily return > 0 | NO | (-29.3%, +55.1%) a year |
| >= 60% of months positive | NO | 3/7 (need 5) |
| >= 20 entries | yes | 1703 |

## Detail

Kind: position | timeframe 1h | coins BTC, ETH, SOL, XRP, BNB, DOGE, ZEC, HYPE, NEAR, SUI, ADA, LINK | 2026-05-24 .. 2026-11-23 (184 days)
Params: {"variant": "novo3"} | file research/strategies/ict_sessions_ny.py @ 77a859aca0bf
Costs: 0.07% per side on every change, funding charged | weight 1/12 per coin, no leverage

| | net | CAGR | Sharpe | max DD | days |
|---|---|---|---|---|---|
| whole period | +5.3% | +10.8% | 0.62 | -6.8% | 184 |
| first two thirds | -5.3% | -14.9% | -0.95 | -6.8% | 122 |
| last third | +11.2% | +86.5% | 2.61 | -4.1% | 62 |

Entries 1703 | time in market 14% | costs paid +19.87% of capital | buy-and-hold of the same coins -17.5%
Random-timing controls (200): median -18.5%, 95th pct -11.7%

Months: 2026-05 -2.4%  2026-06 -1.4%  2026-07 +1.5%  2026-08 -1.3%  2026-09 -2.1%  2026-10 +10.0%  2026-11 +1.4%

By coin (sum of net contributions): BTC +0.29%  ETH -1.32%  SOL +0.08%  XRP +0.85%  BNB -0.53%  DOGE -0.43%  ZEC +4.12%  HYPE +2.24%  NEAR +0.15%  SUI -2.50%  ADA +3.10%  LINK +0.04%

## How many tries

Full runs of 'ict_sessions_ny' with distinct code/params/coins: 2. Distinct variants of all ideas run in the lab: 25.
Every extra variant is another lottery ticket: if you try enough worthless ideas, some will pass by luck. Treat a pass found after many tries as a lead for a forward paper test, not as proof.
