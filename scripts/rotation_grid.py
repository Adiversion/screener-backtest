#!/usr/bin/env python3
"""Sweep the fixed profit target and stop loss the rotation mode trades on.

  python scripts/rotation_grid.py --capital 10000

The engine's headline geometry is +15% net target against a -7% stop. That pair
only breaks even above a 33.6% hit rate, and a hit rate is a property of the
GEOMETRY, not just of the entry: a wider target is hit less often but pays more
when it is. This script measures the whole grid instead of asserting one cell.

Everything else is frozen -- same ranking, same gates, same dates, same costs,
same random null. The grid is reported in full, including the cells that lose,
because picking the best cell after the fact is how a backtest gets turned into
a fantasy. The cell that wins here is a HYPOTHESIS to validate out of sample,
not a rule to trade.
"""
from __future__ import annotations

import argparse
import copy
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


def main() -> int:
    ap = argparse.ArgumentParser(description="Target/stop grid for the rotation mode")
    ap.add_argument("--config", default=None)
    ap.add_argument("--data", default=str(ROOT / "data" / "universe_history.parquet"))
    ap.add_argument("--capital", type=float, default=10000.0)
    ap.add_argument("--start", default=None)
    ap.add_argument("--end", default=None)
    ap.add_argument("--targets", default="0.15,0.25,0.40")
    ap.add_argument("--stops", default="0.07,0.12,0.18")
    ap.add_argument("--picks", default="rank,random")
    ap.add_argument("--outdir", default=str(ROOT / "reports"))
    args = ap.parse_args()

    cfg = load_config(args.config)
    start = args.start or get(cfg, "validation.validation_start")
    end = args.end or get(cfg, "validation.validation_end")
    history = load_history(args.data)
    history = history[(history["Date"] >= pd.Timestamp(start))
                      & (history["Date"] <= pd.Timestamp(end))]
    panel = build_panel(history)
    targets = [float(x) for x in args.targets.split(",")]
    stops = [float(x) for x in args.stops.split(",")]
    picks = [p.strip() for p in args.picks.split(",") if p.strip()]

    rows = []
    for target in targets:
        for stop in stops:
            for pick in picks:
                trial = copy.deepcopy(cfg)
                trial["rotation"]["target_net"] = target
                trial["rotation"]["stop_pct"] = stop
                out = rotation.run(panel, trial, capital=args.capital,
                                   start=start, end=end, pick=pick,
                                   bootstrap_n=2000)
                s = out["summary"]
                # the arithmetic edge the grid is really searching for
                rows.append({
                    "target": target, "stop": stop, "pick": pick,
                    "trades": s["trades"], "CAGR": s["CAGR"],
                    "total_return": s["total_return"], "max_dd": s["max_dd"],
                    "hit_rate": s["WinRate"], "expectancy": s["Expectancy"],
                    "time_exit_rate": s["TimeExitRate"],
                    "exposure": s["exposure"],
                })
                print(f"target {target:>5.0%} stop {stop:>5.0%} {pick:<7} "
                      f"n={s['trades']:<4} CAGR={s['CAGR']:+.4f} "
                      f"maxDD={s['max_dd']:+.3f} hit={(s['WinRate'] or 0):.3f} "
                      f"exp={(s['Expectancy'] or 0):+.4f}", flush=True)

    grid = pd.DataFrame(rows)
    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "rotation_grid.csv").write_text(grid.to_csv(index=False), encoding="utf-8")

    ranked = grid[grid["pick"] == "rank"].sort_values("CAGR", ascending=False)
    print("\ntarget/stop grid, ranked pick, best CAGR first:")
    print(ranked[["target", "stop", "trades", "CAGR", "max_dd", "hit_rate",
                  "expectancy"]].to_string(index=False))
    best = ranked.iloc[0]
    print(f"\nbest cell: target {best['target']:.0%} / stop {best['stop']:.0%} "
          f"-> CAGR {best['CAGR']:+.2%}, max drawdown {best['max_dd']:.1%}")
    print("This is the best cell of a grid searched AFTER the fact. It is a "
          "hypothesis for out-of-sample validation, not a rule.")

    payload = {"window": [str(start), str(end)], "capital": args.capital,
               "rows": rows,
               "caveat": "best-of-grid is in-sample selection; validate out of sample"}
    (out / "rotation_grid.json").write_text(json.dumps(payload, indent=2, default=str),
                                            encoding="utf-8")
    print(f"\nwrote {out / 'rotation_grid.csv'}, {out / 'rotation_grid.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())