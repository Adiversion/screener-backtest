# Validation milestone — the four tests the spec demanded

- Generated: config hash `b1008a242109`
- Universe: 2720 symbols, 2177 sessions (2018-01-01 → 2026-10-23)
- No-lookahead audit: **PASS**

---

## 1. Data integrity — volume regime shifts / price discontinuities

- Bars scanned: **913,828** across 2720 symbols
- Verdict: **VOLUME REGIME SHIFTS FOUND**
- Persistent volume level shifts: **1643**
- Of those, ratio matches a real split ratio: **566** (unexplained: 1077)
- Unadjusted price discontinuities: **0**
- Symbols affected: **456**

> **Honest reading.** `yfinance` is called with `auto_adjust=True`, which back-adjusts OHLC but does **not** split-adjust Volume, so an unadjusted split would be visible here as a flat-price volume step. Only 566 of 1643 shifts match a plausible split ratio (1.25, 1.5, 2.0, 3.0, 4.0, 5.0, 10.0), and price-continuity testing finds no discontinuities at all — so this scan did **not** produce clear evidence of a widespread split-adjustment defect. The remaining 1077 shifts are consistent with genuine liquidity regime changes (index inclusion, rebalance): valid data, but they still break `rvol20` comparability across the shift date, so they are worth seeing.

`360ONE`, `AARTIIND`, `AAVAS`, `ABBOTINDIA`, `ABCAPITAL`, `ABDL`, `ABREL`, `ABSLAMC`, `ACC`, `ACE`, `ACMESOLAR`, `ACUTAAS`, `ADANIENSOL`, `ADANIENT`, `ADANIGREEN`, `ADANIPORTS`, `ADANIPOWER`, `AEGISLOG`, `AEGISVOPAK`, `AETHER`, `AFFLE`, `AIAENG`, `AIIL`, `AJANTPHARM`, `ALKEM`, `AMBER`, `AMBUJACEM`, `ANANDRATHI`, `ANANTRAJ`, `ANGELONE`, `ANURAS`, `APARINDS`, `APLAPOLLO`, `APOLLOHOSP`, `APOLLOTYRE`, `APTUS`, `ARE&M`, `ASAHIINDIA`, `ASHOKLEY`, `ASIANPAINT`, `ASTERDM`, `ASTRAL`, `ATGL`, `ATHERENERG`, `ATUL`, `AUBANK`, `AUROPHARMA`, `AVANTIFEED`, `AWL`, `AXISBANK`, `AZAD`, `BAJAJFINSV`, `BAJAJHFL`, `BAJAJHLDNG`, `BAJFINANCE`, `BALKRISIND`, `BALRAMCHIN`, `BANDHANBNK`, `BANKBARODA`, `BANKINDIA`
_...and 396 more symbols._

---
## 2. Redundancy control — is the signal just repackaged momentum?

- Events tested: **108727** across **2149** dates
- Verdict: **NO_INCREMENTAL_INFORMATION**
- _What that means:_ proposed features are not repackaged, but they explain nothing the controls do not already explain. The spec says discard the complexity.
- Proposed features adding information beyond the controls: **0**
- Proposed/control pairs with |rho| >= 0.6: **0**

### Does each proposed feature survive the controls?

| Feature | Verdict | R2 controls only | R2 + feature | dR2 | t |
|---|---|---|---|---|---|
| `retention` | NO_INCREMENT | 0.005 | 0.00504 | 3.8e-05 | -1.94 |
| `closing_disp` | NO_INCREMENT | 0.005 | 0.00551 | 0.000508 | 7.08 |
| `efficiency` | NO_INCREMENT | 0.005 | 0.005 | 2e-06 | -0.46 |
| `closing_range` | NO_INCREMENT | 0.00224 | 0.00234 | 9.9e-05 | 3.11 |

### Excluded as definitional identities, not findings

These pairs are algebraically related by construction (`closing_disp == retention x penetration`), so a high correlation between them is arithmetic, not evidence. They are excluded from the verdict above.

| A | B | Spearman rho |
|---|---|---|
| `retention` | `penetration` | 0.7708 |
| `closing_disp` | `penetration` | 0.702 |

### Cross-sectional information coefficient vs forward outcome

| Feature | Dates | IC mean | ICIR | t | % dates positive |
|---|---|---|---|---|---|
| `retention` | 2111 | 0.00109 | 0.0048 | 0.22 | 0.5097 |
| `closing_disp` | 2111 | -0.00182 | -0.0079 | -0.36 | 0.4955 |
| `efficiency` | 2111 | 0.01739 | 0.0799 | 3.67 | 0.5343 |
| `closing_range` | 2106 | -0.0069 | -0.0302 | -1.39 | 0.4881 |
| `ret60` | 2074 | 0.00522 | 0.0211 | 0.96 | 0.5145 |
| `ret120` | 2014 | 0.01323 | 0.052 | 2.33 | 0.5387 |
| `prox52` | 1886 | 0.03293 | 0.1335 | 5.8 | 0.5604 |
| `rvol20` | 2111 | -0.02906 | -0.1272 | -5.85 | 0.4292 |
| `atrpct` | 2111 | -0.04317 | -0.1593 | -7.32 | 0.4453 |
| `penetration` | 2111 | -0.01675 | -0.0745 | -3.42 | 0.4709 |
| `ret20` | 2111 | -0.01236 | -0.052 | -2.39 | 0.4837 |

