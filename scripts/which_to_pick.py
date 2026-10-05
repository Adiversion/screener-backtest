#!/usr/bin/env python3
"""Which stocks should actually be held? Top-k clearers vs everything else.

    python scripts/which_to_pick.py

The single-date ledger answers "what happened on 1 Sep". It cannot answer
"which stocks should I pick", because one month is one observation. This asks
the operational question directly: on every session, if you took the top k
names that clear every gate, what did that basket return over the next 20
sessions, compared with holding every gate-clearing name and with holding the
whole universe?

Three comparisons, because they answer different questions:

    top-k vs all clearers   -> does the RANKING add anything, or only the gates?
    top-k vs universe       -> does the whole screen beat just buying the market?
    cash when nothing clears-> what a day with no pick is worth

Cash is carried as a genuine 0% return on the days no name passes, because a
screen that abstains is a position and must be scored as one.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from protocol.data import load_history  # noqa: E402
from protocol.stats import t_stat  # noqa: E402

CACHE = ROOT / "reports" / "scored_panel.parquet"
HORIZON = 20
TOPKS = (1, 3, 5, 10)



def main() -> int:
    s = pd.read_parquet(CACHE)
    s["date"] = pd.to_datetime(s["date"])
    h = load_history(str(ROOT / "data" / "nse_all_history.parquet"))[
        ["Date", "Symbol", "Close"]]
    h["Date"] = pd.to_datetime(h["Date"])
    h = h.sort_values(["Symbol", "Date"])
    h["fwd"] = h.groupby("Symbol", sort=False)["Close"].shift(-HORIZON) / h["Close"] - 1.0
    d = s.merge(h.rename(columns={"Symbol": "symbol", "Date": "date"})[["date", "symbol", "fwd"]],
                on=["date", "symbol"], how="left")

    rows = []
    for date, g in d.groupby("date"):
        g = g.dropna(subset=["fwd"])
        if len(g) < 100:
            continue
        cleared = g[g["clears"]]
        universe = float(g["fwd"].mean())
        all_clear = float(cleared["fwd"].mean()) if len(cleared) else 0.0
        row = {"date": date, "universe": universe, "all_clear": all_clear,
               "n_clear": len(cleared)}
        for k in TOPKS:
            row[f"top{k}"] = float(cleared.nlargest(k, "score")["fwd"].mean()) if len(cleared) else 0.0
        rows.append(row)
    t = pd.DataFrame(rows).dropna()
    print(f"{HORIZON}-session forward return, one row per session, "
          f"{len(t)} sessions\n{t['date'].min().date()} to {t['date'].max().date()}\n")

    base = t["all_clear"]
    print(f"{'basket':<12}{'mean':>9}{'vs all clearers':>18}{'t':>7}"
          f"{'vs universe':>13}{'t':>7}")
    print("-" * 66)
    print(f"{'universe':<12}{t['universe'].mean():>8.2%}{'—':>18}{'—':>7}"
          f"{'—':>13}{'—':>7}")
    print(f"{'all clearers':<12}{base.mean():>8.2%}{'—':>18}{'—':>7}"
          f"{base.mean() - t['universe'].mean():>12.2%}{t_stat(base - t['universe']):>7.2f}")
    for k in TOPKS:
        col = t[f"top{k}"]
        print(f"{'top ' + str(k):<12}{col.mean():>8.2%}"
              f"{(col - base).mean():>17.2%}{t_stat(col - base):>7.2f}"
              f"{(col - t['universe']).mean():>12.2%}{t_stat(col - t['universe']):>7.2f}")

    print(f"\nsessions where nothing cleared: {int((t['n_clear'] == 0).sum())} "
          f"of {len(t)} (counted as 0% return, i.e. cash)")
    print("a t under 2 means the gap is not distinguishable from luck.")

    out = ROOT / "reports" / "which_to_pick.csv"
    t.to_csv(out, index=False)
    print(f"\nwrote {out.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
