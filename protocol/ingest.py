"""Ingest layer: free NSE / yfinance sources for growing the universe.

Sources (all verified reachable, no API key):

  fetch_bhavdata(date)        official full Bhavcopy: OHLCV + delivery + trades
  fetch_yfinance(symbols,..)  adjusted daily OHLCV for an explicit symbol list
  fetch_nifty500_symbols()    Nifty-500 constituents
  fetch_nse_equity_symbols()  the FULL NSE cash-equity master list (~2,400 EQ)
  fetch_index_constituents()  Nifty Total Market / 500, WITH the Industry column
  fetch_index_history()       Nifty 50 / sector index OHLCV for regime + beta

Why the master list matters: the backtest universe was 499 Nifty-500 names,
but the user's actual tradable universe is every NSE cash equity. `EQUITY_L.csv`
is the authoritative list and carries `SERIES`, which is how ETFs, SME stocks
and depository receipts get excluded -- the spec (`chatgpt.txt`, DATA UNIVERSE)
explicitly requires "exclude ETFs, exclude indices" and forbids silently
substituting an index for the market.

Why the index history matters: without it the only "market" available is an
equal-weight cross-sectional mean, which is a weak regime control. A real
index gives honest beta and lets the cross-sectional tests claim to be
market-aware.

None of this is required to run the backtest; the engine never needs the
network.
"""
from __future__ import annotations

import io
from datetime import date
from typing import Iterable

import pandas as pd
import requests

BAVCOPY_URL = "https://archives.nseindia.com/products/content/sec_bhavdata_full_{d}.csv"
NIFTY500_URL = "https://archives.nseindia.com/content/indices/ind_nifty500list.csv"
TOTAL_MARKET_URL = "https://archives.nseindia.com/content/indices/ind_niftytotalmarket_list.csv"
EQUITY_MASTER_URL = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; screener-backtest/1.0)"}

# NSE master-list SERIES codes. Only ordinary cash equity is wanted.
KEEP_SERIES = {"EQ"}
# SERIES codes we deliberately drop, named so the filter is auditable.
DROP_SERIES = {
    "BE": "ETF / closed-end", "ETF": "ETF", "ETFS": "ETF", "SETFS": "ETF",
    "ETFCG": "ETF close", "IV": "SME trading", "SM": "SME", "IL": "income loan / IL&FS",
    "BM": "bond", "BL": "bond", "PC": "partly converted", "PGC": "pre-open depository",
    "MF": "mutual fund", "PP": "derivative", "NDM": "non-deliverable",
}
# Name fragments for funds and trusts that slip through with an EQ series.
FUND_NAME_RE = r"ETF|ETFS|BEES|SETFS|INDEX FUND|MUTUAL FUND|INVITATION|REIT|SIR|FUND$| TRUST$|UNIT$"


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


def _get(url: str, session: requests.Session | None = None, timeout: int = 30) -> str:
    s = session or _session()
    resp = s.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.text


# Accept both the legacy (OPEN/HIGH/...) and current (OPEN_PRICE/...) NSE headers.
_NSE_COLS = {
    "SYMBOL": "Symbol",
    "SERIES": "Series",
    "OPEN": "Open", "OPEN_PRICE": "Open",
    "HIGH": "High", "HIGH_PRICE": "High",
    "LOW": "Low", "LOW_PRICE": "Low",
    "CLOSE": "Close", "CLOSE_PRICE": "Close",
    "PREV_CLOSE": "PrevClose",
    "LAST_PRICE": "Last",
    "TTL_TRD_QNTY": "Volume", "TOTTRDQTY": "Volume",
    "DELIV_QTY": "DelivQty", "DELIVPER": "DelivPct",
    "DELIV_PER": "DelivPct",
    "NO_OF_TRADES": "Trades", "TOTALTRADES": "Trades",
    "TIMESTAMP": "Date", "DATE1": "Date",
}


