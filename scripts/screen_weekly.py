#!/usr/bin/env python3
"""Daily-strong vs weekly-strong confluence, as of a date.

  python scripts/screen_weekly.py
  python scripts/screen_weekly.py --asof 2026-09-25 --top 20
  python scripts/screen_weekly.py --include-partial-week

Runs the 13 daily frameworks and the 12 weekly confluence gates over the same
universe and the same as-of date, then buckets every symbol:

  BOTH         daily pivot AND weekly structure   -> highest conviction
  DAILY_ONLY   daily pivot, no weekly structure   -> late or structurally weak
  WEEKLY_ONLY  weekly structure, no daily pivot   -> the swing watchlist
  NEITHER      not a candidate on either timeframe

WEEKLY_ONLY is the set the daily scan structurally cannot produce: names whose
weekly structure is intact but which have not yet printed a daily pivot. That
is a watchlist, not an entry signal -- the daily engine still has to fire.

Writes reports/WEEKLY_CONFLUENCE.md and reports/weekly_confluence.csv.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from protocol.config import get, load_config  # noqa: E402
from protocol.data import load_history  # noqa: E402
from protocol.github_screeners import compute_screener_features  # noqa: E402
from protocol.timeframe import (  # noqa: E402
    BOTH,
    DAILY_ONLY,
    NEITHER,
    WEEKLY_ONLY,
    bucket_counts,
    confluence,
    daily_strength,
    gate_diagnostics,
    weekly_strength,
)
from protocol.weekly import (  # noqa: E402
    MIN_WEEKLY_BARS,
    WEEKLY_GATE_COUNT,
    WEEKLY_PARAMS,
    weekly_frame,
    weekly_panel,
)


def _fmt_money(v: float) -> str:
    return "-" if pd.isna(v) else f"Rs {float(v):,.0f}"


def _markdown(asof: pd.Timestamp, counts: dict[str, int], conf: pd.DataFrame,
              diag: pd.DataFrame, top: int, partial: bool,
              min_weekly: int) -> str:
    n_all = len(conf)
    lines = [
        f"# Daily vs Weekly Confluence -- {asof.date()}",
        "",
        f"Weekly bar count in this run: {'incomplete trailing week INCLUDED' if partial else 'completed weeks only'}.",
        "",
        "## Headline",
        "",
        "| Bucket | Meaning | Symbols |",
        "| --- | --- | ---: |",
        f"| BOTH | daily pivot + weekly structure | {counts.get(BOTH, 0)} |",
        f"| DAILY_ONLY | daily pivot, no weekly structure | {counts.get(DAILY_ONLY, 0)} |",
        f"| WEEKLY_ONLY | weekly structure, no daily pivot (swing watchlist) | {counts.get(WEEKLY_ONLY, 0)} |",
        f"| NEITHER | not a candidate on either timeframe | {counts.get(NEITHER, 0)} |",
        "",
        f"Weekly strong = at least {min_weekly} of {WEEKLY_GATE_COUNT} weekly gates AND not more "
        f"than {WEEKLY_PARAMS['max_ext_ma30'] * 100:.0f}% above its 30-week MA (anti-climax cap, "
        "mirrors the daily engine's `max_ext_sma50`). "
        f"Daily strong = at least 1 of the 13 daily frameworks. Universe scored: {n_all} symbols.",
        "",
        "## Swing candidates (weekly strong, daily NOT yet strong)",
        "",
    ]

    swing = conf[conf["bucket"] == WEEKLY_ONLY].head(top)
    if swing.empty:
        lines.append("None as of this date: every weekly-strong name has already printed a daily pivot.")
    else:
        lines += [
            "| Symbol | Gates | Grade | Close | 13w ret | 52w ret | RVOL13 | Prox52 | Ext/30w | RSI14 | Why weekly-strong |",
            "| --- | ---: | :-: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
        for _, r in swing.iterrows():
            lines.append(
                f"| **{r['Symbol']}** | {r['n_gates']}/{WEEKLY_GATE_COUNT} | {r['w_grade']} | "
                f"{_fmt_money(r.get('weekly_close'))} | {r.get('wret13', float('nan')) * 100:+.1f}% | "
                f"{r.get('wret52', float('nan')) * 100:+.1f}% | {r.get('w_rvol13', float('nan')):.2f}x | "
                f"{r.get('w_prox52', float('nan')):.2f} | {r.get('w_ext_ma30', float('nan')) * 100:+.1f}% | "
                f"{r.get('w_rsi14', float('nan')):.0f} | {r.get('gates', '')} |"
            )
    lines += ["", "## Highest conviction (BOTH)", ""]
    # Ranked by daily confluence first: a name clearing several daily
    # frameworks is stronger evidence than one clearing more weekly gates.
    both = conf[conf["bucket"] == BOTH].sort_values(
        ["n_frameworks", "n_gates"], ascending=False).head(top)
    if both.empty:
        lines.append("None as of this date.")
    else:
        lines += [
            "| Symbol | Daily frameworks | Weekly gates | Grade | Close |",
            "| --- | ---: | ---: | :-: | ---: |",
        ]
        for _, r in both.iterrows():
            lines.append(
                f"| **{r['Symbol']}** | {r['n_frameworks']} | {r['n_gates']}/{WEEKLY_GATE_COUNT} | "
                f"{r['w_grade']} | {_fmt_money(r.get('weekly_close'))} |"
            )
        lines += ["", "Daily framework detail:",
                  *[f"- **{r['Symbol']}** -- {r['frameworks']}"
                    for _, r in both.head(15).iterrows()]]

    lines += ["", "## Weekly gate selectivity", "",
              "A gate that fires on nearly every symbol is not filtering anything.",
              "",
              "| Gate | Passes | Pass rate |", "| --- | ---: | ---: |"]
    for _, r in diag.iterrows():
        lines.append(f"| {r['label']} | {r['passes']} | {r['pass_rate'] * 100:.1f}% |")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="Daily-strong vs weekly-strong confluence")
    ap.add_argument("--config", default=None)
    wide = ROOT / "data" / "nse_all_history.parquet"
    core = ROOT / "data" / "universe_history.parquet"
    ap.add_argument("--data", default=str(wide if wide.exists() else core))
    ap.add_argument("--asof", default=None)
    ap.add_argument("--symbols", default="all")
    ap.add_argument("--top", type=int, default=25)
    ap.add_argument("--outdir", default=str(ROOT / "reports"))
    ap.add_argument("--min-weekly-gates", type=int, default=int(WEEKLY_PARAMS["min_gates"]))
    ap.add_argument("--min-daily-frameworks", type=int, default=1)
    ap.add_argument("--top-n-per-framework", type=int, default=80)
    ap.add_argument("--min-turnover-cr", type=float, default=0.5)
    ap.add_argument("--include-partial-week", action="store_true",
                    help="Also score the in-progress week. Off by default: an "
                         "unfinished weekly bar is not a weekly close.")
    ap.add_argument("--no-write", action="store_true")
    args = ap.parse_args()

    cfg = load_config(args.config)
    history = load_history(args.data)
    if args.symbols != "all":
        keep = [s.strip().upper() for s in args.symbols.split(",")]
        history = history[history["Symbol"].isin(keep)]
    if history.empty:
        print("no data")
        return 1

    asof = (pd.Timestamp(args.asof) if args.asof
            else max(pd.Timestamp(history["Date"].max()),
                     pd.Timestamp(get(cfg, "validation.validation_end"))))
    history = history[history["Date"] <= asof]
    if history.empty:
        print("no data on/before", asof.date())
        return 1

    # ---- weekly side -----------------------------------------------------
    panel = weekly_panel(history, asof=asof, include_partial=args.include_partial_week)
    wfeat = weekly_frame(panel, asof, include_partial=args.include_partial_week)
    dropped = int(history["Symbol"].nunique() - len(panel))
    weekly = weekly_strength(wfeat)

    # ---- daily side ------------------------------------------------------
    dfeat = compute_screener_features(history, asof)
    daily = daily_strength(dfeat, top_n=args.top_n_per_framework,
                           min_turnover_cr=args.min_turnover_cr,
                           include_delivery="DelivPct" in history.columns)

    conf = confluence(daily, weekly, min_daily=args.min_daily_frameworks,
                      min_weekly=args.min_weekly_gates)
    counts = bucket_counts(conf)
    diag = gate_diagnostics(weekly)

    # ---- console report --------------------------------------------------
    print(f"\nDaily vs Weekly Confluence -- {asof.date()}")
    print(f"universe: {history['Symbol'].nunique()} symbols, "
          f"{len(panel)} with >={MIN_WEEKLY_BARS} weekly bars ({dropped} too short)")
    print(f"as-of session: {history['Date'].max().date()} | "
          f"weekly bar: {'partial week included' if args.include_partial_week else 'completed week only'}")
    print(f"\n  BOTH         {counts[BOTH]:>4}   daily pivot + weekly structure")
    print(f"  DAILY_ONLY   {counts[DAILY_ONLY]:>4}   daily pivot, no weekly structure")
    print(f"  WEEKLY_ONLY  {counts[WEEKLY_ONLY]:>4}   weekly strong, no daily pivot  <- swing watchlist")
    print(f"  NEITHER      {counts[NEITHER]:>4}")
    dropped_ext = int(conf["w_extended"].fillna(False).astype(bool).sum()) \
        if "w_extended" in conf.columns else 0
    if dropped_ext:
        print(f"\n  anti-climax cap: {dropped_ext} name(s) cleared the gate count but sat more "
              f"than {WEEKLY_PARAMS['max_ext_ma30'] * 100:.0f}% above the 30w MA and were "
              "excluded from weekly-strong.")

    swing = conf[conf["bucket"] == WEEKLY_ONLY]
    if not swing.empty:
        print(f"\nSwing candidates (weekly strong, daily not yet strong), "
              f"{args.min_weekly_gates}+/{WEEKLY_GATE_COUNT} gates:")
        print(f"  {'Symbol':<12} {'G':>3} {'Gr':<3} {'Close':>10} {'13w':>8} "
              f"{'52w':>9} {'RV13':>5} {'Prox':>5} {'Ext':>7}  Gates")
        for _, r in swing.head(args.top).iterrows():
            print(f"  {r['Symbol']:<12} {r['n_gates']:>3} {r['w_grade']:<3} "
                  f"{float(r['weekly_close']):>10,.0f} {r['wret13'] * 100:>7.1f}% "
                  f"{r['wret52'] * 100:>8.1f}% {r['w_rvol13']:>5.2f} "
                  f"{r['w_prox52']:>5.2f} {r['w_ext_ma30'] * 100:>6.1f}%  {r['gates']}")
    else:
        print("\nNo weekly-strong names are missing from the daily scan at this date.")

    if not args.no_write:
        outdir = Path(args.outdir)
        outdir.mkdir(parents=True, exist_ok=True)
        (outdir / "WEEKLY_CONFLUENCE.md").write_text(
            _markdown(asof, counts, conf, diag, args.top, args.include_partial_week,
                      args.min_weekly_gates), encoding="utf-8")
        conf.to_csv(outdir / "weekly_confluence.csv", index=False)
        print(f"\nwrote {outdir / 'WEEKLY_CONFLUENCE.md'}")
        print(f"wrote {outdir / 'weekly_confluence.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
