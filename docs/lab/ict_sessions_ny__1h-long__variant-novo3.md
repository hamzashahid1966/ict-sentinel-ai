# Lab: ict_sessions_ny (full run)

Run 2026-11-24 07:57:52 UTC. Research only: no orders are placed.

Hypothesis: The closure signature of a session candle (6-hour quarter, or London vs Asia on the
4-hour cycle) predicts the direction of the next session candle well enough to beat costs and
random timing.

## Verdict: FAIL

| criterion | result | detail |
|---|---|---|
| no look-ahead | yes | signal unchanged when later data is removed |
| net result > 0 | NO | -93.0% |
| beats 95th pct of random-timing controls | NO | -93.0% vs -88.9% (better than 50% of 200) |
| last third > 0 | NO | -52.6% |
| bootstrap 95% CI of mean daily return > 0 | NO | (-49.1%, -19.4%) a year |
| >= 60% of months positive | NO | 24/87 (need 53) |
| >= 20 entries | yes | 21663 |

## Detail

Kind: position | timeframe 1h (long daily history) | coins BTC, ETH, SOL, XRP, BNB, DOGE, ZEC, HYPE, NEAR, SUI, ADA, LINK | 2019-09-08 .. 2026-11-24 (2635 days)
Params: {"variant": "novo3"} | file research/strategies/ict_sessions_ny.py @ 77a859aca0bf
Costs: 0.07% per side on every change, funding charged | weight 1/12 per coin, no leverage

| | net | CAGR | Sharpe | max DD | days |
|---|---|---|---|---|---|
| whole period | -93.0% | -30.8% | -1.67 | -94.5% | 2635 |
| first two thirds | -85.2% | -32.8% | -1.85 | -88.0% | 1756 |
| last third | -52.6% | -26.7% | -1.34 | -56.7% | 879 |

Entries 21663 | time in market 14% | costs paid +252.74% of capital | buy-and-hold of the same coins +1239.5%
Random-timing controls (200): median -92.9%, 95th pct -88.9%

Months: 2019-09 +0.5%  2019-10 +0.7%  2019-11 +0.6%  2019-12 -0.3%  2020-01 -1.6%  2020-02 -1.2%  2020-03 +6.3%  2020-04 +3.2%  2020-05 -0.5%  2020-06 +1.6%  2020-07 -1.8%  2020-08 +5.0%  2020-09 -4.3%  2020-10 +2.5%  2020-11 +7.1%  2020-12 -4.8%  2021-01 -13.5%  2021-02 +3.2%  2021-03 -10.2%  2021-04 +1.0%  2021-05 -26.6%  2021-06 -6.6%  2021-07 -4.0%  2021-08 -1.9%  2021-09 -7.2%  2021-10 +3.3%  2021-11 -2.0%  2021-12 -8.5%  2022-01 -8.2%  2022-02 -14.3%  2022-03 -9.2%  2022-04 +0.7%  2022-05 -11.1%  2022-06 +5.7%  2022-07 -8.6%  2022-08 -3.1%  2022-09 -1.5%  2022-10 -0.5%  2022-11 -2.6%  2022-12 -0.5%  2023-01 -5.4%  2023-02 -5.3%  2023-03 -3.2%  2023-04 -3.7%  2023-05 -6.1%  2023-06 -6.9%  2023-07 +0.3%  2023-08 -0.1%  2023-09 -5.9%  2023-10 -10.1%  2023-11 -1.9%  2023-12 +0.7%  2024-01 -5.2%  2024-02 -6.9%  2024-03 -5.6%  2024-04 -0.6%  2024-05 -0.8%  2024-06 +2.4%  2024-07 -0.9%  2024-08 -2.1%  2024-09 -6.7%  2024-10 -3.3%  2024-11 -7.0%  2024-12 +4.2%  2025-01 +3.1%  2025-02 -11.4%  2025-03 -14.5%  2025-04 +1.4%  2025-05 +0.1%  2025-06 -5.9%  2025-07 -5.7%  2025-08 -9.8%  2025-09 -8.1%  2025-10 -1.4%  2025-11 -1.1%  2025-12 -1.8%  2026-01 -1.9%  2026-02 +17.1%  2026-03 -1.6%  2026-04 -3.3%  2026-05 -9.2%  2026-06 -1.5%  2026-07 +0.4%  2026-08 -2.7%  2026-09 -1.8%  2026-10 +9.7%  2026-11 -2.6%

By coin (sum of net contributions): BTC -18.90%  ETH -27.15%  SOL -27.10%  XRP -19.03%  BNB -24.37%  DOGE -24.36%  ZEC -13.03%  HYPE -6.51%  NEAR -33.53%  SUI -18.20%  ADA -23.54%  LINK -14.44%

## How many tries

Full runs of 'ict_sessions_ny' with distinct code/params/coins: 3. Distinct variants of all ideas run in the lab: 27.
Every extra variant is another lottery ticket: if you try enough worthless ideas, some will pass by luck. Treat a pass found after many tries as a lead for a forward paper test, not as proof.
