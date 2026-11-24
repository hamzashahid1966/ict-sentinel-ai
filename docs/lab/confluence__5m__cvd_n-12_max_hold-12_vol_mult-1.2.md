# Lab: confluence (full run)

Run 2026-11-24 05:26:04 UTC. Research only: no orders are placed.

Hypothesis: When momentum (EMA9>21), trend (EMA50), VWAP side, order flow and CVD, a strong
candle close, above-average volume and above-median volatility all agree, price continues in
that direction long enough to beat the 0.14% round-trip cost.

## Verdict: FAIL

| criterion | result | detail |
|---|---|---|
| no look-ahead | yes | signal unchanged when later data is removed |
| net result > 0 | NO | -74.4% |
| beats 95th pct of random-timing controls | NO | -74.4% vs -67.4% (better than 4% of 200) |
| last third > 0 | NO | -35.4% |
| bootstrap 95% CI of mean daily return > 0 | NO | (-318.8%, -213.3%) a year |
| >= 60% of months positive | NO | 0/7 (need 5) |
| >= 20 entries | yes | 10594 |

## Detail

Kind: position | timeframe 5m | coins BTC, ETH, SOL, XRP, BNB, DOGE, ZEC, HYPE, NEAR, SUI, ADA, LINK | 2026-05-24 .. 2026-11-23 (184 days)
Params: {"cvd_n": 12, "vol_mult": 1.2, "max_hold": 12} | file research/strategies/confluence.py @ 8efb7d995376
Costs: 0.07% per side on every change, funding charged | weight 1/12 per coin, no leverage

| | net | CAGR | Sharpe | max DD | days |
|---|---|---|---|---|---|
| whole period | -74.4% | -93.3% | -13.49 | -74.3% | 184 |
| first two thirds | -60.4% | -93.7% | -15.38 | -60.2% | 122 |
| last third | -35.4% | -92.4% | -10.92 | -32.9% | 62 |

Entries 10594 | time in market 16% | costs paid +123.60% of capital | buy-and-hold of the same coins -16.9%
Random-timing controls (200): median -71.2%, 95th pct -67.4%

Months: 2026-05 -7.0%  2026-06 -24.0%  2026-07 -18.0%  2026-08 -18.9%  2026-09 -23.5%  2026-10 -19.7%  2026-11 -11.4%

By coin (sum of net contributions): BTC -12.06%  ETH -11.78%  SOL -13.84%  XRP -10.73%  BNB -11.11%  DOGE -12.56%  ZEC -5.96%  HYPE -3.94%  NEAR -17.90%  SUI -15.71%  ADA -8.22%  LINK -11.13%

## How many tries

Full runs of 'confluence' with distinct code/params/coins: 1. Distinct variants of all ideas run in the lab: 5.
Every extra variant is another lottery ticket: if you try enough worthless ideas, some will pass by luck. Treat a pass found after many tries as a lead for a forward paper test, not as proof.
