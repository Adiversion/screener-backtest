#!/usr/bin/env python3
"""Grow the universe from 499 Nifty-500 names to every NSE cash equity.

    python scripts/fetch_universe.py --years 2
    python scripts/fetch_universe.py --years 2 --delivery-only
    python scripts/fetch_universe.py --sectors-only

Writes:
    data/nse_all_history.parquet   adjusted OHLCV for every EQ symbol
    data/delivery_history.parquet  bhavcopy delivery + trade counts
    data/sector_map.csv            symbol -> Industry (free, from index lists)

WHY TWO FILES AND NOT ONE
-------------------------
`universe_history.parquet` is the long-horizon core: 499 Nifty-500 names,
2018 onwards. It is what the survivorship-aware event studies run on, and it
must not be disturbed.

The breadth work needs more names than the core has, but not eight years of
history for all of them -- yfinance will rate-limit that long before it
finishes. So this writes a SEPARATE 2-year file for the full equity master.
Long-horizon statistics keep using the 500-name file; breadth and delivery
statistics use this one. Any result must say which file produced it.

THE ADJUSTED/UNADJUSTED TRAP
----------------------------
bhavcopy prices are RAW. yfinance prices are back-adjusted for splits and
dividends. The research protocol explicitly forbids "silently mixing adjusted
and unadjusted prices", so bhavcopy contributes **delivery quantity,
delivery percentage and trade counts only** -- none of which are affected by
price adjustment. Its OHLC columns are dropped on the floor. Anything else
would put split discontinuities straight back into the panel.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from protocol import ingest  # noqa: E402

# Never taken from bhavcopy: they are raw, and merging raw prices with
# adjusted ones is exactly the corruption the protocol warns about.
DELIVERY_ONLY = ["Symbol", "Date", "Volume", "DelivQty", "DelivPct", "Trades"]


def _clip(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    keep = [c for c in cols if c in df.columns]
    return df[keep].dropna(subset=["Symbol", "Date"]) if keep else df


def main() -> int:
    ap = argparse.ArgumentParser(description="Expand to the full NSE equity universe")
    ap.add_argument("--years", type=float, default=2.0,
                    help="years of adjusted price history to fetch")
    ap.add_argument("--start", default=None, help="explicit start date (overrides --years)")
    ap.add_argument("--data", default=str(ROOT / "data"))
    ap.add_argument("--limit", type=int, default=0, help="cap symbols (0 = all)")
    ap.add_argument("--delivery-only", action="store_true")
    ap.add_argument("--prices-only", action="store_true")
    ap.add_argument("--sectors-only", action="store_true")
    ap.add_argument("--sleep", type=float, default=0.0, help="pause between batches")
    args = ap.parse_args()

    out = Path(args.data)
    out.mkdir(parents=True, exist_ok=True)
    start = args.start or (pd.Timestamp.today() - pd.Timedelta(days=int(365.25 * args.years))).strftime("%Y-%m-%d")
    print(f"window: {start} -> today")

    # ---- sector map (cheap, always) -------------------------------------
    sectors = ingest.fetch_index_constituents()
    if sectors.empty:
        print("WARN: no sector data; portfolio sector caps will be unavailable")
    else:
        sectors.to_csv(out / "sector_map.csv", index=False)
        print(f"sectors : {len(sectors)} symbols, {sectors['Industry'].nunique()} "
              f"industries -> {out / 'sector_map.csv'}")
    if args.sectors_only:
        return 0

    # ---- delivery from bhavcopy ------------------------------------------
    if not args.prices_only:
        print("delivery: fetching one bhavcopy request per session ...")
        rows = []
        with ingest._session() as sess:
            import time
            for i, day in enumerate(pd.bdate_range(start=start, periods=int(365 * args.years) + 10)):
                try:
                    df = ingest.fetch_bhavdata(day.date(), sess)
                except Exception:
                    continue
                if not df.empty:
                    rows.append(_clip(df, DELIVERY_ONLY))
                if args.sleep:
                    time.sleep(args.sleep)
                if (i + 1) % 50 == 0:
                    print(f"  {i + 1} sessions, {sum(len(r) for r in rows):,} rows")
        if rows:
            delivery = pd.concat(rows, ignore_index=True).drop_duplicates(
                subset=["Symbol", "Date"]).sort_values(["Symbol", "Date"])
            path = out / "delivery_history.parquet"
            delivery.to_parquet(path, index=False)
            print(f"delivery: {len(delivery):,} rows, {delivery['Date'].nunique()} "
                  f"sessions, {delivery['Symbol'].nunique()} symbols -> {path}")
        else:
            print("delivery: nothing fetched")
    if args.delivery_only:
        return 0

    # ---- adjusted prices for the full EQ master --------------------------
    eq = ingest.fetch_nse_equity_symbols()
    if eq.empty:
        print("could not read the NSE equity master list; aborting")
        return 1
    syms = eq["symbol"].tolist()
    if args.limit:
        syms = syms[: args.limit]
    print(f"prices  : fetching {len(syms)} symbols from {start} ...")
    px = ingest.fetch_yfinance(syms, start=start, progress=True)
    if px.empty:
        print("prices: nothing fetched")
        return 1
    px = px[px["Symbol"].isin(set(syms))].drop_duplicates(subset=["Symbol", "Date"])
    px = px.sort_values(["Symbol", "Date"])
    path = out / "nse_all_history.parquet"
    px.to_parquet(path, index=False)
    print(f"prices  : {len(px):,} rows, {px['Symbol'].nunique()} symbols, "
          f"{px['Date'].nunique()} sessions -> {path}")

    missing = sorted(set(syms) - set(px["Symbol"].unique()))
    if missing:
        print(f"WARN: {len(missing)} of {len(syms)} symbols returned no price data "
              f"(delisted, illiquid, or new listings). First few: {missing[:8]}")
    eq.to_parquet(out / "nse_equity_master.parquet", index=False)
    print(f"master  : {len(eq)} EQ symbols -> {out / 'nse_equity_master.parquet'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())