---
## 3. Multiple-testing control — Benjamini-Hochberg FDR

> **The null being tested:** p-values test H0: expectancy == the seeded `random` strategy's expectancy (-0.0571). Testing against zero would mark every strategy significant, since nearly all are negative.



- Hypotheses tested: **10** (0 untestable and carried through unreported)
- Expected false positives at alpha=0.05: **~0.5**
- Survive Benjamini-Hochberg FDR: **10**
- Survive Bonferroni (reference): **10**

| Strategy | N | Expectancy | p | q (BH) | BH | Bonferroni |
|:---|---:|---:|---:|---:|:---|:---|
| aae_acceptance | 856 | -0.022 | 5.85e-50 | 0 | **yes** | **yes** |
| trap | 2391 | -0.0277 | 1.697e-49 | 0 | **yes** | **yes** |
| breakout_day | 8815 | -0.0191 | 0 | 0 | **yes** | **yes** |
| vol_breakout | 20154 | -0.0203 | 0 | 0 | **yes** | **yes** |
| momentum_top | 6247 | -0.0165 | 2.162e-272 | 0 | **yes** | **yes** |
| high_52w | 4689 | -0.0179 | 3.437e-262 | 0 | **yes** | **yes** |
| trend | 156377 | -0.0152 | 0 | 0 | **yes** | **yes** |
| fip_proxy | 11003 | -0.02 | 0 | 0 | **yes** | **yes** |
| high_effort_low_result | 10308 | -0.0186 | 0 | 0 | **yes** | **yes** |
| recovered_after_rej | 1127 | 0.0117 | 1.785e-149 | 0 | **yes** | **yes** |

_10 hypotheses tested at FDR alpha=0.05. 10 survive Benjamini-Hochberg control; roughly 0.5 would be expected to survive by chance alone._

---
## 4. Cross-sectional basket test

- Rebalance **W**, horizon **20** sessions, non-overlapping: **True**
- Rebalances evaluated: **96**
- Round-trip cost assumed: **58.15 bps** on an account of INR 10,000 (the flat DP charge dominates at this size)
- Equal-weight universe benchmark (gross): **0.02067**
- Out-of-sample from: **2021-01-01**

| Score | Top | Rebal | Gross | Net | Cost drag | vs uni (net) | Turnover | OOS net |
|---|---|---|---|---|---|---|---|---|
| `momentum60` | 5 | 94 | 0.04112 | **0.03717** | 0.00395 | 0.0165 | 0.6787 | 0.0477 |
| `momentum60` | 10 | 94 | 0.0405 | **0.03692** | 0.00358 | 0.01625 | 0.6149 | 0.04575 |
| `momentum60` | 20 | 94 | 0.03517 | **0.03175** | 0.00342 | 0.01107 | 0.5883 | 0.03905 |
| `momentum120` | 5 | 91 | 0.04604 | **0.04311** | 0.00293 | 0.02244 | 0.5033 | 0.04909 |
| `momentum120` | 10 | 91 | 0.03823 | **0.03552** | 0.00272 | 0.01485 | 0.467 | 0.03878 |
| `momentum120` | 20 | 91 | 0.0398 | **0.03734** | 0.00246 | 0.01667 | 0.4231 | 0.04184 |
| `prox52` | 5 | 85 | 0.04137 | **0.03588** | 0.00549 | 0.01521 | 0.9435 | 0.04454 |
| `prox52` | 10 | 85 | 0.03639 | **0.03115** | 0.00524 | 0.01048 | 0.9012 | 0.0349 |
| `prox52` | 20 | 85 | 0.03324 | **0.02852** | 0.00472 | 0.00785 | 0.8112 | 0.02978 |
| `breakout` | 5 | 96 | 0.03559 | **0.02993** | 0.00566 | 0.00926 | 0.9729 | 0.04105 |
| `breakout` | 10 | 96 | 0.03397 | **0.02842** | 0.00555 | 0.00775 | 0.9552 | 0.03959 |
| `breakout` | 20 | 96 | 0.027 | **0.02157** | 0.00543 | 0.0009 | 0.9339 | 0.0289 |
| `acceptance` | 5 | 65 | 0.02595 | **0.02024** | 0.00571 | -0.00043 | 0.9815 | 0.01738 |
| `acceptance` | 10 | 65 | 0.036 | **0.03038** | 0.00562 | 0.00971 | 0.9662 | 0.03005 |
| `acceptance` | 20 | 65 | 0.03587 | **0.03042** | 0.00545 | 0.00975 | 0.9377 | 0.02887 |

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

- Data integrity: 1643 bars sit on a persistent volume level shift, of which 566 match a real split ratio; 0 unadjusted price discontinuities. Any shift breaks rvol20 comparability across that date.
- Redundancy: **no proposed feature adds information beyond the simple momentum/volume controls.** They are not repackaged — they are simply not predictive. The spec says discard the complexity.
- Multiple testing: 10 strategies tested against the seeded random null (-0.0571); 10 survive FDR control versus an expected ~0.5 false positives.
- Cross-sectional: the best basket (`momentum120` top 5) beat the equal-weight universe by 0.0 per rebalance (gross, before costs). Ranking did NOT add value.

> These are research results, not investment advice. Candidates are `HISTORICAL_CANDIDATE`, never "BUY".
