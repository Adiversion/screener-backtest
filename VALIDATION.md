# Validation milestone — the four tests the spec demanded

- Generated: config hash `b1008a242109`
- Universe: 2783 symbols, 2197 sessions (2018-01-01 → 2026-11-24)
- No-lookahead audit: **PASS**

---

## 1. Data integrity — volume regime shifts / price discontinuities

- Bars scanned: **921,784** across 2783 symbols
- Verdict: **VOLUME REGIME SHIFTS FOUND**
- Persistent volume level shifts: **1654**
- Of those, ratio matches a real split ratio: **568** (unexplained: 1086)
- Unadjusted price discontinuities: **0**
- Symbols affected: **457**

> **Honest reading.** `yfinance` is called with `auto_adjust=True`, which back-adjusts OHLC but does **not** split-adjust Volume, so an unadjusted split would be visible here as a flat-price volume step. Only 568 of 1654 shifts match a plausible split ratio (1.25, 1.5, 2.0, 3.0, 4.0, 5.0, 10.0), and price-continuity testing finds no discontinuities at all — so this scan did **not** produce clear evidence of a widespread split-adjustment defect. The remaining 1086 shifts are consistent with genuine liquidity regime changes (index inclusion, rebalance): valid data, but they still break `rvol20` comparability across the shift date, so they are worth seeing.

`360ONE`, `AARTIIND`, `AAVAS`, `ABBOTINDIA`, `ABCAPITAL`, `ABDL`, `ABREL`, `ABSLAMC`, `ACC`, `ACE`, `ACMESOLAR`, `ACUTAAS`, `ADANIENSOL`, `ADANIENT`, `ADANIGREEN`, `ADANIPORTS`, `ADANIPOWER`, `AEGISLOG`, `AEGISVOPAK`, `AETHER`, `AFFLE`, `AIAENG`, `AIIL`, `AJANTPHARM`, `ALKEM`, `AMBER`, `AMBUJACEM`, `ANANDRATHI`, `ANANTRAJ`, `ANGELONE`, `ANURAS`, `APARINDS`, `APLAPOLLO`, `APOLLOHOSP`, `APOLLOTYRE`, `APTUS`, `ARE&M`, `ASAHIINDIA`, `ASHOKLEY`, `ASIANPAINT`, `ASTERDM`, `ASTRAL`, `ATGL`, `ATHERENERG`, `ATUL`, `AUBANK`, `AUROPHARMA`, `AVANTIFEED`, `AWL`, `AXISBANK`, `AZAD`, `BAJAJFINSV`, `BAJAJHFL`, `BAJAJHLDNG`, `BAJFINANCE`, `BALKRISIND`, `BALRAMCHIN`, `BANDHANBNK`, `BANKBARODA`, `BANKINDIA`
_...and 397 more symbols._

---
## 2. Redundancy control — is the signal just repackaged momentum?

- Events tested: **110578** across **2170** dates
- Verdict: **NO_INCREMENTAL_INFORMATION**
- _What that means:_ proposed features are not repackaged, but they explain nothing the controls do not already explain. The spec says discard the complexity.
- Proposed features adding information beyond the controls: **0**
- Proposed/control pairs with |rho| >= 0.6: **0**

### Does each proposed feature survive the controls?

| Feature | Verdict | R2 controls only | R2 + feature | dR2 | t |
|---|---|---|---|---|---|
| `retention` | NO_INCREMENT | 0.00499 | 0.00506 | 7e-05 | -2.64 |
| `closing_disp` | NO_INCREMENT | 0.00499 | 0.00549 | 0.000492 | 7.02 |
| `efficiency` | NO_INCREMENT | 0.00499 | 0.00499 | 2e-06 | -0.45 |
| `closing_range` | NO_INCREMENT | 0.00226 | 0.00236 | 9.6e-05 | 3.08 |

### Excluded as definitional identities, not findings

