"""The INR 1,000 one-position rotation experiment (gpt6 protocol, Part B).

Unlike the event-level backtest, this runs ONE chronological portfolio:
start at `initial_capital`, hold at most one stock, buy whole shares only,
reinvest only the remaining net cash after costs. Entry is the next session's
open; exits are target / stop / time, with stop-first when a bar touches both.

Candidate selection is the frozen ORGANIC ranking from `protocol.screen`
(least-extended, best-retained first); affordability failures fall through to
the next-ranked candidate deterministically. No lookahead: the ranking at a
session close uses only data through that close.
"""
from __future__ import annotations

import copy
from typing import Any

import numpy as np
import pandas as pd

from protocol import pa, screen
from protocol.costs import CostModel
from protocol.features import build_panel
from protocol.simulator import prepare, simulate
from protocol.signals import TradeSignal


def rotation_run_cfg(cfg: dict) -> dict:
    """Exit config for the rotation: time stop only, momentum-fail disabled."""
    out = copy.deepcopy(cfg)
    out.setdefault("run", {})
    out["run"]["hold_sessions"] = int(cfg["rotation"]["max_holding_sessions"])
    out["run"]["momentum_fail_mfe"] = -1.0  # unreachable -> factor disabled
    return out


def build_candidates(panel: dict[str, pd.DataFrame], cfg: dict) -> pd.DataFrame:
    """Every historical session tagged and ranked within its date."""
    wanted = cfg["rotation"]["candidate_tag"]
    frames = []
    for symbol, feat in panel.items():
        events = pa.classify_states(feat, cfg, symbol)
        if events.empty:
            continue
        d = feat.reset_index(drop=True)
        pos = {ts: i for i, ts in enumerate(d["Date"])}
        events = events.assign(
            tag=[screen.tag_state(s, r, c, cfg) for s, r, c in
                 zip(events["state"], events["RVOL20"], events["closing_range"])],
            close=[float(d["Close"].iloc[pos[t]]) for t in events["date"]],
        )
        frames.append(events)
    if not frames:
        return pd.DataFrame()
    all_ev = pd.concat(frames, ignore_index=True)
    cand = all_ev[all_ev["tag"] == wanted].copy()
    if cand.empty:
        return cand
    cand = cand.sort_values(["date", "penetration", "retention"],
                            ascending=[True, True, False])
    cand["rank"] = cand.groupby("date").cumcount() + 1
    return cand.reset_index(drop=True)


def prepare_rotation(cfg: dict, history: pd.DataFrame) -> dict[str, Any]:
    bars = {s: b.sort_values("Date").reset_index(drop=True)
            for s, b in history.groupby("Symbol")}
    return {
        "bars": bars,
        "arrays": {s: prepare(b) for s, b in bars.items()},
        "cands": build_candidates(build_panel(history), cfg),
        "sessions": pd.DatetimeIndex(sorted(history["Date"].unique())),
    }


def run_rotation(cfg: dict, history: pd.DataFrame, start: Any = None, end: Any = None,
                 capital: float | None = None, label: str = "rotation",
                 prepared: dict[str, Any] | None = None) -> dict[str, Any]:
    rot = cfg["rotation"]
    capital = float(capital if capital is not None else rot["initial_capital"])
    prep = prepared or prepare_rotation(cfg, history)
    bars, arrays, cands = prep["bars"], prep["arrays"], prep["cands"]
    sessions = prep["sessions"]
    if start is not None:
        sessions = sessions[sessions >= pd.Timestamp(start)]
    if end is not None:
        sessions = sessions[sessions <= pd.Timestamp(end)]
    if len(sessions) < 2:
        return {"label": label, "metrics": {"trades": 0}, "trades": [], "equity": []}

    sim_cfg = rotation_run_cfg(cfg)
    model = CostModel.from_config(cfg)
    by_date = ({pd.Timestamp(d): g.sort_values("rank")
                for d, g in cands[cands["date"].isin(sessions)].groupby("date")}
               if not cands.empty else {})
    cash, trades, equity = capital, [], []
    i = 0
    while i < len(sessions):
        grp = by_date.get(sessions[i])
        if grp is None or i + 1 >= len(sessions):
            i += 1
            continue
        entry = sessions[i + 1]
        for _, c in grp.iterrows():
            sym = c["symbol"]
            if sym not in bars:
                continue
            sig = TradeSignal(label, sym, pd.Timestamp(sessions[i]), pd.Timestamp(entry),
                              float(c["close"]), stop_pct=float(rot["stop_fraction"]),
                              meta={"tag": c["tag"], "rank": int(c["rank"]), "state": c["state"]})
            out = simulate(sig, bars[sym], sim_cfg, model, cash, arrays[sym],
                           target_gross=float(rot["target_fraction"]))
            if out.get("skipped"):
                continue  # unaffordable / gap / no entry bar -> next-ranked candidate
            trades.append(out)
            cash += float(out["net_pnl"])
            equity.append({"date": str(out["exit_date"]), "cash": round(cash, 2)})
            i = int(sessions.searchsorted(pd.Timestamp(out["exit_date"]), side="right"))
            break
        else:
            i += 1

    metrics = summarize(trades, cash, capital, sessions)
    return {"label": label, "start": str(sessions[0].date()), "end": str(sessions[-1].date()),
            "initial_capital": capital, "final_cash": round(cash, 2), "metrics": metrics,
            "trades": trades, "equity": equity}


