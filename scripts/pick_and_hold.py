#!/usr/bin/env python3
"""Pick on a verdict date, then hold and measure. Pooled over many dates.

    python scripts/pick_and_hold.py --from 2026-05-01 --to 2026-09-01 --top 1
    python scripts/pick_and_hold.py --from 2026-05-01 --top 5 --horizons 5,10,15,20

A single verdict date is one draw, and one draw proves nothing in either
direction. This repeats the whole exercise at many evenly spaced decision bars
and pools the results, which is the only way to tell a working rule from a
lucky session.

What it measures, per verdict date:

    1. rank the universe cross-sectionally using ONLY data through that date
    2. take the top N names that clear every hard gate
    3. hold them, unweighted and untouched, for 5/10/15/20 sessions
    4. compare against the benchmark they were picked FROM

The benchmark matters as much as the picks: an equal-weight basket of the whole
universe, held over the same sessions. "Up 3%" means nothing unless the market
also went up 3% that week.

There is no exit here on purpose. This is a buy-AND-HOLD test of the RANKING.
The rotation mode in `protocol/rotation.py` is a separate question with a
separate exit rule, and its result is allowed to disagree with this one.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from protocol import verdict  # noqa: E402
from protocol.config import load_config  # noqa: E402
from protocol.data import load_history  # noqa: E402
from protocol.features import build_panel  # noqa: E402


def _newey_west_t(x: np.ndarray, lags: int) -> float:
    """t-stat of the mean with a Newey-West (Bartlett) HAC variance.

    The decision bars overlap: a 20-session hold sampled on consecutive sessions
    shares 19 of its 20 days with its neighbour, so the series is autocorrelated
    and an ordinary t-stat would claim far more confidence than the sample earns.
    """
    n = len(x)
    if n < 3:
        return float("nan")
    e = x - x.mean()
    gamma0 = float(e @ e) / n
    var = gamma0
    for lag in range(1, min(lags, n - 1) + 1):
        w = 1.0 - lag / (lags + 1.0)
        var += 2.0 * w * float(e[lag:] @ e[:-lag]) / n
    if var <= 0:
        return float("nan")
    return float(x.mean() / np.sqrt(var / n))


def verdict_dates(dates: pd.DatetimeIndex, every: int, first: pd.Timestamp,
                  last: pd.Timestamp) -> list[pd.Timestamp]:
    """Every `every`-th session inside [first, last], anchored on the window.

    Anchoring on the window (not the whole series) is what makes a single-date
    run work: asking for exactly one date must return that date, not an empty
    list because the date fell between two global anchors.
    """
    inside = [pd.Timestamp(d) for d in dates if first <= pd.Timestamp(d) <= last]
    return inside[::every]


def main() -> int:
    ap = argparse.ArgumentParser(description="Pick, then hold, pooled over dates")
    ap.add_argument("--config", default=None)
    ap.add_argument("--data", default=str(ROOT / "data" / "nse_all_history.parquet"))
    ap.add_argument("--from", dest="start", default="2026-05-01")
    ap.add_argument("--to", dest="end", default="2026-09-01")
    ap.add_argument("--top", type=int, default=1,
                    help="how many top-ranked gate-clearing names to hold")
    ap.add_argument("--every", type=int, default=5, help="sessions between decisions")
    ap.add_argument("--horizons", default="5,10,15,20")
    ap.add_argument("--outdir", default=str(ROOT / "reports"))
    args = ap.parse_args()

    horizons = tuple(int(h) for h in args.horizons.split(","))
    cfg = load_config(args.config)
    history = load_history(args.data)
    panel = build_panel(history)
    print(f"scoring {len(panel)} symbols over {history['Date'].nunique()} sessions …",
          flush=True)
    df = verdict.build(panel, cfg, horizons=tuple(sorted(set(horizons + (1,)))))

    # The 52-week component needs a full year of history before ANY name can
    # clear a gate. Before that point "no pick" is a warm-up artefact, not the
    # screen saying wait, and pooling those bars in would flatter or wreck the
    # result for reasons that have nothing to do with the ranking.
    warm = pd.Timestamp(df[df["prox52"].notna()]["date"].min())
    first = max(pd.Timestamp(args.start), warm)
    if pd.Timestamp(args.start) < warm:
        print(f"note: {warm.date()} is the first session a 52-week high/low can "
              f"be computed, so nothing before it can clear a gate. "
              f"ignoring {args.start} -> {first.date()}")
    last = min(pd.Timestamp(args.end),
               pd.Timestamp(history["Date"].max()) - pd.offsets.BDay(max(horizons)))
    dates = verdict_dates(pd.DatetimeIndex(sorted(df["date"].unique())),
                          args.every, first, last)
    if not dates:
        print(f"no sessions between {args.start} and {args.end} with room for a "
              f"{max(horizons)}-session forward window (data ends "
              f"{pd.Timestamp(history['Date'].max()).date()})")
        return 1
    print(f"{len(dates)} decision bars from {dates[0].date()} to {dates[-1].date()}, "
          f"holding the top {args.top}\n")

    rows = []
    for d in dates:
        day = df[df["date"] == np.datetime64(d)]
        if day.empty:
            continue
        cleared = day[day["clears"]].sort_values("score", ascending=False)
        picks = cleared.head(args.top)
        market = {h: float(day[f"fwd{h}"].mean()) for h in horizons
                  if day[f"fwd{h}"].notna().any()}
        for rank, (_, p) in enumerate(picks.iterrows(), 1):
            row = {"date": str(pd.Timestamp(d).date()), "rank": rank,
                   "symbol": p["symbol"], "score": float(p["score"]),
                   "close": float(p["close"])}
            for h in horizons:
                row[f"fwd{h}"] = float(p[f"fwd{h}"]) if pd.notna(p[f"fwd{h}"]) else None
                row[f"bench{h}"] = market.get(h)
            rows.append(row)
        if picks.empty:
            rows.append({"date": str(pd.Timestamp(d).date()), "rank": 0,
                         "symbol": None, "score": None, "close": None})

    picks_df = pd.DataFrame(rows)
    if picks_df.empty:
        print("no verdict dates in range")
        return 1

    print(f"{'horizon':<10}{'picks':>7}{'mean pick':>12}{'benchmark':>12}"
          f"{'excess':>10}{'beat rate':>11}{'win rate':>10}{'t':>9}")
    print("-" * 81)
    summary = []
    for h in horizons:
        col, bcol = f"fwd{h}", f"bench{h}"
        sub = picks_df[picks_df[col].notna() & picks_df["rank"] > 0]
        if sub.empty:
            continue
        excess = (sub[col] - sub[bcol]).dropna()
        # Overlapping windows: a 20-session hold sampled every session is not 20
        # independent observations, so the naive t-stat understates the standard
        # error. Newey-West with a lag of the horizon is the honest minimum.
        t = _newey_west_t(excess.to_numpy(), lags=max(1, h // 2))
        line = (f"{h}d{' ':<7}{len(sub):>7}{sub[col].mean():>12.4f}"
                f"{sub[bcol].mean():>12.4f}{excess.mean():>10.4f}"
                f"{(excess > 0).mean():>11.3f}{(sub[col] > 0).mean():>10.3f}"
                f"{t:>9.2f}")
        print(line)
        summary.append({"horizon": h, "picks": int(len(sub)),
                        "mean_pick": round(float(sub[col].mean()), 4),
                        "mean_benchmark": round(float(sub[bcol].mean()), 4),
                        "mean_excess": round(float(excess.mean()), 4),
                        "beat_rate": round(float((excess > 0).mean()), 4),
                        "win_rate": round(float((sub[col] > 0).mean()), 4),
                        "t_stat": round(float(t), 2),
                        "worst": round(float(sub[col].min()), 4),
                        "best": round(float(sub[col].max()), 4)})

    empty_days = int((picks_df["rank"] == 0).sum())
    print(f"\n{len(picks_df[picks_df['rank'] > 0])} picks over {len(dates)} bars"
          f" | {empty_days} bars had NO name clearing every gate (stayed in cash)")
    if empty_days:
        print("  those bars are counted, not skipped: a screen that says 'wait' is "
              "a position.")

    print("\nthe picks themselves:")
    show = picks_df[picks_df["rank"] > 0][
        ["date", "rank", "symbol", "score", "close"] + [f"fwd{h}" for h in horizons]]
    print(show.to_string(index=False))

    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)
    summary_df = pd.DataFrame(summary)
    summary_df.to_csv(out / "pick_and_hold.csv", index=False)
    picks_df.to_csv(out / "pick_and_hold_picks.csv", index=False)
    (out / "pick_and_hold.json").write_text(json.dumps(
        {"start": str(dates[0].date()), "end": str(dates[-1].date()),
         "bars": len(dates), "top": args.top, "summary": summary},
        indent=2), encoding="utf-8")
    print(f"\nwrote {out / 'pick_and_hold.csv'}, {out / 'pick_and_hold_picks.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())