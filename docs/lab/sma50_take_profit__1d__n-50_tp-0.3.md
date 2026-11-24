# Lab: sma50_take_profit (full run)

Run 2026-11-24 09:13:04 UTC. Research only: no orders are placed.

Hypothesis: Locking in a trade's profit once it reaches tp keeps more of the gains than holding
until the trend flips.

## Verdict: FAIL

| criterion | result | detail |
|---|---|---|
| no look-ahead | yes | signal unchanged when later data is removed |
| net result > 0 | yes | +380.4% |
| beats 95th pct of random-timing controls | yes | +380.4% vs +14.6% (better than 100% of 200) |
| last third > 0 | yes | +120.2% |
| bootstrap 95% CI of mean daily return > 0 | yes | (+2.8%, +50.7%) a year |
| >= 60% of months positive | NO | 51/87 (need 53) |
| >= 20 entries | yes | 1530 |

## Detail

Kind: position | timeframe 1d (long history since 2019) | coins BTC, ETH, SOL, XRP, BNB, DOGE, ZEC, HYPE, NEAR, SUI, ADA, LINK | 2019-09-08 .. 2026-11-24 (2634 days)
Params: {"n": 50, "tp": 0.3} | file research/strategies/sma50_take_profit.py @ a8f201beabe8
Costs: 0.07% per side on every change, funding charged | weight 1/12 per coin, no leverage

| | net | CAGR | Sharpe | max DD | days |
|---|---|---|---|---|---|
| whole period | +380.4% | +24.3% | 0.85 | -31.0% | 2634 |
| first two thirds | +118.1% | +17.6% | 0.69 | -31.0% | 1756 |
| last third | +120.2% | +38.8% | 1.13 | -29.5% | 878 |

Entries 1530 | time in market 62% | costs paid +17.85% of capital | buy-and-hold of the same coins +1381.6%
Random-timing controls (200): median -57.7%, 95th pct +14.6%

Months: 2019-09 +0.0%  2019-10 -0.4%  2019-11 +0.2%  2019-12 +0.3%  2020-01 +2.3%  2020-02 +2.4%  2020-03 +3.4%  2020-04 -0.5%  2020-05 +2.4%  2020-06 +1.0%  2020-07 +4.2%  2020-08 +1.4%  2020-09 +5.7%  2020-10 -3.2%  2020-11 -0.2%  2020-12 +4.5%  2021-01 +7.6%  2021-02 +2.1%  2021-03 -10.0%  2021-04 +13.3%  2021-05 -23.9%  2021-06 +13.6%  2021-07 +7.1%  2021-08 +18.4%  2021-09 -0.3%  2021-10 -0.8%  2021-11 +1.5%  2021-12 +7.3%  2022-01 +15.8%  2022-02 -5.3%  2022-03 +1.6%  2022-04 -0.9%  2022-05 +20.4%  2022-06 +1.9%  2022-07 -8.6%  2022-08 -1.2%  2022-09 -10.3%  2022-10 +1.5%  2022-11 -7.0%  2022-12 +4.8%  2023-01 +8.8%  2023-02 -4.1%  2023-03 -2.9%  2023-04 -9.3%  2023-05 +2.2%  2023-06 +4.2%  2023-07 -7.7%  2023-08 +7.2%  2023-09 -0.9%  2023-10 +6.3%  2023-11 +9.0%  2023-12 -1.0%  2024-01 -5.0%  2024-02 +9.6%  2024-03 +0.3%  2024-04 +9.5%  2024-05 -7.8%  2024-06 +1.7%  2024-07 -4.4%  2024-08 -2.6%  2024-09 +5.1%  2024-10 -6.0%  2024-11 +14.7%  2024-12 +1.8%  2025-01 -12.5%  2025-02 +17.2%  2025-03 -8.2%  2025-04 +3.4%  2025-05 +8.3%  2025-06 +1.0%  2025-07 +6.0%  2025-08 -11.1%  2025-09 -3.1%  2025-10 -6.5%  2025-11 +15.2%  2025-12 -0.8%  2026-01 +6.8%  2026-02 +15.1%  2026-03 -9.8%  2026-04 -5.7%  2026-05 +7.2%  2026-06 +17.4%  2026-07 -7.7%  2026-08 +14.1%  2026-09 +11.7%  2026-10 -0.1%  2026-11 +30.5%

By coin (sum of net contributions): BTC +27.78%  ETH +31.79%  SOL +5.38%  XRP +10.18%  BNB +12.15%  DOGE +15.42%  ZEC +14.15%  HYPE -1.28%  NEAR +33.23%  SUI +20.05%  ADA +25.52%  LINK -1.34%

## How many tries

Full runs of 'sma50_take_profit' with distinct code/params/coins: 4. Distinct variants of all ideas run in the lab: 36.
Every extra variant is another lottery ticket: if you try enough worthless ideas, some will pass by luck. Treat a pass found after many tries as a lead for a forward paper test, not as proof.
