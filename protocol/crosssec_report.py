"""Reporting half of the cross-sectional basket test.

Split out from `protocol/crosssec.py` purely to respect the 300-line house
rule; the two modules are one concern. `crosssec` builds the matrices and the
per-rebalance records, this module turns them into the net-of-costs summary,
the walk-forward folds and the markdown.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def turnover(prev: list[str] | None, cur: list[str]) -> float:
    """One-way fraction of the basket that changed since the last rebalance."""
    if not prev:
        return 1.0
    return 1.0 - len(set(prev) & set(cur)) / len(cur)


def folds(recs: list[dict[str, Any]], cost_rate: float, n_folds: int,
           oos_from: pd.Timestamp) -> list[dict[str, Any]]:
    """Net mean per walk-forward fold, so era-dependence is visible."""
    if len(recs) < n_folds:
        return []
    edges = np.linspace(0, len(recs), n_folds + 1).astype(int)
    out = []
    for k in range(n_folds):
        chunk = recs[edges[k]:edges[k + 1]]
        if not chunk:
            continue
    prev, nets = None, []
    for r in chunk:
        turn = turnover(prev, r["names"])
        nets.append(r["gross"] - turn * cost_rate)
        prev = r["names"]
        out.append({"fold": k + 1, "n": len(chunk),
                    "from": str(chunk[0]["date"].date()),
                    "to": str(chunk[-1]["date"].date()),
                    "net_mean": round(float(np.mean(nets)), 5),
                    "oos": bool(chunk[0]["date"] >= oos_from)})
    return out


def summarise(buckets, universe, tops, horizon, freq, cost_rate, rt_bps,
               capital, cfg) -> dict[str, Any]:
    oos_from = pd.Timestamp(cfg["validation"]["discovery_end"]) + pd.Timedelta(days=1)
    n_folds = int(cfg["crosssec"].get("walk_forward_folds", 5))
    uni = pd.DataFrame(universe)
    bench = float(uni["mean"].mean()) if not uni.empty else None
    bench_med = float(uni["median"].mean()) if not uni.empty else None
    results: list[dict[str, Any]] = []
    for name, per_top in buckets.items():
        for t in tops:
            recs = per_top.get(t) or []
            if not recs:
                results.append({"score": name, "top": t, "rebalances": 0})
                continue
            prev, nets, turns = None, [], []
            for r in recs:
                turn = turnover(prev, r["names"])
                turns.append(turn)
                nets.append(r["gross"] - turn * cost_rate)
                prev = r["names"]
            gross = float(np.mean([r["gross"] for r in recs]))
            net = float(np.mean(nets))
            oos = [n for r, n in zip(recs, nets) if r["date"] >= oos_from]
            results.append({
                "score": name, "top": t, "rebalances": len(recs),
                "gross_fwd": round(gross, 5), "net_fwd": round(net, 5),
                "cost_drag": round(gross - net, 5),
                "vs_universe_gross": round(gross - bench, 5) if bench is not None else None,
                "vs_universe_net": round(net - bench, 5) if bench is not None else None,
                "mean_turnover": round(float(np.mean(turns)), 4),
                "oos_rebalances": len(oos),
                "oos_net": round(float(np.mean(oos)), 5) if oos else None,
                "folds": folds(recs, cost_rate, n_folds, oos_from),
            })
    live = [r for r in results if r.get("rebalances", 0) > 0]
    live.sort(key=lambda r: -(r.get("vs_universe_net")
                              if r.get("vs_universe_net") is not None else -9e9))
    return {
        "rebalance": freq, "horizon_sessions": horizon,
        "non_overlapping": bool(cfg["crosssec"].get("non_overlapping", True)),
        "rebalances_evaluated": int(len(uni)),
        "median_eligible_breadth": int(np.median(
            [u["n"] for u in universe])) if universe else 0,
        "universe_gross_fwd": round(bench, 5) if bench is not None else None,
        "universe_median_fwd": round(bench_med, 5) if bench_med is not None else None,
        "round_trip_bps": round(rt_bps, 2), "cost_capital": capital,
        "oos_from": str(oos_from.date()),
        "results": results, "ranked": live,
        "best": live[0] if live else None,
        "note": "Net columns deduct the real cost model on the fraction of the "
                "basket that changed. Every configured top-N is reported; there is "
                "no code path that selects a flattering N.",
    }


def to_markdown(payload: dict[str, Any]) -> str:
    p = payload
    if p.get("error"):
        return f"## 4. Cross-sectional basket test\n\n_{p['error']}_\n"
    L = ["## 4. Cross-sectional basket test", "",
         f"- Rebalance **{p['rebalance']}**, horizon **{p['horizon_sessions']}** "
         f"sessions, non-overlapping: **{p['non_overlapping']}**",
         f"- Rebalances evaluated: **{p['rebalances_evaluated']}**",
         f"- Round-trip cost assumed: **{p['round_trip_bps']} bps** on an account of "
         f"INR {p['cost_capital']:,.0f} (the flat DP charge dominates at this size)",
         f"- Equal-weight universe benchmark (gross): **{p['universe_gross_fwd']}**",
         f"- Out-of-sample from: **{p['oos_from']}**", "",
         "| Score | Top | Rebal | Gross | Net | Cost drag | vs uni (net) | Turnover | OOS net |",
         "|---|---|---|---|---|---|---|---|---|"]
    for r in p["results"]:
        if not r.get("rebalances"):
            L.append(f"| `{r['score']}` | {r['top']} | 0 | _no data_ | | | | | |")
            continue
        L.append(f"| `{r['score']}` | {r['top']} | {r['rebalances']} | "
                 f"{r['gross_fwd']} | **{r['net_fwd']}** | {r['cost_drag']} | "
                 f"{r['vs_universe_net']} | {r['mean_turnover']} | {r['oos_net']} |")
    best = p.get("best")
    if best and best.get("folds"):
        L += ["", f"### Walk-forward folds for the best basket "
              f"(`{best['score']}` top {best['top']}, net)", "",
              "| Fold | Period | Rebal | Net | Regime |", "|---|---|---|---|---|"]
        for f in best["folds"]:
            L.append(f"| {f['fold']} | {f['from']} → {f['to']} | {f['n']} | "
                     f"{f['net_mean']} | {'**OOS**' if f['oos'] else 'IS'} |")
    L += ["", f"_{p['note']}_", ""]
    return "\n".join(L)