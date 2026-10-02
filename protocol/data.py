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
_OPTIONAL = ["DelivPct", "DelivQty", "Trades"]  # present only when delivery data is merged

# Explicit alias map, so "DelivPct" does not become "Delivpct" under .title().
_ALIASES = {
    "date": "Date", "symbol": "Symbol",
    "open": "Open", "open_price": "Open",
    "high": "High", "high_price": "High",
    "low": "Low", "low_price": "Low",
    "close": "Close", "close_price": "Close",
    "volume": "Volume", "ttl_trd_qnty": "Volume",
    "trades": "Trades", "no_of_trades": "Trades",
    "delivpct": "DelivPct", "deliv_pct": "DelivPct",
    "delivper": "DelivPct", "deliv_per": "DelivPct",
    "delivqty": "DelivQty", "deliv_qty": "DelivQty",
}


def _normalise(df: pd.DataFrame) -> pd.DataFrame:
    # Flatten accidental MultiIndex columns (yfinance artefacts).
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns={c: _ALIASES.get(str(c).strip().lower(), str(c).strip())
                            for c in df.columns})
    missing = [c for c in _REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"history is missing required columns: {missing}")
    keep = _REQUIRED + [c for c in _OPTIONAL if c in df.columns]
    df = df[keep].copy()
    df["Date"] = pd.to_datetime(df["Date"]).dt.tz_localize(None).dt.normalize()
    df["Symbol"] = df["Symbol"].astype(str).str.upper().str.strip()
    df = df.drop_duplicates(subset=["Symbol", "Date"]).sort_values(["Symbol", "Date"])
    for c in OHLCV:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.reset_index(drop=True)


def load_history(path: str | Path, delivery: str | Path | bool | None = None) -> pd.DataFrame:
    """Load OHLCV and, if a sibling data/delivery_history.parquet exists, merge it.

    Merge is automatic (pass `delivery=False` to disable, or a path to override).
    Without delivery columns the delivery features are simply NaN and filter F4
    stays unavailable — never zero-filled.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"history not found: {p}")
    raw = pd.read_csv(p) if p.suffix.lower() == ".csv" else pd.read_parquet(p)
    df = _normalise(raw)
    return attach_delivery(df, p, delivery)


def attach_delivery(df: pd.DataFrame, path: str | Path,
                    delivery: str | Path | bool | None = None) -> pd.DataFrame:
    if delivery is False:
        return df
    dpath = Path(delivery) if isinstance(delivery, (str, Path)) else Path(path).parent / "delivery_history.parquet"
    if not Path(dpath).exists():
        return df
    d = pd.read_parquet(dpath)
    d = d.rename(columns={c: _ALIASES.get(str(c).strip().lower(), str(c).strip())
                          for c in d.columns})
    if not {"Symbol", "Date"} <= set(d.columns):
        return df
    d["Date"] = pd.to_datetime(d["Date"]).dt.tz_localize(None).dt.normalize()
    d["Symbol"] = d["Symbol"].astype(str).str.upper().str.strip()
    cols = [c for c in _OPTIONAL if c in d.columns]
    if not cols:
        return df
    d = d[["Symbol", "Date", *cols]].drop_duplicates(subset=["Symbol", "Date"])
    return df.merge(d, on=["Symbol", "Date"], how="left")


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
        "delivery_data_available": bool("DelivPct" in df.columns
                                        and df["DelivPct"].notna().any()),
        "delivery_rows": int(df["DelivPct"].notna().sum()) if "DelivPct" in df.columns else 0,
        "surveillance_lists_available": False,
    }
