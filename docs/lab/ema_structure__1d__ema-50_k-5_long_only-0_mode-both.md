# Lab: ema_structure (full run)

Run 2026-11-24 08:52:06 UTC. Research only: no orders are placed.

Hypothesis: Holding the side where the EMA trend and the swing structure (HH/HL or LH/LL) agree
captures trends with fewer false flips than either alone, earning more than costs and beating
random timing.

## Verdict: FAIL

| criterion | result | detail |
|---|---|---|
| no look-ahead | yes | signal unchanged when later data is removed |
| net result > 0 | yes | +679.1% |
| beats 95th pct of random-timing controls | yes | +679.1% vs +48.7% (better than 100% of 200) |
| last third > 0 | yes | +30.9% |
| bootstrap 95% CI of mean daily return > 0 | yes | (+11.6%, +58.4%) a year |
| >= 60% of months positive | NO | 44/87 (need 53) |
| >= 20 entries | yes | 1015 |

## Detail

Kind: position | timeframe 1d (long history since 2019) | coins BTC, ETH, SOL, XRP, BNB, DOGE, ZEC, HYPE, NEAR, SUI, ADA, LINK | 2019-09-08 .. 2026-11-24 (2634 days)
Params: {"mode": "both", "ema": 50, "k": 5, "long_only": 0} | file research/strategies/ema_structure.py @ 05f9fcf6f8c5
Costs: 0.07% per side on every change, funding charged | weight 1/12 per coin, no leverage

| | net | CAGR | Sharpe | max DD | days |
|---|---|---|---|---|---|
| whole period | +679.1% | +32.9% | 1.03 | -33.6% | 2634 |
| first two thirds | +495.4% | +44.9% | 1.24 | -33.6% | 1756 |
| last third | +30.9% | +11.8% | 0.53 | -28.0% | 878 |

Entries 1015 | time in market 43% | costs paid +11.84% of capital | buy-and-hold of the same coins +1381.6%
Random-timing controls (200): median -40.8%, 95th pct +48.7%

Months: 2019-09 +0.0%  2019-10 -0.3%  2019-11 +0.9%  2019-12 +0.4%  2020-01 +0.6%  2020-02 +0.5%  2020-03 -10.8%  2020-04 +3.5%  2020-05 -0.2%  2020-06 -1.5%  2020-07 +13.5%  2020-08 +7.0%  2020-09 -4.0%  2020-10 -1.4%  2020-11 +15.5%  2020-12 +4.6%  2021-01 +48.0%  2021-02 +57.7%  2021-03 +8.8%  2021-04 +32.5%  2021-05 -14.9%  2021-06 -0.9%  2021-07 +4.6%  2021-08 +12.9%  2021-09 -2.9%  2021-10 -5.3%  2021-11 -2.7%  2021-12 +1.8%  2022-01 +17.0%  2022-02 -8.6%  2022-03 +2.7%  2022-04 +0.1%  2022-05 +17.4%  2022-06 +15.2%  2022-07 -3.7%  2022-08 -3.4%  2022-09 -5.3%  2022-10 -3.0%  2022-11 -6.1%  2022-12 +2.9%  2023-01 -4.7%  2023-02 -3.3%  2023-03 -7.2%  2023-04 -1.6%  2023-05 -0.1%  2023-06 +0.3%  2023-07 +2.0%  2023-08 +5.9%  2023-09 +0.7%  2023-10 +2.9%  2023-11 +6.4%  2023-12 +19.2%  2024-01 +2.3%  2024-02 +0.8%  2024-03 +8.2%  2024-04 +1.4%  2024-05 -5.3%  2024-06 -4.9%  2024-07 -9.7%  2024-08 -6.7%  2024-09 -1.9%  2024-10 -3.2%  2024-11 +30.0%  2024-12 +1.8%  2025-01 -5.4%  2025-02 -2.3%  2025-03 -3.1%  2025-04 -2.4%  2025-05 +3.6%  2025-06 +4.3%  2025-07 -9.2%  2025-08 -4.6%  2025-09 +2.1%  2025-10 +21.4%  2025-11 +22.3%  2025-12 -0.2%  2026-01 -8.8%  2026-02 -0.9%  2026-03 -5.2%  2026-04 -5.8%  2026-05 -0.4%  2026-06 +2.9%  2026-07 -7.3%  2026-08 +0.5%  2026-09 +18.8%  2026-10 -5.4%  2026-11 +17.2%

By coin (sum of net contributions): BTC +1.59%  ETH +14.28%  SOL +40.25%  XRP +18.54%  BNB +24.18%  DOGE +75.44%  ZEC +18.25%  HYPE -5.57%  NEAR +24.86%  SUI +6.94%  ADA +18.84%  LINK +5.31%

## How many tries

Full runs of 'ema_structure' with distinct code/params/coins: 1. Distinct variants of all ideas run in the lab: 28.
Every extra variant is another lottery ticket: if you try enough worthless ideas, some will pass by luck. Treat a pass found after many tries as a lead for a forward paper test, not as proof.
