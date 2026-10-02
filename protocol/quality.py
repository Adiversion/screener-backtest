"""Evidence-weighted stock ranking.

Answers the question the strategy tables cannot: *which stocks are worth
looking at right now?*

Version 1 scored a hand-weighted blend of the Pressure-Response-Acceptance
framework because those were the ideas the protocol proposed.
`scripts/validate.py` then measured their information coefficients against the
5-day forward return on 108,742 breakout events, and the verdict was
`NO_INCREMENTAL_INFORMATION`: retention IC +0.00009 (t +0.02), closing_range
-0.0086 (t -1.72), closing_disp -0.0033 (t -0.65). So the protocol's own
instruction applies: discard the complexity.

What the same test DID find, ranked by |t|: atrpct IC -0.0434 (t -7.35) low
volatility wins; prox52 +0.0344 (t 6.03) near the 52-week high wins; rvol20
-0.0289 (t -5.79) LOW relative volume wins; efficiency +0.0178 (t 3.73);
penetration -0.0174 (t -3.57) shallow beats deep; ret120 +0.0147 with ret20
-0.0128, so slow trend works and a recent burst reverses. Version 2 scores
those and drops the rest. Scores are CROSS-SECTIONAL PERCENTILES, because a
ranking is a rank; and there is NO DOUBLE COUNTING, since `efficiency` is
result/volume and already carries the negative-volume effect.

TWO CAVEATS. These weights were set from information coefficients estimated on
2018-2026, so they are fitted to the sample and describe it rather than predict
beyond it. More seriously, they were measured on 5-day FORWARD RETURNS and do
NOT survive a +15% target / -7% stop strategy: `low_vol`, whose factor has the
strongest IC we measured, LOSES to the random null as a registered strategy
because calm names cannot travel far enough to reach a +15% target.

VERSION 3 (2026-10), found by chasing a false positive. The stop gate was a
CEILING, so the TIGHTER stop always passed, and the component scored tightness
as a virtue. Measured: 84.8% of gate-clearing events carried a stop narrower
than 1x ATR and those had the WORST forward 20-session return (+0.23% against
+1.02% for the 1-2 ATR bucket, 7,953 events). It is now a floor AND a ceiling
in ATR, measured below the recent swing low rather than at the 20-session high,
which ordinary noise reaches. Missing data stays UNKNOWN.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from protocol import states

# field -> (label, sign, what it measures, why it earns its weight)
# sign -1 means a LOWER raw value scores HIGHER.
COMPONENTS: dict[str, tuple[str, int, str, str]] = {
    "atrpct": ("Low volatility", -1, "ATR as a % of price",
               "IC -0.0434, t -7.35 - the strongest measured effect"),
    "prox52": ("Near the 52-week high", 1, "close vs the prior 252-session high",
               "IC +0.0344, t +6.03 - momentum, in its cleanest form"),
    "efficiency": ("Effort per result", 1, "result divided by relative volume",
                   "IC +0.0178, t +3.73 - the surviving piece of the framework"),
    "trend_raw": ("Slow trend, no recent chase", 1,
                  "120d return minus half the last 20d",
                  "ret120 +0.0147 but ret20 -0.0128: slow trend, recent burst reverses"),
    "penetration": ("Not extended", -1, "push past the reference, in ATR",
                    "IC -0.0174, t -3.57 - deep penetration is exhaustion"),
    "turnover20": ("Liquidity", 1, "20-session average rupee turnover",
                   "tradability, not a return signal"),
    "stop_proxy": ("Stop room", 1,
                   "distance from the close back to the structural reference",
                   "MEASURED: stops narrower than 1x ATR were the WORST bucket "
                   "(+0.23% fwd20) against +1.02% for 1-2 ATR, so tightness is "
                   "not a virtue -- a stop inside one day's noise gets taken out"),
}

# Kept separate and small: `recovered_after_rej` is the only registered rule that
# ever beat the random null, but was never independently validated.
EDGE_WEIGHT = 0.05
# a stop goes a little below the swing low, not exactly at it
STOP_BUFFER = 0.25


def _num(x: Any) -> float | None:
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    return None if not np.isfinite(f) else f


def panel_row(bar: pd.Series, cfg: dict) -> dict[str, Any]:
    """Every raw field the ranking needs, read from one symbol's latest bar."""
    r20 = _num(bar.get(f"R{int(cfg['pa']['reference'])}"))
    close = _num(bar.get("Close"))
    ret20 = _num(bar.get("ret20")) or 0.0
    ret120 = _num(bar.get("ret120"))
    atr = _num(bar.get("atr14"))
    low10 = _num(bar.get("low10"))
    # The stop is where it would ACTUALLY be placed: below the recent swing low
    # with a buffer, not at the reference high. Nobody stops out exactly at a
    # 20-day high, because ordinary noise reaches it. Below the reference the
    # distance is not a tighter stop but a level already lost, so UNKNOWN.
    stop = None
    if low10 is not None and atr is not None and close and close > 0 \
            and r20 is not None and close > r20:
        stop = round((close - (low10 - STOP_BUFFER * atr)) / close, 4)
    return {
        "close": close, "reference": r20, "ret120": ret120, "stop_proxy": stop,
        "rvol20": _num(bar.get("rvol20")), "ret20": _num(bar.get("ret20")),
        "atrpct": _num(bar.get("atrpct")), "prox52": _num(bar.get("prox52")),
        "efficiency": _num(bar.get("efficiency")),
        "penetration": _num(bar.get("penetration")),
        "turnover20": _num(bar.get("turnover20")),
        # slow trend with the recent burst explicitly backed off
        "trend_raw": None if ret120 is None else round(ret120 - 0.5 * ret20, 6),
    }


