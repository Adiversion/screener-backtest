"""Does the ranking actually rank? Measure the verdict against the outcome.

Judging one stock tells you almost nothing. A single name that rose after a
REJECT proves neither that the engine is right nor that it is broken -- it is
one draw. Measuring 2,000 names across 500 sessions does.

So this module scores every symbol point-in-time and then asks the only
question that matters about a ranking:

    do higher scores actually go with better forward outcomes?

Three readouts, deliberately different in kind:

1. By SCORE DECILE. This is the ranking's own claim. If the top decile does
   not beat the bottom decile, the score is decoration.
2. By GATE VERDICT (clears / does not). This is the screen's claim, and it is
   a much stronger claim than the score: "pass" implies "this is investable".
   It is measured on a small, self-selected sample, so it is also the easiest
   to over-read -- the sample size is reported with every number.
3. By SESSION, for one named date. The same measurement restricted to a single
   decision bar, which is how a real screen is actually used: "what did the
   engine say on 30 Sep, and what happened on 1 Oct".

Everything is reported in full, including the buckets that lose. Forward
returns are outcomes, never inputs: the score at date T uses only data through
T, so nothing here can leak backwards into a verdict.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from protocol import quality, ranking

HORIZONS = (1, 5, 10, 20)
DECILES = 10


def add_outcomes(long: pd.DataFrame, horizons=HORIZONS) -> pd.DataFrame:
    """Forward close-to-close returns per horizon, computed within each symbol.

    Shifted by a negative amount inside the symbol's own time order, so a
    symbol's outcome is never matched with another's.
    """
    out = long.sort_values(["symbol", "date"]).reset_index(drop=True)
    grouped = out.groupby("symbol", sort=False)["close"]
    for h in horizons:
        out[f"fwd{h}"] = grouped.shift(-h) / out["close"] - 1.0
    # the worst price reached before the exit, so a "winner" that was 15% under
    # water on the way is not scored like one that never moved against you
    for h in horizons:
        lows = out.groupby("symbol", sort=False)["low"].transform(
            lambda s: s[::-1].rolling(h, min_periods=h).min()[::-1])
        out[f"mae{h}"] = lows / out["close"] - 1.0
    return out


def decile_table(df: pd.DataFrame, horizon: int = 20,
                 buckets: int = DECILES) -> pd.DataFrame:
    """Mean forward return per score decile -- the ranking's own claim."""
    d = df[df[f"fwd{horizon}"].notna() & df["score"].notna()].copy()
    if d.empty:
        return pd.DataFrame()
    d["bucket"] = pd.qcut(d["score"].rank(method="first", ascending=True),
                          buckets, labels=[f"D{i + 1}" for i in range(buckets)])
    g = d.groupby("bucket", observed=True).agg(
        events=("score", "size"), score_mean=("score", "mean"),
        **{f"fwd{h}": (f"fwd{h}", "mean") for h in HORIZONS},
        mae=(f"mae{horizon}", "mean"))
    universe = float(df[f"fwd{horizon}"].dropna().mean())
    g["excess"] = g[f"fwd{horizon}"] - universe
    g.attrs["universe"] = universe
    return g.round(4)


def verdict_table(df: pd.DataFrame, horizon: int = 20) -> pd.DataFrame:
    """Forward outcome of names that cleared every gate vs names that did not."""
    d = df[df[f"fwd{horizon}"].notna()]
    if d.empty:
        return pd.DataFrame()
    rows = []
    for flag, label in ((True, "CLEARS every gate"), (False, "does NOT clear")):
        sub = d[d["clears"] == flag]
        if sub.empty:
            rows.append({"group": label, "events": 0})
            continue
        rows.append({
            "group": label, "events": int(len(sub)),
            "score_mean": round(float(sub["score"].mean()), 4),
            **{f"fwd{h}": round(float(sub[f"fwd{h}"].mean()), 4)
               for h in HORIZONS},
            "win_rate": round(float((sub[f"fwd{horizon}"] > 0).mean()), 4),
            "mae_mean": round(float(sub[f"mae{horizon}"].mean()), 4),
        })
    out = pd.DataFrame(rows)
    out.attrs["universe"] = round(float(d[f"fwd{horizon}"].mean()), 4)
    return out


def session_audit(df: pd.DataFrame, date: pd.Timestamp,
                  horizon: int = 20, top: int = 25) -> pd.DataFrame:
    """One decision bar in full: the verdict on `date` and what followed."""
    d = df[(df["date"] == np.datetime64(pd.Timestamp(date)))
           & df[f"fwd{horizon}"].notna()].copy()
    if d.empty:
        return pd.DataFrame()
    d = d.sort_values("score", ascending=False).head(top)
    d["outcome"] = np.where(d[f"fwd{horizon}"] > 0, "up", "down")
    return d[["symbol", "date", "score", "clears", "close", f"fwd1",
              f"fwd{horizon}", f"mae{horizon}", "outcome"]].round(4)


