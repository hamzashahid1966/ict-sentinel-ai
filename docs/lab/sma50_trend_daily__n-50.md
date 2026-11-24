# Lab: sma50_trend_daily (full run)

Run 2026-11-24 05:21:46 UTC. Research only: no orders are placed.

Hypothesis: Crypto trends persist for weeks: holding the side of the 50-day average earns more
than the trading costs and beats the same trades placed at random times.

## Verdict: FAIL

| criterion | result | detail |
|---|---|---|
| no look-ahead | yes | signal unchanged when later data is removed |
| net result > 0 | yes | +1371.4% |
| beats 95th pct of random-timing controls | yes | +1371.4% vs +35.9% (better than 100% of 200) |
| last third > 0 | yes | +141.1% |
| bootstrap 95% CI of mean daily return > 0 | yes | (+15.0%, +88.2%) a year |
| >= 60% of months positive | NO | 44/87 (need 53) |
| >= 20 entries | yes | 1530 |

## Detail

Kind: position | timeframe 1d (long daily history) | coins BTC, ETH, SOL, XRP, BNB, DOGE, ZEC, HYPE, NEAR, SUI, ADA, LINK | 2019-09-08 .. 2026-11-23 (2633 days)
Params: {"n": 50} | file research/strategies/sma50_trend_daily.py @ e7720a6db46a
Costs: 0.07% per side on every change, funding charged | weight 1/12 per coin, no leverage

| | net | CAGR | Sharpe | max DD | days |
|---|---|---|---|---|---|
| whole period | +1371.4% | +45.2% | 0.97 | -53.0% | 2633 |
| first two thirds | +510.2% | +45.7% | 0.97 | -53.0% | 1755 |
| last third | +141.1% | +44.2% | 0.97 | -35.8% | 878 |

Entries 1530 | time in market 98% | costs paid +17.85% of capital | buy-and-hold of the same coins +1369.9%
Random-timing controls (200): median -64.1%, 95th pct +35.9%

Months: 2019-09 +0.0%  2019-10 -0.4%  2019-11 +0.2%  2019-12 +0.3%  2020-01 +2.3%  2020-02 +1.0%  2020-03 -5.5%  2020-04 -5.1%  2020-05 +5.7%  2020-06 +1.1%  2020-07 +17.0%  2020-08 +7.4%  2020-09 -10.0%  2020-10 -4.6%  2020-11 +11.1%  2020-12 -0.1%  2021-01 +64.3%  2021-02 +61.3%  2021-03 +2.2%  2021-04 +54.2%  2021-05 -32.0%  2021-06 +2.7%  2021-07 +4.0%  2021-08 +40.3%  2021-09 -1.0%  2021-10 -0.1%  2021-11 -3.1%  2021-12 +3.7%  2022-01 +17.1%  2022-02 -16.8%  2022-03 -1.0%  2022-04 -6.1%  2022-05 +17.1%  2022-06 +24.5%  2022-07 -19.1%  2022-08 -5.5%  2022-09 -10.3%  2022-10 +5.4%  2022-11 -13.5%  2022-12 +9.7%  2023-01 +4.7%  2023-02 -5.3%  2023-03 -5.3%  2023-04 -9.4%  2023-05 +2.2%  2023-06 -0.1%  2023-07 -11.7%  2023-08 +6.7%  2023-09 -0.6%  2023-10 +10.3%  2023-11 +16.8%  2023-12 +18.9%  2024-01 -4.6%  2024-02 +13.0%  2024-03 +12.9%  2024-04 -2.0%  2024-05 -9.7%  2024-06 -0.1%  2024-07 -5.7%  2024-08 -9.9%  2024-09 +7.3%  2024-10 -5.2%  2024-11 +63.4%  2024-12 -5.6%  2025-01 -8.6%  2025-02 +18.0%  2025-03 -13.4%  2025-04 -6.6%  2025-05 +4.6%  2025-06 -0.1%  2025-07 +0.7%  2025-08 -8.3%  2025-09 -1.6%  2025-10 +12.3%  2025-11 +23.3%  2025-12 +4.7%  2026-01 -4.5%  2026-02 +5.8%  2026-03 -19.5%  2026-04 -5.2%  2026-05 +12.9%  2026-06 +15.3%  2026-07 -10.8%  2026-08 +12.2%  2026-09 +30.5%  2026-10 -11.2%  2026-11 +29.8%

By coin (sum of net contributions): BTC +30.52%  ETH +33.68%  SOL +42.38%  XRP +6.83%  BNB +37.25%  DOGE +79.45%  ZEC +24.53%  HYPE -3.99%  NEAR +49.24%  SUI +36.71%  ADA +35.11%  LINK -4.25%

## How many tries

Full runs of 'sma50_trend_daily' with distinct code/params/coins: 1. Distinct variants of all ideas run in the lab: 1.
Every extra variant is another lottery ticket: if you try enough worthless ideas, some will pass by luck. Treat a pass found after many tries as a lead for a forward paper test, not as proof.
