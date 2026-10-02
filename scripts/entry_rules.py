#!/usr/bin/env python3
"""Entry and exit variants, judged over many decision bars instead of one.

    python scripts/entry_rules.py

A single date cannot tell you whether a rule works. On 1 Sep 2026 the flat 7%
stop and the engine's own structural stop disagreed completely, and the flat one
happened to look better. That is one draw. This runs the same comparison across
every post-warm-up session so the disagreement can be settled.

Five variants, all starting from the same top-ranked gate-clearing name:

    base     enter the next session's open, hold 20. The current behaviour.
    stop7    base plus a flat 7% daily stop.
    struct   base plus the engine's own stop, below the 10-session swing low
             less a quarter ATR, which is wide for a volatile name.
    confirm  wait for a close above the PRIOR day's high, then buy. A breakout
             that has not yet cleared its own one-day range may not be one.
    retest   wait for a session that dips INTO the swing low and closes back
             above it, then buy. Buying the retest rather than the high.

Entry is always the open AFTER the signal session, never the signal's own
close, or the rule would be assuming it knew the close before it printed.

Variants that never fire within their patience window are counted as NO TRADE
and reported as such. Dropping them would quietly turn a 40% fill rate into a
selective-looking 100% one.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from protocol.data import load_history  # noqa: E402

CACHE = ROOT / "reports" / "scored_panel.parquet"
HOLD = 20
CONFIRM_PATIENCE = 10
RETEST_PATIENCE = 15


def t_stat(diffs: np.ndarray) -> float:
    d = pd.Series(diffs).dropna()
    if len(d) < 3 or d.std() == 0:
        return float("nan")
    return float(d.mean() / (d.std() / np.sqrt(len(d))))


def build_bars(px: pd.DataFrame) -> dict[str, dict]:
    """Per-symbol numpy arrays. Rolling once beats a groupby per decision bar."""
    out = {}
    for sym, g in px.sort_values("Date").groupby("Symbol"):
        o, h, l, c = (g["Open"].to_numpy(float), g["High"].to_numpy(float),
                      g["Low"].to_numpy(float), g["Close"].to_numpy(float))
        out[sym] = {"date": g["Date"].to_numpy(), "open": o, "high": h,
                    "low": l, "close": c,
                    "low10": pd.Series(l).rolling(10, min_periods=10).min().to_numpy()}
    return out


def fwd(b: dict, i: int, n: int = HOLD) -> float:
    j = i + n
    return b["close"][j] / b["open"][i] - 1.0 if j < len(b["close"]) else np.nan


def find_confirm(b: dict, i: int) -> int | None:
    """First session after i closing above the PRIOR session's high."""
    for k in range(i + 1, min(i + 1 + CONFIRM_PATIENCE, len(b["close"]) - 1)):
        if b["close"][k] > b["high"][k - 1]:
            return k + 1
    return None


def find_retest(b: dict, i: int, level: float) -> int | None:
    """First session after i that dips into the swing low and closes above it."""
    for k in range(i + 1, min(i + 1 + RETEST_PATIENCE, len(b["close"]) - 1)):
        if b["low"][k] <= level and b["close"][k] > level:
            return k + 1
    return None


def main() -> int:
    s = pd.read_parquet(CACHE)
    s["date"] = pd.to_datetime(s["date"])
    px = load_history(str(ROOT / "data" / "nse_all_history.parquet"))
    px["Date"] = pd.to_datetime(px["Date"])
    bars = build_bars(px)
    index = {sym: {pd.Timestamp(d): i for i, d in enumerate(b["date"])}
             for sym, b in bars.items()}

    warm = pd.Timestamp(s[s["prox52"].notna()]["date"].min())
    rows = []
    for date, g in s[s["date"] >= warm].groupby("date"):
        cleared = g[g["clears"]]
        if cleared.empty:
            continue
        p = cleared.nlargest(1, "score").iloc[0]
        sym = p["symbol"]
        b, ix = bars.get(sym), index.get(sym, {})
        i0 = ix.get(pd.Timestamp(date))
        if b is None or i0 is None or i0 + 2 >= len(b["close"]):
            continue
        i1 = i0 + 1
        row = {"date": date, "symbol": sym}
        row["base"] = fwd(b, i1)
        for name, frac in (("stop7", 0.07), ("struct", p["stop_proxy"])):
            entry = b["open"][i1]
            stop = entry * (1 - frac) if pd.notna(frac) and frac and frac > 0 else None
            # The holding window must fit inside the series, and the stop is
            # only meaningful while the position is actually open.
            last = max(i1, len(b["close"]) - HOLD)
            hit = False
            for j in range(i1, last):
                if stop and b["low"][j] <= stop:
                    fill = min(stop, b["open"][j]) if b["open"][j] <= stop else stop
                    row[name] = fill / entry - 1.0
                    hit = True
                    break
            if not hit:
                row[name] = fwd(b, i1)
        k = find_confirm(b, i0)
        row["confirm"] = fwd(b, k) if k else np.nan
        lvl = b["low10"][i0]
        k = find_retest(b, i0, lvl) if lvl == lvl else None
        row["retest"] = fwd(b, k) if k else np.nan
        rows.append(row)

    t = pd.DataFrame(rows).dropna(subset=["base"])
    print(f"{HOLD}-session forward return from entry, {len(t)} decision bars "
          f"from {t['date'].min().date()} to {t['date'].max().date()}")
    print("every bar takes the top-ranked gate-clearing name\n")
    print(f"{'variant':<10}{'filled':>8}{'mean':>9}{'vs base':>10}{'t':>7}"
          f"{'win rate':>10}{'worst':>9}")
    print("-" * 63)
    base = t["base"]
    for name in ("base", "stop7", "struct", "confirm", "retest"):
        col = t[name]
        filled = col.notna()
        if not filled.any():
            print(f"{name:<10}never fired")
            continue
        d = col - base
        tstat = t_stat(d) if name != "base" else float("nan")
        print(f"{name:<10}{int(filled.sum()):>6}/{len(t):<3}{col.mean():>8.2%}"
              f"{(d.mean() if name != 'base' else 0):>9.2%}"
              f"{tstat:>7.2f}{(col > 0).mean():>10.1%}{col.min():>8.1%}")
    print("\n'filled' counts the bars where the rule actually produced an entry;")
    print("the rest are NO TRADE and are excluded from that row's mean only.")
    out = ROOT / "reports" / "entry_rules.csv"
    t.to_csv(out, index=False)
    print(f"\nwrote {out.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
