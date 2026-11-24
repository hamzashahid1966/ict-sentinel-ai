# Lab: ict_candle_signature (full run)

Run 2026-11-24 07:50:45 UTC. Research only: no orders are placed.

Hypothesis: A candle that sweeps the previous candle's high/low and closes back inside predicts a
reversal on the next candle; one that closes beyond it predicts continuation. Following the call
earns more than costs and beats random timing.

## Verdict: FAIL

| criterion | result | detail |
|---|---|---|
| no look-ahead | yes | signal unchanged when later data is removed |
| net result > 0 | NO | -94.7% |
| beats 95th pct of random-timing controls | NO | -94.7% vs -93.0% (better than 32% of 200) |
| last third > 0 | NO | -58.1% |
| bootstrap 95% CI of mean daily return > 0 | NO | (-652.0%, -501.7%) a year |
| >= 60% of months positive | NO | 0/7 (need 5) |
| >= 20 entries | yes | 24492 |

## Detail

Kind: position | timeframe 1h | coins BTC, ETH, SOL, XRP, BNB, DOGE, ZEC, HYPE, NEAR, SUI, ADA, LINK | 2026-05-24 .. 2026-11-23 (184 days)
Params: {} | file research/strategies/ict_candle_signature.py @ 81778415e5ec
Costs: 0.07% per side on every change, funding charged | weight 1/12 per coin, no leverage

| | net | CAGR | Sharpe | max DD | days |
|---|---|---|---|---|---|
| whole period | -94.7% | -99.7% | -17.19 | -94.7% | 184 |
| first two thirds | -87.3% | -99.8% | -17.82 | -87.3% | 122 |
| last third | -58.1% | -99.4% | -16.03 | -57.7% | 62 |

Entries 24492 | time in market 81% | costs paid +285.74% of capital | buy-and-hold of the same coins -17.5%
Random-timing controls (200): median -94.4%, 95th pct -93.0%

Months: 2026-05 -6.7%  2026-06 -47.1%  2026-07 -38.1%  2026-08 -40.3%  2026-09 -39.9%  2026-10 -33.8%  2026-11 -26.9%

By coin (sum of net contributions): BTC -25.71%  ETH -23.69%  SOL -26.12%  XRP -29.28%  BNB -23.81%  DOGE -22.68%  ZEC -25.42%  HYPE -8.93%  NEAR -30.48%  SUI -26.21%  ADA -24.98%  LINK -22.44%

## How many tries

Full runs of 'ict_candle_signature' with distinct code/params/coins: 3. Distinct variants of all ideas run in the lab: 23.
Every extra variant is another lottery ticket: if you try enough worthless ideas, some will pass by luck. Treat a pass found after many tries as a lead for a forward paper test, not as proof.
