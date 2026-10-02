"""Pluggable strategies.

Every strategy turns the feature panel into a list of TradeSignals; the
simulator and metrics are shared, so results are directly comparable.
`REGISTRY` is the single place new strategies are registered.

Params live under `strategies.<name>` in config/protocol_v2.yaml and can be
overridden on the CLI with `--set strategies.<name>.<key>=<value>`.
"""
from __future__ import annotations

from typing import Any, Callable

import numpy as np
import pandas as pd

from protocol import filters as flt
from protocol import states
from protocol.signals import TradeSignal

Builder = Callable[[dict[str, pd.DataFrame], dict], list[TradeSignal]]
REGISTRY: dict[str, Builder] = {}


def register(name: str) -> Callable[[Builder], Builder]:
    def deco(fn: Builder) -> Builder:
        REGISTRY[name] = fn
        return fn
    return deco


def _params(cfg: dict, name: str) -> dict:
    return (cfg.get("strategies") or {}).get(name, {})


def _next_date(feat: pd.DataFrame, idx: int) -> pd.Timestamp | None:
    if idx + 1 >= len(feat):
        return None
    return pd.Timestamp(feat["Date"].iloc[idx + 1])


def _mk(name, symbol, sig_date, entry_date, expected, stop=None, stop_pct=0.07, meta=None):
    return TradeSignal(name, symbol, pd.Timestamp(sig_date), pd.Timestamp(entry_date),
                       float(expected), stop=stop, stop_pct=stop_pct, meta=meta or {})


@register("aae_acceptance")
def aae_acceptance(panel: dict[str, pd.DataFrame], cfg: dict) -> list[TradeSignal]:
    disabled = set(cfg.get("filters", {}).get("disabled", []))
    out: list[TradeSignal] = []
    for symbol, feat in panel.items():
        for ev in states.find_events(feat, cfg):
            if ev["label"] != "CANDIDATE":
                continue
            res = flt.evaluate(feat, ev, cfg)
            reasons = [r for r in res["reasons"] if r not in disabled]
            if reasons:
                continue
            idx = int(feat.reset_index(drop=True).index[feat.reset_index(drop=True)["Date"] == ev["E_date"]][0])
            entry = _next_date(feat, idx)
            if entry is None:
                continue
            out.append(_mk("aae_acceptance", symbol, ev["E_date"], entry, ev["expected_entry"],
                           stop=ev["structural_stop"], stop_pct=0.07,
                           meta={**{k: ev.get(k) for k in
                                    ("D0_date", "R20", "rvol20_d0", "atr14_d0", "retention_d0",
                                     "closing_range_d0", "penetration_d0", "closing_disp_d0",
                                     "efficiency_d0", "stop_distance", "pullback_days")},
                                 "filter_incomplete": res["filter_incomplete"],
                                 "filters": ",".join(res["reasons"])}))
    return out


@register("breakout_day")
def breakout_day(panel, cfg) -> list[TradeSignal]:
    """B2: STATE0 breakout only, no acceptance wait."""
    s0 = cfg["state0"]
    out = []
    for symbol, feat in panel.items():
        d = feat.reset_index(drop=True)
        ok = ((d["Close"] > d["R20"]) & (d["rvol20"] >= s0["rvol_min"]) &
              (d["closing_range"] >= s0["closing_range_min"]) & (d["retention"] >= s0["retention_min"]))
        for idx in np.where(ok.fillna(False).to_numpy())[0]:
            entry = _next_date(d, int(idx))
            if entry is not None:
                out.append(_mk("breakout_day", symbol, d["Date"].iloc[idx], entry, d["Close"].iloc[idx]))
    return out


