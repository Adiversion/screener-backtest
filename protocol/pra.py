"""Pressure -> Response -> Acceptance (PRA) event study.

ChatGPT-suggested sibling to the AAE protocol. Classifies effort/response
events using only data through T, then measures forward outcomes (T+1/T+2/
T+3/T+5) and resolution labels purely as outcomes. Never uses T+n data to
form the state at T.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

CLASSES = ["STRUCTURAL_APPROACH", "EXPANSION_ATTEMPT", "STRONG_RETENTION",
           "WEAK_RETENTION", "HIGH_EFFORT_LOW_RESULT", "LOW_EFFORT_HIGH_RESULT"]


def classify_events(feat: pd.DataFrame, cfg: dict, symbol: str) -> pd.DataFrame:
    p = cfg["pra"]
    ref = f"R{int(p['reference'])}"
    d = feat.reset_index(drop=True)
    rows = []
    for i in range(len(d)):
        r = d[ref].iloc[i]
        if np.isnan(r):
            continue
        high, low, close = d["High"].iloc[i], d["Low"].iloc[i], d["Close"].iloc[i]
        atr = d["atr14"].iloc[i]
        if np.isnan(atr) or atr <= 0:
            continue
        pen = (high - r) / atr
        cdisp = (close - r) / atr
        rng = high - low
        cr = (close - low) / rng if rng > 0 else np.nan
        ret = (close - r) / (high - r) if high > r else np.nan
        rvol = d["rvol20"].iloc[i]
        result = d["result_atr"].iloc[i]
        cls = _classify(pen, high, close, r, atr, ret, rvol, result, p)
        if cls is None:
            continue
        rows.append({
            "symbol": symbol, "date": d["Date"].iloc[i], "reference": ref, "R": r,
            "RVOL20": rvol, "ATR14": atr, "atrpct": d["atrpct"].iloc[i],
            "result_atr": result, "penetration": pen, "closing_disp": cdisp,
            "closing_range": cr, "retention": ret, "efficiency": d["efficiency"].iloc[i],
            "event_class": cls,
            "high_effort_low_result": bool(rvol >= p["high_effort_rvol"] and result <= p["low_result_atr"]),
            "low_effort_high_result": bool(rvol <= p["low_effort_rvol"] and result >= p["high_result_atr"]),
        })
    return pd.DataFrame(rows)


def _classify(pen, high, close, r, atr, ret, rvol, result, p):
    if pen > p["penetration_min"]:
        if close > r:
            return "STRONG_RETENTION" if ret >= p["retention_strong"] else "WEAK_RETENTION"
        return "EXPANSION_ATTEMPT"
    if (r - high) <= p["approach_atr"] * atr:
        return "STRUCTURAL_APPROACH"
    if rvol >= p["high_effort_rvol"] and result <= p["low_result_atr"]:
        return "HIGH_EFFORT_LOW_RESULT"
    if rvol <= p["low_effort_rvol"] and result >= p["high_result_atr"]:
        return "LOW_EFFORT_HIGH_RESULT"
    return None


def attach_outcomes(feat: pd.DataFrame, events: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Forward returns + resolution labels measured only after T."""
    if events.empty:
        return events.assign(**{f"fwd_ret_{h}": [] for h in cfg["pra"]["horizons"]})
    d = feat.reset_index(drop=True)
    idx_of = {ts: i for i, ts in enumerate(d["Date"])}
    horizons = cfg["pra"]["horizons"]
    win = int(cfg["pra"]["resolution_window"])
    out = []
    for _, ev in events.iterrows():
        i = idx_of.get(ev["date"])
        if i is None:
            continue
        close = d["Close"].to_numpy(float)
        row = ev.to_dict()
        for h in horizons:
            j = i + h
            row[f"fwd_ret_{h}"] = close[j] / close[i] - 1.0 if j < len(close) else np.nan
        seg = d.iloc[i + 1:min(i + 1 + max(horizons), len(d))]
        row["MAE"] = float((seg["Low"].min() / close[i] - 1.0)) if len(seg) else np.nan
        row["MFE"] = float((seg["High"].max() / close[i] - 1.0)) if len(seg) else np.nan
        row["resolution"] = _resolution(close, i, win)
        out.append(row)
    return pd.DataFrame(out)


def _resolution(close: np.ndarray, i: int, window: int) -> str:
    rejected = any(close[k] < close[i] * 0.98 for k in range(i + 1, min(i + 1 + window, len(close))))
    recovered = any(close[k] > close[i] for k in range(i + 1, min(i + 4, len(close))))
    if not rejected:
        return "ACCEPTED"
    return "RECOVERED_AFTER_REJECTION" if recovered else "CONTINUED_FAILURE"


def outcome_table(events: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    if events.empty or "event_class" not in events.columns:
        return pd.DataFrame()
    horizons = cfg["pra"]["horizons"]
    rows = []
    for cls, grp in events.groupby("event_class"):
        row = {"event_class": cls, "N": len(grp), "MAE": round(grp["MAE"].mean(), 4),
               "MFE": round(grp["MFE"].mean(), 4)}
        for h in horizons:
            col = f"fwd_ret_{h}"
            row[f"T+{h}_mean"] = round(grp[col].mean(), 4)
            row[f"T+{h}_median"] = round(grp[col].median(), 4)
            row[f"T+{h}_win%"] = round((grp[col] > 0).mean(), 4)
        rows.append(row)
    return pd.DataFrame(rows).sort_values("N", ascending=False)


def ablation_table(events: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Section-23 model ladder A..F; mean T+1 return and win rate per model."""
    if events.empty or "penetration" not in events.columns:
        return pd.DataFrame(columns=["model", "N", "T+1_mean", "T+1_win%", "T+5_mean"])
    p = cfg["pra"]
    a = p["ablation"]
    base = events["penetration"] > p["penetration_min"]
    vol = events["RVOL20"] >= a["rvol_min"]
    resp = events["result_atr"] >= a["response_min"]
    ret = events["retention"] >= a["retention_min"]
    crng = events["closing_range"] >= a["closing_range_min"]
    models = {
        "A_breakout": base,
        "B_plus_volume": base & vol,
        "C_plus_response": base & vol & resp,
        "D_plus_retention": base & vol & ret,
        "E_response_retention": base & vol & resp & ret,
        "F_full": base & vol & resp & ret & crng,
    }
    rows = []
    for name, mask in models.items():
        grp = events[mask.fillna(False)]
        rows.append({"model": name, "N": len(grp),
                     "T+1_mean": round(grp["fwd_ret_1"].mean(), 4) if len(grp) else None,
                     "T+1_win%": round((grp["fwd_ret_1"] > 0).mean(), 4) if len(grp) else None,
                     "T+5_mean": round(grp["fwd_ret_5"].mean(), 4) if len(grp) else None})
    return pd.DataFrame(rows)


def run_event_study(panel: dict[str, pd.DataFrame], cfg: dict) -> dict[str, Any]:
    frames = [attach_outcomes(f, classify_events(f, cfg, s), cfg) for s, f in panel.items()]
    frames = [x for x in frames if not x.empty]
    events = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    return {"events": events, "outcomes": outcome_table(events, cfg),
            "ablation": ablation_table(events, cfg)}