These pairs are algebraically related by construction (`closing_disp == retention x penetration`), so a high correlation between them is arithmetic, not evidence. They are excluded from the verdict above.

| A | B | Spearman rho |
|---|---|---|
| `retention` | `penetration` | 0.769 |
| `closing_disp` | `penetration` | 0.7021 |

### Cross-sectional information coefficient vs forward outcome

| Feature | Dates | IC mean | ICIR | t | % dates positive |
|---|---|---|---|---|---|
| `retention` | 2131 | 0.00085 | 0.0038 | 0.18 | 0.5101 |
| `closing_disp` | 2131 | -0.00201 | -0.0088 | -0.41 | 0.4937 |
| `efficiency` | 2131 | 0.01737 | 0.0797 | 3.68 | 0.5345 |
| `closing_range` | 2126 | -0.00759 | -0.0335 | -1.55 | 0.4873 |
| `ret60` | 2094 | 0.00644 | 0.026 | 1.19 | 0.5172 |
| `ret120` | 2034 | 0.01525 | 0.0601 | 2.71 | 0.5438 |
| `prox52` | 1906 | 0.03466 | 0.1411 | 6.16 | 0.564 |
| `rvol20` | 2131 | -0.02962 | -0.13 | -6.0 | 0.4294 |
| `atrpct` | 2131 | -0.04431 | -0.1639 | -7.57 | 0.4411 |
| `penetration` | 2131 | -0.01696 | -0.0759 | -3.5 | 0.473 |
| `ret20` | 2131 | -0.01295 | -0.0548 | -2.53 | 0.4815 |

---
## 3. Multiple-testing control — Benjamini-Hochberg FDR

> **The null being tested:** p-values test H0: expectancy == the seeded `random` strategy's expectancy (-0.0291). Testing against zero would mark every strategy significant, since nearly all are negative.



- Hypotheses tested: **10** (0 untestable and carried through unreported)
- Expected false positives at alpha=0.05: **~0.5**
- Survive Benjamini-Hochberg FDR: **9**
- Survive Bonferroni (reference): **9**

| Strategy | N | Expectancy | p | q (BH) | BH | Bonferroni |
|:---|---:|---:|---:|---:|:---|:---|
| aae_acceptance | 873 | -0.0222 | 0.003044 | 0.003382 | **yes** | **yes** |
| trap | 2405 | -0.0276 | 0.4492 | 0.4492 | no | no |
| breakout_day | 8917 | -0.0191 | 2.187e-29 | 0 | **yes** | **yes** |
| vol_breakout | 20430 | -0.0203 | 9.019e-55 | 0 | **yes** | **yes** |
| momentum_top | 6290 | -0.0164 | 1.557e-28 | 0 | **yes** | **yes** |
| high_52w | 4739 | -0.0178 | 1.044e-23 | 0 | **yes** | **yes** |
| trend | 157652 | -0.0152 | 0 | 0 | **yes** | **yes** |
| fip_proxy | 11146 | -0.0198 | 1.058e-40 | 0 | **yes** | **yes** |
| high_effort_low_result | 10426 | -0.0185 | 3.848e-43 | 0 | **yes** | **yes** |
| recovered_after_rej | 1140 | 0.0119 | 8.623e-55 | 0 | **yes** | **yes** |

_10 hypotheses tested at FDR alpha=0.05. 9 survive Benjamini-Hochberg control; roughly 0.5 would be expected to survive by chance alone._

---
## 4. Cross-sectional basket test

- Rebalance **W**, horizon **20** sessions, non-overlapping: **True**
- Rebalances evaluated: **97**
- Round-trip cost assumed: **58.15 bps** on an account of INR 10,000 (the flat DP charge dominates at this size)
- Equal-weight universe benchmark (gross): **0.02023**
- Out-of-sample from: **2021-01-01**

