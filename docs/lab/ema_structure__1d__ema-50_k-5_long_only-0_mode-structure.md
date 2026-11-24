# Lab: ema_structure (full run)

Run 2026-11-24 08:52:07 UTC. Research only: no orders are placed.

Hypothesis: Holding the side where the EMA trend and the swing structure (HH/HL or LH/LL) agree
captures trends with fewer false flips than either alone, earning more than costs and beating
random timing.

## Verdict: FAIL

| criterion | result | detail |
|---|---|---|
| no look-ahead | yes | signal unchanged when later data is removed |
| net result > 0 | yes | +545.3% |
| beats 95th pct of random-timing controls | yes | +545.3% vs +100.7% (better than 100% of 200) |
| last third > 0 | NO | -2.8% |
| bootstrap 95% CI of mean daily return > 0 | yes | (+9.2%, +56.6%) a year |
| >= 60% of months positive | NO | 47/87 (need 53) |
| >= 20 entries | yes | 871 |

## Detail

Kind: position | timeframe 1d (long history since 2019) | coins BTC, ETH, SOL, XRP, BNB, DOGE, ZEC, HYPE, NEAR, SUI, ADA, LINK | 2019-09-08 .. 2026-11-24 (2634 days)
Params: {"mode": "structure", "ema": 50, "k": 5, "long_only": 0} | file research/strategies/ema_structure.py @ 05f9fcf6f8c5
Costs: 0.07% per side on every change, funding charged | weight 1/12 per coin, no leverage

| | net | CAGR | Sharpe | max DD | days |
|---|---|---|---|---|---|
| whole period | +545.3% | +29.5% | 0.91 | -42.9% | 2634 |
| first two thirds | +564.0% | +48.2% | 1.25 | -32.4% | 1756 |
| last third | -2.8% | -1.2% | 0.11 | -38.2% | 878 |

Entries 871 | time in market 59% | costs paid +10.16% of capital | buy-and-hold of the same coins +1381.6%
Random-timing controls (200): median -30.9%, 95th pct +100.7%

Months: 2019-09 +0.0%  2019-10 +1.3%  2019-11 +1.2%  2019-12 +0.3%  2020-01 +2.3%  2020-02 -0.0%  2020-03 -11.6%  2020-04 +9.4%  2020-05 +0.3%  2020-06 -2.4%  2020-07 +12.8%  2020-08 +8.1%  2020-09 +4.5%  2020-10 +0.8%  2020-11 +16.4%  2020-12 +11.2%  2021-01 +34.0%  2021-02 +54.7%  2021-03 +10.6%  2021-04 +23.6%  2021-05 -12.1%  2021-06 -3.6%  2021-07 +5.8%  2021-08 +11.5%  2021-09 -4.3%  2021-10 -7.8%  2021-11 -0.0%  2021-12 +1.2%  2022-01 +13.1%  2022-02 -6.7%  2022-03 +2.0%  2022-04 +1.5%  2022-05 +17.5%  2022-06 +15.2%  2022-07 +3.3%  2022-08 -6.4%  2022-09 -4.2%  2022-10 -6.1%  2022-11 -1.1%  2022-12 +0.2%  2023-01 -2.2%  2023-02 +0.4%  2023-03 -6.2%  2023-04 -1.1%  2023-05 +1.2%  2023-06 -2.7%  2023-07 +3.5%  2023-08 +4.4%  2023-09 +1.2%  2023-10 -1.6%  2023-11 +3.9%  2023-12 +20.2%  2024-01 +6.9%  2024-02 -2.2%  2024-03 +8.4%  2024-04 +4.8%  2024-05 -4.9%  2024-06 -9.2%  2024-07 -15.3%  2024-08 -10.4%  2024-09 -8.7%  2024-10 -1.7%  2024-11 +18.5%  2024-12 +4.3%  2025-01 -7.0%  2025-02 -5.9%  2025-03 -0.3%  2025-04 -2.1%  2025-05 +8.8%  2025-06 +7.5%  2025-07 -16.1%  2025-08 +3.7%  2025-09 -0.7%  2025-10 +26.2%  2025-11 +24.3%  2025-12 +0.4%  2026-01 -13.5%  2026-02 -5.4%  2026-03 -5.9%  2026-04 -5.4%  2026-05 +0.8%  2026-06 -2.9%  2026-07 -6.6%  2026-08 -2.4%  2026-09 +15.7%  2026-10 -3.1%  2026-11 +17.6%

By coin (sum of net contributions): BTC -4.25%  ETH +16.17%  SOL +29.08%  XRP +27.86%  BNB +24.23%  DOGE +76.33%  ZEC +31.51%  HYPE -9.35%  NEAR +21.85%  SUI -8.25%  ADA +15.97%  LINK +7.45%

## How many tries

Full runs of 'ema_structure' with distinct code/params/coins: 2. Distinct variants of all ideas run in the lab: 29.
Every extra variant is another lottery ticket: if you try enough worthless ideas, some will pass by luck. Treat a pass found after many tries as a lead for a forward paper test, not as proof.
