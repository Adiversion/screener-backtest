"""Strategies built from the measured information coefficients.

WHY THIS FILE EXISTS
--------------------
`scripts/validate.py` measured the cross-sectional information coefficient of
every candidate feature against the 5-day forward return on 108,742 breakout
events. The ranked result was:

    atrpct       IC -0.0434   t -7.35   low volatility wins
    prox52       IC +0.0344   t +6.03   near the 52-week high wins
    rvol20       IC -0.0289   t -5.79   LOW relative volume wins (exhaustion)
    efficiency   IC +0.0178   t +3.73   effort per unit participation wins
    penetration  IC -0.0174   t -3.57   shallow beats deep
    ret120       IC +0.0147   t +2.58   slow trend works
    ret20        IC -0.0128   t -2.49   recent winners REVERSE
    retention    IC +0.00009  t +0.02   nothing at all

That knowledge lived only in the ranking and the validation report. Not one of
these factors existed as a registered strategy, so none of them had ever been
backtested as an actual trade with costs, a target and a stop. The engine was
holding a conclusion it had not tested operationally. This file closes that gap.

It also encodes the negative findings, which is rarer and more useful:

`avoid_exhaustion` deliberately buys the WORST names on the two factors with the
strongest negative IC. It is the control that tells you whether those factors
carry tradable information or merely correlate with something else. If
avoid_exhaustion loses to `random`, the exhaustion signal is real and
actionable. If it does not, the ICs were an artefact.

THE POST-REJECTION FAMILY
-------------------------
`recovered_after_rej` (B9) is the only registered rule that ever beat the
seeded random null (+0.0125 vs -0.0177, CI 0.0074 to 0.0177). The research
notes argue that the information lives in the *response after* the event rather
than in the event itself, and propose two refinements:

    Recovery  = (C - L) / (R - L)     where R is the reference, L the
                                       post-rejection low, C the recovery close
    time-to-resolution                 sessions between rejection and reclaim

Both are registered here as separate variants so they are measured, not
assumed. An ad-hoc bucket test suggested the effect is real but NON-MONOTONIC:
returns peak when the reclaim is just completed (recovery 0.9-1.0) and get
WORSE when the reclaim overshoots (recovery > 1.0). `recovery_just_clamps` and
`recovery_overshoots` exist to test exactly that.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from protocol.signals import TradeSignal
from protocol.strategies import register
from protocol.strategies_rank import _weekly_topn


def _p(cfg: dict, name: str, key: str, default):
    return float(cfg.get("strategies", {}).get(name, {}).get(key, default))


@register("low_vol")
def low_vol(panel, cfg) -> list[TradeSignal]:
    """Buy the calmest names. Strongest measured factor (t -7.35).

    `nlargest` on `atrpct` would be wrong: LOW volatility is the signal, so the
    score is negated.
    """
    n = int(_p(cfg, "low_vol", "n", 20))
    return _weekly_topn(panel, "calm", n, "low_vol",
                        extra_filter=lambda d: d["prox52"] > 0.60)


@register("low_vol_near_high")
def low_vol_near_high(panel, cfg) -> list[TradeSignal]:
    """Low volatility AND at a 52-week high -- the two strongest factors.

    Combined rather than averaged: a calm stock far below its high is a value
    trap by this evidence, and a stock at its high that is wild is unholdable.
    """
    n = int(_p(cfg, "low_vol_near_high", "n", 20))
    return _weekly_topn(panel, "calm_near_high", n, "low_vol_near_high",
                        extra_filter=lambda d: d["ret120"] > 0)


@register("effort_result")
def effort_result(panel, cfg) -> list[TradeSignal]:
    """High effort per unit participation -- the surviving framework piece."""
    n = int(_p(cfg, "effort_result", "n", 20))
    return _weekly_topn(panel, "efficiency", n, "effort_result",
                        extra_filter=lambda d: d["penetration"] > 0)


@register("avoid_exhaustion")
def avoid_exhaustion(panel, cfg) -> list[TradeSignal]:
    """DELIBERATELY BUY THE WORST NAMES on the strongest negative factors.

    High relative volume (t -5.79) and deep penetration (t -3.57) predict worse
    returns. This strategy buys them on purpose. If the factors are real it
    should lose to `random`; if it does not, the negative ICs were an artefact
    of something else and the ranking's low-volatility weight is unjustified.

    A negative control that loses is the strongest possible confirmation.
    """
    n = int(_p(cfg, "avoid_exhaustion", "n", 20))
    return _weekly_topn(panel, "exhausted", n, "avoid_exhaustion",
                        extra_filter=lambda d: d["turnover20"] > 5e7)


@register("recent_reversal")
def recent_reversal(panel, cfg) -> list[TradeSignal]:
    """Buy what has recently fallen. ret20 IC -0.0128 (t -2.49).

    Small and probably cost-dominated, but it is the one short-horizon effect
    we measured, and short-horizon is where the target/stop actually engages.
    """
    n = int(_p(cfg, "recent_reversal", "n", 20))
    return _weekly_topn(panel, "reversal", n, "recent_reversal",
                        extra_filter=lambda d: d["ret120"] > 0)


# --- post-rejection family -------------------------------------------------
def _rejection_frames(panel, cfg, lookahead: int):
    """One row per rejection event: the recovery close and the low since."""
    lo = int(_p(cfg, "recovery", "min_penetration_atr", 0.0))
    out: list[dict] = []
    for symbol, feat in panel.items():
        d = feat.reset_index(drop=True)
        if len(d) < 40:
            continue
        r20 = d["R20"].to_numpy(float)
        high = d["High"].to_numpy(float)
        low = d["Low"].to_numpy(float)
        close = d["Close"].to_numpy(float)
        atr = d["atr14"].to_numpy(float)
        dates = d["Date"].to_numpy()
        pos = {ts: i for i, ts in enumerate(d["Date"])}
        for i in range(25, len(d) - lookahead - 1):
            r, a = r20[i], atr[i]
            if not (np.isfinite(r) and np.isfinite(a) and a > 0):
                continue
            pen = (high[i] - r) / a
            if not (np.isfinite(pen) and pen > lo):
                continue
            if close[i] >= r:
                continue                       # closed above: not a rejection
            j = i + lookahead
            low_since = np.min(low[i + 1:j + 1])
            if not np.isfinite(low_since) or r <= low_since:
                continue
            rec = (close[j] - low_since) / (r - low_since)
            out.append({"date": pd.Timestamp(dates[j]), "symbol": symbol,
                        "recovery": float(rec), "entry_date": dates[j + 1],
                        "entry_px": float(close[j]),
                        "reclaimed": bool(close[j] > r)})
    return pd.DataFrame(out)


def _recovery_signals(panel, cfg, lo: float, hi: float, name: str,
                      require_reclaim: bool) -> list[TradeSignal]:
    look = int(_p(cfg, "recovery", "lookahead", 3))
    frame = _rejection_frames(panel, cfg, look)
    if frame.empty:
        return []
    frame = frame[(frame["recovery"] >= lo) & (frame["recovery"] <= hi)]
    if require_reclaim:
        frame = frame[frame["reclaimed"]]
    if frame.empty:
        return []
    cache: dict[str, tuple[dict, pd.DataFrame]] = {}
    out: list[TradeSignal] = []
    for _, r in frame.iterrows():
        symbol = r["symbol"]
        hit = cache.get(symbol)
        if hit is None:
            d = panel[symbol].reset_index(drop=True)
            hit = ({ts: i for i, ts in enumerate(d["Date"])}, d)
            cache[symbol] = hit
        pos, d = hit
        i = pos.get(pd.Timestamp(r["date"]))
        if i is None or i + 1 >= len(d):
            continue
        out.append(TradeSignal(name, symbol, r["date"], d["Date"].iloc[i + 1],
                               float(d["Close"].iloc[i]), stop_pct=0.07,
                               meta={"recovery": round(float(r["recovery"]), 4),
                                     "reclaimed": bool(r["reclaimed"])}))
    return out


@register("recovery_partial")
def recovery_partial(panel, cfg) -> list[TradeSignal]:
    """Rejection, then a partial bounce that stops short of the reference."""
    lo = _p(cfg, "recovery_partial", "lo", 0.40)
    hi = _p(cfg, "recovery_partial", "hi", 0.90)
    return _recovery_signals(panel, cfg, lo, hi, "recovery_partial", False)


@register("recovery_just_clamps")
def recovery_just_clamps(panel, cfg) -> list[TradeSignal]:
    """Rejection, then the reference reclaimed without a big overshoot."""
    lo = _p(cfg, "recovery_just_clamps", "lo", 0.90)
    hi = _p(cfg, "recovery_just_clamps", "hi", 1.10)
    return _recovery_signals(panel, cfg, lo, hi, "recovery_just_clamps", True)


@register("recovery_overshoots")
def recovery_overshoots(panel, cfg) -> list[TradeSignal]:
    """Rejection, then a decisive reclaim well past the reference.

    The bucket test suggested this is WORSE than a clean reclaim. Registered
    so that prediction is actually falsifiable rather than just a remark.
    """
    lo = _p(cfg, "recovery_overshoots", "lo", 1.10)
    return _recovery_signals(panel, cfg, lo, 99.0, "recovery_overshoots", True)


@register("recovery_time_to_resolve")
def recovery_time_to_resolve(panel, cfg) -> list[TradeSignal]:
    """The research notes' time-to-resolution idea, as a fast-reclaim rule."""
    look = int(_p(cfg, "recovery_time_to_resolve", "lookahead", 2))
    frame = _rejection_frames(panel, cfg, look)
    if frame.empty:
        return []
    frame = frame[frame["reclaimed"]]
    if frame.empty:
        return []
    cache: dict[str, tuple[dict, pd.DataFrame]] = {}
    out: list[TradeSignal] = []
    for _, r in frame.iterrows():
        symbol = r["symbol"]
        hit = cache.get(symbol)
        if hit is None:
            d = panel[symbol].reset_index(drop=True)
            hit = ({ts: i for i, ts in enumerate(d["Date"])}, d)
            cache[symbol] = hit
        pos, d = hit
        i = pos.get(pd.Timestamp(r["date"]))
        if i is None or i + 1 >= len(d):
            continue
        out.append(TradeSignal("recovery_time_to_resolve", symbol, r["date"],
                               d["Date"].iloc[i + 1], float(d["Close"].iloc[i]),
                               stop_pct=0.07, meta={"lookahead": look}))
    return out