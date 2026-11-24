# Lab: sma50_take_profit (full run)

Run 2026-11-24 09:13:03 UTC. Research only: no orders are placed.

Hypothesis: Locking in a trade's profit once it reaches tp keeps more of the gains than holding
until the trend flips.

## Verdict: PASS

| criterion | result | detail |
|---|---|---|
| no look-ahead | yes | signal unchanged when later data is removed |
| net result > 0 | yes | +317.7% |
| beats 95th pct of random-timing controls | yes | +317.7% vs +29.8% (better than 100% of 200) |
| last third > 0 | yes | +121.4% |
| bootstrap 95% CI of mean daily return > 0 | yes | (+4.8%, +40.8%) a year |
| >= 60% of months positive | yes | 55/87 (need 53) |
| >= 20 entries | yes | 1530 |

## Detail

Kind: position | timeframe 1d (long history since 2019) | coins BTC, ETH, SOL, XRP, BNB, DOGE, ZEC, HYPE, NEAR, SUI, ADA, LINK | 2019-09-08 .. 2026-11-24 (2634 days)
Params: {"n": 50, "tp": 0.2} | file research/strategies/sma50_take_profit.py @ a8f201beabe8
Costs: 0.07% per side on every change, funding charged | weight 1/12 per coin, no leverage

| | net | CAGR | Sharpe | max DD | days |
|---|---|---|---|---|---|
| whole period | +317.7% | +21.9% | 0.95 | -22.0% | 2634 |
| first two thirds | +88.7% | +14.1% | 0.69 | -20.5% | 1756 |
| last third | +121.4% | +39.1% | 1.43 | -22.0% | 878 |

Entries 1530 | time in market 49% | costs paid +17.85% of capital | buy-and-hold of the same coins +1381.6%
Random-timing controls (200): median -42.9%, 95th pct +29.8%

Months: 2019-09 +0.0%  2019-10 -0.4%  2019-11 +0.2%  2019-12 +1.1%  2020-01 +2.1%  2020-02 +1.5%  2020-03 +3.4%  2020-04 +0.6%  2020-05 -1.4%  2020-06 +1.0%  2020-07 +3.7%  2020-08 -0.7%  2020-09 +2.2%  2020-10 -3.3%  2020-11 -4.4%  2020-12 +3.1%  2021-01 +3.9%  2021-02 +2.1%  2021-03 -8.7%  2021-04 +7.0%  2021-05 -10.6%  2021-06 +0.6%  2021-07 +7.2%  2021-08 +13.6%  2021-09 +0.9%  2021-10 +4.0%  2021-11 +2.9%  2021-12 +7.8%  2022-01 +9.7%  2022-02 -6.8%  2022-03 +1.6%  2022-04 +1.8%  2022-05 +7.5%  2022-06 +0.8%  2022-07 -6.1%  2022-08 +4.2%  2022-09 -8.4%  2022-10 +1.8%  2022-11 -4.0%  2022-12 +2.6%  2023-01 +9.6%  2023-02 -2.6%  2023-03 -0.0%  2023-04 -7.0%  2023-05 +2.9%  2023-06 +4.5%  2023-07 -7.8%  2023-08 +6.2%  2023-09 +1.4%  2023-10 +6.0%  2023-11 +6.1%  2023-12 -1.7%  2024-01 -5.8%  2024-02 +7.7%  2024-03 -1.4%  2024-04 +8.4%  2024-05 -4.7%  2024-06 +3.7%  2024-07 -2.1%  2024-08 -1.5%  2024-09 +7.0%  2024-10 -3.4%  2024-11 +7.3%  2024-12 +1.9%  2025-01 -10.8%  2025-02 +9.5%  2025-03 -5.3%  2025-04 +3.8%  2025-05 +12.0%  2025-06 +5.3%  2025-07 +12.6%  2025-08 -9.6%  2025-09 -0.8%  2025-10 -4.7%  2025-11 +14.6%  2025-12 +2.4%  2026-01 +6.8%  2026-02 +2.5%  2026-03 -7.9%  2026-04 -6.8%  2026-05 +6.8%  2026-06 +17.7%  2026-07 -1.8%  2026-08 +12.3%  2026-09 +4.9%  2026-10 -0.8%  2026-11 +19.2%

By coin (sum of net contributions): BTC +19.82%  ETH +20.00%  SOL +11.87%  XRP +5.25%  BNB +13.58%  DOGE +27.21%  ZEC +14.25%  HYPE -2.76%  NEAR +31.93%  SUI +17.74%  ADA +12.94%  LINK -8.47%

## How many tries

Full runs of 'sma50_take_profit' with distinct code/params/coins: 3. Distinct variants of all ideas run in the lab: 35.
Every extra variant is another lottery ticket: if you try enough worthless ideas, some will pass by luck. Treat a pass found after many tries as a lead for a forward paper test, not as proof.
