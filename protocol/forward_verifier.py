"""Forward Trade Verification & Replay Engine.

Allows users on GitHub Pages to select any historical screening date
(e.g., 15-Sep, 18-Sep / 20-Sep weekend, 25-Sep) and inspect exactly what
happened to the candidate stocks day-by-day over the next 7 to 14 sessions:
1. Evaluates Market Regime on the screening date.
2. Identifies all screened candidate stocks across all 10 strategies.
3. Simulates USIC staged execution day-by-day (Next-day Open entry + 25 bps,
   5% stop, +1.5R scale-out to breakeven, +2.5R target).
4. Produces day-by-day price and event logs and compares Staged P&L vs Buy & Hold.
"""
from __future__ import annotations

from typing import Any
import numpy as np
import pandas as pd

from protocol.regime import get_regime_at
from protocol.github_screeners import (
    compute_screener_features, screen_protocol_v2, screen_minervini,
    screen_qullamaggie, screen_canslim,
    screen_relative_strength, screen_stan_weinstein, screen_turtle_trading,
    screen_darvas_box
)
from protocol.sector import get_company_name, get_sector


def simulate_single_stock_forward(
    symbol: str,
    asof_date: pd.Timestamp,
    forward_df: pd.DataFrame,
    entry_cost_bps: float = 25.0,
    stop_pct: float = 0.05,
    target1_mult: float = 1.5,
    target2_mult: float = 2.5,
) -> dict[str, Any] | None:
    """Simulate day-by-day forward trade execution starting from next available session."""
    sub = forward_df[forward_df["Symbol"] == symbol].sort_values("Date").reset_index(drop=True)
    if sub.empty:
        return None

    entry_cost = entry_cost_bps / 10000.0
    entry_open = float(sub.iloc[0]["Open"])
    entry_price = round(entry_open * (1.0 + entry_cost), 2)
    entry_date = sub.iloc[0]["Date"].strftime("%Y-%m-%d")

    stop_price = round(entry_price * (1.0 - stop_pct), 2)
    target1_price = round(entry_price * (1.0 + stop_pct * target1_mult), 2)
    target2_price = round(entry_price * (1.0 + stop_pct * target2_mult), 2)

    pos_half1_open = True
    pos_half2_open = True
    half1_exit_px = None
    half1_exit_date = None
    half1_reason = None

    half2_exit_px = None
    half2_exit_date = None
    half2_reason = None

    current_stop = stop_price
    target1_hit = False

    daily_logs: list[dict[str, Any]] = []

    for idx, row in sub.iterrows():
        d_str = row["Date"].strftime("%Y-%m-%d")
        o = round(float(row["Open"]), 2)
        h = round(float(row["High"]), 2)
        l = round(float(row["Low"]), 2)
        c = round(float(row["Close"]), 2)

        day_events: list[str] = []

        # Half 1 execution check
        if pos_half1_open:
            if l <= current_stop:
                pos_half1_open = False
                pos_half2_open = False
                exit_fill = min(o, current_stop)
                half1_exit_px = round(exit_fill * (1.0 - entry_cost), 2)
                half1_exit_date = d_str
                half1_reason = "STOP_LOSS (-1.0R)"
                half2_exit_px = half1_exit_px
                half2_exit_date = d_str
                half2_reason = "STOP_LOSS (-1.0R)"
                day_events.append(f"🛑 STOP LOSS HIT at ₹{exit_fill:.2f} (Low: ₹{l:.2f}) -> Full position exited")
            elif h >= target1_price:
                target1_hit = True
                pos_half1_open = False
                half1_exit_px = round(target1_price * (1.0 - entry_cost), 2)
                half1_exit_date = d_str
                half1_reason = "TARGET 1 (+1.5R)"
                current_stop = entry_price  # Trailing stop to breakeven!
                day_events.append(f"🎯 TARGET 1 HIT at ₹{target1_price:.2f} -> 50% Profit Banked (+{round(stop_pct*target1_mult*100, 1)}%), Stop on remainder raised to Breakeven (₹{entry_price:.2f})")

        # Half 2 execution check
        if pos_half2_open and not pos_half1_open and half1_exit_date != d_str:
            if l <= current_stop:
                pos_half2_open = False
                exit_fill = min(o, current_stop)
                half2_exit_px = round(exit_fill * (1.0 - entry_cost), 2)
                half2_exit_date = d_str
                half2_reason = "BREAKEVEN_STOP"
                day_events.append(f"🛡️ BREAKEVEN STOP HIT at ₹{exit_fill:.2f} (Low: ₹{l:.2f}) -> Remaining 50% closed risk-free")
            elif h >= target2_price:
                pos_half2_open = False
                half2_exit_px = round(target2_price * (1.0 - entry_cost), 2)
                half2_exit_date = d_str
                half2_reason = "TARGET 2 (+2.5R)"
                day_events.append(f"🚀 TARGET 2 HIT at ₹{target2_price:.2f} -> Remaining 50% Banked (+{round(stop_pct*target2_mult*100, 1)}%)")

        status_event = " • ".join(day_events) if day_events else ("Holding position" if (pos_half1_open or pos_half2_open) else "Position closed")
        daily_logs.append({
            "date": d_str,
            "open": o,
            "high": h,
            "low": l,
            "close": c,
            "event": status_event,
            "is_event": len(day_events) > 0,
        })

        if not pos_half1_open and not pos_half2_open:
            break

    # If position still active at end of horizon, mark to market
    last_row = sub.iloc[-1]
    last_date = last_row["Date"].strftime("%Y-%m-%d")
    last_close = round(float(last_row["Close"]) * (1.0 - entry_cost), 2)

    if pos_half1_open:
        half1_exit_px = last_close
        half1_exit_date = last_date
        half1_reason = "ACTIVE_HOLD"
    if pos_half2_open:
        half2_exit_px = last_close
        half2_exit_date = last_date
        half2_reason = "ACTIVE_HOLD"

    pnl_half1_pct = round(((half1_exit_px - entry_price) / entry_price) * 100, 2)
    pnl_half2_pct = round(((half2_exit_px - entry_price) / entry_price) * 100, 2)
    staged_pnl_pct = round(0.5 * pnl_half1_pct + 0.5 * pnl_half2_pct, 2)
    static_pnl_pct = round(((last_close - entry_price) / entry_price) * 100, 2)

    status = "WIN" if staged_pnl_pct > 1.0 else ("LOSS" if staged_pnl_pct < -1.0 else "BREAKEVEN")
    verdict = (
        f"Protected capital: Banked +{pnl_half1_pct}% at Target 1 and safely exited remainder at breakeven."
        if (target1_hit and half2_reason == "BREAKEVEN_STOP") else (
            f"Achieved full target run (+{staged_pnl_pct}% net gain)."
            if (target1_hit and half2_reason == "TARGET 2 (+2.5R)") else (
                f"Strict -5% stop loss preserved capital (loss capped at {staged_pnl_pct}% vs buy & hold {static_pnl_pct}%)."
                if (half1_reason == "STOP_LOSS (-1.0R)") else (
                    f"Position still open (P&L: {staged_pnl_pct:+}%)."
                )
            )
        )
    )

    max_high = round(float(sub["High"].max()), 2)
    min_low = round(float(sub["Low"].min()), 2)
    max_fwd_gain = round(((max_high - entry_price) / entry_price) * 100, 2)

    return {
        "symbol": symbol,
        "company": get_company_name(symbol),
        "sector": get_sector(symbol),
        "entry_date": entry_date,
        "entry_price": entry_price,
        "stop_price": stop_price,
        "target1_price": target1_price,
        "target2_price": target2_price,
        "target1_hit": target1_hit,
        "status": status,
        "max_high": max_high,
        "min_low": min_low,
        "max_fwd_gain": max_fwd_gain,
        "staged_pnl_pct": staged_pnl_pct,
        "static_pnl_pct": static_pnl_pct,
        "alpha_saved_pct": round(staged_pnl_pct - static_pnl_pct, 2),
        "half1_exit": f"{half1_reason} @ ₹{half1_exit_px:.2f} ({half1_exit_date})",
        "half2_exit": f"{half2_reason} @ ₹{half2_exit_px:.2f} ({half2_exit_date})",
        "verdict": verdict,
        "daily_logs": daily_logs,
    }


