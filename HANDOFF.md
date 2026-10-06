# HANDOFF — screener-backtest (NSE strategy backtest & benchmarking engine)

Written for the next agent picking this up cold. Read this before changing
anything. It covers what exists, why, what is honest vs degraded, and the
exact commands to run/verify everything.

---

## 1. What this project is

A **standalone, strategy-agnostic backtest & benchmarking engine** for the NSE
cash-equity universe. Any universe size, pluggable strategies, tweakable
parameters, side-by-side comparison with a buy-and-hold benchmark.

It is deliberately separate from the main `GSheetScreener` app so it can live
in its own GitHub repo (`Adiversion/screener-backtest`) and run unattended on
GitHub Actions.

Three research protocols are implemented as strategy families:

| Family | Source document | What it tests |
|---|---|---|
| **AAE** — Acceptance-After-Expansion | `ai research.txt` (= `claude-fable-5.1-search.txt`, AAE v2.0) | volume breakout → acceptance hold → expansion trigger, trap filters F1–F11, baselines B0–B9 |
| **PRA** — Pressure→Response→Acceptance | `chatgpt.txt` | effort/response event classes, forward T+1..T+5 outcomes, ablation ladder A–F |
| **PA** — Price-Acceptance states | `Price Acceptance Strategy Origins.pdf` (Gemini) | 4-state A/B/C/D machine + M1–M4 mainstream & N1–N4 community baselines + liquidity gate |
| **Reference variants** | `gpt 6 astar search max.txt` | cash (no-trade) B0 baseline + STRONG_RETENTION on references 5/10/20/60/252 as separately registered variants |

> **Direction (current):** the ₹1,000 rotation experiment was **deleted** — its
> result was an honest loss (see §9). The engine's job is now to **find good,
> quality stocks to invest in**: `protocol/quality.py` blends the surviving
> signals into one ranked shortlist, `protocol/evidence.py` supplies the
> historical evidence, and `scripts/decisions.py` is the headline CLI.

---

## 2. Repository layout & hard rules

`nse-backtest-engine/` (its own git repo; branch `main`)

```
config/protocol_v2.yaml     SINGLE SOURCE OF TRUTH for every threshold
protocol/                   engine internals (one responsibility per file)
  config.py     YAML load + canonical SHA256 + discovery/validation gate
  data.py       parquet/CSV load, column normalisation, data-quality report
  costs.py      CostModel (fees/slippage/DP charge) — all fee math lives here
  features.py   A3 features (ATR, RVOL20, R5..R252, retention, penetration, ...)
  states.py     AAE state machine (breakout -> hold -> expansion)
  filters.py    A5 trap filters F1..F11 (unavailable inputs -> NA, never zero)
  signals.py    TradeSignal contract shared by all strategies
  strategies.py       core AAE strategies + cash/random baselines
  strategies_rank.py  B4/B5/B7 weekly cross-sectional top-N baselines
  strategies_pra.py   PRA strategies incl. reference variants
  strategies_pa.py    PA state strategies + M1/N1–N4 baselines
  pra.py        PRA event classifier + forward outcomes + ablation
  pa.py         PA A/B/C/D state classifier + liquidity mask + state study
  simulator.py  ONE exit engine for every strategy (stop/target/time/momentum-fail)
  metrics.py    cohort stats, seeded bootstrap CIs, single-position portfolio
  audit.py      no-lookahead audit (truncation, shuffle, static scan, ordering, cutoff)
  engine.py     orchestration: build_signals once per strategy, simulate per capital
  report.py     REPORT.md / slim report.json / comparison.csv / trade CSVs
  report_html.py  dynamic self-contained REPORT.html (KPI cards, chart, audit)
  screen.py     EOD candidate screen: ORGANIC/PENDING/TRAP_RISK/... tags + ranking
  quality.py    blended stock-quality score, hard gates, per-stock reason
  evidence.py   strategy catalogue, cohort stats, beats-null comparison, caveats
  ingest.py     optional free-data fetch (yfinance, NSE bhavdata, Nifty500 list)
scripts/       run_backtest.py, decisions.py, screen_candidates.py,
               pra_study.py, pa_study.py, build_report.py, strategy_index.py,
               fetch_data.py, fetch_delivery.py
RUN_BACKTEST.bat    one-click launcher (also `auto` / `full` / `screen` modes)
schedule_daily.bat  install/remove the daily Windows scheduled task
tests/         unittest suite (no network required)
data/          universe_history.parquet (full), small_universe_history.parquet
reports/       outputs (git-ignored)
Makefile, requirements.txt, README.md
```

