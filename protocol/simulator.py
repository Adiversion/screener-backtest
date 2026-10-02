"""A6 trade simulator. One exit engine for every strategy, so cohorts are
directly comparable. Costs come solely from CostModel (SSOT).
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from protocol.costs import CostModel, shares_affordable
from protocol.signals import TradeSignal


def _exit_policy(cfg: dict) -> dict[str, float]:
    r = cfg["run"]
    return {
        "target_net": float(r["target_net"]),
        "hold": int(r["hold_sessions"]),
        "mf_mfe": float(r["momentum_fail_mfe"]),
        "mf_session": int(r["momentum_fail_session"]),
        "gap": float(r["gap_skip"]),
    }


def prepare(bars: pd.DataFrame) -> dict[str, np.ndarray]:
    """Numpy view of one symbol's bars (assumes sorted by Date)."""
    return {
        "date": bars["Date"].to_numpy(),
        "open": bars["Open"].to_numpy(float),
        "high": bars["High"].to_numpy(float),
        "low": bars["Low"].to_numpy(float),
        "close": bars["Close"].to_numpy(float),
    }


def simulate(
    signal: TradeSignal,
    bars: pd.DataFrame,
    cfg: dict,
    model: CostModel,
    capital: float,
    arrays: dict[str, np.ndarray] | None = None,
    target_gross: float | None = None,
) -> dict[str, Any]:
    pol = _exit_policy(cfg)
    if arrays is None:
        arrays = prepare(bars.sort_values("Date").reset_index(drop=True))
    dts, op, hi, lo, cl = (arrays["date"], arrays["open"], arrays["high"],
                           arrays["low"], arrays["close"])
    entry_day = np.datetime64(pd.Timestamp(signal.entry_date))
    e0 = int(np.searchsorted(dts, entry_day))
    if e0 >= len(cl) or dts[e0] != entry_day:
        return _skip(signal, "SKIP_NO_ENTRY_BAR")
    entry_px = float(op[e0])
    if entry_px <= 0 or np.isnan(entry_px):
        return _skip(signal, "SKIP_NO_ENTRY_BAR")
    if entry_px > signal.expected_entry * (1.0 + pol["gap"]):
        return _skip(signal, "SKIP_GAP")
    shares = shares_affordable(capital, entry_px, model)
    if shares < 1:
        return _skip(signal, "SKIP_UNAFFORDABLE")

    stop = signal.stop if signal.stop is not None else entry_px * (1.0 - float(signal.stop_pct or 0.07))
    if target_gross is not None:
        # gpt6 protocol rule: target is a gross move from the actual fill price.
        target = entry_px * (1.0 + float(target_gross))
    else:
        target = model.target_price(entry_px, shares, pol["target_net"])

    mae, mfe = 0.0, 0.0
    last = min(e0 + pol["hold"], len(cl) - 1)
    for k in range(e0, last + 1):
        o, h, l, c = op[k], hi[k], lo[k], cl[k]
        if k > e0:
            mae = min(mae, (l - entry_px) / entry_px)
            mfe = max(mfe, (h - entry_px) / entry_px)
        if k > e0 and k - e0 == pol["mf_session"] and mfe < pol["mf_mfe"]:
            return _result(signal, e0, k, c, shares, entry_px, "MOMENTUM_FAIL", model, mae, mfe, arrays)
        hit_stop = o <= stop or l <= stop
        hit_target = o >= target or h >= target
        if hit_stop:  # same-day stop & target -> stop first (conservative)
            px = o if o <= stop else stop
            return _result(signal, e0, k, px, shares, entry_px,
                           "GAP_STOP" if o <= stop else "STOP", model, mae, mfe, arrays,
                           ambiguous=bool(hit_target))
        if hit_target:
            px = o if o >= target else target
            return _result(signal, e0, k, px, shares, entry_px, "TARGET", model, mae, mfe, arrays)
    return _result(signal, e0, last, float(cl[last]), shares, entry_px, "TIME", model, mae, mfe, arrays)


def _result(signal, e0, k, exit_px, shares, entry_px, reason, model, mae, mfe, a,
            ambiguous: bool = False) -> dict[str, Any]:
    buy_value = entry_px * shares
    buy_cost = model.buy_cost(entry_px, shares)
    net_proceeds = model.sell_net(exit_px, shares)
    net_pnl = net_proceeds - (buy_value + buy_cost)
    net_pct = net_pnl / (buy_value + buy_cost)
    return {
        "strategy": signal.strategy, "symbol": signal.symbol,
        "signal_date": signal.signal_date, "entry_date": signal.entry_date,
        "entry_px": round(entry_px, 4), "exit_date": pd.Timestamp(a["date"][k]),
        "exit_px": round(float(exit_px), 4), "exit_reason": reason,
        "shares": int(shares), "gross_pnl": round(exit_px * shares - buy_value, 4),
        "costs": round(buy_cost + (exit_px * shares * model.sell_rate) + model.dp_charge, 4),
        "net_pnl": round(net_pnl, 4), "net_pnl_pct": round(net_pct, 6),
        "mae": round(mae, 6), "mfe": round(mfe, 6), "sessions_held": int(k - e0 + 1),
        "ambiguous": bool(ambiguous),
        **signal.meta_row(),
    }


def _skip(signal: TradeSignal, reason: str) -> dict[str, Any]:
    return {"strategy": signal.strategy, "symbol": signal.symbol,
            "signal_date": signal.signal_date, "entry_date": signal.entry_date,
            "exit_reason": reason, "skipped": True, "net_pnl_pct": 0.0}
