"""Universal NSE Stock Inspector & Deep Forensic Diagnostics Engine.

Allows looking up ANY stock in the active universe from the search bar,
providing deep Wyckoff auction anatomy, 7-framework pass/fail checklists,
and explicit actionable gameplans explaining why it did or did not qualify.
"""
from __future__ import annotations

from typing import Any
import numpy as np
import pandas as pd

from protocol.sector import get_company_name, get_sector


def build_universe_lookup(
    feat: pd.DataFrame,
    candidates: dict[str, Any],
    deliv_map: dict[str, float] | None = None
) -> dict[str, dict[str, Any]]:
    """Build deep forensic diagnostic record for every active symbol in the universe."""
    deliv_map = deliv_map or {}
    lookup: dict[str, dict[str, Any]] = {}

    for _, row in feat.iterrows():
        sym = str(row["Symbol"])
        close = float(row["Close"])
        open_px = float(row["Open"]) if "Open" in row and not pd.isna(row["Open"]) else close
        high = float(row["High"])
        low = float(row["Low"])
        r10 = float(row["r10"]) if "r10" in row else high
        r20 = float(row["r20"]) if "r20" in row else high
        h52 = float(row["h52"]) if "h52" in row else high
        l52 = float(row["l52"]) if "l52" in row else low
        ema10 = float(row["ema10"]) if "ema10" in row else close
        ema20 = float(row["ema20"]) if "ema20" in row else close
        sma50 = float(row["sma50"]) if "sma50" in row else close
        sma150 = float(row["sma150"]) if "sma150" in row else close
        sma200 = float(row["sma200"]) if "sma200" in row else close
        rvol = float(row["rvol20"]) if "rvol20" in row else 1.0
        rvol50 = float(row["rvol50"]) if "rvol50" in row else rvol
        rs = float(row["rs_rating"]) if "rs_rating" in row and not pd.isna(row["rs_rating"]) else 50.0
        adr20 = float(row["adr20"]) if "adr20" in row else 0.03
        ext50 = float(row.get("ext_sma50", 0.0))
        dp = float(deliv_map.get(sym, 0.0))

        # Wyckoff candle calculations
        rng = high - low
        cr = float((close - low) / rng) if rng > 0 else 0.5
        ret = float((close - r20) / (high - r20)) if high > r20 else (1.0 if close >= r20 else 0.0)
        ret = max(0.0, min(1.0, ret))
        atr = max(adr20 * close, 0.01)

        is_cand = sym in candidates

        # 7-Framework Rejection Audit
        frameworks: list[dict[str, Any]] = []

        # 1. CANSLIM
        c_pass = (close > sma50 > sma200) and (close >= 0.85 * h52) and (close > r20) and (rvol50 >= 1.4) and (rs >= 70.0)
        c_reasons = []
        if close <= r20:
            c_reasons.append(f"Closed ₹{(r20 - close):.1f} below 20d resistance (₹{r20:.1f})")
        if rvol50 < 1.4:
            c_reasons.append(f"Volume surge {rvol50:.2f}x < 1.40x hurdle")
        if rs < 70.0:
            c_reasons.append(f"RS Rating {rs:.0f} < 70")
        frameworks.append({
            "name": "CANSLIM Pivot",
            "passed": bool(c_pass),
            "verdict": "Qualified Breakout" if c_pass else "; ".join(c_reasons)
        })

        # 2. Minervini SEPA
        m_pass = (close > sma150 > sma200) and (sma50 > sma150) and (close > sma50) and (close > r20) and (ext50 <= 0.25)
        m_reasons = []
        if close <= r20:
            m_reasons.append(f"Failed to clear 20d pivot high at ₹{r20:.1f}")
        if ext50 > 0.25:
            m_reasons.append(f"Overextended +{ext50 * 100:.1f}% > 25% from 50 SMA")
        if close <= sma50:
            m_reasons.append("Trading below 50-day SMA")
        frameworks.append({
            "name": "Minervini SEPA",
            "passed": bool(m_pass),
            "verdict": "Stage 2 Breakout" if m_pass else "; ".join(m_reasons)
        })

        # 3. Qullamaggie
        q_pass = (ema10 > ema20 > sma50) and (close > r10) and (rvol >= 1.4) and (cr >= 0.60)
        q_reasons = []
        if close <= r10:
            q_reasons.append(f"Closed below 10d high (₹{r10:.1f})")
        if cr < 0.60:
            q_reasons.append(f"Weak close: Closing range {cr * 100:.1f}% < 60%")
        if rvol < 1.4:
            q_reasons.append(f"RVOL {rvol:.2f}x < 1.40x thrust")
        frameworks.append({
            "name": "Qullamaggie HTF Breakout",
            "passed": bool(q_pass),
            "verdict": "Momentum Flag Breakout" if q_pass else "; ".join(q_reasons)
        })

        # 4. Stan Weinstein Stage 2
        w_pass = (close > sma150 >= sma200) and (close > r20) and (rvol >= 1.4) and (rs >= 65.0)
        w_reasons = []
        if close <= r20:
            w_reasons.append(f"Pending Stage 2 pivot clearance (₹{r20:.1f})")
        if rvol < 1.4:
            w_reasons.append(f"Volume expansion missing ({rvol:.2f}x vs 1.40x)")
        frameworks.append({
            "name": "Stan Weinstein Stage 2",
            "passed": bool(w_pass),
            "verdict": "Stage 2 Breakout Confirmed" if w_pass else "; ".join(w_reasons)
        })

        # 5. Protocol Fortified
        p_pass = (close > sma50 > sma200) and (close > r20) and ((close - r20) / atr >= 0.10) and (ext50 <= 0.20)
        p_reasons = []
        if close <= r20:
            p_reasons.append(f"Negative ATR clearance: {((close - r20) / atr):.2f} ATR")
        if ext50 > 0.20:
            p_reasons.append(f"Extension +{ext50 * 100:.1f}% > 20% limit")
        frameworks.append({
            "name": "Protocol Fortified",
            "passed": bool(p_pass),
            "verdict": "Fortified Setup" if p_pass else "; ".join(p_reasons)
        })

        # 6. Relative Strength Leader
        rs_pass = (close > sma50 > sma200) and (rs >= 80.0) and (rvol >= 1.0) and (ext50 <= 0.25)
        rs_reasons = []
        if rvol < 1.0:
            rs_reasons.append(f"Volume participation thin ({rvol:.2f}x < 1.0x)")
        if rs < 80.0:
            rs_reasons.append(f"RS Rating {rs:.0f} < 80")
        frameworks.append({
            "name": "RS Leader",
            "passed": bool(rs_pass),
            "verdict": f"Market Leader (RS {rs:.0f})" if rs_pass else "; ".join(rs_reasons)
        })

        # 7. PKScreener VCP
        vcp_pass = (close > sma50 > sma200) and (close > r10) and (rvol >= 1.25)
        vcp_reasons = []
        if close <= r10:
            vcp_reasons.append("Did not clear 10-day pivot")
        if rvol < 1.25:
            vcp_reasons.append(f"Volume {rvol:.2f}x < 1.25x")
        frameworks.append({
            "name": "PKScreener VCP",
            "passed": bool(vcp_pass),
            "verdict": "VCP Contraction Breakout" if vcp_pass else "; ".join(vcp_reasons)
        })

        # 8. Turtle Trading (Donchian 20d Breakout)
        t_pass = (close > sma50 > sma200) and (close > r20) and (rvol >= 1.2)
        t_reasons = []
        if close <= r20:
            t_reasons.append(f"Closed below 20-day Donchian ceiling (₹{r20:.1f})")
        if rvol < 1.2:
            t_reasons.append(f"Volume {rvol:.2f}x < 1.20x threshold")
        frameworks.append({
            "name": "Turtle Trading",
            "passed": bool(t_pass),
            "verdict": "Donchian 20d Breakout Confirmed" if t_pass else "; ".join(t_reasons)
        })

        # 9. Darvas Box (Consolidation Ceiling Expansion)
        d_pass = (close > sma50 > sma200) and (close >= 0.85 * h52) and (close > r20) and (rvol >= 1.3)
        d_reasons = []
        if close <= r20:
            d_reasons.append(f"Inside Darvas box ceiling (₹{r20:.1f})")
        if close < 0.85 * h52:
            d_reasons.append(f"Outside upper 15% 52W quadrant (High ₹{h52:.1f})")
        if rvol < 1.3:
            d_reasons.append(f"Volume surge {rvol:.2f}x < 1.30x box expansion hurdle")
        frameworks.append({
            "name": "Darvas Box",
            "passed": bool(d_pass),
            "verdict": "Darvas Box Breakout Confirmed" if d_pass else "; ".join(d_reasons)
        })

        # Wyckoff Auction State
        range_atr = round((high - low) / atr, 2)
        if high > r20 and close < r20 and cr <= 0.35:
            pa_state = "State D: Failed Acceptance Above Resistance"
            wyckoff_narrative = (
                f"Intraday probe above prior pivot ₹{r20:.2f} touched session high ₹{high:.2f}, but price rejected above "
                f"the prior pivot and closed near the session low at ₹{close:.2f} (Closing Range {cr * 100:.1f}%, 0% retention, "
                f"Day Range {range_atr}x ATR), indicating failed acceptance above resistance. Breakout unconfirmed on the tape."
            )
        elif close >= r20 and cr >= 0.60:
            pa_state = "State A: Accepted Expansion"
            wyckoff_narrative = f"Strong auction acceptance: closed near day's high (Closing Range {cr * 100:.1f}%) clearing resistance."
        elif close >= r20:
            pa_state = "State B: Pending Acceptance"
            wyckoff_narrative = f"Holding above ₹{r20:.2f} but closing range ({cr * 100:.1f}%) requires secondary confirmation."
        else:
            pa_state = "Consolidation / Base Building"
            wyckoff_narrative = f"Trading inside normal consolidation band between ₹{low:.2f} and ₹{high:.2f}."

        # Tactical Game Plan
        trigger_px = round(high + 0.10 * atr, 2)
        inval_stop = round(min(ema10, close * 0.95), 2)
        if is_cand:
            status = "QUALIFIED_SETUP"
            gameplan = f"Active buy candidate. Execute breakout entry at ₹{close:.2f} with stop at ₹{inval_stop:.2f}."
        elif close > sma50 and sma50 > sma200:
            status = "WATCHLIST_PIVOT_UNCONFIRMED"
            deliv_obs = f"Security delivery rate ({dp:.1f}%) indicates low participation relative to historical distribution. " if dp > 0 else ""
            gameplan = (
                f"Macro Stage 2 trend and relative strength remain intact, but session breakout attempt lacked volume confirmation (RVOL {rvol:.2f}x) and price acceptance. {deliv_obs}"
                f"Confirmation condition: Subsequent daily close holding above ₹{r20:.2f}–₹{high:.2f} on volume >= {max(1.4, rvol * 1.5):.1f}x with successful hold of the breakout zone. "
                f"Dynamic support aligns at 10 EMA (₹{ema10:.2f}) and 20 EMA (₹{ema20:.2f})."
            )
        else:
            status = "STAGE_4_AVOID"
            gameplan = "Stock is not in a confirmed Stage 2 uptrend. Avoid until price reclaims 50 SMA and 200 SMA."

        lookup[sym] = {
            "symbol": sym,
            "company": get_company_name(sym),
            "sector": get_sector(sym),
            "close": round(close, 2),
            "open": round(open_px, 2),
            "high": round(high, 2),
            "low": round(low, 2),
            "r10": round(r10, 2),
            "r20": round(r20, 2),
            "resistance": round(r20, 2),
            "support": round(low, 2),
            "h52": round(h52, 2),
            "l52": round(l52, 2),
            "ema10": round(ema10, 2),
            "ema20": round(ema20, 2),
            "sma50": round(sma50, 2),
            "sma150": round(sma150, 2),
            "sma200": round(sma200, 2),
            "stage2": bool(close > sma50 and sma50 > sma200),
            "rvol": round(rvol, 2),
            "rvol50": round(rvol50, 2),
            "rs": round(rs, 1),
            "deliv": round(dp, 1),
            "adr": round(adr20 * 100, 1),
            "closing_range": round(cr * 100, 1),
            "retention": round(ret * 100, 1),
            "pa_state": pa_state,
            "wyckoff_narrative": wyckoff_narrative,
            "frameworks": frameworks,
            "tactical_gameplan": gameplan,
            "status": status,
            "is_cand": is_cand,
            "trigger_px": trigger_px,
            "inval_stop": inval_stop,
        }

    return lookup
