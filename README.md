# screener-backtest

Strategy-agnostic backtest & benchmarking engine for the NSE cash-equity
universe. Pluggable strategies, tweakable parameters, any universe size
(≈100 today, 500+ via the ingest layer), and a side-by-side comparison table
with a buy-and-hold benchmark.

Two research protocols are implemented as strategies:

| Family | Source | What it tests |
|---|---|---|
| **AAE** — Acceptance-After-Expansion | `ai research.txt` / `claude-fable-5.1-search.txt` | volume breakout → acceptance hold → expansion trigger, with trap filters and baselines B0–B9 |
| **PRA** — Pressure → Response → Acceptance | `chatgpt.txt` | effort/response event classes, forward T+1/T+2/T+3/T+5 outcomes, ablation ladder A–F |
| **PA** — Price-Acceptance states | `Price Acceptance Strategy Origins.pdf` | 4-state A/B/C/D machine + M1–M4 mainstream and N1–N4 community baselines + the PDF's liquidity gate |
| **Rotation / reference variants** | `gpt 6 astar search max.txt` | cash (no-trade) baseline + STRONG_RETENTION on references 5/10/20/60/252 as separately registered variants |

## One click (Windows)

Double-click **`RUN_BACKTEST.bat`**. It installs the dependencies, refreshes
the Nifty-500 data, asks whether you want a quick/full backtest or just the
rotation screen, then opens the HTML reports in your browser.

## Quick start

```bash
pip install -r requirements.txt

# compare every protocol strategy at ₹1000
python scripts/run_backtest.py --strategies protocol --capital 1000

# compare *all* registered strategies (incl. PRA + rank baselines)
python scripts/run_backtest.py --strategies all

# PRA event study (state -> T+n outcome table + ablation)
python scripts/pra_study.py
python scripts/pra_study.py --start 2026-09-21 --end 2026-09-25   # strict historical week

# PA State A/B/C/D event study
python scripts/pa_study.py

# tests
python -m unittest discover -s tests -v
```

## Report bundle

Every run writes the same story in three formats to `reports/`:

| File | Format | For |
|---|---|---|
| `REPORT.html` | dynamic, self-contained | humans — KPI cards, sortable/filterable table, expectancy bars, audit block. Just open it in a browser (no server). |
| `REPORT.md` | Markdown | quick reading / diffs |
| `report.json` | slim JSON (metrics only, **no** per-trade rows) | AI agents |
| `comparison.csv` | CSV | spreadsheets |
| `trades_<strategy>_<cap>.csv` | CSV | per-trade forensics |

Re-render the bundle from an existing `report.json` without re-running the
strategies (also strips trade rows):

```bash
python scripts/build_report.py
```

## Running on Replit

1. Import this repo into Replit (it reads `.replit` + `replit.nix`).
2. The default run is `python scripts/run_backtest.py --strategies protocol`.
3. To backtest the full Nifty 500, run `python scripts/fetch_data.py --source nifty500 --start 2018-01-01`
   once — it downloads adjusted OHLCV into `data/universe_history.parquet`, then rerun the backtest.

## What to rotate into today

```bash
python scripts/screen_candidates.py            # latest session
python scripts/screen_candidates.py --asof 2026-09-25 --top 5
```

Tags every symbol `ORGANIC` / `PENDING` / `TRAP_RISK` / `REJECTED` /
`NO_SETUP` / `ILLIQUID`, names the stock to rotate into, and writes
`reports/ROTATION.md`, `reports/rotation.csv` and a self-contained,
filterable **`reports/dashboard.html`** (open it in any browser — no server).

## Tweaking a strategy

Thresholds live in `config/protocol_v2.yaml` (single source of truth; every
report embeds its SHA256). Override anything from the CLI without editing files:

```bash
python scripts/run_backtest.py --strategies aae_acceptance \
  --set state0.rvol_min=2.5 \
  --set state2.stop_distance_max=0.07 \
  --set strategies.trap.ret2_min=0.20
```

Disable individual trap filters for an ablation:

```bash
python scripts/run_backtest.py --set filters.disabled='[F1,F5]'
```

## Universe

```bash
--symbols all                 # every symbol in the data file (default)
--symbols data/nifty500.txt   # a symbol list file
--symbols RELIANCE,TCS,INFY   # explicit list
```

## Strategies

`cash` (B0), `trap` (B1), `breakout_day` (B2), `vol_breakout` (B3),
`momentum_top` (B4), `high_52w` (B5), `trend` (B6), `fip_proxy` (B7),
`high_effort_low_result` (B8), `recovered_after_rej` (B9), `random`,
`aae_acceptance`, `pra_strong_retention`, `pra_expansion_attempt`,
`pra_high_effort_low_result`, `pra_full`, `pra_retention_r{5,10,60,252}`,
`pa_state_{a,b,c,d}` (Price-Acceptance states), `m1_momentum_composite`, and the
community scanners `n1_eod_momentum`, `n2_consolidation_breakout`,
`n3_absorption`, `n4_effort_result_discrepancy`.

**→ [`STRATEGIES.md`](STRATEGIES.md) lists every strategy with its exact rule
and gives a five-step, copy-paste guide to adding your own.**

Add your own in `protocol/strategies*.py` with the `@register("name")`
decorator — it returns `TradeSignal`s and inherits the shared simulator,
costs, metrics and comparison table automatically.

## Data honesty

The bundled dataset is **adjusted OHLCV only, 499 Nifty-500 symbols,
2018-01 → 2026-10** (built with `scripts/fetch_data.py --source nifty500`;
`data/small_universe_history.parquet` is a 51-symbol smoke-test set).
There is **no delivery, price-band/ASM/GSM, circuit-lock or corporate-action
calendar** data, so filters F4/F6/F9/F10 are reported as `NA` and flagged
`filter_incomplete` — never zero-filled. Reports carry a `DEGRADED-DATA` banner.
Run `scripts/fetch_data.py` to grow the universe via NSE bhavdata (which does
include delivery fields) or yfinance.

## Discovery / validation gate

```bash
python scripts/run_backtest.py --mode discovery      # freezes the config hash
python scripts/run_backtest.py --mode validation      # refuses on hash mismatch
python scripts/run_backtest.py --mode validation --exploratory   # watermarked
```

## Layout

```
protocol/   config, data, features, states, filters, simulator, costs,
            metrics, strategies (+rank, +pra, +pa), pra, pa, audit, engine,
            report, ingest
scripts/    run_backtest.py, pra_study.py, pa_study.py, fetch_data.py
config/     protocol_v2.yaml
tests/      features/states, simulator/costs/metrics/audit, pra, pa
```

Every source file stays under 300 lines; a single no-lookahead audit
(truncation, shuffle-future, static scan, ordering, cutoff) must pass before a
report is produced.
