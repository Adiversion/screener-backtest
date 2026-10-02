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
in its own GitHub repo (`Adiversion/screener-backtest`) and run on Replit.

Three research protocols are implemented as strategy families:

| Family | Source document | What it tests |
|---|---|---|
| **AAE** — Acceptance-After-Expansion | `ai research.txt` (= `claude-fable-5.1-search.txt`, AAE v2.0) | volume breakout → acceptance hold → expansion trigger, trap filters F1–F11, baselines B0–B9 |
| **PRA** — Pressure→Response→Acceptance | `chatgpt.txt` | effort/response event classes, forward T+1..T+5 outcomes, ablation ladder A–F |
| **PA** — Price-Acceptance states | `Price Acceptance Strategy Origins.pdf` (Gemini) | 4-state A/B/C/D machine + M1–M4 mainstream & N1–N4 community baselines + liquidity gate |
| **Rotation / reference variants** | `gpt 6 astar search max.txt` | cash (no-trade) B0 baseline + STRONG_RETENTION on references 5/10/20/60/252 as separately registered variants |

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
  screen.py     EOD rotation screen: ORGANIC/PENDING/TRAP_RISK/... tags + ranking
  rotation.py   INR 1,000 one-position rotation ledger + metrics + rolling starts
  ingest.py     optional free-data fetch (yfinance, NSE bhavdata, Nifty500 list)
scripts/       run_backtest.py, pra_study.py, pa_study.py, screen_candidates.py,
               rotation_backtest.py, build_report.py, fetch_data.py,
               fetch_delivery.py
RUN_BACKTEST.bat    one-click launcher (also `auto` / `full` / `screen` modes)
schedule_daily.bat  install/remove the daily Windows scheduled task
tests/         unittest suite (no network required)
data/          universe_history.parquet (full), small_universe_history.parquet
reports/       outputs (git-ignored)
.replit, replit.nix, Makefile, requirements.txt, README.md
```

**HARD RULE from the parent repo's `AGENTS.md`: no source file may exceed 300
lines.** Single responsibility, SSOT, no god files. Check with `wc -l` before
committing. Keep it.

---

## 3. Data — what we actually have (be honest)

`data/universe_history.parquet` (the default):

- **499 symbols, 2,166 sessions, 2018-01-01 → 2026-10-01**, adjusted OHLCV only.
- Built with `scripts/fetch_data.py --source nifty500` (yfinance, `auto_adjust=True`),
  from the NSE Nifty-500 constituent CSV (501 symbols; 2 have no data).
- `data/small_universe_history.parquet` (51 symbols) is a fast smoke-test set.

**Missing inputs → reported as NA, never zero-filled:**

- No delivery quantity / % / trade counts → filters **F4** and ATS unavailable.
- No price-band / ASM / GSM / T2T lists → **F6**.
- No results/ex-date corporate-action calendar → **F9**; no circuit-lock history → **F10**.
- No Nifty50 / India VIX history → no regime buckets.
- Bundled data starts 2018, so the protocol's 2015 discovery window is NOT covered.

Every report carries a **`DEGRADED-DATA` watermark** and `data_quality_report()`
counts gaps. **Do not** fabricate delivery/surveillance data.

Grow the universe / add history:

```bash
python scripts/fetch_data.py --source nifty500 --start 2018-01-01 --limit 501
python scripts/fetch_data.py --source bhavdata --days 30            # includes delivery fields
python scripts/fetch_data.py --source bhavdata --date 2026-10-01 --append data/universe_history.parquet
```

`bhavdata` fetches the official NSE full bhavcopy (one request/day, includes
`DELIV_QTY`/`DELIV_PER`/`NO_OF_TRADES`). Wiring those columns into
`features.py` would re-enable F4 — that is the single highest-value next step
(see §8).

---

## 4. How to run

```bash
pip install -r requirements.txt        # pandas numpy pyarrow PyYAML requests yfinance tabulate

