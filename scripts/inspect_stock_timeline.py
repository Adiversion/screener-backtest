#!/usr/bin/env python3
"""Inspect a single stock's multi-framework readiness timeline across dates.

Usage:
  python scripts/inspect_stock_timeline.py --symbol SMCGLOBAL --start 2026-09-01 --end 2026-09-30
  python scripts/inspect_stock_timeline.py --symbol SMCGLOBAL --month 2026-09 --details

Identifies the exact day when a stock cleared the highest number of institutional
screening frameworks (Minervini, Qullamaggie, Weinstein Stage 2, CANSLIM,
PKScreener VCP, Protocol Fortified, Darvas Box, Turtle, Wyckoff, RS Leader).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from protocol.data import load_history
from protocol.frameworks import FRAMEWORKS
from protocol.github_screeners import compute_screener_features


def inspect_symbol_timeline(
    data_path: str,
    symbol: str,
    start_date: str,
    end_date: str,
    show_details: bool = False,
) -> dict[str, Any]:
    symbol = symbol.strip().upper()
    df = load_history(data_path)

    # Filter to requested symbol
    sym_rows = df[df["Symbol"].str.upper() == symbol].copy()
    if sym_rows.empty:
        raise ValueError(f"Symbol '{symbol}' not found in {data_path}")

    sym_rows["Date"] = pd.to_datetime(sym_rows["Date"]).dt.normalize()
    sym_rows = sym_rows.sort_values("Date").reset_index(drop=True)

    start = pd.Timestamp(start_date).normalize()
    end = pd.Timestamp(end_date).normalize()

    # Sessions in range
    sessions = sym_rows[(sym_rows["Date"] >= start) & (sym_rows["Date"] <= end)]["Date"].tolist()
    if not sessions:
        raise ValueError(f"No trading sessions found for {symbol} between {start.date()} and {end.date()}")

    # Check delivery data
    deliv_map_cache: dict[pd.Timestamp, dict[str, float]] = {}
    deliv_path = Path(data_path).parent / "delivery_history.parquet"
    if deliv_path.exists():
        try:
            ddf = pd.read_parquet(deliv_path)
            ddf["Date"] = pd.to_datetime(ddf["Date"]).dt.normalize()
            for d, sub in ddf[ddf["Symbol"] == symbol].groupby("Date"):
                if not sub.empty and "DelivPct" in sub.columns:
                    val = float(sub.iloc[-1]["DelivPct"])
                    deliv_map_cache[d] = {symbol: val}
        except Exception:
            pass

    timeline = []
    print(f"\nAnalyzing {symbol} across {len(sessions)} sessions ({start.date()} to {end.date()})...\n")

    for dt in sessions:
        # History up to this session
        hist_up_to = sym_rows[sym_rows["Date"] <= dt]
        if len(hist_up_to) < 50:
            continue

        feat = compute_screener_features(hist_up_to, asof_date=dt)
        if feat.empty:
            continue

        sym_feat = feat[feat["Symbol"] == symbol]
        if sym_feat.empty:
            continue

        row_feat = sym_feat.iloc[0]
        cur_close = float(row_feat["Close"])
        cur_vol = float(row_feat["Volume"])
        cur_rvol = float(row_feat["rvol20"])
        cur_r20 = float(row_feat["r20"])
        cur_stop = float(row_feat.get("base_low20", cur_close * 0.93))
        cur_adr = float(row_feat.get("adr20", 0.03)) * 100.0

        # Run all 13 canonical frameworks
        passed_frameworks: list[str] = []
        deliv_map = deliv_map_cache.get(dt, None)

        for label, screener_fn, need_arg in FRAMEWORKS:
            kwargs: dict[str, Any] = {"top_n": 100, "min_turnover_cr": 0.05}
            if need_arg == "deliv_map" and deliv_map:
                kwargs["deliv_map"] = deliv_map
            try:
                res = screener_fn(feat, **kwargs)
                if any(r.symbol == symbol for r in res):
                    passed_frameworks.append(label)
            except Exception:
                pass

        score = len(passed_frameworks)
        timeline.append({
            "date": dt.strftime("%Y-%m-%d"),
            "close": cur_close,
            "volume": cur_vol,
            "rvol20": cur_rvol,
            "r20": cur_r20,
            "stop": cur_stop,
            "adr_pct": cur_adr,
            "score": score,
            "frameworks": passed_frameworks,
        })

    # Summary and Peak analysis
    if not timeline:
        print("No valid timeline records could be generated.")
        return {}

    t_df = pd.DataFrame(timeline)
    max_score = t_df["score"].max()
    peak_days = t_df[t_df["score"] == max_score]

    # Print Table
    print("=" * 100)
    print(f"📊 {symbol} INSTITUTIONAL READINESS TIMELINE ({start.date()} → {end.date()})")
    print("=" * 100)
    print(f"{'Date':12} | {'Close':>8} | {'RVOL':>6} | {'Score':>7} | {'Verdict / Setup State':<22} | Key Passing Frameworks")
    print("-" * 100)

    for item in timeline:
        sc = item["score"]
        is_peak = (sc == max_score and sc >= 3)
        fw_count_str = f"{sc}/{len(FRAMEWORKS)}"
        
        if is_peak:
            verdict = "🔥 PRIME BREAKOUT READY"
            badge = "★"
        elif sc >= 5:
            verdict = "⚡ STRONG CONFLUENCE"
            badge = "•"
        elif sc >= 3:
            verdict = "📈 BASE EXPANSION"
            badge = " "
        elif item["rvol20"] < 0.75:
            verdict = "💤 VOLUME DRY-UP BASE"
            badge = " "
        else:
            verdict = "⏳ CONSOLIDATING"
            badge = " "

        fw_str = ", ".join(item["frameworks"][:3])
        if len(item["frameworks"]) > 3:
            fw_str += f" (+{len(item['frameworks']) - 3} more)"
        if not item["frameworks"]:
            fw_str = "None"

        print(f"{item['date']:12} | ₹{item['close']:7.2f} | {item['rvol20']:5.2f}x | {badge} {fw_count_str:>5} | {verdict:<22} | {fw_str}")

    print("=" * 100)

    # Detailed Audit of High-Confluence Setup Days (score >= 5 or max_score)
    top_trigger_days = t_df[t_df["score"] >= max(5, max_score - 1)]
    if top_trigger_days.empty and not peak_days.empty:
        top_trigger_days = peak_days

    print(f"\n🎯 PRIME ENTRY TRIGGER SESSIONS IDENTIFIED: {len(top_trigger_days)}")
    for idx, (_, trig) in enumerate(top_trigger_days.iterrows(), 1):
        trig_date = trig["date"]
        trig_close = trig["close"]
        trig_stop = trig["stop"]
        trig_rvol = trig["rvol20"]
        trig_score = trig["score"]
        trig_fws = trig["frameworks"]
        risk_pct = ((trig_close - trig_stop) / trig_close) * 100.0
        target_2r = trig_close + 2.0 * (trig_close - trig_stop)
        target_2r_pct = ((target_2r - trig_close) / trig_close) * 100.0

        print(f"\n   [{idx}] TRIGGER DATE: {trig_date}  (Score: {trig_score}/{len(FRAMEWORKS)} Frameworks)")
        print(f"       • Buy / Entry Level: ₹{trig_close:.2f} (Next-Day Open or Pivot Clear)")
        print(f"       • 20-Day Resistance: ₹{trig['r20']:.2f}")
        print(f"       • Relative Volume: {trig_rvol:.2f}x average")
        print(f"       • Structural Stop Loss: ₹{trig_stop:.2f} (-{risk_pct:.1f}%)")
        print(f"       • Standard 2R Profit Target: ₹{target_2r:.2f} (+{target_2r_pct:.1f}%)")
        print(f"       • Confluence Frameworks: {', '.join(trig_fws)}")

        post_sessions = sym_rows[sym_rows["Date"] > pd.Timestamp(trig_date).normalize()].head(10)
        if not post_sessions.empty:
            max_fwd_px = post_sessions["High"].max()
            max_fwd_gain = (max_fwd_px - trig_close) / trig_close * 100.0
            last_px = post_sessions.iloc[-1]["Close"]
            last_gain = (last_px - trig_close) / trig_close * 100.0
            print(f"       📈 Subsequent Outcome (Next {len(post_sessions)} sessions): Peak ₹{max_fwd_px:.2f} ({max_fwd_gain:+.1f}%), Closed at ₹{last_px:.2f} ({last_gain:+.1f}%)")
    print("=" * 100 + "\n")

    best_trig = top_trigger_days.iloc[0]
    return {
        "symbol": symbol,
        "peak_date": best_trig["date"],
        "peak_score": int(best_trig["score"]),
        "peak_frameworks": best_trig["frameworks"],
        "timeline": timeline,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Inspect single stock multi-framework readiness timeline")
    ap.add_argument("--symbol", required=True, help="NSE ticker symbol e.g. SMCGLOBAL")
    ap.add_argument("--start", default="2026-09-01", help="Start date (YYYY-MM-DD)")
    ap.add_argument("--end", default="2026-09-30", help="End date (YYYY-MM-DD)")
    ap.add_argument("--month", default=None, help="Convenience format e.g. 2026-09")
    ap.add_argument("--data", default=str(ROOT / "data" / "nse_all_history.parquet"))
    ap.add_argument("--details", action="store_true", help="Print full framework details")
    args = ap.parse_args()

    start = args.start
    end = args.end
    if args.month:
        start = f"{args.month}-01"
        end = f"{args.month}-30"

    inspect_symbol_timeline(
        data_path=args.data,
        symbol=args.symbol,
        start_date=start,
        end_date=end,
        show_details=args.details,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
