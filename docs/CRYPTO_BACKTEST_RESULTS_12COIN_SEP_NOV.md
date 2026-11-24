```
Crypto Sentinel backtest, Fast Scalper, BTC, ETH, SOL, XRP, BNB, DOGE, ZEC, HYPE, NEAR, SUI, ADA, LINK (2026-05-24..2026-11-23)
===============================================================================================================================
trades 699 | net P&L -256.67 on $1,000 (-25.67%) | gross -53.30 | fees -203.37
win rate 66.0% | avg win +0.98 | avg loss -2.98 | profit factor 0.64 | avg net R -0.126 | max drawdown 27.23%
engine signals 23,121 | decisions skipped while the daily lock was on: 0

by coin
  ADAUSDT                 56 trades  win  67.9%  net    -14.34  fees   14.74  avg R -0.084
  BNBUSDT                 30 trades  win  60.0%  net    -21.74  fees    8.00  avg R -0.251
  BTCUSDT                 27 trades  win  59.3%  net    -19.79  fees    7.50  avg R -0.253
  DOGEUSDT                45 trades  win  64.4%  net    -16.21  fees    6.86  avg R -0.202
  ETHUSDT                 40 trades  win  75.0%  net     -8.39  fees   10.05  avg R -0.054
  HYPEUSDT                90 trades  win  74.4%  net     -7.09  fees   25.76  avg R -0.025
  LINKUSDT                54 trades  win  66.7%  net    -29.26  fees   14.63  avg R -0.179
  NEARUSDT                97 trades  win  70.1%  net    -32.02  fees   23.24  avg R -0.110
  SOLUSDT                 41 trades  win  68.3%  net    -12.10  fees   11.29  avg R -0.089
  SUIUSDT                 73 trades  win  58.9%  net    -37.88  fees   23.69  avg R -0.166
  XRPUSDT                 74 trades  win  52.7%  net    -39.89  fees   39.78  avg R -0.188
  ZECUSDT                 72 trades  win  68.1%  net    -17.96  fees   17.82  avg R -0.076
by month
  2026-09                142 trades  win  73.2%  net    -16.79  fees   38.36  avg R -0.041
  2026-10                358 trades  win  63.4%  net   -162.06  fees  116.95  avg R -0.147
  2026-11                199 trades  win  65.3%  net    -77.82  fees   48.07  avg R -0.149
by engine
  B_MOMENTUM_IMP         513 trades  win  66.7%  net   -179.63  fees  143.58  avg R -0.116
  C_LIQUIDATION_SWEEP    186 trades  win  64.0%  net    -77.04  fees   59.80  avg R -0.152
by direction
  LONG                   270 trades  win  62.6%  net   -132.70  fees   81.99  avg R -0.174
  SHORT                  429 trades  win  68.1%  net   -123.97  fees  121.38  avg R -0.095
by exit
  DEFENSIVE_STOP_OUT     271 trades  win  88.6%  net   +100.16  fees   72.92  avg R +0.121
  END_OF_TEST              1 trades  win   0.0%  net     -2.02  fees    0.09  avg R -0.776
  INITIAL_STOP_LOSS      203 trades  win   0.0%  net   -697.44  fees   65.04  avg R -1.148
  STAGNANT_SWAP           15 trades  win  80.0%  net     +1.75  fees    3.57  avg R +0.046
  TARGET_2_FULL_FILL     209 trades  win 100.0%  net   +340.89  fees   61.75  avg R +0.537

risk-gate rejections: REJECTED: Target 1 move too small: 4,970, REJECTED: Auto-Quarantine active on ZECUSDT: 1,544, REJECTED: Auto-Quarantine active on SUIUSDT: 1,428, REJECTED: Auto-Quarantine active on NEARUSDT: 1,398, REJECTED: Auto-Quarantine active on XRPUSDT: 1,348, REJECTED: Auto-Quarantine active on LINKUSDT: 1,255, REJECTED: Auto-Quarantine active on ADAUSDT: 1,119, REJECTED: Auto-Quarantine active on DOGEUSDT: 1,094, REJECTED: Auto-Quarantine active on SOLUSDT: 1,077, REJECTED: Auto-Quarantine active on HYPEUSDT: 1,059, REJECTED: Auto-Quarantine active on ETHUSDT: 739, REJECTED: Auto-Quarantine active on BNBUSDT: 647, REJECTED: Auto-Quarantine active on BTCUSDT: 629, REJECTED: Entry pacing cooldown active: 470, REJECTED: BTC Market Shield active: 332, REJECTED: Active position already exists on ETHUSDT: 178, REJECTED: Active position already exists on XRPUSDT: 164, REJECTED: Active position already exists on HYPEUSDT: 156, REJECTED: Active position already exists on BNBUSDT: 136, REJECTED: Active position already exists on BTCUSDT: 126, REJECTED: Active position already exists on NEARUSDT: 120, REJECTED: Active position already exists on DOGEUSDT: 101, REJECTED: Correlation safeguard active: 93, REJECTED: Active position already exists on SUIUSDT: 91, REJECTED: Active position already exists on ZECUSDT: 90, REJECTED: Active position already exists on ADAUSDT: 87, REJECTED: Active position already exists on LINKUSDT: 75, REJECTED: Active position already exists on SOLUSDT: 68
as deployed (daily drawdown lock never resets): 153 trades, net -31.40, decisions blocked by the lock 21,209
random-direction controls (20): median -293.76, 95th pct -211.18, min -364.46, max -202.62
PASS MARK: net > 0 False | months positive 0/3 (need 4) | beats 95th pct of random False  ==> FAIL
```

See research/crypto_backtest.py for the pre-registered design.
