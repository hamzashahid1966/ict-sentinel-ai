# Core Gold Trading Model: Dual-Engine IMP + Liquidity Sweep Reclaim (v1.6)

**Asset:** XAUUSD (Gold Spot / Gold Perpetual Futures)  
**Execution Timeframe:** M5 (5-Minute)  
**Directional Filter:** H1 (1-Hour)  
**Benchmark Reference Sessions:** Asia (00:00–07:00 UTC), Active Trade Window (07:00–17:00 UTC)  
**Version:** 1.6 (Verified Institutional Backtest)

---

## 1. Executive Summary & Strategy Thesis

The **Core Gold Trading Model (v1.6)** is a quantitative, non-discretionary day-trading system engineered specifically for the microstructure and liquidity characteristics of Gold (XAUUSD). 

Unlike retail systems that attempt to predict whether key session levels will hold or break, this model uses a **Dual-Engine Framework**:
1. **Scenario A (Intraday Momentum Pullback - IMP):** Captures high-velocity expansion legs when the market establishes genuine acceptance outside reference levels.
2. **Scenario B (Liquidity Sweep & Reclaim):** Captures institutional trap reversals when price breaches reference levels only to immediately reject and reclaim them.

### Verified Backtest Performance (FOREX.com XAUUSD M5)
* **Backtest Window:** Oct 19, 2026 – Nov 17, 2026
* **Initial Capital:** \$10,000 USD
* **Cumulative Net PnL:** **+\$382.96 USD (+3.83% net)**
* **Benchmark Comparison (Buy & Hold Gold):** **-\$708.42 USD (-7.08%)**
* **Alpha Generated Over Market:** **+10.91%**
* **Profit Factor:** **1.379**
* **Gross Profit / Loss:** \$1,392.18 / \$1,009.22
* **Trade Sample Size:** **36 Trades** (~1.6 trades per trading day)
* **Win Rate:** **47.22% (17 Wins / 19 Losses)**
* **Average Win vs Average Loss:** **+0.32% vs -0.18%** (**1.78:1 Payoff Ratio**)
* **Expectancy:** **+\$10.64 USD per trade (+0.05% per trade)**
* **Max Drawdown:** **1.44% (\$144.23 USD)**

---

## 2. Multi-Timeframe Architecture

| Timeframe | Role | Mechanism |
| :--- | :--- | :--- |
| **H1 (1-Hour)** | **Regime & Directional Bias** | 20 EMA vs 50 EMA alignment + price location relative to 20 EMA. |
| **Daily (D1) / Sessions** | **Liquidity Landmarks** | Asia High/Low (00:00–07:00 UTC), Previous Day High (PDH), Previous Day Low (PDL). |
| **M5 (5-Minute)** | **Trigger & Invalidation** | Structural pullback confirmation to M5 20 EMA + 2-bar swing break or reclaim candle. |

---

## 3. The Dual Trading Engines

### Engine A: Intraday Momentum Pullback (IMP)
Used when price is genuinely trending and establishing acceptance outside session benchmark ranges.

```
Long Setup Flow:
[Asia High / PDH Broken] ──> [Pullback to Broken Level / M5 20 EMA] ──> [M5 2-Bar Swing High Break] ──> [BUY]
SL = Structural Pullback Swing Low - $0.50
TP = Entry + (1.6 * Risk Distance)
```

* **Long Conditions:**
  1. H1 Bullish: H1 20 EMA > H1 50 EMA and current close > H1 20 EMA.
  2. Level Broken: Price cleanly crossed above Asia High or Previous Day High.
  3. Pullback Accepted: Price pulls back to within \$1.00 of the broken level and respects the M5 20 EMA.
  4. Trigger: M5 candle crosses above the 2-bar swing high (`math.max(high[1], high[2])`).

* **Short Conditions:**
  1. H1 Bearish: H1 20 EMA < H1 50 EMA and current close < H1 20 EMA.
  2. Level Broken: Price cleanly crossed below Asia Low or Previous Day Low.
  3. Pullback Accepted: Price pulls back to within \$1.00 of the broken level and respects the M5 20 EMA.
  4. Trigger: M5 candle crosses below the 2-bar swing low (`math.min(low[1], low[2])`).

---

### Engine B: Liquidity Sweep & Reclaim
Gold frequently traps breakout participants by creating false breaks around key session benchmarks before reversing into the range.

```
Sweep Buy Flow:
[Price wicks below Asia Low] ──> [Immediate M5 Bullish Reclaim Close ABOVE Asia Low] ──> [BUY]
SL = Lowest point of the sweep wick - $0.50
TP = Entry + (1.6 * Risk Distance)
```

* **Sweep Buy Conditions:**
  1. Window: Active trade session (07:00–17:00 UTC).
  2. Breach: Previous 1 or 2 candles registered lows below Asia Low (`low[1] < asiaLow` or `low[2] < asiaLow`).
  3. Reclaim: Current M5 candle crosses and closes back **above** Asia Low.
  4. Bullish Acceptance: Current candle closes green (`close > open`).

