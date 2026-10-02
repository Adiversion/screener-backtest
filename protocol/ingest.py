"""Optional ingest layer (free NSE sources).

- fetch_bhavdata(date) : official full Bhavcopy (OHLCV + delivery + trades)
- fetch_yfinance(...)  : adjusted OHLCV for an explicit symbol list
- fetch_nifty500_symbols() : index constituent CSV

The backtest itself never requires the network; this exists so the universe
can be grown toward the full Nifty 500 on Replit or in CI.
"""
from __future__ import annotations

import io
from datetime import date
from typing import Iterable

import pandas as pd
import requests

BAVCOPY_URL = "https://archives.nseindia.com/products/content/sec_bhavdata_full_{d}.csv"
NIFTY500_URL = "https://archives.nseindia.com/content/indices/ind_nifty500list.csv"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; screener-backtest/1.0)"}

_NSE_COLS = {
    "SYMBOL": "Symbol", "OPEN": "Open", "HIGH": "High", "LOW": "Low",
    "CLOSE": "Close", "TTL_TRD_QNTY": "Volume", "DELIV_QTY": "DelivQty",
    "DELIV_PER": "DelivPct", "NO_OF_TRADES": "Trades", "SERIES": "Series",
}


def fetch_bhavdata(day: date | str, session: requests.Session | None = None) -> pd.DataFrame:
    d = pd.to_datetime(day).strftime("%d%m%Y")
    sess = session or requests.Session()
    resp = sess.get(BAVCOPY_URL.format(d=d), headers=HEADERS, timeout=30)
    resp.raise_for_status()
    df = pd.read_csv(io.StringIO(resp.text))
    df.columns = [c.strip().upper() for c in df.columns]
    df = df.rename(columns=_NSE_COLS)
    keep = [c for c in _NSE_COLS.values() if c in df.columns]
    df = df[keep]
    df["Date"] = pd.to_datetime(day)
    if "Series" in df.columns:
        df = df[df["Series"].isin(["EQ", "BE", "BZ"])]
    return df.reset_index(drop=True)


def fetch_nifty500_symbols(session: requests.Session | None = None) -> list[str]:
    sess = session or requests.Session()
    resp = sess.get(NIFTY500_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    df = pd.read_csv(io.StringIO(resp.text))
    col = "Symbol" if "Symbol" in df.columns else df.columns[2]
    return [str(s).strip().upper() for s in df[col].tolist()]


def fetch_yfinance(symbols: Iterable[str], start: str, end: str | None = None,
                   batch: int = 40) -> pd.DataFrame:
    """Adjusted daily OHLCV for NSE tickers. Symbols without '.NS' get it."""
    import yfinance as yf

    end = end or date.today().isoformat()
    frames: list[pd.DataFrame] = []
    syms = [s if s.endswith(".NS") else f"{s}.NS" for s in symbols]
    for i in range(0, len(syms), batch):
        chunk = syms[i:i + batch]
        raw = yf.download(chunk, start=start, end=end, interval="1d",
                          group_by="ticker", auto_adjust=True, progress=False, threads=True)
        for ns in chunk:
            try:
                one = raw[ns].dropna(how="all").reset_index()
            except KeyError:
                continue
            if one.empty:
                continue
            one["Symbol"] = ns.replace(".NS", "")
            frames.append(one.rename(columns={"index": "Date"}))
    if not frames:
        return pd.DataFrame(columns=["Date", "Symbol", "Open", "High", "Low", "Close", "Volume"])
    out = pd.concat(frames, ignore_index=True)
    out["Date"] = pd.to_datetime(out["Date"]).dt.tz_localize(None).dt.normalize()
    return out[["Date", "Symbol", "Open", "High", "Low", "Close", "Volume"]]
