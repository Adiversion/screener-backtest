#!/usr/bin/env python3
"""How many names clear the gates on each session, and where the panel is thin.

`pick_and_hold.py` reported 54 of 96 decision bars with no pick at all. A screen
that says "wait" is a legitimate position, but a screen that says "wait" because
the features are not warmed up yet is a DATA ARTEFACT, and those two must not be
reported as the same thing. This separates them.

    python scripts/bar_coverage.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from protocol import quality, ranking  # noqa: E402
from protocol.config import load_config  # noqa: E402
from protocol.data import load_history  # noqa: E402
from protocol.features import build_panel  # noqa: E402

CACHE = ROOT / "reports" / "scored_panel.parquet"


def scored(cfg=None) -> pd.DataFrame:
    if CACHE.exists():
        return pd.read_parquet(CACHE)
    history = load_history(str(ROOT / "data" / "nse_all_history.parquet"))
    panel = build_panel(history)
    df = ranking.rank_all(ranking.build_long(panel, cfg or load_config()),
                          cfg or load_config(), quality.COMPONENTS)
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(CACHE, index=False)
    return df


def main() -> int:
    cfg = load_config()
    df = scored(cfg)
    per = df.groupby("date").agg(
        n=("symbol", "size"),
        scored=("score", lambda s: int(s.notna().sum())),
        cleared=("clears", "sum"),
    ).reset_index()
    per["date"] = pd.to_datetime(per["date"])
    per["gate_rate"] = per["cleared"] / per["scored"].replace(0, pd.NA)

    print(f"{'period':<20}{'bars':>6}{'median scored':>16}{'median clearing':>18}")
    for label, sub in per.groupby(per["date"].dt.to_period("M")):
        print(f"{str(label):<20}{len(sub):>6}{sub['scored'].median():>16.0f}"
              f"{sub['cleared'].median():>18.0f}")

    zero = per[per["cleared"] == 0]
    print(f"\n{len(zero)} of {len(per)} sessions have ZERO gate-clearers.")
    if not zero.empty:
        print(f"  span: {zero['date'].min().date()} to {zero['date'].max().date()}")
        warm = zero[zero["scored"] < per["scored"].median()]
        print(f"  of those, {len(warm)} also have a below-median number of scored "
              f"names -> feature warm-up, not a market judgement")
        real = zero[zero["scored"] >= per["scored"].median()]
        print(f"  {len(real)} have a full cross-section and still clear nothing "
              f"-> the gates genuinely rejected the day")
    per.to_csv(ROOT / "reports" / "bar_coverage.csv", index=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
