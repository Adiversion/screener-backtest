#!/usr/bin/env python3
"""Do these price-action ideas carry any signal? Measure before building.

    python scripts/pa_signals.py

The engine already runs on price action: a 20-session reference high, a
10-session swing low, ATR and relative volume. What it does NOT have is a level
that outlives a year. Its longest memory is R252, a rolling 252-session high, so
a swing high from two years ago has been scrolled out of the frame and the
engine cannot see it coming back.

That is a specific, testable claim, so it gets tested here rather than argued
for. Three candidate ideas, each measured on the 499-name panel with eight
years of history, which is long enough to have levels that actually age:

    durable     distance from the close to the highest high of the 250-750
                sessions BEFORE it -- a ceiling roughly one to three years old.
    contraction ATR(5) over ATR(40). Minervini's VCP is progressive volatility
                contraction into a breakout; this is the numeric shadow of it.
    sweep       a low under the prior 20-session low that closes back above it.
                Wyckoff's spring and ICT's liquidity sweep describe this same
                candle, and the engine already has it as recovered_after_rej, so
                this measures what is already there.

Deliberately NOT implemented. This script only measures. Anything that looks
good still has to survive a holdout before it is allowed near the gates.

Every figure is a per-session Spearman correlation, not a pooled one. Pooling
rows across dates mixes a stock's level with that week's market regime and
manufactures correlation out of nothing.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from protocol.data import load_history  # noqa: E402

HORIZON = 20
CACHE = ROOT / "reports" / "pa_signals.parquet"
GAP_START, GAP_END = 250, 750      # sessions before "now" that define a stale level


def build() -> pd.DataFrame:
    if CACHE.exists():
        return pd.read_parquet(CACHE)
    px = load_history(str(ROOT / "data" / "universe_history.parquet"))
    px = px.sort_values(["Symbol", "Date"]).reset_index(drop=True)
    g = px.groupby("Symbol", sort=False)
    close = px["Close"]
    high, low = px["High"], px["Low"]
    tr = (high - low).groupby(px["Symbol"], sort=False)

    d = pd.DataFrame({"date": px["Date"], "symbol": px["Symbol"], "close": close})
    d["fwd"] = g["Close"].shift(-HORIZON) / close - 1.0
    d["atr5"] = tr.transform(lambda s: s.rolling(14, min_periods=14).mean())
    d["atr40"] = tr.transform(lambda s: s.rolling(40, min_periods=40).mean())
    d["contraction"] = d["atr5"] / d["atr40"]

    # A level that is old enough to have been forgotten and young enough to
    # still matter: the highest high between 250 and 750 sessions ago. The
    # engine's own R252 cannot see this, which is the whole point of testing it.
    old_hi = high.groupby(px["Symbol"], sort=False).shift(GAP_START)
    old_lo = low.groupby(px["Symbol"], sort=False).shift(GAP_START)
    d["durable_high"] = old_hi.groupby(px["Symbol"], sort=False).transform(
        lambda s: s.rolling(GAP_END - GAP_START, min_periods=60).max())
    d["durable_low"] = old_lo.groupby(px["Symbol"], sort=False).transform(
        lambda s: s.rolling(GAP_END - GAP_START, min_periods=60).min())
    d["durable_gap"] = d["close"] / d["durable_high"] - 1.0

    pl = low.groupby(px["Symbol"], sort=False).shift(1)
    prior_low = pl.groupby(px["Symbol"], sort=False).transform(
        lambda s: s.rolling(20, min_periods=20).min())
    prior_high = high.groupby(px["Symbol"], sort=False).shift(1).groupby(
        px["Symbol"], sort=False).transform(lambda s: s.rolling(20, min_periods=20).max())
    recent_low = low.groupby(px["Symbol"], sort=False).transform(
        lambda s: s.rolling(3, min_periods=1).min())
    recent_high = high.groupby(px["Symbol"], sort=False).transform(
        lambda s: s.rolling(3, min_periods=1).max())
    d["sweep"] = ((recent_low < prior_low) & (close > prior_low)).astype(int)
    d["rejected"] = ((recent_high >= d["durable_high"]) & (close < d["durable_high"])).astype(int)
    r252 = high.groupby(px["Symbol"], sort=False).shift(1).groupby(
        px["Symbol"], sort=False).transform(lambda s: s.rolling(252, min_periods=252).max())
    d["r252"] = r252
    d["prox252"] = close / r252 - 1.0
    c120 = close.groupby(px["Symbol"], sort=False).shift(120)
    d["ret120"] = close / c120 - 1.0

    d.to_parquet(CACHE, index=False)
    return d


def per_session_ic(d: pd.DataFrame, col: str) -> tuple[float, float, int]:
    vals = []
    for _, s in d.dropna(subset=[col, "fwd"]).groupby("date"):
        if len(s) < 30 or s[col].nunique() < 3:
            continue
        r = s[col].rank().corr(s["fwd"].rank())
        if not np.isnan(r):
            vals.append(r)
    v = pd.Series(vals)
    if len(v) < 3 or v.std() == 0:
        return float("nan"), float("nan"), len(v)
    return float(v.mean()), float(v.mean() / (v.std() / np.sqrt(len(v)))), len(v)


def subset(d: pd.DataFrame, mask: pd.Series, label: str) -> None:
    """Mean forward return on the days a trigger fires, vs the same days' universe."""
    hit = d[mask].dropna(subset=["fwd"])
    if len(hit) < 30:
        print(f"  {label:<34} {len(hit):>6} events  -- too few to say anything")
        return
    day = hit.groupby("date")["fwd"].mean()
    base = d[d["date"].isin(day.index)].groupby("date")["fwd"].mean()
    diff = day - base
    t = (diff.mean() / (diff.std() / np.sqrt(len(diff)))) if diff.std() else float("nan")
    print(f"  {label:<34} {len(hit):>6} events   mean {hit['fwd'].mean():+.2%}"
          f"   vs same-day universe {diff.mean():+.2%}   t {t:+.2f}")


