"""Pressure-Response-Acceptance strategies, so PRA cohorts can be run
through the same simulator and compared against AAE and the baselines.
"""
from __future__ import annotations

import numpy as np

from protocol import pra
from protocol.signals import TradeSignal
from protocol.strategies import register


def _emit_from_classes(panel, cfg, name, classes, extra=None) -> list[TradeSignal]:
    out: list[TradeSignal] = []
    for symbol, feat in panel.items():
        events = pra.classify_events(feat, cfg, symbol)
        if events.empty:
            continue
        events = events[events["event_class"].isin(classes)]
        if extra is not None:
            events = events[extra(events)]
        d = feat.reset_index(drop=True)
        for _, ev in events.iterrows():
            hits = d.index[d["Date"] == ev["date"]]
            if len(hits) == 0:
                continue
            i = int(hits[0])
            if i + 1 >= len(d):
                continue
            out.append(TradeSignal(name, symbol, ev["date"], d["Date"].iloc[i + 1],
                                   float(d["Close"].iloc[i]), stop_pct=0.07,
                                   meta={"event_class": ev["event_class"],
                                         "retention": round(float(ev["retention"]), 4) if not np.isnan(ev["retention"]) else None}))
    return out


@register("pra_strong_retention")
def pra_strong_retention(panel, cfg) -> list[TradeSignal]:
    min_ret = (cfg.get("strategies", {}).get("pra_strong_retention", {})).get("retention_min", 0.60)
    return _emit_from_classes(panel, cfg, "pra_strong_retention", ["STRONG_RETENTION"],
                              extra=lambda e: e["retention"] >= min_ret)


@register("pra_expansion_attempt")
def pra_expansion_attempt(panel, cfg) -> list[TradeSignal]:
    min_rvol = (cfg.get("strategies", {}).get("pra_expansion_attempt", {})).get("rvol_min", 1.5)
    return _emit_from_classes(panel, cfg, "pra_expansion_attempt", ["EXPANSION_ATTEMPT"],
                              extra=lambda e: e["RVOL20"] >= min_rvol)


@register("pra_high_effort_low_result")
def pra_high_effort_low_result(panel, cfg) -> list[TradeSignal]:
    return _emit_from_classes(panel, cfg, "pra_high_effort_low_result", ["HIGH_EFFORT_LOW_RESULT"])


@register("pra_full")
def pra_full(panel, cfg) -> list[TradeSignal]:
    a = cfg["pra"]["ablation"]
    return _emit_from_classes(panel, cfg, "pra_full", ["STRONG_RETENTION"],
                              extra=lambda e: (e["RVOL20"] >= a["rvol_min"]) &
                              (e["result_atr"] >= a["response_min"]) &
                              (e["retention"] >= a["retention_min"]) &
                              (e["closing_range"] >= a["closing_range_min"]))


def _with_reference(cfg: dict, reference: int) -> dict:
    return {**cfg, "pra": {**cfg["pra"], "reference": reference}}


def _make_reference_variant(name: str, reference: int):
    @register(name)
    def _variant(panel, cfg, _ref=reference, _name=name) -> list[TradeSignal]:
        return _emit_from_classes(panel, _with_reference(cfg, _ref), _name, ["STRONG_RETENTION"])


# gpt6 requires references 5/10/20/60/252 as separately registered variants.
for _ref in (5, 10, 60, 252):
    _make_reference_variant(f"pra_retention_r{_ref}", _ref)
