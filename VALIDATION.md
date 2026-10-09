# Validation milestone — the four tests the spec demanded

- Generated: config hash `b1008a242109`
- Universe: 2697 symbols, 2167 sessions (2018-01-01 → 2026-10-09)
- No-lookahead audit: **PASS**

---

## 1. Data integrity — volume regime shifts / price discontinuities

- Bars scanned: **910,916** across 2697 symbols
- Verdict: **VOLUME REGIME SHIFTS FOUND**
- Persistent volume level shifts: **1642**
- Of those, ratio matches a real split ratio: **566** (unexplained: 1076)
- Unadjusted price discontinuities: **0**
- Symbols affected: **457**

> **Honest reading.** `yfinance` is called with `auto_adjust=True`, which back-adjusts OHLC but does **not** split-adjust Volume, so an unadjusted split would be visible here as a flat-price volume step. Only 566 of 1642 shifts match a plausible split ratio (1.25, 1.5, 2.0, 3.0, 4.0, 5.0, 10.0), and price-continuity testing finds no discontinuities at all — so this scan did **not** produce clear evidence of a widespread split-adjustment defect. The remaining 1076 shifts are consistent with genuine liquidity regime changes (index inclusion, rebalance): valid data, but they still break `rvol20` comparability across the shift date, so they are worth seeing.

`360ONE`, `AARTIIND`, `AAVAS`, `ABBOTINDIA`, `ABCAPITAL`, `ABDL`, `ABREL`, `ABSLAMC`, `ACC`, `ACE`, `ACMESOLAR`, `ACUTAAS`, `ADANIENSOL`, `ADANIENT`, `ADANIGREEN`, `ADANIPORTS`, `ADANIPOWER`, `AEGISLOG`, `AEGISVOPAK`, `AETHER`, `AFFLE`, `AIAENG`, `AIIL`, `AJANTPHARM`, `ALKEM`, `AMBER`, `AMBUJACEM`, `ANANDRATHI`, `ANANTRAJ`, `ANGELONE`, `ANURAS`, `APARINDS`, `APLAPOLLO`, `APOLLOHOSP`, `APOLLOTYRE`, `APTUS`, `ARE&M`, `ASAHIINDIA`, `ASHOKLEY`, `ASIANPAINT`, `ASTERDM`, `ASTRAL`, `ATGL`, `ATHERENERG`, `ATUL`, `AUBANK`, `AUROPHARMA`, `AVANTIFEED`, `AWL`, `AXISBANK`, `AZAD`, `BAJAJFINSV`, `BAJAJHFL`, `BAJAJHLDNG`, `BAJFINANCE`, `BALKRISIND`, `BALRAMCHIN`, `BANDHANBNK`, `BANKBARODA`, `BANKINDIA`
_...and 397 more symbols._

---
## 2. Redundancy control — is the signal just repackaged momentum?

- Events tested: **108764** across **2140** dates
- Verdict: **NO_INCREMENTAL_INFORMATION**
- _What that means:_ proposed features are not repackaged, but they explain nothing the controls do not already explain. The spec says discard the complexity.
- Proposed features adding information beyond the controls: **0**
- Proposed/control pairs with |rho| >= 0.6: **0**

### Does each proposed feature survive the controls?

| Feature | Verdict | R2 controls only | R2 + feature | dR2 | t |
|---|---|---|---|---|---|
| `retention` | NO_INCREMENT | 0.00502 | 0.00504 | 2.2e-05 | -1.46 |
| `closing_disp` | NO_INCREMENT | 0.00502 | 0.0055 | 0.000475 | 6.85 |
| `efficiency` | NO_INCREMENT | 0.00502 | 0.00502 | 2e-06 | -0.47 |
| `closing_range` | NO_INCREMENT | 0.00229 | 0.00239 | 9.3e-05 | 3.02 |

### Excluded as definitional identities, not findings

