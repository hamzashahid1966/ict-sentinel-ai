# Lab: sma50_take_profit (full run)

Run 2026-11-24 09:13:02 UTC. Research only: no orders are placed.

Hypothesis: Locking in a trade's profit once it reaches tp keeps more of the gains than holding
until the trend flips.

## Verdict: FAIL

| criterion | result | detail |
|---|---|---|
| no look-ahead | yes | signal unchanged when later data is removed |
| net result > 0 | yes | +55.8% |
| beats 95th pct of random-timing controls | yes | +55.8% vs +35.8% (better than 98% of 200) |
| last third > 0 | yes | +43.5% |
| bootstrap 95% CI of mean daily return > 0 | NO | (-4.5%, +19.9%) a year |
| >= 60% of months positive | yes | 53/87 (need 53) |
| >= 20 entries | yes | 1530 |

## Detail

Kind: position | timeframe 1d (long history since 2019) | coins BTC, ETH, SOL, XRP, BNB, DOGE, ZEC, HYPE, NEAR, SUI, ADA, LINK | 2019-09-08 .. 2026-11-24 (2634 days)
Params: {"n": 50, "tp": 0.1} | file research/strategies/sma50_take_profit.py @ a8f201beabe8
Costs: 0.07% per side on every change, funding charged | weight 1/12 per coin, no leverage

| | net | CAGR | Sharpe | max DD | days |
|---|---|---|---|---|---|
| whole period | +55.8% | +6.3% | 0.45 | -25.7% | 2634 |
| first two thirds | +8.6% | +1.7% | 0.19 | -25.7% | 1756 |
| last third | +43.5% | +16.2% | 0.92 | -20.5% | 878 |

Entries 1530 | time in market 32% | costs paid +17.85% of capital | buy-and-hold of the same coins +1381.6%
Random-timing controls (200): median -34.3%, 95th pct +35.8%

Months: 2019-09 +0.0%  2019-10 -0.4%  2019-11 +0.2%  2019-12 +0.0%  2020-01 +1.7%  2020-02 +0.4%  2020-03 +0.8%  2020-04 +2.7%  2020-05 -1.1%  2020-06 +0.8%  2020-07 +0.9%  2020-08 +0.4%  2020-09 -0.5%  2020-10 -3.3%  2020-11 -5.8%  2020-12 +0.8%  2021-01 +5.0%  2021-02 +0.3%  2021-03 -7.5%  2021-04 +4.9%  2021-05 -10.5%  2021-06 -1.1%  2021-07 +5.4%  2021-08 +6.3%  2021-09 +1.6%  2021-10 -0.5%  2021-11 +0.2%  2021-12 +4.2%  2022-01 +7.7%  2022-02 -5.0%  2022-03 -1.0%  2022-04 +1.6%  2022-05 +2.7%  2022-06 -0.1%  2022-07 -5.3%  2022-08 +2.4%  2022-09 -8.9%  2022-10 +1.0%  2022-11 -2.9%  2022-12 +1.1%  2023-01 +7.3%  2023-02 -1.0%  2023-03 -0.3%  2023-04 -2.4%  2023-05 +3.6%  2023-06 -1.0%  2023-07 -9.0%  2023-08 +7.1%  2023-09 +1.0%  2023-10 +3.1%  2023-11 +0.9%  2023-12 -2.0%  2024-01 -5.6%  2024-02 +5.6%  2024-03 -5.1%  2024-04 +4.7%  2024-05 +1.2%  2024-06 +5.0%  2024-07 +1.5%  2024-08 +1.4%  2024-09 +8.5%  2024-10 -1.0%  2024-11 +3.5%  2024-12 +1.1%  2025-01 -10.6%  2025-02 +3.5%  2025-03 -2.5%  2025-04 +1.5%  2025-05 +6.9%  2025-06 +2.9%  2025-07 +7.1%  2025-08 -10.4%  2025-09 -1.2%  2025-10 -3.1%  2025-11 +6.5%  2025-12 +1.6%  2026-01 +6.1%  2026-02 -1.5%  2026-03 -8.5%  2026-04 -6.3%  2026-05 +5.1%  2026-06 +9.5%  2026-07 +0.2%  2026-08 +9.7%  2026-09 +3.7%  2026-10 +0.5%  2026-11 +5.6%

By coin (sum of net contributions): BTC +5.61%  ETH +13.98%  SOL +2.17%  XRP -4.79%  BNB +12.65%  DOGE +5.80%  ZEC +9.47%  HYPE -3.00%  NEAR +17.45%  SUI +6.01%  ADA +2.20%  LINK -12.75%

## How many tries

Full runs of 'sma50_take_profit' with distinct code/params/coins: 2. Distinct variants of all ideas run in the lab: 34.
Every extra variant is another lottery ticket: if you try enough worthless ideas, some will pass by luck. Treat a pass found after many tries as a lead for a forward paper test, not as proof.