def summarize(trades: list[dict], final_cash: float, capital: float,
              sessions) -> dict[str, Any]:
    n = len(trades)
    if n == 0:
        return {"trades": 0, "final_value": round(final_cash, 2),
                "total_return": round(final_cash / capital - 1.0, 4),
                "time_in_cash": 1.0, "total_fees": 0.0}
    pct = np.array([t["net_pnl_pct"] for t in trades], dtype=float)
    reasons = [t["exit_reason"] for t in trades]
    wins, losses = pct[pct > 0], pct[pct < 0]
    running, peak, max_dd = capital, capital, 0.0
    streak = worst_streak = 0
    for t in trades:
        running += float(t["net_pnl"])
        peak = max(peak, running)
        max_dd = min(max_dd, running / peak - 1.0)
        streak = streak + 1 if t["net_pnl"] < 0 else 0
        worst_streak = max(worst_streak, streak)
    held = int(sum(t["sessions_held"] for t in trades))
    start, end = pd.Timestamp(trades[0]["entry_date"]), pd.Timestamp(trades[-1]["exit_date"])
    years = max((end - start).days / 365.25, 1e-9)
    cagr = (final_cash / capital) ** (1.0 / years) - 1.0 if final_cash > 0 else -1.0
    gross_loss = -losses.sum()
    return {
        "trades": n,
        "target_first_rate": round(float(np.mean([r == "TARGET" for r in reasons])), 4),
        "stop_first_rate": round(float(np.mean([r in ("STOP", "GAP_STOP") for r in reasons])), 4),
        "time_exit_rate": round(float(np.mean([r == "TIME" for r in reasons])), 4),
        "ambiguous_bars": int(sum(bool(t.get("ambiguous")) for t in trades)),
        "net_win_rate": round(float((pct > 0).mean()), 4),
        "expectancy": round(float(pct.mean()), 4),
        "avg_win": round(float(wins.mean()), 4) if len(wins) else None,
        "avg_loss": round(float(losses.mean()), 4) if len(losses) else None,
        "profit_factor": round(float(pct[pct > 0].sum() / gross_loss), 3) if gross_loss > 0 else None,
        "best_trade": round(float(pct.max()), 4), "worst_trade": round(float(pct.min()), 4),
        "max_drawdown": round(float(max_dd), 4), "longest_losing_streak": int(worst_streak),
        "total_fees": round(float(sum(t.get("costs", 0.0) for t in trades)), 2),
        "sessions_in_market": held,
        "time_in_cash": round(1.0 - held / max(len(sessions), 1), 4),
        "final_value": round(final_cash, 2),
        "total_return": round(final_cash / capital - 1.0, 4),
        "cagr": round(cagr, 4), "years": round(years, 2),
    }


def rolling_starts(cfg: dict, history: pd.DataFrame, step_sessions: int = 252,
                   capital: float | None = None) -> pd.DataFrame:
    """Predefined rolling-start experiments (gpt6 s14): all starts, not just the best."""
    prep = prepare_rotation(cfg, history)
    sessions = prep["sessions"]
    rows = []
    for k in range(0, max(len(sessions) - 60, 1), int(step_sessions)):
        res = run_rotation(cfg, history, start=sessions[k], capital=capital,
                           label=f"start_{sessions[k].date()}", prepared=prep)
        m = res["metrics"]
        rows.append({"start": res["start"], "end": res["end"],
                     "trades": m.get("trades"), "final_value": m.get("final_value"),
                     "total_return": m.get("total_return"), "cagr": m.get("cagr"),
                     "max_drawdown": m.get("max_drawdown"),
                     "stop_first_rate": m.get("stop_first_rate")})
    return pd.DataFrame(rows)
