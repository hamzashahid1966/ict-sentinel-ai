# Slow strategies on Binance perps (2020-01-01 .. 2026-11-22)

Pre-registered rules are in the header of `research/slow_strategies.py`. Costs: perp 0.07% per side, spot 0.12% per side; funding charged on every settlement. Universe chosen today (survivorship bias; shared by the controls and buy and hold).

## Trend following

| variant | total | CAGR | Sharpe | max DD | last 12m | funding | costs | turnover/yr | years + |
|---|---|---|---|---|---|---|---|---|---|
| T1 SMA20 long/short (PRIMARY) | +420.1% | +27.0% | 0.70 | 58.2% | +42.5% | -51.4% | -45.9% | 95.0 | 5/7 |
| T2 SMA50 long/short | +2200.4% | +57.5% | 1.01 | 61.1% | +46.1% | -59.2% | -27.5% | 57.0 | 6/7 |
| T3 SMA20 long-only | +4117.7% | +72.0% | 1.45 | 45.5% | +17.9% | -62.3% | -21.3% | 44.2 | 5/7 |
| T4 SMA50 long-only | +7452.6% | +87.2% | 1.51 | 48.7% | +19.8% | -66.2% | -12.3% | 25.5 | 6/7 |
| Buy and hold (benchmark) | +2994.3% | +64.5% | 1.03 | 78.9% | -21.0% | -73.2% | -4.0% | 8.2 | 4/7 |

Calendar years:

| variant | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|
| T1 SMA20 long/short (PRIMARY) | +67.4% | +42.2% | -3.5% | +2.6% | +109.7% | -32.3% | +55.5% |
| T2 SMA50 long/short | +71.2% | +417.2% | -15.8% | +20.8% | +45.6% | +17.3% | +49.7% |
| T3 SMA20 long-only | +185.3% | +452.3% | -33.3% | +56.1% | +137.9% | -12.8% | +23.9% |
| T4 SMA50 long-only | +184.4% | +783.5% | -36.2% | +69.3% | +95.5% | +17.1% | +21.6% |
| Buy and hold (benchmark) | +213.4% | +923.5% | -71.4% | +113.9% | +126.3% | -15.5% | -17.6% |

Per coin, T1 (sum of daily contributions to portfolio return):

BTC +5.1% | ETH +44.9% | SOL +36.8% | XRP +20.8% | BNB +33.6% | DOGE +29.4% | ZEC +38.2% | HYPE -3.1% | NEAR +41.6% | SUI +27.4% | ADA +36.6% | LINK +0.2%

Random controls for T1 (200, same flip count per coin): median -63.4%, 95th pct +156.9%, best +2061.4%; T1 ranks above 100% of them.

**PASS MARK T1:** net > 0 True | Sharpe >= 0.5 True (0.70) | beats random 95th pct True | years positive 5/7 (need 4) True ==> **PASS**

## Delta-neutral funding carry (long spot + short perp)

| variant | total | CAGR | Sharpe | max DD | last 12m | funding | basis | costs | days in trade |
|---|---|---|---|---|---|---|---|---|---|
| C enter >10%/yr, exit <0% (PRIMARY) | +73.8% | +8.3% | 6.94 | 1.2% | +0.1% | +63.6% | +0.7% | -8.9% | 14459 |
| Always on (reference) | +66.5% | +7.7% | 4.17 | 5.0% | +1.4% | +54.4% | -2.4% | -0.9% | 25077 |

Calendar years (C): 2020 +15.7% | 2021 +31.1% | 2022 +0.2% | 2023 +4.3% | 2024 +8.5% | 2025 +0.8% | 2026 +0.2%

Per coin (C): BTC +7.0% (1564d) | ETH +8.2% (1511d) | SOL +3.3% (1063d) | XRP +6.1% (1486d) | BNB +3.2% (713d) | DOGE +4.6% (1361d) | ZEC +6.5% (1814d) | HYPE +0.0% (48d) | NEAR +3.7% (1190d) | SUI +0.9% (535d) | ADA +5.9% (1501d) | LINK +5.7% (1673d)