def build_forward_verification_suite(
    history: pd.DataFrame,
    max_dates: int = 8,
) -> dict[str, Any]:
    """Generates complete day-by-day forward trade verification database for recent sessions."""
    from pathlib import Path
    root_dir = Path(__file__).resolve().parent.parent
    liquid_file = root_dir / "data" / "universe_history.parquet"
    if liquid_file.exists():
        try:
            liq_syms = set(pd.read_parquet(liquid_file, columns=["Symbol"])["Symbol"])
            history = history[history["Symbol"].isin(liq_syms)].copy()
        except Exception:
            pass

    all_dates = sorted(history["Date"].drop_duplicates())
    if len(all_dates) < 5:
        return {"available_dates": [], "sessions": {}}

    target_dates = {"2026-10-01", "2026-09-30", "2026-09-28", "2026-09-25", "2026-09-21", "2026-09-18", "2026-09-15", "2026-09-11"}
    candidate_dates = [d for d in all_dates if d.strftime("%Y-%m-%d") in target_dates]
    if len(candidate_dates) < 5:
        candidate_dates = [d for d in all_dates[-max_dates:]]

    date_records: dict[str, Any] = {}
    available_dates: list[str] = []

    for asof in reversed(candidate_dates):
        d_str = asof.strftime("%Y-%m-%d")
        hist_asof = history[history["Date"] <= asof]
        reg = get_regime_at(hist_asof, asof)

        feat = compute_screener_features(hist_asof, asof)
        if feat.empty:
            continue

        # Extract shortlisted candidates across main strategies
        cands_set: set[str] = set()
        cands_meta: dict[str, list[str]] = {}

        # 2. Protocol Fortified
        proto = screen_protocol_v2(feat, top_n=5)
        for s in proto:
            cands_set.add(s.symbol)
            cands_meta.setdefault(s.symbol, []).append("Protocol Fortified")

        # 3. Relative Strength Leaders
        rs_picks = screen_relative_strength(feat, top_n=5)
        for s in rs_picks:
            cands_set.add(s.symbol)
            cands_meta.setdefault(s.symbol, []).append("Relative Strength Leader")

        # 4. Minervini & Qullamaggie
        miner = screen_minervini(feat, top_n=5)
        for s in miner:
            cands_set.add(s.symbol)
            cands_meta.setdefault(s.symbol, []).append("Minervini Template")

        qulla = screen_qullamaggie(feat, top_n=5)
        for s in qulla:
            cands_set.add(s.symbol)
            cands_meta.setdefault(s.symbol, []).append("Qullamaggie Breakout")

        # 5. Stan Weinstein Stage 2
        wein = screen_stan_weinstein(feat, top_n=5)
        for s in wein:
            cands_set.add(s.symbol)
            cands_meta.setdefault(s.symbol, []).append("Stan Weinstein Stage 2")

        # 6. CANSLIM Pivot
        cans = screen_canslim(feat, top_n=5)
        for s in cans:
            cands_set.add(s.symbol)
            cands_meta.setdefault(s.symbol, []).append("CANSLIM Pivot")

        # 7. Turtle & Darvas Box
        turt = screen_turtle_trading(feat, top_n=5)
        for s in turt:
            cands_set.add(s.symbol)
            cands_meta.setdefault(s.symbol, []).append("Turtle Trading (Donchian)")

        darv = screen_darvas_box(feat, top_n=5)
        for s in darv:
            cands_set.add(s.symbol)
            cands_meta.setdefault(s.symbol, []).append("Darvas Box Breakout")

        # 8. Pure 20-Day Price Breakout with Volume Thrust
        if "r20" in feat.columns and "rvol20" in feat.columns:
            bo_mask = (feat["Close"] > feat["r20"]) & (feat["rvol20"] >= 1.3)
            for _, r_bo in feat[bo_mask].head(6).iterrows():
                sym = str(r_bo["Symbol"])
                cands_set.add(sym)
                cands_meta.setdefault(sym, []).append("20-Day Volume Breakout")

        # Limit to top 15 unique candidates to keep payload light and fast
        selected_symbols = list(cands_set)[:15]

        # Get forward history after asof
        forward_history = history[(history["Date"] > asof) & (history["Symbol"].isin(selected_symbols))]

        trades: list[dict[str, Any]] = []
        for sym in selected_symbols:
            sim = simulate_single_stock_forward(sym, asof, forward_history)
            if sim:
                sim["strategies"] = cands_meta.get(sym, ["Quant Screen"])
                trades.append(sim)

        # Sort trades: WINs first, then staged P&L desc
        trades.sort(key=lambda t: t["staged_pnl_pct"], reverse=True)

        # Summary KPIs for this screening date
        if trades:
            wins = sum(1 for t in trades if t["staged_pnl_pct"] > 0)
            avg_staged = round(float(np.mean([t["staged_pnl_pct"] for t in trades])), 2)
            avg_static = round(float(np.mean([t["static_pnl_pct"] for t in trades])), 2)
            alpha_saved = round(avg_staged - avg_static, 2)
            win_rate = round((wins / len(trades)) * 100, 1)
        else:
            wins, avg_staged, avg_static, alpha_saved, win_rate = 0, 0.0, 0.0, 0.0, 0.0

        label = f"{d_str} ({asof.strftime('%A')})"
        if d_str == "2026-09-18":
            label += " • 20-Sep Weekend"
        elif d_str == "2026-09-15":
            label += " • Mid-Sep Defensive"

        date_records[d_str] = {
            "date": d_str,
            "label": label,
            "regime": reg.get("regime", "UNKNOWN"),
            "action": reg.get("action", "CASH"),
            "breadth": reg.get("pct_above_sma20", 0.0),
            "ew_index": reg.get("ew_close", 0.0),
            "sma20": reg.get("sma20", 0.0),
            "message": reg.get("message", ""),
            "summary": {
                "total_trades": len(trades),
                "wins": wins,
                "win_rate": win_rate,
                "avg_staged_pnl": avg_staged,
                "avg_static_pnl": avg_static,
                "alpha_saved": alpha_saved,
            },
            "trades": trades,
        }
        available_dates.append(d_str)

    trades_by_symbol: dict[str, list[dict[str, Any]]] = {}
    for d_str, rec in date_records.items():
        for t in rec.get("trades", []):
            sym = t["symbol"]
            item = dict(t)
            item["session_date"] = d_str
            item["session_label"] = rec.get("label", d_str)
            trades_by_symbol.setdefault(sym, []).append(item)

    return {
        "available_dates": available_dates,
        "sessions": date_records,
        "trades_by_symbol": trades_by_symbol,
        "all_symbols": sorted(list(trades_by_symbol.keys())),
    }
