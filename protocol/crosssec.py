"""Cross-sectional basket testing.

The spec (`chatgpt.txt`, CROSS-SECTIONAL TEST) requires:

    "At each historical date: rank eligible stocks by (1) momentum baseline,
     (2) 52W-high baseline, (3) breakout baseline, (4) proposed retention
     model. Compare top-N baskets. Use Top 5 / Top 10 / Top 20 only if enough
     securities exist. Do not cherry-pick the N that looks best."

Every result the engine produces is *event-level*: each qualifying trade is
scored independently, so nothing measures whether ranking stocks against each
other actually beats holding the universe. That gap matters, because
`scripts/decisions.py` ranks a cross-section and assumes the ranking carries
information -- an assumption the backtest never tested.

Three things this module refuses to do dishonestly:

  1. REPORT GROSS AND CALL IT A RESULT. Every basket return here is net of the
     real cost model (`protocol.costs`), charged on the fraction of the basket
     that actually changed. On a small account the flat DP charge is a large
     fraction of a position, and a gross number flatters exactly the
     high-turnover baskets that are hardest to actually trade.

  2. LET OVERLAPPING REBALANCES FAKE INDEPENDENCE. A weekly rebalance with a
     20-session holding period means four baskets are open at once and their
     returns are the same market move counted four times. Non-overlapping mode
     takes a new basket only once the previous one has finished, and the
     overlap factor is reported either way.

  3. LET THE FULL SAMPLE STAND IN FOR OUT-OF-SAMPLE. Results are also split
     into contiguous walk-forward folds around the configured discovery
     boundary, so a result that only exists in one era is visible as such.

Everything else is deliberately boring: a fixed rebalance calendar, a lagged
liquidity gate, scores read only from bars at or before the rebalance date,
outcomes measured strictly forward, and the equal-weight eligible universe as
the benchmark on the same dates.

Every configured top-N is reported. There is no code path that selects the
flattering one; `best` is presentational only.

Performance: NSE symbols share a session calendar, so scores are stacked into
aligned (symbol x date) matrices once and sliced column-wise per rebalance.
That turns a 700k-iteration Python loop into a few hundred vector operations.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from protocol.costs import CostModel
from protocol.reporting import crosssec_report

to_markdown = crosssec_report.to_markdown

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

    `breakout_score`    distance above the prior 20-session high.
    `acceptance_score`  PA State A acceptance -- retention weighted with closing
    range, discounted by how far the bar penetrated past the level (a huge
    penetration on weak retention is exhaustion, not strength).
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


def round_trip_bps(model: CostModel, capital: float) -> float:
    """Cost of buying and selling the WHOLE account, in basis points.

    The flat DP charge is converted to bps of the account, which is the only
    honest way to express it -- it does not scale with trade size, so on a
    small account it dominates everything else.
    """
    dp_bps = 1e4 * model.dp_charge / max(capital, 1.0)
    return 1e4 * (model.buy_rate + model.sell_rate) + dp_bps


def run_baskets(panel: dict[str, pd.DataFrame], cfg: dict,
                asof: pd.Timestamp | None = None) -> dict[str, Any]:
    """Rank eligible stocks each rebalance date and score the top-N baskets."""
    c = cfg["crosssec"]
    horizon = int(c["horizon"])
    tops = [int(t) for t in c["tops"]]
    min_elig = int(c["min_eligible"])
    freq = str(c["rebalance"])
    non_overlap = bool(c.get("non_overlapping", True))
    capital = float(c.get("cost_capital") or cfg["run"]["capitals"][0])
    rt_bps = round_trip_bps(CostModel.from_config(cfg), capital)
    cost_rate = rt_bps / 1e4
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
    n_d = len(dates)

    close = _stack(prepared, "Close", dates, symbols)
    fwd = np.full_like(close, np.nan)
    fwd[:, :n_d - horizon] = close[:, horizon:] / close[:, :n_d - horizon] - 1.0
    liq = cfg["liquidity"]
    eligible = (_stack(prepared, "turnover20", dates, symbols) >= float(liq["min_turnover20"])) \
        & (close >= float(liq["min_price"]))
    # Eligibility is lagged: the gate may only use information available
    # before the rebalance date, so it is shifted forward one session.
    eligible[:, 1:] = eligible[:, :-1]
    eligible[:, 0] = False
    eligible &= np.isfinite(fwd)
    scores = {name: _stack(prepared, col, dates, symbols)
              for name, col in SCORES.items()}

    buckets: dict[str, dict[int, list[dict[str, Any]]]] = {
        s: {t: [] for t in tops} for s in SCORES}
    universe: list[dict[str, Any]] = []
    last_j = -10 ** 9

    for j in np.where(rebalance_mask(dates, freq))[0]:
        if non_overlap and j - last_j < horizon:
            continue            # previous basket has not finished yet
        mask = eligible[:, j]
        if int(mask.sum()) < min_elig:
            continue
        last_j = j
        uni = fwd[mask, j]
        universe.append({"date": str(dates[j].date()), "n": int(mask.sum()),
                         "mean": float(np.nanmean(uni)),
                         "median": float(np.nanmedian(uni)),
                         "hit": float(np.nanmean(uni > 0))})
        idx = np.where(mask)[0]
        for name, mat in scores.items():
            vals = mat[idx, j]
            ok = np.isfinite(vals)
            if ok.sum() < min_elig:
                continue
            order = idx[ok][np.argsort(-vals[ok])]
            for t in tops:
                if len(order) < t:
                    continue
                buckets[name][t].append({
                    "date": dates[j],
                    "gross": float(np.nanmean(fwd[order[:t], j])),
                    "names": [symbols[i] for i in order[:t]],
                })
    return crosssec_report.summarise(buckets, universe, tops, horizon, freq,
                                     cost_rate, rt_bps, capital, cfg)
