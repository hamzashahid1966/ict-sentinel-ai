# Polymarket 5m maker backtest (2026-11-22 18:35 .. 2026-11-23 15:55 UTC)

Rounds with an official outcome: 679 (BTC 179, ETH 176, SOL 162, XRP 162). Rules: header of `research/pm5m_maker.py`. Maker fee 0, rebate counted as 0. P&L in dollars; 10 shares per side (about 10 dollars of outlay per round).

| variant | rounds | fills | fill rate | fills won | avg price | won - price | P&L | per $ | 95% CI |
|---|---|---|---|---|---|---|---|---|---|
| **PRIMARY** post 240s, best prices, strict, gaps <= 120s | 271 | 493 (243 up / 250 down) | 91% | 45.2% | 0.478 | -2.5 pts | -125.30 | -5.3% | (-184.90, -70.50) |
| gap-free rounds only (<= 10s) | 29 | 57 (29 up / 28 down) | 98% | 50.9% | 0.486 | +2.3 pts | +13.00 | +4.7% | (+4.90, +27.60) |
| post 180s | 273 | 490 (248 up / 242 down) | 90% | 45.1% | 0.467 | -1.6 pts | -77.50 | -3.4% | (-132.70, -29.30) |
| post 120s | 256 | 413 (211 up / 202 down) | 81% | 43.1% | 0.449 | -1.8 pts | -73.24 | -4.0% | (-118.45, -31.94) |
| post 60s | 162 | 168 (77 up / 91 down) | 52% | 36.3% | 0.447 | -8.4 pts | -141.78 | -18.9% | (-198.81, -90.49) |
| improve 1c | 271 | 496 (246 up / 250 down) | 92% | 45.6% | 0.480 | -2.5 pts | -121.80 | -5.1% | (-178.20, -67.79) |
| lenient fills | 271 | 503 (249 up / 254 down) | 93% | 46.1% | 0.478 | -1.7 pts | -83.20 | -3.5% | (-143.80, -26.50) |
| first run's design: $5 per side, gap-free | 29 | 57 (29 up / 28 down) | 98% | 50.9% | 0.486 | +2.3 pts | +30.91 | +10.8% | (-13.65, +81.62) |

Primary: both sides filled in 222 rounds (P&L +39.20, the locked spread); one side only in 49 rounds (P&L -164.50, 48 of them lost); no fill in 0 rounds.

By coin (primary): BTC -18.90 (114 fills) | ETH -39.00 (141 fills) | SOL -34.40 (123 fills) | XRP -33.00 (115 fills)

Taker control (random side at the ask, 240s, fee paid): 281 trades, P&L -142.16 (-10.1% per $), 95% CI (-335.37, +74.73).

**PASS MARK (primary):** P&L > 0 False (-125.30) | 95% CI above 0 False ==> **FAIL**

## Reading

- This is textbook adverse selection. When the price wiggles both ways, both bids fill and the round locks a small spread: +39.20 over 222 rounds, about +0.18 a round. When the price runs one way, only the bid on the losing side fills, and it is held to zero: -164.50 over 49 rounds, 48 of which lost. One trending round wipes out about 20 wiggling ones.
- Posting later is worse (-18.9% per dollar at 60 s), because late moves are more decisive.
- The gap-free subset (29 rounds) is positive, but those are the rounds where the recorder never stalled, which are likely calmer ones; 29 rounds is too few to read.
- The maker rebate (counted as 0 here) cannot close the gap: even collecting the whole 20% rebate pool on every fill would add roughly 17 dollars against a 125-dollar loss.
- Professional makers survive this by cancelling and re-quoting within milliseconds when the price moves. A bot reading the book every ~1.7 s and leaving quotes for minutes cannot.
