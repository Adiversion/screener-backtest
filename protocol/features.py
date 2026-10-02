"""A3 feature variables.

Every feature at date T is computed from rows with date <= T. Rolling
windows that reference a level (R5..R252) are shifted by one session so the
current bar is always excluded. No centred windows, no forward shifts, no
full-series normalisation.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

REF_WINDOWS = {"R5": 5, "R10": 10, "R20": 20, "R60": 60, "R252": 252}


def wilder_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    atr = tr.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    return atr


def _reference_level(high: pd.Series, window: int) -> pd.Series:
    return high.rolling(window, min_periods=window).max().shift(1)


def build_features(bars: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of `bars` (sorted by Date) with A3 feature columns."""
    df = bars.sort_values("Date").reset_index(drop=True).copy()
    close, high, low, openp = df["Close"], df["High"], df["Low"], df["Open"]
    vol = df["Volume"].astype("float64")

    df["atr14"] = wilder_atr(high, low, close)
    df["atrpct"] = df["atr14"] / close
    df["rvol20"] = vol / vol.rolling(20, min_periods=20).mean().shift(1)

    result = (close - close.shift(1))
    df["result_atr"] = result.abs() / df["atr14"]
    df["dir_result"] = result / df["atr14"]

    rng = (high - low)
    df["closing_range"] = np.where(rng > 0, (close - low) / rng, np.nan)
    df["body_eff"] = np.where(rng > 0, (close - openp) / rng, np.nan)
    df["efficiency"] = df["result_atr"] / df["rvol20"]

    for name, w in REF_WINDOWS.items():
        df[name] = _reference_level(high, w)

    r20 = df["R20"]
    df["penetration"] = (high - r20) / df["atr14"]
    df["closing_disp"] = (close - r20) / df["atr14"]
    denom = (high - r20)
    df["retention"] = np.where(denom > 0, (close - r20) / denom, np.nan)

    ema20 = close.ewm(span=20, adjust=False).mean()
    df["ema20"] = ema20
    df["extension"] = (close - ema20) / df["atr14"]
    # the recent swing low: where a stop would actually be placed, as opposed to
    # the reference high, which nobody uses as a stop because ordinary noise
    # reaches it. Computed to and including the current bar -- a stop must sit
    # below the lows that have already printed.
    df["low10"] = df["Low"].rolling(10, min_periods=10).min()


    for n in (2, 20, 60, 120):
        df[f"ret{n}"] = close / close.shift(n) - 1.0

    df["prox52"] = close / df["R252"]
    df["pos_day_freq60"] = (close > close.shift(1)).rolling(60, min_periods=60).mean()
    # ---- ranking scores for the evidence-backed strategies ----------------
    # Derived from features already computed at or before this bar, so they add
    # no lookahead. Each is monotone such that a HIGHER score always means more
    # of what the measured information coefficient says is good:
    #   atrpct IC -0.0434, prox52 +0.0344, rvol20 -0.0289,
    #   penetration -0.0174, ret20 -0.0128  (see protocol/strategies_evidence.py)
    df["calm"] = -df["atrpct"]
    df["calm_near_high"] = -df["atrpct"] * df["prox52"]
    # exhaustion: heavy participation that went deep and did not hold
    df["exhausted"] = df["rvol20"] * df["penetration"]
    df["reversal"] = -df["ret20"]

    df["turnover20"] = (close * vol).rolling(20, min_periods=20).mean()

    # Delivery / trade-count features. Available only when a delivery_history
    # file has been merged (scripts/fetch_delivery.py); otherwise they stay NA
    # so filter F4 is honestly reported as unavailable, never zero-filled.
    if "DelivPct" in df.columns and df["DelivPct"].notna().any():
        dp = pd.to_numeric(df["DelivPct"], errors="coerce") / 100.0
        df["deliv_pct"] = dp
        df["deliv_pct_rel"] = dp / dp.rolling(20, min_periods=20).mean().shift(1)
        dq = pd.to_numeric(df["DelivQty"], errors="coerce") if "DelivQty" in df.columns else pd.Series(np.nan, index=df.index)
        df["deliv_rvol20"] = dq / dq.rolling(20, min_periods=20).mean().shift(1)
        trades = pd.to_numeric(df["Trades"], errors="coerce").replace(0, np.nan) if "Trades" in df.columns else pd.Series(np.nan, index=df.index)
        df["avg_trade_size"] = vol / trades
        df["ats_rel"] = df["avg_trade_size"] / df["avg_trade_size"].rolling(20, min_periods=20).mean().shift(1)
    else:
        for col in ("deliv_pct", "deliv_rvol20", "deliv_pct_rel", "avg_trade_size", "ats_rel"):
            df[col] = np.nan
    return df


def build_panel(history: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Feature panel keyed by symbol, each frame indexed by Date."""
    panel: dict[str, pd.DataFrame] = {}
    for symbol, bars in history.groupby("Symbol", sort=False):
        feat = build_features(bars)
        panel[symbol] = feat.set_index("Date", drop=False)
    return panel
