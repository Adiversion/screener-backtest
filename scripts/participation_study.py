#!/usr/bin/env python3
"""Does falling participation after a big advance mean accumulation or distribution?

    python scripts/participation_study.py
    python scripts/participation_study.py --data data/universe_history.parquet

Neither word is knowable from OHLCV: both look identical on a volume chart.
The testable question underneath is what PRICE did while participation decayed,
and this measures it -- the same low-volume state split by whether the
structural reference held or was lost, plus the control of high participation
while price is already below the level.

Writes reports/PARTICIPATION.md and reports/participation.json.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from protocol import participation  # noqa: E402
from protocol.config import load_config  # noqa: E402
from protocol.data import load_history  # noqa: E402
from protocol.features import build_panel  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Participation-decay cohort study")
    ap.add_argument("--config", default=None)
    ap.add_argument("--data", default=str(ROOT / "data" / "universe_history.parquet"))
    ap.add_argument("--outdir", default=str(ROOT / "reports"))
    args = ap.parse_args()

    cfg = load_config(args.config)
    history = load_history(args.data)
    if history.empty:
        print("no data")
        return 1
    panel = build_panel(history)
    horizons = tuple(cfg["participation"]["horizons"])
    print(f"labelling cohorts over {len(panel)} symbols, "
          f"{history['Date'].nunique()} sessions …", flush=True)
    result = participation.study(panel, cfg, horizons)

    table = result["table"]
    print(f"\n{'cohort':<30}{'events':>9}{'fwd20':>10}{'vs univ':>10}")
    for _, r in table.iterrows():
        print(f"{r['cohort']:<30}{r['events']:>9,}{str(r.get('fwd20')):>10}"
              f"{str(r.get('excess_vs_universe_fwd20')):>10}")
    print(f"\nuniverse baseline fwd20: {result['baseline'][20]['mean']}")
    print("\n" + result["verdict"])

    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "PARTICIPATION.md").write_text(participation.to_markdown(result),
                                          encoding="utf-8")
    payload = {k: v for k, v in result.items() if k != "long"}
    payload["long"] = result["long"].groupby("cohort", dropna=True).size().to_dict()
    (out / "participation.json").write_text(
        json.dumps(payload, indent=2, default=str), encoding="utf-8")
    table.to_csv(out / "participation_cohorts.csv", index=False)
    print(f"\nwrote {out / 'PARTICIPATION.md'}, {out / 'participation.json'}, "
          f"{out / 'participation_cohorts.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())