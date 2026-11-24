# Lab: ema_structure (full run)

Run 2026-11-24 08:52:07 UTC. Research only: no orders are placed.

Hypothesis: Holding the side where the EMA trend and the swing structure (HH/HL or LH/LL) agree
captures trends with fewer false flips than either alone, earning more than costs and beating
random timing.

## Verdict: FAIL

| criterion | result | detail |
|---|---|---|
| no look-ahead | yes | signal unchanged when later data is removed |
| net result > 0 | yes | +721.4% |
| beats 95th pct of random-timing controls | yes | +721.4% vs +13.5% (better than 100% of 200) |
| last third > 0 | yes | +94.6% |
| bootstrap 95% CI of mean daily return > 0 | yes | (+5.1%, +80.6%) a year |
| >= 60% of months positive | NO | 43/87 (need 53) |
| >= 20 entries | yes | 1846 |

## Detail

Kind: position | timeframe 1d (long history since 2019) | coins BTC, ETH, SOL, XRP, BNB, DOGE, ZEC, HYPE, NEAR, SUI, ADA, LINK | 2019-09-08 .. 2026-11-24 (2634 days)
Params: {"mode": "ema", "ema": 50, "k": 5, "long_only": 0} | file research/strategies/ema_structure.py @ 05f9fcf6f8c5
Costs: 0.07% per side on every change, funding charged | weight 1/12 per coin, no leverage

| | net | CAGR | Sharpe | max DD | days |
|---|---|---|---|---|---|
| whole period | +721.4% | +33.9% | 0.82 | -61.1% | 2634 |
| first two thirds | +322.1% | +34.9% | 0.83 | -61.1% | 1756 |
| last third | +94.6% | +31.9% | 0.80 | -41.9% | 878 |

Entries 1846 | time in market 98% | costs paid +21.54% of capital | buy-and-hold of the same coins +1381.6%
Random-timing controls (200): median -72.1%, 95th pct +13.5%

Months: 2019-09 +0.0%  2019-10 -0.4%  2019-11 +0.2%  2019-12 +0.3%  2020-01 +1.4%  2020-02 +1.0%  2020-03 -6.0%  2020-04 -13.6%  2020-05 +1.7%  2020-06 +0.2%  2020-07 +20.1%  2020-08 +6.6%  2020-09 -15.5%  2020-10 -3.4%  2020-11 +4.7%  2020-12 -3.7%  2021-01 +72.1%  2021-02 +62.0%  2021-03 +8.8%  2021-04 +54.3%  2021-05 -37.5%  2021-06 +4.4%  2021-07 -0.6%  2021-08 +39.3%  2021-09 -1.2%  2021-10 -0.4%  2021-11 -5.4%  2021-12 +5.1%  2022-01 +19.7%  2022-02 -16.4%  2022-03 -4.9%  2022-04 -0.8%  2022-05 +17.1%  2022-06 +24.5%  2022-07 -22.8%  2022-08 -4.7%  2022-09 -11.2%  2022-10 +5.8%  2022-11 -13.6%  2022-12 +7.6%  2023-01 +0.9%  2023-02 -10.9%  2023-03 -7.4%  2023-04 -7.4%  2023-05 -0.7%  2023-06 +0.7%  2023-07 -13.5%  2023-08 +7.8%  2023-09 -0.2%  2023-10 +12.9%  2023-11 +13.0%  2023-12 +22.0%  2024-01 -4.8%  2024-02 +17.7%  2024-03 +14.1%  2024-04 -4.4%  2024-05 -11.1%  2024-06 +3.5%  2024-07 -0.7%  2024-08 -5.0%  2024-09 +3.1%  2024-10 -5.4%  2024-11 +63.3%  2024-12 -7.3%  2025-01 -3.0%  2025-02 +15.3%  2025-03 -13.5%  2025-04 -9.2%  2025-05 -3.5%  2025-06 -2.7%  2025-07 +5.1%  2025-08 -13.6%  2025-09 -2.3%  2025-10 +10.1%  2025-11 +21.7%  2025-12 +3.0%  2026-01 -3.9%  2026-02 +5.9%  2026-03 -10.1%  2026-04 -5.4%  2026-05 +10.1%  2026-06 +9.8%  2026-07 -12.4%  2026-08 +13.8%  2026-09 +29.5%  2026-10 -14.1%  2026-11 +22.6%

By coin (sum of net contributions): BTC +19.45%  ETH +15.66%  SOL +42.13%  XRP -7.43%  BNB +26.28%  DOGE +71.33%  ZEC +18.83%  HYPE +1.37%  NEAR +47.57%  SUI +40.62%  ADA +34.14%  LINK -1.03%

## How many tries

Full runs of 'ema_structure' with distinct code/params/coins: 3. Distinct variants of all ideas run in the lab: 30.
Every extra variant is another lottery ticket: if you try enough worthless ideas, some will pass by luck. Treat a pass found after many tries as a lead for a forward paper test, not as proof.
