# Decision trail — which stocks, why, and on what evidence

- As of: **2026-10-23**  |  config hash `f4b4e3f7a20e`
- Universe: 2742 symbols, 1496 sessions (2020-10-05 → 2026-10-23)
- No-lookahead audit: **PASS**

> [!CAUTION]
> **MARKET REGIME: DEFENSIVE (CASH)**
> Market is in DEFENSIVE regime: Universe index is below 20-day SMA and breadth is weak (8.3% above SMA20). Capital protection (CASH) recommended.
> *Universe Index: 805.62 (SMA20: 930.91) | Breadth: 8.3% above 20d SMA*

## 1. The one-line answer

**MARKET REGIME DEFENSIVE (CASH): Market is in DEFENSIVE regime: Universe index is below 20-day SMA and breadth is weak (8.3% above SMA20). Capital protection (CASH) recommended. Top defensive candidate is MOREPENLAB (score 0.5926). Capital protection (CASH) advised.**

## 2. What you would buy today

| Rank | Stock | Score | Close | 52w high | ATR% | 120d | RVOL20 | Turnover (20d) | Why |
|---|---|---|---|---|---|---|---|---|---|
| 1 | **MOREPENLAB** | 0.5926 | 146.97 | 1.01184165232358 | 0.04969814310158844 | 2.5218713351075253 | 1.1270484382938433 | 2,198,137,276 | MOREPENLAB scored 0.59/1.00 against 2742 candidates (top: slow trend, no recent chase 100%, near the 52-week high 100%, liquidity 95%). Close INR 146.97, 52w-high 1.01, ATR% 4.97%, RVOL20 1.13, turnover INR 2,198,137,276. |
| 2 | **CYIENT** | 0.5405 | 1233.0 | 1.0114848236259228 | 0.04269050026386357 | 0.4362259755387303 | 34.38952727619804 | 1,818,334,446 | CYIENT scored 0.54/1.00 against 2742 candidates (top: near the 52-week high 100%, liquidity 94%, slow trend, no recent chase 91%). Close INR 1233.00, 52w-high 1.01, ATR% 4.27%, RVOL20 34.39, turnover INR 1,818,334,446. |
| 3 | **SSWL** | 0.5358 | 468.75 | 1.080069124423963 | 0.05492317281210765 | 1.2595429280057546 | 13.3853520369822 | 1,011,232,741 | SSWL scored 0.54/1.00 against 2742 candidates (top: near the 52-week high 100%, slow trend, no recent chase 99%, liquidity 88%). Close INR 468.75, 52w-high 1.08, ATR% 5.49%, RVOL20 13.39, turnover INR 1,011,232,741. |

## 2.1 Multi-Framework Confluence Leaders (Top 10+ Setups)

> [!TIP]
> Evaluated across **12 Institutional Frameworks** (Minervini SEPA, Kristjan Qullamaggie HTF/EP, CANSLIM, PKScreener VCP, Turtle, Darvas Box, Oliver Kell, Weinstein Stage 2, RS Leaders, etc.).

| Rank | Stock | Sector | Confluence | Frameworks Passed | Close (INR) | 52w Proximity | RVOL20 | Delivery % |
|---|---|---|---|---|---|---|---|---|
| 1 | **CYIENT** | Information Technology | **8/12** | Protocol Fortified, Relative Strength Leader, Qullamaggie Breakout (+5 more) | 1233.00 | 100.0% | 43.06x | 10.5% |
| 2 | **KOLTEPATIL** | Unknown | **8/12** | Protocol Fortified, Relative Strength Leader, Minervini Template (+5 more) | 458.30 | 100.0% | 18.64x | 16.9% |
| 3 | **BLUSPRING** | Unknown | **3/12** | Relative Strength Leader, Minervini Template, Connors RSI Pullback | 146.58 | 100.0% | 1.79x | 48.4% |
| 4 | **AAREYDRUGS** | Unknown | **3/12** | Relative Strength Leader, Minervini Template, Connors RSI Pullback | 106.73 | 100.0% | 1.31x | 74.3% |
| 5 | **VALIANTORG** | Chemicals | **3/12** | Relative Strength Leader, Minervini Template, Connors RSI Pullback | 412.65 | 100.0% | 1.62x | 48.8% |
| 6 | **PTCIL** | Capital Goods | **3/12** | Relative Strength Leader, Minervini Template, Connors RSI Pullback | 23455.00 | 100.0% | 1.72x | 39.9% |
| 7 | **LAURUSLABS** | Healthcare | **3/12** | Relative Strength Leader, Minervini Template, Connors RSI Pullback | 1970.00 | 100.0% | 1.29x | 45.3% |
| 8 | **UTTAMSUGAR** | Unknown | **2/12** | Relative Strength Leader, Minervini Template | 352.40 | 100.0% | 1.70x | 26.9% |
| 9 | **SHRINGARMS** | Unknown | **2/12** | Relative Strength Leader, Connors RSI Pullback | 282.57 | 100.0% | 1.77x | 31.8% |
| 10 | **ONEPOINT** | Unknown | **2/12** | Minervini Template, Connors RSI Pullback | 69.17 | 100.0% | 0.55x | 49.5% |

## 3. What each name is made of