**HARD RULE from the parent repo's `AGENTS.md`: no source file may exceed 300
lines.** Single responsibility, SSOT, no god files. Check with `wc -l` before
committing. Keep it.

---

## 3. Data — what we actually have (as of October 5, 2026)

- `data/nse_all_history.parquet`: **2,000+ listed cash equities, 2,568,895 rows, through 2026-10-05**.
  Contains official NSE Bhavcopy cash equity price bars (`Series == 'EQ'`) appended directly from NSE.
- `data/universe_history.parquet`: **499 symbols, 899,935 rows, through 2026-10-05**.
- `data/delivery_history.parquet`: **40-day delivery quantities, percentages, and turnover** from official NSE Bhavdata, activating Filter F4 and institutional absorption detection.
- `data/sec_list_latest.csv`, `data/board_meetings.csv`, `data/corporate_actions.csv`: Official NSE surveillance (ASM, GSM, T2T), upcoming earnings, dividends, splits, and bonus issues.
- `data/small_universe_history.parquet` (51 symbols): fast smoke-test set for quick unit tests.

**Data Ingestion & Refresh:**
```bash
# Append latest session Bhavcopy cash equity bars into history
python scripts/fetch_data.py --source bhavdata --days 1 --append data/nse_all_history.parquet

# Refresh rolling delivery history (activates Filter F4 & delivery absorption)
python scripts/fetch_delivery.py --days 40

# Refresh corporate events & surveillance lists
python scripts/fetch_nse_annex.py
```

---

## 4. How to run

```bash
pip install -r requirements.txt        # pandas numpy pyarrow PyYAML requests yfinance tabulate

make test                              # python -m unittest discover -s tests -v
python scripts/run_backtest.py --strategies all --capital 1000
python scripts/pra_study.py            # PRA event study
python scripts/pa_study.py             # PA State A/B/C/D event study
python scripts/decisions.py --top 10   # ranked good stocks + reason + evidence
python scripts/screen_candidates.py    # session tag board + dashboard.html
python scripts/fetch_delivery.py --days 40   # NSE delivery data (activates F4)
python scripts/build_report.py         # re-render md/html/slim json from report.json
```

On Windows: double-click `RUN_BACKTEST.bat` (interactive), or use
`RUN_BACKTEST.bat auto|full|screen` for unattended runs. `schedule_daily.bat
install 19:00` registers a daily Windows task that runs the `auto` mode and
logs to `reports\scheduled_run.log`.

**Running without a PC** — `.github/workflows/update-reports.yml` runs the whole
pipeline on GitHub's servers daily at 19:00 IST (or on demand via
**Actions → Run workflow**), then force-publishes `reports/` to the `live`
branch and uploads an artifact. `.github/workflows/pages.yml` optionally deploys
the same content to GitHub Pages (enable once: **Settings → Pages → Source:
GitHub Actions**). `Colab_Backtest.ipynb` runs the whole engine from a browser
tab with no install. The local `schedule_daily.bat` Windows task and the GitHub
Actions schedule are **independent** — disable whichever you do not want.

**Output formats for each run** (`reports/`): `REPORT.html` (dynamic,
self-contained, human-friendly), `REPORT.md`, `report.json` (**slim** — metrics
only, no per-trade rows, so an agent can read the whole thing),
`comparison.csv`, and `trades_<strategy>_<cap>.csv`. `scripts/decisions.py` adds
`DECISIONS.md` + `decisions.json`; the candidate screen adds `CANDIDATES.md`,
`candidates.csv` and `dashboard.html`.

