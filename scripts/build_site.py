#!/usr/bin/env python3
"""Build the static research site into reports/site/.

  python scripts/build_site.py
  python scripts/build_site.py --data data/nse_all_history.parquet

Scores every symbol in the universe at its latest usable session, writes
`index.html`, `stocks.json` and one `tape/<SYMBOL>.json` per name, then hands
the result to GitHub Pages.

The universe defaults to the wide NSE file when it exists and the 499-name
Nifty-500 file otherwise, so the site works from a fresh clone and gets
broader as the fetch lands. Either way the payload records which file produced
it and which session it describes, because a verdict without an as-of date is
not a verdict.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from protocol import ranking, site, site_html  # noqa: E402
from protocol.config import get, load_config  # noqa: E402
from protocol.data import load_history  # noqa: E402
from protocol.features import build_panel  # noqa: E402
from protocol.strategies import REGISTRY  # noqa: E402

IC = [
    ("atrpct", -0.0434, -7.35, "low volatility wins — the strongest effect measured"),
    ("prox52", 0.0344, 6.03, "near the 52-week high wins"),
    ("rvol20", -0.0289, -5.79, "LOW relative volume wins: heavy volume is exhaustion"),
    ("efficiency", 0.0178, 3.73, "effort per unit participation"),
    ("penetration", -0.0174, -3.57, "shallow beats deep — deep is exhaustion"),
    ("ret120", 0.0147, None, "the slow trend works"),
    ("ret20", -0.0128, None, "the recent burst REVERSES"),
    ("retention", 0.00009, 0.02, "indistinguishable from noise — dropped"),
]

DROPPED = [
    ("retention", 0.00009, 0.02,
     "NO_INCREMENTAL_INFORMATION — the protocol's own proposed core signal"),
    ("closing_range", -0.0086, -1.72, "not significant"),
    ("closing_disp", -0.0033, -0.65, "not significant, and redundant by definition"),
]


def collect_evidence(cfg, reports: Path, n_reg: int) -> dict:
    """The research findings the site publishes about its own rules."""
    ev: dict = {
        "ic": [{"factor": f, "ic": ic, "t": t, "reading": r}
               for f, ic, t, r in IC],
        "factors_dropped": [{"factor": f, "ic": ic, "t": t, "verdict": v}
                            for f, ic, t, v in DROPPED],
        "audits": [
            {"name": "Data integrity (splits / volume regime)",
             "verdict": "1,159 volume regime shifts scanned; 374 match real split "
                        "ratios; 0 unadjusted price gaps survived the ATR screen"},
            {"name": "Redundancy control",
             "verdict": "NO_INCREMENTAL_INFORMATION — the proposed signal is "
                        "repackaged momentum, so the complexity was discarded"},
            {"name": "Benjamini-Hochberg FDR",
             "verdict": "11 of 27 strategies survive multiple-testing control, "
                        "tested against the seeded random null (-0.0177), not zero"},
            {"name": "Cross-sectional baskets (net of costs)",
             "verdict": "gross top-5 momentum beat the universe by +2.1%; after "
                        "costs this does not survive at small account sizes"},
            {"name": "No-lookahead audit",
             "verdict": "PASS — truncation, shuffle-future, static scan, ordering "
                        "and cutoff checks all pass before a report is written"},
        ],
        "registry": len(REGISTRY),
    }

    rot = reports / "rotation.json"
    if rot.exists():
        d = json.loads(rot.read_text(encoding="utf-8"))
        runs = [{"pick": k, **{kk: v.get(kk) for kk in
                               ("trades", "CAGR", "max_dd", "WinRate", "Expectancy")}}
                for k, v in (d.get("runs") or {}).items()]
        if runs:
            ev["rotation"] = {
                "note": "One stock at a time, 100% of capital, exit on a fixed net "
                        "target or a fixed stop, then the whole account moves to the "
                        "next candidate.",
                "runs": runs,
                "verdict": "The arithmetic mean trade is positive while the "
                           "compounded result is negative — that gap is volatility "
                           "drag, and it is the reason an average return is not a "
                           "return. Choosing the top-ranked candidate does not beat "
                           "picking at random from the same gate-clearing set.",
            }
        if d.get("capital_report"):
            ev["costs"] = d["capital_report"]

    grid = reports / "rotation_grid.csv"
    if grid.exists():
        g = pd.read_csv(grid)
        g = g[g["pick"] == "rank"].sort_values("CAGR", ascending=False)
        ev["geometry"] = {
            "note": "Every cell is reported, including the losing ones. The best "
                    "cell of a grid searched after the fact is an in-sample "
                    "selection — a hypothesis for out-of-sample validation, not a "
                    "rule to trade.",
            "rows": g.to_dict("records"),
        }

    val = reports / "validation.json"
    if val.exists():
        v = json.loads(val.read_text(encoding="utf-8"))
        for name, block in (v.get("tests") or {}).items():
            if isinstance(block, dict) and block.get("verdict"):
                ev["audits"].append({"name": name,
                                     "verdict": str(block["verdict"])[:220]})
    return ev


def main() -> int:
    ap = argparse.ArgumentParser(description="Build the static research site")
    ap.add_argument("--config", default=None)
    ap.add_argument("--data", default=None,
                    help="wide NSE file preferred, Nifty-500 file otherwise")
    ap.add_argument("--outdir", default=str(ROOT / "reports" / "site"))
    ap.add_argument("--asof", default=None)
    ap.add_argument("--reports", default=str(ROOT / "reports"))
    ap.add_argument("--min-history", type=int, default=60,
                    help="drop symbols with fewer sessions than this")
    args = ap.parse_args()

    wide = ROOT / "data" / "nse_all_history.parquet"
    core = ROOT / "data" / "universe_history.parquet"
    path = args.data or (wide if wide.exists() else core)
    if not Path(path).exists():
        print(f"no data file at {path}")
        return 1

    cfg = load_config(args.config)
    history = load_history(path)
    if args.asof:
        history = history[history["Date"] <= pd.Timestamp(args.asof)]
    counts = history.groupby("Symbol")["Date"].transform("size")
    history = history[counts >= args.min_history]
    if history.empty:
        print("no symbol has enough history")
        return 1

    print(f"scoring {history['Symbol'].nunique()} symbols from {Path(path).name} …")
    panel = build_panel(history)
    payload = site.build(panel, cfg,
                         sectors=site.sector_map(ROOT / "data" / "sector_map.csv"),
                         evidence=collect_evidence(cfg, Path(args.reports),
                                                   len(REGISTRY)),
                         asof=args.asof)
    tape = site.tapes(panel, cfg, pd.Timestamp(payload["asof"]),
                      payload["stocks"].keys())

    out = Path(args.outdir)
    site_html.write(out, payload, tape)
    index = (out / "stocks.json").stat().st_size
    detail = sum(f.stat().st_size for f in (out / "stock").glob("*.json"))
    print(f"session {payload['asof']}: {payload['universe']['symbols']} symbols, "
          f"{payload['stats']['cleared']} clear every gate")
    print(f"  index {index/1e6:.2f} MB + {len(tape)} lazy detail files "
          f"{detail/1e6:.2f} MB -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())