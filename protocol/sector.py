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
_COMPANY_CACHE: dict[str, str] | None = None


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


def get_company_map() -> dict[str, str]:
    """Map of Symbol -> Official Company Name."""
    global _COMPANY_CACHE
    if _COMPANY_CACHE is not None:
        return _COMPANY_CACHE
    _COMPANY_CACHE = {}
    master_file = ROOT / "data" / "nse_equity_master.parquet"
    if master_file.exists():
        try:
            mdf = pd.read_parquet(master_file)
            _COMPANY_CACHE.update(dict(zip(mdf["symbol"].astype(str), mdf["name"].astype(str))))
        except Exception:
            pass
    if SECTOR_FILE.exists():
        try:
            sdf = pd.read_csv(SECTOR_FILE)
            if "Company" in sdf.columns:
                _COMPANY_CACHE.update(dict(zip(sdf["Symbol"].astype(str), sdf["Company"].astype(str))))
        except Exception:
            pass
    return _COMPANY_CACHE


def get_company_name(symbol: str) -> str:
    """Return the official company name for a symbol."""
    cmap = get_company_map()
    return cmap.get(symbol.strip().upper(), symbol)


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
