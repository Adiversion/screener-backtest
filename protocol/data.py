"""Price-data access layer.

Reads OHLCV history (parquet or CSV), normalises column names, sorts by
(symbol, date) and runs the data-quality checks from Part B. Delivery and
surveillance fields are simply absent in the current free data feed; when
absent they are reported as unavailable (never zero-filled).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

OHLCV = ["Open", "High", "Low", "Close", "Volume"]
_REQUIRED = ["Date", "Symbol", *OHLCV]


def _normalise(df: pd.DataFrame) -> pd.DataFrame:
    # Flatten accidental MultiIndex columns (yfinance artefacts).
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns={c: str(c).strip().title() for c in df.columns})
    missing = [c for c in _REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"history is missing required columns: {missing}")
    df = df[_REQUIRED].copy()
    df["Date"] = pd.to_datetime(df["Date"]).dt.tz_localize(None).dt.normalize()
    df["Symbol"] = df["Symbol"].astype(str).str.upper().str.strip()
    df = df.drop_duplicates(subset=["Symbol", "Date"]).sort_values(["Symbol", "Date"])
    for c in OHLCV:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.reset_index(drop=True)


def load_history(path: str | Path) -> pd.DataFrame:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"history not found: {p}")
    if p.suffix.lower() == ".csv":
        raw = pd.read_csv(p)
    else:
        raw = pd.read_parquet(p)
    return _normalise(raw)


def data_quality_report(df: pd.DataFrame) -> dict[str, Any]:
    """Fail-loud checks; returns a JSON-serialisable summary."""
    bad_hl = int((df["High"] < df["Low"]).sum())
    close_out = int(((df["Close"] < df["Low"]) | (df["Close"] > df["High"])).sum())
    missing = int(df[OHLCV].isna().sum().sum())
    zero_vol = int((df["Volume"] == 0).sum())
    dups = int(df.duplicated(subset=["Symbol", "Date"]).sum())
    non_positive = int((df[["Open", "High", "Low", "Close"]] <= 0).sum().sum())
    return {
        "rows": int(len(df)),
        "symbols": int(df["Symbol"].nunique()),
        "sessions": int(df["Date"].nunique()),
        "date_min": str(df["Date"].min().date()),
        "date_max": str(df["Date"].max().date()),
        "missing_ohlcv_cells": missing,
        "duplicate_symbol_date": dups,
        "high_less_than_low": bad_hl,
        "close_outside_range": close_out,
        "zero_volume": zero_vol,
        "non_positive_price": non_positive,
        "delivery_data_available": False,
        "surveillance_lists_available": False,
    }
