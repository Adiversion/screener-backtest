"""Price-Acceptance strategies and the PDF's M1/N1-N4 baselines.

From "Price Acceptance Strategy Origins": the four-state A/B/C/D machine plus
the mainstream (M1-M4) and community (N1-N4) comparison models. M2-M4 already
exist as `high_52w`, `vol_breakout` and `trend`; this module registers the
remaining ones on the shared simulator so all cohorts are directly comparable.

The PDF's liquidity gate (20-day turnover / minimum price / 252 sessions) is
applied inside every strategy registered here.
"""
from __future__ import annotations

import numpy as np

from protocol import pa
from protocol.signals import TradeSignal
from protocol.strategies import _params, register
from protocol.strategies_rank import _weekly_topn


def _emit_daily(panel, cfg, name, condition, stop_pct=0.07) -> list[TradeSignal]:
    """Emit a next-session entry for every bar passing `condition`."""
    out: list[TradeSignal] = []
    for symbol, feat in panel.items():
        d = feat.reset_index(drop=True)
        if len(d) < 2:
            continue
        ok = condition(d) & pa.liquid_mask(d, cfg)
        for idx in np.where(ok.fillna(False).to_numpy())[0]:
            i = int(idx)
            if i + 1 >= len(d):
                continue
            out.append(TradeSignal(name, symbol, d["Date"].iloc[i], d["Date"].iloc[i + 1],
                                   float(d["Close"].iloc[i]), stop_pct=stop_pct, meta={}))
    return out


def _emit_states(panel, cfg, name, wanted, stop_pct=0.07) -> list[TradeSignal]:
    """Emit a next-session entry for each classified State A/B/C/D event."""
    out: list[TradeSignal] = []
    for symbol, feat in panel.items():
        events = pa.classify_states(feat, cfg, symbol)
        if events.empty:
            continue
        events = events[events["state"].isin(wanted)]
        d = feat.reset_index(drop=True)
        idx_of = {ts: i for i, ts in enumerate(d["Date"])}
        for _, ev in events.iterrows():
            i = idx_of.get(ev["date"])
            if i is None or i + 1 >= len(d):
                continue
            ret = ev["retention"]
            out.append(TradeSignal(name, symbol, ev["date"], d["Date"].iloc[i + 1],
                                   float(d["Close"].iloc[i]), stop_pct=stop_pct,
                                   meta={"state": ev["state"],
                                         "retention": round(float(ret), 4) if not np.isnan(ret) else None}))
    return out


@register("pa_state_a")
def pa_state_a(panel, cfg) -> list[TradeSignal]:
    return _emit_states(panel, cfg, "pa_state_a", ["A_ACCEPTED_EXPANSION"])


@register("pa_state_b")
def pa_state_b(panel, cfg) -> list[TradeSignal]:
    return _emit_states(panel, cfg, "pa_state_b", ["B_PENDING_ACCEPTANCE"])


@register("pa_state_c")
def pa_state_c(panel, cfg) -> list[TradeSignal]:
    return _emit_states(panel, cfg, "pa_state_c", ["C_REJECTION_RECOVERY_PENDING"])


@register("pa_state_d")
def pa_state_d(panel, cfg) -> list[TradeSignal]:
    """Deliberate failure control: State D should show negative expectancy."""
    return _emit_states(panel, cfg, "pa_state_d", ["D_FAILED_ACCEPTANCE"])


@register("m1_momentum_composite")
def m1_momentum_composite(panel, cfg) -> list[TradeSignal]:
    """M1: equal-weight 20/60/120-day composite, weekly top-N."""
    n = int(_params(cfg, "m1_momentum_composite").get("n", 20))
    temp = {}
    for symbol, feat in panel.items():
        d = feat.copy()
        d["_m1"] = (d["ret20"].fillna(0.0) + d["ret60"].fillna(0.0)
                    + d["ret120"].fillna(0.0)) / 3.0
        temp[symbol] = d
    return _weekly_topn(temp, "_m1", n, "m1_momentum_composite")


@register("n1_eod_momentum")
def n1_eod_momentum(panel, cfg) -> list[TradeSignal]:
    """N1: gap + relative volume + 20d breakout + ATR expansion + 5d slope."""
    p = _params(cfg, "n1_eod_momentum")
    gap_min, rvol_min = p.get("gap_min", 0.01), p.get("rvol_min", 1.5)

    def cond(d):
        gap = d["Open"] / d["Close"].shift(1) - 1.0
        return ((gap >= gap_min) & (d["rvol20"] >= rvol_min) & (d["Close"] > d["R20"])
                & (d["atr14"] > d["atr14"].shift(1)) & (d["Close"] > d["Close"].shift(5)))

    return _emit_daily(panel, cfg, "n1_eod_momentum", cond)


@register("n2_consolidation_breakout")
def n2_consolidation_breakout(panel, cfg) -> list[TradeSignal]:
    """N2: break of the prior 10-session 20d level out of a compressed band."""
    p = _params(cfg, "n2_consolidation_breakout")
    max_band, rvol_min = p.get("max_band", 0.08), p.get("rvol_min", 1.2)

    def cond(d):
        prior = d.shift(1)
        band = (prior["High"].rolling(10).max() - prior["Low"].rolling(10).min()) / prior["Close"]
        return (band <= max_band) & (d["Close"] > d["R10"]) & (d["rvol20"] >= rvol_min)

    return _emit_daily(panel, cfg, "n2_consolidation_breakout", cond)


@register("n3_absorption")
def n3_absorption(panel, cfg) -> list[TradeSignal]:
    """N3: high effort, low price progress, near the 20-day high."""
    p = _params(cfg, "n3_absorption")
    rvol_min, max_res = p.get("rvol_min", 2.0), p.get("max_result_atr", 0.5)
    near = p.get("near_high", 0.98)

    def cond(d):
        return ((d["rvol20"] >= rvol_min) & (d["result_atr"] <= max_res)
                & (d["Close"] >= near * d["R20"]))

    return _emit_daily(panel, cfg, "n3_absorption", cond)


@register("n4_effort_result_discrepancy")
def n4_effort_result_discrepancy(panel, cfg) -> list[TradeSignal]:
    """N4 Wyckoff effort/result failure: high volume, poor closing range."""
    p = _params(cfg, "n4_effort_result_discrepancy")
    rvol_min, max_cr = p.get("rvol_min", 2.0), p.get("max_closing_range", 0.35)

    def cond(d):
        return (d["rvol20"] >= rvol_min) & (d["closing_range"] <= max_cr)

    return _emit_daily(panel, cfg, "n4_effort_result_discrepancy", cond)