def rank_components(frame: pd.DataFrame) -> pd.DataFrame:
    """Raw values -> cross-sectional percentile scores in [0, 1].

    Rows where the raw value is unknown stay NaN. Unknown is not zero.
    """
    out = pd.DataFrame(index=frame.index)
    for field, (_label, sign, _m, _w) in COMPONENTS.items():
        vals = pd.to_numeric(frame[field], errors="coerce") if field in frame else \
            pd.Series(np.nan, index=frame.index)
        out[field] = (-vals if sign < 0 else vals).rank(pct=True, na_option="keep")
    return out


def coverage(scores: pd.Series) -> tuple[float, str]:
    """Fraction of components computable, and a FULL/THIN/INSUFFICIENT label."""
    total = len(COMPONENTS)
    frac = float(scores.notna().sum()) / total if total else 0.0
    return round(frac, 4), ("FULL" if frac >= 1.0 else "THIN" if frac >= 0.5
                            else "INSUFFICIENT")


def gates(row: pd.Series, cfg: dict) -> list[dict[str, Any]]:
    """Hard filters. A stock failing any of these is not ranked at all.

    Each gate distinguishes passed / failed / UNKNOWN. An unknown input is
    never counted as a pass.
    """
    q = cfg["quality"]
    turnover, close = _num(row.get("turnover20")), _num(row.get("close"))
    r120, ref = _num(row.get("ret120")), _num(row.get("reference"))
    pen, stop = _num(row.get("penetration")), _num(row.get("stop_proxy"))
    atr, cov = _num(row.get("atrpct")), float(row.get("coverage") or 0.0)

    def ok(v, test):  # lazy, so a None input never reaches the comparison
        return v is not None and bool(test(v))

    return [
        {"criterion": "20-day average turnover", "value": turnover,
         "threshold": f">= INR {q['min_turnover20']:,.0f}",
         "passed": ok(turnover, lambda v: v >= q["min_turnover20"]),
         "meaning": "large enough to trade"},
        {"criterion": "Closing price", "value": close,
         "threshold": f">= INR {q['min_price']}",
         "passed": ok(close, lambda v: v >= q["min_price"]),
         "meaning": "not a sub-penny lottery ticket"},
        {"criterion": "120-day return", "value": r120,
         "threshold": f"> {q['trend_min']}",
         "passed": ok(r120, lambda v: v > q["trend_min"]),
         "meaning": "the slow trend is working"},
        {"criterion": "Close above the prior 20-session high", "value": ref,
         "threshold": "Close > R20",
         "passed": (ref is not None and close is not None and close > ref
                    and (pen or 0) > 0),
         "meaning": "at its structural high right now"},
        {"criterion": "Stop width", "value": stop,
         "threshold": f"{q['min_stop_atr']:.1f}x to {q['max_stop_atr']:.1f}x ATR",
         "passed": ok(stop, lambda v: atr is not None and atr > 0
                      and q["min_stop_atr"] * atr <= v <= q["max_stop_atr"] * atr),
         "meaning": "wide enough to survive normal noise, not absurdly wide"},
        {"criterion": "History available", "value": row.get("sessions"),
         "threshold": f">= {q['min_sessions']} sessions",
         "passed": (row.get("sessions") or 0) >= q["min_sessions"],
         "meaning": "enough data to compute the features"},
        {"criterion": "Data coverage", "value": cov,
         "threshold": f"= {q['min_coverage']:.0%} of components computable",
         "passed": cov >= float(q["min_coverage"]),
         "meaning": "every component had the data it needed"},
    ]


def edge_dates(panel: dict[str, pd.DataFrame], cfg: dict) -> dict[str, pd.Timestamp]:
    """Most recent reclaimed-reference event per symbol."""
    out: dict[str, pd.Timestamp] = {}
    for symbol, feat in panel.items():
        try:
            events = states.find_events(feat, cfg)
        except Exception:  # a malformed symbol must not kill the screen
            continue
        stamps = [pd.Timestamp(e["reject_date"]) for e in events
                  if e.get("label") == "RECOVERED_AFTER_REJ" and e.get("reject_date")]
        if stamps:
            out[symbol] = max(stamps)
    return out