These pairs are algebraically related by construction (`closing_disp == retention x penetration`), so a high correlation between them is arithmetic, not evidence. They are excluded from the verdict above.

| A | B | Spearman rho |
|---|---|---|
| `retention` | `penetration` | 0.7708 |
| `closing_disp` | `penetration` | 0.7019 |

### Cross-sectional information coefficient vs forward outcome

| Feature | Dates | IC mean | ICIR | t | % dates positive |
|---|---|---|---|---|---|
| `retention` | 2101 | 0.00079 | 0.0035 | 0.16 | 0.5079 |
| `closing_disp` | 2101 | -0.00253 | -0.0111 | -0.51 | 0.4926 |
| `efficiency` | 2101 | 0.01734 | 0.0798 | 3.66 | 0.5317 |
| `closing_range` | 2096 | -0.00713 | -0.0314 | -1.44 | 0.4876 |
| `ret60` | 2064 | 0.00573 | 0.0232 | 1.05 | 0.516 |
| `ret120` | 2004 | 0.01462 | 0.0574 | 2.57 | 0.5384 |
| `prox52` | 1876 | 0.03476 | 0.1415 | 6.13 | 0.5597 |
| `rvol20` | 2101 | -0.02905 | -0.1276 | -5.85 | 0.4307 |
| `atrpct` | 2101 | -0.04237 | -0.1562 | -7.16 | 0.4469 |
| `penetration` | 2101 | -0.01737 | -0.0774 | -3.55 | 0.4698 |
| `ret20` | 2101 | -0.01228 | -0.052 | -2.38 | 0.4807 |

---
## 3. Multiple-testing control — Benjamini-Hochberg FDR

> **The null being tested:** p-values test H0: expectancy == the seeded `random` strategy's expectancy (-0.0322). Testing against zero would mark every strategy significant, since nearly all are negative.



- Hypotheses tested: **10** (0 untestable and carried through unreported)
- Expected false positives at alpha=0.05: **~0.5**
- Survive Benjamini-Hochberg FDR: **10**
- Survive Bonferroni (reference): **9**

| Strategy | N | Expectancy | p | q (BH) | BH | Bonferroni |
|:---|---:|---:|---:|---:|:---|:---|
| aae_acceptance | 862 | -0.0221 | 1.727e-05 | 1.9e-05 | **yes** | **yes** |
| trap | 2408 | -0.0276 | 0.01996 | 0.01996 | **yes** | no |
| breakout_day | 8825 | -0.0192 | 6.903e-48 | 0 | **yes** | **yes** |
| vol_breakout | 20202 | -0.0203 | 4.606e-97 | 0 | **yes** | **yes** |
| momentum_top | 6232 | -0.0163 | 2.795e-43 | 0 | **yes** | **yes** |
| high_52w | 4681 | -0.0177 | 1.624e-37 | 0 | **yes** | **yes** |
| trend | 156593 | -0.0152 | 0 | 0 | **yes** | **yes** |
| fip_proxy | 10994 | -0.0199 | 6.303e-69 | 0 | **yes** | **yes** |
| high_effort_low_result | 10300 | -0.0185 | 7.521e-70 | 0 | **yes** | **yes** |
| recovered_after_rej | 1133 | 0.0122 | 1.47e-63 | 0 | **yes** | **yes** |

_10 hypotheses tested at FDR alpha=0.05. 10 survive Benjamini-Hochberg control; roughly 0.5 would be expected to survive by chance alone._

---
## 4. Cross-sectional basket test

- Rebalance **W**, horizon **20** sessions, non-overlapping: **True**
- Rebalances evaluated: **96**
- Round-trip cost assumed: **58.15 bps** on an account of INR 10,000 (the flat DP charge dominates at this size)
- Equal-weight universe benchmark (gross): **0.02065**
- Out-of-sample from: **2021-01-01**

