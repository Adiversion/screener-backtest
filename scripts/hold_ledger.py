#!/usr/bin/env python3
"""The plain ledger: put money in on one date, look at it on another.

    python scripts/hold_ledger.py --pick 2026-09-01 --mark 2026-10-01 --top 10

Every other study in this repo reports a mean over many decision bars, which is
the right way to ask whether a RULE works. It is the wrong way to answer "what
happened to the stocks you picked me". This script answers only that: one date
in, one date out, rupee P&L on a fixed stake per name.

Entry is the NEXT session's open, not the pick-date close. The verdict is
computed from that day's close, so trading at it would be assuming you already
knew the day's final print. Open is also what you would actually have paid.

The benchmark is the equal-weight mean of every symbol scored that day, marked
over the same sessions. Without it a number like "+4%" has no meaning.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from protocol import quality, ranking  # noqa: E402
from protocol.config import load_config  # noqa: E402
from protocol.data import load_history  # noqa: E402
from protocol.features import build_panel  # noqa: E402

CACHE = ROOT / "reports" / "scored_panel.parquet"


def scored_panel(cfg=None) -> pd.DataFrame:
    """The scored panel, cached, because scoring 2,317 symbols takes minutes."""
    if CACHE.exists():
        return pd.read_parquet(CACHE)
    cfg = cfg or load_config()
    history = load_history(str(ROOT / "data" / "nse_all_history.parquet"))
    df = ranking.rank_all(ranking.build_long(build_panel(history), cfg),
                          cfg, quality.COMPONENTS)
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(CACHE, index=False)
    return df


def session_on_or_after(dates: pd.DatetimeIndex, when: pd.Timestamp,
                        direction: str) -> pd.Timestamp | None:
    if direction == "next":
        later = dates[dates > when]
        return pd.Timestamp(later[0]) if len(later) else None
    earlier = dates[dates <= when]
    return pd.Timestamp(earlier[-1]) if len(earlier) else None


def main() -> int:
    ap = argparse.ArgumentParser(description="One date in, one date out, rupees")
    ap.add_argument("--pick", required=True, help="verdict date, e.g. 2026-09-01")
    ap.add_argument("--mark", required=True, help="valuation date, e.g. 2026-10-01")
    ap.add_argument("--top", type=int, default=10, help="how many to hold")
    ap.add_argument("--stake", type=float, default=10000.0, help="rupees per name")
    args = ap.parse_args()

    cfg = load_config()
    history = load_history(str(ROOT / "data" / "nse_all_history.parquet"))
    px = history.copy()
    px["Date"] = pd.to_datetime(px["Date"])
    panel = scored_panel(cfg)
    panel["date"] = pd.to_datetime(panel["date"])

    sessions = pd.DatetimeIndex(sorted(px["Date"].unique()))
    pick, mark = pd.Timestamp(args.pick), pd.Timestamp(args.mark)
    entry = session_on_or_after(sessions, pick, "next")
    exit_ = session_on_or_after(sessions, mark, "prev")
    if entry is None or exit_ is None or entry > exit_:
        print("pick/mark dates leave no room to trade; data spans "
              f"{sessions[0].date()} to {sessions[-1].date()}")
        return 1

    day = panel[panel["date"] == pick]
    if day.empty:
        print(f"no scored session on {pick.date()}")
        return 1
    cleared = day[day["clears"]].nlargest(args.top, "score")
    if cleared.empty:
        print(f"nothing cleared every gate on {pick.date()} -- the correct "
              f"position was cash")
        return 0

    print(f"verdict {pick.date()}  |  enter {entry.date()} at the open  |  "
          f"valued {exit_.date()} at the close  |  {args.stake:,.0f} per name\n")
    open_ = px[px["Date"] == entry].set_index("Symbol")["Open"]
    close_ = px[px["Date"] == exit_].set_index("Symbol")["Close"]
    entry_close = px[px["Date"] == entry].set_index("Symbol")["Close"]
    mark_close = px[px["Date"] == exit_].set_index("Symbol")["Close"]

    rows = []
    for rank, (_, p) in enumerate(cleared.iterrows(), 1):
        sym = p["symbol"]
        o = float(open_.get(sym, np.nan))
        m = float(close_.get(sym, np.nan))
        if not o or pd.isna(o) or pd.isna(m):
            continue
        qty = args.stake / o
        rows.append({"rank": rank, "symbol": sym, "score": round(float(p["score"]), 4),
                     "open": round(o, 2), "close": round(m, 2),
                     "qty": round(qty, 2), "pnl": round(qty * (m - o), 2),
                     "ret": round(m / o - 1.0, 4)})
    led = pd.DataFrame(rows)
    if led.empty:
        print("no priced entries on the entry date")
        return 1

    # Equal-weight basket of the same names that were SCORED on the pick date,
    # each held from the same entry open to the same closing print. Averaging
    # closes instead would weight the benchmark by share price, which has
    # nothing to do with how a rupee is deployed.
    universe = day[day["close"].notna()]["symbol"]
    u_open, u_mark = entry_close.reindex(universe), mark_close.reindex(universe)
    ok = u_open.notna() & u_mark.notna() & (u_open > 0)
    bench_ret = float((u_mark[ok] / u_open[ok] - 1.0).mean())
    bench_n = int(ok.sum())
    invested = args.stake * len(led)
    value = float((led["qty"] * led["close"]).sum())

    print(f"{'#':>2} {'symbol':<14}{'score':>7}{'entry':>11}{'1 Oct':>11}"
          f"{'qty':>9}{'P&L':>11}{'ret':>8}")
    print("-" * 73)
    for _, r in led.iterrows():
        print(f"{int(r['rank']):>2} {r['symbol']:<14}{r['score']:>7.4f}"
              f"{r['open']:>11.2f}{r['close']:>11.2f}{r['qty']:>9.2f}"
              f"{r['pnl']:>11.2f}{r['ret']:>8.2%}")
    print("-" * 73)
    print(f"{'':<34}{'invested':>11}{invested:>11.2f}")
    print(f"{'':<34}{'value':>11}{value:>11.2f}")
    print(f"{'':<34}{'P&L':>11}{value - invested:>11.2f}"
          f"{(value / invested - 1):>8.2%}")
    print(f"\nequal-weight universe over the same sessions: {bench_ret:+.2%}")
    print(f"your picks beat it by {value / invested - 1 - bench_ret:+.2%}")
    print(f"winners {int((led['pnl'] > 0).sum())}/{len(led)}   "
          f"worst {led['ret'].min():+.2%} ({led.nsmallest(1, 'ret')['symbol'].iloc[0]})   "
          f"best {led['ret'].max():+.2%} ({led.nlargest(1, 'ret')['symbol'].iloc[0]})")
    print("\nno exit rule, no stop, no target -- bought and forgotten, exactly "
          "as asked.")

    out = ROOT / "reports"
    out.mkdir(parents=True, exist_ok=True)
    led.to_csv(out / f"hold_ledger_{pick.date()}_{exit_.date()}.csv", index=False)
    print(f"\nwrote {out / f'hold_ledger_{pick.date()}_{exit_.date()}.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
