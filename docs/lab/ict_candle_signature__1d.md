# Lab: ict_candle_signature (full run)

Run 2026-11-24 07:50:39 UTC. Research only: no orders are placed.

Hypothesis: A candle that sweeps the previous candle's high/low and closes back inside predicts a
reversal on the next candle; one that closes beyond it predicts continuation. Following the call
earns more than costs and beats random timing.

## Verdict: FAIL

| criterion | result | detail |
|---|---|---|
| no look-ahead | yes | signal unchanged when later data is removed |
| net result > 0 | NO | -98.2% |
| beats 95th pct of random-timing controls | NO | -98.2% vs -54.6% (better than 0% of 200) |
| last third > 0 | NO | -15.6% |
| bootstrap 95% CI of mean daily return > 0 | NO | (-78.1%, -17.3%) a year |
| >= 60% of months positive | NO | 29/87 (need 53) |
| >= 20 entries | yes | 13045 |

## Detail

Kind: position | timeframe 1d (long daily history) | coins BTC, ETH, SOL, XRP, BNB, DOGE, ZEC, HYPE, NEAR, SUI, ADA, LINK | 2019-09-08 .. 2026-11-23 (2633 days)
Params: {} | file research/strategies/ict_candle_signature.py @ 81778415e5ec
Costs: 0.07% per side on every change, funding charged | weight 1/12 per coin, no leverage

| | net | CAGR | Sharpe | max DD | days |
|---|---|---|---|---|---|
| whole period | -98.2% | -42.6% | -1.10 | -98.4% | 2633 |
| first two thirds | -97.8% | -54.9% | -1.63 | -98.2% | 1755 |
| last third | -15.6% | -6.8% | 0.03 | -48.1% | 878 |

Entries 13045 | time in market 81% | costs paid +152.19% of capital | buy-and-hold of the same coins +1369.9%
Random-timing controls (200): median -85.5%, 95th pct -54.6%

Months: 2019-09 +1.8%  2019-10 +0.5%  2019-11 +0.4%  2019-12 -2.4%  2020-01 -5.0%  2020-02 +10.5%  2020-03 -23.1%  2020-04 -2.8%  2020-05 -7.4%  2020-06 -11.7%  2020-07 -1.6%  2020-08 -0.8%  2020-09 -12.7%  2020-10 -6.9%  2020-11 -8.8%  2020-12 -21.4%  2021-01 -38.7%  2021-02 +21.1%  2021-03 -14.1%  2021-04 +10.8%  2021-05 -46.2%  2021-06 -1.7%  2021-07 +0.2%  2021-08 -5.1%  2021-09 +2.9%  2021-10 +2.5%  2021-11 -6.6%  2021-12 +1.5%  2022-01 +8.7%  2022-02 -5.1%  2022-03 -11.2%  2022-04 -12.2%  2022-05 -20.4%  2022-06 -1.8%  2022-07 -7.1%  2022-08 -2.3%  2022-09 -20.6%  2022-10 -3.7%  2022-11 +0.1%  2022-12 -3.0%  2023-01 -4.7%  2023-02 -1.8%  2023-03 -9.9%  2023-04 -8.3%  2023-05 -1.2%  2023-06 -11.2%  2023-07 +0.3%  2023-08 -5.1%  2023-09 -3.4%  2023-10 +5.5%  2023-11 -9.3%  2023-12 -9.5%  2024-01 -4.6%  2024-02 -1.0%  2024-03 -18.6%  2024-04 +11.6%  2024-05 -16.3%  2024-06 -1.7%  2024-07 +10.6%  2024-08 +5.3%  2024-09 -5.8%  2024-10 +8.7%  2024-11 +15.1%  2024-12 +0.9%  2025-01 +7.3%  2025-02 -6.6%  2025-03 -6.1%  2025-04 -18.6%  2025-05 -7.6%  2025-06 +16.8%  2025-07 +5.7%  2025-08 -6.3%  2025-09 +0.3%  2025-10 +10.1%  2025-11 +10.5%  2025-12 -12.2%  2026-01 +11.4%  2026-02 -12.4%  2026-03 -1.0%  2026-04 -21.0%  2026-05 +5.5%  2026-06 +17.5%  2026-07 -2.1%  2026-08 -1.4%  2026-09 -1.6%  2026-10 -11.1%  2026-11 -10.2%

By coin (sum of net contributions): BTC -24.44%  ETH -37.69%  SOL -27.89%  XRP -34.19%  BNB -25.63%  DOGE -54.31%  ZEC -4.23%  HYPE -3.44%  NEAR -46.41%  SUI -10.43%  ADA -36.03%  LINK -28.00%

## How many tries

Full runs of 'ict_candle_signature' with distinct code/params/coins: 1. Distinct variants of all ideas run in the lab: 21.
Every extra variant is another lottery ticket: if you try enough worthless ideas, some will pass by luck. Treat a pass found after many tries as a lead for a forward paper test, not as proof.
