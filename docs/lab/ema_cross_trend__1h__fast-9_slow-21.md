# Lab: ema_cross_trend (full run)

Run 2026-11-24 07:20:12 UTC. Research only: no orders are placed.

Hypothesis: Holding the side of the EMA9/21 cross captures multi-day crypto trends and earns
more than the trading costs, beating the same trades placed at random times.

## Verdict: FAIL

| criterion | result | detail |
|---|---|---|
| no look-ahead | yes | signal unchanged when later data is removed |
| net result > 0 | NO | -16.6% |
| beats 95th pct of random-timing controls | NO | -16.6% vs -7.4% (better than 80% of 200) |
| last third > 0 | NO | -29.7% |
| bootstrap 95% CI of mean daily return > 0 | NO | (-157.9%, +142.8%) a year |
| >= 60% of months positive | NO | 3/7 (need 5) |
| >= 20 entries | yes | 2335 |

## Detail

Kind: position | timeframe 1h | coins BTC, ETH, SOL, XRP, BNB, DOGE, ZEC, HYPE, NEAR, SUI, ADA, LINK | 2026-05-24 .. 2026-11-23 (184 days)
Params: {"fast": 9, "slow": 21} | file research/strategies/ema_cross_trend.py @ 01819142f587
Costs: 0.07% per side on every change, funding charged | weight 1/12 per coin, no leverage

| | net | CAGR | Sharpe | max DD | days |
|---|---|---|---|---|---|
| whole period | -16.6% | -30.2% | -0.46 | -34.6% | 184 |
| first two thirds | +18.6% | +66.7% | 1.29 | -25.0% | 122 |
| last third | -29.7% | -87.4% | -3.68 | -31.5% | 62 |

Entries 2335 | time in market 100% | costs paid +27.24% of capital | buy-and-hold of the same coins -17.5%
Random-timing controls (200): median -27.5%, 95th pct -7.4%

Months: 2026-05 -2.2%  2026-06 +10.7%  2026-07 -3.4%  2026-08 +0.3%  2026-09 +8.3%  2026-10 -18.7%  2026-11 -9.6%

By coin (sum of net contributions): BTC -1.09%  ETH -1.41%  SOL +2.18%  XRP -1.27%  BNB +0.53%  DOGE -4.96%  ZEC +5.35%  HYPE -3.11%  NEAR +1.54%  SUI -5.83%  ADA -2.90%  LINK -1.70%

## How many tries

Full runs of 'ema_cross_trend' with distinct code/params/coins: 3. Distinct variants of all ideas run in the lab: 20.
Every extra variant is another lottery ticket: if you try enough worthless ideas, some will pass by luck. Treat a pass found after many tries as a lead for a forward paper test, not as proof.
