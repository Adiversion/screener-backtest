"""Corporate Events and Surveillance Integration for NSE Quant Screener.

Loads and evaluates:
1. NSE Price Band & Surveillance data (sec_list_latest.csv) for ASM/GSM & circuit limits.
2. Corporate Board Meetings / Financial Results calendar (board_meetings.csv).
3. Corporate Actions (corporate_actions.csv) for bonus, splits, and dividends.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"


@lru_cache(maxsize=1)
def load_surveillance_map() -> dict[str, dict[str, str]]:
    """Map Symbol -> {series, band, remarks}."""
    path = DATA_DIR / "sec_list_latest.csv"
    if not path.exists():
        # Fallback to any sec_list file
        candidates = list(DATA_DIR.glob("sec_list_*.csv"))
        if candidates:
            path = candidates[0]
        else:
            return {}

    try:
        df = pd.read_csv(path)
        res = {}
        for _, row in df.iterrows():
            sym = str(row.get("Symbol", "")).strip().upper()
            if not sym:
                continue
            res[sym] = {
                "series": str(row.get("Series", "EQ")).strip(),
                "band": str(row.get("Band", "20")).strip(),
                "remarks": str(row.get("Remarks", "-")).strip(),
            }
        return res
    except Exception:
        return {}


@lru_cache(maxsize=1)
def load_board_meetings_map() -> dict[str, list[dict[str, str]]]:
    """Map Symbol -> list of upcoming board meetings."""
    path = DATA_DIR / "board_meetings.csv"
    if not path.exists():
        return {}
    try:
        df = pd.read_csv(path)
        res: dict[str, list[dict[str, str]]] = {}
        for _, row in df.iterrows():
            sym = str(row.get("bm_symbol", "")).strip().upper()
            if not sym:
                continue
            entry = {
                "date": str(row.get("bm_date", "")).strip(),
                "purpose": str(row.get("bm_purpose", "")).strip(),
                "desc": str(row.get("bm_desc", "")).strip(),
            }
            res.setdefault(sym, []).append(entry)
        return res
    except Exception:
        return {}


@lru_cache(maxsize=1)
def load_corporate_actions_map() -> dict[str, list[dict[str, str]]]:
    """Map Symbol -> list of corporate actions."""
    path = DATA_DIR / "corporate_actions.csv"
    if not path.exists():
        return {}
    try:
        df = pd.read_csv(path)
        res: dict[str, list[dict[str, str]]] = {}
        for _, row in df.iterrows():
            sym = str(row.get("symbol", "")).strip().upper()
            if not sym:
                continue
            entry = {
                "ex_date": str(row.get("exDate", "")).strip(),
                "subject": str(row.get("subject", "")).strip(),
            }
            res.setdefault(sym, []).append(entry)
        return res
    except Exception:
        return {}


def get_corporate_audit(
    symbol: str,
    sector: str = "",
    is_extended: bool = False,
    ema10: float = 0.0,
) -> dict[str, Any]:
    """Generate regulatory surveillance check and corporate event audit."""
    sym = symbol.strip().upper()
    surv_map = load_surveillance_map()
    bm_map = load_board_meetings_map()
    ca_map = load_corporate_actions_map()

    surv = surv_map.get(sym, {"series": "EQ", "band": "20", "remarks": "-"})
    series = surv.get("series", "EQ")
    band = surv.get("band", "20")
    remarks = surv.get("remarks", "-")

    badges: list[str] = []
    warnings: list[str] = []

    # 1. Surveillance checks
    is_t2t = series in ("BE", "BZ", "ST")
    if is_t2t:
        badges.append(f"⚠️ {series} SERIES (T2T DELIVERY ONLY)")
        warnings.append(f"Series {series} requires 100% upfront delivery margin (no intraday squaring allowed).")

    if band in ("2", "5"):
        badges.append(f"CIRCUIT CAP: {band}%")
        warnings.append(f"Tight {band}% daily circuit limit poses high liquidity and lock-in risk.")
    elif band == "10":
        badges.append("CIRCUIT: 10%")

    if "GSM" in remarks:
        badges.append(f"🚨 {remarks}")
        warnings.append(f"Under SEBI/NSE Graded Surveillance Measure ({remarks}). High risk.")

    # 2. Board Meetings / Earnings Blackout
    meetings = bm_map.get(sym, [])
    has_earnings = False
    for m in meetings:
        dt = m.get("date", "")
        purp = m.get("purpose", "")
        if "financial" in purp.lower() or "result" in purp.lower():
            has_earnings = True
            badges.append(f"⚠️ EARNINGS: {dt}")
            warnings.append(f"Board meeting on {dt} for quarterly financial results. High gap-down risk.")
        else:
            warnings.append(f"Board meeting on {dt}: {purp}.")

    # 3. Corporate Actions
    actions = ca_map.get(sym, [])
    for a in actions:
        ex = a.get("ex_date", "")
        sub = a.get("subject", "")
        badges.append(f"📢 {sub[:15]} ({ex})")
        warnings.append(f"Corporate action: {sub} (Ex-Date: {ex}).")

    # 4. Sector / Extension contextual notes
    if "Automobile" in sector:
        warnings.append("Auto monthly dispatch figures print on 1st of month (exercise caution).")
    if is_extended:
        warnings.append(f"Stock extended >20% above 50 SMA; wait for pullback toward 10 EMA (₹{ema10:.2f}).")

    if not warnings:
        warnings.append("Clear event horizon: No immediate corporate results or surveillance restrictions.")

    return {
        "series": series,
        "circuit_band": band,
        "surveillance_remarks": remarks,
        "is_t2t": is_t2t,
        "has_earnings_soon": has_earnings,
        "badges": badges,
        "warning_text": " ".join(warnings),
        "board_meetings": meetings,
        "corporate_actions": actions,
    }
