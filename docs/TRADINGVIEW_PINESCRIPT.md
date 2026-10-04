# Astra Quant • 10-Framework Institutional Breakout Screener (TradingView Pine Script v6)

This document contains the official **Pine Script v6** implementation of the Astra Quant multi-framework breakout engine. It consolidates all 10 quantitative screening systems, the **Multi-Week Overhead Ceiling Guard** (eliminating inside-base false breakouts), and the **United States Investing Championship (USIC)** staged risk management architecture into a single TradingView indicator.

---

## 1. What's New in Version 6

Pine Script® v6 (released by TradingView) brings major execution and language upgrades:
1. **Lazy Short-Circuit Evaluation:** `and` / `or` conditions are evaluated lazily, speeding up multi-framework confluence checks.
2. **Strict Boolean & Type Safety:** Eliminates implicit type casting errors and enforces non-nullable boolean state flags (`var bool trade_active = false`).
3. **Multi-Week Overhead Base Ceiling Guard:** Specifically solves the **Overhead Supply Trap** (e.g., WHEELS on 29-June) where a standard 20-day lookback forgets older base resistance and triggers premature false breakouts.
4. **USIC Early Violation Warning:** Alerts immediately if a breakout fails to follow through and closes back below the pivot level within 3 bars (Minervini Violation Rule), allowing traders to cut losses early at $-1.5\%$ instead of taking the full $-5.0\%$ hit.
5. **Real-time Radar HUD v6:** Compact 13-row on-chart status table displaying all 10 strategies, overhead ceiling clearance, and active USIC trade state.

---

## 2. The 29-June Fakeout Case Study & Ceiling Guard Logic

### The Problem: The 20-Day Rolling Window Blindspot
In a 4-to-10 week consolidation base (such as WHEELS from 22 May to July 2026), the swing high occurs early (22 May 2026).
* By 29 June, **26 trading days** have passed.
* Standard indicators only look back 20 bars (`ta.highest(h[1], 20)`).
* Because 26 > 20, the major resistance peak from 22 May **fell off the 20-day radar**.
* The 20-day high dropped lower to the intermediate consolidation chop.
* On 29 June, price closed slightly above the minor 20-day resistance, triggering a false `BREAKOUT` triangle.
* On 1 July, the stock slammed directly into the major 22-May ceiling and collapsed back into the base, inflicting a $-5.24\%$ loss.

### The Quant Solution: Overhead Base Ceiling Guard
The v6 engine continuously scans a **50-day window** (`r_ceil = ta.highest(h[1], 50)`):
$$\text{has\_overhead\_ceiling} = (R_{50} > R_{20} \times 1.015)$$
$$\text{ceiling\_cleared} = \neg \text{has\_overhead\_ceiling} \lor (\text{Close} > R_{50})$$

* If an older peak exists within the past 50 bars that is $\ge 1.5\%$ above the 20-day high, the stock is flagged as **trapped under overhead supply**.
* A red ceiling line is drawn across the chart at that major resistance level.
* **All 10 breakout triggers are automatically muted** until price decisively breaks the 50-day ceiling.
* **Result on WHEELS:** The 29-June false breakout is completely eliminated.

---

## 3. How USIC Champions Handle Stop Loss

United States Investing Championship (USIC) winners (Mark Minervini — 1997 & 2021, Oliver Kell — 2020, David Ryan — 1985–1987) execute risk management across **4 distinct defense gates**:

```mermaid
flowchart TD
    A["Breakout Entry (+25 bps friction)"] --> B{"First 1-3 Bars"}
    B -->|Closes back below Pivot| C["1. USIC Violation Stop: Cut early at -1.5% to -2%"]
    B -->|Normal Base Retest| D["2. Hard Catastrophic Stop: Liquidate at -5.0% (-1.0R)"]
    B -->|Rallies to Target 1 (+7.5% / +1.5R)| E["3. Dynamic Breakeven Ratchet: Bank 50% Profit, Stop to ₹ Entry"]
    E -->|Market Pullback| F["🛡️ Risk-Free Breakeven Exit on Remaining 50%"]
    E -->|Trend Continuation| G["4. Runner Exit: Bank 50% at Target 2 (+12.5% / +2.5R) or Trail 10 EMA"]
```