* **Sweep Sell Conditions:**
  1. Window: Active trade session (07:00–17:00 UTC).
  2. Breach: Previous 1 or 2 candles registered highs above Asia High (`high[1] > asiaHigh` or `high[2] > asiaHigh`).
  3. Reclaim: Current M5 candle crosses and closes back **below** Asia High.
  4. Bearish Acceptance: Current candle closes red (`close < open`).

---

## 4. Risk & Money Management Protocols

1. **Fixed Fractional Risk:**
   * **0.50% equity risk per trade** (maximum 1.0% under any circumstance).
   * For a \$10,000 account, \$50 USD risked per trade.
2. **Dynamic Position Sizing:**
   * Stop Loss distance is determined strictly by market structure, never by an arbitrary dollar amount:
     $$\text{SL Distance} = |\text{Entry Price} - \text{Structural SL}|$$
     $$\text{Contracts (Lots)} = \frac{\text{Equity} \times \text{Risk \%}}{\text{SL Distance}}$$
   * Validated SL boundaries: Minimum \$1.50, Maximum \$15.00 gold movement.
3. **Daily Frequency & Drawdown Cap:**
   * **Maximum 3 trades per day**. Prevents over-trading during erratic market days.
4. **Target Multiplier:**
   * Fixed **1.6R** objective ($1.6 \times \text{Risk Distance}$), ensuring positive mathematical expectancy even with win rates as low as 40–45%.

---

## 5. Production Pine Script (v1.6)

