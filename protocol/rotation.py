"""Single-position rotation: one stock, the whole account, exit on target or stop.

This is the deployment shape the engine is for: no day trading, no
derivatives, no basket. One candidate at a time, 100% of capital in it, exit
when the fixed profit target or the fixed stop is hit, then move the whole
account to the next prime candidate. If nothing clears the gates the account
stays in cash -- that is a real position, not a gap in the report.

Point in time is respected end to end: the ranking at date T reads only rows
with date <= T, the fill is the Open of the next session that symbol actually
traded, and the exit uses the High/Low of the sessions really held. A symbol
that has not traded yet has no row on that date and is simply not a candidate.

The cost of rotating is modelled honestly. The DP charge is flat per SELL, so
it scales as 1/capital and a small account pays a real fraction of capital per
rotation; `capital_report()` prints that arithmetic instead of hiding it.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from protocol import metrics, quality, ranking
from protocol.costs import CostModel, shares_affordable

STOP_REASONS = ("STOP", "GAP_STOP")


# ----------------------------------------------------------------- price view
def price_arrays(panel: dict[str, pd.DataFrame]) -> dict[str, dict[str, np.ndarray]]:
    """Per symbol, the OHLC columns the fill and the exit actually read."""
    out: dict[str, dict[str, np.ndarray]] = {}
    for symbol, feat in panel.items():
        d = feat.reset_index(drop=True)
        out[symbol] = {
            "date": pd.DatetimeIndex(d["Date"]).to_numpy(),
            **{f: pd.to_numeric(d[f], errors="coerce").to_numpy(float)
               for f in ("Open", "High", "Low", "Close")},
        }
    return out


def _bar(cols: dict[str, np.ndarray], day: pd.Timestamp, field: str = "Close") -> float:
    j = int(np.searchsorted(cols["date"], np.datetime64(day), side="right")) - 1
    return float(cols[field][j]) if j >= 0 else float("nan")


# ------------------------------------------------------------------ the exit
def exit_from(cols: dict[str, np.ndarray], e0: int, entry_px: float, shares: int,
              model: CostModel, cfg: dict) -> tuple[int, float, str]:
    """Sessions after entry until the fixed target, the fixed stop, or the time stop.

    A bar that touches both exits at the STOP: without intraday bars the order
    of the two touches is unknowable, and the pessimistic reading is the only
    honest one.
    """
    pol = cfg["rotation"]
    o, h, l, c = (cols["Open"][e0:], cols["High"][e0:],
                  cols["Low"][e0:], cols["Close"][e0:])
    target = model.target_price(entry_px, shares, float(pol["target_net"]))
    stop = entry_px * (1.0 - float(pol["stop_pct"]))
    last = min(int(pol["hold_sessions"]), len(c) - 1)
    for k in range(1, last + 1):
        if o[k] <= stop or l[k] <= stop:
            return k, float(o[k] if o[k] <= stop else stop), (
                "GAP_STOP" if o[k] <= stop else "STOP")
        if o[k] >= target or h[k] >= target:
            return k, float(o[k] if o[k] >= target else target), "TARGET"
    return last, float(c[last]), "TIME"


def _open_position(cols, symbol, day_i, cash, model, cfg, signal_date, score):
    """Buy the whole account at this bar's Open and resolve the exit now."""
    entry_px = float(cols["Open"][day_i])
    shares = shares_affordable(cash, entry_px, model)
    if shares < 1:
        return None
    k, exit_px, reason = exit_from(cols, day_i, entry_px, shares, model, cfg)
    invest = entry_px * shares * (1.0 + model.buy_rate)
    proceeds = model.sell_net(exit_px, shares)
    idle = cash - invest
    window = slice(day_i, day_i + k + 1)
    trade = {
        "strategy": "rotation", "symbol": symbol,
        "signal_date": signal_date,
        "entry_date": pd.Timestamp(cols["date"][day_i]),
        "entry_px": round(entry_px, 4), "shares": int(shares),
        "exit_date": pd.Timestamp(cols["date"][day_i + k]),
        "exit_px": round(exit_px, 4), "exit_reason": reason,
        "gross_move": round(exit_px / entry_px - 1.0, 6),
        "net_pnl": round(proceeds - invest, 2),
        "net_pnl_pct": round((proceeds - invest) / invest, 6),
        "costs": round(invest + entry_px * shares - proceeds, 2),
        "invested": round(invest, 2), "idle_cash": round(idle, 2),
        # the ACCOUNT after the exit, not just the proceeds of the sold shares:
        # a share count that does not use the capital exactly leaves cash over
        "capital_before": round(cash, 2),
        "capital_after": round(proceeds + idle, 2),
        "sessions_held": int(k), "score": score,
        "mae": round(float((cols["Low"][window].min() - entry_px) / entry_px), 6),
        "mfe": round(float((cols["High"][window].max() - entry_px) / entry_px), 6),
        "ambiguous": False,
    }
    return {"trade": trade, "idle": idle, "cash_after": proceeds + idle}


