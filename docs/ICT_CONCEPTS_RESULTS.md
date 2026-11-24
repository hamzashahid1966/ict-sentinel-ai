```
ICT concept test on real Binance 1m data (BTC, ETH, SOL, XRP, BNB, DOGE, ZEC, HYPE, NEAR, SUI, ADA, LINK; 2026-05-24..2026-11-23)
=================================================================================================================================
R = profit in units of the stop distance. Net R is after the 0.05% fee per side and 0.02% slippage.

concept    trades    win  gross R    net R       net R 95% CI   total R  months +  random med  random p95  verdict
FVG         14240  34.9%   -0.008   -0.224 (-0.257, -0.191)   -3184.9    0/7         -0.271      -0.256  FAIL
SWEEP_MSS    6563  36.5%   -0.068   -0.214 (-0.256, -0.171)   -1401.3    0/7         -0.170      -0.154  FAIL
OTE          3728  35.9%   +0.017   -0.195 (-0.266, -0.118)    -726.5    0/7         -0.267      -0.227  FAIL
SMT           288  30.2%   -0.194   -0.432 (-0.564, -0.289)    -124.3    0/7         -0.224      -0.070  FAIL

killzones (net R per trade by session of entry, New York time):
  FVG        LONDON_KZ: 1524 trades -0.230R | NY_KZ: 2068 trades -0.230R | OUTSIDE_KZ: 10648 trades -0.222R
  SWEEP_MSS  LONDON_KZ: 801 trades -0.130R | NY_KZ: 1103 trades -0.246R | OUTSIDE_KZ: 4659 trades -0.220R
  OTE        LONDON_KZ: 370 trades -0.335R | NY_KZ: 606 trades -0.076R | OUTSIDE_KZ: 2752 trades -0.202R
  SMT        LONDON_KZ: 20 trades -0.121R | NY_KZ: 62 trades -0.609R | OUTSIDE_KZ: 206 trades -0.408R

by coin (net R per trade):
  FVG        ADA:-0.28(1628) BNB:-0.20(490) BTC:-0.20(453) DOGE:-0.25(1028) ETH:-0.26(746) HYPE:-0.09(484) LINK:-0.32(1227) NEAR:-0.23(2232) SOL:-0.25(1029) SUI:-0.23(1659) XRP:-0.23(1008) ZEC:-0.12(2256)
  SWEEP_MSS  ADA:-0.17(565) BNB:-0.30(502) BTC:-0.25(494) DOGE:-0.17(576) ETH:-0.21(525) HYPE:-0.23(230) LINK:-0.23(668) NEAR:-0.20(637) SOL:-0.27(603) SUI:-0.17(621) XRP:-0.28(570) ZEC:-0.10(572)
  OTE        ADA:-0.18(442) BNB:-0.48(112) BTC:-0.18(121) DOGE:-0.12(310) ETH:-0.08(202) HYPE:-0.17(126) LINK:-0.13(371) NEAR:-0.25(527) SOL:-0.26(287) SUI:-0.28(429) XRP:-0.18(282) ZEC:-0.14(519)
  SMT        BTC:-0.41(117) ETH:-0.44(171)

by exit:
  FVG        STOP: 8989 trades -1.265R | TARGET: 4508 trades +1.785R | TIME: 743 trades +0.187R
  SWEEP_MSS  STOP: 3296 trades -1.182R | TARGET: 1147 trades +1.841R | TIME: 2120 trades +0.181R
  OTE        STOP: 2330 trades -1.258R | TARGET: 1201 trades +1.787R | TIME: 197 trades +0.292R
  SMT        STOP: 194 trades -1.286R | TARGET: 66 trades +1.748R | TIME: 28 trades +0.353R

by month (total net R):
  FVG        2026-05:-140.2 2026-06:-594.1 2026-07:-516.8 2026-08:-343.9 2026-09:-654.8 2026-10:-510.0 2026-11:-425.1
  SWEEP_MSS  2026-05:-64.1 2026-06:-164.1 2026-07:-264.9 2026-08:-179.5 2026-09:-258.3 2026-10:-225.9 2026-11:-244.5
  OTE        2026-05:-12.2 2026-06:-105.6 2026-07:-200.1 2026-08:-86.0 2026-09:-149.2 2026-10:-120.4 2026-11:-53.1
  SMT        2026-05:-4.4 2026-06:-27.6 2026-07:-27.5 2026-08:-6.0 2026-09:-13.2 2026-10:-27.4 2026-11:-18.2
```

See research/ict_concepts.py for the pre-registered definitions.