@register("vol_breakout")
def vol_breakout(panel, cfg) -> list[TradeSignal]:
    """B3: Close > R20 and RVOL20 >= 1.5."""
    rvol = _params(cfg, "vol_breakout").get("rvol_min", 1.5)
    out = []
    for symbol, feat in panel.items():
        d = feat.reset_index(drop=True)
        ok = (d["Close"] > d["R20"]) & (d["rvol20"] >= rvol)
        for idx in np.where(ok.fillna(False).to_numpy())[0]:
            entry = _next_date(d, int(idx))
            if entry is not None:
                out.append(_mk("vol_breakout", symbol, d["Date"].iloc[idx], entry, d["Close"].iloc[idx]))
    return out


@register("trend")
def trend(panel, cfg) -> list[TradeSignal]:
    """B6: Close > SMA50 > SMA200, ROC20 > 0, RSI14 > 50."""
    out = []
    for symbol, feat in panel.items():
        d = feat.reset_index(drop=True)
        close = d["Close"]
        sma50 = close.rolling(50).mean()
        sma200 = close.rolling(200).mean()
        rsi = _rsi(close)
        ok = (close > sma50) & (sma50 > sma200) & (d["ret20"] > 0) & (rsi > 50)
        for idx in np.where(ok.fillna(False).to_numpy())[0]:
            entry = _next_date(d, int(idx))
            if entry is not None:
                out.append(_mk("trend", symbol, d["Date"].iloc[idx], entry, close.iloc[idx]))
    return out


@register("trap")
def trap(panel, cfg) -> list[TradeSignal]:
    """B1: buy anything already up >= 15% over 2 sessions."""
    thr = _params(cfg, "trap").get("ret2_min", 0.15)
    out = []
    for symbol, feat in panel.items():
        d = feat.reset_index(drop=True)
        for idx in np.where((d["ret2"] >= thr).fillna(False).to_numpy())[0]:
            entry = _next_date(d, int(idx))
            if entry is not None:
                out.append(_mk("trap", symbol, d["Date"].iloc[idx], entry, d["Close"].iloc[idx]))
    return out


@register("high_effort_low_result")
def high_effort_low_result(panel, cfg) -> list[TradeSignal]:
    """B8: RVOL20 >= 2.5 and ResultATR <= 0.5 (Gervais vs Turtle-Soup cell)."""
    out = []
    for symbol, feat in panel.items():
        d = feat.reset_index(drop=True)
        ok = (d["rvol20"] >= 2.5) & (d["result_atr"] <= 0.5)
        for idx in np.where(ok.fillna(False).to_numpy())[0]:
            entry = _next_date(d, int(idx))
            if entry is not None:
                out.append(_mk("high_effort_low_result", symbol, d["Date"].iloc[idx], entry, d["Close"].iloc[idx]))
    return out


@register("recovered_after_rej")
def recovered_after_rej(panel, cfg) -> list[TradeSignal]:
    """B9: REJECTED then close > R20 within 3 sessions; entry on reclaim+1."""
    out = []
    for symbol, feat in panel.items():
        d = feat.reset_index(drop=True)
        for ev in states.find_events(feat, cfg):
            if ev["label"] != "RECOVERED_AFTER_REJ":
                continue
            idx = int(d.index[d["Date"] == ev["reject_date"]][0])
            entry = _next_date(d, idx)
            if entry is not None:
                out.append(_mk("recovered_after_rej", symbol, ev["reject_date"], entry, d["Close"].iloc[idx]))
    return out


@register("random")
def random_baseline(panel, cfg) -> list[TradeSignal]:
    """B0: the true null. Seeded random (symbol, session)."""
    p = _params(cfg, "random")
    n = int(p.get("n", 2000))
    rng = np.random.default_rng(cfg["run"]["seed"])
    syms = list(panel.keys())
    out = []
    for _ in range(n):
        symbol = syms[int(rng.integers(0, len(syms)))]
        d = panel[symbol].reset_index(drop=True)
        if len(d) < 2:
            continue
        idx = int(rng.integers(0, len(d) - 1))
        entry = _next_date(d, idx)
        if entry is not None:
            out.append(_mk("random", symbol, d["Date"].iloc[idx], entry, d["Close"].iloc[idx]))
    return out


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))