> **Do not** put per-trade rows back into `report.json` — it ballooned to
> 251 MB for the full universe before `report.summary_payload` stripped them.

Key CLI flags (`scripts/run_backtest.py`):

- `--symbols all | path/to/list.txt | SYM1,SYM2`
- `--strategies protocol | all | name1,name2`
- `--capital 1000` (omit for the 3-tier sensitivity sweep)
- `--mode discovery | validation | exploratory` (`--exploratory` bypasses the hash gate)
- `--cutoff 2026-09-25`, `--outdir reports`
- `--set state0.rvol_min=2.5 --set run.bootstrap_n=2000` (dotted overrides, no file edits)

**Performance note:** signals are computed **once per strategy** in
`engine.build_signals` and reused across capitals (`run_strategy(..., signals=...)`).
`pra.classify_events` and `pa.classify_states` are **vectorised** (numpy) —
keep them that way. On the 499-symbol universe a full `--strategies all`
3-capital run is heavy; use a single `--capital` for quick iterations.

---

## 5. Adding / tweaking strategies

> **See `STRATEGIES.md`** for the catalogue of all 29 registered strategies
> (rule, family, source) and a fuller five-step authoring guide with tests.

Register a builder in any `protocol/strategies*.py`:

```python
from protocol.strategies import register
from protocol.signals import TradeSignal

@register("my_setup")
def my_setup(panel, cfg) -> list[TradeSignal]:
    out = []
    for symbol, feat in panel.items():
        d = feat.reset_index(drop=True)
        ok = (d["Close"] > d["R20"]) & (d["rvol20"] >= 2.0)
        for idx in np.where(ok.fillna(False).to_numpy())[0]:
            i = int(idx)
            if i + 1 < len(d):
                out.append(TradeSignal("my_setup", symbol, d["Date"].iloc[i],
                                       d["Date"].iloc[i + 1], float(d["Close"].iloc[i]),
                                       stop_pct=0.07, meta={}))
    return out
```

Then import the module in `protocol/__init__.py`, add params under
`strategies.<name>` in `config/protocol_v2.yaml`, and you automatically get the
shared simulator, costs, metrics, comparison table and trade CSVs.

**Never** put exit logic or fee math in a strategy — that lives in
`simulator.py` / `costs.py` so every cohort stays comparable.

Available feature columns (see `features.py`): `atr14, atrpct, rvol20,
result_atr, dir_result, closing_range, body_eff, efficiency, R5, R10, R20, R60,
R252, penetration, closing_disp, retention, ema20, extension, ret2, ret20,
ret60, ret120, prox52, pos_day_freq60, turnover20` and the delivery columns
(always `NaN` today).

---

## 6. Config hash gate (discovery → validation)

`config/protocol_v2.yaml` is hashed (canonical JSON, sorted keys) into
`cfg["_hash"]` and embedded in every report.

```bash
python scripts/run_backtest.py --mode discovery     # freezes the hash to .protocol_state.json
python scripts/run_backtest.py --mode validation    # refuses to run on a changed hash
python scripts/run_backtest.py --mode validation --exploratory   # watermarked override
```

**Any edit to the YAML changes the hash and invalidates the frozen discovery
run.** That is intentional. Current hash is printed at the top of every report;
trust the file over this document.

---

## 7. No-lookahead guarantees

`protocol/audit.py` runs before any report is written: truncation-identity,
shuffle-future, static scan (forbids `shift(-`, `center=True`, `bfill`,
`backfill` in protocol source), signal-before-entry ordering, and cutoff. The
report embeds `audit.passed`. Reporting labels are `HISTORICAL_CANDIDATE` /
`SKIP_<reason>` — never "BUY", and never any participant-identity inference.

---

## 8. Current System Capabilities (Implemented & Operational)

