"""Cross-timeframe comparison: daily-strong vs weekly-strong, as of a date.

The daily engine answers "what has already printed a pivot?". It cannot answer
"what is structurally strong but still building?", which is the question that
produces early swing entries. This module runs both sides and buckets every
symbol, so the gap between them is explicit:

    BOTH         daily pivot AND weekly structure  -> the highest-conviction names
    DAILY_ONLY   pivot without weekly structure   -> late, or structurally weak
    WEEKLY_ONLY  weekly structure, no daily pivot -> the swing watchlist
    NEITHER      not a candidate on either timeframe

`WEEKLY_ONLY` is the set the daily scan structurally cannot produce. It is a
watchlist, not an entry signal: the daily engine still has to fire before a
position is taken. Nothing here changes the daily pipeline or the live site.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from protocol.frameworks import run_frameworks
from protocol.weekly import (
    GATE_KEYS,
    WEEKLY_GATES,
    WEEKLY_PARAMS,
    evaluate_weekly,
)

BOTH, DAILY_ONLY, WEEKLY_ONLY, NEITHER = "BOTH", "DAILY_ONLY", "WEEKLY_ONLY", "NEITHER"
BUCKETS = (BOTH, DAILY_ONLY, WEEKLY_ONLY, NEITHER)

DAILY_COLS = ("Symbol", "n_frameworks", "frameworks", "daily_close", "daily_best_score")
# The weekly metrics a reader needs to judge a name are carried through the
# join, not just the gate count -- a "6/12" with no return, volume or extension
# context is not actionable.
WEEKLY_COLS = ("Symbol", "n_gates", "gates", "w_grade", "w_strong", "w_extended",
               "weekly_close", "w_score", "wret13", "wret52", "w_rvol13",
               "w_prox52", "w_ext_ma30", "w_rsi14", "week_complete", "Date")


def daily_strength(feat: pd.DataFrame, *, top_n: int = 60,
                   min_turnover_cr: float = 0.5, ind_df: Any | None = None,
                   deliv_map: dict[str, float] | None = None,
                   include_delivery: bool = True) -> pd.DataFrame:
    """Which symbols the 13 daily frameworks picked, and how many picked each.

    `top_n` is per framework, matching `frameworks.run_frameworks`, so a name can
    clear several frameworks at once. Every symbol that clears at least one is
    reported -- nothing is truncated away, because the point of this module is
    coverage of the daily side, not a shortlist.
    """
    if feat is None or feat.empty:
        return pd.DataFrame(columns=list(DAILY_COLS))
    rows: dict[str, dict[str, Any]] = {}
    for label, picks in run_frameworks(feat, top_n=top_n, min_turnover_cr=min_turnover_cr,
                                       ind_df=ind_df, deliv_map=deliv_map,
                                       include_delivery=include_delivery):
        for pick in picks:
            entry = rows.setdefault(pick.symbol, {
                "Symbol": pick.symbol, "frameworks": [],
                "daily_close": float(pick.close), "daily_best_score": float(pick.score),
            })
            entry["frameworks"].append(label)
            entry["daily_best_score"] = max(entry["daily_best_score"], float(pick.score))

    if not rows:
        return pd.DataFrame(columns=list(DAILY_COLS))
    out = pd.DataFrame(rows.values())
    out["n_frameworks"] = out["frameworks"].str.len()
    out["frameworks"] = out["frameworks"].str.join(", ")
    return out[list(DAILY_COLS)].sort_values(
        ["n_frameworks", "daily_best_score"], ascending=False).reset_index(drop=True)


def weekly_strength(feat: pd.DataFrame, *,
                    p: dict[str, float] | None = None) -> pd.DataFrame:
    """Which symbols cleared the weekly confluence gates, and which gates."""
    p = {**WEEKLY_PARAMS, **(p or {})}
    scored = evaluate_weekly(feat, p=p)
    if scored.empty:
        return pd.DataFrame(columns=["Symbol", "n_gates", "gates", "w_grade",
                                     "w_strong", "weekly_close", "w_score"])
    # The gate labels must be read off `scored`, which still carries the `g_*`
    # columns. Selecting the display columns first would drop them and silently
    # report an empty gate list for every symbol.
    gates = [", ".join(label for key, label in WEEKLY_GATES
                       if bool(row.get(f"g_{key}", False)))
             for _, row in scored.iterrows()]
    cols = ["Symbol", "n_gates", "w_grade", "w_strong", "w_extended", "Close",
            "w_score", "wret13", "wret52", "w_rvol13", "w_prox52", "w_ext_ma30",
            "w_rsi14", "week_complete", "Date"]
    # The `g_*` flags are kept so `gate_diagnostics` and the CSV export can
    # still show per-gate selectivity after the display columns are projected.
    cols += [f"g_{k}" for k in GATE_KEYS if f"g_{k}" in scored.columns]
    keep = [c for c in cols if c in scored.columns]
    out = scored[keep].copy()
    out["gates"] = gates
    out["weekly_close"] = out["Close"]
    order = ["Symbol", "n_gates", "gates", "w_grade", "w_strong", "weekly_close", "w_score"]
    rest = [c for c in out.columns if c not in order]
    return out[order + rest].sort_values(
        ["n_gates", "w_score"], ascending=False).reset_index(drop=True)


def confluence(daily: pd.DataFrame, weekly: pd.DataFrame, *,
               min_daily: int = 1, min_weekly: int | None = None) -> pd.DataFrame:
    """Bucket every symbol into BOTH / DAILY_ONLY / WEEKLY_ONLY / NEITHER.

    The join is an outer one on purpose. A name the daily engine could not
    evaluate at all (too little daily history, or below the liquidity floor) is
    still a legitimate weekly candidate, and must appear as WEEKLY_ONLY rather
    than vanishing from the comparison.
    """
    min_weekly = int(WEEKLY_PARAMS["min_gates"]) if min_weekly is None else int(min_weekly)

    d = daily[[c for c in DAILY_COLS if c in daily.columns]].copy() if not daily.empty \
        else pd.DataFrame(columns=list(DAILY_COLS))
    w = weekly[[c for c in WEEKLY_COLS if c in weekly.columns]].copy() if not weekly.empty \
        else pd.DataFrame(columns=list(WEEKLY_COLS))

    merged = d.merge(w, on="Symbol", how="outer")
    for col, fill in (("n_frameworks", 0), ("n_gates", 0), ("w_score", np.nan),
                      ("daily_best_score", np.nan)):
        if col in merged.columns:
            merged[col] = merged[col].fillna(fill)
    for col in ("frameworks", "gates", "w_grade"):
        if col in merged.columns:
            merged[col] = merged[col].fillna("")

    merged["n_frameworks"] = merged.get("n_frameworks", pd.Series(0, index=merged.index)).fillna(0).astype(int)
    merged["n_gates"] = merged.get("n_gates", pd.Series(0, index=merged.index)).fillna(0).astype(int)
    merged["daily_strong"] = merged["n_frameworks"] >= min_daily
    # `w_strong` carries the hard anti-climax extension cap, which a bare
    # `n_gates` threshold cannot express. Both conditions must hold, so the
    # caller's `min_weekly` still tightens (or loosens) the gate requirement
    # instead of being silently ignored.
    if "w_strong" in merged.columns:
        merged["weekly_strong"] = merged["w_strong"].fillna(False).astype(bool)
    else:
        merged["weekly_strong"] = pd.Series(True, index=merged.index)
    merged["weekly_strong"] &= merged["n_gates"] >= min_weekly
    merged["bucket"] = _bucket(merged["daily_strong"], merged["weekly_strong"])
    # The gap the daily engine cannot see by construction.
    merged["swing_candidate"] = merged["bucket"] == WEEKLY_ONLY
    return merged.sort_values(
        ["swing_candidate", "n_gates", "n_frameworks"], ascending=[False, False, False]
    ).reset_index(drop=True)


def _bucket(daily_strong: pd.Series, weekly_strong: pd.Series) -> pd.Series:
    def pick(d: bool, w: bool) -> str:
        if d and w:
            return BOTH
        if d:
            return DAILY_ONLY
        if w:
            return WEEKLY_ONLY
        return NEITHER
    return pd.Series([pick(bool(d), bool(w)) for d, w in zip(daily_strong, weekly_strong)],
                     index=daily_strong.index, dtype=object)


def bucket_counts(conf: pd.DataFrame) -> dict[str, int]:
    """Headline counts per bucket, including the empty ones."""
    counts = {b: 0 for b in BUCKETS}
    if conf.empty:
        return counts
    for name, n in conf["bucket"].value_counts().items():
        counts[str(name)] = int(n)
    return counts


def gate_diagnostics(weekly: pd.DataFrame) -> pd.DataFrame:
    """How selective each weekly gate was, and how often it agrees with the rest.

    A gate that fires on nearly every symbol is not a gate; `pass_rate` above
    ~0.9 means the cut-off is doing no work and should be tightened.
    """
    if weekly.empty:
        return pd.DataFrame(columns=["gate", "label", "passes", "pass_rate"])
    rows = []
    for key, label in WEEKLY_GATES:
        col = f"g_{key}"
        if col not in weekly.columns:
            continue
        n = int(weekly[col].sum())
        rows.append({"gate": key, "label": label, "passes": n,
                     "pass_rate": round(n / len(weekly), 4)})
    if not rows:
        return pd.DataFrame(columns=["gate", "label", "passes", "pass_rate"])
    return pd.DataFrame(rows).sort_values("pass_rate").reset_index(drop=True)
