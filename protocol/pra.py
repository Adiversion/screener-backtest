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
    if d.empty:
        return pd.DataFrame()
    r = d[ref].to_numpy(float)
    atr = d["atr14"].to_numpy(float)
    high, low, close = d["High"].to_numpy(float), d["Low"].to_numpy(float), d["Close"].to_numpy(float)
    rvol, result = d["rvol20"].to_numpy(float), d["result_atr"].to_numpy(float)
    rng = high - low
    with np.errstate(divide="ignore", invalid="ignore"):
        pen = (high - r) / atr
        cdisp = (close - r) / atr
        cr = np.where(rng > 0, (close - low) / rng, np.nan)
        ret = np.where(high > r, (close - r) / (high - r), np.nan)
    valid = (~np.isnan(r)) & (~np.isnan(atr)) & (atr > 0)
    pen_hit = valid & (pen > p["penetration_min"])
    above = close > r
    strong = ret >= p["retention_strong"]
    near = valid & (~pen_hit) & ((r - high) <= p["approach_atr"] * atr)
    c5 = valid & (~pen_hit) & (~near) & (rvol >= p["high_effort_rvol"]) & (result <= p["low_result_atr"])
    c6 = valid & (~pen_hit) & (~near) & (~c5) & (rvol <= p["low_effort_rvol"]) & (result >= p["high_result_atr"])
    state = np.select(
        [pen_hit & above & strong, pen_hit & above & (~strong), pen_hit & (~above),
         near, c5, c6],
        ["STRONG_RETENTION", "WEAK_RETENTION", "EXPANSION_ATTEMPT",
         "STRUCTURAL_APPROACH", "HIGH_EFFORT_LOW_RESULT", "LOW_EFFORT_HIGH_RESULT"],
        default="")
    idx = np.where(state != "")[0]
    if len(idx) == 0:
        return pd.DataFrame()
    return pd.DataFrame({
        "symbol": symbol, "date": d["Date"].to_numpy()[idx], "reference": ref,
        "R": r[idx], "RVOL20": rvol[idx], "ATR14": atr[idx],
        "atrpct": d["atrpct"].to_numpy(float)[idx], "result_atr": result[idx],
        "penetration": pen[idx], "closing_disp": cdisp[idx], "closing_range": cr[idx],
        "retention": ret[idx], "efficiency": d["efficiency"].to_numpy(float)[idx],
        "event_class": state[idx],
        "high_effort_low_result": (rvol[idx] >= p["high_effort_rvol"]) & (result[idx] <= p["low_result_atr"]),
        "low_effort_high_result": (rvol[idx] <= p["low_effort_rvol"]) & (result[idx] >= p["high_result_atr"]),
    })


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
