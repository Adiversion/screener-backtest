"""Sector & Industry mapping and diversification engine.

Quant portfolios must avoid concentration in a single industry group to prevent
correlated drawdowns from industry-specific shocks (e.g. automotive sales dips).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SECTOR_FILE = ROOT / "data" / "sector_map.csv"

_CACHE: dict[str, str] | None = None


def get_sector_map() -> dict[str, str]:
    """Map of Symbol -> Industry (e.g. Automobile and Auto Components)."""
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    if not SECTOR_FILE.exists():
        _CACHE = {}
        return _CACHE
    df = pd.read_csv(SECTOR_FILE)
    _CACHE = dict(zip(df["Symbol"].astype(str), df["Industry"].astype(str)))
    return _CACHE


def get_sector(symbol: str) -> str:
    """Return the industry for a symbol, or 'Unknown'."""
    smap = get_sector_map()
    return smap.get(symbol.strip().upper(), "Unknown")


def apply_sector_diversification(
    picks: pd.DataFrame,
    max_per_sector: int = 1,
    top: int = 10
) -> pd.DataFrame:
    """Filter ranked picks so no single industry exceeds `max_per_sector`."""
    if picks.empty or "symbol" not in picks.columns:
        return picks
    
    smap = get_sector_map()
    sector_counts: dict[str, int] = {}
    selected_indices: list[int] = []
    
    for idx, row in picks.iterrows():
        sym = str(row["symbol"]).strip().upper()
        sec = smap.get(sym, "Unknown")
        cnt = sector_counts.get(sec, 0)
        
        # Unknown sectors are allowed, but identified sectors are capped
        if sec == "Unknown" or cnt < max_per_sector:
            sector_counts[sec] = cnt + 1
            selected_indices.append(idx)
            if len(selected_indices) >= top:
                break
                
    result = picks.loc[selected_indices].copy()
    result["industry"] = [smap.get(s, "Unknown") for s in result["symbol"]]
    return result.reset_index(drop=True)
