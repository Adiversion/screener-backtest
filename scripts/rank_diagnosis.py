#!/usr/bin/env python3
"""Why does the score order outcomes poorly among the names that pass?

    python scripts/rank_diagnosis.py

The gates and the score are two different claims. The gates say "this name is
tradeable at all". The score says "of the tradeable ones, this one is best".
Testing only the gates hides the second failure: on 1 Sep 2026 the top half of
the gate-clearers returned LESS than the bottom half.

A gate that requires a rising 120-day trend has already fixed most of the trend
component for everyone who passes it. If the score still spends a fifth of its
weight on that component, it is adding noise, not information -- the dispersion
it is trying to rank on no longer exists inside the surviving group. This
measures each component's information content separately, inside and outside
the gates, so the difference is visible.

Reported per component: Spearman rank correlation with the forward return, and
the t-stat of that correlation. A t below 2 is not evidence of anything.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from protocol import quality  # noqa: E402
from protocol.config import load_config  # noqa: E402
from protocol.data import load_history  # noqa: E402

CACHE = ROOT / "reports" / "scored_panel.parquet"
HORIZON = 20


def with_forward(df: pd.DataFrame, horizon: int = HORIZON) -> pd.DataFrame:
    """Attach the forward return the ranking is supposed to predict."""
    h = load_history(str(ROOT / "data" / "nse_all_history.parquet"))
    h = h[["Date", "Symbol", "Close"]].copy()
    h["Date"] = pd.to_datetime(h["Date"])
    h = h.sort_values(["Symbol", "Date"])
    h["fwd"] = h.groupby("Symbol", sort=False)["Close"].shift(-horizon) / h["Close"] - 1.0
    out = df.merge(h.rename(columns={"Symbol": "symbol", "Date": "date"})[["date", "symbol", "fwd"]],
                   on=["date", "symbol"], how="left")
    return out.dropna(subset=["fwd", "score"])


def ic_table(df: pd.DataFrame, cols: list[str], label: str) -> pd.DataFrame:
    """Spearman IC and its t-stat for each column, per-session then averaged.

    Per-session first, because pooling rows across dates mixes a stock's level
    with its date's regime and inflates the correlation.
    """
    rows = []
    for c in cols:
        per = []
        for _, g in df.groupby("date"):
            if len(g) < 20 or g[c].nunique() < 3:
                continue
            r = g[c].rank().corr(g["fwd"].rank())
            if not np.isnan(r):
                per.append(r)
        s = pd.Series(per)
        t = s.mean() / (s.std() / np.sqrt(len(s))) if len(s) > 2 and s.std() else np.nan
        rows.append({"group": label, "component": c, "sessions": len(s),
                     "ic": round(float(s.mean()), 4) if len(s) else np.nan,
                     "t": round(float(t), 2) if not np.isnan(t) else np.nan})
    return pd.DataFrame(rows)


def main() -> int:
    cfg = load_config()
    df = pd.read_parquet(CACHE)
    df["date"] = pd.to_datetime(df["date"])
    df = with_forward(df)

    # The raw columns are not comparable across components -- turnover20 is
    # rupees of volume, atrpct is a fraction. Only the cross-sectional
    # percentile columns carry a common scale, so only those are used.
    feat_cols = [f"{c}_pct" for c in quality.COMPONENTS
                 if f"{c}_pct" in df.columns and c != "edge"]
    print(f"forward horizon {HORIZON} sessions | sessions {df['date'].min().date()}"
          f" to {df['date'].max().date()}\n")

    cleared = df[df["clears"]]
    inside = ic_table(cleared, feat_cols + ["score"], "INSIDE the gates")
    outside = ic_table(df[~df["clears"] & df["score"].notna()],
                       feat_cols + ["score"], "OUTSIDE the gates")
    tab = pd.concat([inside, outside])
    print("information coefficient (Spearman vs 20-session forward return)")
    print(tab.pivot(index="component", columns="group",
                    values=["ic", "t"]).to_string())

    print("\nwhat the gates themselves do to the trend components:")
    for c in feat_cols:
        a, b = df.loc[df["clears"], c], df.loc[~df["clears"] & df["score"].notna(), c]
        print(f"  {c:<14} percentile inside gates {a.mean():5.1f}   "
              f"outside {b.mean():5.1f}   -> the gate has already fixed "
              f"{a.mean() - b.mean():+.1f} of this component")

    print("\ndeciles of the score, computed ONLY among gate-clearers:")
    c = cleared.copy()
    c["bucket"] = pd.qcut(c["score"].rank(method="first", ascending=True), 5,
                          labels=[f"D{i + 1}" for i in range(5)])
    g = c.groupby("bucket", observed=True).agg(
        events=("fwd", "size"), mean_fwd=("fwd", "mean")).reset_index()
    g["mean_fwd"] = (g["mean_fwd"] * 100).round(3)
    print(g.to_string(index=False))
    spread = g["mean_fwd"].iloc[-1] - g["mean_fwd"].iloc[0]
    print(f"\n  D5 - D1 = {spread:+.3f} pp over {HORIZON} sessions")
    print("  D1 is the LOWEST score, D5 the highest. A working ranking would "
          "put the sign on D5.")

    out = ROOT / "reports" / "rank_diagnosis.csv"
    tab.to_csv(out, index=False)
    print(f"\nwrote {out.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
