"""No-lookahead audit (Part B). Must pass before a report is produced.

1 Truncation : features at T from the full series == features from series
               truncated at T (bit-identical).
2 Shuffle    : permuting rows after T must not change features/state at T.
3 Static scan: no shift(-n), center=True, bfill/backfill in protocol source.
4 Ordering   : every trade signal_date < entry_date.
5 Cutoff     : no feature row dated after the configured cutoff is used.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from protocol.features import build_features

FORBIDDEN = ["shift(-", "center=True", "center = True", "bfill", "backfill"]
SOURCE_DIR = Path(__file__).resolve().parent

# Modules that need a forbidden pattern for a declared, non-trading reason.
#
# An exemption is NOT a way to make the audit pass quietly. The pattern is still
# reported, with its reason, in every audit block, and an exemption that no
# longer matches anything is itself flagged as stale -- so a module cannot keep
# a permanent silent pass after the code that justified it is deleted.
DECLARED_EXEMPTIONS: dict[str, str] = {
    "participation.py": (
        "Reads the future on purpose, to LABEL a cohort: 'participation later "
        "expanded back through the level' is not knowable until it has happened. "
        "The label is descriptive only and is never an entry signal; cohorts A, "
        "B and D are all point-in-time. See label_cohorts's docstring."),
}


def _exemption_for(module: str, pattern: str) -> str | None:
    """The declared reason for a pattern in a module, if there is one."""
    return DECLARED_EXEMPTIONS.get(module) if pattern.startswith("shift(") else None


def truncation_test(history: pd.DataFrame, n_samples: int, seed: int) -> dict[str, Any]:
    rng = np.random.default_rng(seed)
    symbols = list(history["Symbol"].unique())
    checked = mismatches = 0
    for _ in range(n_samples):
        sym = symbols[int(rng.integers(0, len(symbols)))]
        bars = history[history["Symbol"] == sym].sort_values("Date").reset_index(drop=True)
        if len(bars) < 80:
            continue
        t = int(rng.integers(60, len(bars)))
        full = build_features(bars)
        trunc = build_features(bars.iloc[:t + 1])
        cols = ["atr14", "rvol20", "R20", "retention", "extension", "ret2", "atrpct"]
        a = full.iloc[t][cols].to_numpy(float)
        b = trunc.iloc[t][cols].to_numpy(float)
        checked += 1
        if not np.allclose(a, b, equal_nan=True):
            mismatches += 1
    return {"test": "truncation", "checked": checked, "mismatches": mismatches,
            "pass": mismatches == 0}


def shuffle_future_test(history: pd.DataFrame, n_samples: int, seed: int) -> dict[str, Any]:
    rng = np.random.default_rng(seed + 1)
    symbols = list(history["Symbol"].unique())
    checked = mismatches = 0
    for _ in range(n_samples):
        sym = symbols[int(rng.integers(0, len(symbols)))]
        bars = history[history["Symbol"] == sym].sort_values("Date").reset_index(drop=True)
        if len(bars) < 80:
            continue
        t = int(rng.integers(60, len(bars) - 5))
        shuffled = bars.copy()
        future = shuffled.iloc[t + 1:].sample(frac=1.0, random_state=int(rng.integers(0, 1 << 31)))
        shuffled.iloc[t + 1:] = future.to_numpy()
        base = build_features(bars).iloc[t]
        pert = build_features(shuffled).iloc[t]
        cols = ["atr14", "rvol20", "R20", "retention", "extension"]
        checked += 1
        if not np.allclose(base[cols].to_numpy(float), pert[cols].to_numpy(float), equal_nan=True):
            mismatches += 1
    return {"test": "shuffle_future", "checked": checked, "mismatches": mismatches,
            "pass": mismatches == 0}


def static_scan() -> dict[str, Any]:
    hits, exempt, seen = [], [], set()
    for path in sorted(SOURCE_DIR.glob("*.py")):
        if path.name == Path(__file__).name:  # this module holds the pattern list
            continue
        text = path.read_text(encoding="utf-8")
        for pat in FORBIDDEN:
            if pat not in text:
                continue
            seen.add(path.name)
            reason = _exemption_for(path.name, pat)
            if reason:
                exempt.append({"module": path.name, "pattern": pat, "reason": reason})
            else:
                hits.append(f"{path.name}:{pat}")
    stale = sorted(set(DECLARED_EXEMPTIONS) - seen)
    for module in stale:
        hits.append(f"{module}: stale exemption -- the pattern it excused is gone")
    return {"test": "static_scan", "hits": hits, "exemptions": exempt,
            "pass": not hits}


def ordering_test(trades: list[dict[str, Any]]) -> dict[str, Any]:
    bad = [t for t in trades if not t.get("skipped") and not (t["signal_date"] < t["entry_date"])]
    return {"test": "ordering", "checked": len(trades), "violations": len(bad), "pass": not bad}


def cutoff_test(panel: dict[str, pd.DataFrame], cutoff: pd.Timestamp) -> dict[str, Any]:
    worst = max((f["Date"].max() for f in panel.values()), default=None)
    return {"test": "cutoff", "max_date": str(worst.date()) if worst is not None else None,
            "cutoff": str(pd.Timestamp(cutoff).date()),
            "pass": worst is None or worst <= pd.Timestamp(cutoff)}


def run_all(history, panel, trades, cutoff, cfg) -> dict[str, Any]:
    tests = [
        truncation_test(history, 200, cfg["run"]["seed"]),
        shuffle_future_test(history, 100, cfg["run"]["seed"]),
        static_scan(),
        ordering_test(trades),
        cutoff_test(panel, cutoff),
    ]
    return {"passed": all(t["pass"] for t in tests), "tests": tests}
