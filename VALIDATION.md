# Validation milestone — the four tests the spec demanded

- Generated: config hash `b1008a242109`
- Universe: 2768 symbols, 2186 sessions (2018-01-01 → 2026-11-06)
- No-lookahead audit: **PASS**

---

## 1. Data integrity — volume regime shifts / price discontinuities

- Bars scanned: **920,684** across 2768 symbols
- Verdict: **VOLUME REGIME SHIFTS FOUND**
- Persistent volume level shifts: **1650**
- Of those, ratio matches a real split ratio: **568** (unexplained: 1082)
- Unadjusted price discontinuities: **0**
- Symbols affected: **457**

> **Honest reading.** `yfinance` is called with `auto_adjust=True`, which back-adjusts OHLC but does **not** split-adjust Volume, so an unadjusted split would be visible here as a flat-price volume step. Only 568 of 1650 shifts match a plausible split ratio (1.25, 1.5, 2.0, 3.0, 4.0, 5.0, 10.0), and price-continuity testing finds no discontinuities at all — so this scan did **not** produce clear evidence of a widespread split-adjustment defect. The remaining 1082 shifts are consistent with genuine liquidity regime changes (index inclusion, rebalance): valid data, but they still break `rvol20` comparability across the shift date, so they are worth seeing.

`360ONE`, `AARTIIND`, `AAVAS`, `ABBOTINDIA`, `ABCAPITAL`, `ABDL`, `ABREL`, `ABSLAMC`, `ACC`, `ACE`, `ACMESOLAR`, `ACUTAAS`, `ADANIENSOL`, `ADANIENT`, `ADANIGREEN`, `ADANIPORTS`, `ADANIPOWER`, `AEGISLOG`, `AEGISVOPAK`, `AETHER`, `AFFLE`, `AIAENG`, `AIIL`, `AJANTPHARM`, `ALKEM`, `AMBER`, `AMBUJACEM`, `ANANDRATHI`, `ANANTRAJ`, `ANGELONE`, `ANURAS`, `APARINDS`, `APLAPOLLO`, `APOLLOHOSP`, `APOLLOTYRE`, `APTUS`, `ARE&M`, `ASAHIINDIA`, `ASHOKLEY`, `ASIANPAINT`, `ASTERDM`, `ASTRAL`, `ATGL`, `ATHERENERG`, `ATUL`, `AUBANK`, `AUROPHARMA`, `AVANTIFEED`, `AWL`, `AXISBANK`, `AZAD`, `BAJAJFINSV`, `BAJAJHFL`, `BAJAJHLDNG`, `BAJFINANCE`, `BALKRISIND`, `BALRAMCHIN`, `BANDHANBNK`, `BANKBARODA`, `BANKINDIA`
_...and 397 more symbols._

---
## 2. Redundancy control — is the signal just repackaged momentum?

- Events tested: **109621** across **2159** dates
- Verdict: **NO_INCREMENTAL_INFORMATION**
- _What that means:_ proposed features are not repackaged, but they explain nothing the controls do not already explain. The spec says discard the complexity.
- Proposed features adding information beyond the controls: **0**
- Proposed/control pairs with |rho| >= 0.6: **0**

### Does each proposed feature survive the controls?

| Feature | Verdict | R2 controls only | R2 + feature | dR2 | t |
|---|---|---|---|---|---|
| `retention` | NO_INCREMENT | 0.005 | 0.005 | 0.0 | -0.16 |
| `closing_disp` | NO_INCREMENT | 0.005 | 0.00548 | 0.000481 | 6.9 |
| `efficiency` | NO_INCREMENT | 0.00499 | 0.005 | 2e-06 | -0.46 |
| `closing_range` | NO_INCREMENT | 0.00226 | 0.00235 | 9.1e-05 | 2.98 |

### Excluded as definitional identities, not findings

These pairs are algebraically related by construction (`closing_disp == retention x penetration`), so a high correlation between them is arithmetic, not evidence. They are excluded from the verdict above.

| A | B | Spearman rho |
|---|---|---|
| `retention` | `penetration` | 0.7694 |
| `closing_disp` | `penetration` | 0.7019 |

### Cross-sectional information coefficient vs forward outcome

| Feature | Dates | IC mean | ICIR | t | % dates positive |
|---|---|---|---|---|---|
| `retention` | 2119 | 0.00085 | 0.0038 | 0.18 | 0.5144 |
| `closing_disp` | 2119 | -0.00293 | -0.0129 | -0.59 | 0.4965 |
| `efficiency` | 2119 | 0.01759 | 0.0812 | 3.74 | 0.5337 |
| `closing_range` | 2114 | -0.00876 | -0.0386 | -1.78 | 0.4853 |
| `ret60` | 2082 | 0.00657 | 0.0265 | 1.21 | 0.5187 |
| `ret120` | 2022 | 0.01513 | 0.0591 | 2.66 | 0.5396 |
| `prox52` | 1894 | 0.03416 | 0.139 | 6.05 | 0.5607 |
| `rvol20` | 2119 | -0.02998 | -0.1309 | -6.03 | 0.4294 |
| `atrpct` | 2119 | -0.0441 | -0.1632 | -7.51 | 0.4431 |
| `penetration` | 2119 | -0.01698 | -0.076 | -3.5 | 0.4729 |
| `ret20` | 2119 | -0.01268 | -0.0535 | -2.46 | 0.4809 |