| Component | Weight | Measures | Why it matters |
|---|---|---|---|
| Low volatility | 0.25 | ATR as a % of price | IC -0.0434, t -7.35 - the strongest measured effect |
| Near the 52-week high | 0.2 | close vs the prior 252-session high | IC +0.0344, t +6.03 - momentum, in its cleanest form |
| Effort per result | 0.2 | result divided by relative volume | IC +0.0178, t +3.73 - the surviving piece of the framework |
| Slow trend, no recent chase | 0.15 | 120d return minus half the last 20d | ret120 +0.0147 but ret20 -0.0128: slow trend, recent burst reverses |
| Not extended | 0.1 | push past the reference, in ATR | IC -0.0174, t -3.57 - deep penetration is exhaustion |
| Liquidity | 0.05 | 20-session average rupee turnover | tradability, not a return signal |
| Stop room | 0.05 | distance from the close back to the structural reference | MEASURED: stops narrower than 1x ATR were the WORST bucket (+0.23% fwd20) against +1.02% for 1-2 ATR, so tightness is not a virtue -- a stop inside one day's noise gets taken out |
| Reclaimed-reference pattern | 0.05 | the recovered_after_rej pattern fired recently | the only registered rule that ever beat the random null, but never independently validated, so the weight is held small |

### Hard gates — a stock must clear all of these to be ranked

| Gate | Threshold | Why |
|---|---|---|
| 20-day average turnover | `>= INR 50,000,000` | large enough to trade |
| Closing price | `>= INR 20.0` | not a sub-penny lottery ticket |
| 120-day return | `> 0.0` | the slow trend is working |
| Close above the prior 20-session high | `Close > R20` | at its structural high right now |
| Stop width | `1.0x to 5.0x ATR` | wide enough to survive normal noise, not absurdly wide |
| History available | `>= 252 sessions` | enough data to compute the features |
| Data coverage | `= 100% of components computable` | every component had the data it needed |

Excluded for **lack of data**: 441 symbols; **partial data** (ranked, flagged THIN): 2293; full data: 8. Excluded for lack of data is NOT the same as rejected on merit. These names are unknown to the ranking, not judged bad by it.

## 4. Strategies in this engine

| Strategy | Family | Baseline | Rule |
|---|---|---|---|
| `recovered_after_rej` | AAE | B9 | A breakout was rejected (close back under the prior 20-day high), then the level was reclaimed within 3 sessions. Enter on the reclaim. |
| `pa_state_a` | PA | State A | Closed above the prior 20-day high with retention >= 0.60 and closing range >= 0.50 — the accepted-expansion state. |
| `pa_state_b` | PA | State B | Closed above the prior 20-day high but retention or closing range not yet confirmed — pending acceptance. |
| `pa_state_c` | PA | State C | Broke the level intraday, closed slightly below it — rejection, recovery pending. |
| `pa_state_d` | PA | State D | Broke the level, surrendered it and closed near the low — failed acceptance (control: expected to lose). |
| `momentum_top` | rank | B4 | Weekly top-20 by 60-day return. |
| `high_52w` | rank | B5 | Weekly top-20 by proximity to the 252-day high. |
| `vol_breakout` | rank | B3 | Close above the prior 20-day high with RVOL20 >= 1.5. |
| `trend` | rank | B6 | Close > SMA50 > SMA200, 20-day return positive, RSI14 > 50. |
| `trap` | AAE | B1 | Buys anything already up >= 15% over two sessions. The fear being tested. |
| `cash` | AAE | B0 | Never trades. The no-risk reference. |
| `random` | AAE | B0 null | Seeded random (stock, session). Anything at or below this row is noise. |

## 5. The historical evidence behind the rules

| Strategy | N | Hit +15% | No stop | Worse than -7% | Avg net/trade | 95% CI | PF | vs null |
|---|---|---|---|---|---|---|---|---|
| `recovered_after_rej` | 3427 | 0.2705 | 0.7919 | 0.2454 | 0.0175 | 0.0141 to 0.0207 | 1.54 | **beats** |
| `pa_state_a` | 11678 | 0.1344 | 0.6695 | 0.3963 | -0.023 | -0.0245 to -0.0215 | 0.531 | **beats** |
| `trap` | 12754 | 0.1825 | 0.3767 | 0.6553 | -0.0346 | -0.0363 to -0.033 | 0.469 | below null |
| `random` | 1604 | 0.0979 | 0.712 | 0.3566 | -0.0308 | -0.0344 to -0.0271 | 0.378 | below null |

## 6. What this does and does not prove

- Prices are adjusted OHLCV only; no delivery % in the main price file.
- No price-band / ASM / GSM surveillance lists, no corporate-action calendar, so trap filters F4/F6/F9/F10 are unavailable and flagged, never zero-filled.
- History starts 2018, so the protocol's 2015-2020 discovery window is not covered.
- The universe is today's Nifty-500 constituents, so this is a current-constituent backtest, not a survivorship-controlled historical one.
- Event-level results allow many simultaneous trades, so no single-account CAGR/MaxDD is reported unless trades genuinely do not overlap.

Nothing here is investment advice. Candidates are labelled `RESEARCH_CANDIDATE`, never "BUY".