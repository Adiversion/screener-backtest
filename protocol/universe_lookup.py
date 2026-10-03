"""Universal NSE Stock Inspector & Diagnostics Engine.

Allows looking up ANY stock in the active universe from the search bar,
providing immediate technical diagnostics, Wyckoff price acceptance status,
and explicit reasons why it did or did not qualify for today's active setups.
"""
from __future__ import annotations

from typing import Any
import pandas as pd

from protocol.sector import get_company_name, get_sector


def build_universe_lookup(
    feat: pd.DataFrame,
    candidates: dict[str, Any],
    deliv_map: dict[str, float] | None = None
) -> dict[str, dict[str, Any]]:
    """Build compact diagnostic record for every active symbol in the universe."""
    deliv_map = deliv_map or {}
    lookup: dict[str, dict[str, Any]] = {}

    for _, row in feat.iterrows():
        sym = str(row["Symbol"])
        close = float(row["Close"])
        high = float(row["High"])
        r20 = float(row["r20"])
        h52 = float(row["h52"])
        sma50 = float(row["sma50"])
        sma200 = float(row["sma200"])
        rvol = float(row["rvol20"])
        rs = float(row["rs_rating"]) if "rs_rating" in row and not pd.isna(row["rs_rating"]) else 50.0
        dp = deliv_map.get(sym, 0.0)

        is_cand = sym in candidates

        if is_cand:
            status = "QUALIFIED_SETUP"
            strats = candidates[sym].get("strategies", [])
            why = f"Qualified setup across {len(strats)} frameworks: " + ", ".join(strats)
        else:
            reasons = []
            if close < r20:
                if high >= r20:
                    reasons.append(f"Intraday upthrust: High reached ₹{high:.2f} but closed back at ₹{close:.2f} below 20d ceiling (₹{r20:.2f})")
                else:
                    reasons.append(f"Below 20d resistance (₹{r20:.2f}, -{((r20 - close) / r20) * 100:.1f}%)")
            if rvol < 1.2:
                reasons.append(f"Volume below hurdle ({rvol:.2f}x vs 1.20x min)")
            if close <= sma50 or sma50 <= sma200:
                reasons.append("Trend misaligned: Not in confirmed Stage 2 uptrend")
            if float(row.get("ext_sma50", 0.0)) > 0.25:
                reasons.append(f"Overextended +{float(row['ext_sma50']) * 100:.1f}% above 50 SMA (>25% limit)")

            status = "WATCHLIST_NO_BREAKOUT" if (close > sma50 and sma50 > sma200) else "STAGE_4_LAGGARD"
            why = "; ".join(reasons) if reasons else "No active breakout trigger today"

        lookup[sym] = {
            "symbol": sym,
            "company": get_company_name(sym),
            "sector": get_sector(sym),
            "close": round(close, 2),
            "high": round(high, 2),
            "r20": round(r20, 2),
            "h52": round(h52, 2),
            "sma50": round(sma50, 2),
            "sma200": round(sma200, 2),
            "stage2": bool(close > sma50 and sma50 > sma200),
            "rvol": round(rvol, 2),
            "rs": round(rs, 1),
            "deliv": round(dp, 1),
            "status": status,
            "is_cand": is_cand,
            "why": why,
        }

    return lookup
