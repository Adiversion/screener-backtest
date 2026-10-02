#!/usr/bin/env python3
"""Fetch recent NSE full-bhavcopy delivery data (one request per session).

  python scripts/fetch_delivery.py --days 45
  python scripts/fetch_delivery.py --days 10 --date 2026-10-01
  python scripts/fetch_delivery.py --days 45 --append      # extend what exists

Writes data/delivery_history.parquet with Symbol, Date, DelivQty, DelivPct,
Trades. `protocol.data.load_history` merges it automatically when present, and
`protocol.features` then computes deliv_pct / deliv_pct_rel / deliv_rvol20 /
avg_trade_size / ats_rel — which is what filter F4 needs.

NSE is rate-limited and sometimes blocks; holidays are skipped with a warning.
Delivery history is only available per day (no bulk endpoint), so this is a
bounded recent window, not 2018-2026.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from protocol.ingest import fetch_bhavdata  # noqa: E402

KEEP = ["Symbol", "Date", "DelivQty", "DelivPct", "Trades"]


def main() -> int:
    ap = argparse.ArgumentParser(description="Fetch NSE delivery data")
    ap.add_argument("--days", type=int, default=45)
    ap.add_argument("--date", default=None, help="end date (default: today)")
    ap.add_argument("--out", default=str(ROOT / "data" / "delivery_history.parquet"))
    ap.add_argument("--append", action="store_true")
    args = ap.parse_args()

    end = pd.to_datetime(args.date).normalize() if args.date else pd.Timestamp(date.today())
    frames, got, tried = [], 0, 0
    for i in range(args.days):
        day = (end - timedelta(days=i)).normalize()
        if day.weekday() >= 5:
            continue
        tried += 1
        try:
            df = fetch_bhavdata(day)
        except Exception as exc:  # holiday / rate limit / network
            print(f"  {day.date()}: skipped ({type(exc).__name__})")
            continue
        if df.empty:
            continue
        frames.append(df[[c for c in KEEP if c in df.columns]])
        got += 1
        print(f"  {day.date()}: {len(df)} rows")

    if not frames:
        print(f"BLOCKED: no bhavcopy sessions retrieved ({tried} attempted).")
        return 1

    out = Path(args.out)
    df = pd.concat(frames, ignore_index=True)
    if args.append and out.exists():
        df = pd.concat([pd.read_parquet(out), df], ignore_index=True)
    df = df.drop_duplicates(subset=["Symbol", "Date"]).sort_values(["Symbol", "Date"])
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    print(f"wrote {len(df)} rows ({got} sessions, {df['Symbol'].nunique()} symbols) -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
