# Lab: ema_structure (full run)

Run 2026-11-24 08:52:08 UTC. Research only: no orders are placed.

Hypothesis: Holding the side where the EMA trend and the swing structure (HH/HL or LH/LL) agree
captures trends with fewer false flips than either alone, earning more than costs and beating
random timing.

## Verdict: FAIL

| criterion | result | detail |
|---|---|---|
| no look-ahead | yes | signal unchanged when later data is removed |
| net result > 0 | yes | +793.2% |
| beats 95th pct of random-timing controls | yes | +793.2% vs +218.2% (better than 100% of 200) |
| last third > 0 | yes | +50.8% |
| bootstrap 95% CI of mean daily return > 0 | yes | (+13.6%, +55.4%) a year |
| >= 60% of months positive | NO | 38/87 (need 53) |
| >= 20 entries | yes | 503 |

## Detail

Kind: position | timeframe 1d (long history since 2019) | coins BTC, ETH, SOL, XRP, BNB, DOGE, ZEC, HYPE, NEAR, SUI, ADA, LINK | 2019-09-08 .. 2026-11-24 (2634 days)
Params: {"mode": "both", "ema": 50, "k": 5, "long_only": 1} | file research/strategies/ema_structure.py @ 05f9fcf6f8c5
Costs: 0.07% per side on every change, funding charged | weight 1/12 per coin, no leverage

| | net | CAGR | Sharpe | max DD | days |
|---|---|---|---|---|---|
| whole period | +793.2% | +35.4% | 1.27 | -31.2% | 2634 |
| first two thirds | +492.3% | +44.7% | 1.40 | -31.2% | 1756 |
| last third | +50.8% | +18.6% | 0.96 | -22.6% | 878 |

Entries 503 | time in market 22% | costs paid +5.87% of capital | buy-and-hold of the same coins +1381.6%
Random-timing controls (200): median +77.6%, 95th pct +218.2%

Months: 2019-09 +0.0%  2019-10 -0.3%  2019-11 +0.0%  2019-12 +0.0%  2020-01 +0.6%  2020-02 +0.5%  2020-03 -6.1%  2020-04 +7.2%  2020-05 +0.1%  2020-06 -1.2%  2020-07 +15.9%  2020-08 +6.9%  2020-09 -4.6%  2020-10 -1.0%  2020-11 +19.6%  2020-12 +6.1%  2021-01 +54.9%  2021-02 +57.7%  2021-03 +8.8%  2021-04 +32.5%  2021-05 -14.2%  2021-06 -1.7%  2021-07 +1.4%  2021-08 +16.0%  2021-09 -2.4%  2021-10 +1.3%  2021-11 -2.7%  2021-12 +0.7%  2022-01 -0.1%  2022-02 -2.0%  2022-03 +3.7%  2022-04 -4.7%  2022-05 +0.0%  2022-06 +0.0%  2022-07 -0.6%  2022-08 -3.6%  2022-09 -0.9%  2022-10 -0.6%  2022-11 -4.7%  2022-12 -1.7%  2023-01 +1.7%  2023-02 -2.6%  2023-03 -1.0%  2023-04 -1.5%  2023-05 -1.4%  2023-06 -1.7%  2023-07 +2.1%  2023-08 -1.2%  2023-09 +1.8%  2023-10 +6.2%  2023-11 +6.8%  2023-12 +19.2%  2024-01 +1.6%  2024-02 +4.2%  2024-03 +9.1%  2024-04 -5.4%  2024-05 +0.1%  2024-06 -3.3%  2024-07 -0.5%  2024-08 -1.9%  2024-09 +0.5%  2024-10 -2.2%  2024-11 +33.4%  2024-12 +1.1%  2025-01 -4.4%  2025-02 -2.8%  2025-03 +0.0%  2025-04 +0.2%  2025-05 +3.7%  2025-06 -0.6%  2025-07 -5.3%  2025-08 +2.2%  2025-09 +4.8%  2025-10 +17.0%  2025-11 +5.4%  2025-12 +0.0%  2026-01 -5.5%  2026-02 -1.1%  2026-03 -2.0%  2026-04 -1.7%  2026-05 -1.2%  2026-06 -3.4%  2026-07 -2.1%  2026-08 +2.0%  2026-09 +18.8%  2026-10 -4.6%  2026-11 +0.0%

By coin (sum of net contributions): BTC +3.60%  ETH +7.02%  SOL +39.44%  XRP +23.33%  BNB +26.81%  DOGE +63.18%  ZEC +32.16%  HYPE -2.23%  NEAR +25.27%  SUI +5.57%  ADA +13.05%  LINK +6.12%

## How many tries

Full runs of 'ema_structure' with distinct code/params/coins: 4. Distinct variants of all ideas run in the lab: 31.
Every extra variant is another lottery ticket: if you try enough worthless ideas, some will pass by luck. Treat a pass found after many tries as a lead for a forward paper test, not as proof.