def _normalise_nse(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]      # headers carry a space
    rename = {k: v for k, v in _NSE_COLS.items() if k in df.columns}
    out = df.rename(columns=rename)
    if "Date" in out.columns:
        d = pd.to_datetime(out["Date"], errors="coerce", format="mixed")
        if d.isna().any():
            # bhavcopy also dates files by name; fall back to the filename date
            pass
        out["Date"] = d.dt.normalize()
    for num_col in ("Open", "High", "Low", "Close", "PrevClose", "Last", "Volume", "DelivQty", "DelivPct", "Trades"):
        if num_col in out.columns:
            out[num_col] = pd.to_numeric(out[num_col].astype(str).str.strip().str.replace(",", ""), errors="coerce")
    keep = [c for c in ("Date", "Symbol", "Series", "Open", "High", "Low",
                        "Close", "PrevClose", "Last", "Volume", "DelivQty",
                        "DelivPct", "Trades") if c in out.columns]
    out = out[keep]
    # _NSE_COLS maps several source headers onto one target; after renaming the
    # frame can hold duplicate columns, and `df.col` would then return a
    # DataFrame rather than a Series.
    out = out.loc[:, ~out.columns.duplicated()]
    return out.dropna(subset=["Symbol", "Close"]) if "Close" in out.columns else out


def fetch_bhavdata(day: date | str, session: requests.Session | None = None) -> pd.DataFrame:
    """One full session: OHLCV plus delivery quantity/percentage and trades."""
    d = pd.Timestamp(day).strftime("%d%m%Y")
    text = _get(BAVCOPY_URL.format(d=d), session)
    out = _normalise_nse(pd.read_csv(io.StringIO(text)))
    if "Date" in out.columns:
        out["Date"] = pd.Timestamp(day).normalize()
    return out


def fetch_nifty500_symbols(session: requests.Session | None = None) -> list[str]:
    """Nifty-500 constituents only. Kept for the original `--source nifty500`."""
    df = pd.read_csv(io.StringIO(_get(NIFTY500_URL, session)))
    df.columns = [str(c).strip() for c in df.columns]
    col = "Symbol" if "Symbol" in df.columns else df.columns[2]
    return [str(s).strip().upper() for s in df[col].tolist()]


def fetch_index_constituents(session: requests.Session | None = None) -> pd.DataFrame:
    """Nifty Total Market + Nifty 500 constituents WITH the Industry column.

    This is the free sector classification. It does not cover every symbol on
    the exchange, so `sector_of()` falls back to "UNCLASSIFIED" rather than
    guessing -- and the portfolio layer treats that as a real limitation.
    """
    frames = []
    for name, url in (("TOTAL_MARKET", TOTAL_MARKET_URL), ("NIFTY500", NIFTY500_URL)):
        try:
            df = pd.read_csv(io.StringIO(_get(url, session)))
        except Exception:
            continue
        df.columns = [str(c).strip() for c in df.columns]
        col = "Symbol" if "Symbol" in df.columns else df.columns[2]
        out = pd.DataFrame({
            "Symbol": df[col].astype(str).str.strip().str.upper(),
            "Company": df.get("Company Name", pd.Series(dtype=str)).astype(str),
            "Industry": df.get("Industry", pd.Series(dtype=str)).astype(str)
                        .str.strip().str.replace(r"\s+", " ", regex=True),
            "Index": name,
        })
        out = out[out["Industry"].notna() & (out["Industry"] != "")]
        if not out.empty:
            frames.append(out)
    if not frames:
        return pd.DataFrame(columns=["Symbol", "Company", "Industry", "Index"])
    combined = pd.concat(frames, ignore_index=True)
    combined["Symbol"] = combined["Symbol"].str.replace(r"\s+", "", regex=True)
    return combined.drop_duplicates(subset=["Symbol"], keep="first").reset_index(drop=True)


