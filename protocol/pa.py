"""Price-Acceptance (PA) discrete state machine.

Implements the four non-overlapping behavioural states from
"Price Acceptance Strategy Origins" (lineage/taxonomy/audit of the
Pressure-Response-Acceptance framework):

  A_ACCEPTED_EXPANSION          penetrated R, closed above R, strong
                                retention AND strong closing range.
  B_PENDING_ACCEPTANCE          penetrated R, closed above R, but retention
                                or closing range not yet confirmed.
  C_REJECTION_RECOVERY_PENDING  penetrated R, closed slightly below R with a
                                still-decent close -> recovery pending.
  D_FAILED_ACCEPTANCE           penetrated R, surrendered it and closed near
                                the session low -> structural failure.

Every field at session T is computed from rows date <= T (see features.py);
the state is therefore knowable at the 15:30 IST close with no lookahead.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

STATES = ("A_ACCEPTED_EXPANSION", "B_PENDING_ACCEPTANCE",
          "C_REJECTION_RECOVERY_PENDING", "D_FAILED_ACCEPTANCE")


_COLUMNS = ["symbol", "date", "state", "reference", "R", "RVOL20", "ATR14",
            "result_atr", "penetration", "closing_disp", "closing_range",
            "retention", "efficiency"]


def classify_states(feat: pd.DataFrame, cfg: dict, symbol: str | None = None) -> pd.DataFrame:
    """One row per classified session (vectorised); data through T only."""
    p = cfg["pa"]
    ref = f"R{int(p['reference'])}"
    d = feat.reset_index(drop=True)
    if symbol is None and "Symbol" in d.columns and len(d):
        symbol = str(d["Symbol"].iloc[0])
    if d.empty:
        return pd.DataFrame(columns=_COLUMNS)
    r = d[ref].to_numpy(float)
    atr = d["atr14"].to_numpy(float)
    high, low, close = d["High"].to_numpy(float), d["Low"].to_numpy(float), d["Close"].to_numpy(float)
    rvol = d["rvol20"].to_numpy(float)
    rng = high - low
    with np.errstate(divide="ignore", invalid="ignore"):
        pen = (high - r) / atr
        cdisp = (close - r) / atr
        cr = np.where(rng > 0, (close - low) / rng, np.nan)
        denom = high - r
        ret = np.where(denom > 0, (close - r) / denom, np.nan)
    valid = (~np.isnan(r)) & (~np.isnan(atr)) & (atr > 0) & liquid_mask(d, cfg).to_numpy()
    hit = valid & (pen > p["penetration_min"]) & (~np.isnan(rvol)) & (rvol >= p["rvol_min"])
    above = close > r
    state = np.select(
        [hit & above & (ret >= p["accepted_retention"]) & (cr >= p["accepted_closing_range"]),
         hit & above,
         hit & (~above) & (cdisp > p["rejection_disp_atr"]) & (cr >= p["rejection_closing_range"])],
        ["A_ACCEPTED_EXPANSION", "B_PENDING_ACCEPTANCE", "C_REJECTION_RECOVERY_PENDING"],
        default="D_FAILED_ACCEPTANCE")
    idx = np.where(hit)[0]
    if len(idx) == 0:
        return pd.DataFrame(columns=_COLUMNS)
    return pd.DataFrame({
        "symbol": symbol, "date": d["Date"].to_numpy()[idx], "state": state[idx],
        "reference": ref, "R": r[idx], "RVOL20": rvol[idx], "ATR14": atr[idx],
        "result_atr": d["result_atr"].to_numpy(float)[idx], "penetration": pen[idx],
        "closing_disp": cdisp[idx], "closing_range": cr[idx], "retention": ret[idx],
        "efficiency": d["efficiency"].to_numpy(float)[idx],
    })


def liquid_mask(feat: pd.DataFrame, cfg: dict) -> pd.Series:
    """PDF liquidity gate: >= min 20d turnover, price > min, enough history."""
    lq = cfg.get("liquidity") or {}
    d = feat.reset_index(drop=True)
    mask = pd.Series(True, index=d.index)
    if "min_sessions" in lq:
        mask &= pd.Series(np.arange(len(d)) >= int(lq["min_sessions"]), index=d.index)
    if "min_turnover20" in lq and "turnover20" in d:
        mask &= d["turnover20"].fillna(0.0).to_numpy() >= float(lq["min_turnover20"])
    if "min_price" in lq and "Close" in d:
        mask &= d["Close"].to_numpy() >= float(lq["min_price"])
    return mask


def run_state_study(panel: dict[str, pd.DataFrame], cfg: dict) -> dict[str, Any]:
    """Classify every symbol, attach forward T+n outcomes, summarise by state."""
    from protocol import pra  # reuse the sibling event-study outcome engine

    frames = []
    for symbol, feat in panel.items():
        events = classify_states(feat, cfg, symbol)
        if events.empty:
            continue
        frames.append(pra.attach_outcomes(feat, events, cfg))
    events = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if events.empty:
        return {"events": events, "outcomes": pd.DataFrame()}
    outcomes = pra.outcome_table(events.rename(columns={"state": "event_class"}), cfg)
    return {"events": events, "outcomes": outcomes}
