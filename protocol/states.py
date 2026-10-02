"""A4 state machine: BREAKOUT_DAY -> ACCEPTANCE_HOLD -> ACCEPTED_EXPANSION_TRIGGER.

Pure per-symbol scan over a feature frame. Every decision at day E reads only
rows with date <= E. The forward wait from D0 to E is a study of the state,
not lookahead: no value known after E is used to form the E decision.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

_KEYS = ("Date", "High", "Low", "Close", "Volume", "R20", "atr14", "rvol20",
         "closing_range", "retention", "ret2", "extension", "penetration",
         "closing_disp", "efficiency")


def _arrays(feat: pd.DataFrame) -> dict[str, np.ndarray]:
    d = feat.reset_index(drop=True)
    return {k: d[k].to_numpy(float) if k != "Date" else d[k].to_numpy() for k in _KEYS}


def find_events(feat: pd.DataFrame, cfg: dict) -> list[dict[str, Any]]:
    s0, s1, s2 = cfg["state0"], cfg["state1"], cfg["state2"]
    window, base_n = int(s1["window"]), int(s0["r_ref"])
    undercut = float(s1["undercut_atr"])
    a = _arrays(feat)
    close, high, low = a["Close"], a["High"], a["Low"]
    events: list[dict[str, Any]] = []
    n = len(close)
    i = base_n
    while i < n - 1:
        if _is_breakout(i, cfg, a, base_n):
            ev = _scan_acceptance(i, window, undercut, s2, a)
            events.append(ev)
            i = ev["_next_index"]
        else:
            i += 1
    return [e for e in events if e.pop("_emit")]


def _is_breakout(i: int, cfg: dict, a: dict, base_n: int) -> bool:
    s0 = cfg["state0"]
    close, high, low = a["Close"], a["High"], a["Low"]
    if np.isnan(a["R20"][i]) or np.isnan(a["atr14"][i]):
        return False
    if not (close[i] > a["R20"][i] and a["rvol20"][i] >= s0["rvol_min"]):
        return False
    if not (a["closing_range"][i] >= s0["closing_range_min"] and a["retention"][i] >= s0["retention_min"]):
        return False
    hi = np.nanmax(high[i - base_n:i])
    lo = np.nanmin(low[i - base_n:i])
    if not (hi - lo) / close[i] <= s0["base_range_max"]:
        return False
    return a["ret2"][i - 1] < s0["ret2_max"] and a["extension"][i - 1] < s0["extension_max"]


def _scan_acceptance(i: int, window: int, undercut: float, s2: dict, a: dict) -> dict[str, Any]:
    close, high, low, vol = a["Close"], a["High"], a["Low"], a["Volume"]
    r20_d0, vol_d0, atr_d0, high_d0 = a["R20"][i], vol[i], a["atr14"][i], high[i]
    date = a["Date"]
    for j in range(i + 1, min(i + 1 + window, len(close))):
        if close[j] < r20_d0:
            return _rejected(i, j, a, r20_d0)
        held = vol[j] < vol_d0 and low[j] >= r20_d0 - undercut * atr_d0
        if not held:
            continue
        pullback_high = high_d0 if j == i + 1 else np.nanmax(high[i + 1:j])
        if close[j] > pullback_high and a["closing_range"][j] >= s2["closing_range_min"]:
            stop = float(np.nanmin(low[i + 1:j + 1]) - 0.25 * a["atr14"][j])
            dist = (close[j] - stop) / close[j]
            return {
                "_emit": True, "_next_index": j + 1,
                "label": "CANDIDATE" if dist <= s2["stop_distance_max"] else "SKIP_STOP_TOO_WIDE",
                "D0_date": date[i], "E_date": date[j],
                "R20": r20_d0, "rvol20_d0": a["rvol20"][i], "atr14_d0": atr_d0,
                "atr14_e": float(a["atr14"][j]), "closing_range_d0": a["closing_range"][i],
                "retention_d0": a["retention"][i], "penetration_d0": a["penetration"][i],
                "closing_disp_d0": a["closing_disp"][i], "efficiency_d0": a["efficiency"][i],
                "structural_stop": stop, "stop_distance": float(dist),
                "expected_entry": float(close[j]), "pullback_days": j - i,
                "volume_d0": float(vol_d0),
            }
    return {"_emit": False, "_next_index": i + 1}


def _rejected(i: int, j: int, a: dict, r20_d0: float) -> dict[str, Any]:
    close = a["Close"]
    recovered = any(close[k] > r20_d0 for k in range(j + 1, min(j + 4, len(close))))
    return {
        "_emit": True, "_next_index": j + 1,
        "label": "RECOVERED_AFTER_REJ" if recovered else "CONTINUED_FAILURE",
        "D0_date": a["Date"][i], "E_date": a["Date"][j], "reject_date": a["Date"][j],
        "structural_stop": float("nan"), "stop_distance": float("nan"),
        "expected_entry": float("nan"), "pullback_days": j - i,
    }


def high_effort_low_result(feat: pd.DataFrame) -> list[dict[str, Any]]:
    """A4 outcome-side label: RVOL20 >= 2.5 and ResultATR <= 0.5."""
    d = feat.reset_index(drop=True)
    mask = (d["rvol20"] >= 2.5) & (d["result_atr"] <= 0.5)
    return [{"date": r["Date"], "symbol": r["Symbol"]} for _, r in d[mask].iterrows()]
