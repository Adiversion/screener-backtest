"""End-of-day candidate screen.

Classifies every symbol's most recent session into human-readable buckets so
the engine can answer "which stocks are worth looking at today?":

  ORGANIC    accepted expansion with contained volume -> genuine demand
  PENDING    accepted expansion but effort/close not confirmed yet
  TRAP_RISK  failed acceptance, or a climactic exhaustion spike
  REJECTED   penetration that closed back below the reference
  NO_SETUP   no structural event on the session
  ILLIQUID   fails the turnover/price/session gate

Every tag is derived from data through the session close only (no lookahead);
the ranking is a frozen, configurable heuristic, not a tuned fit.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from protocol import pa

TAGS = ("ORGANIC", "PENDING", "TRAP_RISK", "REJECTED", "NO_SETUP", "ILLIQUID")


def _num(v: Any) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if np.isnan(f) else round(f, 4)


def tag_state(state: str | None, rvol: float | None, cr: float | None, cfg: dict) -> str:
    sc = cfg["screen"]
    if state == "A_ACCEPTED_EXPANSION":
        if (rvol is not None and rvol >= sc["trap_rvol_min"]
                and cr is not None and cr <= sc["trap_closing_range_max"]):
            return "TRAP_RISK"
        return "ORGANIC" if (rvol is not None and rvol <= sc["organic_rvol_max"]) else "PENDING"
    if state == "B_PENDING_ACCEPTANCE":
        return "PENDING"
    if state == "D_FAILED_ACCEPTANCE":
        return "TRAP_RISK"
    if state == "C_REJECTION_RECOVERY_PENDING":
        return "REJECTED"
    return "NO_SETUP"


def screen(panel: dict[str, pd.DataFrame], cfg: dict, asof: pd.Timestamp) -> pd.DataFrame:
    """One row per symbol for the latest session on/before `asof`."""
    asof = pd.Timestamp(asof)
    stale = int(cfg["screen"]["stale_days"])
    rows: list[dict[str, Any]] = []
    for symbol, feat in panel.items():
        d = feat.reset_index(drop=True)
        if d.empty:
            continue
        upto = d[d["Date"] <= asof]
        if upto.empty:
            continue
        i = len(upto) - 1
        day = upto["Date"].iloc[i]
        if (asof - day).days > stale:
            continue
        row = upto.iloc[i]
        liquid = bool(pa.liquid_mask(d, cfg).iloc[i])
        states = pa.classify_states(feat, cfg, symbol)
        state = None
        if not states.empty:
            hit = states[states["date"] == day]
            if not hit.empty:
                state = str(hit["state"].iloc[0])
        rvol = _num(row["rvol20"])
        cr = _num(row["closing_range"])
        close = _num(row["Close"])
        ref = _num(row[f"R{int(cfg['pa']['reference'])}"])
        tag = "ILLIQUID" if not liquid else tag_state(state, rvol, cr, cfg)
        rv = _num(row["ret2"])
        stop_proxy = round((close - ref) / close, 4) if (close and ref) else None
        rows.append({
            "symbol": symbol, "date": str(day.date()), "tag": tag, "state": state,
            "close": close, "reference": ref, "rvol20": rvol,
            "closing_range": cr, "retention": _num(row["retention"]),
            "penetration": _num(row["penetration"]), "result_atr": _num(row["result_atr"]),
            "ret2": rv, "stop_proxy": stop_proxy,
            "turnover20": _num(row["turnover20"]),
        })
    return pd.DataFrame(rows)


def rank_candidates(rows: pd.DataFrame, cfg: dict, top: int = 1) -> pd.DataFrame:
    """ORGANIC candidates whose risk-to-reference is inside the protocol's
    stop-distance limit, least-extended and best-retained first."""
    if rows.empty or "tag" not in rows.columns:
        return rows.iloc[0:0] if not rows.empty else rows
    cand = rows[rows["tag"] == "ORGANIC"].copy()
    if cand.empty:
        return cand
    max_risk = float(cfg["state2"]["stop_distance_max"])
    risk = pd.to_numeric(cand["stop_proxy"], errors="coerce")
    cand = cand[risk.isna() | (risk <= max_risk)]
    if cand.empty:
        return cand
    cand = cand.sort_values(by=["penetration", "retention"], ascending=[True, False])
    cand["rank"] = range(1, len(cand) + 1)
    return cand.head(max(top, 1))


def story(rows: pd.DataFrame, cfg: dict) -> list[str]:
    """Plain-English summary of the session's candidate board."""
    if rows.empty:
        return ["No symbols had a usable session in the window."]
    counts = rows["tag"].value_counts().to_dict()
    lines = [
        f"Session scanned: {rows['date'].max()} over {len(rows)} symbols.",
        "  ".join(f"{t}={counts.get(t, 0)}" for t in TAGS),
    ]
    picks = rank_candidates(rows, cfg, top=3)
    if picks.empty:
        lines.append("Watchlist: empty - no ORGANIC candidate cleared the gates today.")
    else:
        best = picks.iloc[0]
        lines.append(
            f"Top candidate: {best['symbol']} (close {best['close']}, "
            f"reference {best['reference']}, RVOL20 {best['rvol20']}, "
            f"retention {best['retention']}, risk-to-ref {best['stop_proxy']}).")
        others = ", ".join(picks["symbol"].tolist()[1:]) or "none"
        lines.append(f"Backups: {others}")
    traps = rows[rows["tag"] == "TRAP_RISK"]
    if not traps.empty:
        lines.append("Avoid (trap risk): " + ", ".join(traps["symbol"].head(8).tolist()))
    return lines
