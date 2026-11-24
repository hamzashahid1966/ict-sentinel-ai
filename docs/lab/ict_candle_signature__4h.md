# Lab: ict_candle_signature (full run)

Run 2026-11-24 07:50:42 UTC. Research only: no orders are placed.

Hypothesis: A candle that sweeps the previous candle's high/low and closes back inside predicts a
reversal on the next candle; one that closes beyond it predicts continuation. Following the call
earns more than costs and beats random timing.

## Verdict: FAIL

| criterion | result | detail |
|---|---|---|
| no look-ahead | yes | signal unchanged when later data is removed |
| net result > 0 | NO | -62.8% |
| beats 95th pct of random-timing controls | NO | -62.8% vs -39.9% (better than 2% of 200) |
| last third > 0 | NO | -23.3% |
| bootstrap 95% CI of mean daily return > 0 | NO | (-274.9%, -115.9%) a year |
| >= 60% of months positive | NO | 0/7 (need 5) |
| >= 20 entries | yes | 6225 |

## Detail

Kind: position | timeframe 4h | coins BTC, ETH, SOL, XRP, BNB, DOGE, ZEC, HYPE, NEAR, SUI, ADA, LINK | 2026-05-24 .. 2026-11-23 (184 days)
Params: {} | file research/strategies/ict_candle_signature.py @ 81778415e5ec
Costs: 0.07% per side on every change, funding charged | weight 1/12 per coin, no leverage

| | net | CAGR | Sharpe | max DD | days |
|---|---|---|---|---|---|
| whole period | -62.8% | -85.9% | -5.92 | -64.1% | 184 |
| first two thirds | -51.5% | -88.5% | -8.10 | -52.7% | 122 |
| last third | -23.3% | -79.0% | -3.56 | -26.0% | 62 |

Entries 6225 | time in market 79% | costs paid +72.62% of capital | buy-and-hold of the same coins -17.9%
Random-timing controls (200): median -52.5%, 95th pct -39.9%

Months: 2026-05 -3.0%  2026-06 -32.0%  2026-07 -15.2%  2026-08 -1.9%  2026-09 -19.1%  2026-10 -8.5%  2026-11 -8.4%

By coin (sum of net contributions): BTC -8.05%  ETH -11.25%  SOL -7.24%  XRP -11.53%  BNB -7.11%  DOGE -8.95%  ZEC -3.69%  HYPE -0.98%  NEAR -7.80%  SUI -9.48%  ADA -7.57%  LINK -12.52%

## How many tries

Full runs of 'ict_candle_signature' with distinct code/params/coins: 2. Distinct variants of all ideas run in the lab: 22.
Every extra variant is another lottery ticket: if you try enough worthless ideas, some will pass by luck. Treat a pass found after many tries as a lead for a forward paper test, not as proof.
