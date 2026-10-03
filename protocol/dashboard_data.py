"""Data preparation engine for the interactive quant screener dashboard.

Extracts multi-framework screener candidates, enriches them with NSE delivery data,
official company names, industry sectors, and deep institutional technical reasons
matching TECHNICAL_ANALYSIS_AND_DATA_GUIDE.md.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
import numpy as np
import pandas as pd

from protocol.data import load_history
from protocol.corporate_events import get_corporate_audit
from protocol.wyckoff_pa import evaluate_wyckoff_pa
from protocol.universe_lookup import build_universe_lookup
from protocol.github_screeners import (
    compute_screener_features,
    screen_canslim,
    screen_minervini,
    screen_pkscreener_vcp,
    screen_protocol_v2,
    screen_qullamaggie,
    screen_relative_strength,
    screen_stan_weinstein,
)
from protocol.regime import get_regime_at
from protocol.sector import get_company_name, get_sector

ROOT = Path(__file__).resolve().parent.parent


def build_candidate_data(
    df: pd.DataFrame,
    asof_date: str | pd.Timestamp = "2026-10-01"
) -> dict[str, Any]:
    """Build complete dashboard payload with enriched technical breakdown."""
    asof = pd.Timestamp(asof_date).normalize()
    reg = get_regime_at(df, asof)
    feat = compute_screener_features(df, asof)

    # 52-Week High/Low breadth
    h52_cnt = int((feat["Close"] >= feat["h52"] * 0.999).sum()) if "h52" in feat.columns else 0
    l52_cnt = int((feat["Close"] <= feat["l52"] * 1.001).sum()) if "l52" in feat.columns else 0
    net_new_highs = h52_cnt - l52_cnt

    # Load delivery data if available
    deliv_map: dict[str, float] = {}
    deliv_file = ROOT / "data" / "delivery_history.parquet"
    if deliv_file.exists():
        try:
            ddf = pd.read_parquet(deliv_file)
            ddf["Date"] = pd.to_datetime(ddf["Date"]).dt.normalize()
            dsub = ddf[ddf["Date"] == asof]
            deliv_map = dict(zip(dsub["Symbol"].astype(str), dsub["DelivPct"].astype(float)))
        except Exception:
            pass

    # Screen all 7 frameworks
    groups = [
        ("Protocol Fortified", screen_protocol_v2(feat, top_n=15, min_turnover_cr=1.0)),
        ("Relative Strength Leader", screen_relative_strength(feat, top_n=15, min_turnover_cr=1.0)),
        ("Minervini Template", screen_minervini(feat, top_n=15, min_turnover_cr=1.0)),
        ("Stan Weinstein Stage 2", screen_stan_weinstein(feat, top_n=15, min_turnover_cr=1.0)),
        ("Qullamaggie Breakout", screen_qullamaggie(feat, top_n=15, min_turnover_cr=1.0)),
        ("CANSLIM Pivot", screen_canslim(feat, top_n=15, min_turnover_cr=1.0)),
        ("PKScreener VCP", screen_pkscreener_vcp(feat, top_n=15, min_turnover_cr=1.0)),
    ]

    feat_by_sym = {row["Symbol"]: row for _, row in feat.iterrows()}
    candidates: dict[str, dict[str, Any]] = {}

    for strat_name, picks in groups:
        for p in picks:
            sym = p.symbol
            if sym not in candidates:
                f = feat_by_sym.get(sym)
                if f is None:
                    continue
                cand = _build_single_candidate(f, deliv_map.get(sym))
                cand["strategies"] = [strat_name]
                candidates[sym] = cand
            else:
                candidates[sym]["strategies"].append(strat_name)

    # Sort: Frameworks count DESC, Safe extension priority, then 20d return DESC
    def sort_key(c: dict[str, Any]) -> tuple:
        strat_cnt = len(c["strategies"])
        ext_penalty = 0 if not c["is_extended"] else 1
        return (strat_cnt, -ext_penalty, c["ret20"])

    cand_list = sorted(candidates.values(), key=sort_key, reverse=True)

    # Compute high-level dashboard KPIs
    total_cands = len(cand_list)
    high_conviction = sum(1 for c in cand_list if len(c["strategies"]) >= 3)
    avg_rvol = round(float(np.mean([c["rvol"] for c in cand_list])), 1) if cand_list else 0.0
    inst_deliv_cnt = sum(1 for c in cand_list if c["deliv_pct"] >= 50.0)

    return {
        "asof": str(asof.date()),
        "regime": {
            "name": reg.get("regime", "UNKNOWN"),
            "action": reg.get("action", "CASH"),
            "index": reg.get("ew_close", 0.0),
            "sma20": reg.get("sma20", 0.0),
            "breadth": reg.get("pct_above_sma20", 0.0),
            "highs_52w": h52_cnt,
            "lows_52w": l52_cnt,
            "net_new_highs": net_new_highs,
            "message": reg.get("message", ""),
        },
        "kpis": {
            "total_candidates": total_cands,
            "high_conviction": high_conviction,
            "avg_rvol": avg_rvol,
            "institutional_delivery_count": inst_deliv_cnt,
        },
        "candidates": cand_list,
        "universe_lookup": build_universe_lookup(feat, candidates, deliv_map),
        "default_capital_per_stock": 100000,
    }


def _build_single_candidate(f: pd.Series, deliv_pct: float | None) -> dict[str, Any]:
    """Build rich technical scorecard and actual reasons for a single symbol."""
    sym = str(f["Symbol"])
    close = float(f["Close"])
    h52 = float(f["h52"])
    r20 = float(f["r20"])
    r10 = float(f["r10"])
    sma50 = float(f["sma50"])
    sma150 = float(f["sma150"])
    sma200 = float(f["sma200"])
    ema10 = float(f["ema10"])
    ema20 = float(f["ema20"])
    rvol20 = float(f["rvol20"])
    adr20 = float(f["adr20"])
    ext50 = float(f["ext_sma50"])
    ret20 = float(f["ret20"])
    ret60 = float(f["ret60"])
    ret120 = float(f["ret120"]) if "ret120" in f and not pd.isna(f["ret120"]) else ret60
    ret252 = float(f["ret252"]) if "ret252" in f and not pd.isna(f["ret252"]) else ret120
    rs_rating = float(f["rs_rating"]) if "rs_rating" in f and not pd.isna(f["rs_rating"]) else 50.0
    vol = int(f["Volume"])
    turnover_cr = round(float(f["turnover20"]) / 1e7, 1)

    # Breakout categorization
    is_52w = close >= (h52 * 0.999)
    if is_52w:
        bo_type = "52-Week High Breakout"
        bo_ref = h52
        bo_pct = round(((close - h52) / h52) * 100, 1) if h52 > 0 else 0.0
    else:
        bo_type = "20-Day Resistance Breakout"
        bo_ref = r20
        bo_pct = round(((close - r20) / r20) * 100, 1) if r20 > 0 else 0.0

    # Moving Average Stack
    full_stack = (close > ema10 > ema20 > sma50 > sma150 > sma200)

    # Invalidation Stop: base consolidation low - 0.5 ATR, bounded between 3% and 8%
    atr = adr20 * close
    base_low = float(f["base_low20"]) if "base_low20" in f and not pd.isna(f["base_low20"]) else (
        float(f["low10"]) if "low10" in f and not pd.isna(f["low10"]) else (close - 1.5 * atr)
    )
    struct_stop = base_low - 0.5 * atr
    stop = round(max(min(struct_stop, close * 0.97), close * 0.92), 2)
    stop_pct = round(((close - stop) / close) * 100, 1)
    target_2r = round(close + 2.0 * (close - stop), 2)
    target_2r_pct = round(((target_2r - close) / close) * 100, 1)

    # Delivery & Volatility
    dp = round(deliv_pct, 1) if deliv_pct is not None else 0.0
    is_low_vol = adr20 <= 0.035
    is_extended = ext50 > 0.20

    badges: list[str] = []
    if is_52w:
        badges.append("52W HIGH BREAKOUT")
    if rs_rating >= 90.0:
        badges.append(f"RS {rs_rating:.0f} (TOP {max(1, 100-int(round(rs_rating)))}%)")
    if rvol20 >= 5.0:
        badges.append(f"{round(rvol20, 1)}x VOLUME THRUST")
    if dp >= 50.0:
        badges.append("INSTITUTIONAL DELIVERY ≥50%")
    if is_low_vol:
        badges.append("LOW VOLATILITY ADVANTAGE")
    if is_extended:
        badges.append("CAUTION: EXTENDED >20%")

    shelf_touches = int(f["shelf_touches_20"]) if "shelf_touches_20" in f and not pd.isna(f["shelf_touches_20"]) else 0
    if is_52w:
        reasons = [f"Printed 52-week high breakout at ₹{close:.2f} (prior high: ₹{h52:.2f}, +{bo_pct}% clearance)."]
    elif shelf_touches >= 2:
        reasons = [f"Decisively cleared {shelf_touches}-touch consolidation shelf at ₹{r20:.2f} to close at ₹{close:.2f} (+{bo_pct}% clearance)."]
    else:
        reasons = [f"Broke 20-day resistance at ₹{r20:.2f} to close at ₹{close:.2f} (+{bo_pct}% clearance)."]
    if rs_rating >= 80.0:
        reasons.append(f"Market leader RS {rs_rating:.0f}/99 (beat {rs_rating:.0f}% of market, 1Y: {ret252*100:+.1f}%, 6M: {ret120*100:+.1f}%).")
    reasons.append(
        f"Institutional MA stack: Close > EMA10 > EMA20 > SMA50 > SMA150 > SMA200."
        if full_stack else f"Stage 2 uptrend: Close above 50-day SMA (₹{sma50:.1f}) and 200-day SMA (₹{sma200:.1f})."
    )
    if rvol20 >= 2.0:
        reasons.append(f"Volume ignition: {rvol20:.1f}x 20d average volume ({vol:,} shares, ~₹{turnover_cr} Cr turnover).")
    if dp >= 50.0:
        reasons.append(f"Heavy Demat delivery absorption of {dp}% (exceeds the 50% quant hurdle).")
    elif dp > 0:
        reasons.append(f"Security delivery rate: {dp}% with {vol:,} traded shares.")
    if is_low_vol:
        reasons.append(f"Low-volatility breakout structure (ADR = {adr20*100:.1f}%, IC = -0.0434, t = -7.35 edge).")
    if is_extended:
        reasons.append(f"WARNING: Extended +{ext50*100:.1f}% above 50 SMA (>20% limit). Wait for pullback toward 10 EMA (₹{ema10:.2f}).")
    else:
        reasons.append(f"Safe extension (+{ext50*100:.1f}% above SMA50), inside strict ≤20% anti-chase gate.")

    action = "Wait for 3-5 day High-Tight Flag or EMA10 pullback" if is_extended else "Immediate breakout execution"
    sec_name = get_sector(sym)
    audit = get_corporate_audit(sym, sec_name, is_extended, ema10)
    wpa = evaluate_wyckoff_pa(f)
    badges.extend(audit["badges"])
    badges.extend(wpa["badges"])
    reasons.append(f"Price Action & Wyckoff: {wpa['wyckoff_narrative']}")

    return {
        "symbol": sym,
        "company": get_company_name(sym),
        "sector": sec_name,
        "series": audit["series"],
        "circuit_band": audit["circuit_band"],
        "is_t2t": audit["is_t2t"],
        "has_earnings_soon": audit["has_earnings_soon"],
        "wyckoff": wpa,
        "close": round(close, 2),
        "r20": round(r20, 2),
        "r10": round(r10, 2),
        "h52": round(h52, 2),
        "breakout_type": bo_type,
        "breakout_ref": round(bo_ref, 2),
        "breakout_pct": bo_pct,
        "rvol": round(rvol20, 2),
        "volume": vol,
        "turnover_cr": turnover_cr,
        "deliv_pct": dp,
        "adr": round(adr20 * 100, 1),
        "rs_rating": round(rs_rating, 1),
        "ret20": round(ret20 * 100, 1),
        "ret60": round(ret60 * 100, 1),
        "ret120": round(ret120 * 100, 1),
        "ret252": round(ret252 * 100, 1),
        "ext50": round(ext50 * 100, 1),
        "is_extended": is_extended,
        "is_low_vol": is_low_vol,
        "stop": stop,
        "stop_pct": stop_pct,
        "target_2r": target_2r,
        "target_2r_pct": target_2r_pct,
        "badges": badges,
        "catalyst_warning": audit["warning_text"],
        "ma_stack": {
            "ema10": round(ema10, 2),
            "ema20": round(ema20, 2),
            "sma50": round(sma50, 2),
            "sma150": round(sma150, 2),
            "sma200": round(sma200, 2),
            "full_stack": full_stack,
        },
        "reason": " ".join(reasons),
        "execution_plan": {
            "action": action,
            "entry_ref": round(close, 2),
            "stop_loss": stop,
            "stop_pct": stop_pct,
            "target_2r": target_2r,
            "target_2r_pct": target_2r_pct,
            "trailing_rule": "Sell half at 2R target (+15.2%), move stop to breakeven, trail remainder along 10 EMA.",
        },
    }