def _frames(panel, cfg, asof, lookback_days):
    """One row per symbol with every field the ranking and gates need."""
    edges = edge_dates(panel, cfg)
    rows = []
    for symbol, feat in panel.items():
        d = feat.reset_index(drop=True)
        upto = d[d["Date"] <= pd.Timestamp(asof)]
        if upto.empty:
            continue
        bar = upto.iloc[-1]
        age = ((pd.Timestamp(asof) - edges[symbol]).days
               if symbol in edges else None)
        row = panel_row(bar, cfg)
        row.update({"symbol": symbol, "date": str(pd.Timestamp(bar["Date"]).date()),
                    "sessions": int(len(upto)), "edge_age_days": age})
        row["edge"] = 1.0 if (age is not None and age <= lookback_days) else 0.0
        rows.append(row)
    return pd.DataFrame(rows)


def score_frame(frame: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Attach percentile components, coverage, the blended score and gates."""
    if frame.empty:
        return frame
    w = dict(cfg["quality"]["weights"])
    w["edge"] = EDGE_WEIGHT
    wset = {k: float(w.get(k, 0.0)) for k in COMPONENTS}
    scored = rank_components(frame)
    for field in COMPONENTS:
        frame[field + "_pct"] = scored[field]
    cols = [f + "_pct" for f in COMPONENTS]
    weight_series = pd.Series(wset).reindex(COMPONENTS).rename(
        index=lambda f: f + "_pct")
    contrib = frame[cols].mul(weight_series, axis=1)
    num = contrib.sum(axis=1) + frame["edge"] * EDGE_WEIGHT
    den = contrib.notna().mul(weight_series, axis=1).sum(axis=1) + EDGE_WEIGHT
    frame["score"] = (num / den).round(4)
    cov = [coverage(scored.loc[i]) for i in frame.index]
    frame["coverage"] = [c for c, _ in cov]
    frame["data_status"] = [s for _, s in cov]
    frame["candidates"] = int(len(frame))
    checks = [gates(r, cfg) for _, r in frame.iterrows()]
    frame["gates"] = checks
    frame["failed"] = ["; ".join(c["criterion"] for c in g if not c["passed"])
                       for g in checks]
    return frame


def rank(panel: dict[str, pd.DataFrame], cfg: dict, asof: pd.Timestamp,
         top: int = 10, lookback_days: int = 20) -> pd.DataFrame:
    """Rank every symbol cross-sectionally and return the best that clear
    every hard gate."""
    frame = score_frame(_frames(panel, cfg, asof, lookback_days), cfg)
    if frame.empty:
        return frame
    out = frame[frame["failed"] == ""].sort_values("score", ascending=False)
    out = out.head(max(int(top), 1)).copy()
    if not out.empty:
        out.insert(0, "rank", range(1, len(out) + 1))
    return out


def data_sufficiency_report(panel: dict[str, pd.DataFrame], cfg: dict,
                            asof: pd.Timestamp) -> dict[str, Any]:
    """Who is excluded for LACK OF DATA rather than for being bad.

    Excluded for lack of data is NOT the same as rejected on merit. Recent
    IPOs are the population this matters for; in a 2300-name universe they are
    a real slice of the market.
    """
    q = cfg["quality"]
    min_cov, thin_cov = float(q["min_coverage"]), float(q["thin_coverage"])
    note = ("Excluded for lack of data is NOT the same as rejected on merit. "
            "These names are unknown to the ranking, not judged bad by it.")
    frame = _frames(panel, cfg, asof, 20)
    if frame.empty:
        return {"full": 0, "thin": 0, "insufficient": 0, "thin_symbols": [],
                "insufficient_symbols": [], "note": "no panel data"}
    scored = rank_components(frame)
    cov = pd.Series({i: coverage(scored.loc[i])[0] for i in frame.index})
    buckets: dict[str, list] = {"FULL": [], "THIN": [], "INSUFFICIENT": []}
    for sym, frac in zip(frame["symbol"], cov.to_numpy()):
        buckets["FULL" if frac >= min_cov
                else "THIN" if frac >= thin_cov else "INSUFFICIENT"].append(sym)
    return {"min_coverage": min_cov, "thin_coverage": thin_cov,
            "full": len(buckets["FULL"]), "thin": len(buckets["THIN"]),
            "insufficient": len(buckets["INSUFFICIENT"]),
            "thin_symbols": sorted(buckets["THIN"]),
            "insufficient_symbols": sorted(buckets["INSUFFICIENT"]), "note": note}


def reason(row: pd.Series, cfg: dict) -> str:
    """One sentence: what this stock is, and why it scored where it did."""
    parts = [(f, row.get(f + "_pct")) for f in COMPONENTS]
    parts = [(f, v) for f, v in parts if v is not None and pd.notna(v)]
    parts.sort(key=lambda kv: -float(kv[1]))
    top = ", ".join(f"{COMPONENTS[f][0].lower()} {float(v):.0%}" for f, v in parts[:3])
    return (f"{row['symbol']} scored {row['score']:.2f}/1.00 against "
            f"{int(row.get('candidates') or 0)} candidates today "
            f"(strongest: {top}). Close INR {row['close']}, 52w-high "
            f"{row['prox52']}, ATR% {row['atrpct']}, RVOL20 {row['rvol20']}, "
            f"120d {row['ret120']}, turnover INR "
            f"{round(float(row['turnover20'] or 0)):,}. Coverage "
            f"{float(row.get('coverage') or 0):.0%} ({row.get('data_status')}).")