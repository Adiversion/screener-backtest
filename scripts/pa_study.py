#!/usr/bin/env python3
"""Price-Acceptance State A/B/C/D event study.

  python scripts/pa_study.py
  python scripts/pa_study.py --start 2026-09-21 --end 2026-09-25   # strict week
  python scripts/pa_study.py --symbols CUPID,MARINE,WELSPUNLIV --outdir reports/pa
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from protocol import audit  # noqa: E402
from protocol.config import get, load_config  # noqa: E402
from protocol.data import data_quality_report, load_history  # noqa: E402
from protocol.features import build_panel  # noqa: E402
from protocol.pa import run_state_study  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Price-Acceptance state study")
    ap.add_argument("--config", default=None)
    ap.add_argument("--data", default=str(ROOT / "data" / "universe_history.parquet"))
    ap.add_argument("--symbols", default="all")
    ap.add_argument("--start", default=None)
    ap.add_argument("--end", default=None)
    ap.add_argument("--outdir", default=str(ROOT / "reports" / "pa"))
    args = ap.parse_args()

    cfg = load_config(args.config)
    cutoff = args.end or get(cfg, "validation.validation_end")
    history = load_history(args.data)
    if cutoff:
        history = history[history["Date"] <= pd.Timestamp(cutoff)]
    if args.start:
        history = history[history["Date"] >= pd.Timestamp(args.start)]
    if args.symbols != "all":
        syms = [s.strip().upper() for s in args.symbols.split(",")]
        history = history[history["Symbol"].isin(syms)]
    if history.empty:
        print("no data in window")
        return 1

    study = run_state_study(build_panel(history), cfg)
    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)
    events, outcomes = study["events"], study["outcomes"]
    if not events.empty:
        events.to_csv(out / "pa_events.csv", index=False)
    outcomes.to_csv(out / "pa_outcomes.csv", index=False)

    report = [
        "# Price-Acceptance — State A/B/C/D Event Study", "",
        f"- config hash: `{cfg['_hash']}`",
        f"- data: {data_quality_report(history)}", "",
        "## Outcome table (state -> forward T+n)", "",
        outcomes.to_markdown(index=False) if not outcomes.empty else "_(no events)_",
        "", "## No-lookahead audit", "",
        f"- static scan passed: {audit.static_scan()['pass']}",
    ]
    (out / "PA_REPORT.md").write_text("\n".join(report), encoding="utf-8")
    print(f"events: {len(events)}  -> {out / 'PA_REPORT.md'}")
    if not outcomes.empty:
        print(outcomes.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
