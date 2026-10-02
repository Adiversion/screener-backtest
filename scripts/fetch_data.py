#!/usr/bin/env python3
"""Grow the backtest universe from free NSE sources.

  python scripts/fetch_data.py --source nifty500 --start 2018-01-01
  python scripts/fetch_data.py --source bhavdata --days 400
  python scripts/fetch_data.py --source bhavdata --date 2026-10-01 --append data/universe_history.parquet
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from protocol.ingest import fetch_bhavdata, fetch_nifty500_symbols, fetch_yfinance  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["bhavdata", "nifty500"], required=True)
    ap.add_argument("--date", default=None)
    ap.add_argument("--days", type=int, default=1)
    ap.add_argument("--start", default="2018-01-01")
    ap.add_argument("--end", default=None)
    ap.add_argument("--limit", type=int, default=500)
    ap.add_argument("--out", default=str(ROOT / "data" / "universe_history.parquet"))
    ap.add_argument("--append", default=None)
    args = ap.parse_args()

    if args.source == "nifty500":
        syms = fetch_nifty500_symbols()[: args.limit]
        print(f"fetching {len(syms)} symbols via yfinance from {args.start} ...")
        df = fetch_yfinance(syms, args.start, args.end)
    else:
        end = pd.to_datetime(args.date) if args.date else pd.Timestamp(date.today())
        frames = []
        for i in range(args.days):
            d = (end - timedelta(days=i)).normalize()
            if d.weekday() >= 5:
                continue
            try:
                frames.append(fetch_bhavdata(d))
                print(f"  {d.date()}: {len(frames[-1])} rows")
            except Exception as exc:  # network / holiday
                print(f"  {d.date()}: skipped ({exc})")
        df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    out = Path(args.append or args.out)
    if args.append and out.exists():
        df = pd.concat([pd.read_parquet(out), df], ignore_index=True)
    df.to_parquet(out, index=False)
    print(f"wrote {len(df)} rows -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
