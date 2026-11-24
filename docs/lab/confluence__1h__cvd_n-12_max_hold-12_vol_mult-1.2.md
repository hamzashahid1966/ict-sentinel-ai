# Lab: confluence (full run)

Run 2026-11-24 05:26:14 UTC. Research only: no orders are placed.

Hypothesis: When momentum (EMA9>21), trend (EMA50), VWAP side, order flow and CVD, a strong
candle close, above-average volume and above-median volatility all agree, price continues in
that direction long enough to beat the 0.14% round-trip cost.

## Verdict: FAIL

| criterion | result | detail |
|---|---|---|
| no look-ahead | yes | signal unchanged when later data is removed |
| net result > 0 | NO | -4.6% |
| beats 95th pct of random-timing controls | NO | -4.6% vs -3.5% (better than 94% of 200) |
| last third > 0 | NO | -12.6% |
| bootstrap 95% CI of mean daily return > 0 | NO | (-67.3%, +67.7%) a year |
| >= 60% of months positive | NO | 2/7 (need 5) |
| >= 20 entries | yes | 1033 |

## Detail

Kind: position | timeframe 1h | coins BTC, ETH, SOL, XRP, BNB, DOGE, ZEC, HYPE, NEAR, SUI, ADA, LINK | 2026-05-24 .. 2026-11-23 (184 days)
Params: {"cvd_n": 12, "vol_mult": 1.2, "max_hold": 12} | file research/strategies/confluence.py @ 8efb7d995376
Costs: 0.07% per side on every change, funding charged | weight 1/12 per coin, no leverage

| | net | CAGR | Sharpe | max DD | days |
|---|---|---|---|---|---|
| whole period | -4.6% | -8.8% | -0.28 | -13.4% | 184 |
| first two thirds | +9.2% | +30.0% | 1.28 | -13.2% | 122 |
| last third | -12.6% | -54.7% | -3.02 | -12.2% | 62 |

Entries 1033 | time in market 20% | costs paid +12.05% of capital | buy-and-hold of the same coins -17.5%
Random-timing controls (200): median -13.1%, 95th pct -3.5%

Months: 2026-05 -0.7%  2026-06 -2.1%  2026-07 -3.7%  2026-08 +10.5%  2026-09 +2.0%  2026-10 -7.2%  2026-11 -2.6%

By coin (sum of net contributions): BTC -1.05%  ETH -0.91%  SOL +2.17%  XRP -1.78%  BNB +0.25%  DOGE -2.10%  ZEC +5.26%  HYPE +0.08%  NEAR +1.90%  SUI -2.60%  ADA -1.24%  LINK -3.02%

## How many tries

Full runs of 'confluence' with distinct code/params/coins: 3. Distinct variants of all ideas run in the lab: 7.
Every extra variant is another lottery ticket: if you try enough worthless ideas, some will pass by luck. Treat a pass found after many tries as a lead for a forward paper test, not as proof.
