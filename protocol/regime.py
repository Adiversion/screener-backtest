"""Market Regime & Breadth Engine.

Quant systems must never initiate aggressive momentum/breakout positions
when the broader market is in distribution or below structural moving averages.

Evaluates:
  1. Equal-Weight Universe Index vs 20-day and 50-day SMA.
  2. Market Breadth: fraction of universe symbols above their 20-day & 50-day SMA.
  3. Regime classification:
     - BULL: Index > SMA20 and Breadth(SMA50) >= 50%
     - NEUTRAL: Index > SMA50 or Breadth between 40% and 50%
     - DEFENSIVE: Index < SMA20 and Breadth(SMA20) < 45% (Shift to CASH)
"""
from __future__ import annotations

from typing import Any
import numpy as np
import pandas as pd


def compute_market_regime(history: pd.DataFrame) -> pd.DataFrame:
    """Compute market benchmark index, moving averages, and breadth."""
    df = history.sort_values("Date").copy()
    
    # 1. Equal-weight universe daily mean close
    agg = df.groupby("Date").agg(
        ew_close=("Close", "mean"),
        total_symbols=("Symbol", "count")
    ).reset_index()
    
    agg["sma20"] = agg["ew_close"].rolling(20, min_periods=20).mean()
    agg["sma50"] = agg["ew_close"].rolling(50, min_periods=50).mean()
    
    # 2. Per-symbol SMA20 & SMA50 for breadth
    df["sym_sma20"] = df.groupby("Symbol")["Close"].transform(
        lambda s: s.rolling(20, min_periods=20).mean()
    )
    df["sym_sma50"] = df.groupby("Symbol")["Close"].transform(
        lambda s: s.rolling(50, min_periods=50).mean()
    )
    df["above_sma20"] = (df["Close"] > df["sym_sma20"]).astype(float)
    df["above_sma50"] = (df["Close"] > df["sym_sma50"]).astype(float)
    
    breadth = df.groupby("Date").agg(
        pct_above_sma20=("above_sma20", "mean"),
        pct_above_sma50=("above_sma50", "mean")
    ).reset_index()
    
    mkt = agg.merge(breadth, on="Date")
    mkt["trend_20"] = mkt["ew_close"] > mkt["sma20"]
    mkt["trend_50"] = mkt["ew_close"] > mkt["sma50"]
    
    def _classify(row: pd.Series) -> str:
        if pd.isna(row["sma20"]) or pd.isna(row["pct_above_sma20"]):
            return "NEUTRAL"
        if (not row["trend_20"]) and row["pct_above_sma20"] < 0.45:
            return "DEFENSIVE"
        if row["trend_20"] and row["trend_50"] and row["pct_above_sma50"] >= 0.50:
            return "BULL"
        return "NEUTRAL"
        
    mkt["regime"] = mkt.apply(_classify, axis=1)
    return mkt


def get_regime_at(history: pd.DataFrame, asof: pd.Timestamp) -> dict[str, Any]:
    """Retrieve market regime state on or immediately before `asof`."""
    asof = pd.Timestamp(asof)
    upto = history[history["Date"] <= asof]
    if upto.empty:
        return {
            "date": str(asof.date()),
            "regime": "UNKNOWN",
            "is_risk_on": False,
            "action": "CASH",
            "message": "No historical market data available on or before date.",
        }
        
    mkt = compute_market_regime(upto)
    if mkt.empty:
        return {
            "date": str(asof.date()),
            "regime": "UNKNOWN",
            "is_risk_on": False,
            "action": "CASH",
            "message": "Insufficient data to compute regime.",
        }
        
    last = mkt.iloc[-1]
    regime = str(last["regime"])
    is_risk_on = regime in ("BULL", "NEUTRAL")
    action = "ALLOCATE" if regime == "BULL" else "REDUCE" if regime == "NEUTRAL" else "CASH"
    
    p20 = round(float(last["pct_above_sma20"]) * 100, 1) if pd.notna(last["pct_above_sma20"]) else 0.0
    p50 = round(float(last["pct_above_sma50"]) * 100, 1) if pd.notna(last["pct_above_sma50"]) else 0.0
    
    if regime == "DEFENSIVE":
        msg = (f"Market is in DEFENSIVE regime: Universe index is below 20-day SMA "
               f"and breadth is weak ({p20}% above SMA20). Capital protection (CASH) recommended.")
    elif regime == "BULL":
        msg = (f"Market is in BULL regime: Universe index is above 20d & 50d SMA "
               f"with healthy breadth ({p50}% above SMA50). Full allocation permitted.")
    else:
        msg = (f"Market is in NEUTRAL/CHOPPY regime: Breadth is mixed ({p20}% above SMA20). "
               f"Cautious sizing recommended.")
               
    return {
        "date": str(pd.Timestamp(last["Date"]).date()),
        "regime": regime,
        "ew_close": round(float(last["ew_close"]), 2),
        "sma20": round(float(last["sma20"]), 2) if pd.notna(last["sma20"]) else None,
        "sma50": round(float(last["sma50"]), 2) if pd.notna(last["sma50"]) else None,
        "pct_above_sma20": p20,
        "pct_above_sma50": p50,
        "is_risk_on": is_risk_on,
        "action": action,
        "message": msg,
    }
