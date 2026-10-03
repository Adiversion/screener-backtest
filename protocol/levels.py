"""Levels that outlive the rolling window & Multi-Touch Structural Shelves.

The engine's longest memory is R252, a rolling 252-session high. That is a
year, and a swing high is good for considerably longer than a year -- a level
set in 2024 is still a level in 2026, and by then the rolling window has
scrolled straight past it. This module keeps the old ones.

In addition to multi-year extremes, this module provides:
1. Multi-touch consolidation shelf detection (distinguishing multi-touch bases
   from lone aberration wicks).
2. ATR-normalized breakout clearance (filtering out intraday friction & whipsaws).
3. Structural base invalidation stops (anchoring risk to the true consolidation floor).

All features are strictly causal: computed from past printed bars with zero lookahead.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# 260, not 250: R252 already covers the most recent 252 sessions, so a window
# starting at 250 would overlap it by two sessions and quietly double-count
# those highs. The gap is deliberate and a test enforces it.
STALE_LO = 260
STALE_HI = 760
TOUCH_WINDOW = 3
REQUIRED = STALE_HI
CLEARANCE_ATR_HURDLE = 0.20
SHELF_TOLERANCE_ATR = 0.75


def stale_extremes(high: pd.Series, low: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Highest high and lowest low over the window that has aged out of R252.

    The window is shifted before rolling, so every value is built strictly from
    sessions that have already printed. No centred window, no forward shift.
    """
    span = STALE_HI - STALE_LO
    dh = high.groupby(level=0).shift(STALE_LO) if isinstance(high.index, pd.MultiIndex) else high.shift(STALE_LO)
    dl = low.groupby(level=0).shift(STALE_LO) if isinstance(low.index, pd.MultiIndex) else low.shift(STALE_LO)
    return dh.rolling(span, min_periods=60).max(), dl.rolling(span, min_periods=60).min()


def _ensure_atr(df: pd.DataFrame, close: pd.Series, high: pd.Series, low: pd.Series) -> pd.Series:
    """Return existing atr14 if available, or compute a causal rolling ATR fallback."""
    if "atr14" in df.columns and df["atr14"].notna().any():
        return df["atr14"].astype(float)
    prev_close = close.shift(1)
    tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    return tr.rolling(14, min_periods=1).mean()


def add_levels(df: pd.DataFrame) -> pd.DataFrame:
    """Attach the level and structural shelf columns in place and return the frame.

    Every durable column is NaN when the history is shorter than REQUIRED, so a short
    panel produces a visible absence rather than a plausible-looking number.
    """
    close, high, low = df["Close"], df["High"], df["Low"]
    durable_high, durable_low = stale_extremes(high, low)
    df["durable_high"] = durable_high
    df["durable_low"] = durable_low
    # Positive when the close is below the old ceiling, negative once it is
    # through it. This is the same sign convention as prox52 so the two can be
    # compared without flipping one of them.
    df["level_gap"] = close / durable_high - 1.0
    df["level_width"] = (durable_high - durable_low) / durable_low

    recent_high = high.rolling(TOUCH_WINDOW, min_periods=1).max()
    recent_low = low.rolling(TOUCH_WINDOW, min_periods=1).min()
    df["level_touch"] = (recent_high >= durable_high).astype(float)
    df["level_support_touch"] = (recent_low <= durable_low).astype(float)
    # A touch only counts as a rejection if the close finished back under the
    # level. Touching and holding above is a different event and is labelled
    # separately rather than being folded in.
    df["level_reject"] = ((recent_high >= durable_high) & (close < durable_high)).astype(float)
    df["level_break"] = (close > durable_high).astype(float)
    df["level_sufficient"] = float(len(df) >= REQUIRED)

    # ---- Reinforced S/R: Clearance, Multi-Touch Shelves, & Structural Stops ----
    atr = _ensure_atr(df, close, high, low)
    # 1. Durable level clearance in ATR units & confirmed breakout flag
    df["level_clearance_atr"] = (close - durable_high) / atr
    df["durable_break_confirmed"] = (
        (close > durable_high) & (df["level_clearance_atr"] >= CLEARANCE_ATR_HURDLE)
    ).astype(float)

    # 2. Multi-Touch Resistance Shelf (tested on 20-day horizon shifted by 1)
    r20 = df["R20"] if "R20" in df.columns else high.rolling(20, min_periods=10).max().shift(1)
    shelf_band_lo = r20 - SHELF_TOLERANCE_ATR * atr
    near_ceiling = ((high >= shelf_band_lo) & (high <= (r20 + 0.5 * atr))).astype(float)
    # Count touches in the prior 20 sessions (shifted by 1 so today's candle doesn't count as history)
    df["shelf_touches_20"] = near_ceiling.rolling(20, min_periods=5).sum().shift(1).fillna(0.0)
    df["is_shelf_r20"] = (df["shelf_touches_20"] >= 2.0).astype(float)

    # Clearance above R20 in ATR units & confirmed expansion
    df["r20_clearance_atr"] = (close - r20) / atr
    df["r20_break_confirmed"] = (
        (close > r20) & (df["r20_clearance_atr"] >= CLEARANCE_ATR_HURDLE)
    ).astype(float)

    # 3. Structural Invalidation Base Stop (the floor of the 20-day base minus 0.5 ATR buffer)
    base_low20 = low.rolling(20, min_periods=10).min().shift(1)
    df["base_low20"] = base_low20
    df["base_stop_level"] = base_low20 - 0.5 * atr
    df["base_stop_pct"] = np.where(close > 0, (close - df["base_stop_level"]) / close, np.nan)

    return df


def sufficiency(n_sessions: int) -> dict[str, object]:
    """What the level block can and cannot say, given a history length."""
    if n_sessions >= REQUIRED:
        return {"ok": True, "sessions": n_sessions, "required": REQUIRED,
                "note": f"durable levels available back to {STALE_LO} sessions"}
    return {"ok": False, "sessions": n_sessions, "required": REQUIRED,
            "note": f"history is {REQUIRED - n_sessions} sessions short of the "
                    f"{REQUIRED} needed for a level older than R252; columns are "
                    f"NaN, not estimated"}
