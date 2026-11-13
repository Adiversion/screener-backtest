# Validation milestone — the four tests the spec demanded

- Generated: config hash `b1008a242109`
- Universe: 2761 symbols, 2191 sessions (2018-01-01 → 2026-11-13)
- No-lookahead audit: **PASS**

---

## 1. Data integrity — volume regime shifts / price discontinuities

- Bars scanned: **922,002** across 2761 symbols
- Verdict: **VOLUME REGIME SHIFTS FOUND**
- Persistent volume level shifts: **1647**
- Of those, ratio matches a real split ratio: **566** (unexplained: 1081)
- Unadjusted price discontinuities: **0**
- Symbols affected: **456**

> **Honest reading.** `yfinance` is called with `auto_adjust=True`, which back-adjusts OHLC but does **not** split-adjust Volume, so an unadjusted split would be visible here as a flat-price volume step. Only 566 of 1647 shifts match a plausible split ratio (1.25, 1.5, 2.0, 3.0, 4.0, 5.0, 10.0), and price-continuity testing finds no discontinuities at all — so this scan did **not** produce clear evidence of a widespread split-adjustment defect. The remaining 1081 shifts are consistent with genuine liquidity regime changes (index inclusion, rebalance): valid data, but they still break `rvol20` comparability across the shift date, so they are worth seeing.

`360ONE`, `AARTIIND`, `AAVAS`, `ABBOTINDIA`, `ABCAPITAL`, `ABDL`, `ABREL`, `ABSLAMC`, `ACC`, `ACE`, `ACMESOLAR`, `ACUTAAS`, `ADANIENSOL`, `ADANIENT`, `ADANIGREEN`, `ADANIPORTS`, `ADANIPOWER`, `AEGISLOG`, `AEGISVOPAK`, `AETHER`, `AFFLE`, `AIAENG`, `AIIL`, `AJANTPHARM`, `ALKEM`, `AMBER`, `AMBUJACEM`, `ANANTRAJ`, `ANGELONE`, `ANURAS`, `APARINDS`, `APLAPOLLO`, `APOLLOHOSP`, `APOLLOTYRE`, `APTUS`, `ARE&M`, `ASAHIINDIA`, `ASHOKLEY`, `ASIANPAINT`, `ASTERDM`, `ASTRAL`, `ATGL`, `ATHERENERG`, `ATUL`, `AUBANK`, `AUROPHARMA`, `AVANTIFEED`, `AWL`, `AXISBANK`, `AZAD`, `BAJAJFINSV`, `BAJAJHFL`, `BAJAJHLDNG`, `BAJFINANCE`, `BALKRISIND`, `BALRAMCHIN`, `BANDHANBNK`, `BANKBARODA`, `BANKINDIA`, `BATAINDIA`
_...and 396 more symbols._

---
## 2. Redundancy control — is the signal just repackaged momentum?

- Events tested: **109940** across **2164** dates
- Verdict: **NO_INCREMENTAL_INFORMATION**
- _What that means:_ proposed features are not repackaged, but they explain nothing the controls do not already explain. The spec says discard the complexity.
- Proposed features adding information beyond the controls: **0**
- Proposed/control pairs with |rho| >= 0.6: **0**

### Does each proposed feature survive the controls?

| Feature | Verdict | R2 controls only | R2 + feature | dR2 | t |
|---|---|---|---|---|---|
| `retention` | NO_INCREMENT | 0.00497 | 0.00498 | 6e-06 | -0.74 |
| `closing_disp` | NO_INCREMENT | 0.00497 | 0.00547 | 0.000493 | 7.0 |
| `efficiency` | NO_INCREMENT | 0.00497 | 0.00497 | 2e-06 | -0.46 |
| `closing_range` | NO_INCREMENT | 0.00225 | 0.00235 | 9.5e-05 | 3.05 |

### Excluded as definitional identities, not findings

These pairs are algebraically related by construction (`closing_disp == retention x penetration`), so a high correlation between them is arithmetic, not evidence. They are excluded from the verdict above.

| A | B | Spearman rho |
|---|---|---|
| `retention` | `penetration` | 0.769 |
| `closing_disp` | `penetration` | 0.7019 |

### Cross-sectional information coefficient vs forward outcome

| Feature | Dates | IC mean | ICIR | t | % dates positive |
|---|---|---|---|---|---|
| `retention` | 2125 | -0.00102 | -0.0045 | -0.21 | 0.5134 |
| `closing_disp` | 2125 | -0.00312 | -0.0136 | -0.63 | 0.4979 |
| `efficiency` | 2125 | 0.01768 | 0.0803 | 3.7 | 0.5365 |
| `closing_range` | 2120 | -0.00823 | -0.0362 | -1.67 | 0.4844 |
| `ret60` | 2088 | 0.0049 | 0.0198 | 0.9 | 0.5148 |
| `ret120` | 2028 | 0.01426 | 0.0561 | 2.53 | 0.5394 |
| `prox52` | 1900 | 0.0336 | 0.1358 | 5.92 | 0.56 |
| `rvol20` | 2125 | -0.02984 | -0.1306 | -6.02 | 0.4292 |
| `atrpct` | 2125 | -0.04366 | -0.1614 | -7.44 | 0.4438 |
| `penetration` | 2125 | -0.01909 | -0.0843 | -3.89 | 0.4706 |
| `ret20` | 2125 | -0.01358 | -0.0575 | -2.65 | 0.4786 |

---
## 3. Multiple-testing control — Benjamini-Hochberg FDR

> **The null being tested:** p-values test H0: expectancy == the seeded `random` strategy's expectancy (-0.0208). Testing against zero would mark every strategy significant, since nearly all are negative.



