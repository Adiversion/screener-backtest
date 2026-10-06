# Production Audit — what actually runs

**Status:** draft for review. This document describes the **live production system**
only. It deliberately ignores the legacy research docs (`README.md`,
`ENGINE_REVIEW.md`, `STRATEGIES.md`, `STRATEGY_INDEX.md`), which describe the
earlier AAE/PRA/PA backtest engine and no longer match the deployed product.

Everything below was extracted from the code with static analysis (module
inventory, import graph, reachability from entry points) plus direct reading of
the production modules. Line numbers are approximate (they move).

---

## 1. What "production" means here

| Surface | Trigger | What runs |
|---|---|---|
| Daily refresh | `.github/workflows/update-reports.yml`, 17:30 IST (12:00 UTC) | fetch bhavcopy EQ → backtest → validate → decisions → screen → weekly confluence → summary report → build sites → verdict audit → tests → force-push `live` branch |
| Portfolio guardian | `.github/workflows/guard-portfolio.yml`, every 15 min, market hours | `scripts/track_paper_portfolio.py --once` |
| Published site | `.github/workflows/pages.yml` on `live` push | GitHub Pages serves the generated dashboard (`index.html`, `report.html`) |
| Local/CI checks | `Makefile`, `package.json` | `run_backtest`, `pra_study`, `pa_study`, `screen_candidates`, `screen_weekly`, `decisions`, `fetch_data`, `pre_push_check`, `build_interactive_dashboard` |

**Production entry points (16 scripts):**
`fetch_data`, `fetch_delivery`, `fetch_nse_annex`, `fetch_universe`,
`run_backtest`, `validate`, `decisions`, `screen_candidates`, `screen_weekly`,
`build_site`, `build_interactive_dashboard`, `verdict_audit`,
`track_paper_portfolio`, `pra_study`, `pa_study`, `pre_push_check`.

---

## 2. Architecture (data flow)

```
                 yfinance / NSE bhavcopy / NSE annex / delivery
                                   │
                        protocol/ingest.py, protocol/data.py
                                   │
                       data/*.parquet  +  data/*.csv (surveillance, events, sector)
                                   │
        ┌──────────────────────────┴───────────────────────────┐
        │                                                       │
  RESEARCH / BACKTEST                                   PRODUCT / DASHBOARD
  features → signals → simulator → metrics               github_screeners (13 screeners)
  → reporting (md/html/json)                              + sniper_mode (7 gates)
  scripts/run_backtest.py                                 + wyckoff_pa, corporate_events
  scripts/validate.py (dataqc, redundancy,               → dashboard_data.build_candidate_data
    inference, crosssec)                                  → dashboard_html (template)
  scripts/verdict_audit.py                                → docs/*.html  (GitHub Pages)
                                                          scripts/build_interactive_dashboard.py
  scripts/decisions.py  (quality ranking + confluence)
  scripts/screen_candidates.py  (EOD tag board)
  scripts/build_site.py  (research site: site.py → site_html)
        │
        └──────────────► reports/  (git-ignored build output)
```

The **product** (what users see) is the interactive dashboard:
12→13 frameworks, Sniper Mode, Wyckoff/PA badges, corporate-event audits,
the Forward Verifier, and the Paper Trading station. The **research** side
(backtest, validation, rotation) feeds numbers in but is not the product.

---

## 3. Inventory

**57 modules under `protocol/`, 29 scripts under `scripts/`.**

### 3.1 Core data & features (shared plumbing)
| Module | Purpose |
|---|---|
| `data.py` | price access; `load_history`, delivery merge, quality report |
| `ingest.py` | free sources: bhavcopy, yfinance, index constituents |
| `features.py` | `build_features` / `build_panel` (all windows lagged ≥1) |
| `levels.py` | durable levels beyond the rolling window |
| `costs.py` | single fee model (`CostModel`) |
| `signals.py` | the `TradeSignal` contract |
| `config.py` | YAML + stable hash |
| `audit.py` | no-lookahead audit |

### 3.2 Product / dashboard
| Module | Purpose |
|---|---|
| `github_screeners.py` | **the 13 screeners** (484 L — over house rule) |
| `frameworks.py` | canonical registry of the 13 screeners (added in refactor) |
| `sniper_mode.py` | 7-gate Sniper badge + `screen_sniper_mode` |
| `wyckoff_pa.py` | Wyckoff effort/result + PA state badges |
| `corporate_events.py` | surveillance (ASM/GSM/circuit), board meetings, actions |
| `sector.py` | sector map, diversification, industry momentum |
| `regime.py` | breadth, BULL/NEUTRAL/DEFENSIVE, O'Neil FTD |
| `dashboard_data.py` | builds the candidate payload (327 L) |
| `dashboard_html.py` | injects JSON into the template |
| `forward_verifier.py` | replay engine (356 L) |
| `universe_lookup.py` | inspector search / forensics (381 L) |
| `sizing.py` | volatility risk-parity position sizing |
| `staged_execution.py` | staged exit simulation |
| `exits.py` | 4 dynamic exit strategies |

