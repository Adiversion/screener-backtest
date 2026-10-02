#!/usr/bin/env python3
"""Run the single-position rotation mode: one stock, whole account, rotate.

  python scripts/rotate.py --capital 1000
  python scripts/rotate.py --capital 10000 --start 2021-01-01
  python scripts/rotate.py --capital 1000 --no-markdown

This is the engine's real deployment shape: investment only, no day trading,
no derivatives. One candidate at a time, 100% of capital in it, exit when the
fixed profit target or the fixed stop is hit, then the entire account moves to
the next prime candidate. `random` picks uniformly among the SAME
gate-clearing candidates, so it is the null the ranked mode has to beat before
any of its picks mean anything.

Writes reports/ROTATION.md and reports/rotation.json.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from protocol import rotation  # noqa: E402
from protocol.config import get, load_config  # noqa: E402
from protocol.data import load_history  # noqa: E402
from protocol.features import build_panel  # noqa: E402


def _day(value) -> str:
    """Dates live as Timestamps in the trade record; reports want ISO days."""
    return str(pd.Timestamp(value).date())


def to_markdown(payload: dict) -> str:
    s = payload["summary"]
    L = [
        "# Single-position rotation -- one stock, the whole account", "",
        f"- As of: **{payload['asof']}**  |  config hash `{payload['config_hash'][:12]}`",
        f"- Universe: {payload['universe']['symbols']} symbols, "
        f"{payload['universe']['from']} to {payload['universe']['to']}",
        f"- Exit rule: net target {payload['policy']['target_net']:.0%}, stop "
        f"{payload['policy']['stop_pct']:.0%}, time stop "
        f"{payload['policy']['hold_sessions']} sessions",
        "", "## 1. The answer", "",
        f"**{payload['headline']}**", "",
        "## 2. One rotation per line", "",
    ]
    if payload["trades"]:
        L += ["| # | Stock | In | Out | Days | Reason | Gross | Net | Capital after |",
              "|---|---|---|---|---|---|---|---|---|"]
        for i, t in enumerate(payload["trades"], 1):
            L.append(
                f"| {i} | **{t['symbol']}** | {_day(t['entry_date'])} @ {t['entry_px']} "
                f"| {_day(t['exit_date'])} @ {t['exit_px']} | {t['sessions_held']} "
                f"| {t['exit_reason']} | {t['gross_move']:.2%} | {t['net_pnl_pct']:.2%} "
                f"| {t['capital_after']:,} |")
    else:
        L.append("_No position was ever opened: nothing cleared the hard gates._")
    L += ["", "## 3. What one rotation costs you", "",
          "The DP charge is flat per SELL, so it scales as 1/capital. This is "
          "arithmetic, not opinion.", "",
          "| Capital | Shares @ Rs250 | DP as % of capital | Round trip | Idle cash | Gross move needed for the net target |",
          "|---|---|---|---|---|---|"]
    for r in payload["capital_report"]:
        L.append(f"| {r['capital']:,} | {r['shares@250']} | {r['dp_pct_of_capital']}% "
                 f"| {r['round_trip_bps_of_capital']} bps | {r['idle_cash_pct']}% "
                 f"| {r['gross_for_target']:.2%} |")
    L += ["", "## 4. What this does and does not prove", ""]
    L += [f"- {c}" for c in payload["caveats"]]
    L += ["", "Nothing here is investment advice. Labels are `HISTORICAL_CANDIDATE`, "
          "never \"BUY\"."]
    return "\n".join(L)


CAVEATS = [
    "One position at a time means compounding is real, but so is concentration "
    "risk: a single stop costs a single stock's full drawdown.",
    "The universe is today's Nifty-500 constituents, so this is a "
    "current-constituent walk-forward, not a survivorship-controlled one.",
    "The ranking weights were fitted to 5-day forward returns; they were never "
    "validated on a months-long holding period (see protocol/quality.py).",
    "Prices are adjusted OHLCV; delivery percentages are not in the price file.",
]


def main() -> int:
    ap = argparse.ArgumentParser(description="One stock, whole account, rotate")
    ap.add_argument("--config", default=None)
    ap.add_argument("--data", default=str(ROOT / "data" / "universe_history.parquet"))
    ap.add_argument("--capital", type=float, default=1000.0)
    ap.add_argument("--start", default=None)
    ap.add_argument("--end", default=None)
    ap.add_argument("--picks", default=None, help="comma list, default from config")
    ap.add_argument("--no-markdown", action="store_true")
    ap.add_argument("--outdir", default=str(ROOT / "reports"))
    args = ap.parse_args()

    cfg = load_config(args.config)
    start = args.start or get(cfg, "validation.validation_start")
    end = args.end or get(cfg, "validation.validation_end")
    history = load_history(args.data)
    history = history[(history["Date"] >= pd.Timestamp(start))
                      & (history["Date"] <= pd.Timestamp(end))]
    if history.empty:
        print("no data between", start, "and", end)
        return 1
    panel = build_panel(history)

    picks = ([p.strip() for p in args.picks.split(",") if p.strip()]
             if args.picks else list(cfg["rotation"]["picks"]))
    runs = {}
    for pick in picks:
        print(f"running pick={pick} ...", flush=True)
        runs[pick] = rotation.run(panel, cfg, capital=args.capital,
                                  start=start, end=end, pick=pick)

    base = runs.get("rank") or next(iter(runs.values()))
    s = base["summary"]
    ranked_beats = ("rank" not in runs or runs["rank"]["summary"]["CAGR"]
                    > (runs.get("random", {}).get("summary", {}) or {}).get("CAGR", -9))
    headline = (
        f"Ranking the universe and rotating the whole account produced "
        f"{s['trades']} trades over {s['years']} years, turning "
        f"INR {s['initial']:,.0f} into INR {s['final']:,.0f} "
        f"({s['total_return']:+.1%} total, {s['CAGR']:+.1%} a year, worst "
        f"drawdown {s['max_dd']:.1%}). "
        + (f"Choosing the top-ranked candidate "
           f"{'BEATS' if ranked_beats else 'does NOT beat'} picking at random from "
           f"the same gate-clearing candidates." if "random" in runs else ""))
    payload = {
        "asof": str(end), "config_hash": cfg["_hash"], "capital": args.capital,
        "window": [str(start), str(end)], "policy": cfg["rotation"],
        "universe": {"symbols": int(history["Symbol"].nunique()),
                     "from": str(history["Date"].min().date()),
                     "to": str(history["Date"].max().date())},
        "headline": headline, "summary": s, "trades": base["trades"],
        "runs": {k: v["summary"] for k, v in runs.items()},
        "capital_report": rotation.capital_report(cfg).to_dict("records"),
        "caveats": CAVEATS,
    }

    print("\n" + headline)
    print(f"\n{'pick':<10}{'trades':>8}{'CAGR':>10}{'total':>10}{'maxDD':>9}"
          f"{'win':>8}{'expectancy':>12}{'exposure':>10}")
    for k, v in runs.items():
        r = v["summary"]
        print(f"{k:<10}{r['trades']:>8}{r['CAGR']:>10.4f}{r['total_return']:>10.4f}"
              f"{r['max_dd']:>9.4f}{(r['WinRate'] or 0):>8.3f}"
              f"{(r['Expectancy'] or 0):>12.4f}{r['exposure']:>10.3f}")
    if base["trades"]:
        print("\ntrade ledger:")
        for t in base["trades"]:
            print(f"  {_day(t['entry_date'])} -> {_day(t['exit_date'])}  "
                  f"{t['symbol']:<12} {t['exit_reason']:<9} "
                  f"gross {t['gross_move']:+.2%}  net {t['net_pnl_pct']:+.2%}  "
                  f"capital {t['capital_after']:,.0f}")
    print("\n" + rotation.capital_report(cfg).to_string(index=False))

    if not args.no_markdown:
        out = Path(args.outdir)
        out.mkdir(parents=True, exist_ok=True)
        (out / "ROTATION.md").write_text(to_markdown(payload), encoding="utf-8")
        (out / "rotation.json").write_text(
            json.dumps({**payload, "equity": base["equity"]}, indent=2, default=str),
            encoding="utf-8")
        print(f"\nwrote {out / 'ROTATION.md'}, {out / 'rotation.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())