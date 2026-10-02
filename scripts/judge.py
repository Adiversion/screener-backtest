#!/usr/bin/env python3
"""Judge a named stock: engine verdict, gates, screen tag, recent tape.

  python scripts/judge.py --symbols CUPID,MARINE

This is the research-analyst entry point. It answers one question per
symbol -- "good, watch, or reject?" -- and prints the evidence behind the
verdict: the blended score, every hard gate with its measured value, the
end-of-day screen tag, and the last 15 sessions so a human can check the
story by eye instead of trusting a number.

A symbol that is not in the panel is reported as OUTSIDE PANEL, never
silently skipped and never guessed at.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from protocol import quality, screen  # noqa: E402
from protocol.config import get, load_config  # noqa: E402
from protocol.data import load_history  # noqa: E402
from protocol.features import build_panel  # noqa: E402


def _recent(feat: pd.DataFrame, asof: pd.Timestamp, n: int = 15) -> pd.DataFrame:
    d = feat[feat["Date"] <= asof].tail(n)
    cols = ["Date", "Close", "Volume", "rvol20", "ret20", "ret120"]
    cols = [c for c in cols if c in d.columns]
    return d[cols].copy()


def judge_one(feat, cfg, asof, ranked):
    """Engine verdict for a single symbol, as a dict of reportable parts."""
    row = ranked[ranked["symbol"] == feat["Symbol"].iloc[0]]
    recent = _recent(feat, asof)
    if recent.empty:
        return {"status": "NO DATA", "symbol": feat["Symbol"].iloc[0]}
    last = recent.iloc[-1]
    failed = str(row["failed"].iloc[0]) if not row.empty else "not scored"
    rec = {
        "status": "GATES FAILED" if failed else "CLEARS GATES",
        "symbol": feat["Symbol"].iloc[0],
        "date": str(pd.Timestamp(last["Date"]).date()),
        "close": quality._num(last.get("Close")),
        "rvol20": quality._num(last.get("rvol20")),
        "atrpct": quality._num(last.get("atrpct")),
        "prox52": quality._num(last.get("prox52")),
        "ret20": quality._num(last.get("ret20")),
        "ret120": quality._num(last.get("ret120")),
        "failed": failed,
        "recent": recent,
    }
    if not row.empty:
        r = row.iloc[0]
        rec["score"] = quality._num(r.get("score"))
        rec["coverage"] = quality._num(r.get("coverage"))
        rec["data_status"] = r.get("data_status")
        rec["percentile_rank"] = float((ranked["score"] < r["score"]).mean()) if \
            ranked["score"].notna().any() else None
        rec["reason"] = quality.reason(r, cfg)
        rec["gates"] = [
            {"criterion": g["criterion"], "value": g["value"],
             "threshold": g["threshold"], "passed": g["passed"]}
            for g in r["gates"]
        ]
    return rec


def main() -> int:
    ap = argparse.ArgumentParser(description="Judge named stocks against the engine")
    ap.add_argument("--config", default=None)
    ap.add_argument("--data", default=str(ROOT / "data" / "universe_history.parquet"))
    ap.add_argument("--asof", default=None)
    ap.add_argument("--symbols", required=True)
    ap.add_argument("--recent", type=int, default=15)
    ap.add_argument("--universe", default="panel",
                    help="'panel' scores against the whole benchmark universe "
                         "so percentiles mean something, or comma-separated "
                         "symbols to score against a small group")
    args = ap.parse_args()

    cfg = load_config(args.config)
    history = load_history(args.data)
    # Default to the LATEST session in the data, not the protocol's
    # validation_end. That cutoff is a backtest window boundary frozen for the
    # discovery/validation split; using it here would answer "what do I think of
    # this stock TODAY?" with a verdict from weeks ago and silently hide newer
    # bars. Pass --asof to judge a specific session on purpose.
    if args.asof:
        asof = pd.Timestamp(args.asof)
    else:
        available = pd.Timestamp(history["Date"].max())
        asof = max(available, pd.Timestamp(get(cfg, "validation.validation_end")))
    history = history[history["Date"] <= asof]
    syms = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]

    known = set(history["Symbol"].unique())
    wanted = [s for s in syms if s in known]
    missing = [s for s in syms if s not in wanted]
    if missing:
        print("OUTSIDE PANEL (no data in this universe, cannot be judged): "
              + ", ".join(missing))
        print()
    if not wanted:
        return 1

    # Percentiles are only meaningful cross-sectionally, so the comparison set
    # is the whole universe by default. Ranking a stock against itself and one
    # other name would hand it a 100th-percentile component on no evidence.
    peers = list(known) if args.universe == "panel" else [
        s.strip().upper() for s in args.universe.split(",") if s.strip()]
    panel = build_panel(history[history["Symbol"].isin(peers)])
    ranked = quality.score_frame(quality._frames(panel, cfg, asof, 20), cfg)
    screen_rows = screen.screen(panel, cfg, asof)
    cleared = int((ranked["failed"] == "").sum()) if "failed" in ranked else 0
    print(f"scored against {len(ranked)} symbols in the comparison set; "
          f"{cleared} clear every gate\n")

    for sym in wanted:
        feat = panel.get(sym)
        if feat is None:
            print(f"{sym}: no feature frame")
            continue
        rec = judge_one(feat, cfg, asof, ranked)
        print("=" * 78)
        print(f"{rec['symbol']}  [{rec['status']}]  as of {rec['date']}")
        print("=" * 78)
        if rec.get("reason"):
            pct = rec.get("percentile_rank")
            pctl = f" (rank {pct:.0%} of panel)" if pct is not None else ""
            print(f"  score {rec['score']:.4f}{pctl}  coverage {rec['coverage']:.0%} "
                  f"{rec['data_status']}")
            print(f"  {rec['reason']}")
            print()
            print(f"  {'gate':<38}{'value':>14}  {'threshold':<26}ok")
            for g in rec["gates"]:
                val = g["value"]
                val = f"{val:,.4f}" if isinstance(val, (int, float)) else str(val)
                print(f"  {g['criterion']:<38}{val:>14}  {g['threshold']:<26}"
                      f"{'Y' if g['passed'] else 'N'}")
        hit = screen_rows[screen_rows["symbol"] == sym]
        if not hit.empty:
            s = hit.iloc[0]
            print(f"\n  screen tag: {s['tag']}   state: {s['state']}   "
                  f"R20: {s['reference']}   closing_range: {s['closing_range']}")
        print("\n  recent tape (date, close, volume, rvol20, ret20, ret120):")
        with pd.option_context("display.width", 120, "display.max_columns", 10):
            print(rec["recent"].to_string(index=False))
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())