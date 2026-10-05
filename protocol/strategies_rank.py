"""B4/B5/B7: cross-sectional weekly top-N ranking baselines.

Each Monday (first trading bar of the ISO week per symbol) every symbol is
ranked on a score; the top N by score are signalled, entry next session.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from protocol.signals import TradeSignal
from protocol.strategies import register


def _weekly_topn(panel, score_col, n, name, extra_filter=None):
    """First session of each ISO week per symbol -> top-N by score each week."""
    rows: list[tuple] = []
    for symbol, feat in panel.items():
        d = feat.reset_index(drop=True)
        if extra_filter is not None:
            d = d[extra_filter(d)]
        if d.empty:
            continue
        iso = d["Date"].dt.isocalendar()
        wk = iso["year"].to_numpy() * 100 + iso["week"].to_numpy()
        _, first = np.unique(wk, return_index=True)  # first row of each week
        score = d[score_col].to_numpy(float)
        dates = d["Date"].to_numpy()
        for i in first:
            if not np.isnan(score[i]):
                rows.append((dates[i], symbol, float(score[i])))
    if not rows:
        return []
    frame = pd.DataFrame(rows, columns=["date", "symbol", "score"])
    cache: dict[str, tuple[dict, object]] = {}
    out: list[TradeSignal] = []
    for date, grp in frame.groupby("date", sort=True):
        day = pd.Timestamp(date)
        for _, r in grp.nlargest(n, "score").iterrows():
            symbol = r["symbol"]
            hit = cache.get(symbol)
            if hit is None:
                d = panel[symbol].reset_index(drop=True)
                hit = ({ts: i for i, ts in enumerate(d["Date"])}, d)
                cache[symbol] = hit
            pos, d = hit
            i = pos.get(day)
            if i is None or i + 1 >= len(d):
                continue
            out.append(TradeSignal(name, symbol, day, d["Date"].iloc[i + 1],
                                   float(d["Close"].iloc[i]), stop_pct=0.07, meta={}))
    return out


@register("momentum_top")
def momentum_top(panel, cfg) -> list[TradeSignal]:
    n = int((cfg.get("strategies", {}).get("momentum_top", {})).get("n", 20))
    return _weekly_topn(panel, "ret60", n, "momentum_top")


@register("high_52w")
def high_52w(panel, cfg) -> list[TradeSignal]:
    n = int((cfg.get("strategies", {}).get("high_52w", {})).get("n", 20))
    return _weekly_topn(panel, "prox52", n, "high_52w")


@register("fip_proxy")
def fip_proxy(panel, cfg) -> list[TradeSignal]:
    n = int((cfg.get("strategies", {}).get("fip_proxy", {})).get("n", 20))
    return _weekly_topn(panel, "pos_day_freq60", n, "fip_proxy",
                        extra_filter=lambda d: d["ret120"] > 0)
