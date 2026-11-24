# Lab: sma50_trailing (full run)

Run 2026-11-24 09:15:24 UTC. Research only: no orders are placed.

Hypothesis: An exit that follows each trade (a volatility trailing stop, or giving back half the
open profit) keeps more of the big trends' gains than waiting for the SMA50 flip, with smaller
drops.

## Verdict: FAIL

| criterion | result | detail |
|---|---|---|
| no look-ahead | yes | signal unchanged when later data is removed |
| net result > 0 | yes | +739.6% |
| beats 95th pct of random-timing controls | yes | +739.6% vs +40.9% (better than 100% of 200) |
| last third > 0 | yes | +105.9% |
| bootstrap 95% CI of mean daily return > 0 | yes | (+7.6%, +75.1%) a year |
| >= 60% of months positive | NO | 44/87 (need 53) |
| >= 20 entries | yes | 1530 |

## Detail

Kind: position | timeframe 1d (long history since 2019) | coins BTC, ETH, SOL, XRP, BNB, DOGE, ZEC, HYPE, NEAR, SUI, ADA, LINK | 2019-09-08 .. 2026-11-24 (2634 days)
Params: {"n": 50, "mode": "atr", "k": 3} | file research/strategies/sma50_trailing.py @ 3374774f223b
Costs: 0.07% per side on every change, funding charged | weight 1/12 per coin, no leverage

| | net | CAGR | Sharpe | max DD | days |
|---|---|---|---|---|---|
| whole period | +739.6% | +34.3% | 0.85 | -51.6% | 2634 |
| first two thirds | +307.7% | +33.9% | 0.85 | -51.6% | 1756 |
| last third | +105.9% | +35.0% | 0.85 | -36.1% | 878 |

Entries 1530 | time in market 92% | costs paid +17.85% of capital | buy-and-hold of the same coins +1381.6%
Random-timing controls (200): median -67.4%, 95th pct +40.9%

Months: 2019-09 +0.0%  2019-10 -0.4%  2019-11 +0.2%  2019-12 +0.3%  2020-01 +2.3%  2020-02 +1.2%  2020-03 -5.0%  2020-04 -2.0%  2020-05 +5.7%  2020-06 +1.1%  2020-07 +17.0%  2020-08 +7.5%  2020-09 -10.0%  2020-10 -4.9%  2020-11 +10.8%  2020-12 -1.8%  2021-01 +15.4%  2021-02 +50.7%  2021-03 -4.9%  2021-04 +43.2%  2021-05 -28.2%  2021-06 +2.7%  2021-07 +4.0%  2021-08 +40.7%  2021-09 -2.2%  2021-10 -2.4%  2021-11 -4.3%  2021-12 +4.8%  2022-01 +17.1%  2022-02 -15.6%  2022-03 -1.0%  2022-04 -5.1%  2022-05 +17.1%  2022-06 +25.2%  2022-07 -18.9%  2022-08 -5.1%  2022-09 -10.0%  2022-10 +5.4%  2022-11 -12.1%  2022-12 +7.6%  2023-01 +7.6%  2023-02 -6.1%  2023-03 -5.3%  2023-04 -9.6%  2023-05 +2.6%  2023-06 -0.4%  2023-07 -11.2%  2023-08 +7.9%  2023-09 -0.6%  2023-10 +10.3%  2023-11 +16.3%  2023-12 +18.9%  2024-01 -3.7%  2024-02 +13.9%  2024-03 +11.6%  2024-04 -0.7%  2024-05 -9.7%  2024-06 +1.2%  2024-07 -6.9%  2024-08 -7.1%  2024-09 +7.3%  2024-10 -6.2%  2024-11 +55.8%  2024-12 -6.8%  2025-01 -12.5%  2025-02 +19.5%  2025-03 -14.7%  2025-04 -4.3%  2025-05 +4.6%  2025-06 -0.3%  2025-07 +1.8%  2025-08 -12.0%  2025-09 -1.2%  2025-10 +11.1%  2025-11 +23.3%  2025-12 +4.7%  2026-01 -3.1%  2026-02 +2.7%  2026-03 -16.8%  2026-04 -5.2%  2026-05 +13.8%  2026-06 +12.5%  2026-07 -10.2%  2026-08 +11.0%  2026-09 +28.0%  2026-10 -10.0%  2026-11 +28.8%

By coin (sum of net contributions): BTC +26.46%  ETH +35.04%  SOL +39.86%  XRP +6.52%  BNB +26.40%  DOGE +33.99%  ZEC +25.91%  HYPE -3.76%  NEAR +49.66%  SUI +30.19%  ADA +35.00%  LINK -6.06%

## How many tries

Full runs of 'sma50_trailing' with distinct code/params/coins: 3. Distinct variants of all ideas run in the lab: 39.
Every extra variant is another lottery ticket: if you try enough worthless ideas, some will pass by luck. Treat a pass found after many tries as a lead for a forward paper test, not as proof.