1. **Delivery Data & Institutional Absorption**: `scripts/fetch_delivery.py` merges official NSE Bhavdata delivery quantities and percentages. Filter F4 and delivery surge detection are active.
2. **Surveillance & Corporate Actions**: `scripts/fetch_nse_annex.py` tracks ASM, GSM, Trade-to-Trade (T2T), earnings dates, and corporate actions directly from NSE feeds.
3. **Market Regime Engine**: `protocol/regime.py` computes an equal-weight universe index against its 20-day SMA and calculates market breadth (% of stocks > 20d SMA) to output BULL vs DEFENSIVE directives.
4. **Multi-Framework Screening**: `protocol/frameworks.py` evaluates 12 quantitative models simultaneously (Protocol Fortified, Minervini Trend Template, Stan Weinstein Stage 2, Qullamaggie Breakout, CANSLIM Pivot, PKScreener VCP, Turtle Trading, Darvas Box, Wyckoff Closing Range, Sector Momentum, Delivery Absorption, Connors RSI).
5. **Weekly Timeframe Confluence**: `protocol/weekly.py` and `scripts/screen_weekly.py` resample daily history into weekly bars, scoring 11 macro structural gates, assigning grades (A+ to C), and applying an anti-climax exhaustion cap.
6. **Executive Briefing & GitHub Pages**:
   - `protocol/dashboard_data.py` aggregates hard-gate leaders, multi-confluence setups, dual timeframe consensus, and swing watchlists.
   - `docs/index.html` and `docs/report.html` provide an interactive web app with `⚡ Briefing` view and TradingView chart inspector.
7. **Pre-Push Browser Audit Gateway**: `scripts/pre_push_check.py` runs headless Playwright tests before any git push to prevent regressions in GitHub Pages.
8. **Automated CI/CD**: `.github/workflows/update-reports.yml` runs daily at 17:30 IST (12:00 UTC), appends latest Bhavcopy EQ bars, re-runs screens, streams the synthesized markdown to `$GITHUB_STEP_SUMMARY`, and updates GitHub Pages.

---

## 9. Current results

Full **499-symbol Nifty-500** run, 2018-01-01 → 2026-09-25 (2,162 sessions),
₹1000 capital, all costs included, `--strategies all`, audit PASS.
Regenerate with `python scripts/run_backtest.py --strategies all --capital 1000`.
Live table: **`reports/REPORT.md`** / **`reports/comparison.csv`**; event
studies in `reports/pa/PA_REPORT.md` and `reports/pra/PRA_REPORT.md`.

Head of the comparison (Expectancy = mean net P&L % per trade):

| Strategy | N | WinRate | SafeRate | Expectancy | PF | TailBreach |
|---|---|---|---|---|---|---|
| **recovered_after_rej** | 1126 | 0.202 | 0.857 | **+0.0126** | 1.44 | 0.176 |
| pra_retention_r252 | 4546 | 0.159 | 0.721 | −0.0130 | 0.70 | 0.331 |
| trend | 156624 | 0.121 | 0.781 | −0.0151 | 0.62 | 0.277 |
| pa_state_a | 7769 | 0.126 | 0.745 | −0.0175 | 0.59 | 0.319 |
| random (null) | 1368 | 0.110 | 0.780 | −0.0177 | 0.57 | 0.284 |
| pa_state_d | 8510 | 0.120 | 0.760 | −0.0181 | 0.58 | 0.312 |
| aae_acceptance | 862 | 0.073 | 0.527 | −0.0221 | 0.44 | **0.143** |
| trap (B1) | 2381 | 0.195 | 0.450 | **−0.0274** | 0.55 | **0.588** |
| cash (B0) | 0 | — | — | — | — | — |

**The whole story, honestly:**

1. **`recovered_after_rej` (B9) is the only strategy with positive expectancy**
   (~+1.3% net per trade, PF 1.44, SafeRate 86%) — and it clears the seeded
   random null at ~−1.8%. In words: *a breakout that is rejected, then
   reclaims its reference level, is where the edge lives on this data.* Its
   MaxDD is still brutal (−93%) because the portfolio model is one position
   at a time at ₹1000.
