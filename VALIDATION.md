# Validation milestone — the four tests the spec demanded

- Generated: config hash `b1008a242109`
- Universe: 2715 symbols, 2172 sessions (2018-01-01 → 2026-10-16)
- No-lookahead audit: **PASS**

---

## 1. Data integrity — volume regime shifts / price discontinuities

- Bars scanned: **913,474** across 2715 symbols
- Verdict: **VOLUME REGIME SHIFTS FOUND**
- Persistent volume level shifts: **1643**
- Of those, ratio matches a real split ratio: **566** (unexplained: 1077)
- Unadjusted price discontinuities: **0**
- Symbols affected: **457**

> **Honest reading.** `yfinance` is called with `auto_adjust=True`, which back-adjusts OHLC but does **not** split-adjust Volume, so an unadjusted split would be visible here as a flat-price volume step. Only 566 of 1643 shifts match a plausible split ratio (1.25, 1.5, 2.0, 3.0, 4.0, 5.0, 10.0), and price-continuity testing finds no discontinuities at all — so this scan did **not** produce clear evidence of a widespread split-adjustment defect. The remaining 1077 shifts are consistent with genuine liquidity regime changes (index inclusion, rebalance): valid data, but they still break `rvol20` comparability across the shift date, so they are worth seeing.

`360ONE`, `AARTIIND`, `AAVAS`, `ABBOTINDIA`, `ABCAPITAL`, `ABDL`, `ABREL`, `ABSLAMC`, `ACC`, `ACE`, `ACMESOLAR`, `ACUTAAS`, `ADANIENSOL`, `ADANIENT`, `ADANIGREEN`, `ADANIPORTS`, `ADANIPOWER`, `AEGISLOG`, `AEGISVOPAK`, `AETHER`, `AFFLE`, `AIAENG`, `AIIL`, `AJANTPHARM`, `ALKEM`, `AMBER`, `AMBUJACEM`, `ANANDRATHI`, `ANANTRAJ`, `ANGELONE`, `ANURAS`, `APARINDS`, `APLAPOLLO`, `APOLLOHOSP`, `APOLLOTYRE`, `APTUS`, `ARE&M`, `ASAHIINDIA`, `ASHOKLEY`, `ASIANPAINT`, `ASTERDM`, `ASTRAL`, `ATGL`, `ATHERENERG`, `ATUL`, `AUBANK`, `AUROPHARMA`, `AVANTIFEED`, `AWL`, `AXISBANK`, `AZAD`, `BAJAJFINSV`, `BAJAJHFL`, `BAJAJHLDNG`, `BAJFINANCE`, `BALKRISIND`, `BALRAMCHIN`, `BANDHANBNK`, `BANKBARODA`, `BANKINDIA`
_...and 397 more symbols._

---
## 2. Redundancy control — is the signal just repackaged momentum?

- Events tested: **108925** across **2146** dates
- Verdict: **NO_INCREMENTAL_INFORMATION**
- _What that means:_ proposed features are not repackaged, but they explain nothing the controls do not already explain. The spec says discard the complexity.
- Proposed features adding information beyond the controls: **0**
- Proposed/control pairs with |rho| >= 0.6: **0**

### Does each proposed feature survive the controls?

| Feature | Verdict | R2 controls only | R2 + feature | dR2 | t |
|---|---|---|---|---|---|
| `retention` | NO_INCREMENT | 0.00505 | 0.00506 | 3e-06 | -0.55 |
| `closing_disp` | NO_INCREMENT | 0.00505 | 0.00554 | 0.000486 | 6.92 |
| `efficiency` | NO_INCREMENT | 0.00505 | 0.00505 | 2e-06 | -0.47 |
| `closing_range` | NO_INCREMENT | 0.00232 | 0.00242 | 9.7e-05 | 3.09 |

### Excluded as definitional identities, not findings

These pairs are algebraically related by construction (`closing_disp == retention x penetration`), so a high correlation between them is arithmetic, not evidence. They are excluded from the verdict above.

