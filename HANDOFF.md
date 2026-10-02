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
  report.py     REPORT.md / report.json / comparison.csv / trade CSVs
  ingest.py     optional free-data fetch (yfinance, NSE bhavdata, Nifty500 list)
scripts/       run_backtest.py, pra_study.py, pa_study.py, fetch_data.py
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
```

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

1. **Delivery data**: ingest `bhavdata` delivery columns into `features.py`
   (`deliv_pct`, `deliv_pct_rel`, `deliv_rvol20`) so filter F4 and the ATS
   study activate. This is the biggest honesty win available.
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

Full 499-symbol NSE (Nifty-500 constituents) run, 2018-01-01 → 2026-09-25,
₹1000 capital, costs included, `--strategies all`:

See **`reports/REPORT.md`** for the live table (regenerate with
`python scripts/run_backtest.py --strategies all --capital 1000`) and
`reports/pa/PA_REPORT.md` / `reports/pra/PRA_REPORT.md` for the event studies.

**Honest summary:** after realistic ₹1000 position costs, essentially no
strategy beats the null/random baseline with statistical confidence on this
data. Individual states separate risk (State A has the best next-day skew,
State D the worst), but that is a risk-control signal, not standalone alpha —
consistent with the PDF's own verdict of **PARTIALLY SUPPORTED**.

Always re-read the `DEGRADED-DATA` banner and the audit block before quoting
any number.

---

## 10. Replit

`.replit` runs `python scripts/run_backtest.py --strategies protocol`; `replit.nix`
pins the Python deps. First Replit run should do `pip install -r requirements.txt`
(then optionally `python scripts/fetch_data.py --source nifty500` to refresh data).

## 11. Git

Repo root for this project is `nse-backtest-engine/` (not the parent
`GSheetScreener` repo). Remote is expected to be
`https://github.com/Adiversion/screener-backtest.git`. `.gitignore` excludes
`reports/`, `.protocol_state.json`, `__pycache__/`.

> Large `data/*.parquet` files are committed. If the repo grows, switch them to
> Git LFS or re-fetch on clone.
