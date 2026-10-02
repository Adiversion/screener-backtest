#!/usr/bin/env python3
"""Pressure -> Response -> Acceptance event study.

  python scripts/pra_study.py
  python scripts/pra_study.py --start 2026-09-21 --end 2026-09-25   # strict week
  python scripts/pra_study.py --symbols data/nifty500.txt --outdir reports/pra
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
from protocol.pra import run_event_study  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="PRA event study")
    ap.add_argument("--config", default=None)
    ap.add_argument("--data", default=str(ROOT / "data" / "universe_history.parquet"))
    ap.add_argument("--symbols", default="all")
    ap.add_argument("--start", default=None)
    ap.add_argument("--end", default=None)
    ap.add_argument("--outdir", default=str(ROOT / "reports" / "pra"))
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

    panel = build_panel(history)
    study = run_event_study(panel, cfg)
    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)
    events, outcomes, ablation = study["events"], study["outcomes"], study["ablation"]
    if not events.empty:
        events.to_csv(out / "pra_events.csv", index=False)
    outcomes.to_csv(out / "pra_outcomes.csv", index=False)
    ablation.to_csv(out / "pra_ablation.csv", index=False)

    report = [
        "# Pressure -> Response -> Acceptance — Event Study", "",
        f"- config hash: `{cfg['_hash']}`",
        f"- data: {data_quality_report(history)}", "",
        "## Outcome table (state -> forward T+n)", "",
        outcomes.to_markdown(index=False) if not outcomes.empty else "_(no events)_",
        "", "## Ablation ladder (Section 23)", "",
        ablation.to_markdown(index=False) if not ablation.empty else "_(no events)_",
        "", "## No-lookahead audit", "",
        f"- passed: {audit.static_scan()['pass']}",
    ]
    (out / "PRA_REPORT.md").write_text("\n".join(report), encoding="utf-8")
    print(f"events: {len(events)}  -> {out / 'PRA_REPORT.md'}")
    if not outcomes.empty:
        print(outcomes.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