### 3.3 Research / backtest (feeds numbers, not the product)
| Module | Purpose |
|---|---|
| `simulator.py`, `metrics.py`, `engine.py` | trade simulation + metrics |
| `strategies*.py` (5 modules) | 29 registered research strategies |
| `states.py`, `filters.py`, `pra.py`, `pa.py` | AAE/PRA/PA research machinery |
| `quality.py`, `ranking.py` | the evidence-weighted ranking |
| `dataqc.py`, `redundancy.py`, `inference.py`, `crosssec.py` | the 4 validation tests |
| `walk_forward.py`, `rotation.py` | walk-forward + rotation studies |
| `verdict.py`, `participation.py` | decile/outcome audit, participation study |
| `site.py`, `site_html.py`, `site_js.py`, `site_assets.py` | the research site |
| `reporting/` (4 modules) | md/html/json rendering |

---

## 4. Dependency snapshot (protocol internals)

Most-imported (fan-in):
- `data`, `features`, `config` → pulled in by ~20 scripts each.
- `github_screeners` → `dashboard_data`, `forward_verifier`, `frameworks`, `sniper_mode`, `decisions`.
- `sector`, `sniper_mode` → `dashboard_data`, `forward_verifier`, `universe_lookup`.
- `frameworks` → `dashboard_data`, `decisions` (post-refactor).

The product cluster (`dashboard_data` → `github_screeners` + `sniper_mode` +
`wyckoff_pa` + `corporate_events` + `regime` + `sector` + `forward_verifier` +
`universe_lookup`) is fairly self-contained and does **not** import the research
cluster (`states`, `filters`, `pra`, `pa`, `strategies*`). That is the natural
seam for any future split.

---

## 5. Reachability

- **No `protocol/` module is unreachable** from the production entry points —
  `protocol/__init__.py` imports all five strategy modules for registration, so
  the whole package is pulled in transitively.
- **14 scripts are NOT referenced by any production entry point**
  (diagnostic/research only):
  `bar_coverage`, `build_report`, `entry_rules`, `hold_ledger`, `judge`,
  `pa_signals`, `pick_and_hold`, `rank_diagnosis`, `rotate`, `rotation_grid`,
  `run_walk_forward`, `sign_experiment`, `strategy_index`, `which_to_pick`.

---

## 6. The 13 frameworks — and Sniper Mode's 7 gates

### 6.1 The 13 registered screeners (`protocol/frameworks.py`)
1 Protocol Fortified · 2 Relative Strength Leader · 3 Minervini Template ·
4 Stan Weinstein Stage 2 · 5 Qullamaggie Breakout · 6 CANSLIM Pivot ·
7 PKScreener VCP · 8 Turtle Trading · 9 Darvas Box · 10 Wyckoff Closing Range ·
11 Sector Momentum Leader · 12 Institutional Delivery Absorption ·
13 **Connors RSI Pullback**

**Sniper Mode is NOT one of them.** It is a per-candidate badge
(`evaluate_sniper_gates` → `is_sniper`), computed separately in
`dashboard_data.py`.

### 6.2 Sniper Mode's 7 gates (from `protocol/sniper_mode.py`)
| # | Gate | Exact code condition |
|---|---|---|
| 1 | Stage 2 trend | `Close > SMA50 > SMA200` |
| 2 | RS leader | `rs_rating >= 80` |
| 3 | VCP compression | `range20 <= 0.14` *(docstring says ≤8% — stale)* |
| 4 | Wyckoff absorption | `closing_range >= 0.65` **and** `rvol20 >= 1.3` |
| 5 | Extension veto | `ext_sma50 <= 0.20` |
| 6 | Delivery | `deliv_pct is None` **or** `>= 45` |
| 7 | Sector tailwind | `ind_rank is None` **or** `>= 50` |

`is_sniper = passed >= 6`; `screen_sniper_mode` relaxes to `passed >= 5` when
nothing qualifies, but still returns results labelled `SNIPER_MODE_65`.

### 6.3 Are Sniper's gates the same as the frameworks'? **Yes — mostly.**
Every Sniper gate already exists inside one or more frameworks, usually with a
slightly different cut-point:

| Sniper gate | Same condition already inside framework(s) | Cut-point difference |
|---|---|---|
| 1 Stage 2 | 1 Protocol Fortified, 2 RS, 6 CANSLIM, 7 VCP, 8 Turtle, 9 Darvas, 10 Wyckoff, 11 Sector, 12 Delivery (**9 of 13**) | identical |
| 2 RS ≥ 80 | 2 Relative Strength Leader (`>= 80`) | identical; #6 uses 70, #4 uses 65 |
| 3 range20 ≤ 0.14 | 9 Darvas (`<= 0.18`), 7 PKScreener VCP (ratio `range20 < range60*0.85`) | tighter than Darvas, different form than VCP |
| 4 CR ≥ .65 & RVOL ≥ 1.3 | 10 Wyckoff Closing Range | identical CR; RVOL 1.3 vs **1.4** |
| 5 ext ≤ 0.20 | 1 Protocol Fortified, 10 Wyckoff (`<= 0.20`) | identical; most others use 0.25 |
| 6 deliv ≥ 45 | 12 Institutional Delivery (`>= 50`) | looser by 5 pts |
| 7 ind_rank ≥ 50 | 11 Sector Momentum Leader (`>= 60`) | looser by 10 pts |

