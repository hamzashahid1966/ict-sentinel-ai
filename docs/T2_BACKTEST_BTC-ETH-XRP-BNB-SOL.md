# T2 backtest, trade by trade (2020-01-01 .. 2026-11-23)

Coins: BTC, ETH, SOL, XRP, BNB (not the paper test's 12).
T2 = the strategy in the forward paper test: once a day, each coin is long above its 50-day average and short below it; equal money in each listed coin; 0.07% per side; funding charged. Generated 2026-11-24 08:41 UTC by `python -m research.t2_backtest`. The coin list is chosen today (survivorship bias: coins that died are not in it).

## $1,000 over the whole period

| | T2 | buy and hold (same coins) |
|---|---|---|
| end value | $13,447 | $22,902 |
| total | +1245% | +2190% |
| worst drop from a peak | -63.5% (2022-06-18 to 2023-08-05, recovered 2026-02-04) | -78.6% (2021-11-08 to 2022-11-09) |
| longest time below a previous peak | 1326 days | 1098 days |
| fees paid | +26.6% of capital (simple sum) | +3.0% |
| funding | -63.0% (simple sum) | -58.0% |

## Each calendar year

| year | T2 | buy and hold | T2 trades opened | T2 win rate |
|---|---|---|---|---|
| 2020 | +59.3% | +152.5% | 87 | 24% |
| 2021 | +265.7% | +772.1% | 93 | 26% |
| 2022 | -15.5% | -68.0% | 106 | 21% |
| 2023 | +22.8% | +173.6% | 114 | 26% |
| 2024 | +12.5% | +112.0% | 112 | 22% |
| 2025 | +30.2% | -6.7% | 116 | 23% |
| 2026 | +51.8% | -40.0% | 94 | 22% |

## Months

Positive months: 43 of 83. Average month: +4.8%; median month: +2.2%.

Best: 2021-02 +81.9% | 2021-04 +78.5% | 2021-08 +59.6% | 2024-11 +54.0% | 2022-06 +35.9%

Worst: 2021-05 -32.5% | 2022-02 -28.8% | 2022-11 -23.3% | 2022-07 -22.9% | 2020-09 -22.7%

## Recent periods (T2 vs buy and hold)

| last | T2 | buy and hold |
|---|---|---|
| 30 days | +28.8% | -27.0% |
| 90 days | +37.0% | -27.0% |
| 180 days | +73.2% | -18.4% |
| 365 days | +50.2% | -40.8% |

## The trades

Closed trades: 717 over 7 years (about 104 a year across all coins, 21 per coin a year). Still open: 5.

| | count | share | average result | median days held |
|---|---|---|---|---|
| winners | 169 | 24% | +46.2% | 48 |
| losers | 548 | 76% | -4.4% | 3 |
| all | 717 | | +7.5% | 5 |

An average winner is 10.4x the size of an average loser. Trades held 1-3 days: 45%; held 30+ days: 19%.

- LONG: 359 trades, win rate 25%, average +15.3%
- SHORT: 358 trades, win rate 22%, average -0.3%

### Per coin

| coin | trades | win rate | average | best | worst | share of T2's profit |
|---|---|---|---|---|---|---|
| BTC | 134 | 25% | +4.6% | +389% | -12% | 22% |
| ETH | 125 | 26% | +4.2% | +268% | -18% | 23% |
| SOL | 122 | 23% | +17.7% | +1486% | -30% | 29% |
| XRP | 168 | 21% | +1.7% | +361% | -67% | 4% |
| BNB | 168 | 24% | +10.7% | +1628% | -14% | 23% |

### 10 biggest winners

| coin | side | entry | exit | days | entry price | exit price | result |
|---|---|---|---|---|---|---|---|
| BNB | LONG | 2020-12-13 | 2021-05-17 | 155 | 29.182 | 512.44 | +1628.0% |
| SOL | LONG | 2021-01-03 | 2021-05-19 | 136 | 2.1767 | 34.952 | +1486.4% |
| SOL | LONG | 2021-07-30 | 2021-11-26 | 119 | 32.35 | 192.423 | +486.6% |
| BTC | LONG | 2020-10-08 | 2021-04-18 | 192 | 10919.5 | 56140.1 | +389.1% |
| XRP | LONG | 2024-11-07 | 2025-02-02 | 87 | 0.5559 | 2.5784 | +360.6% |
| SOL | LONG | 2023-09-30 | 2024-01-22 | 114 | 21.348 | 83.883 | +288.8% |
| ETH | LONG | 2020-10-18 | 2021-02-25 | 130 | 378.29 | 1482.09 | +267.8% |
| BNB | LONG | 2023-12-08 | 2024-04-16 | 130 | 239.1 | 537.52 | +129.8% |
| XRP | LONG | 2021-03-25 | 2021-05-19 | 55 | 0.511 | 1.0578 | +92.7% |
| XRP | LONG | 2020-11-05 | 2020-12-22 | 47 | 0.2456 | 0.4452 | +78.3% |

### 10 biggest losers

| coin | side | entry | exit | days | entry price | exit price | result |
|---|---|---|---|---|---|---|---|
| XRP | SHORT | 2023-07-04 | 2023-07-13 | 9 | 0.487 | 0.8154 | -67.4% |
| SOL | LONG | 2021-05-20 | 2021-05-22 | 2 | 44.431 | 31.225 | -29.9% |
| SOL | SHORT | 2021-05-19 | 2021-05-20 | 1 | 34.952 | 44.431 | -27.2% |
| SOL | SHORT | 2021-05-22 | 2021-06-03 | 12 | 31.225 | 39.627 | -26.7% |
| XRP | LONG | 2023-07-13 | 2023-08-15 | 33 | 0.8154 | 0.6099 | -26.2% |
| XRP | SHORT | 2023-03-20 | 2023-03-21 | 1 | 0.3733 | 0.4694 | -25.9% |
| XRP | SHORT | 2024-08-05 | 2024-08-07 | 2 | 0.4887 | 0.6001 | -22.9% |
| SOL | SHORT | 2021-01-02 | 2021-01-03 | 1 | 1.7976 | 2.1767 | -21.8% |
| XRP | LONG | 2025-03-02 | 2025-03-03 | 1 | 2.9384 | 2.386 | -18.9% |
| ETH | SHORT | 2022-07-17 | 2022-07-18 | 1 | 1338.27 | 1580.12 | -18.2% |

### Last 20 closed trades

| coin | side | entry | exit | days | entry price | exit price | result |
|---|---|---|---|---|---|---|---|
| BNB | LONG | 2026-07-30 | 2026-08-01 | 2 | 592.38 | 575.46 | -3.0% |
| BTC | SHORT | 2026-07-31 | 2026-08-02 | 2 | 62859.9 | 63550 | -1.2% |
| BNB | SHORT | 2026-08-01 | 2026-08-02 | 1 | 575.46 | 588.86 | -2.4% |
| SOL | SHORT | 2026-07-28 | 2026-08-08 | 11 | 73.77 | 76 | -3.0% |
| SOL | LONG | 2026-08-08 | 2026-08-12 | 4 | 76 | 75.59 | -0.7% |
| SOL | SHORT | 2026-08-12 | 2026-08-13 | 1 | 75.59 | 76.23 | -1.0% |
| BTC | LONG | 2026-08-02 | 2026-08-14 | 12 | 63550 | 63015 | -1.2% |
| SOL | LONG | 2026-08-13 | 2026-08-14 | 1 | 76.23 | 75.37 | -1.3% |
| BTC | SHORT | 2026-08-14 | 2026-08-17 | 3 | 63015 | 64504.1 | -2.5% |
| SOL | SHORT | 2026-08-14 | 2026-08-18 | 4 | 75.37 | 77.03 | -2.3% |
| XRP | SHORT | 2026-07-23 | 2026-08-19 | 27 | 1.1073 | 1.1054 | +0.2% |
| XRP | LONG | 2026-08-19 | 2026-10-07 | 49 | 1.1054 | 1.4204 | +27.7% |
| ETH | LONG | 2026-07-10 | 2026-10-08 | 90 | 1796.03 | 2474.01 | +36.5% |
| BNB | LONG | 2026-08-02 | 2026-10-08 | 67 | 588.86 | 735.77 | +24.0% |
| BNB | SHORT | 2026-10-08 | 2026-10-09 | 1 | 735.77 | 742.2 | -1.0% |
| SOL | LONG | 2026-08-18 | 2026-10-12 | 55 | 77.03 | 105.7 | +36.5% |
| BNB | LONG | 2026-10-09 | 2026-10-12 | 3 | 742.2 | 733.18 | -1.4% |
| BTC | LONG | 2026-08-17 | 2026-10-22 | 66 | 64504.1 | 81384.6 | +25.0% |
| BNB | SHORT | 2026-10-12 | 2026-10-28 | 16 | 733.18 | 760.14 | -3.7% |
| BNB | LONG | 2026-10-28 | 2026-10-29 | 1 | 760.14 | 697.96 | -8.3% |

### Open now (marked at the last complete day's close, entry cost only)

| coin | side | entry | exit | days | entry price | exit price | result |
|---|---|---|---|---|---|---|---|
| BTC | SHORT | 2026-10-22 | open | 32 | 81384.6 | 61239.9 | +25.3% |
| ETH | SHORT | 2026-10-08 | open | 46 | 2474.01 | 1709.85 | +31.2% |
| SOL | SHORT | 2026-10-12 | open | 42 | 105.7 | 71.98 | +32.2% |
| XRP | SHORT | 2026-10-07 | open | 47 | 1.4204 | 0.9401 | +34.3% |
| BNB | SHORT | 2026-10-29 | open | 25 | 697.96 | 556.68 | +20.4% |

