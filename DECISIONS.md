# Decision trail — which stocks, why, and on what evidence

- As of: **2026-11-24**  |  config hash `f4b4e3f7a20e`
- Universe: 2857 symbols, 1494 sessions (2020-10-05 → 2026-11-24)
- No-lookahead audit: **PASS**

> [!CAUTION]
> **MARKET REGIME: DEFENSIVE (CASH)**
> Market is in DEFENSIVE regime: Universe index is below 20-day SMA and breadth is weak (22.5% above SMA20). Capital protection (CASH) recommended.
> *Universe Index: 795.88 (SMA20: 945.12) | Breadth: 22.5% above 20d SMA*

## 1. The one-line answer

**MARKET REGIME DEFENSIVE (CASH): Market is in DEFENSIVE regime: Universe index is below 20-day SMA and breadth is weak (22.5% above SMA20). Capital protection (CASH) recommended. Top defensive candidate is MOREPENLAB (score 0.6853). Capital protection (CASH) advised.**

## 2. What you would buy today

| Rank | Stock | Score | Close | 52w high | ATR% | 120d | RVOL20 | Turnover (20d) | Why |
|---|---|---|---|---|---|---|---|---|---|
| 1 | **MOREPENLAB** | 0.6853 | 146.97 | 1.01184165232358 | 0.04969814310158844 | 2.5218713351075253 | 1.1270484382938433 | 2,198,137,276 | MOREPENLAB scored 0.69/1.00 against 2857 candidates (top: slow trend, no recent chase 100%, near the 52-week high 100%, effort per result 99%). Close INR 146.97, 52w-high 1.01, ATR% 4.97%, RVOL20 1.13, turnover INR 2,198,137,276. |

## 2.1 Multi-Framework Confluence Leaders (Top 10+ Setups)

> [!TIP]
> Evaluated across **12 Institutional Frameworks** (Minervini SEPA, Kristjan Qullamaggie HTF/EP, CANSLIM, PKScreener VCP, Turtle, Darvas Box, Oliver Kell, Weinstein Stage 2, RS Leaders, etc.).

| Rank | Stock | Sector | Confluence | Frameworks Passed | Close (INR) | 52w Proximity | RVOL20 | Delivery % |
|---|---|---|---|---|---|---|---|---|
| 1 | **SOUTHBANK** | Financial Services | **2/12** | Relative Strength Leader, Minervini Template | 58.87 | 100.0% | 1.58x | 48.5% |
| 2 | **MODIS** | Unknown | **2/12** | Relative Strength Leader, Minervini Template | 460.25 | 100.0% | 2.94x | 51.2% |
| 3 | **PGIL** | Textiles | **2/12** | Relative Strength Leader, Minervini Template | 1479.40 | 100.0% | 2.04x | 36.0% |
| 4 | **LAURUSLABS** | Healthcare | **2/12** | Relative Strength Leader, Minervini Template | 2370.70 | 100.0% | 1.29x | 38.9% |
| 5 | **MOTILALOFS** | Financial Services | **2/12** | Relative Strength Leader, Minervini Template | 1235.00 | 100.0% | 2.10x | 37.8% |
| 6 | **DIVISLAB** | Healthcare | **2/12** | Relative Strength Leader, Minervini Template | 11203.00 | 100.0% | 2.56x | 66.6% |
| 7 | **NAVINFLUOR** | Chemicals | **2/12** | Relative Strength Leader, Minervini Template | 10154.00 | 100.0% | 1.57x | 40.7% |
| 8 | **KDDL** | Unknown | **2/12** | Relative Strength Leader, Minervini Template | 4604.00 | 100.0% | 2.73x | 17.3% |
| 9 | **SYNCOMF** | Healthcare | **2/12** | Relative Strength Leader, Minervini Template | 22.89 | 100.0% | 3.43x | 17.0% |
| 10 | **EMCURE** | Healthcare | **2/12** | Relative Strength Leader, Minervini Template | 2309.90 | 100.0% | 2.27x | 57.4% |

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

Excluded for **lack of data**: 557 symbols; **partial data** (ranked, flagged THIN): 2294; full data: 6. Excluded for lack of data is NOT the same as rejected on merit. These names are unknown to the ranking, not judged bad by it.

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
| `recovered_after_rej` | 3425 | 0.2709 | 0.7924 | 0.2444 | 0.0176 | 0.0144 to 0.0208 | 1.543 | **beats** |
| `pa_state_a` | 11699 | 0.1346 | 0.6724 | 0.3934 | -0.0227 | -0.0243 to -0.0212 | 0.535 | below null |
| `trap` | 12904 | 0.1803 | 0.3897 | 0.6427 | -0.0343 | -0.036 to -0.0326 | 0.469 | below null |
| `random` | 1591 | 0.1307 | 0.7454 | 0.2967 | -0.0174 | -0.0215 to -0.0132 | 0.603 | below null |

## 6. What this does and does not prove

- Prices are adjusted OHLCV only; no delivery % in the main price file.
- No price-band / ASM / GSM surveillance lists, no corporate-action calendar, so trap filters F4/F6/F9/F10 are unavailable and flagged, never zero-filled.
- History starts 2018, so the protocol's 2015-2020 discovery window is not covered.
- The universe is today's Nifty-500 constituents, so this is a current-constituent backtest, not a survivorship-controlled historical one.
- Event-level results allow many simultaneous trades, so no single-account CAGR/MaxDD is reported unless trades genuinely do not overlap.

Nothing here is investment advice. Candidates are labelled `RESEARCH_CANDIDATE`, never "BUY".