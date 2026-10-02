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
| **Reference variants** | `gpt 6 astar search max.txt` | cash (no-trade) baseline + STRONG_RETENTION on references 5/10/20/60/252 as separately registered variants |

> **What this engine is *for*:** finding good, quality stocks to invest in.
> The strategy tables tell you which *rules* survive history; the
> [quality ranking](#finding-good-stocks-to-invest-in) turns those rules into
> one ranked shortlist of today's stocks, each with a reason and its
> historical evidence.

## One click (Windows)

Double-click **`RUN_BACKTEST.bat`**. It installs the dependencies, refreshes
the Nifty-500 data, asks whether you want a quick/full backtest or just the
stock picks, then opens the HTML reports in your browser.

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

# rank today's good stocks, with the reason and the evidence behind each
python scripts/decisions.py --top 10

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

## Running in the cloud (GitHub Actions, no PC needed)

Everything is pure Python on pandas/numpy/PyYAML, so GitHub Actions is the
primary cloud route — it runs the full pipeline on GitHub's servers and
publishes the results. You do not need a cloud IDE.

1. **Actions → Update live reports → Run workflow** to run it on demand.
2. It also runs automatically every day at 19:00 IST.
3. Reports are published to the `live` branch and uploaded as an artifact.
4. For a browsable URL, enable Pages once: **Settings → Pages → Source:
   GitHub Actions**.

To run it yourself without GitHub, `Colab_Backtest.ipynb` runs the whole
engine in a browser tab (**Runtime → Run all**).

## Validation milestone — is the signal real?

```bash
python scripts/validate.py               # the four tests below
python scripts/validate.py --quick       # skip the cross-sectional pass
```

This consumes `reports/report.json`, so run `run_backtest.py` first. It writes
`reports/VALIDATION.md` and `reports/validation.json`. It answers the four
questions the research protocol demanded and that had never been answered:

| # | Test | Question | Module |
|---|---|---|---|
| 1 | Data integrity | Do volume regime shifts or unadjusted price discontinuities corrupt the volume features? | `protocol/dataqc.py` |
| 2 | **Redundancy control** | Is the proposed signal just repackaged momentum? | `protocol/redundancy.py` |
| 3 | **Benjamini-Hochberg FDR** | How many of the 27 strategies survive multiple-testing control? | `protocol/inference.py` |
| 4 | **Cross-sectional baskets** | Do top-5/10/20 baskets beat the equal-weight universe? | `protocol/crosssec.py` |

Test 2 is the important one. The protocol's closing principle is *"try to
answer: is there information here that simpler models do not already
contain? If the answer is no, discard the complexity."* It reports a verdict
of `INDEPENDENT`, `PARTLY INCREMENTAL`, `REPACKAGED`,
`NO_INCREMENTAL_INFORMATION` or `INCONCLUSIVE`, and never rounds an
"adds nothing" result up to a pass.

Test 3's p-values test against the **seeded `random` strategy's expectancy**,
not against zero — every strategy in this study is negative, so a zero-null
would mark all of them significant and mean nothing.

> BH assumes independence between tests. The PA/PRA variants are heavily
> overlapping rules, so the true false-discovery rate is higher than the
> nominal one. The Bonferroni column is shown alongside as a conservative
> reference.

## Unknown is not the same as bad

A stock with no 120-day history is **UNKNOWN** on trend — which is a
different statement from a stock whose trend is genuinely flat. Scoring
missing data as `0.0` would let an insufficient-history name score as "bad
but investable" and rank among genuinely-assessed names.

So components that cannot be computed return `None`, never `0.0`, and the
ranking reports a **data coverage** fraction with a `FULL` / `THIN` /
`INSUFFICIENT_DATA` status. `quality.data_sufficiency_report()` lists who was
excluded for *lack of data* separately from who was rejected on merit — in a
2300-name universe, recent IPOs are a real slice of the market.

## Finding good stocks to invest in

```bash
python scripts/decisions.py --top 10
```

This is the headline command. It blends the surviving technical signals into
**one ranked list of today's stocks**, each with a one-sentence reason and the
historical cohort evidence behind it. Output: `reports/DECISIONS.md` and
`reports/decisions.json`.

**Hard gates** — a stock is not ranked at all unless it clears *all* of these
(`config/protocol_v2.yaml` → `quality:`):

| Gate | Threshold | Why |
|---|---|---|
| 20-day average turnover | ≥ ₹5 crore | you must be able to get in and out at your size |
| Closing price | ≥ ₹20 | not a lottery ticket |
| 60-day return | > 0 | the stock is already working |
| 120-day return | > 0 | not a one-week bounce |
| Close vs the prior 20-session high | Close > R20, positive penetration | it is at its structural high right now |
| Risk to reference | ≤ 8% | a normal stop, not an absurdly wide one |
| History available | ≥ 252 sessions | enough data to compute the features |

**Blended score** — the six components, their weights and what each measures:

| Component | Weight | Measures |
|---|---|---|
| Price acceptance | 0.30 | retention into the close and closing range vs the prior 20-day high |
| Trend | 0.20 | 60-day and 120-day return |
| Liquidity | 0.15 | 20-day average rupee turnover (log scale) |
| Volume sanity | 0.15 | relative volume vs its 20-session mean — a tent: fades when too quiet or too frantic |
| Risk to reference | 0.10 | distance from the close back to the structural reference |
| Evidence edge | 0.10 | the reclaimed-reference pattern fired within the last 20 sessions |

The weights are a **frozen judgement, not a fit** — they were not tuned
against outcomes, and nothing here is fitted at all. Change them only as a
deliberate new experiment.

`decisions.py` also prints the evidence table underneath the shortlist: every
strategy's trade count, expectancy, bootstrap 95% CI, and whether it beats a
seeded **random null**. On the current data exactly one rule clears the null —
`recovered_after_rej` (+0.0125 net/trade vs −0.0177 for the null) — which is
why it carries the `evidence edge` component.

> Every name in this list is labelled a **HISTORICAL_CANDIDATE**. This is a
> research screen, not investment advice, and no participant identity is
> inferred anywhere in the output.

### The raw session board

```bash
python scripts/screen_candidates.py            # latest session
python scripts/screen_candidates.py --asof 2026-09-25 --top 5
```

Tags every symbol `ORGANIC` / `PENDING` / `TRAP_RISK` / `REJECTED` /
`NO_SETUP` / `ILLIQUID` on the latest session only, and writes
`reports/CANDIDATES.md`, `reports/candidates.csv` and a self-contained,
filterable **`reports/dashboard.html`** (open it in any browser — no server).
This is the unranked tag board; `decisions.py` is the ranked shortlist.

## Delivery data (activates filter F4)

```bash
python scripts/fetch_delivery.py --days 40     # one NSE request per session
```

Writes `data/delivery_history.parquet`. `load_history` merges it automatically
when it sits next to the price file, and `features.py` then computes
`deliv_pct`, `deliv_pct_rel`, `deliv_rvol20`, `avg_trade_size`, `ats_rel` —
which is what trap filter **F4** needs. Without it these stay `NA` and F4 is
reported as *unavailable*, never zero-filled. NSE exposes no bulk delivery
endpoint, so this is a bounded recent window, not 2018-2026.

## Run it daily, automatically

```bat
REM double-click, or:
schedule_daily.bat install 19:00     :: create a daily Windows task
schedule_daily.bat run               :: run the job now
schedule_daily.bat remove            :: delete the task
```

The task calls `RUN_BACKTEST.bat auto`, which refreshes data, rebuilds the
stock-pick shortlist and the dashboard, and logs to `reports\scheduled_run.log`.
It runs only while the PC is on and you are logged in.

## Run it online (no PC needed)

Pick whichever fits:

| Option | What happens | How to use |
|---|---|---|
| **GitHub Actions (recommended)** | Runs every day at 19:00 IST on GitHub's servers, publishes reports to the `live` branch and as an artifact | Nothing to install. Watch it in the repo's **Actions** tab, or press **Run workflow**. Config: `.github/workflows/update-reports.yml` |
| **GitHub Pages** | Same, plus a live dashboard URL you can open on a phone | Repo → **Settings → Pages → Source: GitHub Actions** (one-time). Config: `.github/workflows/pages.yml` |
| **Google Colab** | Whole engine in a browser tab, nothing installed | Open `Colab_Backtest.ipynb` in Colab → **Runtime > Run all** |

`Colab_Backtest.ipynb` is a convenience only; GitHub Actions is the route to
use, because it also publishes `reports/` to the `live` branch and (with
Pages enabled) gives you a URL you can open on a phone.

Browse the results the workflow produced at
`https://github.com/Adiversion/screener-backtest/tree/live`.

> GitHub pauses scheduled workflows on repos with no activity for 60+ days, and
> schedules can start up to ~15 minutes late. If that happens, use
> **Actions → Update live reports → Run workflow**.

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

The bundled dataset is **adjusted OHLCV for 499 Nifty-500 symbols,
2018-01 → 2026-10** (built with `scripts/fetch_data.py --source nifty500`;
`data/small_universe_history.parquet` is a 51-symbol smoke-test set), plus a
**delivery window** from `scripts/fetch_delivery.py` (~84k rows, 29 sessions —
NSE has no bulk delivery endpoint, so it cannot reach back to 2018).

There is **no price-band/ASM/GSM, circuit-lock or results-calendar** data, so
filters F6/F9/F10 are reported as `NA` and flagged `filter_incomplete` — never
zero-filled. F4 (delivery) is active whenever the delivery file is present.
Reports carry a `DEGRADED-DATA` banner while any filter is incomplete.
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
            report, ingest, screen, quality, evidence
scripts/    run_backtest.py, decisions.py, screen_candidates.py,
            pra_study.py, pa_study.py, fetch_data.py, fetch_delivery.py,
            build_report.py, strategy_index.py
config/     protocol_v2.yaml
tests/      features/states, simulator/costs/metrics/audit, pra, pa,
            screen, delivery
```

Every source file stays under 300 lines; a single no-lookahead audit
(truncation, shuffle-future, static scan, ordering, cutoff) must pass before a
report is produced.
