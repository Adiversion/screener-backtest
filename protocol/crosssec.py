"""Cross-sectional basket testing.

The spec (`chatgpt.txt`, CROSS-SECTIONAL TEST) requires:

    "At each historical date: rank eligible stocks by (1) momentum baseline,
     (2) 52W-high baseline, (3) breakout baseline, (4) proposed retention
     model. Compare top-N baskets. Use Top 5 / Top 10 / Top 20 only if enough
     securities exist. Do not cherry-pick the N that looks best."

This was never implemented. Every result the engine produces is *event-level*:
each qualifying trade is scored independently, so nothing measures whether
ranking stocks against each other actually beats holding the universe. That
gap matters, because `scripts/decisions.py` ranks a cross-section and assumes
the ranking carries information -- an assumption the backtest never tested.

The design is deliberately boring so that it cannot cheat:

  * a rebalance calendar (weekly by default), never event-driven
  * eligibility from a **lagged** liquidity gate, so the filter uses only
    data that existed before the rebalance date
  * every score reads only bars at or before the rebalance date
  * the outcome is the equal-weighted forward return over the holding horizon,
    measured strictly forward
  * the benchmark is the whole eligible cross-section on the same dates, so
    the comparison is like-for-like and market-agnostic
  * turnover is reported, because a basket that swaps its whole membership
    every week is not something a person can actually hold

Every top-N in the configured list is reported. There is no code path that
selects the flattering one; `best` is presentational only.

Performance: NSE symbols share a session calendar, so scores are stacked into
aligned (symbol x date) matrices once and then sliced column-wise per
rebalance date. That turns a 700k-iteration Python loop into a few hundred
vector operations.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

# name -> source column. All are point-in-time features already in the panel.
SCORES: dict[str, str] = {
    "momentum60": "ret60",
    "momentum120": "ret120",
    "prox52": "prox52",
    "breakout": "breakout_score",
    "acceptance": "acceptance_score",
}


def add_scores(feat: pd.DataFrame) -> pd.DataFrame:
    """Attach the cross-sectional score columns. All point-in-time.

    `breakout_score`  distance above the prior 20-session high.
    `acceptance_score`  PA State A acceptance -- retention weighted with closing
    range, discounted by how far the bar penetrated past the level (a huge
    penetration on weak retention is the exhaustion case, not the good one).
    """
    d = feat.copy()
    r20 = d["R20"] if "R20" in d.columns else pd.Series(np.nan, index=d.index)
    with np.errstate(divide="ignore", invalid="ignore"):
        d["breakout_score"] = np.where(
            (r20 > 0).to_numpy(), (d["Close"] / r20.replace(0, np.nan)).to_numpy() - 1.0,
            np.nan)
    ret = pd.to_numeric(d["retention"], errors="coerce")
    cr = pd.to_numeric(d["closing_range"], errors="coerce")
    pen = pd.to_numeric(d.get("penetration", np.nan), errors="coerce").fillna(0.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        d["acceptance_score"] = (0.6 * ret + 0.4 * cr).to_numpy() / \
                               (1.0 + pen.clip(lower=0.0)).to_numpy()
    return d


def rebalance_mask(dates: pd.DatetimeIndex, freq: str) -> np.ndarray:
    """Boolean mask of sessions on which a rebalance may occur."""
    s = pd.Series(dates)
    f = str(freq).upper()
    if f.startswith("W"):
        key = s.dt.isocalendar().year.astype(str) + "W" + \
              s.dt.isocalendar().week.astype(str).str.zfill(2)
    elif f.startswith("M"):
        key = s.dt.to_period("M").astype(str)
    else:
        return np.ones(len(s), dtype=bool)
    return (~key.duplicated()).to_numpy()


def _stack(panel: dict[str, pd.DataFrame], column: str,
           dates: pd.DatetimeIndex, symbols: list[str]) -> np.ndarray:
    """(symbol x date) matrix for one column, NaN where unavailable."""
    out = np.full((len(symbols), len(dates)), np.nan)
    for i, sym in enumerate(symbols):
        d = panel.get(sym)
        if d is None or column not in d.columns:
            continue
        s = pd.to_numeric(d[column], errors="coerce")
        out[i] = s.reindex(dates).to_numpy()
    return out


def run_baskets(panel: dict[str, pd.DataFrame], cfg: dict,
                asof: pd.Timestamp | None = None) -> dict[str, Any]:
    """Rank eligible stocks each rebalance date and score the top-N baskets."""
    c = cfg["crosssec"]
    horizon = int(c["horizon"])
    tops = [int(t) for t in c["tops"]]
    min_elig = int(c["min_eligible"])
    freq = str(c["rebalance"])
    end = pd.Timestamp(asof) if asof is not None else None

    prepared: dict[str, pd.DataFrame] = {}
    for symbol, feat in panel.items():
        d = add_scores(feat.reset_index(drop=True))
        if end is not None:
            d = d[d["Date"] <= end].reset_index(drop=True)
        if len(d) > horizon + 2:
            prepared[symbol] = d.set_index("Date")
    if not prepared:
        return {"error": "no panel data"}

    dates = pd.DatetimeIndex(sorted(set().union(
        *[set(prepared[s].index) for s in prepared])))
    symbols = sorted(prepared)
    n_s, n_d = len(symbols), len(dates)

    close = _stack(prepared, "Close", dates, symbols)
    fwd = np.full_like(close, np.nan)
    fwd[:, :n_d - horizon] = close[:, horizon:] / close[:, :n_d - horizon] - 1.0
    liq = cfg["liquidity"]
    turn = _stack(prepared, "turnover20", dates, symbols)
    price = close
    # Eligibility is lagged: the gate may only use information available
    # before the rebalance date, so it is shifted forward one session.
    eligible = (turn >= float(liq["min_turnover20"])) & (price >= float(liq["min_price"]))
    eligible[:, 1:] = eligible[:, :-1]
    eligible[:, 0] = False
    eligible &= np.isfinite(fwd)

    scores = {name: _stack(prepared, col, dates, symbols)
              for name, col in SCORES.items()}

    buckets: dict[str, dict[int, list[dict[str, Any]]]] = {
        s: {t: [] for t in tops} for s in SCORES}
    universe: list[dict[str, Any]] = []
    breadth: list[int] = []

    for j in np.where(rebalance_mask(dates, freq))[0]:
        mask = eligible[:, j]
        n_elig = int(mask.sum())
        if n_elig < min_elig:
            continue
        breadth.append(n_elig)
        uni_fwd = fwd[mask, j]
        universe.append({"date": str(dates[j].date()),
                         "mean": float(np.nanmean(uni_fwd)),
                         "median": float(np.nanmedian(uni_fwd)),
                         "hit": float(np.nanmean(uni_fwd > 0))})
        idx = np.where(mask)[0]
        for name, mat in scores.items():
            vals = mat[idx, j]
            ok = np.isfinite(vals)
            if ok.sum() < min_elig:
                continue
            order = idx[ok][np.argsort(-vals[ok])]
            picks = fwd[order, j]
            for t in tops:
                if len(order) < t:
                    continue
                head = picks[:t]
                buckets[name][t].append({
                    "date": str(dates[j].date()),
                    "mean": float(np.nanmean(head)),
                    "median": float(np.nanmedian(head)),
                    "hit": float(np.nanmean(head > 0)),
                    "names": [symbols[i] for i in order[:t]],
                })
    return _summarise(buckets, universe, tops, breadth, horizon, freq)


def _turnover(records: list[dict[str, Any]]) -> float | None:
    """Average fraction of the basket that changed between rebalances."""
    if len(records) < 2:
        return None
    changed = [1.0 - len(set(a["names"]) & set(b["names"])) / len(b["names"])
               for a, b in zip(records, records[1:])]
    return round(float(np.mean(changed)), 4) if changed else None


def _summarise(buckets, universe, tops, breadth, horizon, freq) -> dict[str, Any]:
    uni = pd.DataFrame(universe)
    bench = float(uni["mean"].mean()) if not uni.empty else None
    bench_med = float(uni["median"].mean()) if not uni.empty else None
    bench_hit = (round(float(uni["hit"].mean()), 4) if not uni.empty else None)
    results: list[dict[str, Any]] = []
    for name, per_top in buckets.items():
        for t in tops:
            recs = per_top.get(t) or []
            if not recs:
                results.append({"score": name, "top": t, "rebalances": 0})
                continue
            m = float(np.mean([r["mean"] for r in recs]))
            med = float(np.mean([r["median"] for r in recs]))
            results.append({
                "score": name, "top": t, "rebalances": len(recs),
                "mean_fwd": round(m, 5), "median_fwd": round(med, 5),
                "hit_rate": round(float(np.mean([r["hit"] for r in recs])), 4),
                "vs_universe_mean": round(m - bench, 5) if bench is not None else None,
                "vs_universe_median": round(med - bench_med, 5) if bench_med is not None else None,
                "turnover": _turnover(recs),
            })
    live = [r for r in results if r.get("rebalances", 0) > 0]
    live.sort(key=lambda r: -(r.get("vs_universe_mean") if r.get("vs_universe_mean")
                              is not None else -9e9))
    return {
        "rebalance": freq, "horizon_sessions": horizon,
        "rebalances_evaluated": int(len(uni)),
        "median_eligible_breadth": int(np.median(breadth)) if breadth else 0,
        "universe_mean_fwd": round(bench, 5) if bench is not None else None,
        "universe_median_fwd": round(bench_med, 5) if bench_med is not None else None,
        "universe_hit_rate": bench_hit,
        "results": results, "ranked": live,
        "best": live[0] if live else None,
        "note": "Every configured top-N is reported. There is no code path that "
                "selects a flattering N; `best` is presentational only.",
    }


def to_markdown(payload: dict[str, Any]) -> str:
    p = payload
    if p.get("error"):
        return f"## 4. Cross-sectional basket test\n\n_{p['error']}_\n"
    L = ["## 4. Cross-sectional basket test", "",
         f"- Rebalance: **{p['rebalance']}**, holding horizon "
         f"**{p['horizon_sessions']} sessions**",
         f"- Rebalances evaluated: **{p['rebalances_evaluated']}**",
         f"- Median eligible breadth: **{p['median_eligible_breadth']}** names",
         f"- Equal-weight universe benchmark: mean **{p['universe_mean_fwd']}**, "
         f"median **{p['universe_median_fwd']}**, hit **{p['universe_hit_rate']}**", "",
         "| Score | Top | Rebalances | Mean fwd | Median fwd | Hit | vs universe | Turnover |",
         "|---|---|---|---|---|---|---|---|"]
    for r in p["results"]:
        if not r.get("rebalances"):
            L.append(f"| `{r['score']}` | {r['top']} | 0 | _no data_ | | | | |")
            continue
        L.append(f"| `{r['score']}` | {r['top']} | {r['rebalances']} | "
                 f"{r['mean_fwd']} | {r['median_fwd']} | {r['hit_rate']} | "
                 f"{r['vs_universe_mean']} | {r['turnover']} |")
    L += ["", f"_{p['note']}_", ""]
    return "\n".join(L)