def fetch_nse_equity_symbols(session: requests.Session | None = None) -> pd.DataFrame:
    """The full NSE cash-equity master list, filtered to tradable EQ shares.

    Returns a DataFrame with `symbol`, `series`, `listing_date` and `name` so
    the caller can report exactly what was included and excluded rather than
    claiming "NSE-wide" from a subset.
    """
    df = pd.read_csv(io.StringIO(_get(EQUITY_MASTER_URL, session)))
    df.columns = [str(c).strip() for c in df.columns]
    series = df["SERIES"].astype(str).str.strip()
    name = df["NAME OF COMPANY"].astype(str)
    listed = pd.to_datetime(df.get("DATE OF LISTING", pd.Series(index=df.index)),
                            errors="coerce", dayfirst=True)
    out = pd.DataFrame({
        "symbol": df["SYMBOL"].astype(str).str.strip().str.upper(),
        "series": series,
        "name": name,
        "listing_date": listed,
        "isin": df.get("ISIN NUMBER", pd.Series(index=df.index)).astype(str).str.strip(),
    })
    out = out[out["series"].isin(KEEP_SERIES)].copy()
    fund = out["name"].str.contains(FUND_NAME_RE, case=False, na=False, regex=True)
    out = out[~fund].copy()
    return out.drop_duplicates(subset=["symbol"]).reset_index(drop=True)


def sector_map(session: requests.Session | None = None) -> dict[str, str]:
    """symbol -> Industry, for whichever symbols the index lists cover."""
    df = fetch_index_constituents(session)
    return dict(zip(df["Symbol"], df["Industry"])) if not df.empty else {}


def fetch_yfinance(symbols: Iterable[str], start: str, end: str | None = None,
                   batch: int = 40, progress: bool = False) -> pd.DataFrame:
    """Adjusted daily OHLCV for NSE tickers. Symbols without '.NS' get it."""
    import yfinance as yf

    end = end or date.today().isoformat()
    frames: list[pd.DataFrame] = []
    syms = [s if s.endswith(".NS") else f"{s}.NS" for s in symbols]
    for i in range(0, len(syms), batch):
        chunk = syms[i:i + batch]
        try:
            raw = yf.download(chunk, start=start, end=end, interval="1d",
                              group_by="ticker", auto_adjust=True, progress=False,
                              threads=True)
        except Exception:
            continue
        for ns in chunk:
            try:
                one = raw[ns].dropna(how="all").reset_index()
            except (KeyError, IndexError):
                continue
            if one.empty:
                continue
            one["Symbol"] = ns.replace(".NS", "")
            frames.append(one.rename(columns={"index": "Date"}))
        if progress and (i // batch) % 10 == 0:
            print(f"  yfinance: {min(i + batch, len(syms))}/{len(syms)}")
    if not frames:
        return pd.DataFrame(columns=["Date", "Symbol", "Open", "High", "Low",
                                     "Close", "Volume"])
    out = pd.concat(frames, ignore_index=True)
    out["Date"] = pd.to_datetime(out["Date"]).dt.tz_localize(None).dt.normalize()
    return out[["Date", "Symbol", "Open", "High", "Low", "Close", "Volume"]].dropna(
        subset=["Close"])


INDEX_TICKERS = {
    "NIFTY50": "^NSEI", "NIFTYBANK": "^NSEBANK", "NIFTYIT": "^CNXIT",
    "NIFTYAUTO": "^CNXAUTO", "NIFTYPHARMA": "^CNXPHARMA",
    "NIFTYMETAL": "^CNXMETAL", "NIFTYFMCG": "^CNXFMCG", "NIFTYREALTY": "^CNXREALTY",
}


def fetch_index_history(start: str, end: str | None = None) -> pd.DataFrame:
    """Index OHLCV for regime control and beta. Free via yfinance."""
    import yfinance as yf

    end = end or date.today().isoformat()
    out = yf.download(list(INDEX_TICKERS.values()), start=start, end=end,
                      interval="1d", group_by="ticker", auto_adjust=True,
                      progress=False, threads=True)
    if out is None or out.empty:
        return pd.DataFrame()
    rows = []
    for label, ticker in INDEX_TICKERS.items():
        try:
            one = out[ticker].dropna(how="all").reset_index()
        except (KeyError, IndexError):
            continue
        if one.empty:
            continue
        one = one.rename(columns={"index": "Date"})
        one["Index"] = label
        one["Symbol"] = label
        rows.append(one)
    if not rows:
        return pd.DataFrame()
    out = pd.concat(rows, ignore_index=True)
    out["Date"] = pd.to_datetime(out["Date"]).dt.tz_localize(None).dt.normalize()
    return out