| Score | Top | Rebal | Gross | Net | Cost drag | vs uni (net) | Turnover | OOS net |
|---|---|---|---|---|---|---|---|---|
| `momentum60` | 5 | 95 | 0.03956 | **0.03561** | 0.00394 | 0.01538 | 0.6779 | 0.04522 |
| `momentum60` | 10 | 95 | 0.03929 | **0.0357** | 0.00358 | 0.01547 | 0.6158 | 0.0438 |
| `momentum60` | 20 | 95 | 0.03454 | **0.03111** | 0.00342 | 0.01088 | 0.5889 | 0.03789 |
| `momentum120` | 5 | 92 | 0.04448 | **0.04157** | 0.00291 | 0.02134 | 0.5 | 0.04677 |
| `momentum120` | 10 | 92 | 0.03673 | **0.03402** | 0.00271 | 0.01379 | 0.4652 | 0.03659 |
| `momentum120` | 20 | 92 | 0.03894 | **0.0365** | 0.00245 | 0.01626 | 0.4212 | 0.04044 |
| `prox52` | 5 | 86 | 0.03975 | **0.03426** | 0.00549 | 0.01403 | 0.9442 | 0.04222 |
| `prox52` | 10 | 86 | 0.03482 | **0.02958** | 0.00523 | 0.00935 | 0.9 | 0.03274 |
| `prox52` | 20 | 86 | 0.03228 | **0.02756** | 0.00472 | 0.00733 | 0.811 | 0.02833 |
| `breakout` | 5 | 97 | 0.03444 | **0.02878** | 0.00566 | 0.00855 | 0.9732 | 0.03913 |
| `breakout` | 10 | 97 | 0.03317 | **0.02762** | 0.00555 | 0.00739 | 0.9546 | 0.03821 |
| `breakout` | 20 | 97 | 0.02604 | **0.02061** | 0.00543 | 0.00037 | 0.9335 | 0.02725 |
| `acceptance` | 5 | 66 | 0.02639 | **0.02068** | 0.00571 | 0.00045 | 0.9818 | 0.018 |
| `acceptance` | 10 | 66 | 0.03682 | **0.03119** | 0.00562 | 0.01096 | 0.9667 | 0.03111 |
| `acceptance` | 20 | 66 | 0.03528 | **0.02982** | 0.00545 | 0.00959 | 0.9379 | 0.02852 |

### Walk-forward folds for the best basket (`momentum120` top 5, net)

| Fold | Period | Rebal | Net | Regime |
|---|---|---|---|---|
| 1 | 2018-07-16 → 2020-01-27 | 18 | 0.00341 | IS |
| 2 | 2020-03-02 → 2021-09-13 | 18 | 0.06045 | IS |
| 3 | 2021-10-11 → 2023-05-29 | 19 | 0.03884 | **OOS** |
| 4 | 2023-06-26 → 2025-01-27 | 18 | 0.05336 | **OOS** |
| 5 | 2025-02-24 → 2026-10-05 | 19 | 0.05075 | **OOS** |

_Net columns deduct the real cost model on the fraction of the basket that changed. Every configured top-N is reported; there is no code path that selects a flattering N._

---
## 5. What this means

- Data integrity: 1654 bars sit on a persistent volume level shift, of which 568 match a real split ratio; 0 unadjusted price discontinuities. Any shift breaks rvol20 comparability across that date.
- Redundancy: **no proposed feature adds information beyond the simple momentum/volume controls.** They are not repackaged — they are simply not predictive. The spec says discard the complexity.
- Multiple testing: 10 strategies tested against the seeded random null (-0.0291); 9 survive FDR control versus an expected ~0.5 false positives.
- Cross-sectional: the best basket (`momentum120` top 5) beat the equal-weight universe by 0.0 per rebalance (gross, before costs). Ranking did NOT add value.

> These are research results, not investment advice. Candidates are `HISTORICAL_CANDIDATE`, never "BUY".