| A | B | Spearman rho |
|---|---|---|
| `retention` | `penetration` | 0.7707 |
| `closing_disp` | `penetration` | 0.7019 |

### Cross-sectional information coefficient vs forward outcome

| Feature | Dates | IC mean | ICIR | t | % dates positive |
|---|---|---|---|---|---|
| `retention` | 2106 | 0.00087 | 0.0039 | 0.18 | 0.5119 |
| `closing_disp` | 2106 | -0.00269 | -0.0118 | -0.54 | 0.4943 |
| `efficiency` | 2106 | 0.01738 | 0.0797 | 3.66 | 0.5323 |
| `closing_range` | 2101 | -0.00766 | -0.0336 | -1.54 | 0.486 |
| `ret60` | 2069 | 0.00588 | 0.0238 | 1.08 | 0.5181 |
| `ret120` | 2009 | 0.01472 | 0.0577 | 2.59 | 0.5416 |
| `prox52` | 1881 | 0.0337 | 0.137 | 5.94 | 0.5614 |
| `rvol20` | 2106 | -0.02956 | -0.13 | -5.97 | 0.4302 |
| `atrpct` | 2106 | -0.042 | -0.1549 | -7.11 | 0.4478 |
| `penetration` | 2106 | -0.01722 | -0.0767 | -3.52 | 0.4677 |
| `ret20` | 2106 | -0.01205 | -0.0511 | -2.34 | 0.4848 |

---
## 3. Multiple-testing control — Benjamini-Hochberg FDR

> **The null being tested:** p-values test H0: expectancy == the seeded `random` strategy's expectancy (-0.02). Testing against zero would mark every strategy significant, since nearly all are negative.



- Hypotheses tested: **10** (0 untestable and carried through unreported)
- Expected false positives at alpha=0.05: **~0.5**
- Survive Benjamini-Hochberg FDR: **4**
- Survive Bonferroni (reference): **4**

| Strategy | N | Expectancy | p | q (BH) | BH | Bonferroni |
|:---|---:|---:|---:|---:|:---|:---|
| aae_acceptance | 865 | -0.0221 | 0.3714 | 0.4643 | no | no |
| trap | 2407 | -0.0275 | 0.0001486 | 0.000495 | **yes** | **yes** |
| breakout_day | 8831 | -0.0192 | 0.3708 | 0.4643 | no | no |
| vol_breakout | 20207 | -0.0203 | 0.5981 | 0.6646 | no | no |
| momentum_top | 6241 | -0.0164 | 0.001776 | 0.004441 | **yes** | **yes** |
| high_52w | 4689 | -0.0178 | 0.05191 | 0.08824 | no | no |
| trend | 156712 | -0.0152 | 8.536e-129 | 0 | **yes** | **yes** |
| fip_proxy | 11011 | -0.0199 | 0.8863 | 0.8863 | no | no |
| high_effort_low_result | 10311 | -0.0185 | 0.05294 | 0.08824 | no | no |
| recovered_after_rej | 1134 | 0.012 | 5.822e-34 | 0 | **yes** | **yes** |

_10 hypotheses tested at FDR alpha=0.05. 4 survive Benjamini-Hochberg control; roughly 0.5 would be expected to survive by chance alone._

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

- Data integrity: 1643 bars sit on a persistent volume level shift, of which 566 match a real split ratio; 0 unadjusted price discontinuities. Any shift breaks rvol20 comparability across that date.
- Redundancy: **no proposed feature adds information beyond the simple momentum/volume controls.** They are not repackaged — they are simply not predictive. The spec says discard the complexity.
- Multiple testing: 10 strategies tested against the seeded random null (-0.02); 4 survive FDR control versus an expected ~0.5 false positives.
- Cross-sectional: the best basket (`momentum120` top 5) beat the equal-weight universe by 0.0 per rebalance (gross, before costs). Ranking did NOT add value.

> These are research results, not investment advice. Candidates are `HISTORICAL_CANDIDATE`, never "BUY".
