"""Wyckoff Volume-Price Spread Analysis (VSA) & Price-Acceptance Engine.

Quantifies:
1. Richard Wyckoff's Law of Effort vs. Result (Volume vs. Candle Spread Progress).
2. Four-state Price-Acceptance (PA) machine from protocol/pa.py:
   - State A: Accepted Expansion (penetrated R, closed above R, strong retention and closing range).
   - State B: Pending Acceptance.
   - State D: Failed Acceptance / Upthrust.
3. Support & Resistance context (52-week blue-sky vs. 20-day resistance).
"""
from __future__ import annotations

from typing import Any
import pandas as pd


def evaluate_wyckoff_pa(f: pd.Series) -> dict[str, Any]:
    """Evaluate Wyckoff Effort vs Result, Closing Range, and Price Acceptance."""
    close = float(f["Close"])
    open_px = float(f["Open"]) if "Open" in f and not pd.isna(f["Open"]) else close
    high = float(f["High"])
    low = float(f["Low"])
    r20 = float(f["r20"])
    h52 = float(f["h52"])
    rvol = float(f["rvol20"])
    adr20 = float(f["adr20"]) if "adr20" in f else 0.03
    atr = max(adr20 * close, 0.01)

    rng = high - low
    cr = float((close - low) / rng) if rng > 0 else 0.5
    cr_pct = round(cr * 100, 1)

    # Penetration above 20-day resistance in ATR units
    pen_atr = round((high - r20) / atr, 2) if r20 > 0 else 0.0

    # Retention: fraction of breakout gain held at close
    if high > r20:
        ret = float((close - r20) / (high - r20))
        ret = max(0.0, min(1.0, ret))
    else:
        ret = 1.0 if close >= r20 else 0.0
    ret_pct = round(ret * 100, 1)

    above_r20 = close >= r20
    is_52w = close >= (h52 * 0.999)

    # 1. Price Acceptance State (protocol/pa.py)
    if above_r20 and cr >= 0.60 and ret >= 0.60:
        pa_state = "State A: Accepted Expansion"
        pa_badge = "STATE A ACCEPTANCE"
    elif above_r20:
        pa_state = "State B: Pending Acceptance"
        pa_badge = "STATE B EXPANSION"
    else:
        pa_state = "State D: Failed Acceptance (Upthrust)"
        pa_badge = "UPTHRUST TRAP"

    # 2. Wyckoff Effort vs. Result
    if rvol >= 2.0 and cr >= 0.65:
        wyckoff_label = "Wyckoff Absorption (High Effort → High Result)"
        wyckoff_badge = "WYCKOFF ABSORPTION"
        wyckoff_narrative = (
            f"High Effort ({rvol:.1f}x volume) met with dominant Result: closed near high of the session "
            f"(Closing Range {cr_pct}%, {ret_pct}% breakout retention). Overhead supply was aggressively absorbed."
        )
    elif rvol >= 3.0 and cr <= 0.50:
        wyckoff_label = "Effort vs Result Warning (Churn / Climax)"
        wyckoff_badge = "EFFORT VS RESULT CHURN"
        wyckoff_narrative = (
            f"Heavy Effort ({rvol:.1f}x volume) but weak Result (Closing Range only {cr_pct}%). "
            f"Upper wick indicates supply is actively hitting bids into the close."
        )
    elif rvol <= 1.0 and cr >= 0.70 and above_r20:
        wyckoff_label = "Supply Vacuum (Low Effort → Clean Glide)"
        wyckoff_badge = "SUPPLY VACUUM GLIDE"
        wyckoff_narrative = (
            f"Low Effort ({rvol:.1f}x volume) produced clean upward expansion (Closing Range {cr_pct}%). "
            f"Demonstrates complete absence of opposing overhead selling pressure."
        )
    else:
        wyckoff_label = "Balanced Breakout Expansion"
        wyckoff_badge = "BALANCED EXPANSION"
        wyckoff_narrative = (
            f"Standard breakout structure: RVOL {rvol:.1f}x, Closing Range {cr_pct}%, "
            f"holding {ret_pct}% of the move over resistance."
        )

    # 3. Support & Resistance Context (Multi-Touch Shelf vs Lone Peak)
    shelf_touches = int(f["shelf_touches_20"]) if "shelf_touches_20" in f and not pd.isna(f["shelf_touches_20"]) else 0
    badges = [pa_badge, wyckoff_badge]
    if is_52w:
        sr_type = "52-Week All-Time Resistance"
        sr_desc = f"Cleared 52-week high at ₹{h52:.2f} into zero-overhead blue sky."
    elif shelf_touches >= 2:
        sr_type = f"Multi-Touch Shelf ({shelf_touches}x Tested)"
        sr_desc = f"Decisively cleared {shelf_touches}-touch structural shelf at ₹{r20:.2f} (+{pen_atr} ATRs)."
        badges.append(f"{shelf_touches}X SHELF BREAKOUT")
    else:
        sr_type = "20-Day Swing Resistance"
        sr_desc = f"Expanded past 20-day swing ceiling at ₹{r20:.2f} (+{pen_atr} ATRs)."

    return {
        "closing_range": cr_pct,
        "retention": ret_pct,
        "penetration_atr": pen_atr,
        "shelf_touches": shelf_touches,
        "pa_state": pa_state,
        "pa_badge": pa_badge,
        "wyckoff_label": wyckoff_label,
        "wyckoff_badge": wyckoff_badge,
        "wyckoff_narrative": wyckoff_narrative,
        "sr_type": sr_type,
        "sr_desc": sr_desc,
        "badges": badges,
    }