**Conclusion:** Sniper Mode is not an independent framework. It is an **AND
re-composition of thresholds that already live in the 13 frameworks**, with a
few cut-points shifted and two gates that pass automatically when data is
missing. So it double-counts signals the confluence count already contains, and
its "7 institutional gates" are largely the same institutional gates.

Additionally, Sniper is used inconsistently:
- `dashboard_data.py` → badge only (excluded from confluence).
- `forward_verifier.py` → used as a **candidate source** ("Sniper Mode (65%+ WR)")
  alongside the 10 strategies. Same signal, two roles.

---

## 7. Findings register (consolidated)

| # | Severity | Finding | Evidence |
|---|---|---|---|
| F1 | High | **Framework count drift: 13 registered, every label says "/12".** A stock can render "13/12 FRAMEWORKS ACHIEVED". | `frameworks.FRAMEWORK_COUNT == 13`; ``/12` in `dashboard_template.html` (11 literals), `evidence.py:137,153`, `decisions.py:260,268` |
| F2 | High | **Sniper gates 6 & 7 pass on missing data** (`None` → `True`), inflating the pass count; violates "unknown ≠ pass". | `sniper_mode.py` gates 6, 7 |
| F3 | High | **Sniper overclaims**: `SNIPER_MODE_65` label with an unmeasured ">65% WR"; internal 6→5 relaxation keeps the label. | `sniper_mode.py` docstring + `screen_sniper_mode` fallback |
| F4 | High | **Guardian (Python) and browser (JS) diverge**: Python applies all rules per tick; JS returns after the first. | `track_paper_portfolio.evaluate_staged_positions` vs template `checkAutomaticExecution` |
| F5 | High | **Five exit engines** for the same idea: `staged_execution`, `forward_verifier.simulate_single_stock_forward`, `exits` (4 strategies), `track_paper_portfolio`, browser JS. Different rules/costs. | module docstrings + code |
| F6 | Med | **Regime computed but not enforced**: DEFENSIVE does not block entries in the dashboard/sniper/paper paths. | `regime.py` intent vs no consumer gate |
| F7 | Med | **Non-determinism**: `list(cands_set)[:15]` in the Forward Verifier — `set[str]` order is randomized per process, so results can differ per run. | `forward_verifier.build_forward_verification_suite` |
| F8 | Med | **Endogenous relaxations**: sniper 6→5, Connors 25→32, delivery 50→40, sector fallback — strictness depends on the day; relaxations are not recorded/surfaced. | the four screeners |
| F9 | Med | **Overstated independence**: confluence counts overlapping conditions as independent votes (see §6.3). | §6 |
| F10 | Med | **Hardcoded dates** in production: `target_dates = {"2026-10-01", ...}` and weekend labels; silently falls back after those dates. | `forward_verifier.py` |
| F11 | Low | **Cost basis inconsistency**: staged sims use flat 25 bps; the guardian uses `CostModel` (DP + rates). | `staged_execution.py` vs `costs.py` |
| F12 | Low | **Dead field**: `framework_count` kept in the paper-trading payload but never produced by `_build_single_candidate`. | `dashboard_html.py` keep-list |
| F13 | Low | **House-rule breach (≤300 L)**: `github_screeners` 484, `universe_lookup` 381, `forward_verifier` 356, `dashboard_data` 327, `quality` 305, `dataqc` 302. | line counts |
| F14 | Low | **Sniper role inconsistency**: badge in the dashboard, screener in the forward verifier. | §6.3 |
| F15 | Low | **Stale docstrings**: sniper gate 3 "≤8%" vs code 14%; "12 frameworks" vs 13; "10 strategies" references. | see F1, F2 |

---

## 8. Open questions / decisions needed

1. **F1:** is the intended denominator 13, or is one framework deliberately
   excluded from the "12"? (Recommend: inject `FRAMEWORK_COUNT` everywhere.)
2. **F3:** does Sniper Mode keep a "65% WR" claim, or is it relabelled to what
   is measured?
3. **F4/F5:** which exit semantics is canonical — all-rules-per-tick (guardian)
   or first-rule (browser)? (Recommend: all-rules, since the guardian polls
   every 15 min; make the browser match.)
4. **F6:** should DEFENSIVE hard-block new entries, or only scale size down?
5. **§5:** are the 14 diagnostic-only scripts still wanted?

---

## 9. Suggested next step

Turn this into a refactor plan with two workstreams:
- **Correctness (F1–F4, F7, F10):** small, testable, high-value; no new features.
- **Consolidation (F5, F9, F13):** introduce a single execution spec and a single
  source of truth for counts/labels; split the oversized product modules.

No code has been changed by this audit; the only prior edits were the earlier
refactor (see git status) plus the test correction.