- Hypotheses tested: **10** (0 untestable and carried through unreported)
- Expected false positives at alpha=0.05: **~0.5**
- Survive Benjamini-Hochberg FDR: **6**
- Survive Bonferroni (reference): **5**

| Strategy | N | Expectancy | p | q (BH) | BH | Bonferroni |
|:---|---:|---:|---:|---:|:---|:---|
| aae_acceptance | 870 | -0.0225 | 0.4622 | 0.4622 | no | no |
| trap | 2427 | -0.0276 | 0.0005387 | 0.001347 | **yes** | **yes** |
| breakout_day | 8895 | -0.0191 | 0.05601 | 0.08001 | no | no |
| vol_breakout | 20354 | -0.0202 | 0.2888 | 0.3209 | no | no |
| momentum_top | 6279 | -0.0165 | 0.0001809 | 0.000603 | **yes** | **yes** |
| high_52w | 4723 | -0.0177 | 0.005978 | 0.009964 | **yes** | no |
| trend | 157023 | -0.0153 | 3.192e-169 | 0 | **yes** | **yes** |
| fip_proxy | 11107 | -0.0199 | 0.1963 | 0.2453 | no | no |
| high_effort_low_result | 10395 | -0.0184 | 0.001851 | 0.003702 | **yes** | **yes** |
| recovered_after_rej | 1138 | 0.0122 | 4.721e-36 | 0 | **yes** | **yes** |

_10 hypotheses tested at FDR alpha=0.05. 6 survive Benjamini-Hochberg control; roughly 0.5 would be expected to survive by chance alone._

---
## 4. Cross-sectional basket test

- Rebalance **W**, horizon **20** sessions, non-overlapping: **True**
- Rebalances evaluated: **97**
- Round-trip cost assumed: **58.15 bps** on an account of INR 10,000 (the flat DP charge dominates at this size)
- Equal-weight universe benchmark (gross): **0.02019**
- Out-of-sample from: **2021-01-01**

| Score | Top | Rebal | Gross | Net | Cost drag | vs uni (net) | Turnover | OOS net |
|---|---|---|---|---|---|---|---|---|
| `momentum60` | 5 | 95 | 0.03954 | **0.0356** | 0.00394 | 0.0154 | 0.6779 | 0.0452 |
| `momentum60` | 10 | 95 | 0.03919 | **0.03561** | 0.00359 | 0.01541 | 0.6168 | 0.04366 |
| `momentum60` | 20 | 95 | 0.03438 | **0.03095** | 0.00343 | 0.01076 | 0.5895 | 0.03765 |
| `momentum120` | 5 | 92 | 0.04463 | **0.04174** | 0.0029 | 0.02155 | 0.4978 | 0.04701 |
| `momentum120` | 10 | 92 | 0.03685 | **0.03415** | 0.0027 | 0.01396 | 0.4641 | 0.03677 |
| `momentum120` | 20 | 92 | 0.03861 | **0.03616** | 0.00245 | 0.01596 | 0.4217 | 0.03996 |
| `prox52` | 5 | 86 | 0.04007 | **0.03458** | 0.00549 | 0.01439 | 0.9442 | 0.04265 |
| `prox52` | 10 | 86 | 0.03464 | **0.0294** | 0.00523 | 0.00921 | 0.9 | 0.0325 |
| `prox52` | 20 | 86 | 0.03237 | **0.02766** | 0.00471 | 0.00747 | 0.8099 | 0.02846 |
| `breakout` | 5 | 97 | 0.03426 | **0.0286** | 0.00566 | 0.00841 | 0.9732 | 0.03885 |
| `breakout` | 10 | 97 | 0.03335 | **0.0278** | 0.00555 | 0.0076 | 0.9546 | 0.03848 |
| `breakout` | 20 | 97 | 0.0261 | **0.02067** | 0.00543 | 0.00047 | 0.9335 | 0.02734 |
| `acceptance` | 5 | 65 | 0.02588 | **0.02017** | 0.00571 | -2e-05 | 0.9815 | 0.0173 |
| `acceptance` | 10 | 65 | 0.03605 | **0.03043** | 0.00562 | 0.01024 | 0.9662 | 0.03012 |
| `acceptance` | 20 | 65 | 0.03518 | **0.02972** | 0.00545 | 0.00953 | 0.9377 | 0.02836 |

### Walk-forward folds for the best basket (`momentum120` top 5, net)

| Fold | Period | Rebal | Net | Regime |
|---|---|---|---|---|
| 1 | 2018-07-16 → 2020-01-27 | 18 | 0.00341 | IS |
| 2 | 2020-03-02 → 2021-09-13 | 18 | 0.06045 | IS |
| 3 | 2021-10-11 → 2023-05-29 | 19 | 0.03884 | **OOS** |
| 4 | 2023-06-26 → 2025-01-27 | 18 | 0.05421 | **OOS** |
| 5 | 2025-02-24 → 2026-10-05 | 19 | 0.05075 | **OOS** |

_Net columns deduct the real cost model on the fraction of the basket that changed. Every configured top-N is reported; there is no code path that selects a flattering N._

---
## 5. What this means

- Data integrity: 1647 bars sit on a persistent volume level shift, of which 566 match a real split ratio; 0 unadjusted price discontinuities. Any shift breaks rvol20 comparability across that date.
- Redundancy: **no proposed feature adds information beyond the simple momentum/volume controls.** They are not repackaged — they are simply not predictive. The spec says discard the complexity.
- Multiple testing: 10 strategies tested against the seeded random null (-0.0208); 6 survive FDR control versus an expected ~0.5 false positives.
- Cross-sectional: the best basket (`momentum120` top 5) beat the equal-weight universe by 0.0 per rebalance (gross, before costs). Ranking did NOT add value.

> These are research results, not investment advice. Candidates are `HISTORICAL_CANDIDATE`, never "BUY".
