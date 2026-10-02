"""Orchestration: run one strategy or many, produce comparable result blocks."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from protocol import metrics
from protocol.costs import CostModel
from protocol.features import build_panel
from protocol.simulator import prepare, simulate
from protocol.strategies import REGISTRY


def universe_benchmark(history: pd.DataFrame) -> dict[str, Any]:
    """Equal-weight buy-and-hold return of the universe over the window."""
    rets = []
    for _, bars in history.groupby("Symbol"):
        bars = bars.sort_values("Date")
        if len(bars) < 2 or bars["Close"].iloc[0] <= 0:
            continue
        rets.append(bars["Close"].iloc[-1] / bars["Close"].iloc[0] - 1.0)
    if not rets:
        return {"N": 0}
    arr = np.array(rets)
    return {"N": len(arr), "mean_return": round(float(arr.mean()), 4),
            "median_return": round(float(np.median(arr)), 4),
            "pct_positive": round(float((arr > 0).mean()), 4)}


def _split_by_date(signals, start, end):
    if start is None and end is None:
        return signals
    out = []
    for s in signals:
        d = s.signal_date
        if start is not None and d < pd.Timestamp(start):
            continue
        if end is not None and d > pd.Timestamp(end):
            continue
        out.append(s)
    return out


def build_signals(
    name: str,
    panel: dict[str, pd.DataFrame],
    cfg: dict,
    window: tuple[str | None, str | None] = (None, None),
) -> list[Any]:
    """Generate a strategy's signals once; capital only affects simulation."""
    return _split_by_date(REGISTRY[name](panel, cfg), *window)


def run_strategy(
    name: str,
    panel: dict[str, pd.DataFrame],
    bars_by_symbol: dict[str, pd.DataFrame],
    cfg: dict,
    capital: float,
    window: tuple[str | None, str | None] = (None, None),
    signals: list[Any] | None = None,
    arrays_by_symbol: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if signals is None:
        signals = build_signals(name, panel, cfg, window)
    model = CostModel.from_config(cfg)
    trades: list[dict[str, Any]] = []
    skipped = 0
    for sig in signals:
        bars = bars_by_symbol.get(sig.symbol)
        if bars is None:
            continue
        arrays = (arrays_by_symbol or {}).get(sig.symbol)
        out = simulate(sig, bars, cfg, model, capital, arrays)
        if out.get("skipped"):
            skipped += 1
        trades.append(out)
    m = metrics.cohort_metrics(trades, cfg["run"]["target_net"], cfg["run"]["seed"], cfg["run"]["bootstrap_n"])
    m["Strategy"] = name
    m["signals"] = len(signals)
    m["skipped"] = skipped
    return {"strategy": name, "capital": capital, "metrics": m,
            "portfolio": metrics.portfolio(trades, capital, cfg["run"]["target_net"]),
            "trades": [t for t in trades if not t.get("skipped")]}


def _cap_key(cap: float) -> str:
    return str(int(cap)) if float(cap).is_integer() else str(cap)


def run_comparison(cfg, history, strategies, capitals, window=(None, None)) -> dict[str, Any]:
    panel = build_panel(history)
    bars_by_symbol = {s: b.sort_values("Date").reset_index(drop=True)
                      for s, b in history.groupby("Symbol")}
    arrays_by_symbol = {s: prepare(b) for s, b in bars_by_symbol.items()}
    results: dict[str, Any] = {}
    for name in strategies:
        if name not in REGISTRY:
            results[name] = {"error": f"unknown strategy: {name}"}
            continue
        signals = build_signals(name, panel, cfg, window)  # computed once, reused per capital
        results[name] = {
            _cap_key(cap): run_strategy(name, panel, bars_by_symbol, cfg, float(cap), window,
                                        signals, arrays_by_symbol)
            for cap in capitals
        }
    return {
        "config_hash": cfg["_hash"], "window": list(window),
        "universe": {"symbols": history["Symbol"].nunique(),
                     "sessions": history["Date"].nunique(),
                     "from": str(history["Date"].min().date()),
                     "to": str(history["Date"].max().date())},
        "benchmark": universe_benchmark(history),
        "results": results,
    }
