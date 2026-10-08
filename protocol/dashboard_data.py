"""Data preparation engine for the interactive quant screener dashboard.

Extracts multi-framework screener candidates, enriches them with NSE delivery data,
official company names, industry sectors, and deep institutional technical reasons
matching TECHNICAL_ANALYSIS_AND_DATA_GUIDE.md.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
import numpy as np
import pandas as pd

from protocol.corporate_events import get_corporate_audit
from protocol.wyckoff_pa import evaluate_wyckoff_pa
from protocol.universe_lookup import build_universe_lookup
from protocol.frameworks import load_delivery_map, run_frameworks
from protocol.github_screeners import compute_screener_features
from protocol.regime import get_regime_at
from protocol.sector import (
    get_company_name, get_sector, compute_industry_momentum,
    get_symbol_industry_momentum
)
from protocol.forward_verifier import build_forward_verification_suite
from protocol.price_action import load_price_action_board
from protocol.weekly import WEEKLY_GATES

ROOT = Path(__file__).resolve().parent.parent


def _load_report(filename: str) -> dict[str, Any]:
    for p in (ROOT / "reports" / filename, ROOT / "data" / filename):
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                pass
    return {}


def _load_weekly_confluence() -> pd.DataFrame:
    for p in (ROOT / "reports" / "weekly_confluence.csv", ROOT / "data" / "weekly_confluence.csv"):
        if p.exists():
            try:
                return pd.read_csv(p)
            except Exception:
                pass
    return pd.DataFrame()


def _parse_weekly_gates(gates_str: Any) -> list[str]:
    """Parse comma-separated weekly gate string safely without splitting on internal commas."""
    if not gates_str or pd.isna(gates_str):
        return []
    s = str(gates_str)
    return [label for _, label in WEEKLY_GATES if label in s]


def build_candidate_data(df: pd.DataFrame, asof_date: str | pd.Timestamp | None = None) -> dict[str, Any]:
    """Build complete dashboard payload with enriched technical breakdown."""
    if asof_date is None or asof_date == "latest":
        asof_date = df["Date"].max()
    asof = pd.Timestamp(asof_date).normalize()
    reg = get_regime_at(df, asof)
    feat = compute_screener_features(df, asof)

    # 52-Week High/Low breadth
    h52_cnt = int((feat["Close"] >= feat["h52"] * 0.999).sum()) if "h52" in feat.columns else 0
    l52_cnt = int((feat["Close"] <= feat["l52"] * 1.001).sum()) if "l52" in feat.columns else 0
    net_new_highs = h52_cnt - l52_cnt

    deliv_map = load_delivery_map(asof)
    ind_df = compute_industry_momentum(feat)

    groups = run_frameworks(feat, top_n=60, min_turnover_cr=0.5,
                            ind_df=ind_df, deliv_map=deliv_map)

    feat_by_sym = {row["Symbol"]: row for _, row in feat.iterrows()}
    candidates: dict[str, dict[str, Any]] = {}

    for strat_name, picks in groups:
        for p in picks:
            sym = p.symbol
            if sym not in candidates:
                f = feat_by_sym.get(sym)
                if f is None:
                    continue
                cand = _build_single_candidate(f, deliv_map.get(sym), ind_df=ind_df)
                cand["strategies"] = [strat_name]
                candidates[sym] = cand
            else:
                candidates[sym]["strategies"].append(strat_name)

    # Enrich candidates with weekly timeframe confluence and add weekly swing watchlist
    weekly_df = _load_weekly_confluence()
    weekly_map = {}
    if not weekly_df.empty and "Symbol" in weekly_df.columns:
        weekly_map = {str(row["Symbol"]): row for _, row in weekly_df.iterrows()}

    for sym, cand in list(candidates.items()):
        wrow = weekly_map.get(sym)
        if wrow is not None:
            cand["weekly_bucket"] = str(wrow.get("bucket", "DAILY_ONLY"))
            cand["weekly_gates"] = int(wrow.get("n_gates", 0)) if pd.notna(wrow.get("n_gates")) else 0
            cand["weekly_grade"] = str(wrow.get("w_grade", "")) if pd.notna(wrow.get("w_grade")) else ""
            cand["weekly_strong"] = bool(wrow.get("w_strong", False))
            cand["weekly_gates_list"] = _parse_weekly_gates(wrow.get("gates"))
            cand["weekly_rvol13"] = round(float(wrow["w_rvol13"]), 1) if pd.notna(wrow.get("w_rvol13")) else None
            cand["weekly_ext_ma30"] = round(float(wrow["w_ext_ma30"]) * 100, 1) if pd.notna(wrow.get("w_ext_ma30")) else None
            cand["weekly_rsi"] = round(float(wrow["w_rsi14"]), 1) if pd.notna(wrow.get("w_rsi14")) else None
            if cand["weekly_bucket"] == "BOTH":
                cand["badges"].append({"text": "🏆 DUAL CONFLUENCE", "style": "background:rgba(192,132,252,0.22);color:#c084fc;border:1px solid rgba(192,132,252,0.45);font-weight:700;"})
        else:
            cand["weekly_bucket"] = "DAILY_ONLY"
            cand["weekly_gates"] = 0
            cand["weekly_grade"] = ""
            cand["weekly_strong"] = False
            cand["weekly_gates_list"] = []

    # Also include top WEEKLY_ONLY swing candidates (weekly strong bases before daily breakout)
    if not weekly_df.empty and "bucket" in weekly_df.columns:
        w_only = weekly_df[weekly_df["bucket"] == "WEEKLY_ONLY"].sort_values(by="n_gates", ascending=False)
        for _, wrow in w_only.iterrows():
            wsym = str(wrow["Symbol"])
            if wsym in candidates:
                continue
            wf = feat_by_sym.get(wsym)
            if wf is None:
                continue
            wcand = _build_single_candidate(wf, deliv_map.get(wsym), ind_df=ind_df)
            gates_list = _parse_weekly_gates(wrow.get("gates"))
            wcand["strategies"] = [f"Weekly: {g.strip()}" for g in gates_list] if gates_list else ["Weekly Stage 2 Base"]
            wcand["setup_badge"] = "WEEKLY BASE"
            wcand["setup_desc"] = f"Weekly Stage 2 Base ({wrow['n_gates']}/12 Gates): {wrow.get('w_grade', 'A+')} Grade"
            wcand["weekly_bucket"] = "WEEKLY_ONLY"
            wcand["is_weekly_watchlist"] = True
            wcand["weekly_gates"] = int(wrow.get("n_gates", 0)) if pd.notna(wrow.get("n_gates")) else len(gates_list)
            wcand["weekly_grade"] = str(wrow.get("w_grade", "")) if pd.notna(wrow.get("w_grade")) else ""
            wcand["weekly_strong"] = True
            wcand["weekly_gates_list"] = gates_list
            wcand["weekly_rvol13"] = round(float(wrow["w_rvol13"]), 1) if pd.notna(wrow.get("w_rvol13")) else None
            wcand["weekly_ext_ma30"] = round(float(wrow["w_ext_ma30"]) * 100, 1) if pd.notna(wrow.get("w_ext_ma30")) else None
            wcand["weekly_rsi"] = round(float(wrow["w_rsi14"]), 1) if pd.notna(wrow.get("w_rsi14")) else None
            wcand["badges"].append({"text": "📅 WEEKLY STRONG", "style": "background:rgba(56,189,248,0.2);color:#38bdf8;border:1px solid rgba(56,189,248,0.45);font-weight:700;"})
            candidates[wsym] = wcand

    # Attach recent 120 daily OHLCV candles and EMAs/SMAs to each candidate for interactive charting
    cand_symbols = set(candidates.keys())
    sub_df = df[(df["Symbol"].isin(cand_symbols)) & (df["Date"] <= asof)].copy()
    sub_df.sort_values(by=["Symbol", "Date"], inplace=True)
    
    tapes: dict[str, list[list[Any]]] = {}

    for sym, cand in candidates.items():
        sym_history = sub_df[sub_df["Symbol"] == sym].copy()
        if sym_history.empty:
            cand["candles"] = []
            tapes[sym] = []
            continue

        # Full multi-year tape (up to 1500 bars / ~6 years of daily OHLCV) stored as compact tuples:
        # [date_str, open, high, low, close, volume]
        # Redundant MAs (EMA10/20, SMA50/200) are computed dynamically client-side in sub-millisecond time.
        display_bars = sym_history.tail(1500)
        tape_rows: list[list[Any]] = []
        for r in display_bars.itertuples():
            tape_rows.append([
                str(pd.to_datetime(r.Date).strftime("%Y-%m-%d")),
                round(float(r.Open), 2),
                round(float(r.High), 2),
                round(float(r.Low), 2),
                round(float(r.Close), 2),
                int(r.Volume),
            ])
        tapes[sym] = tape_rows
        # Embed recent 150 daily bars in main payload for instant zero-latency first paint
        cand["candles"] = tape_rows[-150:] if len(tape_rows) > 150 else tape_rows

    # Load decision trail data for quality audit integration
    decisions_data = _load_report("decisions.json")
    q_map = {q["symbol"]: q for q in decisions_data.get("today", [])}

    # Synthesize rich "Why Chosen / Setup Thesis" and detailed bullets for every candidate
    for sym, cand in candidates.items():
        strat_cnt = cand.get("weekly_gates") if cand.get("is_weekly_watchlist") and cand.get("weekly_gates") else len(cand.get("strategies", []))
        q_item = q_map.get(sym)
        if q_item:
            cand["quality_score"] = round(float(q_item.get("score", 0.0)), 3)
            cand["quality_rank"] = q_item.get("rank")
            cand["quality_reason"] = q_item.get("reason")

        bullets = []
        summary_tags = []

        is_52w = cand.get("breakout_type") == "52-Week High Breakout"
        shelf = cand.get("wyckoff", {}).get("shelf_touches", 0) if isinstance(cand.get("wyckoff"), dict) else 0
        close = cand.get("close", 0.0)
        h52 = cand.get("h52", 0.0)
        bo_ref = cand.get("breakout_ref", cand.get("resistance", 0.0))
        bo_pct = cand.get("breakout_pct", 0.0)
        rs = cand.get("rs_rating", 0.0)
        rvol = cand.get("rvol", 0.0)
        deliv = cand.get("deliv_pct", 0.0)
        ext50 = cand.get("ext50", 0.0)
        full_stack = cand.get("ma_stack", {}).get("full_stack", False)

        if is_52w:
            summary_tags.append(f"New 52W High (+{bo_pct}% clearance)")
            bullets.append(f"📌 Price Action: Printed new 52-week high breakout at ₹{close:.2f} (+{bo_pct}% clearance over ₹{h52:.2f}).")
        elif shelf >= 2:
            summary_tags.append(f"Cleared {shelf}x Shelf (₹{bo_ref:.2f})")
            bullets.append(f"📌 Price Action: Cleared {shelf}-touch consolidation shelf ceiling at ₹{bo_ref:.2f} to close at ₹{close:.2f} (+{bo_pct}%).")
        elif cand.get("is_weekly_watchlist"):
            summary_tags.append(f"Weekly Base (Grade {cand.get('weekly_grade', 'A+')})")
            bullets.append(f"📌 Weekly Base: Cleared {strat_cnt}/12 weekly accumulation gates with {cand.get('weekly_grade', 'A+')} grade structure.")
        else:
            summary_tags.append(f"20D Breakout (₹{bo_ref:.2f})")
            bullets.append(f"📌 Price Action: Broke 20-day resistance at ₹{bo_ref:.2f} to close at ₹{close:.2f} (+{bo_pct}%).")

        if not cand.get("is_weekly_watchlist"):
            summary_tags.append(f"{strat_cnt}/12 Frameworks")
            strats_str = ", ".join(cand.get("strategies", []))
            bullets.append(f"⚡ Institutional Confluence: Cleared {strat_cnt} of 12 screening frameworks ({strats_str}).")

        if q_item:
            summary_tags.append(f"Quality Score {q_item.get('score', 0):.3f}")
            bullets.append(f"🏆 Quality Leader #{q_item.get('rank', 1)}: {q_item.get('reason')}")

        if rs >= 80:
            summary_tags.append(f"RS {rs:.0f}/99 Leader")
            bullets.append(f"🚀 Relative Strength: RS Rating {rs:.0f}/99 — outperformed {rs:.0f}% of the entire market over 1-year window.")

        if rvol >= 1.5:
            summary_tags.append(f"{rvol:.1f}x Volume Ignition")
            bullets.append(f"🏛️ Institutional Volume: {rvol:.1f}x volume ignition thrust (~₹{cand.get('turnover_cr', 0)} Cr turnover).")

        if deliv >= 50:
            summary_tags.append(f"{deliv:.0f}% Demat Delivery")
            bullets.append(f"📦 Demat Delivery: {deliv:.1f}% delivery absorption confirms genuine institutional accumulation (hurdle: ≥50%).")

        if full_stack:
            summary_tags.append("Full MA Stack")
            bullets.append("📈 Trend Structure: Full moving average stack (Close > EMA10 > EMA20 > SMA50 > SMA150 > SMA200).")

        if cand.get("is_extended"):
            summary_tags.append(f"⚠️ Extended +{ext50:.1f}%")
            bullets.append(f"🛡️ Risk Note: Extended +{ext50:.1f}% above 50 SMA. Wait for 3-5 day high-tight flag or 10 EMA pullback before execution.")
        else:
            summary_tags.append(f"Safe Distance (+{ext50:.1f}% SMA50)")
            bullets.append(f"🛡️ Risk Discipline: Non-extended (+{ext50:.1f}% above 50 SMA), inside strict ≤20% anti-chase safety gate.")

        bullets.append(f"🎯 Execution Plan: Invalidation Stop Loss at ₹{cand.get('stop', 0):.2f} (-{cand.get('stop_pct', 0)}%), Target 2R at ₹{cand.get('target_2r', 0):.2f} (+{cand.get('target_2r_pct', 0)}%).")

        cand["selection_thesis"] = " • ".join(summary_tags[:4])
        cand["thesis_bullets"] = bullets

    # Enrich confluence_top leaders with synthesized thesis
    cf_leaders = decisions_data.get("confluence_top", [])
    for cf in cf_leaders:
        c_match = candidates.get(cf.get("symbol"))
        if c_match:
            cf["selection_thesis"] = c_match.get("selection_thesis")
            cf["thesis_bullets"] = c_match.get("thesis_bullets")

    # Sort: Daily candidates first, ordered by framework confluence count, then dual confluence
    def sort_key(c: dict[str, Any]) -> tuple:
        strat_cnt = len(c.get("strategies", []))
        is_w_only = 1 if c.get("weekly_bucket") == "WEEKLY_ONLY" else 0
        is_both = 1 if c.get("weekly_bucket") == "BOTH" else 0
        return (-is_w_only, strat_cnt, is_both, -(1 if c["is_extended"] else 0), c["ret20"])

    cand_list = sorted(candidates.values(), key=sort_key, reverse=True)

    # Compute high-level dashboard KPIs
    total_cands = len(cand_list)
    high_conviction = sum(1 for c in cand_list if len(c["strategies"]) >= 3 or c.get("weekly_bucket") == "BOTH")
    avg_rvol = round(float(np.mean([c["rvol"] for c in cand_list])), 1) if cand_list else 0.0
    inst_deliv_cnt = sum(1 for c in cand_list if c["deliv_pct"] >= 50.0)
    both_cnt = sum(1 for c in cand_list if c.get("weekly_bucket") == "BOTH")
    weekly_only_cnt = sum(1 for c in cand_list if c.get("weekly_bucket") == "WEEKLY_ONLY")
    daily_only_cnt = sum(1 for c in cand_list if c.get("weekly_bucket") == "DAILY_ONLY")

    full_universe = build_universe_lookup(feat, candidates, deliv_map)

    swing_watchlist = []
    dual_confluence = []
    if not weekly_df.empty and "bucket" in weekly_df.columns:
        w_only = weekly_df[weekly_df["bucket"] == "WEEKLY_ONLY"].sort_values(by="n_gates", ascending=False)
        for _, r in w_only.head(15).iterrows():
            swing_watchlist.append({
                "symbol": str(r["Symbol"]),
                "gates": int(r["n_gates"]) if pd.notna(r.get("n_gates")) else 0,
                "grade": str(r.get("w_grade", "")),
                "close": round(float(r["weekly_close"]), 2) if pd.notna(r.get("weekly_close")) else None,
                "wret13": round(float(r["wret13"]) * 100, 1) if pd.notna(r.get("wret13")) else None,
                "wret52": round(float(r["wret52"]) * 100, 1) if pd.notna(r.get("wret52")) else None,
                "rvol13": round(float(r["w_rvol13"]), 2) if pd.notna(r.get("w_rvol13")) else None,
                "ext_ma30": round(float(r["w_ext_ma30"]) * 100, 1) if pd.notna(r.get("w_ext_ma30")) else None,
                "gates_list": _parse_weekly_gates(r.get("gates")),
            })
        both_df = weekly_df[weekly_df["bucket"] == "BOTH"].sort_values(by=["n_frameworks", "n_gates"], ascending=False)
        for _, r in both_df.head(15).iterrows():
            dual_confluence.append({
                "symbol": str(r["Symbol"]),
                "daily_frameworks": int(r["n_frameworks"]) if pd.notna(r.get("n_frameworks")) else 0,
                "weekly_gates": int(r["n_gates"]) if pd.notna(r.get("n_gates")) else 0,
                "grade": str(r.get("w_grade", "")),
                "close": round(float(r["daily_close"]), 2) if pd.notna(r.get("daily_close")) else None,
                "frameworks_str": str(r.get("frameworks", "")),
                "gates_list": _parse_weekly_gates(r.get("gates")),
            })

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
            "ftd_status": reg.get("ftd_status", ""),
            "is_ftd": bool(reg.get("is_ftd", False)),
            "ftd_active": bool(reg.get("ftd_active", False)),
            "rally_day": int(reg.get("rally_day", 0)),
            "last_ftd_date": reg.get("last_ftd_date", None),
        },
        "kpis": {
            "total_candidates": total_cands,
            "high_conviction": high_conviction,
            "avg_rvol": avg_rvol,
            "institutional_delivery_count": inst_deliv_cnt,
            "both_count": both_cnt,
            "weekly_only_count": weekly_only_cnt,
            "daily_only_count": daily_only_cnt,
        },
        "weekly_kpis": {
            "both_count": both_cnt,
            "weekly_only_count": weekly_only_cnt,
            "daily_only_count": daily_only_cnt,
        },
        "executive_report": {
            "headline": decisions_data.get("headline", ""),
            "quality_leaders": decisions_data.get("today", []),
            "confluence_leaders": decisions_data.get("confluence_top", []),
            "dual_confluence": dual_confluence,
            "swing_watchlist": swing_watchlist,
        },
        "candidates": cand_list,
        "price_action_board": load_price_action_board(),
        "universe_lookup": {s: full_universe[s] for s in cand_symbols if s in full_universe},
        "walk_forward": _load_report("walk_forward_report.json"),
        "industry_rankings": ind_df.to_dict(orient="records") if not ind_df.empty else [],
        "forward_verifier": build_forward_verification_suite(df, max_dates=16),
        "default_capital_per_stock": 100000,
        "_tapes": tapes,
        "_full_universe_lookup": full_universe,
    }


def _build_single_candidate(f: pd.Series, deliv_pct: float | None, ind_df: pd.DataFrame | None = None) -> dict[str, Any]:
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
    bo_type = "52-Week High Breakout" if is_52w else "20-Day Resistance Breakout"
    bo_ref = h52 if is_52w else r20
    bo_pct = round(((close - bo_ref) / bo_ref) * 100, 1) if bo_ref > 0 else 0.0

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

    ind_info = get_symbol_industry_momentum(sym, ind_df) if ind_df is not None else {}
    r60 = float(f["r60"]) if "r60" in f and not pd.isna(f["r60"]) else (
        float(f["R60"]) if "R60" in f and not pd.isna(f["R60"]) else r20
    )
    has_overhead_ceiling = (r60 > r20 * 1.015)
    ceiling_cleared = (not has_overhead_ceiling) or (close >= r60)

    crsi_val = float(f.get("crsi", 50.0)) if "crsi" in f and not pd.isna(f["crsi"]) else 50.0

    badges: list[str] = [
        "52W HIGH BREAKOUT" if is_52w else "",
        f"RS {rs_rating:.0f} (TOP {max(1, 100-int(round(rs_rating)))}%)" if rs_rating >= 90.0 else "",
        f"{round(rvol20, 1)}x VOLUME THRUST" if rvol20 >= 5.0 else "",
        "INSTITUTIONAL DELIVERY ≥50%" if dp >= 50.0 else "",
        "LOW VOLATILITY ADVANTAGE" if is_low_vol else "",
        "CAUTION: EXTENDED >20%" if is_extended else "",
        f"SECTOR TAILWIND: {str(ind_info.get('tier','')).split(':')[0]}" if ind_info.get("is_tailwind") else "",
        f"OVERSOLD DIP (CRSI {crsi_val:.0f})" if crsi_val <= 25.0 else "",
        "60D BASE CEILING CLEARED" if (has_overhead_ceiling and ceiling_cleared) else (
            f"CAUTION: OVERHEAD CEILING (₹{r60:.1f})" if (has_overhead_ceiling and not ceiling_cleared) else ""
        ),
    ]
    badges = [b for b in badges if b]

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
    reasons.append(f"Key S/R Architecture: Overhead Resistance cleared at ₹{bo_ref:.2f} (+{bo_pct}%), Base Support Floor at ₹{base_low:.2f} (-{round(((close - base_low)/close)*100, 1)}%).")

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
        "resistance": round(bo_ref, 2),
        "support": round(base_low, 2),
        "breakout_type": bo_type,
        "breakout_ref": round(bo_ref, 2),
        "breakout_pct": bo_pct,
        "rvol": round(rvol20, 2),
        "volume": vol,
        "turnover_cr": turnover_cr,
        "deliv_pct": dp,
        "crsi": round(crsi_val, 1),
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
        "industry_tier": ind_info.get("tier", "Tier 3: Neutral"),
        "industry_rs": ind_info.get("rs_rank", 50.0),
        "is_sector_tailwind": bool(ind_info.get("is_tailwind", False)),
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
        "reasons_list": reasons,
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