def main() -> int:
    d = build()
    d = d.dropna(subset=["fwd", "close"])
    print(f"{HORIZON}-session forward return | {d['symbol'].nunique()} names | "
          f"{d['date'].nunique()} sessions | {d['date'].min().date()} to "
          f"{d['date'].max().date()}\n")

    print("does an old level still matter? (correlation with forward return)")
    for col, desc in (("durable_gap", "distance to a 1-3yr-old high"),
                      ("prox252", "distance to the rolling 252d high"),
                      ("contraction", "ATR(5)/ATR(40)"),
                      ("ret120", "120-session return")):
        ic, t, n = per_session_ic(d, col)
        print(f"  {desc:<34} IC {ic:+.4f}   t {t:+6.2f}   over {n} sessions")

    print("\ntrigger events, against the same day's whole universe:")
    near = (d["durable_gap"] > -0.03) & (d["durable_gap"] < 0)
    near252 = (d["prox252"] > -0.03) & (d["prox252"] < 0)
    trend = d["ret120"] > 0
    tight = d["contraction"] < 0.8
    subset(d, trend, "rising 120d (the engine's base case)")
    subset(d, near252, "within 3% of the ROLLING 252d high")
    subset(d, near, "within 3% of a 1-3yr OLD high")
    subset(d, d["rejected"] == 1, "closed back under an old high (rejection)")
    subset(d, tight, "volatility contracted to 0.8x")
    subset(d, trend & tight, "rising 120d AND contracted")
    subset(d, d["sweep"] == 1, "swept the 20d low and closed back up")
    subset(d, trend & (d["sweep"] == 1), "rising 120d AND swept the low")

    print("\nA t under 2 is not evidence. Counts under ~1,000 events on a 499-name")
    print("panel are too thin to survive being added as a gate.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
