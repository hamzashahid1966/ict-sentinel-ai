```
Crypto Sentinel backtest, Fast Scalper, BTC, ETH, SOL, XRP, BNB, DOGE, ZEC, NEAR, SUI, ADA, LINK (2026-05-24..2026-11-23)
=========================================================================================================================
trades 1735 | net P&L -563.84 on $1,000 (-56.38%) | gross -168.11 | fees -395.74
win rate 65.9% | avg win +0.76 | avg loss -2.43 | profit factor 0.61 | avg net R -0.142 | max drawdown 58.07%
engine signals 66,953 | decisions skipped while the daily lock was on: 0

by coin
  ADAUSDT                181 trades  win  70.7%  net    -47.58  fees   37.08  avg R -0.090
  BNBUSDT                140 trades  win  71.4%  net    -23.42  fees   33.39  avg R -0.090
  BTCUSDT                 95 trades  win  65.3%  net    -37.92  fees   22.74  avg R -0.184
  DOGEUSDT               129 trades  win  62.0%  net    -32.55  fees   16.32  avg R -0.205
  ETHUSDT                116 trades  win  72.4%  net    -29.61  fees   25.03  avg R -0.104
  LINKUSDT               141 trades  win  63.1%  net    -75.42  fees   31.93  avg R -0.234
  NEARUSDT               281 trades  win  66.5%  net    -75.47  fees   59.92  avg R -0.106
  SOLUSDT                146 trades  win  69.2%  net    -41.62  fees   31.42  avg R -0.098
  SUIUSDT                154 trades  win  60.4%  net    -68.45  fees   34.26  avg R -0.197
  XRPUSDT                183 trades  win  52.5%  net    -99.26  fees   71.68  avg R -0.237
  ZECUSDT                169 trades  win  72.8%  net    -32.56  fees   31.97  avg R -0.065
by month
  2026-05                127 trades  win  73.2%  net     -3.30  fees   40.95  avg R -0.018
  2026-06                519 trades  win  67.2%  net   -210.62  fees  136.72  avg R -0.130
  2026-07                225 trades  win  60.0%  net   -117.92  fees   59.56  avg R -0.211
  2026-08                212 trades  win  67.9%  net    -63.27  fees   47.73  avg R -0.139
  2026-09                244 trades  win  65.6%  net    -69.35  fees   44.97  avg R -0.155
  2026-10                229 trades  win  65.1%  net    -53.07  fees   40.33  avg R -0.137
  2026-11                179 trades  win  63.1%  net    -46.31  fees   25.47  avg R -0.170
by engine
  B_MOMENTUM_IMP        1283 trades  win  66.3%  net   -408.67  fees  283.42  avg R -0.141
  C_LIQUIDATION_SWEEP    452 trades  win  64.6%  net   -155.18  fees  112.32  avg R -0.147
by direction
  LONG                   762 trades  win  62.2%  net   -358.12  fees  171.01  avg R -0.200
  SHORT                  973 trades  win  68.8%  net   -205.72  fees  224.73  avg R -0.097
by exit
  DEFENSIVE_STOP_OUT     698 trades  win  89.8%  net   +207.16  fees  149.76  avg R +0.117
  END_OF_TEST              1 trades  win   0.0%  net     -1.19  fees    0.05  avg R -0.776
  INITIAL_STOP_LOSS      517 trades  win   0.0%  net  -1418.13  fees  125.24  avg R -1.141
  STAGNANT_SWAP           28 trades  win  89.3%  net     +9.46  fees    7.21  avg R +0.120
  TARGET_2_FULL_FILL     491 trades  win 100.0%  net   +638.86  fees  113.48  avg R +0.527

risk-gate rejections: REJECTED: Target 1 move too small: 13,541, REJECTED: Auto-Quarantine active on ZECUSDT: 5,225, REJECTED: Auto-Quarantine active on LINKUSDT: 4,638, REJECTED: Auto-Quarantine active on NEARUSDT: 4,614, REJECTED: Auto-Quarantine active on XRPUSDT: 4,599, REJECTED: Auto-Quarantine active on SUIUSDT: 4,396, REJECTED: Auto-Quarantine active on ADAUSDT: 3,999, REJECTED: Auto-Quarantine active on DOGEUSDT: 3,716, REJECTED: Auto-Quarantine active on SOLUSDT: 3,521, REJECTED: Auto-Quarantine active on ETHUSDT: 2,991, REJECTED: Auto-Quarantine active on BTCUSDT: 2,510, REJECTED: Auto-Quarantine active on BNBUSDT: 2,039, REJECTED: Entry pacing cooldown active: 966, REJECTED: BTC Market Shield active: 858, REJECTED: Active position already exists on BNBUSDT: 580, REJECTED: Active position already exists on BTCUSDT: 514, REJECTED: Active position already exists on ETHUSDT: 477, REJECTED: Active position already exists on XRPUSDT: 385, REJECTED: Active position already exists on SOLUSDT: 358, REJECTED: Active position already exists on NEARUSDT: 307, REJECTED: Active position already exists on SUIUSDT: 282, REJECTED: Correlation safeguard active: 265, REJECTED: Active position already exists on LINKUSDT: 257, REJECTED: Active position already exists on ADAUSDT: 251, REJECTED: Active position already exists on DOGEUSDT: 247, REJECTED: Active position already exists on ZECUSDT: 216
as deployed (daily drawdown lock never resets): 377 trades, net -32.94, decisions blocked by the lock 61,150
random-direction controls (20): median -529.79, 95th pct -430.01, min -628.72, max -420.21
PASS MARK: net > 0 False | months positive 0/7 (need 4) | beats 95th pct of random False  ==> FAIL
```

See research/crypto_backtest.py for the pre-registered design.