# ------------------------------------------------------------------ the walk
def run(panel, cfg, capital=1000.0, start=None, end=None, pick="rank",
        seed=None, bootstrap_n=2000) -> dict[str, Any]:
    """One position at a time, redeploying the entire account on every exit.

    `pick="rank"` takes the highest-scoring gate-clearing name. `pick="random"`
    takes a uniformly random name from the SAME gate-clearing set: the null this
    mode has to beat before any of its picks mean anything.
    """
    pol = cfg["rotation"]
    prices = price_arrays(panel)
    ranked = ranking.rank_all(ranking.build_long(panel, cfg), cfg, quality.COMPONENTS)
    model = CostModel.from_config(cfg)
    rng = np.random.default_rng(cfg["run"]["seed"] if seed is None else seed)

    lo = pd.Timestamp(start) if start is not None else None
    hi = pd.Timestamp(end) if end is not None else None
    calendar = [pd.Timestamp(d) for d in ranked["date"].unique()
                if (lo is None or pd.Timestamp(d) >= lo)
                and (hi is None or pd.Timestamp(d) <= hi)]
    calendar.sort()
    if not calendar:
        return {"trades": [], "summary": {"trades": 0}, "calendar": [],
                "equity": [], "capital": capital}

    # index the rankings by date once; the walk asks for the same dates repeatedly
    by_date = {pd.Timestamp(d): g for d, g in ranked.groupby("date", sort=False)}

    cash, pos, order = float(capital), None, None
    done: list[dict[str, Any]] = []
    equity: list[float] = []
    cooldown: dict[str, pd.Timestamp] = {}

    def pick_name(day):
        day_rows = by_date.get(pd.Timestamp(day))
        if day_rows is None:
            return None
        live = day_rows[day_rows["clears"]
                        & ~day_rows["symbol"].isin(list(cooldown))]
        if live.empty:
            return None
        if pick == "rank":
            return live.sort_values(["score", "symbol"],
                                    ascending=[False, True]).iloc[0]
        return live.iloc[int(rng.integers(0, len(live)))]

    for day in calendar:
        # 1. a position whose exit session is today closes out first
        if pos is not None and day >= pos["trade"]["exit_date"]:
            # `cash_after` is already the whole account: the sell proceeds plus
            # the idle cash a rounded-down share count left over
            cash = pos["cash_after"]
            done.append(pos["trade"])
            if pos["trade"]["exit_reason"] in STOP_REASONS:
                cooldown[pos["trade"]["symbol"]] = day
            pos, order = None, None

        # 2. fill an order decided on an earlier session
        if order is not None:
            if day == order["fill_date"]:
                cols = prices[order["symbol"]]
                opened = _open_position(cols, order["symbol"], order["bar_i"],
                                        cash, model, cfg, order["signal_date"],
                                        order["score"])
                order = None
                if opened is not None:
                    pos = opened
                    equity.append(pos["idle"] + opened["trade"]["capital_after"])
                    continue
            elif day > order["fill_date"]:
                order = None  # the fill window passed; do not chase a stale entry

        if pos is not None:
            equity.append(pos["idle"] + _bar(prices[pos["trade"]["symbol"]], day)
                          * pos["trade"]["shares"])
            continue

        # 3. flat and nothing pending: mark the account, then find the next name
        equity.append(cash)
        blocked = {s for s, d in cooldown.items()
                   if (day - d).days < int(pol["cooldown_sessions"])}
        if blocked:
            cooldown = {s: d for s, d in cooldown.items() if s not in blocked}
        best = pick_name(day)
        if best is None:
            continue
        symbol = str(best["symbol"])
        cols = prices.get(symbol)
        if cols is None:
            continue
        j = int(np.searchsorted(cols["date"], np.datetime64(day), side="right")) - 1
        if j < 0 or j + 1 >= len(cols["date"]):
            continue
        order = {"symbol": symbol, "bar_i": j + 1,
                 "fill_date": pd.Timestamp(cols["date"][j + 1]),
                 "signal_date": day, "score": float(best["score"])}

    if pos is not None:
        done.append(pos["trade"])

    m = metrics.cohort_metrics(done, float(pol["target_net"]),
                               cfg["run"]["seed"], bootstrap_n)
    eq = np.array(equity, dtype=float)
    years = max((calendar[-1] - calendar[0]).days / 365.25, 1e-9)
    peak = np.maximum.accumulate(eq) if len(eq) else np.array([capital])
    final = float(eq[-1]) if len(eq) else float(capital)
    held = sum(t["sessions_held"] for t in done)
    summary = {
        "pick": pick, "trades": len(done), "initial": capital,
        "final": round(final, 2),
        "total_return": round(final / capital - 1.0, 4),
        "CAGR": round((final / capital) ** (1.0 / years) - 1.0, 4),
        "max_dd": round(float((eq / peak - 1.0).min()) if len(eq) else 0.0, 4),
        "exposure": round(min(held / max(len(calendar), 1), 1.0), 4),
        "years": round(years, 2),
        **{k: m.get(k) for k in ("WinRate", "Expectancy", "Expectancy_CI",
                                  "ProfitFactor", "SafeRate", "Sessions_mean",
                                  "TimeExitRate", "TailBreach")},
    }
    return {"trades": done, "summary": summary,
            "calendar": [str(d.date()) for d in calendar],
            "equity": eq.round(2).tolist()}


# --------------------------------------------------------------- cost reality
def capital_report(cfg: dict, capitals=None) -> pd.DataFrame:
    """What one rotation costs at each account size, before any edge question.

    The DP charge is flat per SELL and therefore scales as 1/capital. This is
    the table that decides whether a small account can rotate at all.
    """
    model = CostModel.from_config(cfg)
    target = float(cfg["rotation"]["target_net"])
    rows = []
    for cap in (capitals or cfg["run"]["capitals"]):
        px, shares = 250.0, shares_affordable(float(cap), 250.0, model)
        invested = px * shares
        gross = model.target_price(px, shares, target) / px - 1.0
        round_trip = (invested * model.buy_rate + invested * model.sell_rate
                      + model.dp_charge)
        rows.append({
            "capital": cap, "shares@250": shares,
            "dp_pct_of_capital": round(model.dp_charge / cap * 100, 2),
            "invested": round(invested * (1.0 + model.buy_rate), 2),
            "idle_cash_pct": round((cap - invested * (1.0 + model.buy_rate))
                                   / cap * 100, 1),
            "round_trip_bps_of_capital": round(round_trip / cap * 10000, 1),
            "gross_for_target": round(gross, 4),
        })
    return pd.DataFrame(rows)