#!/usr/bin/env python3
"""Comparative Benchmark Runner: GitHub Screeners vs Our Quant Engine.

Runs 5 screening methodologies on NSE as of 2026-09-01:
1. Minervini Trend Template (RyanJHamby/stock-screener, icedevil2001)
2. Qullamaggie Breakout & HTF (axidzz/Qullamaggie-Setups)
3. CANSLIM Pivot Breakout (William O'Neil)
4. PKScreener VCP (pkjmesra/PKScreener)
5. Protocol v2 Fortified Screener

Simulates each portfolio across September 2026 under both Passive and Dynamic Exits.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from protocol.data import load_history  # noqa: E402
from protocol.exits import ExitStrategy, simulate_dynamic_trade  # noqa: E402
from protocol.github_screeners import (  # noqa: E402
    compute_screener_features,
    screen_canslim,
    screen_minervini,
    screen_pkscreener_vcp,
    screen_protocol_v2,
    screen_qullamaggie,
)


def run_benchmark(data_path: str, asof_date: str = "2026-09-01", top_n: int = 5) -> dict:
    print(f"Loading market dataset from {data_path}...")
    t0 = time.time()
    df = load_history(data_path)
    print(f"Loaded {len(df):,} rows in {time.time()-t0:.2f}s.")

    print(f"Computing technical features as of {asof_date}...")
    t1 = time.time()
    features = compute_screener_features(df, asof_date)
    print(f"Computed features for {len(features):,} active symbols in {time.time()-t1:.2f}s.")

    # Run each screener
    screeners = {
        "Minervini Trend Template": screen_minervini(features, top_n=top_n),
        "Qullamaggie Breakout": screen_qullamaggie(features, top_n=top_n),
        "CANSLIM Pivot": screen_canslim(features, top_n=top_n),
        "PKScreener VCP": screen_pkscreener_vcp(features, top_n=top_n),
        "Protocol v2 Fortified": screen_protocol_v2(features, top_n=top_n),
    }

    # Pre-slice symbol bars with forward history up to 2026-10-05
    all_picked_symbols = set()
    for res_list in screeners.values():
        for item in res_list:
            all_picked_symbols.add(item.symbol)

    symbol_bars = {}
    for sym in all_picked_symbols:
        s_df = df[df["Symbol"] == sym].sort_values("Date").reset_index(drop=True)
        # Precompute indicators for exit evaluation
        s_df["ema10"] = s_df["Close"].ewm(span=10, adjust=False).mean()
        s_df["ema20"] = s_df["Close"].ewm(span=20, adjust=False).mean()
        s_df["vol_sma20"] = s_df["Volume"].rolling(20).mean().shift(1)
        prev_c = s_df["Close"].shift(1)
        tr = pd.concat([
            s_df["High"] - s_df["Low"],
            (s_df["High"] - prev_c).abs(),
            (s_df["Low"] - prev_c).abs()
        ], axis=1).max(axis=1)
        s_df["atr14"] = tr.ewm(alpha=1.0 / 14, adjust=False).mean()
        symbol_bars[sym] = s_df

    # Evaluate across exit strategies
    exit_strategies = [
        ExitStrategy.PASSIVE_HOLD,
        ExitStrategy.STRUCTURE_EMA20,
        ExitStrategy.CHANDELIER_ATR,
        ExitStrategy.QULLAMAGGIE_2R,
    ]

    benchmark_summary = {}

    for name, picks in screeners.items():
        benchmark_summary[name] = {"picks": picks, "results": {}}
        for strat in exit_strategies:
            outcomes = []
            for p in picks:
                bars = symbol_bars.get(p.symbol)
                if bars is not None:
                    res = simulate_dynamic_trade(p.symbol, bars, asof_date, exit_strategy=strat)
                    if res is not None:
                        outcomes.append(res)
            if outcomes:
                rets = [o.net_pnl_pct for o in outcomes]
                wins = [r for r in rets if r > 0]
                benchmark_summary[name]["results"][strat.value] = {
                    "count": len(outcomes),
                    "mean_pnl": np.mean(rets),
                    "win_rate": len(wins) / len(outcomes),
                    "max_pnl": np.max(rets),
                    "min_pnl": np.min(rets),
                    "outcomes": outcomes,
                }

    return benchmark_summary


def format_markdown_report(summary: dict, asof_date: str) -> str:
    lines = [
        f"# GitHub Screeners Benchmark Report ({asof_date})",
        "",
        "Evaluation of open-source momentum screeners against our fortified quant engine across September 2026.",
        "",
        "## 1. Top Candidates Selected on 2026-09-01",
        "",
        "| Screener | Top Picks (Ranked) | Key Selection Drivers |",
        "| :--- | :--- | :--- |",
    ]

    for name, data in summary.items():
        picks_str = ", ".join([f"`{p.symbol}` ({p.ret20*100:+.1f}%, {p.rvol20:.1f}x)" for p in data["picks"]])
        lines.append(f"| **{name}** | {picks_str} |")

    lines.extend([
        "",
        "## 2. Performance Comparison Across Exit Strategies",
        "",
        "| Screener | Exit Engine | Mean Return | Win Rate | Best Trade | Worst Trade |",
        "| :--- | :--- | :--- | :--- | :--- | :--- |",
    ])

    for name, data in summary.items():
        for strat_name, metrics in data["results"].items():
            mean_ret = f"{metrics['mean_pnl']*100:+.2f}%"
            win_rate = f"{metrics['win_rate']*100:.1f}%"
            best_trade = f"{metrics['max_pnl']*100:+.2f}%"
            worst_trade = f"{metrics['min_pnl']*100:+.2f}%"
            lines.append(f"| {name} | `{strat_name}` | **{mean_ret}** | {win_rate} | {best_trade} | {worst_trade} |")

    lines.extend([
        "",
        "## 3. Trade-by-Trade Performance Log",
        "",
    ])

    for name, data in summary.items():
        lines.append(f"### {name}")
        for strat_name in ["PASSIVE_HOLD", "STRUCTURE_EMA20", "QULLAMAGGIE_2R"]:
            metrics = data["results"].get(strat_name)
            if not metrics:
                continue
            lines.append(f"#### Exit Strategy: `{strat_name}`")
            lines.append("| Symbol | Entry Price | Exit Date | Exit Price | Exit Reason | Net Return | Days Held |")
            lines.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
            for o in metrics["outcomes"]:
                d_str = str(o.exit_date)[:10]
                lines.append(f"| `{o.symbol}` | ₹{o.entry_px:.2f} | {d_str} | ₹{o.exit_px:.2f} | `{o.exit_reason}` | **{o.net_pnl_pct*100:+.2f}%** | {o.sessions_held}d |")
            lines.append("")

    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Benchmark GitHub Screeners")
    ap.add_argument("--data", default=str(ROOT / "data" / "nse_all_history.parquet"))
    ap.add_argument("--asof", default="2026-09-01")
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--report", default=str(ROOT / "reports" / "SCREENER_BENCHMARK.md"))
    args = ap.parse_args()

    summary = run_benchmark(args.data, asof_date=args.asof, top_n=args.top)
    md = format_markdown_report(summary, args.asof)

    out_file = Path(args.report)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(md, encoding="utf-8")
    print(f"Report written to {out_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