| Score | Top | Rebal | Gross | Net | Cost drag | vs uni (net) | Turnover | OOS net |
|---|---|---|---|---|---|---|---|---|
| `momentum60` | 5 | 94 | 0.04112 | **0.03717** | 0.00395 | 0.01652 | 0.6787 | 0.0477 |
| `momentum60` | 10 | 94 | 0.0405 | **0.03692** | 0.00358 | 0.01627 | 0.6149 | 0.04575 |
| `momentum60` | 20 | 94 | 0.03524 | **0.03182** | 0.00342 | 0.01117 | 0.5883 | 0.03905 |
| `momentum120` | 5 | 91 | 0.04604 | **0.04311** | 0.00293 | 0.02246 | 0.5033 | 0.04909 |
| `momentum120` | 10 | 91 | 0.03823 | **0.03552** | 0.00272 | 0.01487 | 0.467 | 0.03878 |
| `momentum120` | 20 | 91 | 0.03988 | **0.03742** | 0.00246 | 0.01677 | 0.4236 | 0.04184 |
| `prox52` | 5 | 85 | 0.04137 | **0.03588** | 0.00549 | 0.01523 | 0.9435 | 0.04454 |
| `prox52` | 10 | 85 | 0.03639 | **0.03115** | 0.00524 | 0.0105 | 0.9012 | 0.0349 |
| `prox52` | 20 | 85 | 0.03322 | **0.0285** | 0.00472 | 0.00785 | 0.8118 | 0.0296 |
| `breakout` | 5 | 96 | 0.0356 | **0.02994** | 0.00566 | 0.00929 | 0.9729 | 0.04106 |
| `breakout` | 10 | 96 | 0.03423 | **0.02867** | 0.00555 | 0.00802 | 0.9552 | 0.03998 |
| `breakout` | 20 | 96 | 0.02705 | **0.02162** | 0.00543 | 0.00097 | 0.9344 | 0.0289 |
| `acceptance` | 5 | 65 | 0.02588 | **0.02017** | 0.00571 | -0.00048 | 0.9815 | 0.0173 |
| `acceptance` | 10 | 65 | 0.03589 | **0.03027** | 0.00562 | 0.00962 | 0.9662 | 0.02991 |
| `acceptance` | 20 | 65 | 0.0352 | **0.02975** | 0.00545 | 0.0091 | 0.9377 | 0.0284 |

### Walk-forward folds for the best basket (`momentum120` top 5, net)

| Fold | Period | Rebal | Net | Regime |
|---|---|---|---|---|
| 1 | 2018-07-16 → 2020-01-27 | 18 | 0.00341 | IS |
| 2 | 2020-03-02 → 2021-09-13 | 18 | 0.06045 | IS |
| 3 | 2021-10-11 → 2023-04-24 | 18 | 0.02411 | **OOS** |
| 4 | 2023-05-29 → 2024-12-23 | 18 | 0.06865 | **OOS** |
| 5 | 2025-01-27 → 2026-08-31 | 19 | 0.05751 | **OOS** |

_Net columns deduct the real cost model on the fraction of the basket that changed. Every configured top-N is reported; there is no code path that selects a flattering N._

---
## 5. What this means

- Data integrity: 1642 bars sit on a persistent volume level shift, of which 566 match a real split ratio; 0 unadjusted price discontinuities. Any shift breaks rvol20 comparability across that date.
- Redundancy: **no proposed feature adds information beyond the simple momentum/volume controls.** They are not repackaged — they are simply not predictive. The spec says discard the complexity.
- Multiple testing: 10 strategies tested against the seeded random null (-0.0322); 10 survive FDR control versus an expected ~0.5 false positives.
- Cross-sectional: the best basket (`momentum120` top 5) beat the equal-weight universe by 0.0 per rebalance (gross, before costs). Ranking did NOT add value.

> These are research results, not investment advice. Candidates are `HISTORICAL_CANDIDATE`, never "BUY".
