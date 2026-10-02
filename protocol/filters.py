"""A5 trap filters F1..F11 evaluated at trigger day E.

Filters whose input data is absent from the feed (delivery, price bands,
corporate-action calendar, circuit locks) return None => the candidate is
flagged `filter_incomplete` and reported with and without. A candidate is
rejected if ANY available filter is True.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

_UNAVAILABLE = {
    "F4": "delivery data unavailable",
    "F6": "price-band/surveillance lists unavailable",
    "F9": "corporate-action calendar unavailable",
    "F10": "circuit-lock history unavailable",
}


def evaluate(feat: pd.DataFrame, event: dict[str, Any], cfg: dict) -> dict[str, Any]:
    f = cfg["filters"]
    d = feat.reset_index(drop=True)
    e_idx = int(d.index[d["Date"] == event["E_date"]][0])
    d0_idx = int(d.index[d["Date"] == event["D0_date"]][0])

    close = float(d["Close"].iloc[e_idx])
    atrpct = float(d["atrpct"].iloc[e_idx])
    ext = float(d["extension"].iloc[e_idx])
    ret2 = float(d["ret2"].iloc[e_idx])

    checks = {
        "F1": ret2 >= f["f1_ret2_max"],
        "F2": ext > f["f2_extension_max"],
        "F3": _exhaustion_candle(d, e_idx, f),
        "F4": None,
        "F5": (atrpct > f["f5_atr_pct_max"]) or (atrpct < f["f5_atr_pct_min"]),
        "F6": None,
        "F7": close < f["f7_min_price"],
        "F8": _illiquid(d, e_idx, f),
        "F9": None,
        "F10": None,
        "F11": _pullback_distribution(d, d0_idx, e_idx, event),
    }
    reasons = [k for k, v in checks.items() if v is True]
    incomplete = any(v is None for v in checks.values())
    return {
        "filters": checks,
        "reasons": reasons,
        "rejected_by_filter": bool(reasons),
        "filter_incomplete": incomplete,
        "unavailable": {k: _UNAVAILABLE[k] for k, v in checks.items() if v is None},
    }


def _exhaustion_candle(d: pd.DataFrame, e_idx: int, f: dict) -> bool:
    lo = max(0, e_idx - int(f["f3_range_window"]) + 1)
    w = d.iloc[lo:e_idx + 1].copy()
    w["rng"] = w["High"] - w["Low"]
    big = w.loc[w["rng"].idxmax()]
    return bool(big["closing_range"] < f["f3_closing_range_min"])


def _illiquid(d: pd.DataFrame, e_idx: int, f: dict) -> bool:
    turnover = d["turnover20"].iloc[e_idx]
    if np.isnan(turnover):
        return False
    return bool(turnover < f["f8_min_turnover"])


def _pullback_distribution(d: pd.DataFrame, d0_idx: int, e_idx: int, event: dict) -> bool:
    if e_idx - d0_idx <= 1:
        return False
    pull = d["Volume"].iloc[d0_idx + 1:e_idx]
    vol_d0 = event.get("volume_d0")
    if vol_d0 is None or np.isnan(vol_d0) or len(pull) == 0:
        return False
    return bool(pull.mean() > vol_d0)
