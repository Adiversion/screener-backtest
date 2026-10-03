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


def compute_industry_momentum(feat: pd.DataFrame) -> pd.DataFrame:
    """Compute equal-weight 60d return and percentile rank for all mapped industries."""
    if feat.empty or "Symbol" not in feat.columns:
        return pd.DataFrame()
    smap = get_sector_map()
    sub = feat.copy()
    sub["Industry"] = sub["Symbol"].map(smap).fillna("Diversified / Emerging")
    
    ret_col = "ret60" if "ret60" in sub.columns else ("ret20" if "ret20" in sub.columns else "Close")
    ind = sub.groupby("Industry").agg(
        symbol_count=(ret_col, "count"),
        median_ret60=(ret_col, "median"),
        mean_ret60=(ret_col, "mean"),
    ).reset_index()

    # Percentile ranking
    ind["rank_pct"] = (ind["median_ret60"].rank(pct=True) * 100).round(1)

    def _tier(pct: float) -> str:
        if pct >= 80.0:
            return "Tier 1: Leading Sector"
        elif pct >= 60.0:
            return "Tier 2: Upper Momentum"
        elif pct >= 40.0:
            return "Tier 3: Neutral / Mixed"
        return "Tier 4: Lagging Sector"

    ind["tier"] = ind["rank_pct"].apply(_tier)
    return ind.sort_values("rank_pct", ascending=False).reset_index(drop=True)


def get_symbol_industry_momentum(symbol: str, ind_df: pd.DataFrame) -> dict[str, Any]:
    """Return industry momentum details and whether it qualifies as an institutional tailwind."""
    ind = get_sector(symbol)
    if ind_df.empty or "Industry" not in ind_df.columns:
        return {"industry": ind, "rs_rank": 50.0, "tier": "Tier 3: Neutral", "is_tailwind": False, "median_ret60": 0.0}
    row = ind_df[ind_df["Industry"] == ind]
    if row.empty:
        return {"industry": ind, "rs_rank": 50.0, "tier": "Tier 3: Neutral", "is_tailwind": False, "median_ret60": 0.0}
    r = row.iloc[0]
    rank_pct = float(r["rank_pct"])
    tier = str(r["tier"])
    median_ret = round(float(r["median_ret60"]) * 100, 1)
    return {
        "industry": ind,
        "rs_rank": rank_pct,
        "tier": tier,
        "median_ret60": median_ret,
        "symbol_count": int(r["symbol_count"]),
        "is_tailwind": rank_pct >= 60.0,
    }

