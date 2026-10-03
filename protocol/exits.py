"""Dynamic quantitative exit engines for momentum trading.

Implements non-percentage exits used by top quant engines and momentum traders:
1. Breakout Bar Low (Market Structure Invalidation)
2. EMA20 Close Violation on Volume (Institutional Distribution)
3. Chandelier Trailing Exit (Volatility-adaptive ATR trailing stop)
4. Qullamaggie 2R Hybrid (2R partial profit-taking, breakeven, EMA trailing)
5. Time-Stop / Momentum Stagnation (Exit stalled breakouts after N sessions)
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

import numpy as np
import pandas as pd

from protocol.costs import CostModel


class ExitStrategy(str, Enum):
    PASSIVE_HOLD = "PASSIVE_HOLD"
    STRUCTURE_EMA20 = "STRUCTURE_EMA20"
    CHANDELIER_ATR = "CHANDELIER_ATR"
    QULLAMAGGIE_2R = "QULLAMAGGIE_2R"


@dataclass
class TradeOutcome:
    symbol: str
    entry_date: pd.Timestamp
    entry_px: float
    exit_date: pd.Timestamp
    exit_px: float
    exit_reason: str
    net_pnl_pct: float
    sessions_held: int
    mfe: float  # Maximum Favorable Excursion
    mae: float  # Maximum Adverse Excursion


def simulate_dynamic_trade(
    symbol: str,
    bars: pd.DataFrame,
    entry_date: pd.Timestamp | str,
    exit_strategy: ExitStrategy = ExitStrategy.STRUCTURE_EMA20,
    cost_model: CostModel | None = None,
    atr_mult: float = 2.5,
    max_hold: int = 20,
) -> TradeOutcome | None:
    """Simulates a trade bar-by-bar with dynamic volatility and structural exits."""
    df = bars.sort_values("Date").reset_index(drop=True)
    dates = pd.to_datetime(df["Date"]).dt.normalize()
    target_dt = pd.Timestamp(entry_date).normalize()

    idx_matches = np.where(dates == target_dt)[0]
    if len(idx_matches) == 0:
        return None
    e0 = int(idx_matches[0])
    if e0 >= len(df) - 1:
        return None

    entry_px = float(df.loc[e0, "Close"])
    breakout_low = float(df.loc[e0, "Low"])
    entry_atr = float(df.loc[e0, "atr14"]) if "atr14" in df.columns else entry_px * 0.03
    if np.isnan(entry_atr) or entry_atr <= 0:
        entry_atr = entry_px * 0.03

    # Initial stop: Invalidation of breakout bar low or 2.0x ATR, whichever is tighter
    initial_stop = max(breakout_low * 0.998, entry_px - 2.0 * entry_atr)
    # Never allow stop wider than 8%
    initial_stop = max(initial_stop, entry_px * 0.92)
    risk_unit = max(entry_px - initial_stop, entry_px * 0.02)

    current_stop = initial_stop
    highest_high = entry_px
    partial_taken = False
    first_half_pnl = 0.0

    mae = 0.0
    mfe = 0.0
    last_idx = min(e0 + max_hold, len(df) - 1)

    for k in range(e0 + 1, last_idx + 1):
        o = float(df.loc[k, "Open"])
        h = float(df.loc[k, "High"])
        l = float(df.loc[k, "Low"])
        c = float(df.loc[k, "Close"])
        v = float(df.loc[k, "Volume"])
        dt = pd.Timestamp(df.loc[k, "Date"])

        ema10 = float(df.loc[k, "ema10"]) if "ema10" in df.columns else np.nan
        ema20 = float(df.loc[k, "ema20"]) if "ema20" in df.columns else np.nan
        vol_sma20 = float(df.loc[k, "vol_sma20"]) if "vol_sma20" in df.columns else v
        atr = float(df.loc[k, "atr14"]) if "atr14" in df.columns else entry_atr

        highest_high = max(highest_high, h)
        mfe = max(mfe, (h - entry_px) / entry_px)
        mae = min(mae, (l - entry_px) / entry_px)

        # 1. Passive Hold
        if exit_strategy == ExitStrategy.PASSIVE_HOLD:
            if l <= entry_px * 0.93:  # 7% hard stop
                exit_px = min(o, entry_px * 0.93)
                net = (exit_px - entry_px) / entry_px - 0.003
                return TradeOutcome(symbol, target_dt, entry_px, dt, exit_px, "HARD_STOP_7PCT", net, k - e0, mfe, mae)
            if k == last_idx:
                net = (c - entry_px) / entry_px - 0.003
                return TradeOutcome(symbol, target_dt, entry_px, dt, c, "TIME_HORIZON_20D", net, k - e0, mfe, mae)

        # 2. Structure & EMA20 Close Violation
        elif exit_strategy == ExitStrategy.STRUCTURE_EMA20:
            if o <= current_stop or l <= current_stop:
                exit_px = o if o <= current_stop else current_stop
                net = (exit_px - entry_px) / entry_px - 0.003
                return TradeOutcome(symbol, target_dt, entry_px, dt, exit_px, "STRUCTURE_STOP", net, k - e0, mfe, mae)
            if not np.isnan(ema20) and c < ema20 and v >= vol_sma20:
                net = (c - entry_px) / entry_px - 0.003
                return TradeOutcome(symbol, target_dt, entry_px, dt, c, "EMA20_DISTRIBUTION", net, k - e0, mfe, mae)
            # Time decay: if flat or negative after 5 days, kill trade
            if k - e0 >= 5 and c <= entry_px * 0.99:
                net = (c - entry_px) / entry_px - 0.003
                return TradeOutcome(symbol, target_dt, entry_px, dt, c, "TIME_STAGNATION", net, k - e0, mfe, mae)

        # 3. Chandelier Trailing Exit
        elif exit_strategy == ExitStrategy.CHANDELIER_ATR:
            chandelier_stop = highest_high - (atr_mult * atr)
            current_stop = max(current_stop, chandelier_stop)
            if o <= current_stop or l <= current_stop:
                exit_px = o if o <= current_stop else current_stop
                net = (exit_px - entry_px) / entry_px - 0.003
                return TradeOutcome(symbol, target_dt, entry_px, dt, exit_px, "CHANDELIER_ATR_STOP", net, k - e0, mfe, mae)

        # 4. Qullamaggie 2R Hybrid
        elif exit_strategy == ExitStrategy.QULLAMAGGIE_2R:
            # Check 2R profit target for first half
            target_2r = entry_px + (2.0 * risk_unit)
            if not partial_taken and (o >= target_2r or h >= target_2r):
                partial_taken = True
                first_half_pnl = 2.0 * (risk_unit / entry_px)
                current_stop = max(current_stop, entry_px)  # Move stop to breakeven

            # Check stop on remaining
            if o <= current_stop or l <= current_stop:
                exit_px = o if o <= current_stop else current_stop
                half_pnl = (exit_px - entry_px) / entry_px
                total_pnl = (first_half_pnl + half_pnl) / 2.0 if partial_taken else half_pnl
                net = total_pnl - 0.003
                return TradeOutcome(symbol, target_dt, entry_px, dt, exit_px, "QULLA_STOP_OR_BE", net, k - e0, mfe, mae)

            # Check EMA10/EMA20 violation on remaining
            if partial_taken and not np.isnan(ema10) and c < ema10 and v >= vol_sma20:
                half_pnl = (c - entry_px) / entry_px
                total_pnl = (first_half_pnl + half_pnl) / 2.0
                net = total_pnl - 0.003
                return TradeOutcome(symbol, target_dt, entry_px, dt, c, "QULLA_EMA10_EXIT", net, k - e0, mfe, mae)

    # Reached end of horizon
    final_c = float(df.loc[last_idx, "Close"])
    half_pnl = (final_c - entry_px) / entry_px
    total_pnl = (first_half_pnl + half_pnl) / 2.0 if partial_taken else half_pnl
    net = total_pnl - 0.003
    return TradeOutcome(symbol, target_dt, entry_px, dates.iloc[last_idx], final_c, "TIME_EXPIRATION", net, last_idx - e0, mfe, mae)
