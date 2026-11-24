# Lab: ema_cross_trend (full run)

Run 2026-11-24 07:20:06 UTC. Research only: no orders are placed.

Hypothesis: Holding the side of the EMA9/21 cross captures multi-day crypto trends and earns
more than the trading costs, beating the same trades placed at random times.

## Verdict: FAIL

| criterion | result | detail |
|---|---|---|
| no look-ahead | yes | signal unchanged when later data is removed |
| net result > 0 | yes | +523.3% |
| beats 95th pct of random-timing controls | yes | +523.3% vs +37.7% (better than 100% of 200) |
| last third > 0 | yes | +52.6% |
| bootstrap 95% CI of mean daily return > 0 | yes | (+4.1%, +74.6%) a year |
| >= 60% of months positive | NO | 47/87 (need 53) |
| >= 20 entries | yes | 1046 |

## Detail

Kind: position | timeframe 1d (long daily history) | coins BTC, ETH, SOL, XRP, BNB, DOGE, ZEC, HYPE, NEAR, SUI, ADA, LINK | 2019-09-08 .. 2026-11-23 (2633 days)
Params: {"fast": 9, "slow": 21} | file research/strategies/ema_cross_trend.py @ 01819142f587
Costs: 0.07% per side on every change, funding charged | weight 1/12 per coin, no leverage

| | net | CAGR | Sharpe | max DD | days |
|---|---|---|---|---|---|
| whole period | +523.3% | +28.9% | 0.75 | -55.1% | 2633 |
| first two thirds | +308.3% | +34.0% | 0.83 | -55.1% | 1755 |
| last third | +52.6% | +19.2% | 0.60 | -37.9% | 878 |

Entries 1046 | time in market 99% | costs paid +12.20% of capital | buy-and-hold of the same coins +1369.9%
Random-timing controls (200): median -65.4%, 95th pct +37.7%

Months: 2019-09 -0.1%  2019-10 -1.7%  2019-11 +0.6%  2019-12 -0.2%  2020-01 +2.9%  2020-02 +7.0%  2020-03 +0.9%  2020-04 -1.6%  2020-05 +5.1%  2020-06 -0.3%  2020-07 +16.6%  2020-08 +6.5%  2020-09 -3.3%  2020-10 -1.0%  2020-11 +9.7%  2020-12 -3.5%  2021-01 -10.7%  2021-02 +58.7%  2021-03 -8.7%  2021-04 +52.6%  2021-05 -21.7%  2021-06 +6.1%  2021-07 +1.2%  2021-08 +42.2%  2021-09 +2.3%  2021-10 -2.5%  2021-11 -2.2%  2021-12 -8.2%  2022-01 +6.9%  2022-02 -17.4%  2022-03 +0.8%  2022-04 +8.0%  2022-05 +17.1%  2022-06 +15.7%  2022-07 -15.0%  2022-08 -1.8%  2022-09 -11.9%  2022-10 -1.9%  2022-11 -16.4%  2022-12 +8.9%  2023-01 +7.3%  2023-02 -15.5%  2023-03 -2.6%  2023-04 -7.2%  2023-05 +4.3%  2023-06 +4.0%  2023-07 -13.2%  2023-08 +7.0%  2023-09 +0.6%  2023-10 +8.2%  2023-11 +16.6%  2023-12 +19.7%  2024-01 +2.5%  2024-02 +15.9%  2024-03 +14.4%  2024-04 -0.8%  2024-05 -10.1%  2024-06 +5.0%  2024-07 -4.5%  2024-08 -17.4%  2024-09 +2.6%  2024-10 -8.0%  2024-11 +49.9%  2024-12 -3.2%  2025-01 -14.2%  2025-02 +20.9%  2025-03 -15.5%  2025-04 -6.1%  2025-05 +6.3%  2025-06 +0.0%  2025-07 +9.4%  2025-08 -14.3%  2025-09 -6.3%  2025-10 +6.3%  2025-11 +19.7%  2025-12 +4.1%  2026-01 -3.5%  2026-02 +7.8%  2026-03 -18.0%  2026-04 -3.0%  2026-05 +10.0%  2026-06 +11.4%  2026-07 -11.0%  2026-08 +5.6%  2026-09 +21.7%  2026-10 -4.6%  2026-11 +25.5%

By coin (sum of net contributions): BTC +23.09%  ETH +26.08%  SOL +48.63%  XRP -2.35%  BNB +38.57%  DOGE +12.92%  ZEC +47.22%  HYPE -0.99%  NEAR +34.82%  SUI +27.10%  ADA +21.57%  LINK +4.75%

## How many tries

Full runs of 'ema_cross_trend' with distinct code/params/coins: 1. Distinct variants of all ideas run in the lab: 18.
Every extra variant is another lottery ticket: if you try enough worthless ideas, some will pass by luck. Treat a pass found after many tries as a lead for a forward paper test, not as proof.