2. **The trap baseline is the worst strategy** (Exp −2.7%, TailBreach 59%) —
   buying stocks already up ≥15% over two sessions loses, exactly the fear the
   protocol was built to test.
3. **The PA state machine is a risk descriptor, not alpha.** States A/B/C/D
   all land within ~0.2% expectancy of each other; State A's separation shows
   up only in next-day *skew* (PDF's own verdict: PARTIALLY SUPPORTED).
4. **High-trade-count strategies (trend, N-counts in the 10k–150k range) are
   cost-dominated** — ₹1000 positions pay a flat ₹15.93 DP charge plus
   slippage, which eats the edge.
5. `aae_acceptance` has the **lowest TailBreach (0.143)** and the best drawdown
   profile among the AAE cohorts — a risk filter, not a return generator.

Always re-read the `DEGRADED-DATA` banner and the audit block before quoting
any number. The `random` row is the honest null; anything at or below it is
noise.

### Deleted: the INR 1,000 one-position rotation

`protocol/rotation.py`, `scripts/rotation_backtest.py` and
`tests/test_rotation.py` were **git rm`'d**. The experiment was the actual-capital
one (gpt6 Part B), 2018-01 → 2026-09 over 499 symbols, and it lost:

| Metric | Value |
|---|---|
| Final value | **₹5.10** (from ₹1,000) |
| Total return / CAGR | **−99.5% / −56%** |
| Max drawdown | −99.6% |
| Trades | 103 |
| Target-first / stop-first / time | 24% / 48% / 28% |
| Expectancy / profit factor | −4.6% / 0.40 |
| **Total fees on ₹1,000** | **₹1,904** |
| Longest losing streak | 10 |

**The reason is costs**: the ₹15.93 DP charge plus slippage on every trade means
~₹1,904 of fees were paid while the account started at ₹1,000. Only the most
recent rolling start was positive. Kept here as a finding, not as code — do not
re-add it, and do not "fix" the numbers by changing the capital or the costs.

### Finding good stocks (`protocol/quality.py` + `scripts/decisions.py`)

`decisions.py` is now the headline command. It scores every symbol on six
components, applies hard gates, and ranks what clears them. Weights and gates
live in `config/protocol_v2.yaml` under `quality:` — a **frozen judgement, not
a fit**; changing them is a new experiment, not a tweak.

| Component | Weight | Measures |
|---|---|---|
| acceptance | 0.30 | retention into the close + closing range vs the prior 20-day high |
| trend | 0.20 | 60-day and 120-day return |
| liquidity | 0.15 | 20-day average rupee turnover (log) |
| volume_sanity | 0.15 | RVOL vs its 20-session mean — a tent, fades when too quiet or too frantic |
| risk | 0.10 | distance from close back to the structural reference |
| edge | 0.10 | the reclaimed-reference pattern fired in the last 20 sessions |

Gates (all must pass): 20-day turnover ≥ ₹5 crore, close ≥ ₹20, 60d > 0,
120d > 0, close > R20 with positive penetration, risk-to-ref ≤ 8%, ≥ 252
sessions of history.

The `edge` component exists because **exactly one rule beats the seeded random
null** — `recovered_after_rej`, +0.0125 net/trade vs −0.0177 for the null,
bootstrap CI 0.0074 → 0.0177. Everything else is at or below the null.

Every name is labelled a **HISTORICAL_CANDIDATE**, never "BUY". No participant
identity is inferred anywhere in the output.

### Candidate board (`scripts/screen_candidates.py`)

Scans the latest session, tagging every symbol ORGANIC / PENDING / TRAP_RISK /
REJECTED / NO_SETUP / ILLIQUID, and writes `reports/CANDIDATES.md`,
`reports/candidates.csv` and a self-contained `reports/dashboard.html`.
This is the raw unranked board; `decisions.py` is the ranked shortlist.

---

## 9b. Validation milestone (`scripts/validate.py`)

Four tests the research protocol demanded and that had never been run. Writes
`reports/VALIDATION.md` + `validation.json`. Consumes `reports/report.json`, so
run `run_backtest.py` first.

| # | Module | Question |
|---|---|---|
| 1 | `dataqc.py` | Volume regime shifts / unadjusted price gaps? |
| 2 | `redundancy.py` | Is the signal just repackaged momentum? |
| 3 | `inference.py` | How many strategies survive BH-FDR? |
| 4 | `crosssec.py` | Do top-5/10/20 baskets beat the equal-weight universe? |

**Rules learned the hard way — do not undo these:**

- The FDR p-values must test against the **seeded `random` expectancy**, never
  against 0. Nearly every strategy here is negative, so a zero-null flags all
  27 as "significant" and means nothing.
- `closing_disp == retention x penetration` **exactly**, by definition. Those
  pairs are excluded as definitional identities (`DEFINITIONAL_PAIRS`) — a high
  correlation there is arithmetic, not a finding.
- "Not repackaged" is **not** a pass. A feature that is uncorrelated with
  momentum but explains nothing either gets `NO_INCREMENTAL_INFORMATION`, and
  the spec says discard the complexity.
- In `dataqc`, persistence must compare the PRE-shift window to a window two
  periods later. Comparing the two post-shift windows tests whether volume kept
  *rising*, which silently undercounts real shifts.
- `NaN < threshold` is `False`, so unfiltered NaNs pass a threshold gate. Every
  NaN check must be explicit (`np.isfinite`).
- Constant volume has zero variance, so the Welch t-stat is 0/0. Synthetic test
  fixtures need noisy volume.
- Missing feature data must return `None`, not `0.0` (`quality.components`).

---

## 10. Running it in the cloud

GitHub Actions is the primary route — the repo is pure Python on
pandas/numpy/PyYAML, so nothing needs a cloud IDE.

- `.github/workflows/update-reports.yml` runs daily at 19:00 IST and on demand
  (**Actions → Update live reports → Run workflow**), then force-publishes
  `reports/` to the `live` branch and uploads an artifact.
- `.github/workflows/pages.yml` deploys the same content to GitHub Pages. Enable
  once: **Settings → Pages → Source: GitHub Actions**.
- `Colab_Backtest.ipynb` runs the whole engine from a browser tab as a
  convenience fallback.
- `schedule_daily.bat` (local Windows task) is **independent** of the GitHub
  schedule — disable whichever you do not want.

`.replit` / `replit.nix` are no longer a documented route.

## 11. Git

The project lives at **`D:\screener-backtest`**. It was deliberately MOVED OUT
of `D:\GSheetScreener` so the two git repos cannot absorb each other
(GSheetScreener saw it as an untracked nested repo and would have committed it
as a broken embedded repo on the next `git add -A`).

- `origin = https://github.com/Adiversion/screener-backtest.git`, branch `main`.
- `.gitignore` excludes `reports/`, `.protocol_state.json`, `__pycache__/`.
- All scripts derive paths from `Path(__file__)`, so they work from any folder.

> Large `data/*.parquet` files are committed (32 MB). If the repo grows,
> switch them to Git LFS or re-fetch on clone.

---

## 12. One-click Windows launcher

`RUN_BACKTEST.bat` (at the repo root) is the whole product for a non-technical
user. Double-click it and it:

1. finds Python (`py` then `python`),
2. `pip install -r requirements.txt`,
3. refreshes data with `fetch_data.py --source nifty500`,
4. asks *1 quick / 2 full / 3 stock-picks / 4 everything*,
5. runs the backtest, rebuilds the report bundle, then runs `decisions.py`
   (ranked shortlist) and `screen_candidates.py` (tag board),
6. opens `reports\dashboard.html` and `reports\REPORT.html` in the browser.

Keep it CRLF-encoded (it was written with `sed -i 's/$/\r/'`). If you add
steps, do not break the `%~dp0` `cd /d` — it is what makes double-click work
from any working directory.
