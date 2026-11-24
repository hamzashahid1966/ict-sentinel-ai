# Lab: ema_structure (full run)

Run 2026-11-24 08:52:13 UTC. Research only: no orders are placed.

Hypothesis: Holding the side where the EMA trend and the swing structure (HH/HL or LH/LL) agree
captures trends with fewer false flips than either alone, earning more than costs and beating
random timing.

## Verdict: FAIL

| criterion | result | detail |
|---|---|---|
| no look-ahead | yes | signal unchanged when later data is removed |
| net result > 0 | NO | -97.3% |
| beats 95th pct of random-timing controls | NO | -97.3% vs -92.2% (better than 22% of 200) |
| last third > 0 | NO | -54.8% |
| bootstrap 95% CI of mean daily return > 0 | NO | (-67.2%, -22.3%) a year |
| >= 60% of months positive | NO | 23/87 (need 53) |
| >= 20 entries | yes | 25830 |

## Detail

Kind: position | timeframe 1h (long history since 2019) | coins BTC, ETH, SOL, XRP, BNB, DOGE, ZEC, HYPE, NEAR, SUI, ADA, LINK | 2019-09-08 .. 2026-11-24 (2635 days)
Params: {"mode": "both", "ema": 50, "k": 5, "long_only": 0} | file research/strategies/ema_structure.py @ 05f9fcf6f8c5
Costs: 0.07% per side on every change, funding charged | weight 1/12 per coin, no leverage

| | net | CAGR | Sharpe | max DD | days |
|---|---|---|---|---|---|
| whole period | -97.3% | -39.4% | -1.36 | -97.8% | 2635 |
| first two thirds | -94.1% | -44.4% | -1.60 | -95.2% | 1756 |
| last third | -54.8% | -28.1% | -0.87 | -65.9% | 879 |

Entries 25830 | time in market 42% | costs paid +301.35% of capital | buy-and-hold of the same coins +1232.8%
Random-timing controls (200): median -96.0%, 95th pct -92.2%

Months: 2019-09 +0.9%  2019-10 -0.7%  2019-11 +0.7%  2019-12 -1.3%  2020-01 -0.9%  2020-02 -1.9%  2020-03 -7.6%  2020-04 -6.8%  2020-05 -2.9%  2020-06 -9.7%  2020-07 +2.0%  2020-08 -4.9%  2020-09 +2.6%  2020-10 -6.8%  2020-11 +16.0%  2020-12 -5.5%  2021-01 +25.7%  2021-02 +6.3%  2021-03 -10.7%  2021-04 -0.3%  2021-05 -25.6%  2021-06 -16.3%  2021-07 -12.2%  2021-08 -1.9%  2021-09 -11.0%  2021-10 +5.5%  2021-11 -9.5%  2021-12 -4.1%  2022-01 -8.8%  2022-02 -2.2%  2022-03 +3.6%  2022-04 -5.2%  2022-05 -2.1%  2022-06 -11.6%  2022-07 +4.6%  2022-08 -7.2%  2022-09 -12.0%  2022-10 -1.7%  2022-11 -0.9%  2022-12 +2.3%  2023-01 -5.7%  2023-02 -0.6%  2023-03 +0.9%  2023-04 -13.6%  2023-05 -8.3%  2023-06 -7.8%  2023-07 -12.3%  2023-08 -4.1%  2023-09 -8.1%  2023-10 -2.6%  2023-11 -5.3%  2023-12 -8.0%  2024-01 -8.7%  2024-02 -3.5%  2024-03 -18.0%  2024-04 -16.2%  2024-05 -9.5%  2024-06 -4.3%  2024-07 +6.5%  2024-08 +5.7%  2024-09 -2.1%  2024-10 +0.7%  2024-11 +12.3%  2024-12 -6.2%  2025-01 -10.5%  2025-02 -0.7%  2025-03 -6.8%  2025-04 -11.6%  2025-05 -11.5%  2025-06 +3.1%  2025-07 +2.4%  2025-08 -8.6%  2025-09 -1.2%  2025-10 -6.3%  2025-11 -7.6%  2025-12 +1.0%  2026-01 +8.9%  2026-02 +4.0%  2026-03 -4.0%  2026-04 -13.2%  2026-05 -0.8%  2026-06 +0.5%  2026-07 -0.7%  2026-08 +2.0%  2026-09 -11.8%  2026-10 -10.8%  2026-11 -4.7%

By coin (sum of net contributions): BTC -26.79%  ETH -33.36%  SOL -29.15%  XRP -4.26%  BNB -36.67%  DOGE -9.19%  ZEC -22.33%  HYPE -6.52%  NEAR -39.02%  SUI -27.10%  ADA -42.62%  LINK -41.72%

## How many tries

Full runs of 'ema_structure' with distinct code/params/coins: 5. Distinct variants of all ideas run in the lab: 32.
Every extra variant is another lottery ticket: if you try enough worthless ideas, some will pass by luck. Treat a pass found after many tries as a lead for a forward paper test, not as proof.
