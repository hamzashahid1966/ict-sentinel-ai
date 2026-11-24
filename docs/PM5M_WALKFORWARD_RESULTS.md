```
Polymarket 5m walk-forward (BTC, ETH, SOL, XRP, 2026-05-24..2026-11-23; folds 30d, min train 60d, holdout 30d)
==============================================================================================================
out-of-sample decisions: 405,249 on 140,244 rounds | market log-loss 0.35147
folds: dev1 2026-07-23..2026-08-22 (train 206,333, test 103,177), dev2 2026-08-22..2026-09-21 (train 309,510, test 102,768), dev3 2026-09-21..2026-10-21 (train 412,278, test 98,778), dev4 2026-10-21..2026-10-24 (train 511,056, test 6,854), holdout 2026-10-24..2026-11-23 (train 517,910, test 93,672)

model     log-loss            gain vs market (95% CI)    Brier mkt Brier   bets    win  avg px       P&L
recal      0.35194     -0.00047 (-0.00058, -0.00035)  0.11325   0.11322      0   0.0%   0.000     +0.00   <- control: market recalibrated
logit      0.35175     -0.00028 (-0.00045, -0.00011)  0.11318   0.11322   4869  54.7%   0.506   +163.66   <- PRIMARY: logistic
gbm        0.35148     -0.00001 (-0.00022, +0.00021)  0.11322   0.11322  15434  39.9%   0.395  -1438.46   <- secondary: gradient boosting

per fold (primary logistic): dev1: 1178 bets, P&L +31.43, ll gain -0.00026 | dev2: 641 bets, P&L +326.77, ll gain +0.00056 | dev3: 1869 bets, P&L -114.76, ll gain -0.00077 | dev4: 95 bets, P&L -21.63, ll gain -0.00149 | holdout: 1086 bets, P&L -58.15, ll gain -0.00063
feature-group value (log-loss lost when the group is removed; >0 = the group helped):
  price_position  +0.000236
  order_flow      +0.000026
  structure       +0.000007
  timing          +0.000006
  candle          +0.000005
  trend           -0.000005
  volatility      -0.000010
  regime          -0.000017
  momentum        -0.000030

PASS MARK: log-loss CI above zero False | holdout P&L > 0 False | majority of dev folds P&L > 0 False | total P&L > 0 True  ==> FAIL
```

See research/pm5m_walkforward.py for the pre-registered design.
