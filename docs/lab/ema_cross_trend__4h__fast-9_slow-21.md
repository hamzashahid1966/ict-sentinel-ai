# Lab: ema_cross_trend (full run)

Run 2026-11-24 07:20:09 UTC. Research only: no orders are placed.

Hypothesis: Holding the side of the EMA9/21 cross captures multi-day crypto trends and earns
more than the trading costs, beating the same trades placed at random times.

## Verdict: FAIL

| criterion | result | detail |
|---|---|---|
| no look-ahead | yes | signal unchanged when later data is removed |
| net result > 0 | yes | +10.7% |
| beats 95th pct of random-timing controls | yes | +10.7% vs +9.1% (better than 96% of 200) |
| last third > 0 | NO | -14.1% |
| bootstrap 95% CI of mean daily return > 0 | NO | (-92.9%, +176.7%) a year |
| >= 60% of months positive | NO | 4/7 (need 5) |
| >= 20 entries | yes | 564 |

## Detail

Kind: position | timeframe 4h | coins BTC, ETH, SOL, XRP, BNB, DOGE, ZEC, HYPE, NEAR, SUI, ADA, LINK | 2026-05-24 .. 2026-11-23 (184 days)
Params: {"fast": 9, "slow": 21} | file research/strategies/ema_cross_trend.py @ 01819142f587
Costs: 0.07% per side on every change, funding charged | weight 1/12 per coin, no leverage

| | net | CAGR | Sharpe | max DD | days |
|---|---|---|---|---|---|
| whole period | +10.7% | +22.4% | 0.67 | -26.6% | 184 |
| first two thirds | +28.9% | +113.6% | 2.00 | -14.6% | 122 |
| last third | -14.1% | -59.1% | -1.65 | -26.6% | 62 |

Entries 564 | time in market 98% | costs paid +6.58% of capital | buy-and-hold of the same coins -17.9%
Random-timing controls (200): median -13.1%, 95th pct +9.1%

Months: 2026-05 -0.6%  2026-06 +5.6%  2026-07 -2.8%  2026-08 +16.0%  2026-09 +5.4%  2026-10 -20.0%  2026-11 +11.0%

By coin (sum of net contributions): BTC -0.50%  ETH -2.63%  SOL +3.65%  XRP +1.14%  BNB +0.07%  DOGE +0.80%  ZEC +1.15%  HYPE +0.99%  NEAR -3.81%  SUI +4.86%  ADA +8.93%  LINK +0.40%

## How many tries

Full runs of 'ema_cross_trend' with distinct code/params/coins: 2. Distinct variants of all ideas run in the lab: 19.
Every extra variant is another lottery ticket: if you try enough worthless ideas, some will pass by luck. Treat a pass found after many tries as a lead for a forward paper test, not as proof.