def monotonicity(table: pd.DataFrame, horizon: int = 20) -> dict[str, Any]:
    """Does the HIGHEST-score bucket beat the LOWEST-score bucket?

    This is the whole test. A ranking whose best bucket does not beat its worst
    is not a ranking, whatever its individual numbers look like.

    The buckets arrive labelled D1..D10 by ASCENDING score, so the highest
    scoring bucket is the LAST row. Getting that backwards inverts the sign of
    the result and reports the opposite of the truth.
    """
    if table.empty:
        return {"verdict": "NO DATA"}
    col = f"fwd{horizon}" if f"fwd{horizon}" in table.columns else "fwd20"
    best, worst = table.iloc[-1], table.iloc[0]
    spread = float(best[col] - worst[col])
    # correlation between the bucket index and the bucket mean: near zero means
    # the score carries no ordering information at all
    order_corr = float(np.corrcoef(
        np.arange(len(table)), table[col].to_numpy())[0, 1]) if len(table) > 2 else None
    if spread > 0:
        verdict = (f"The highest-scoring bucket beats the lowest-scoring bucket by "
                   f"{spread:.2%} over {horizon} sessions, and the ladder between them "
                   f"is {'monotone' if order_corr > 0.9 else 'broadly increasing'}. "
                   f"The ranking orders outcomes.")
    else:
        verdict = (f"The highest-scoring bucket does NOT beat the lowest-scoring "
                   f"one ({spread:.2%} over {horizon} sessions). The ranking does "
                   f"not order outcomes.")
    return {"verdict": verdict, "top_minus_bottom": round(spread, 4),
            "trend_corr": round(order_corr, 3) if order_corr is not None else None,
            "universe_mean": table.attrs.get("universe")}


def build(panel, cfg, horizons=HORIZONS) -> pd.DataFrame:
    """Score every symbol on every session, then attach the forward outcomes."""
    long = ranking.build_long(panel, cfg)
    scored = ranking.rank_all(long, cfg, quality.COMPONENTS)
    return add_outcomes(scored, horizons)


def to_markdown(payload: dict[str, Any]) -> str:
    d = payload["deciles"]
    v = payload["verdicts"]
    L = [
        "# Does the ranking actually rank?", "",
        f"Session range {payload['from']} to {payload['to']}, "
        f"{payload['symbols']} symbols, {payload['events']:,} scored observations.",
        "", "## 1. The one-line answer", "", f"**{payload['summary']}**", "",
        "## 2. Score decile vs what actually happened next", "",
        "| Decile | Events | Mean score | +1d | +5d | +10d | +20d | vs universe |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for _, r in d.iterrows():
        L.append(f"| **{r.name}** | {int(r['events']):,} | {r['score_mean']} | "
                 f"{r.get('fwd1')} | {r.get('fwd5')} | {r.get('fwd10')} | "
                 f"{r.get('fwd20')} | {r.get('excess')} |")
    L += ["", f"Universe mean 20-session forward return: "
              f"**{payload['monotonicity'].get('universe_mean')}**", "",
          "## 3. The gate verdict -- the screen's strongest claim", "",
          "| Group | Events | Mean score | +1d | +5d | +10d | +20d | Win rate | Worst-excursion |",
          "|---|---|---|---|---|---|---|---|---|"]
    for _, r in v.iterrows():
        if not r.get("events"):
            L.append(f"| {r['group']} | 0 | — | — | — | — | — | — | — |")
            continue
        L.append(f"| **{r['group']}** | {int(r['events']):,} | {r['score_mean']} | "
                 f"{r.get('fwd1')} | {r.get('fwd5')} | {r.get('fwd10')} | "
                 f"{r.get('fwd20')} | {r.get('win_rate')} | {r.get('mae_mean')} |")
    s = payload["session"]
    if s is not None and not s.empty:
        L += ["", f"## 4. One decision bar in full — {s.iloc[0]['date']}", "",
              "The same measurement restricted to a single session, which is how "
              "a screen is actually used: what the engine said, and what followed.",
              "| Symbol | Score | Clears | Close | +1d | +20d | Worst excursion |",
              "|---|---|---|---|---|---|---|"]
        for _, r in s.iterrows():
            L.append(f"| {r['symbol']} | {r['score']} | "
                     f"{'yes' if r['clears'] else 'no'} | {r['close']} | "
                     f"{r.get('fwd1')} | {r.get('fwd20')} | {r.get('mae20')} |")
    L += ["", "## What this does and does not prove", ""]
    L += [f"- {c}" for c in payload["caveats"]]
    L += ["", "Forward returns are OUTCOMES. Every score was computed from data "
          "through its own session, so no outcome feeds back into a verdict."]
    return "\n".join(L)