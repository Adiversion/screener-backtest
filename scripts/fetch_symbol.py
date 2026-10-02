#!/usr/bin/env python3
"""Pull symbols that are outside the benchmark panel and judge them anyway.

  python scripts/fetch_symbol.py --symbols MOREPENLAB,JGCHEM
  python scripts/fetch_symbol.py --symbols MOREPENLAB --judge

The benchmark universe is the 499 Nifty-500 names, so a small-cap outside it
cannot be scored cross-sectionally at all: a percentile against itself is 100%
by construction and means nothing. This fetches the missing symbols from
yfinance, writes them ALONGSIDE the panel into a separate ad-hoc dataset
(never over `data/universe_history.parquet`), and hands that to `judge.py` so
the stock is ranked against the same 499 names everything else is ranked
against.

Point in time is unaffected -- adjusted OHLCV, features computed per symbol,
gates and percentiles computed within the single session being judged.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from protocol.config import load_config  # noqa: E402
from protocol.data import load_history  # noqa: E402


def fetch(symbols, period="5y") -> pd.DataFrame:
    """Adjusted daily OHLCV for the named NSE symbols, as one long frame."""
    import yfinance as yf

    frames = []
    for sym in symbols:
        raw = yf.download(f"{sym}.NS", period=period, auto_adjust=True,
                          progress=False)
        if raw is None or len(raw) == 0:
            print(f"{sym}: no data returned")
            continue
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.get_level_values(0)
        d = raw.reset_index()
        # yfinance returns 'Close'/'Volume'; normalise to the engine's schema
        d = d.rename(columns={c: str(c).strip().capitalize()
                              for c in d.columns})
        d = d.rename(columns={"Date": "Date", "Timestamp": "Date"})
        d["Symbol"] = sym
        missing = {"Date", "Symbol", "Open", "High", "Low", "Close",
                   "Volume"} - set(d.columns)
        if missing:
            print(f"{sym}: unexpected columns {list(d.columns)}, skipping")
            continue
        frames.append(d[["Date", "Symbol", "Open", "High", "Low", "Close",
                         "Volume"]])
        print(f"{sym}: {len(d)} sessions, "
              f"{pd.Timestamp(d['Date'].iloc[0]).date()} to "
              f"{pd.Timestamp(d['Date'].iloc[-1]).date()}")
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="Judge a symbol outside the panel")
    ap.add_argument("--symbols", required=True)
    ap.add_argument("--panel", default=str(ROOT / "data" / "universe_history.parquet"))
    ap.add_argument("--period", default="5y")
    ap.add_argument("--outdir", default=str(ROOT / "data"))
    ap.add_argument("--judge", action="store_true",
                    help="run scripts/judge.py on the merged dataset afterwards")
    args = ap.parse_args()

    cfg = load_config()
    syms = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    extra = fetch(syms, args.period)
    if extra.empty:
        return 1

    panel = load_history(args.panel)
    known = set(panel["Symbol"].unique())
    fresh = extra[~extra["Symbol"].isin(known)]
    if fresh.empty:
        print("all requested symbols are already in the panel")
        return 0

    merged = pd.concat([panel, fresh], ignore_index=True)
    out = Path(args.outdir) / f"adhoc_{'_'.join(sorted(fresh['Symbol'].unique()))}.parquet"
    merged.to_parquet(out, index=False)
    print(f"wrote {out} ({len(merged)} rows, "
          f"{merged['Symbol'].nunique()} symbols including "
          f"{len(fresh['Symbol'].unique())} ad-hoc)")

    if args.judge:
        cmd = [sys.executable, str(ROOT / "scripts" / "judge.py"),
               "--data", str(out), "--symbols", ",".join(syms)]
        return subprocess.call(cmd)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())