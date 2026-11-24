# Lab: confluence (full run)

Run 2026-11-24 05:26:10 UTC. Research only: no orders are placed.

Hypothesis: When momentum (EMA9>21), trend (EMA50), VWAP side, order flow and CVD, a strong
candle close, above-average volume and above-median volatility all agree, price continues in
that direction long enough to beat the 0.14% round-trip cost.

## Verdict: FAIL

| criterion | result | detail |
|---|---|---|
| no look-ahead | yes | signal unchanged when later data is removed |
| net result > 0 | NO | -36.5% |
| beats 95th pct of random-timing controls | NO | -36.5% vs -28.9% (better than 50% of 200) |
| last third > 0 | NO | -9.9% |
| bootstrap 95% CI of mean daily return > 0 | NO | (-136.9%, -40.1%) a year |
| >= 60% of months positive | NO | 0/7 (need 5) |
| >= 20 entries | yes | 3859 |

## Detail

Kind: position | timeframe 15m | coins BTC, ETH, SOL, XRP, BNB, DOGE, ZEC, HYPE, NEAR, SUI, ADA, LINK | 2026-05-24 .. 2026-11-23 (184 days)
Params: {"cvd_n": 12, "vol_mult": 1.2, "max_hold": 12} | file research/strategies/confluence.py @ 8efb7d995376
Costs: 0.07% per side on every change, funding charged | weight 1/12 per coin, no leverage

| | net | CAGR | Sharpe | max DD | days |
|---|---|---|---|---|---|
| whole period | -36.5% | -59.4% | -4.59 | -36.9% | 184 |
| first two thirds | -29.5% | -64.8% | -5.52 | -30.0% | 122 |
| last third | -9.9% | -46.0% | -2.93 | -11.3% | 62 |

Entries 3859 | time in market 18% | costs paid +45.02% of capital | buy-and-hold of the same coins -17.1%
Random-timing controls (200): median -36.5%, 95th pct -28.9%

Months: 2026-05 -1.7%  2026-06 -17.4%  2026-07 -8.3%  2026-08 -2.0%  2026-09 -7.0%  2026-10 -0.9%  2026-11 -5.6%

By coin (sum of net contributions): BTC -5.62%  ETH -3.12%  SOL -4.44%  XRP -3.36%  BNB -3.65%  DOGE -5.02%  ZEC +0.42%  HYPE -0.60%  NEAR -7.43%  SUI -5.70%  ADA -1.98%  LINK -3.35%

## How many tries

Full runs of 'confluence' with distinct code/params/coins: 2. Distinct variants of all ideas run in the lab: 6.
Every extra variant is another lottery ticket: if you try enough worthless ideas, some will pass by luck. Treat a pass found after many tries as a lead for a forward paper test, not as proof.