---
## 3. Multiple-testing control — Benjamini-Hochberg FDR

> **The null being tested:** p-values test H0: expectancy == the seeded `random` strategy's expectancy (-0.0139). Testing against zero would mark every strategy significant, since nearly all are negative.



- Hypotheses tested: **10** (0 untestable and carried through unreported)
- Expected false positives at alpha=0.05: **~0.5**
- Survive Benjamini-Hochberg FDR: **10**
- Survive Bonferroni (reference): **9**

| Strategy | N | Expectancy | p | q (BH) | BH | Bonferroni |
|:---|---:|---:|---:|---:|:---|:---|
| aae_acceptance | 863 | -0.022 | 0.000574 | 0.000638 | **yes** | **yes** |
| trap | 2442 | -0.0278 | 1.095e-12 | 0 | **yes** | **yes** |
| breakout_day | 8875 | -0.0191 | 5.481e-09 | 0 | **yes** | **yes** |
| vol_breakout | 20311 | -0.0202 | 1.096e-28 | 0 | **yes** | **yes** |
| momentum_top | 6265 | -0.0165 | 0.02373 | 0.02373 | **yes** | no |
| high_52w | 4714 | -0.0178 | 0.0005501 | 0.000638 | **yes** | **yes** |
| trend | 157110 | -0.0152 | 5.536e-11 | 0 | **yes** | **yes** |
| fip_proxy | 11095 | -0.0199 | 7.286e-18 | 0 | **yes** | **yes** |
| high_effort_low_result | 10383 | -0.0185 | 2.47e-09 | 0 | **yes** | **yes** |
| recovered_after_rej | 1138 | 0.012 | 7.635e-23 | 0 | **yes** | **yes** |

_10 hypotheses tested at FDR alpha=0.05. 10 survive Benjamini-Hochberg control; roughly 0.5 would be expected to survive by chance alone._

---
## 4. Cross-sectional basket test

- Rebalance **W**, horizon **20** sessions, non-overlapping: **True**
- Rebalances evaluated: **97**
- Round-trip cost assumed: **58.15 bps** on an account of INR 10,000 (the flat DP charge dominates at this size)
- Equal-weight universe benchmark (gross): **0.02025**
- Out-of-sample from: **2021-01-01**

| Score | Top | Rebal | Gross | Net | Cost drag | vs uni (net) | Turnover | OOS net |
|---|---|---|---|---|---|---|---|---|
| `momentum60` | 5 | 95 | 0.03956 | **0.03561** | 0.00394 | 0.01536 | 0.6779 | 0.04522 |
| `momentum60` | 10 | 95 | 0.03929 | **0.0357** | 0.00358 | 0.01545 | 0.6158 | 0.0438 |
| `momentum60` | 20 | 95 | 0.03455 | **0.03112** | 0.00342 | 0.01087 | 0.5889 | 0.0379 |
| `momentum120` | 5 | 92 | 0.04448 | **0.04157** | 0.00291 | 0.02132 | 0.5 | 0.04677 |
| `momentum120` | 10 | 92 | 0.03673 | **0.03402** | 0.00271 | 0.01377 | 0.4652 | 0.03659 |
| `momentum120` | 20 | 92 | 0.03894 | **0.0365** | 0.00245 | 0.01624 | 0.4212 | 0.04045 |
| `prox52` | 5 | 86 | 0.03975 | **0.03426** | 0.00549 | 0.014 | 0.9442 | 0.04222 |
| `prox52` | 10 | 86 | 0.03482 | **0.02958** | 0.00523 | 0.00933 | 0.9 | 0.03274 |
| `prox52` | 20 | 86 | 0.03228 | **0.02757** | 0.00472 | 0.00731 | 0.811 | 0.02834 |
| `breakout` | 5 | 97 | 0.03444 | **0.02878** | 0.00566 | 0.00853 | 0.9732 | 0.03913 |
| `breakout` | 10 | 97 | 0.03317 | **0.02762** | 0.00555 | 0.00737 | 0.9546 | 0.03821 |
| `breakout` | 20 | 97 | 0.02605 | **0.02062** | 0.00543 | 0.00037 | 0.9335 | 0.02727 |
| `acceptance` | 5 | 65 | 0.02588 | **0.02017** | 0.00571 | -8e-05 | 0.9815 | 0.0173 |
| `acceptance` | 10 | 65 | 0.03589 | **0.03027** | 0.00562 | 0.01002 | 0.9662 | 0.02991 |
| `acceptance` | 20 | 65 | 0.0352 | **0.02975** | 0.00545 | 0.0095 | 0.9377 | 0.0284 |

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

- Data integrity: 1650 bars sit on a persistent volume level shift, of which 568 match a real split ratio; 0 unadjusted price discontinuities. Any shift breaks rvol20 comparability across that date.
- Redundancy: **no proposed feature adds information beyond the simple momentum/volume controls.** They are not repackaged — they are simply not predictive. The spec says discard the complexity.
- Multiple testing: 10 strategies tested against the seeded random null (-0.0139); 10 survive FDR control versus an expected ~0.5 false positives.
- Cross-sectional: the best basket (`momentum120` top 5) beat the equal-weight universe by 0.0 per rebalance (gross, before costs). Ranking did NOT add value.

> These are research results, not investment advice. Candidates are `HISTORICAL_CANDIDATE`, never "BUY".