Random-timing controls (200, same episodes placed at random): median +25.9%, 95th pct +32.4%, best +37.0%.

**PASS MARK C:** net > 0 True | quarters positive 24/28 (need 2/3) True | max DD <= 10% True (1.2%) | beats random-timing 95th pct True ==> **PASS**

Quarters (C): 2020Q1 +4.9% | 2020Q2 +1.5% | 2020Q3 +5.1% | 2020Q4 +3.4% | 2021Q1 +15.1% | 2021Q2 +7.0% | 2021Q3 +2.8% | 2021Q4 +3.5% | 2022Q1 +0.1% | 2022Q2 +0.1% | 2022Q3 +0.0% | 2022Q4 -0.0% | 2023Q1 +1.0% | 2023Q2 +0.6% | 2023Q3 +0.2% | 2023Q4 +2.4% | 2024Q1 +4.7% | 2024Q2 +1.4% | 2024Q3 +0.2% | 2024Q4 +2.0% | 2025Q1 +0.2% | 2025Q2 +0.0% | 2025Q3 +0.8% | 2025Q4 -0.2% | 2026Q1 -0.1% | 2026Q2 -0.1% | 2026Q3 +0.2% | 2026Q4 +0.1%

## Robustness checks (run after the pre-registered verdict; informational)

Script: one-off checks with the same harness. Total / CAGR / Sharpe / max drawdown.

| check | T1 SMA20 L/S | T2 SMA50 L/S | T3 SMA20 long | T4 SMA50 long | Buy and hold |
|---|---|---|---|---|---|
| trade one day late | +649% / 33.9% / 0.78 / 57% | +3567% / 68.6% / 1.12 / 49% | +4629% / 74.9% / 1.45 / 57% | +9070% / 92.5% / 1.56 / 48% | +3008% / 64.6% / 1.03 / 79% |
| double costs (0.14%/side) | +229% / 18.8% / 0.60 / 61% | +1647% / 51.4% / 0.95 / 63% | +3308% / 66.8% / 1.38 / 49% | +6581% / 83.9% / 1.47 / 50% | +2875% / 63.5% / 1.02 / 79% |
| 2022 onward only | +119% / 17.3% / 0.57 / 58% | +160% / 21.5% / 0.63 / 61% | +168% / 22.3% / 0.73 / 44% | +201% / 25.2% / 0.80 / 43% | -3.5% / -0.7% / 0.33 / 73% |
| BTC + ETH only | -14% / -2.2% / 0.27 / 82% | +1094% / 43.3% / 0.88 / 61% | +387% / 25.8% / 0.75 / 52% | +1683% / 51.8% / 1.16 / 57% | +406% / 26.5% / 0.69 / 77% |
| BTC + ETH, 2022 onward | -21% / -4.7% / 0.18 / 68% | +271% / 30.7% / 0.77 / 61% | +11% / 2.1% / 0.24 / 38% | +146% / 20.2% / 0.70 / 42% | -37% / -9.1% / 0.12 / 69% |

Reading:
- Trading a day late does not hurt, so the result does not depend on filling at the exact close the signal used.
- The primary T1 (SMA20 long/short) passes on the 12 coins but loses on BTC + ETH alone: its result leans on the altcoins, where the hindsight-chosen universe helps most.
- The SMA50 variants hold up in every check, including BTC + ETH since 2022. They were secondary in the pre-registration, so choosing them now is a choice made after seeing the data; they need a forward test before being trusted.
- Drawdowns of 40-60% appear in every trend variant.
- Carry by year (net): 2020 +15.7%, 2021 +31.1%, 2022 +0.2%, 2023 +4.3%, 2024 +8.5%, 2025 +0.8%, 2026 +0.2%. It passed on its history, but almost all of the money came from 2020-2021 and 2024; for the last two years it has earned less than holding cash.
