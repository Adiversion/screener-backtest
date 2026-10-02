"""Blended stock-quality ranking.

Answers the question the strategy tables cannot: *which good stocks could I
invest in right now?* Every symbol is scored on six point-in-time components
and the ones that clear every hard gate are ranked.

Nothing here is fitted to outcomes. The weights live in `config/protocol_v2.yaml`
under `quality:` and are a frozen judgement — changing them is a new experiment,
not a tweak. Every component reads data through the decision bar only, so the
ranking is reproducible and passes the no-lookahead audit like everything else.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from protocol import states

# name -> (label, what it measures, why it matters)
COMPONENTS = {
    "acceptance": ("Price acceptance",
                   "Retention into the close and closing range vs the prior 20-day high",
                   "buyers defended the new territory instead of selling into it"),
    "trend": ("Trend", "60-day and 120-day return",
             "quality names are already going up, not being fished out of a decline"),
    "liquidity": ("Liquidity", "20-day average rupee turnover",
                  "you must be able to get in and out at your size"),
    "volume_sanity": ("Volume sanity", "Relative volume vs its 20-session mean",
                      "interest, but not the climactic spike that marks exhaustion"),
    "risk": ("Risk to reference", "Distance from close back to the structural reference",
             "a normal stop, not an absurdly wide one"),
    "edge": ("Evidence edge", "The reclaimed-reference pattern fired recently",
             "the only rule in this engine that beat the random null"),
}


def _clip01(x: float | None) -> float:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return 0.0
    return float(min(max(x, 0.0), 1.0))


def _num(x: Any) -> float | None:
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    return None if np.isnan(f) else f


def components(row: pd.Series, cfg: dict, edge_days: float | None) -> dict[str, Any]:
    """Score each component, or None where the data cannot support it.

    A component that cannot be computed returns **None**, not 0.0. That
    distinction is the whole point: a stock with no 120-day history is
    UNKNOWN on trend, which is a different statement from a stock whose trend
    is genuinely flat. Coercing missing data to zero would let an
    insufficient-history name score as "bad but sellable" and rank among
    genuinely-assessed names -- precisely the confusion this avoids.

    `edge` is the one component where 0.0 is a real value: not firing within
    the lookback window is a fact about the stock, not missing data.
    """
    q = cfg["quality"]
    ret = _num(row.get("retention"))
    cr = _num(row.get("closing_range"))
    rvol = _num(row.get("rvol20"))
    turnover = _num(row.get("turnover20"))
    stop = _num(row.get("stop_proxy"))
    r60 = _num(row.get("ret60"))
    r120 = _num(row.get("ret120"))
    scale = float(q["trend_min"]) + 0.30  # 0.30 = "full marks" for a 30% move

    acceptance = (None if ret is None or cr is None else
                  0.5 * _clip01(ret / cfg["pa"]["accepted_retention"]) +
                  0.5 * _clip01(cr / cfg["pa"]["accepted_closing_range"]))
    trend = (None if r60 is None or r120 is None else
             0.5 * _clip01(r60 / scale) + 0.5 * _clip01(r120 / scale))
    liquidity = (None if turnover is None else
                 _clip01(np.log10(max(turnover / q["min_turnover20"], 1e-9))))
    if rvol is None:
        volume_sanity = None
    else:  # a tent: fades when too quiet or too frantic
        volume_sanity = _clip01(rvol / q["rvol_min"]) * _clip01(q["rvol_max"] / rvol)
    risk = _clip01(1.0 - (stop / q["max_risk_to_ref"])) if stop is not None else None
    edge = 1.0 if edge_days is not None else 0.0
    return {"acceptance": acceptance, "trend": trend, "liquidity": liquidity,
            "volume_sanity": volume_sanity, "risk": risk, "edge": edge}


def coverage(comps: dict[str, Any]) -> tuple[float, str]:
    """Fraction of the components that are computable, and a status label."""
    q_vals = [v for k, v in comps.items() if k != "edge"]
    known = [v for v in q_vals if v is not None]
    frac = len(known) / len(q_vals) if q_vals else 0.0
    return round(frac, 4), ("FULL" if frac >= 1.0 else
                            "THIN" if frac >= 0.5 else "INSUFFICIENT")


def gates(row: pd.Series, cfg: dict, age_days: float | None) -> list[dict[str, Any]]:
    """Hard filters. A stock failing any of these is not ranked at all.

    Every gate distinguishes three states: passed, failed, and UNKNOWN
    (the input was not computable). An unknown is never counted as a pass.
    """
    q = cfg["quality"]
    turnover, close = _num(row.get("turnover20")), _num(row.get("close"))
    r60, r120 = _num(row.get("ret60")), _num(row.get("ret120"))
    ref, pen = _num(row.get("reference")), _num(row.get("penetration"))
    stop = _num(row.get("stop_proxy"))
    out = [
        {"criterion": "20-day average turnover", "value": turnover,
         "threshold": f">= INR {q['min_turnover20']:,.0f}",
         "passed": turnover is not None and turnover >= q["min_turnover20"],
         "meaning": "large enough to trade"},
        {"criterion": "Closing price", "value": close,
         "threshold": f">= INR {q['min_price']}",
         "passed": close is not None and close >= q["min_price"],
         "meaning": "not a sub-penny lottery ticket"},
        {"criterion": "60-day return", "value": r60, "threshold": f"> {q['trend_min']}",
         "passed": r60 is not None and r60 > q["trend_min"],
         "meaning": "the stock is already working"},
        {"criterion": "120-day return", "value": r120, "threshold": f"> {q['trend_min']}",
         "passed": r120 is not None and r120 > q["trend_min"],
         "meaning": "not just a one-week bounce"},
        {"criterion": "Price above the prior 20-session high", "value": ref,
         "threshold": "Close > R20", "passed": ref is not None and close is not None
         and close > ref and (pen or 0) > 0,
         "meaning": "it is at its structural high right now"},
        {"criterion": "Risk to reference", "value": stop,
         "threshold": f"<= {q['max_risk_to_ref']}",
         "passed": stop is not None and stop <= q["max_risk_to_ref"],
         "meaning": "a normal stop distance"},
        {"criterion": "History available", "value": row.get("sessions"),
         "threshold": f">= {q['min_sessions']} sessions",
         "passed": (row.get("sessions") or 0) >= q["min_sessions"],
         "meaning": "enough data to compute the features"},
    ]
    # A stock can clear min_sessions and still have an uncomputable component
    # (a NaN bar, a missing reference). Those are excluded explicitly rather
    # than silently scored as zero.
    cov = float(row.get("coverage") or 0.0)
    out.append({
        "criterion": "Data coverage", "value": cov,
        "threshold": f"= {q['min_coverage']:.0%} of components computable",
        "passed": cov >= float(q["min_coverage"]),
        "meaning": "every score component had the data it needed",
    })
    return out


def edge_dates(panel: dict[str, pd.DataFrame], cfg: dict) -> dict[str, pd.Timestamp]:
    """Most recent reclaimed-reference event per symbol (the only rule with edge)."""
    out: dict[str, pd.Timestamp] = {}
    for symbol, feat in panel.items():
        try:
            events = states.find_events(feat, cfg)
        except Exception:  # a malformed symbol must not kill the screen
            continue
        stamps = [pd.Timestamp(e["reject_date"]) for e in events
                  if e.get("label") == "RECOVERED_AFTER_REJ" and e.get("reject_date") is not None]
        if stamps:
            out[symbol] = max(stamps)
    return out


def rank(panel: dict[str, pd.DataFrame], cfg: dict, asof: pd.Timestamp,
         top: int = 10, lookback_days: int = 20) -> pd.DataFrame:
    """Score every symbol and return the best that clear all hard gates."""
    q = cfg["quality"]
    ref = f"R{int(cfg['pa']['reference'])}"
    edges = edge_dates(panel, cfg)
    rows: list[dict[str, Any]] = []
    for symbol, feat in panel.items():
        d = feat.reset_index(drop=True)
        upto = d[d["Date"] <= pd.Timestamp(asof)]
        if upto.empty:
            continue
        i = len(upto) - 1
        bar = upto.iloc[i]
        row = {
            "symbol": symbol, "date": str(pd.Timestamp(bar["Date"]).date()),
            "close": _num(bar["Close"]), "reference": _num(bar.get(ref)),
            "rvol20": _num(bar["rvol20"]), "closing_range": _num(bar["closing_range"]),
            "retention": _num(bar["retention"]), "penetration": _num(bar["penetration"]),
            "ret60": _num(bar["ret60"]), "ret120": _num(bar["ret120"]),
            "turnover20": _num(bar["turnover20"]),
            "stop_proxy": round((float(bar["Close"]) - float(bar[ref])) / float(bar["Close"]), 4)
            if bar.get(ref) == bar.get(ref) and float(bar["Close"]) else None,
            "sessions": int(len(upto)),
        }
        edge_days = None
        if symbol in edges:
            edge_days = (pd.Timestamp(asof) - edges[symbol]).days
        comps = components(row, cfg, edge_days)
        row.update(comps)
        row["edge"] = 1.0 if (edge_days is not None and edge_days <= lookback_days) else 0.0
        row["edge_age_days"] = edge_days
        cov, status = coverage(comps)
        row["coverage"] = cov
        row["data_status"] = status
        checks = gates(row, cfg, edge_days)
        row["failed"] = "; ".join(c["criterion"] for c in checks if not c["passed"])
        row["gates"] = checks
        # Score only over the components that could actually be computed, and
        # renormalise the weights so a THIN name is not punished twice.
        live_w = sum(float(q["weights"][k]) for k in COMPONENTS
                     if comps.get(k) is not None or k == "edge")
        row["score"] = (round(sum(float(q["weights"][k]) * float(row[k])
                                 for k in COMPONENTS
                                 if row.get(k) is not None) / live_w, 4)
                        if live_w > 0 else None)
        rows.append(row)
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    ranked = frame[frame["failed"] == ""].sort_values("score", ascending=False)
    ranked = ranked.head(max(int(top), 1)).copy()
    if not ranked.empty:
        ranked.insert(0, "rank", range(1, len(ranked) + 1))
    return ranked


def data_sufficiency_report(panel: dict[str, pd.DataFrame], cfg: dict,
                            asof: pd.Timestamp) -> dict[str, Any]:
    """Who is being excluded for LACK OF DATA rather than for being bad.

    The fallback ladder, stated rather than hidden:

      FULL        every component computable -> ranked normally
      THIN        some components computable -> ranked with renormalised
                  weights AND flagged, never mixed in silently
      INSUFFICIENT too little history -> not ranked, and listed here so the
                  gap is visible instead of looking like rejection on merit

    Recent IPOs are the population this matters for; in a 2300-name universe
    they are a real slice of the market.
    """
    min_cov = float(cfg["quality"]["min_coverage"])
    thin_cov = float(cfg["quality"]["thin_coverage"])
    buckets: dict[str, list[str]] = {"FULL": [], "THIN": [], "INSUFFICIENT": []}
    for symbol, feat in panel.items():
        d = feat.reset_index(drop=True)
        upto = d[d["Date"] <= pd.Timestamp(asof)]
        if upto.empty:
            buckets["INSUFFICIENT"].append(symbol)
            continue
        bar = upto.iloc[-1]
        row = {"retention": _num(bar.get("retention")),
               "closing_range": _num(bar.get("closing_range")),
               "rvol20": _num(bar.get("rvol20")),
               "turnover20": _num(bar.get("turnover20")),
               "ret60": _num(bar.get("ret60")), "ret120": _num(bar.get("ret120")),
               "stop_proxy": None if bar.get("R20") in (None, 0) else
               round((float(bar["Close"]) - float(bar["R20"])) / float(bar["Close"]), 4)}
        frac, _status = coverage(components(row, cfg, None))
        if frac >= min_cov:
            buckets["FULL"].append(symbol)
        elif frac >= thin_cov:
            buckets["THIN"].append(symbol)
        else:
            buckets["INSUFFICIENT"].append(symbol)
    return {
        "min_coverage": min_cov, "thin_coverage": thin_cov,
        "full": len(buckets["FULL"]), "thin": len(buckets["THIN"]),
        "insufficient": len(buckets["INSUFFICIENT"]),
        "thin_symbols": sorted(buckets["THIN"]),
        "insufficient_symbols": sorted(buckets["INSUFFICIENT"]),
        "note": "Excluded for lack of data is NOT the same as rejected on merit. "
                "These names are unknown to the ranking, not judged bad by it.",
    }


def reason(row: pd.Series, cfg: dict) -> str:
    """One sentence: what this stock is, and why it scored where it did."""
    strong = sorted(((k, row[k]) for k in COMPONENTS if k in row and row[k] is not None),
                    key=lambda kv: kv[1], reverse=True)
    top = ", ".join(f"{COMPONENTS[k][0].lower()} {v:.2f}" for k, v in strong[:3])
    return (f"{row['symbol']} scored {row['score']:.2f}/1.00 "
            f"(strongest: {top}). Close INR {row['close']}, reference INR "
            f"{row['reference']}, RVOL20 {row['rvol20']}, 60d {row['ret60']}, "
            f"120d {row['ret120']}, turnover INR {round(float(row['turnover20'] or 0)):,}. "
            f"Data coverage {float(row.get('coverage') or 0):.0%} ({row.get('data_status')}).")