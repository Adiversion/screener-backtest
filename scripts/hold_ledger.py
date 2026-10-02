#!/usr/bin/env python3
"""The plain ledger: put money in on one date, look at it on another.

    python scripts/hold_ledger.py --pick 2026-09-01 --mark 2026-10-01 --top 10
    python scripts/hold_ledger.py --pick 2026-09-01 --mark 2026-10-01 --top 10 --stop 0.07

Every other study in this repo reports a mean over many decision bars, which is
the right way to ask whether a RULE works. It is the wrong way to answer "what
happened to the stocks you picked me". This script answers only that: one date
in, one date out, rupee P&L on a fixed stake per name.

Entry is the NEXT session's open, not the pick-date close. The verdict is
computed from that day's close, so trading at it would be assuming you already
knew the day's final print. Open is also what you would actually have paid.

A stop, if given, is checked against each session's LOW, because that is the
price that would have triggered it, and a gap through the stop fills at the open
rather than at the stop price. Pretending every stop fills exactly at the stop
is the single easiest way to make a stop-loss rule look profitable.

The benchmark is the equal-weight mean of every symbol scored that day, held
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


def session_on_or_before(dates: pd.DatetimeIndex, when: pd.Timestamp,
                         forward: bool) -> pd.Timestamp | None:
    sel = dates[dates > when] if forward else dates[dates <= when]
    if not len(sel):
        return None
    return pd.Timestamp(sel[0] if forward else sel[-1])


def walk_to_stop(bars: pd.DataFrame, entry_px: float, entry_date: pd.Timestamp,
                 stop_pct: float | None,
                 mark: pd.Timestamp) -> tuple[pd.Timestamp, float, str]:
    """Follow one name from entry until the stop, the mark date, or the end.

    `bars` must already start at the entry session. The stop is tested against
    each session's LOW, which is the print that would actually have triggered
    it; a session that opened below the stop had no chance to fill at the stop
    price, so the fill is the open.
    """
    if stop_pct:
        stop = entry_px * (1.0 - stop_pct)
        for i in range(1, len(bars)):
            row = bars.iloc[i]
            if row["Low"] <= stop:
                fill = min(stop, float(row["Open"])) if row["Open"] <= stop else stop
                return pd.Timestamp(row["Date"]), float(fill), "stop"
    held = bars[bars["Date"] <= mark]
    row = held.iloc[-1]
    return pd.Timestamp(row["Date"]), float(row["Close"]), "held"


def main() -> int:
    ap = argparse.ArgumentParser(description="One date in, one date out, rupees")
    ap.add_argument("--pick", required=True, help="verdict date, e.g. 2026-09-01")
    ap.add_argument("--mark", required=True, help="valuation date, e.g. 2026-10-01")
    ap.add_argument("--top", type=int, default=10, help="how many to hold")
    ap.add_argument("--stake", type=float, default=10000.0, help="rupees per name")
    ap.add_argument("--stop", default=None,
                    help="'auto' for each stock's own structural stop below its "
                         "10-session swing low, or a fraction like 0.07. "
                         "Default is the structural stop, because a flat 7%% "
                         "is narrower than the volatility of half the names "
                         "it is applied to.")
    ap.add_argument("--flat-stop", type=float, default=None,
                    help="force a single fractional stop, for comparison")
    args = ap.parse_args()

    stop_pct = None
    if args.stop == "auto":
        stop_pct = "auto"
    elif args.stop is not None:
        stop_pct = float(args.stop)
    elif args.flat_stop is not None:
        stop_pct = float(args.flat_stop)
    if stop_pct is None:
        stop_pct = "auto"

    cfg = load_config()
    history = load_history(str(ROOT / "data" / "nse_all_history.parquet"))
    px = history.copy()
    px["Date"] = pd.to_datetime(px["Date"])
    panel = scored_panel(cfg)
    panel["date"] = pd.to_datetime(panel["date"])

    sessions = pd.DatetimeIndex(sorted(px["Date"].unique()))
    pick, mark = pd.Timestamp(args.pick), pd.Timestamp(args.mark)
    entry = session_on_or_before(sessions, pick, forward=True)
    exit_ = session_on_or_before(sessions, mark, forward=False)
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

    stop_txt = (" | per-stock structural stop, checked daily against the low"
                if stop_pct == "auto" else f" | {stop_pct:.0%} stop, daily, vs the low")
    print(f"verdict {pick.date()}  |  enter {entry.date()} at the open  |  "
          f"valued {exit_.date()}{stop_txt}\n")
    print(f"{'#':>2} {'symbol':<13}{'score':>7}{'entry':>10}{'out':>10}{'exit':>12}"
          f"{'stop':>7}{'why':>7}{'P&L':>10}{'ret':>8}")
    print("-" * 87)

    by_symbol = {s: g.sort_values("Date").reset_index(drop=True)
                 for s, g in px.groupby("Symbol")}
    entry_close = px[px["Date"] == entry].set_index("Symbol")["Close"]
    mark_close = px[px["Date"] == exit_].set_index("Symbol")["Close"]

    rows = []
    for rank, (_, p) in enumerate(cleared.iterrows(), 1):
        sym = p["symbol"]
        bars = by_symbol.get(sym)
        if bars is None or entry not in set(bars["Date"]):
            continue
        px_entry = float(bars.loc[bars["Date"] == entry, "Open"].iloc[0])
        if not px_entry:
            continue
        # "auto" reads the stop the quality engine already computed for this
        # name on the pick date: below its 10-session swing low, less a quarter
        # ATR. It is wide for a volatile name and tight for a calm one, which
        # is the whole point -- a flat 7% is narrower than the noise in half
        # the universe and gets stopped out by ordinary movement.
        use = stop_pct
        if stop_pct == "auto":
            sp = float(p.get("stop_proxy", np.nan)) if "stop_proxy" in cleared.columns else np.nan
            use = sp if pd.notna(sp) and sp > 0 else None
        path = bars[bars["Date"] >= entry].reset_index(drop=True)
        out_date, out_px, why = walk_to_stop(path, px_entry, entry, use, exit_)
        qty = args.stake / px_entry
        rows.append({"rank": rank, "symbol": sym,
                     "score": round(float(p["score"]), 4),
                     "entry": round(px_entry, 2), "qty": round(qty, 2),
                     "out_date": str(out_date.date()), "exit": round(out_px, 2),
                     "why": why, "pnl": round(qty * (out_px - px_entry), 2),
                     "ret": round(out_px / px_entry - 1.0, 4),
                     "stop": None if use is None else round(float(use), 4)})
    led = pd.DataFrame(rows)
    if led.empty:
        print("no priced entries on the entry date")
        return 1

    for _, r in led.iterrows():
        print(f"{int(r['rank']):>2} {r['symbol']:<13}{r['score']:>7.4f}"
              f"{r['entry']:>10.2f}{r['qty']:>9.2f} {r['exit']:>9.2f} on {r['out_date']}"
              f"{('  n/a' if r['stop'] is None else format(r['stop'], '.1%')):>7}"
              f"{r['why']:>7}{r['pnl']:>10.2f}{r['ret']:>8.2%}")
    print("-" * 79)
    invested = args.stake * len(led)
    value = float((led["qty"] * led["exit"]).sum())
    stopped = int((led["why"] == "stop").sum())
    print(f"{'':<40}{'invested':>10}{invested:>10.2f}")
    print(f"{'':<40}{'value':>10}{value:>10.2f}")
    print(f"{'':<40}{'P&L':>10}{value - invested:>10.2f}"
          f"{(value / invested - 1):>8.2%}")

    universe = day[day["close"].notna()]["symbol"]
    u_open, u_mark = entry_close.reindex(universe), mark_close.reindex(universe)
    ok = u_open.notna() & u_mark.notna() & (u_open > 0)
    bench = float((u_mark[ok] / u_open[ok] - 1.0).mean())
    print(f"\nequal-weight universe over the same sessions "
          f"({int(ok.sum())} names): {bench:+.2%}")
    print(f"your picks beat it by {value / invested - 1 - bench:+.2%}")
    print(f"winners {int((led['pnl'] > 0).sum())}/{len(led)}   "
          f"stopped out {stopped}/{len(led)}   "
          f"worst {led['ret'].min():+.2%} ({led.nsmallest(1, 'ret')['symbol'].iloc[0]})   "
          f"best {led['ret'].max():+.2%} ({led.nlargest(1, 'ret')['symbol'].iloc[0]})")

    out = ROOT / "reports"
    out.mkdir(parents=True, exist_ok=True)
    tag = "structstop" if stop_pct == "auto" else f"stop{float(stop_pct):.0%}"
    path = out / f"hold_ledger_{pick.date()}_{exit_.date()}_{tag}.csv"
    led.to_csv(path, index=False)
    print(f"\nwrote {path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