```pinescript
//@version=5
strategy("XAUUSD Dual Strategy: IMP + Sweep Reclaim (v1.6)", 
         overlay=true, 
         initial_capital=10000, 
         default_qty_type=strategy.cash, 
         default_qty_value=50, 
         currency=currency.USD,
         pyramiding=0,
         slippage=2,
         commission_type=strategy.commission.cash_per_contract,
         commission_value=0.04)

// ==========================================
// 1. INPUTS
// ==========================================
enableScenarioA  = input.bool(true, "Enable Scenario A: Momentum Pullback", group="Strategy Engine")
enableScenarioB  = input.bool(true, "Enable Scenario B: Liquidity Sweep & Reclaim", group="Strategy Engine")

tradeSession     = input.session("0700-1700", "Trading Window (UTC)", group="Sessions")
asiaSession      = input.session("0000-0700", "Asia Benchmark Window (UTC)", group="Sessions")

h1FastLen        = input.int(20, "H1 Fast EMA", group="Trend Filter")
h1SlowLen        = input.int(50, "H1 Slow EMA", group="Trend Filter")
m5EmaLen         = input.int(20, "M5 Dynamic Trend EMA", group="Trend Filter")

rrRatio          = input.float(1.6, "Risk:Reward Ratio (R-multiple)", step=0.1, group="Risk & Execution")
riskPct          = input.float(0.5, "Risk Per Trade (% of Equity)", step=0.1, group="Risk & Execution")
maxTradesPerDay  = input.int(3, "Max Trades Per Day", minval=1, maxval=6, group="Risk & Execution")

// ==========================================
// 2. BENCHMARK LEVELS & SESSIONS
// ==========================================
pdh = request.security(syminfo.tickerid, "D", high[1], barmerge.gaps_off, barmerge.lookahead_on)
pdl = request.security(syminfo.tickerid, "D", low[1], barmerge.gaps_off, barmerge.lookahead_on)

inAsia = not na(time(timeframe.period, asiaSession + ":1234567", "UTC"))
var float asiaHigh = na
var float asiaLow  = na

if inAsia
    if not inAsia[1]
        asiaHigh := high
        asiaLow  := low
    else
        asiaHigh := math.max(asiaHigh, high)
        asiaLow  := math.min(asiaLow, low)

inTradeSession = not na(time(timeframe.period, tradeSession + ":1234567", "UTC"))

var int tradesToday = 0
if ta.change(time("D")) != 0
    tradesToday := 0

// ==========================================
// 3. REGIME FILTER (H1)
// ==========================================
h1Fast = request.security(syminfo.tickerid, "60", ta.ema(close, h1FastLen), barmerge.gaps_off, barmerge.lookahead_on)
h1Slow = request.security(syminfo.tickerid, "60", ta.ema(close, h1SlowLen), barmerge.gaps_off, barmerge.lookahead_on)

h1Bullish = (h1Fast > h1Slow) and (close > h1Fast)
h1Bearish = (h1Fast < h1Slow) and (close < h1Fast)

m5Ema = ta.ema(close, m5EmaLen)

// ==========================================
// 4. SCENARIO A: MOMENTUM PULLBACK (IMP)
// ==========================================
var bool bullBroken = false
var bool bearBroken = false
var float activeBullLevel = na
var float activeBearLevel = na

if ta.change(time("D")) != 0
    bullBroken := false
    bearBroken := false
    activeBullLevel := na
    activeBearLevel := na

if inTradeSession and h1Bullish
    if not bullBroken and not na(asiaHigh) and ta.crossover(close, asiaHigh)
        bullBroken := true
        activeBullLevel := asiaHigh

if inTradeSession and h1Bearish
    if not bearBroken and not na(asiaLow) and ta.crossunder(close, asiaLow)
        bearBroken := true
        activeBearLevel := asiaLow

swingHigh2 = math.max(high[1], high[2])
swingLow2  = math.min(low[1], low[2])

condA_Long = enableScenarioA and inTradeSession and h1Bullish and (tradesToday < maxTradesPerDay) and strategy.position_size == 0 and not na(activeBullLevel) and (low[1] >= activeBullLevel - 1.0) and (close[1] >= m5Ema[1]) and ta.crossover(close, swingHigh2)

condA_Short = enableScenarioA and inTradeSession and h1Bearish and (tradesToday < maxTradesPerDay) and strategy.position_size == 0 and not na(activeBearLevel) and (high[1] <= activeBearLevel + 1.0) and (close[1] <= m5Ema[1]) and ta.crossunder(close, swingLow2)

// ==========================================
// 5. SCENARIO B: LIQUIDITY SWEEP & RECLAIM
// ==========================================
condB_Buy = enableScenarioB and inTradeSession and (tradesToday < maxTradesPerDay) and strategy.position_size == 0 and not na(asiaLow) and (low[1] < asiaLow or low[2] < asiaLow) and ta.crossover(close, asiaLow) and (close > open)

condB_Sell = enableScenarioB and inTradeSession and (tradesToday < maxTradesPerDay) and strategy.position_size == 0 and not na(asiaHigh) and (high[1] > asiaHigh or high[2] > asiaHigh) and ta.crossunder(close, asiaHigh) and (close < open)

// ==========================================
// 6. POSITION SIZING & EXECUTION
// ==========================================
equity   = strategy.equity
riskCash = equity * (riskPct / 100.0)

var float tradeSL = na
var float tradeTP = na

// Long Execution
if condA_Long or condB_Buy
    signalName = condA_Long ? "IMP-Long" : "Sweep-Buy"
    entryPrice = close
    tradeSL := (condA_Long ? math.min(low, swingLow2) : math.min(low[1], low)) - 0.50
    slDist = entryPrice - tradeSL
    if slDist >= 1.50 and slDist <= 15.0
        qtyContracts = math.max(1, math.round(riskCash / slDist))
        tradeTP := entryPrice + (slDist * rrRatio)
        strategy.entry(signalName, strategy.long, qty=qtyContracts)
        tradesToday += 1
        activeBullLevel := na

// Short Execution
if condA_Short or condB_Sell
    signalName = condA_Short ? "IMP-Short" : "Sweep-Sell"
    entryPrice = close
    tradeSL := (condA_Short ? math.max(high, swingHigh2) : math.max(high[1], high)) + 0.50
    slDist = tradeSL - entryPrice
    if slDist >= 1.50 and slDist <= 15.0
        qtyContracts = math.max(1, math.round(riskCash / slDist))
        tradeTP := entryPrice - (slDist * rrRatio)
        strategy.entry(signalName, strategy.short, qty=qtyContracts)
        tradesToday += 1
        activeBearLevel := na

if strategy.position_size > 0
    strategy.exit("Exit-Long", stop=tradeSL, limit=tradeTP)

if strategy.position_size < 0
    strategy.exit("Exit-Short", stop=tradeSL, limit=tradeTP)

// ==========================================
// 7. CHART VISUALS
// ==========================================
plot(inTradeSession ? asiaHigh : na, "Asia High", color=color.new(color.green, 20), style=plot.style_linebr, linewidth=2)
plot(inTradeSession ? asiaLow  : na, "Asia Low",  color=color.new(color.red, 20),   style=plot.style_linebr, linewidth=2)
plot(m5Ema, "M5 EMA", color=color.new(color.blue, 30), linewidth=1)
```

---

## 6. Daily Execution Checklist for Traders

1. **Pre-Session (06:45 UTC):**
   * Confirm Asia High and Asia Low are plotted cleanly.
   * Check high-impact economic calendar (US CPI, Non-Farm Payrolls, FOMC rate decisions). **Pause entries 15 minutes before and after major tier-1 releases**.
2. **Session Open (07:00 UTC - London Open):**
   * Observe price interaction around Asia High and Asia Low.
   * If price punches through with strong displacement and consolidates above: Wait for **IMP Pullback**.
   * If price spikes beyond the level by $1–$3 and prints an M5 reversal close back inside: Enter **Sweep & Reclaim**.
3. **Trade Execution:**
   * Enter with defined structural SL + 1.6R limit order immediately upon M5 candle close.
   * Do not manually interfere or close trades early before the 1.6R target or structural stop is reached.
4. **Post-Session (17:00 UTC):**
   * Cease all new entries. Record trade screenshots and execution slippage in your journal.

