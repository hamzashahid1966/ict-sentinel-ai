# Core Gold London Model: 24-Month Validation of the Production Engine

**Date:** 2026-11-22
**Data:** PAXGUSDT 5-minute bars from Binance public archives, 2024-11-01 to 2026-11-22 (216,518 bars). PAXG is tokenised gold and tracks XAU/USD closely; it is a proxy, not the CME or FOREX.com tape.
**Engine under test:** the live code path, `IPDAEngine.evaluate_market("GOLD", ...)`, which routes London-window bars through the v1.6 dual-engine model (IMP pullback and Asia sweep-and-reclaim) and, in the early London window, the generic sweep/fair-value-gap logic.
**Harness:** `ict_sentinel/gold_backtest.py` (`python3 -m ict_sentinel.gold_backtest --data real_data/gold/gold_5m_24m.json`).

## Fill model

Deliberately conservative and the same for every variant:

- Signals fire on a closed bar; entry is the next bar's open plus 0.10 points adverse slippage.
- Stops fill with 0.10 points adverse slippage; targets fill at price.
- A bar that touches both stop and target counts as a stop.
- 0.30 points round-trip friction (spread plus commission) per unit on every trade.
- Positions are flattened at the session exit deadline exactly as the live OMS does (06:00 ET London, 07:15 ET London Core).
- One position at a time, with the live 15-minute re-entry cooldown.
- Sizing is fractional at 0.5% of current equity per trade unless stated.

## Results, 24 months, $10,000 equity, 0.5% risk

| Variant | Trades | Win % | Profit factor | Expectancy | Net | Max DD |
|---|---|---|---|---|---|---|
| Production exit (BE at 1R, full exit 2R) | 929 | 42.4 | 0.81 | -0.094R | -36.4% | 37.4% |
| Fixed 1.6R target, no BE move (Pine v1.6) | 896 | 40.6 | 0.84 | -0.104R | -38.3% | 41.6% |
| Fixed 2R target, no BE move | 864 | 37.2 | 0.82 | -0.119R | -41.3% | 42.6% |
| Production exit with live quarantine gate | 11 | 45.5 | 0.90 | -0.048R | -0.3% | 1.6% |

The quarantine variant traded 11 times in November 2024 and then rejected 2,450 later signals. A quarantined pair never trades, so its score never updates, so it never releases. In production the only release is a manual account reset.

## Results with Pine v1.6 constraints (max 3 trades/day, one entry per setup per day, gold model only)

| Variant | Trades | Win % | Profit factor | Expectancy | Net | Max DD |
|---|---|---|---|---|---|---|
| Fixed 1.6R target | 553 | 39.4 | 0.80 | -0.126R | -30.1% | 33.3% |
| Production exit | 559 | 42.6 | 0.79 | -0.108R | -26.7% | 28.4% |

## Calibration against the Pine v1.6 claim (2026-05-01 to 2026-11-17)

The Pine backtest in `docs/CORE_GOLD_TRADING_MODEL_v1.6.md` reported 36 trades, 47% wins, profit factor 1.38, +3.83% on this window.

| Variant | Trades | Win % | Profit factor | Net |
|---|---|---|---|---|
| Production engine, fixed 1.6R | 254 | 37.4 | 0.74 | -19.9% |
| Production engine, production exit | 257 | 31.9 | 0.80 | -13.4% |
| Production engine, fixed 1.6R, Pine constraints | 149 | 36.9 | 0.74 | -11.7% |

The production port fires four to seven times more often than the Pine script on the same bars. Pine consumes a broken level after its first entry (`activeBullLevel := na`); the Python port has no such state, so after the 15-minute cooldown it re-enters the same pullback again. The port also trades the generic BISI/SIBI logic in the 02:00 to 04:30 ET window, which the Pine model never did.

## Live configuration: one micro contract ($10/pt) on a $500 account

| Variant | Trades | Net | Max DD |
|---|---|---|---|
| Production exit | 929 | -$5,073 | account exhausted many times over |
| Production exit with quarantine | 11 | -$125 (-25%) | 42.7%, then locked for two years |

## Breakdown that matters

- Every year with a meaningful sample is negative: 2025 (n=480) -0.10R per trade, 2026 (n=399) -0.11R. November to December 2024 (n=50) was +0.06R, the kind of short positive stretch the Pine claim rests on.
- Both setups lose: Asia sweep -0.09R to -0.18R, IMP pullback -0.05R to -0.12R. Both directions lose.
- Stops cost -1.1R and targets pay +1.5R or +1.9R, so the breakeven hit rate after costs is about 42% at 1.6R and 37% at 2R. The engine lands within a point or two of exactly that in every variant. That is the signature of no edge rather than a broken rule.
- Friction accounts for roughly 0.06R to 0.08R per trade. Removing it entirely would lift the best variant to about -0.03R. Still not positive.
- Session-deadline exits are mildly positive (+0.1R to +0.2R); the stop is what loses.

## Conclusion

On two years of 5-minute gold the production London model has negative expectancy under every exit rule, every sizing, and every constraint tested, and the 2026 window that the v1.6 document presents as a verified edge is negative when the shipped code is replayed on it. The quarantine gate does not manage risk; it stops the system permanently after its first two losses. The micro-contract sizing on a $500 account would exhaust the account within the first year.

Nothing here says the ICT concepts are worthless. It says this implementation, as it trades today, has not earned live capital.

## Caveats

- PAXG, not XAU/USD futures; spreads and overnight behaviour differ.
- 0.30 points friction may be slightly high for a tight CFD; see the friction estimate above.
- No intra-bar path information; the stop-first rule is conservative by design.
- The harness replays the engine with a 180-bar window as the live server does; shorter or longer context changes the Asia range and H1 EMA inputs.
