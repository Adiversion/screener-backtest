"""Levels that outlive the rolling window.

The engine's longest memory is R252, a rolling 252-session high. That is a
year, and a swing high is good for considerably longer than a year -- a level
set in 2024 is still a level in 2026, and by then the rolling window has
scrolled straight past it. This module keeps the old ones.

A level is defined here purely by price. Nothing in this file claims who set
it, who took it, or why. OHLCV cannot answer those questions, and a feature
that implied it had the answers would be asserting something the data does not
contain.

    durable_high   the highest high between STALE_LO and STALE_HI sessions ago
    durable_low    the lowest low over the same span
    level_gap      how far the close sits below that old ceiling, as a fraction
    level_touch    a session inside the last TOUCH_WINDOW reached the ceiling
    level_reject   touched the ceiling recently and closed back under it
    level_break    the close is above the ceiling outright

STALE_LO deliberately starts beyond R252. A level only 252 sessions old is
already in R252, and this exists to cover what the rolling window has lost, not
to duplicate what it still holds.

Requires STALE_HI prior sessions, so a panel shorter than that yields NaN
throughout rather than a quietly wrong level. Callers are expected to report
that as a data-sufficiency limit, not to fill it in.
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


def stale_extremes(high: pd.Series, low: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Highest high and lowest low over the window that has aged out of R252.

    The window is shifted before rolling, so every value is built strictly from
    sessions that have already printed. No centred window, no forward shift.
    """
    span = STALE_HI - STALE_LO
    dh = high.groupby(level=0).shift(STALE_LO) if isinstance(high.index, pd.MultiIndex) else high.shift(STALE_LO)
    dl = low.groupby(level=0).shift(STALE_LO) if isinstance(low.index, pd.MultiIndex) else low.shift(STALE_LO)
    return dh.rolling(span, min_periods=60).max(), dl.rolling(span, min_periods=60).min()


def add_levels(df: pd.DataFrame) -> pd.DataFrame:
    """Attach the level columns in place and return the frame.

    Every column is NaN when the history is shorter than REQUIRED, so a short
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
