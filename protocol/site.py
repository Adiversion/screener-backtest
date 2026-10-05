"""Build the payload the research site serves.

The site is static: a nightly job scores the whole universe once and writes
JSON, and the browser does the searching. That makes the search instant and
free, at the cost of the data being as fresh as the last successful run -- so
`asof` travels with every payload and the page always shows which session it
is talking about.

Two files, not one. `stocks.json` carries the score, the gates and the tape
for every symbol and is loaded once; `tape/<SYMBOL>.json` carries the recent
sessions and is fetched only when someone opens a stock. Shipping 2,300 tapes
inside the index payload would triple its size for data most visitors never
scroll to.

The verdict is the engine's, unchanged: a strict gate verdict plus the full
evidence behind it. This module adds no judgement of its own -- a rejected
stock must arrive with every failed gate and its measured value, so "no" is an
explained answer rather than a dead end.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from protocol import quality, ranking, screen

TAPE_ROWS = 12
# feature-frame column -> JSON key. `Close` is capitalised in the panel, so the
# mapping is explicit rather than a lowercase guess.
TAPE_FIELDS = (("Close", "close"), ("rvol20", "rvol20"),
               ("atrpct", "atrpct"), ("ret20", "ret20"))


def _num(value: Any) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return round(f, 4) if np.isfinite(f) else None


def sector_map(path: Path) -> dict[str, str]:
    """symbol -> Industry, when the free index-derived map is available."""
    p = Path(path)
    if not p.exists():
        return {}
    df = pd.read_csv(p)
    cols = {c.lower(): c for c in df.columns}
    if "symbol" not in cols or "industry" not in cols:
        return {}
    return {str(r[cols["symbol"]]).strip().upper(): str(r[cols["industry"]])
            for _, r in df.iterrows()}


def latest_session(ranked: pd.DataFrame) -> pd.Timestamp:
    """The most recent session that still has a usable universe behind it.

    The last row of the file is often a partial session: a handful of symbols
    traded, everyone else missing. Percentiles across 12 names are meaningless,
    so the site refuses to rank on a thin day rather than publish a number that
    looks precise and is not.
    """
    counts = ranked.groupby("date")["symbol"].transform("size")
    per_day = ranked.assign(_n=counts).groupby("date")["_n"].max()
    full = per_day[per_day >= max(20, int(0.25 * per_day.max()))]
    return pd.Timestamp(full.index.max() if len(full) else per_day.index.max())


def _row_payload(row: pd.Series, percentile: float, sectors: dict,
                 tag: str | None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "symbol": str(row["symbol"]),
        "score": _num(row.get("score")),
        "percentile": round(float(percentile), 4),
        "coverage": _num(row.get("coverage")),
        "data_status": str(row.get("data_status")),
        "clears": bool(row.get("clears")),
        "sessions": int(row.get("sessions") or 0),
        "screen_tag": tag,
        "industry": sectors.get(str(row["symbol"]).upper()),
    }
    for field in ("close", "reference", "rvol20", "atrpct", "prox52",
                   "efficiency", "penetration", "ret20", "ret120",
                   "turnover20", "stop_proxy"):
        out[field] = _num(row.get(field))
    out["components"] = {f: _num(row.get(f + "_pct")) for f in quality.COMPONENTS}
    return out


def gate_report(row: pd.Series, cfg: dict) -> list[dict[str, Any]]:
    """Every gate with its measured value and verdict -- the 'why', not just the 'no'.

    Values are coerced to plain Python: `quality.gates` reads a pandas Series, so
    its booleans and floats are numpy scalars, which json refuses to serialise.
    """
    out = []
    for g in quality.gates(row, cfg):
        value = g["value"]
        out.append({"criterion": g["criterion"],
                    "value": _num(value) if isinstance(value, (int, float)) else value,
                    "threshold": g["threshold"],
                    "passed": bool(g["passed"]),
                    "meaning": g["meaning"]})
    return out


def build(panel, cfg, sectors=None, evidence=None, asof=None) -> dict[str, Any]:
    """The site index: one light row per symbol, plus the rules and the research.

    Deliberately LIGHT. The per-symbol gate table and component percentiles are
    the bulk of the payload and most visitors open one or two stocks, so they
    live in `stock/<SYMBOL>.json` and are fetched on demand. Shipping 2,000 gate
    tables up front tripled the index for data nobody ever scrolls to.
    """
    long_ = ranking.build_long(panel, cfg)
    ranked = ranking.rank_all(long_, cfg, quality.COMPONENTS)
    session = pd.Timestamp(asof) if asof is not None else latest_session(ranked)
    today = ranked[ranked["date"] == np.datetime64(session)].copy()

    scores = today["score"].dropna()
    # percentile = share of the universe this name outranks
    today["_pct_rank"] = scores.map(lambda v: float((scores < v).mean()))
    sectors = sectors or {}

    screen_rows = screen.screen(panel, cfg, session)
    tags = dict(zip(screen_rows["symbol"], screen_rows["tag"])) if len(screen_rows) else {}

    stocks: dict[str, Any] = {}
    detail: dict[str, Any] = {}
    light = ("symbol", "score", "percentile", "clears", "close", "ret120",
             "ret20", "atrpct", "prox52", "industry", "screen_tag",
             "coverage", "data_status")
    for _, row in today.iterrows():
        sym = str(row["symbol"])
        full = _row_payload(row, row.get("_pct_rank", 0.0), sectors, tags.get(sym))
        detail[sym] = {**full, "gates": gate_report(row, cfg)}
        stocks[sym] = {k: full[k] for k in light}

    cleared = sorted((s for s, v in stocks.items() if v["clears"]),
                     key=lambda s: -stocks[s]["score"])
    components = [{"field": f, "label": label, "sign": sign,
                   "weight": cfg["quality"]["weights"].get(f),
                   "measures": measures, "why": why}
                  for f, (label, sign, measures, why) in quality.COMPONENTS.items()]
    return {
        "asof": str(session.date()),
        "config_hash": cfg.get("_hash", ""),
        "universe": {"symbols": int(today["symbol"].nunique()),
                     "sessions": int(long_["date"].nunique()),
                     "from": str(pd.Timestamp(long_["date"].min()).date()),
                     "to": str(pd.Timestamp(long_["date"].max()).date())},
        "clearing": cleared,
        "stats": {"cleared": len(cleared),
                  "thin": sum(1 for v in stocks.values()
                              if v["data_status"] == "THIN"),
                  "insufficient": sum(1 for v in stocks.values()
                                      if v["data_status"] == "INSUFFICIENT")},
        "components": components,
        "gates": gate_report(today.iloc[0], cfg) if len(today) else [],
        "evidence": evidence or {},
        "caveats": [
            "Prices are adjusted OHLCV. Delivery percentages cover only a short "
            "recent window, so the delivery-based trap filter is reported as "
            "unavailable for most of this history, never zero-filled.",
            "The universe is today's listed NSE cash equities: this is a "
            "current-constituent screen, not a survivorship-controlled backtest.",
            "The component weights were fitted to 5-day forward returns. They "
            "were never validated on a months-long holding period, and the "
            "strongest factor loses as a short-horizon entry rule.",
            "A gate that fails is UNKNOWN on that criterion, not proven bad. A "
            "THIN data status means a component could not be computed at all.",
            "A label of RESEARCH_CANDIDATE is a research screen, never "
            "investment advice. No participant identity is inferred anywhere.",
        ],
        "stocks": stocks,
        "_detail": detail,
    }


def tapes(panel, cfg, session, symbols) -> dict[str, list[dict]]:
    """Recent sessions per symbol, built only for the symbols asked for."""
    wanted = {s.strip().upper() for s in symbols}
    out: dict[str, list[dict]] = {}
    for symbol, feat in panel.items():
        if wanted and symbol not in wanted:
            continue
        d = feat.reset_index(drop=True)
        upto = d[d["Date"] <= pd.Timestamp(session)].tail(TAPE_ROWS)
        out[symbol] = [{"date": str(pd.Timestamp(r["Date"]).date()),
                         **{key: _num(r.get(col)) for col, key in TAPE_FIELDS}}
                        for _, r in upto.iterrows()]
    return out