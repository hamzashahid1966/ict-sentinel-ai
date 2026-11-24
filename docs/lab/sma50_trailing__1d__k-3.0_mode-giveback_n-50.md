# Lab: sma50_trailing (full run)

Run 2026-11-24 09:15:17 UTC. Research only: no orders are placed.

Hypothesis: An exit that follows each trade (a volatility trailing stop, or giving back half the
open profit) keeps more of the big trends' gains than waiting for the SMA50 flip, with smaller
drops.

## Verdict: FAIL

| criterion | result | detail |
|---|---|---|
| no look-ahead | yes | signal unchanged when later data is removed |
| net result > 0 | yes | +215.9% |
| beats 95th pct of random-timing controls | yes | +215.9% vs +36.0% (better than 100% of 200) |
| last third > 0 | yes | +149.4% |
| bootstrap 95% CI of mean daily return > 0 | NO | (-1.1%, +44.8%) a year |
| >= 60% of months positive | NO | 49/87 (need 53) |
| >= 20 entries | yes | 1530 |

## Detail

Kind: position | timeframe 1d (long history since 2019) | coins BTC, ETH, SOL, XRP, BNB, DOGE, ZEC, HYPE, NEAR, SUI, ADA, LINK | 2019-09-08 .. 2026-11-24 (2634 days)
Params: {"n": 50, "mode": "giveback", "k": 3.0} | file research/strategies/sma50_trailing.py @ 3374774f223b
Costs: 0.07% per side on every change, funding charged | weight 1/12 per coin, no leverage

| | net | CAGR | Sharpe | max DD | days |
|---|---|---|---|---|---|
| whole period | +215.9% | +17.3% | 0.64 | -37.1% | 2634 |
| first two thirds | +26.7% | +5.0% | 0.32 | -37.1% | 1756 |
| last third | +149.4% | +46.2% | 1.26 | -26.4% | 878 |

Entries 1530 | time in market 61% | costs paid +17.85% of capital | buy-and-hold of the same coins +1381.6%
Random-timing controls (200): median -55.6%, 95th pct +36.0%

Months: 2019-09 +0.0%  2019-10 -0.4%  2019-11 +0.0%  2019-12 +0.0%  2020-01 +2.5%  2020-02 +1.2%  2020-03 -6.0%  2020-04 -6.7%  2020-05 +3.1%  2020-06 +1.7%  2020-07 +7.6%  2020-08 +0.7%  2020-09 -6.5%  2020-10 -0.4%  2020-11 -4.7%  2020-12 +0.2%  2021-01 +5.0%  2021-02 +21.7%  2021-03 -3.8%  2021-04 +27.0%  2021-05 -24.8%  2021-06 +0.6%  2021-07 +6.7%  2021-08 +24.4%  2021-09 -1.4%  2021-10 -5.0%  2021-11 +0.1%  2021-12 +1.5%  2022-01 +6.5%  2022-02 -10.1%  2022-03 -2.9%  2022-04 +1.5%  2022-05 +1.0%  2022-06 +0.7%  2022-07 -8.2%  2022-08 +1.2%  2022-09 -8.8%  2022-10 +7.6%  2022-11 -9.1%  2022-12 +5.8%  2023-01 +7.3%  2023-02 -3.2%  2023-03 -1.7%  2023-04 -6.5%  2023-05 +2.7%  2023-06 -2.2%  2023-07 -4.4%  2023-08 +5.8%  2023-09 -1.3%  2023-10 +2.4%  2023-11 +6.6%  2023-12 +8.7%  2024-01 -9.5%  2024-02 +5.3%  2024-03 +0.9%  2024-04 -0.5%  2024-05 -5.3%  2024-06 +5.5%  2024-07 -3.2%  2024-08 -3.2%  2024-09 +8.4%  2024-10 +0.1%  2024-11 +51.7%  2024-12 -4.0%  2025-01 -8.0%  2025-02 +11.3%  2025-03 -15.6%  2025-04 -0.1%  2025-05 +7.0%  2025-06 -0.9%  2025-07 +13.0%  2025-08 -10.5%  2025-09 +0.8%  2025-10 +16.8%  2025-11 +7.9%  2025-12 +1.8%  2026-01 +1.8%  2026-02 +4.2%  2026-03 -13.1%  2026-04 -7.1%  2026-05 +6.3%  2026-06 +18.2%  2026-07 -7.5%  2026-08 +9.1%  2026-09 +23.6%  2026-10 -7.3%  2026-11 +15.4%

By coin (sum of net contributions): BTC +26.61%  ETH +8.11%  SOL -11.69%  XRP +7.39%  BNB -4.98%  DOGE +32.71%  ZEC +20.25%  HYPE +0.00%  NEAR +53.67%  SUI +23.80%  ADA +30.51%  LINK -29.06%

## How many tries

Full runs of 'sma50_trailing' with distinct code/params/coins: 2. Distinct variants of all ideas run in the lab: 38.
Every extra variant is another lottery ticket: if you try enough worthless ideas, some will pass by luck. Treat a pass found after many tries as a lead for a forward paper test, not as proof.
