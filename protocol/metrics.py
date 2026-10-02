"""A7 outcome metrics: cohort stats, seeded bootstrap CIs, and a
single-position portfolio simulation (rotate net proceeds).
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

STOP_REASONS = {"STOP", "GAP_STOP"}


def cohort_metrics(trades: list[dict[str, Any]], target_net: float, seed: int, n_boot: int) -> dict[str, Any]:
    done = [t for t in trades if not t.get("skipped")]
    if not done:
        return {"N": 0}
    pct = np.array([t["net_pnl_pct"] for t in done], dtype=float)
    reasons = [t["exit_reason"] for t in done]
    safe = np.array([r not in STOP_REASONS for r in reasons], dtype=float)
    win = (pct >= target_net).astype(float)
    rng = np.random.default_rng(seed)
    chunk = max(1, int(2_000_000 // max(len(pct), 1)))  # bounded bootstrap memory

    def ci(arr: np.ndarray) -> list[float]:
        boots = np.empty(n_boot)
        for start in range(0, n_boot, chunk):
            k = min(chunk, n_boot - start)
            idx = rng.integers(0, len(pct), size=(k, len(pct)))
            boots[start:start + k] = arr[idx].mean(axis=1)
        return [round(float(np.percentile(boots, 2.5)), 4), round(float(np.percentile(boots, 97.5)), 4)]

    gross_win = pct[pct > 0].sum()
    gross_loss = -pct[pct < 0].sum()
    return {
        "N": len(done),
        "WinRate": round(float(win.mean()), 4), "WinRate_CI": ci(win),
        "LossRate": round(float((pct < 0).mean()), 4),
        "TimeExitRate": round(float(np.mean([r == "TIME" for r in reasons])), 4),
        "SafeRate": round(float(safe.mean()), 4), "SafeRate_CI": ci(safe),
        "TailBreach": round(float((pct < -0.07).mean()), 4),
        "Expectancy": round(float(pct.mean()), 4), "Expectancy_CI": ci(pct),
        "Expectancy_median": round(float(np.median(pct)), 4),
        "ProfitFactor": round(float(gross_win / gross_loss), 3) if gross_loss > 0 else None,
        "Std": round(float(pct.std()), 4),
        "P25": round(float(np.percentile(pct, 25)), 4),
        "P75": round(float(np.percentile(pct, 75)), 4),
        "MAE_mean": round(float(np.mean([t["mae"] for t in done])), 4),
        "MFE_mean": round(float(np.mean([t["mfe"] for t in done])), 4),
        "Sessions_mean": round(float(np.mean([t["sessions_held"] for t in done])), 2),
    }


def portfolio(trades: list[dict[str, Any]], initial_capital: float, target_net: float) -> dict[str, Any]:
    """One position at a time; rotate the entire net proceeds."""
    done = [t for t in trades if not t.get("skipped")]
    done.sort(key=lambda t: (t["entry_date"], t["exit_date"]))
    capital = initial_capital
    equity, peak, max_dd = [], capital, 0.0
    streak = worst_streak = 0
    taken = 0
    for t in done:
        capital *= (1.0 + t["net_pnl_pct"])
        taken += 1
        equity.append(capital)
        peak = max(peak, capital)
        max_dd = min(max_dd, capital / peak - 1.0)
        streak = streak + 1 if t["net_pnl_pct"] < 0 else 0
        worst_streak = max(worst_streak, streak)
    if not equity:
        return {"trades": 0, "final": initial_capital, "max_dd": 0.0}
    years = max((done[-1]["exit_date"] - done[0]["entry_date"]).days / 365.25, 1e-9)
    cagr = (capital / initial_capital) ** (1.0 / years) - 1.0
    return {
        "trades": taken, "final": round(capital, 2),
        "total_return": round(capital / initial_capital - 1.0, 4),
        "max_dd": round(max_dd, 4), "longest_losing_streak": worst_streak,
        "trades_per_year": round(taken / years, 1), "CAGR": round(cagr, 4),
        "double_prob": None,
    }
