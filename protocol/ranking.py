"""Vectorised cross-sectional ranking for walk-forward use.

`protocol/quality.py` builds its frame one symbol at a time because it answers
a question about a single date ("what should I look at today?"). A walk-forward
rotation asks the same question about ~1400 dates, and doing it row by row costs
minutes per run.

This module computes exactly the same numbers for every date at once:
percentile components, coverage, the blended score, and the seven hard gates.
It is a performance rewrite, NOT a second definition -- `tests/test_validation.py`
asserts row-for-row agreement with `quality.score_frame` on a real panel, so a
divergence between the two fails the suite rather than quietly changing results.

Point in time is preserved: every value at date T comes from rows with
date <= T, and percentiles are taken within the date only.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from protocol import states

RAW = ("close", "reference", "rvol20", "ret20", "ret120", "atrpct", "prox52",
       "efficiency", "penetration", "turnover20", "stop_proxy", "sessions")


def edge_dates(panel: dict[str, pd.DataFrame], cfg: dict) -> dict[str, np.ndarray]:
    """Sorted RECOVERED_AFTER_REJ dates per symbol. Computed once, reused always."""
    empty = np.array([], dtype="datetime64[ns]")
    out: dict[str, np.ndarray] = {}
    for symbol, feat in panel.items():
        try:
            evs = states.find_events(feat, cfg)
        except Exception:  # one malformed symbol must not kill the walk-forward
            out[symbol] = empty
            continue
        stamps = [pd.Timestamp(e["reject_date"]) for e in evs
                  if e.get("label") == "RECOVERED_AFTER_REJ" and e.get("reject_date")]
        out[symbol] = pd.DatetimeIndex(sorted(stamps)).to_numpy() if stamps else empty
    return out


def _edge_asof(stamps: np.ndarray, dates: np.ndarray, lookback_days: int) -> np.ndarray:
    """Was the most recent reclaim event inside the lookback, on each date?"""
    if len(stamps) == 0:
        return np.zeros(len(dates))
    pos = np.searchsorted(stamps, dates, side="right")
    prev = np.where(pos > 0, stamps[np.clip(pos - 1, 0, len(stamps) - 1)],
                    np.datetime64("NaT"))
    age = (dates - prev) / np.timedelta64(1, "D")
    return np.where(np.isnat(prev) | (age > lookback_days) | (age < 0), 0.0, 1.0)


def build_long(panel: dict[str, pd.DataFrame], cfg: dict, lookback_days: int = 20
               ) -> pd.DataFrame:
    """One row per (date, symbol) with every raw field the ranking reads."""
    ref = f"R{int(cfg['pa']['reference'])}"
    edges = edge_dates(panel, cfg)
    frames = []
    for symbol, feat in panel.items():
        d = feat.reset_index(drop=True)
        dates = pd.DatetimeIndex(d["Date"]).to_numpy()
        close = pd.to_numeric(d["Close"], errors="coerce").to_numpy(float)
        r20 = pd.to_numeric(d[ref], errors="coerce").to_numpy(float)
        atr = pd.to_numeric(d["atrpct"], errors="coerce").to_numpy(float)
        ret20 = pd.to_numeric(d["ret20"], errors="coerce").to_numpy(float)
        ret120 = pd.to_numeric(d["ret120"], errors="coerce").to_numpy(float)
        # a stop distance only exists ABOVE the reference; below it the raw
        # difference is negative, which is not a tight stop (see quality.py)
        above = close > r20
        stop = np.where(above, (close - r20) / close, np.nan)
        frames.append(pd.DataFrame({
            "date": dates, "symbol": symbol,
            "sessions": np.arange(1, len(d) + 1, dtype=float),
            "close": close, "reference": r20,
            "rvol20": pd.to_numeric(d["rvol20"], errors="coerce").to_numpy(float),
            "ret20": ret20, "ret120": ret120, "atrpct": atr,
            "prox52": pd.to_numeric(d["prox52"], errors="coerce").to_numpy(float),
            "efficiency": pd.to_numeric(d["efficiency"], errors="coerce").to_numpy(float),
            "penetration": pd.to_numeric(d["penetration"], errors="coerce").to_numpy(float),
            "turnover20": pd.to_numeric(d["turnover20"], errors="coerce").to_numpy(float),
            "stop_proxy": stop,
            "trend_raw": np.where(np.isfinite(ret120), ret120 - 0.5 * ret20, np.nan),
            "edge": _edge_asof(edges.get(symbol, np.array([], dtype="datetime64[ns]")),
                               dates, lookback_days),
        }))
    if not frames:
        return pd.DataFrame(columns=["date", "symbol", *RAW, "trend_raw", "edge"])
    return pd.concat(frames, ignore_index=True)


def _gate_mask(long: pd.DataFrame, cfg: dict, coverage: pd.Series) -> pd.Series:
    """The seven hard gates, vectorised. Unknown never counts as a pass."""
    q = cfg["quality"]
    return (
        (long["turnover20"] >= float(q["min_turnover20"]))
        & (long["close"] >= float(q["min_price"]))
        & (long["ret120"] > float(q["trend_min"]))
        & (long["close"] > long["reference"])
        & (long["penetration"] > 0)
        & (long["stop_proxy"] <= float(q["max_risk_to_ref"]))
        & (long["sessions"] >= float(q["min_sessions"]))
        & (coverage >= float(q["min_coverage"]))
    )


def rank_all(long: pd.DataFrame, cfg: dict, components: dict) -> pd.DataFrame:
    """Percentile components, coverage, blended score and the gate mask.

    Percentiles are taken WITHIN each date, which is what a cross-sectional
    ranking means: a stock's 80th-percentile volatility is the 80th percentile
    of that day's universe, not of the whole history.
    """
    from protocol.quality import EDGE_WEIGHT

    out = long.sort_values(["date", "symbol"]).reset_index(drop=True)
    weights = dict(cfg["quality"]["weights"])
    num = pd.Series(0.0, index=out.index)
    den = pd.Series(float(EDGE_WEIGHT), index=out.index)
    known = pd.Series(0, index=out.index, dtype=int)
    for field, (_label, sign, _m, _w) in components.items():
        # Rank the (possibly negated) raw values exactly as quality.py does.
        # `1 - rank(x)` is NOT the same thing once there are ties, because the
        # average ranks do not complement; negating the values does.
        vals = -out[field] if sign < 0 else out[field]
        pct = vals.groupby(out["date"], sort=False).rank(pct=True, na_option="keep")
        out[field + "_pct"] = pct
        w = float(weights.get(field, 0.0))
        num += pct.fillna(0.0) * w
        den += pct.notna().astype(float) * w
        known += pct.notna().astype(int)
    out["edge"] = out["edge"].fillna(0.0)
    out["score"] = ((num + out["edge"] * EDGE_WEIGHT) / den).round(4)
    total = len(components)
    out["coverage"] = (known / total).round(4)
    out["data_status"] = np.where(out["coverage"] >= 1.0, "FULL",
                                  np.where(out["coverage"] >= float(
                                      cfg["quality"]["thin_coverage"]), "THIN",
                                  "INSUFFICIENT"))
    out["clears"] = _gate_mask(out, cfg, out["coverage"])
    return out


def best_on(ranked: pd.DataFrame, date: pd.Timestamp, exclude=()) -> pd.Series | None:
    """Highest-scoring gate-clearing candidate on `date`, or None."""
    day = ranked[ranked["date"] == np.datetime64(pd.Timestamp(date))]
    day = day[day["clears"] & ~day["symbol"].isin(list(exclude))]
    if day.empty:
        return None
    return day.sort_values(["score", "symbol"], ascending=[False, True]).iloc[0]