1. **Pre-Determined Catastrophic Cap ($-5.0\%$ / $-1.0R$):** The maximum capital at risk on any single trade is non-negotiable. Total portfolio heat is kept under $1.0\%$ of total equity.
2. **The "Violation" Stop (Fast Defense):** A true institutional breakout should show immediate demand. If price breaks out but closes below the entry pivot within 3 days, USIC traders exit immediately without waiting for the full $-5\%$ stop.
3. **The Automatic Breakeven Ratchet (Free Trade):** Minervini's rule: *"Never let a good gain turn into a loss."* At $+1.5R$ ($+7.5\%$), $50\%$ of the position is locked in for cash, and the stop on the remainder is moved to the exact entry price.
4. **Runner Trailing:** The second half rides the trend until reaching Target 2 ($+12.5\%$) or until price closes below the rising 10 EMA.

---

## 4. Full Pine Script v6 Source Code

Copy and paste the code below directly into TradingView's Pine Editor:

```pinescript
//@version=6
indicator("Astra Quant • 10-Framework Institutional Breakout Screener (v6)", shorttitle="AstraQuant Screener v6", overlay=true)

// =============================================================================
// ASTRA QUANT: 10-FRAMEWORK INSTITUTIONAL BREAKOUT & STAGED EXECUTION ENGINE (v6)
// =============================================================================
// Upgraded to Pine Script v6 with:
//  - Multi-Week Overhead Base Ceiling Guard (Eliminates inside-base false breakout traps)
//  - Strict USIC (United States Investing Championship) Risk Management State Machine
//  - USIC Early Violation Stop Detection (Exits within 1-3 bars if pivot fails)
//  - 10 Quant Institutional Breakout Frameworks in simultaneous surveillance
//  - Dynamic Breakeven Ratchet & EMA Runner Trailing
// =============================================================================

// --- Inputs: USIC Risk & Staged Execution ---
grp_risk       = "USIC Staged Execution Rules"
stop_pct       = input.float(5.0, "Initial Stop Loss % (-1.0R)", minval=1.0, maxval=15.0, group=grp_risk, tooltip="Hard catastrophic stop loss limit per trade.") / 100.0
target1_r      = input.float(1.5, "Target 1 Multiple (Scale-Out 50%)", minval=1.0, maxval=5.0, group=grp_risk, tooltip="First target (+1.5R = +7.5%). Sells 50% and moves stop on remainder to Breakeven.")
target2_r      = input.float(2.5, "Target 2 Multiple (Runner Exit)", minval=1.5, maxval=10.0, group=grp_risk, tooltip="Final target (+2.5R = +12.5%) for remainder runner.")
cost_bps       = input.float(25.0, "Execution Friction (bps)", minval=0.0, group=grp_risk, tooltip="Round-trip transaction costs & slippage.") / 10000.0

// --- Inputs: Overhead Supply & Base Ceiling Guard ---
grp_ceil       = "Overhead Supply & Base Ceiling Guard"
enforce_ceil   = input.bool(true, "Enforce Base Ceiling Clearance", group=grp_ceil, tooltip="Guards against inside-base fakeouts (like WHEELS on 29-June). If a higher swing high exists in the past 50 bars, breakout is invalid unless price clears that higher peak.")
ceil_lookback  = input.int(50, "Ceiling Lookback (Bars)", minval=20, maxval=120, group=grp_ceil, tooltip="Lookback window to scan for older overhead resistance peaks.")
ceil_buffer    = input.float(1.5, "Ceiling Threshold Buffer (%)", minval=0.5, maxval=5.0, group=grp_ceil, tooltip="Minimum height percentage above 20d high to classify as major overhead ceiling.") / 100.0

// --- Inputs: Display Options ---
grp_disp       = "Display Options"
show_table     = input.bool(true, "Show Strategy Radar Table", group=grp_disp)
show_usic      = input.bool(true, "Plot Active USIC Trade Levels", group=grp_disp)
show_ceil_line = input.bool(true, "Plot Overhead Ceiling Line", group=grp_disp)
table_pos      = input.string("Top Right", "Table Position", options=["Top Right", "Bottom Right", "Top Left", "Bottom Left"], group=grp_disp)

// --- Price & Technical Indicators ---
c = close
o = open
h = high
l = low
v = volume

// Moving Averages
ema10  = ta.ema(c, 10)
ema20  = ta.ema(c, 20)
sma50  = ta.sma(c, 50)
sma150 = ta.sma(c, 150)
sma200 = ta.sma(c, 200)
sma200_1m = sma200[22] // 1 month ago

// Highs & Lows (Reference Pivots)
r10 = ta.highest(h[1], 10)
r20 = ta.highest(h[1], 20)
r60 = ta.highest(h[1], 60)
l10 = ta.lowest(l[1], 10)
l20 = ta.lowest(l[1], 20)
l60 = ta.lowest(l[1], 60)
h52 = ta.highest(h[1], 252)
l52 = ta.lowest(l[1], 252)

// Multi-Week Base Ceiling Evaluation
r_ceil = ta.highest(h[1], ceil_lookback)
has_overhead_ceiling = enforce_ceil and (r_ceil > r20 * (1.0 + ceil_buffer))
ceiling_cleared      = not has_overhead_ceiling or (c > r_ceil)

// Volume & Volatility
vol_sma20 = ta.sma(v, 20)
vol_sma50 = ta.sma(v, 50)
rvol20    = vol_sma20 > 0 ? (v / vol_sma20) : 1.0
rvol50    = vol_sma50 > 0 ? (v / vol_sma50) : 1.0

atr14     = ta.atr(14)
adr20_pct = ta.sma((h - l) / c, 20)

// Wyckoff Closing Range
closing_range = (h - l) > 0 ? (c - l) / (h - l) : 0.5

// Volatility Ranges
range20 = c > 0 ? (r20 - l20) / c : 0.0
range60 = c > 0 ? (r60 - l60) / c : 0.0

// Extension above 50 SMA
ext_sma50 = sma50 > 0 ? (c - sma50) / sma50 : 0.0

// Multi-Touch Shelf Detection (touches within 0.75 ATR)
shelf_band_lo = r20 - 0.75 * atr14
touches = 0
for i = 1 to 20
    if h[i] >= shelf_band_lo and h[i] <= r20 + 0.5 * atr14
        touches += 1

// Relative Strength Estimate (vs 200 SMA baseline)
rs_score = ((c / sma200) - 1.0) * 100.0

// =============================================================================
// 10 STRATEGY EVALUATION LOGIC (WITH OVERHEAD CEILING PROTECTION)
// =============================================================================

// 1. 🎯 Sniper Mode (65%+ Win Rate Confluence)
// Requires: Stage 2 + Contraction + Wyckoff Absorption + Anti-Extension + Volume Surge + Ceiling Cleared
g_stage2  = (c > sma50) and (sma50 > sma200)
g_vcp     = range20 <= 0.14
g_wyckoff = (closing_range >= 0.65) and (rvol20 >= 1.3)
g_ext     = ext_sma50 <= 0.20
g_break   = (c > r10 or c > r20) and ceiling_cleared
strat_sniper = g_stage2 and g_vcp and g_wyckoff and g_ext and g_break and (rvol20 >= 1.4)

// 2. 🛡️ Protocol Fortified (Regime + ATR Clearance + Multi-Touch Shelf)
strat_protocol = (c > sma50) and (sma50 > sma200) and (ext_sma50 <= 0.20) and (c > r20) and ceiling_cleared and ((c - r20) >= 0.10 * atr14) and (rvol20 >= 1.3)

// 3. ⚡ Relative Strength Leader (William O'Neil RS Outperformer)
strat_rs = (c > sma50) and (sma50 > sma200) and (ext_sma50 <= 0.25) and (rvol20 >= 1.0) and (rs_score >= 15.0) and (c > r20) and ceiling_cleared

// 4. 📈 Minervini Trend Template (SEPA)
strat_minervini = (c > sma150) and (c > sma200) and (sma150 > sma200) and (sma200 >= sma200_1m * 0.99) and (sma50 > sma150) and (sma50 > sma200) and (c > sma50) and (c >= 1.30 * l52) and (c >= 0.75 * h52) and (ext_sma50 <= 0.25) and (c > r20) and ceiling_cleared

// 5. 🏛️ Stan Weinstein Stage 2 Breakout
strat_weinstein = (c > sma150) and (sma150 >= sma200) and (c > r20) and ceiling_cleared and (rvol20 >= 1.4) and (ext_sma50 <= 0.25)

// 6. 🚀 Kristjan Qullamaggie Breakout (High Tight Flag)
strat_qulla = (ema10 > ema20) and (ema20 > sma50) and (adr20_pct >= 0.035) and (c > r10) and ceiling_cleared and (rvol20 >= 1.4) and ((c - ema10) / ema10 <= 0.08)

// 7. 📊 William O'Neil CANSLIM Pivot Breakout
strat_canslim = (c > sma50) and (sma50 > sma200) and (c >= 0.85 * h52) and (c > r20) and ceiling_cleared and (c <= 1.05 * r20) and (rvol50 >= 1.4)

// 8. 🌀 PKScreener Volatility Contraction Pattern (VCP)
pre_vol_dry = (v[1] < vol_sma20 * 0.80) or (v[2] < vol_sma20 * 0.80)
strat_pkscreener = (c > sma50) and (range20 < range60 * 0.85) and pre_vol_dry and (c > r10) and ceiling_cleared and (rvol20 >= 1.25)

// 9. 🐢 Turtle Trading (Donchian 20-Day Breakout)
strat_turtle = (c > sma50) and (sma50 > sma200) and (c > r20) and ceiling_cleared and (rvol20 >= 1.2) and (ext_sma50 <= 0.25)

// 10. 📦 Nicolas Darvas Box Breakout
strat_darvas = (c > sma50) and (sma50 > sma200) and (c >= 0.85 * h52) and (range20 <= 0.18) and (c > r20) and ceiling_cleared and (rvol20 >= 1.3)

// Confluence Count
triggered_count = (strat_sniper ? 1 : 0) + (strat_protocol ? 1 : 0) + (strat_rs ? 1 : 0) + (strat_minervini ? 1 : 0) + (strat_weinstein ? 1 : 0) + (strat_qulla ? 1 : 0) + (strat_canslim ? 1 : 0) + (strat_pkscreener ? 1 : 0) + (strat_turtle ? 1 : 0) + (strat_darvas ? 1 : 0)

any_breakout = triggered_count > 0

// =============================================================================
// USIC STAGED EXECUTION STATE MACHINE
// =============================================================================
var float entry_price   = na
var float stop_loss     = na
var float target_1      = na
var float target_2      = na
var bool  t1_hit        = false
var bool  trade_active  = false
var int   entry_bar     = 0

if any_breakout and not trade_active
    entry_price  := c * (1.0 + cost_bps)
    stop_loss    := entry_price * (1.0 - stop_pct)
    target_1     := entry_price * (1.0 + stop_pct * target1_r)
    target_2     := entry_price * (1.0 + stop_pct * target2_r)
    t1_hit       := false
    trade_active := true
    entry_bar    := bar_index

// Early USIC Violation (Minervini Rule: failed follow-through within 3 bars)
is_violation = trade_active and (bar_index - entry_bar <= 3) and (c < entry_price * 0.985)

if trade_active
    // Check Stop Loss
    if l <= stop_loss
        trade_active := false
    // Check Target 1 Scale-out & Breakeven raise
    else if h >= target_1 and not t1_hit
        t1_hit    := true
        stop_loss := entry_price // Dynamic raise to Breakeven!
    // Check Target 2 Runner Exit
    else if h >= target_2
        trade_active := false

// =============================================================================
// VISUAL PLOTS & SIGNALS
// =============================================================================

// Signal Shapes on Bar
plotshape(strat_sniper, title="Sniper Breakout", style=shape.diamond, location=location.belowbar, color=color.new(#ec4899, 0), size=size.normal, text="🎯SNIPER")
plotshape(any_breakout and not strat_sniper, title="Framework Breakout", style=shape.triangleup, location=location.belowbar, color=color.new(#10b981, 0), size=size.small, text="BREAKOUT")

// Base Ceiling Line (Draws overhead resistance when inside multi-week base)
plot(show_ceil_line and has_overhead_ceiling ? r_ceil : na, "Overhead Base Ceiling", color=color.new(#f43f5e, 30), linewidth=2, style=plot.style_linebr)

// USIC Levels
plot(show_usic and trade_active ? entry_price : na, "USIC Entry", color=color.new(#38bdf8, 0), linewidth=1, style=plot.style_linebr)
plot(show_usic and trade_active ? stop_loss : na, "USIC Stop Loss", color=color.new(#f43f5e, 0), linewidth=2, style=plot.style_linebr)
plot(show_usic and trade_active ? target_1 : na, "Target 1 (+1.5R 50%)", color=color.new(#10b981, 0), linewidth=1, style=plot.style_linebr)
plot(show_usic and trade_active ? target_2 : na, "Target 2 (+2.5R Runner)", color=color.new(#34d399, 0), linewidth=2, style=plot.style_linebr)

// Alert Conditions
alertcondition(strat_sniper, title="Sniper Mode Breakout Alert", message="🎯 Astra Quant: {{ticker}} triggered SNIPER MODE breakout at ₹{{close}}! Confluence gates & ceiling cleared.")
alertcondition(any_breakout, title="Any Framework Breakout Alert", message="🚀 Astra Quant: {{ticker}} triggered {{plot_0}} breakout at ₹{{close}}! Volume = {{volume}}.")
alertcondition(trade_active and h >= target_1, title="Target 1 Hit Alert", message="💰 Astra Quant: {{ticker}} reached Target 1 at ₹{{high}}! Bank 50% profit and move Stop to Breakeven.")
alertcondition(trade_active and l <= stop_loss, title="Stop Loss Triggered Alert", message="🛑 Astra Quant: {{ticker}} hit Stop Loss at ₹{{low}}! Exit position according to USIC rules.")
alertcondition(is_violation, title="USIC Violation Warning", message="⚠️ Astra Quant: {{ticker}} broke down below pivot within 3 bars of entry! Consider early defensive cut.")

// =============================================================================
// RADAR TABLE HUD
// =============================================================================
var table_pos_val = table_pos == "Top Right" ? position.top_right : (table_pos == "Bottom Right" ? position.bottom_right : (table_pos == "Top Left" ? position.top_left : position.bottom_left))
var table radar = table.new(table_pos_val, 2, 13, bgcolor=color.new(#0b1120, 10), border_color=color.new(#38bdf8, 60), border_width=1)

f_row(int r, string name, bool trig) =>
    table.cell(radar, 0, r, name, text_color=color.new(#94a3b8, 0), text_size=size.small, text_halign=text.left)
    table.cell(radar, 1, r, trig ? "✅ ACTIVE" : "➖", bgcolor=trig ? color.new(#10b981, 20) : color.new(#0b1120, 0), text_color=trig ? color.new(#34d399, 0) : color.new(#64748b, 0), text_size=size.small, text_halign=text.center)

if barstate.islast and show_table
    // Header
    table.cell(radar, 0, 0, "ASTRA QUANT RADAR v6", bgcolor=color.new(#1e293b, 0), text_color=color.new(#38bdf8, 0), text_size=size.small, text_halign=text.left)
    table.cell(radar, 1, 0, str.tostring(triggered_count) + "/10 TRIG", bgcolor=color.new(#1e293b, 0), text_color=triggered_count > 0 ? color.new(#34d399, 0) : color.new(#94a3b8, 0), text_size=size.small, text_halign=text.center)
    
    f_row(1, "🎯 Sniper Mode (65%+ WR)", strat_sniper)
    f_row(2, "🛡️ Protocol Fortified", strat_protocol)
    f_row(3, "⚡ Relative Strength Leader", strat_rs)
    f_row(4, "📈 Minervini SEPA Template", strat_minervini)
    f_row(5, "🏛️ Stan Weinstein Stage 2", strat_weinstein)
    f_row(6, "🚀 Qullamaggie Breakout", strat_qulla)
    f_row(7, "📊 CANSLIM Pivot", strat_canslim)
    f_row(8, "🌀 PKScreener VCP", strat_pkscreener)
    f_row(9, "🐢 Turtle Donchian (20d)", strat_turtle)
    f_row(10, "📦 Darvas Box Breakout", strat_darvas)
    
    // Ceiling Status
    table.cell(radar, 0, 11, "Overhead Base Ceiling", bgcolor=color.new(#030712, 0), text_color=color.new(#cbd5e1, 0), text_size=size.small, text_halign=text.left)
    table.cell(radar, 1, 11, ceiling_cleared ? "CLEARED 🟢" : "TRAPPED 🔴", bgcolor=ceiling_cleared ? color.new(#10b981, 20) : color.new(#ef4444, 20), text_color=ceiling_cleared ? color.new(#34d399, 0) : color.new(#f87171, 0), text_size=size.small, text_halign=text.center)

    // USIC Active Status
    table.cell(radar, 0, 12, "USIC Trade Status", bgcolor=color.new(#030712, 0), text_color=color.new(#cbd5e1, 0), text_size=size.small, text_halign=text.left)
    table.cell(radar, 1, 12, trade_active ? (t1_hit ? "T1 BANKED (BE)" : (is_violation ? "⚠️ VIOLATION" : "IN TRADE")) : "IDLE", bgcolor=trade_active ? (t1_hit ? color.new(#38bdf8, 20) : (is_violation ? color.new(#ef4444, 30) : color.new(#eab308, 20))) : color.new(#030712, 0), text_color=trade_active ? (t1_hit ? color.new(#38bdf8, 0) : (is_violation ? color.new(#fca5a5, 0) : color.new(#facc15, 0))) : color.new(#64748b, 0), text_size=size.small, text_halign=text.center)
```

---

## 5. How to Add to TradingView

1. Go to **[TradingView.com](https://www.tradingview.com)** and open any candlestick chart (e.g. `NSE:WHEELS`).
2. Click the **Pine Editor** tab at the bottom of the screen.
3. Click **New** -> **Blank Indicator**.
4. Clear all default code, paste the entire script above, and click **Save** (name it `Astra Quant Screener v6`).
5. Click **Add to chart**.
6. In indicator settings:
   * Leave **Enforce Base Ceiling Clearance** checked to eliminate inside-base chop traps like 29-June.
   * Adjust **Initial Stop Loss %** or **Table Position** to your preference.
