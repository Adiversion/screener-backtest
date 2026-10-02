"""B4/B5/B7: cross-sectional weekly top-N ranking baselines.

Each Monday (first trading bar of the ISO week per symbol) every symbol is
ranked on a score; the top N by score are signalled, entry next session.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from protocol.signals import TradeSignal
from protocol.strategies import REGISTRY, register


def _weekly_topn(panel, score_col, n, name, extra_filter=None):
    rows = []
    for symbol, feat in panel.items():
        d = feat.reset_index(drop=True)
        if extra_filter is not None:
            d = d[extra_filter(d)]
        d = d.assign(_week=d["Date"].dt.isocalendar().week.astype(int),
                     _year=d["Date"].dt.isocalendar().year.astype(int))
        first = d.groupby(["_year", "_week"], sort=False).head(1)
        for _, r in first.iterrows():
            if not np.isnan(r[score_col]):
                rows.append((r["Date"], symbol, float(r[score_col])))
    if not rows:
        return []
    frame = pd.DataFrame(rows, columns=["date", "symbol", "score"])
    out: list[TradeSignal] = []
    for date, grp in frame.groupby("date"):
        for _, r in grp.nlargest(n, "score").iterrows():
            d = panel[r["symbol"]].reset_index(drop=True)
            hits = d.index[d["Date"] == date]
            if len(hits) == 0 or int(hits[0]) + 1 >= len(d):
                continue
            idx = int(hits[0])
            out.append(TradeSignal(name, r["symbol"], date, d["Date"].iloc[idx + 1],
                                   float(d["Close"].iloc[idx]), stop_pct=0.07, meta={}))
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
