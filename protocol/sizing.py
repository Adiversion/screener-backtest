"""Volatility Risk-Parity & Capital Infusion Sizing Engine.

Implements institutional position sizing used by QuantConnect, Qlib, and Van Tharp:
Position size is anchored to instrument volatility (ATR) and a fixed portfolio risk budget,
ensuring every trade risks the exact same dollar amount rather than naive equal cash.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import floor
from typing import Any

import numpy as np
import pandas as pd

from protocol.costs import CostModel


@dataclass(frozen=True)
class PositionAllocation:
    symbol: str
    entry_price: float
    shares: int
    capital_allocated: float
    capital_pct: float
    stop_price: float
    stop_distance: float
    risk_rupees: float
    risk_pct_portfolio: float
    atr14: float
    reason: str


def compute_volatility_allocation(
    symbol: str,
    entry_price: float,
    atr14: float,
    total_portfolio_capital: float,
    risk_per_trade_pct: float = 0.01,  # 1.0% risk of portfolio equity per trade
    max_capital_per_stock_pct: float = 0.20,  # Max 20% of capital in a single stock
    atr_multiplier: float = 2.0,
    stop_price: float | None = None,
    cost_model: CostModel | None = None,
) -> PositionAllocation:
    """Calculates exact shares and capital to infuse based on volatility risk parity."""
    model = cost_model or CostModel()
    eff_price = entry_price * (1.0 + model.buy_rate)

    if entry_price <= 0 or total_portfolio_capital <= 0:
        return PositionAllocation(symbol, entry_price, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, atr14, "INVALID_INPUT")

    # Clean ATR floor
    safe_atr = atr14 if (not np.isnan(atr14) and atr14 > 0) else entry_price * 0.03

    # Calculate stop distance
    if stop_price is not None and stop_price < entry_price:
        stop_dist = max(entry_price - stop_price, safe_atr * 1.0)
        calc_stop = stop_price
    else:
        stop_dist = max(safe_atr * atr_multiplier, entry_price * 0.02)  # At least 2% floor
        calc_stop = max(entry_price - stop_dist, entry_price * 0.92)  # Cap at max 8% stop
        stop_dist = entry_price - calc_stop

    # Risk budget in Rupees (e.g. 1% of Rs. 100,000 = Rs. 1,000)
    risk_budget_rupees = total_portfolio_capital * risk_per_trade_pct

    # Raw shares by risk parity: Shares = Risk Budget / Stop Distance
    raw_shares = int(floor(risk_budget_rupees / stop_dist))

    # Capital constraint: Maximum capital allowed per position
    max_capital_allowed = total_portfolio_capital * max_capital_per_stock_pct
    max_shares_by_cap = int(floor(max_capital_allowed / eff_price))

    final_shares = max(0, min(raw_shares, max_shares_by_cap))

    # Ensure at least 1 share if affordable and fits within max capital
    if final_shares == 0 and eff_price <= max_capital_allowed and eff_price <= total_portfolio_capital:
        final_shares = 1

    capital_allocated = final_shares * eff_price
    actual_risk_rupees = final_shares * stop_dist
    risk_pct = actual_risk_rupees / total_portfolio_capital if total_portfolio_capital > 0 else 0.0
    cap_pct = capital_allocated / total_portfolio_capital if total_portfolio_capital > 0 else 0.0

    reason = "RISK_PARITY" if final_shares == raw_shares else "CAPPED_BY_MAX_POSITION"
    if final_shares == 1 and raw_shares == 0:
        reason = "MIN_1_SHARE"

    return PositionAllocation(
        symbol=symbol,
        entry_price=round(entry_price, 2),
        shares=final_shares,
        capital_allocated=round(capital_allocated, 2),
        capital_pct=round(cap_pct, 4),
        stop_price=round(calc_stop, 2),
        stop_distance=round(stop_dist, 2),
        risk_rupees=round(actual_risk_rupees, 2),
        risk_pct_portfolio=round(risk_pct, 4),
        atr14=round(safe_atr, 2),
        reason=reason,
    )


def allocate_portfolio_capital(
    candidates: list[dict[str, Any]],
    total_portfolio_capital: float,
    risk_per_trade_pct: float = 0.01,
    max_capital_per_stock_pct: float = 0.20,
    cost_model: CostModel | None = None,
) -> tuple[list[PositionAllocation], float]:
    """Allocates capital across ranked candidate list with cash budget constraint.

    Returns (allocations, remaining_cash).
    """
    remaining_cash = total_portfolio_capital
    allocations = []

    for c in candidates:
        sym = c["symbol"]
        px = float(c["entry_price"])
        atr = float(c.get("atr14", px * 0.03))
        stop_px = float(c["stop_price"]) if "stop_price" in c and c["stop_price"] is not None else None

        alloc = compute_volatility_allocation(
            symbol=sym,
            entry_price=px,
            atr14=atr,
            total_portfolio_capital=total_portfolio_capital,
            risk_per_trade_pct=risk_per_trade_pct,
            max_capital_per_stock_pct=max_capital_per_stock_pct,
            stop_price=stop_px,
            cost_model=cost_model,
        )

        # Check if enough remaining cash
        if alloc.shares > 0 and alloc.capital_allocated <= remaining_cash:
            allocations.append(alloc)
            remaining_cash -= alloc.capital_allocated
        elif alloc.shares > 0 and remaining_cash >= px:
            # Partially scale down to fit remaining cash
            reduced_shares = int(floor(remaining_cash / px))
            if reduced_shares >= 1:
                scaled_alloc = compute_volatility_allocation(
                    symbol=sym,
                    entry_price=px,
                    atr14=atr,
                    total_portfolio_capital=total_portfolio_capital,
                    risk_per_trade_pct=risk_per_trade_pct,
                    max_capital_per_stock_pct=remaining_cash / total_portfolio_capital,
                    stop_price=stop_px,
                    cost_model=cost_model,
                )
                if scaled_alloc.shares > 0 and scaled_alloc.capital_allocated <= remaining_cash:
                    allocations.append(scaled_alloc)
                    remaining_cash -= scaled_alloc.capital_allocated

    return allocations, round(remaining_cash, 2)


def allocate_fixed_capital_per_stock(
    candidates: list[dict[str, Any]],
    capital_per_stock: float = 100000.0,
    cost_model: CostModel | None = None,
) -> list[PositionAllocation]:
    """Allocates a fixed rupee amount (e.g. Rs. 100,000) to EVERY selected stock."""
    model = cost_model or CostModel()
    allocations = []
    for c in candidates:
        sym = c["symbol"]
        px = float(c["entry_price"])
        eff_px = px * (1.0 + model.buy_rate)
        if eff_px <= 0 or capital_per_stock < eff_px:
            shares = 1 if px <= capital_per_stock else 0
        else:
            shares = int(floor(capital_per_stock / eff_px))

        atr = float(c.get("atr14", px * 0.03))
        stop_px = float(c["stop_price"]) if "stop_price" in c and c["stop_price"] is not None else max(px - 2.0 * atr, px * 0.92)
        stop_dist = max(px - stop_px, px * 0.02)
        cap_alloc = shares * eff_px
        risk_rupees = shares * stop_dist

        allocations.append(PositionAllocation(
            symbol=sym,
            entry_price=round(px, 2),
            shares=shares,
            capital_allocated=round(cap_alloc, 2),
            capital_pct=1.0,
            stop_price=round(stop_px, 2),
            stop_distance=round(stop_dist, 2),
            risk_rupees=round(risk_rupees, 2),
            risk_pct_portfolio=round(risk_rupees / capital_per_stock if capital_per_stock > 0 else 0.0, 4),
            atr14=round(atr, 2),
            reason="FIXED_CAPITAL_PER_STOCK",
        ))
    return allocations
