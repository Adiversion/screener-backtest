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


def simulate(
    signal: TradeSignal,
    bars: pd.DataFrame,
    cfg: dict,
    model: CostModel,
    capital: float,
) -> dict[str, Any]:
    pol = _exit_policy(cfg)
    b = bars.sort_values("Date").reset_index(drop=True)
    hits = b.index[b["Date"] == signal.entry_date]
    if len(hits) == 0:
        return _skip(signal, "SKIP_NO_ENTRY_BAR")
    e0 = int(hits[0])
    entry_px = float(b["Open"].iloc[e0])
    if entry_px <= 0 or np.isnan(entry_px):
        return _skip(signal, "SKIP_NO_ENTRY_BAR")
    if entry_px > signal.expected_entry * (1.0 + pol["gap"]):
        return _skip(signal, "SKIP_GAP")
    shares = shares_affordable(capital, entry_px, model)
    if shares < 1:
        return _skip(signal, "SKIP_UNAFFORDABLE")

    stop = signal.stop if signal.stop is not None else entry_px * (1.0 - float(signal.stop_pct or 0.07))
    target = model.target_price(entry_px, shares, pol["target_net"])

    mae, mfe = 0.0, 0.0
    last = min(e0 + pol["hold"], len(b) - 1)
    for k in range(e0, last + 1):
        row = b.iloc[k]
        hi, lo, op, cl = float(row["High"]), float(row["Low"]), float(row["Open"]), float(row["Close"])
        if k > e0:
            mae = min(mae, (lo - entry_px) / entry_px)
            mfe = max(mfe, (hi - entry_px) / entry_px)
        if k > e0 and k - e0 == pol["mf_session"] and mfe < pol["mf_mfe"]:
            return _result(signal, e0, k, cl, shares, entry_px, "MOMENTUM_FAIL", model, mae, mfe, b)
        hit_stop = op <= stop or lo <= stop
        hit_target = op >= target or hi >= target
        if hit_stop:  # same-day stop & target -> stop first (conservative)
            px = op if op <= stop else stop
            return _result(signal, e0, k, px, shares, entry_px, "GAP_STOP" if op <= stop else "STOP", model, mae, mfe, b)
        if hit_target:
            px = op if op >= target else target
            return _result(signal, e0, k, px, shares, entry_px, "TARGET", model, mae, mfe, b)
    row = b.iloc[last]
    return _result(signal, e0, last, float(row["Close"]), shares, entry_px, "TIME", model, mae, mfe, b)


def _result(signal, e0, k, exit_px, shares, entry_px, reason, model, mae, mfe, b) -> dict[str, Any]:
    buy_value = entry_px * shares
    buy_cost = model.buy_cost(entry_px, shares)
    net_proceeds = model.sell_net(exit_px, shares)
    net_pnl = net_proceeds - (buy_value + buy_cost)
    net_pct = net_pnl / (buy_value + buy_cost)
    row = b.iloc[k]
    return {
        "strategy": signal.strategy, "symbol": signal.symbol,
        "signal_date": signal.signal_date, "entry_date": signal.entry_date,
        "entry_px": round(entry_px, 4), "exit_date": row["Date"],
        "exit_px": round(float(exit_px), 4), "exit_reason": reason,
        "shares": int(shares), "gross_pnl": round(exit_px * shares - buy_value, 4),
        "costs": round(buy_cost + (exit_px * shares * model.sell_rate) + model.dp_charge, 4),
        "net_pnl": round(net_pnl, 4), "net_pnl_pct": round(net_pct, 6),
        "mae": round(mae, 6), "mfe": round(mfe, 6), "sessions_held": int(k - e0 + 1),
        **signal.meta_row(),
    }


def _skip(signal: TradeSignal, reason: str) -> dict[str, Any]:
    return {"strategy": signal.strategy, "symbol": signal.symbol,
            "signal_date": signal.signal_date, "entry_date": signal.entry_date,
            "exit_reason": reason, "skipped": True, "net_pnl_pct": 0.0}
