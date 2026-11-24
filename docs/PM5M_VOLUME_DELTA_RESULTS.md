```
quote timing: after the signal
Volume-delta rule on Polymarket 5m (|VD| > 0.2, last 4 completed Binance 1m candles, $10, ask 0.2-0.8)
======================================================================================================
trades 160,928 | win 51.35% (95% CI 51.10-51.59) | avg ask 0.526 | break-even 54.26% | P&L -95,114.29 on $1,609,280 staked (-5.91%)
by coin
  BTC               41238 trades  win  52.1%  avg ask 0.530  P&L  -22563.37 (-5.47%)
  ETH               39022 trades  win  50.6%  avg ask 0.521  P&L  -25730.16 (-6.59%)
  SOL               40647 trades  win  51.3%  avg ask 0.528  P&L  -25077.86 (-6.17%)
  XRP               40021 trades  win  51.3%  avg ask 0.525  P&L  -21742.90 (-5.43%)
by month
  2026-05            7408 trades  win  50.2%  avg ask 0.515  P&L   -4287.72 (-5.79%)
  2026-06           26192 trades  win  50.2%  avg ask 0.519  P&L  -18381.43 (-7.02%)
  2026-07           28854 trades  win  50.8%  avg ask 0.518  P&L  -15901.89 (-5.51%)
  2026-08           27845 trades  win  52.2%  avg ask 0.530  P&L  -13884.11 (-4.99%)
  2026-09           25837 trades  win  52.4%  avg ask 0.536  P&L  -13990.10 (-5.41%)
  2026-10           26793 trades  win  51.4%  avg ask 0.529  P&L  -17358.50 (-6.48%)
  2026-11           17999 trades  win  51.5%  avg ask 0.529  P&L  -11310.53 (-6.28%)
by entry minute (seconds into the round)
  +  0s            117556 trades  win  50.1%  avg ask 0.515  P&L  -71774.14 (-6.11%)
  + 60s             23421 trades  win  55.0%  avg ask 0.562  P&L  -13170.63 (-5.62%)
  +120s             11496 trades  win  54.4%  avg ask 0.554  P&L   -6408.78 (-5.57%)
  +180s              5962 trades  win  54.9%  avg ask 0.547  P&L   -1632.07 (-2.74%)
  +240s              2493 trades  win  50.8%  avg ask 0.525  P&L   -2128.67 (-8.54%)
by |volume delta|
  0.20-0.30         59615 trades  win  51.6%  avg ask 0.526  P&L  -32377.12 (-5.43%)
  0.30-0.45         55361 trades  win  51.1%  avg ask 0.526  P&L  -34300.74 (-6.20%)
  0.45+             45952 trades  win  51.3%  avg ask 0.527  P&L  -28436.43 (-6.19%)
by side
  DOWN              82684 trades  win  51.8%  avg ask 0.529  P&L  -44645.06 (-5.40%)
  UP                78244 trades  win  50.9%  avg ask 0.523  P&L  -50469.24 (-6.45%)

controls: coin-flip side median -90,508.00, 95th pct -86,064.69 | opposite side -83,365.21
price-gate sensitivity (same rule, other ask bands; not part of the pass mark):
  no price gate  183822 trades  win  54.3%  avg ask 0.555  P&L -115999.07 (-6.31%)
  ask <= 0.60    141392 trades  win  43.9%  avg ask 0.451  P&L -114354.61 (-8.09%)
  ask 0.60-0.90  102339 trades  win  72.0%  avg ask 0.730  P&L  -33592.22 (-3.28%)
PASS MARK: P&L > 0 False | win CI above break-even False | full months positive 0/5 (need 4) False | coins positive 0/4 (need 3) False | beats 95th pct of coin flips False  ==> FAIL
```

See research/pm5m_volume_delta.py for the pre-registered design.