make test                              # python -m unittest discover -s tests -v
python scripts/run_backtest.py --strategies all --capital 1000
python scripts/pra_study.py            # PRA event study
python scripts/pa_study.py             # PA State A/B/C/D event study
python scripts/screen_candidates.py    # "what to rotate into" + dashboard.html
python scripts/rotation_backtest.py    # the INR 1,000 one-position rotation
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
`comparison.csv`, and `trades_<strategy>_<cap>.csv`. The rotation screen adds
`ROTATION.md`, `rotation.csv` and `dashboard.html`.

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

## 8. Known gaps / TODO for the next agent

1. **Delivery data — DONE but shallow.** `scripts/fetch_delivery.py` fetches
   the official NSE full bhavcopy and `data.py`/`features.py` now merge and use
   it (filter F4 returns a real bool when data exists, `None` otherwise).
   Limitation: NSE has **no bulk delivery endpoint**, so only a recent window
   (~29 sessions at time of writing) is loaded. To extend, re-run
   `fetch_delivery.py --days N --append`. Full-history delivery would need a
   paid vendor.
2. **History depth**: bundled history starts 2018; the protocol's 2015–2020
   discovery window is under-covered. Extend via `fetch_data.py`.
3. **Surveillance/price-band lists (F6), results calendar (F9), circuit locks
   (F10)** are still unavailable — keep them NA.
4. **Health check**: `python scripts/health_check.py` (if present) — otherwise
   run `make test` + a `--capital 1000 --strategies protocol` smoke run.
5. **Capital sweep cost**: with signals built once it is ~3× simulation. Still
   slow on 499 symbols; consider per-strategy parallelism (`multiprocessing`)
   if it becomes a bottleneck.
6. **Report rendering** uses `tabulate` for the PRA/PA markdown tables; keep
   `tabulate` in `requirements.txt`.
7. **`reports/` is git-ignored**; if you want results committed, force-add the
   specific files or change `.gitignore` deliberately.
8. **Gemini source**: the PA protocol was transcribed from
   `C:\Users\Anadi\Downloads\Documents\Price Acceptance Strategy Origins.pdf`.
   The extracted text is not committed; the state thresholds are in the
   `pa:` block of `config/protocol_v2.yaml`.

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

### INR 1,000 one-position rotation (`scripts/rotation_backtest.py`)

The actual-capital experiment (gpt6 Part B), 2018-01 → 2026-09, 499 symbols:

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

**The rotation does not work, and the reason is costs**: the ₹15.93 DP charge
plus slippage on every trade means ~₹1,904 of fees were paid while the account
started at ₹1,000. Only the most recent rolling start (2026-02-27) is positive;
every earlier start is deeply negative. Report this as-is — do not "fix" it by
changing the capital or dropping costs.

### Rotation output (`scripts/screen_candidates.py`)

Scans the latest session and names the stock to rotate into, tagging every
symbol ORGANIC / PENDING / TRAP_RISK / REJECTED / NO_SETUP / ILLIQUID, and
writes `reports/ROTATION.md`, `reports/rotation.csv` and a self-contained
`reports/dashboard.html`. Last run (as-of 2026-10-01): one ORGANIC candidate
(STLTECH), trap-risk flagged LEMONTREE / MTARTECH / KOTAKBANK / DMART.

---

## 10. Replit

`.replit` runs `python scripts/run_backtest.py --strategies protocol`; `replit.nix`
pins the Python deps. First Replit run should do `pip install -r requirements.txt`
(then optionally `python scripts/fetch_data.py --source nifty500` to refresh data).

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
4. asks *1 quick / 2 full / 3 rotation-screen / 4 everything*,
5. runs the backtest, rebuilds the report bundle, runs the rotation screen,
6. opens `reports\dashboard.html` and `reports\REPORT.html` in the browser.

Keep it CRLF-encoded (it was written with `sed -i 's/$/\r/'`). If you add
steps, do not break the `%~dp0` `cd /d` — it is what makes double-click work
from any working directory.
