# Lab: rsi_reversion_1h (full run)

Run 2026-11-24 05:22:09 UTC. Research only: no orders are placed.

Hypothesis: Hourly overshoots revert: after RSI(14) goes below 30 (above 70) price tends to
bounce (fall back) by more than the round-trip cost of 0.14%.

## Verdict: FAIL

| criterion | result | detail |
|---|---|---|
| no look-ahead | yes | signal unchanged when later data is removed |
| net result > 0 | NO | -19.6% |
| beats 95th pct of random-timing controls | NO | -19.6% vs +10.6% (better than 3% of 200) |
| last third > 0 | yes | +11.8% |
| bootstrap 95% CI of mean daily return > 0 | NO | (-152.1%, +52.2%) a year |
| >= 60% of months positive | NO | 3/7 (need 5) |
| >= 20 entries | yes | 717 |

## Detail

Kind: position | timeframe 1h | coins BTC, ETH, SOL, XRP, BNB, DOGE, ZEC, HYPE, NEAR, SUI, ADA, LINK | 2026-05-24 .. 2026-11-23 (184 days)
Params: {"n": 14, "low": 30, "high": 70} | file research/strategies/rsi_reversion_1h.py @ d6e4e7896d99
Costs: 0.07% per side on every change, funding charged | weight 1/12 per coin, no leverage

| | net | CAGR | Sharpe | max DD | days |
|---|---|---|---|---|---|
| whole period | -19.6% | -35.2% | -1.23 | -28.6% | 184 |
| first two thirds | -28.1% | -62.7% | -2.87 | -28.5% | 122 |
| last third | +11.8% | +92.3% | 2.52 | -7.6% | 62 |

Entries 717 | time in market 34% | costs paid +8.37% of capital | buy-and-hold of the same coins -17.5%
Random-timing controls (200): median -5.0%, 95th pct +10.6%

Months: 2026-05 -0.6%  2026-06 -7.9%  2026-07 +0.5%  2026-08 -14.7%  2026-09 -5.5%  2026-10 +7.9%  2026-11 +0.3%

By coin (sum of net contributions): BTC -1.61%  ETH -3.04%  SOL -0.75%  XRP -2.82%  BNB -1.46%  DOGE -1.18%  ZEC -4.55%  HYPE +0.79%  NEAR +1.17%  SUI +0.65%  ADA -5.55%  LINK -0.79%

## How many tries

Full runs of 'rsi_reversion_1h' with distinct code/params/coins: 1. Distinct variants of all ideas run in the lab: 2.
Every extra variant is another lottery ticket: if you try enough worthless ideas, some will pass by luck. Treat a pass found after many tries as a lead for a forward paper test, not as proof.
