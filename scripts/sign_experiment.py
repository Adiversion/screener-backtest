#!/usr/bin/env python3
"""Before/after test of component sign choices. Score, then measure, then judge.

    python scripts/sign_experiment.py

Two claims in this repo turned out to be wrong when re-measured on the rebuilt
6-year panel, and both concern the SIGN a component is given:

  - `efficiency` genuinely flips. IC is positive among names that clear the
    gates (+0.0321, t +4.15 at 20 sessions) and negative among those that do
    not (-0.0198, t -18.20). The engine only ever buys gate-clearers, so only
    the first number describes the regime it trades in.
  - `atrpct` was reported as flipping too. It does not. It is positive in BOTH
    regimes, which means the "-1, low volatility wins" sign inherited from the
    original breakout-event study points the wrong way for the population the
    engine actually trades.

Re-measuring is cheap. Changing a sign on the strength of it is not, because a
sign is a fitted parameter like any other. So every variant here is scored on
the same panel, held to the same gates, and measured by the same pooled test
that judged the baseline. A change is only worth keeping if it moves that
number, not because the sign looks tidier.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from protocol import quality, ranking  # noqa: E402
from protocol.config import load_config  # noqa: E402
from protocol.data import load_history  # noqa: E402
from protocol.features import build_panel  # noqa: E402

HOLD = 20
CACHE = ROOT / "reports" / "sign_variants.parquet"
RAW_PATH = ROOT / "reports" / "sign_raw_long.parquet"

VARIANTS = {
    # name: {component: sign}. Anything absent keeps its current sign.
    "A_baseline": {},
    "B_atrpct_flip": {"atrpct": +1},
    "C_both_flip": {"atrpct": +1, "efficiency": +1},
    "D_flip_and_drop_pinned": {"atrpct": +1, "efficiency": +1, "penetration": 0},
}


def components_with(signs: dict[str, int]) -> dict:
    out = dict(quality.COMPONENTS)
    for k, s in signs.items():
        if k in out and s == 0:
            out.pop(k)
        elif k in out:
            label, _, what, why = out[k]
            out[k] = (label, s, what, why)
    return out


def build_all(cfg) -> pd.DataFrame:
    """Score every variant on the same long frame, in one pass."""
    if CACHE.exists():
        return pd.read_parquet(CACHE)
    history = load_history(str(ROOT / "data" / "nse_all_history.parquet"))
    long = ranking.build_long(build_panel(history), cfg)
    long.to_parquet(RAW_PATH, index=False)
    frames = []
    first = next(iter(VARIANTS))
    for name, signs in VARIANTS.items():
        comps = components_with(signs)
        scored = ranking.rank_all(long.copy(), cfg, comps)
        scored = scored.rename(columns={"score": f"score_{name}"})
        # `clears` comes from the gates and is identical across variants, so it
        # is carried once; carrying it per variant collides on merge.
        keep = ["date", "symbol", "clears", f"score_{name}"] if name == first             else ["date", "symbol", f"score_{name}"]
        frames.append(scored[keep])
        print(f"  scored {name}", flush=True)
    out = frames[0]
    for f in frames[1:]:
        out = out.merge(f, on=["date", "symbol"], how="outer")
    out.to_parquet(CACHE, index=False)
    return out


def main() -> int:
    cfg = load_config()
    h = load_history(str(ROOT / "data" / "nse_all_history.parquet"))
    h = h.sort_values(["Symbol", "Date"])
    h["fwd"] = h.groupby("Symbol")["Close"].shift(-HOLD) / h["Close"] - 1.0
    h = h[["Date", "Symbol", "fwd"]].rename(
        columns={"Date": "date", "Symbol": "symbol"})

    print("scoring every sign variant on the same panel ...", flush=True)
    d = build_all(cfg).merge(h, on=["date", "symbol"], how="left")
    d = d[d["fwd"].notna() & d["clears"]]
    print(f"{len(d):,} gate-clearers with a {HOLD}-session outcome, "
          f"{d['date'].nunique()} sessions\n")

    print(f"{'variant':<24}{'top1':>9}{'top3':>9}{'top10':>9}"
          f"{'t vs base':>11}{'beat rate':>11}")
    print("-" * 73)
    base = None
    results = {}
    for name in VARIANTS:
        col = f"score_{name}"
        # The top-N names' FORWARD RETURN, not their score. Selecting the score
        # value and subtracting the return gives a number near the score itself
        # (~0.7) and a ~100% beat rate, which is how that mistake was caught.
        def _ret(g: pd.DataFrame, k: int) -> float:
            return g.nlargest(k, col)["fwd"].mean()

        per_day = d.groupby("date").apply(_ret, include_groups=False, k=1)
        top1 = d["date"].map(per_day)
        top3 = d["date"].map(d.groupby("date").apply(_ret, include_groups=False, k=3))
        top10 = d["date"].map(d.groupby("date").apply(_ret, include_groups=False, k=10))
        r = (top1 - d["fwd"]).groupby(d["date"]).mean()
        if base is None:
            base = r
            t = np.nan
        else:
            diff = (r - base).dropna()
            t = diff.mean() / (diff.std() / np.sqrt(len(diff))) if diff.std() else np.nan
        results[name] = (top1.mean(), top3.mean(), top10.mean(), t,
                         (top1 > d["fwd"]).mean())
        print(f"{name:<24}{top1.mean():>8.2%}{top3.mean():>9.2%}"
              f"{top10.mean():>9.2%}{t:>11.2f}{(top1 > d['fwd']).mean():>11.1%}")

    print("\ntop1 is the 20-session forward return of the single highest-scoring")
    print("name each session. 'beat rate' is how often that name beat the")
    print("same day's mean gate-clearing name. A t under 2 is not evidence.")
    best = max(results, key=lambda k: results[k][0])
    print(f"\nhighest mean top1: {best} at {results[best][0]:+.2%}")
    if results[best][3] is not np.nan and abs(results[best][3]) < 2:
        print("but its improvement over the baseline is NOT significant. "
              "Keeping it would be fitting a sign to noise.")
    CACHE.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
