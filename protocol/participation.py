"""Does falling participation after a big advance mean accumulation or distribution?

OHLCV cannot tell you what the participants intended. Anyone who claims a
contracting-volume stock is "accumulating" or "distributing" is asserting an
intent the data does not contain. What the data CAN answer is the narrower,
testable question underneath:

    participation is decaying -- so what is PRICE doing while it decays?

    A. price holds above the structural reference  -> contraction, unresolved
    B. price loses the structural reference        -> rejection
    C. participation contracts, then expands back through the level
                                                       -> resolved upward

A and B look identical on a volume chart. They are not the same state, and if
they carry different forward returns then "low volume" is an incomplete
description of the world -- it hides the variable that matters.

This module measures all three against the equal-weight universe baseline, so
the answer is a number rather than a story. Nothing here infers intent: a
cohort is named for what price did, never for what someone was doing.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

COHORTS = {
    "A_holds_reference":
        "participation decaying, price still ABOVE the prior 20-session high",
    "B_loses_reference":
        "participation decaying, price now BELOW the prior 20-session high",
    "C_contracts_then_expands":
        "participation decays, then volume expands back through the level",
    "D_high_participation_loses":
        "control: participation HIGH while price is below the reference",
}


def _fwd(d: pd.DataFrame, horizon: int) -> pd.Series:
    """Forward close-to-close return over `horizon` sessions, NaN past the end."""
    return d["Close"].shift(-horizon) / d["Close"] - 1.0


def label_cohorts(d: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """One row per session per symbol, labelled by what price did.

    Everything is read from the current bar and earlier: the reference level is
    the prior `participation.reference` sessions' high, shifted, so the current
    bar never defines its own level.

    ONE EXCEPTION, DELIBERATE: cohort C ("contracts then expands") is defined by
    what happens in the NEXT `expand_within` sessions, because "participation
    expanded back through the level" is not knowable until it has happened. That
    label is therefore DESCRIPTIVE ONLY -- it says what a completed move looked
    like, and the `expanded` flag is never used as a trading signal, so it can
    never leak into an entry decision. Cohorts A, B and D are all point-in-time.
    """
    pol = cfg["participation"]
    ref_n, low, high = int(pol["reference"]), float(pol["rvol_low"]), \
        float(pol["rvol_high"])
    win, lookback = int(pol["decay_window"]), int(pol["decay_lookback"])
    expand_in, expand_rvol = int(pol["expand_within"]), float(pol["expand_rvol"])

    out = pd.DataFrame({
        "Date": d["Date"], "Symbol": d["Symbol"],
        "rvol20": d["rvol20"], "close": d["Close"], "R": d[f"R{ref_n}"],
        "ret120": d["ret120"], "atr": d["atr14"],
    })
    out["above"] = out["close"] > out["R"]
    # participation decaying: today's volume below a window that excludes today,
    # and that window itself below the one before it
    vol = d["Volume"].astype(float)
    now = vol / vol.rolling(win, min_periods=win).mean().shift(1)
    prev = (vol.rolling(win, min_periods=win).mean().shift(1)
            / vol.rolling(win, min_periods=win).mean().shift(win))
    out["decaying"] = (now < 1.0) & (prev < 1.0) & (now.notna() & prev.notna())
    out["high_participation"] = d["rvol20"] >= high
    for h in (5, 10, 20, 40):
        out[f"fwd{h}"] = _fwd(d, h)

    # Did participation expand back and take the level within `expand_in`
    # sessions? Read from the FUTURE only to LABEL a cohort; the label is never
    # used as a trading signal, so it cannot leak into an entry decision.
    # Vectorised: n shifted comparisons OR-ed together, not a per-row window.
    expands = pd.Series(False, index=out.index)
    for k in range(1, expand_in + 1):
        expands |= ((out["rvol20"].shift(-k) >= expand_rvol)
                    & (out["close"].shift(-k) > out["R"])).fillna(False)
    out["expanded"] = expands

    out["cohort"] = np.select(
        [
            out["decaying"] & out["expanded"],
            out["decaying"] & out["above"],
            out["decaying"],
            out["high_participation"] & ~out["above"],
        ],
        ["C_contracts_then_expands", "A_holds_reference", "B_loses_reference",
         "D_high_participation_loses"],
        default="",
    )
    return out.replace({"cohort": {"": np.nan}})


def forward_means(long: pd.DataFrame, horizons=(5, 10, 20, 40)) -> pd.DataFrame:
    """Mean forward return per cohort per horizon, with n and the excess."""
    rows = []
    for name in list(COHORTS) :
        sub = long[long["cohort"] == name]
        row = {"cohort": name, "what_it_is": COHORTS[name], "events": int(len(sub))}
        for h in horizons:
            col = f"fwd{h}"
            row[f"fwd{h}"] = round(float(sub[col].mean()), 4) if len(sub) else None
            row[f"n{h}"] = int(sub[col].notna().sum())
        rows.append(row)
    return pd.DataFrame(rows)


def study(panel: dict[str, pd.DataFrame], cfg: dict,
          horizons=(5, 10, 20, 40)) -> dict[str, Any]:
    """Measure all cohorts, plus the universe baseline they must beat."""
    frames = [label_cohorts(f.reset_index(drop=True), cfg)
              for f in panel.values()]
    long = pd.concat(frames, ignore_index=True)

    table = forward_means(long, horizons)
    base = {}
    for h in horizons:
        col = long[f"fwd{h}"].dropna()
        base[h] = {"mean": round(float(col.mean()), 4), "n": int(len(col))}
    table["excess_vs_universe_fwd20"] = [
        round(float(r["fwd20"] - base[20]["mean"]), 4) if r["fwd20"] is not None else None
        for _, r in table.iterrows()]

    # does the SAME low-participation state split into different outcomes?
    decay = long[long["cohort"].isin(["A_holds_reference", "B_loses_reference"])]
    split = {}
    for h in horizons:
        a = decay[decay["cohort"] == "A_holds_reference"][f"fwd{h}"].dropna()
        b = decay[decay["cohort"] == "B_loses_reference"][f"fwd{h}"].dropna()
        split[h] = {
            "A_mean": round(float(a.mean()), 4) if len(a) else None, "A_n": int(len(a)),
            "B_mean": round(float(b.mean()), 4) if len(b) else None, "B_n": int(len(b)),
            "gap": round(float(a.mean() - b.mean()), 4) if len(a) and len(b) else None,
        }

    verdict = _verdict(table, split, base)
    return {"table": table, "baseline": base, "split": split, "verdict": verdict,
            "long": long}


def _verdict(table: pd.DataFrame, split: dict, base: dict) -> str:
    """Plain words for what the numbers say -- and what they do not."""
    parts = []
    g20 = split.get(20, {}).get("gap")
    if g20 is None:
        parts.append("Too few events to separate the two low-participation states.")
    else:
        direction = "better" if g20 > 0 else "worse"
        parts.append(
            f"With participation decaying, holding the structural reference is "
            f"{direction} than losing it by {abs(g20):.2%} over 20 sessions "
            f"({split[20]['A_mean']} vs {split[20]['B_mean']}). "
            f"So 'low volume' is an incomplete description: what PRICE did while "
            f"the volume decayed carries the difference.")
    parts.append(
        "None of this establishes intent. A cohort named for what price did is "
        "not a claim about who was buying or selling; OHLCV cannot support that "
        "claim, and the engine does not make it.")
    return " ".join(parts)


def to_markdown(result: dict[str, Any]) -> str:
    t = result["table"]
    L = [
        "# Does falling participation mean accumulation or distribution?", "",
        "Neither word is knowable from OHLCV. The testable question underneath "
        "is what PRICE did while participation decayed.", "",
        "| Cohort | What it is | Events | fwd 5d | fwd 10d | fwd 20d | fwd 40d | vs universe (20d) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for _, r in t.iterrows():
        L.append(f"| **{r['cohort']}** | {r['what_it_is']} | {r['events']:,} | "
                 f"{r.get('fwd5')} | {r.get('fwd10')} | {r.get('fwd20')} | "
                 f"{r.get('fwd40')} | {r.get('excess_vs_universe_fwd20')} |")
    b = result["baseline"]
    L.append(f"| _universe baseline_ | every symbol, every session | — | "
             f"{b[5]['mean']} | {b[10]['mean']} | {b[20]['mean']} | {b[40]['mean']} | 0 |")
    L += ["", "## The same low volume, split by what price did", "",
          "| Horizon | Participation decaying, price HOLDS | Participation decaying, price LOSES | Gap | n hold / n lose |",
          "|---|---|---|---|---|"]
    for h in (5, 10, 20, 40):
        s = result["split"].get(h, {})
        L.append(f"| {h}d | {s.get('A_mean')} | {s.get('B_mean')} | "
                 f"**{s.get('gap')}** | {s.get('A_n')} / {s.get('B_n')} |")
    L += ["", "## Verdict", "", result["verdict"], ""]
    return "\n".join(L)