#!/usr/bin/env python3
"""Run and compare strategy backtests.

Examples
--------
  python scripts/run_backtest.py --strategies aae_acceptance,trap,breakout_day
  python scripts/run_backtest.py --strategies all --capital 1000
  python scripts/run_backtest.py --set state0.rvol_min=2.5 --set strategies.trap.ret2_min=0.20
  python scripts/run_backtest.py --mode validation      # enforces the config-hash gate
  python scripts/run_backtest.py --mode validation --exploratory
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from protocol import audit, engine, report  # noqa: E402
from protocol.config import (  # noqa: E402
    assert_validation_gate, get, load_config, record_discovery_hash,
)
from protocol.data import data_quality_report, load_history  # noqa: E402
from protocol.strategies import REGISTRY  # noqa: E402

DEFAULT_DATA = ROOT / "data" / "universe_history.parquet"
PROTOCOL_STRATEGIES = ["aae_acceptance", "trap", "breakout_day", "vol_breakout",
                       "momentum_top", "high_52w", "trend", "fip_proxy",
                       "high_effort_low_result", "recovered_after_rej", "random"]


def _apply_override(cfg: dict, assignment: str) -> None:
    key, _, raw = assignment.partition("=")
    node = cfg
    parts = key.split(".")
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    node[parts[-1]] = yaml.safe_load(raw)


def _load_universe_arg(value: str | None, history) -> list[str] | None:
    if not value or value == "all":
        return None
    p = Path(value)
    if p.exists():
        return [ln.strip().upper() for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
    return [s.strip().upper() for s in value.split(",") if s.strip()]


def main() -> int:
    ap = argparse.ArgumentParser(description="Strategy comparison backtester")
    ap.add_argument("--config", default=None)
    ap.add_argument("--data", default=str(DEFAULT_DATA))
    ap.add_argument("--symbols", default="all", help="all | file.txt | SYM1,SYM2")
    ap.add_argument("--strategies", default="protocol", help="protocol | all | comma list")
    ap.add_argument("--capital", type=float, default=None)
    ap.add_argument("--mode", choices=["discovery", "validation", "exploratory"], default="exploratory")
    ap.add_argument("--exploratory", action="store_true")
    ap.add_argument("--cutoff", default=None)
    ap.add_argument("--outdir", default=str(ROOT / "reports"))
    ap.add_argument("--set", action="append", default=[], dest="overrides")
    args = ap.parse_args()

    cfg = load_config(args.config)
    for assignment in args.overrides:
        _apply_override(cfg, assignment)
    exploratory = args.exploratory or args.mode == "exploratory"
    if args.mode == "validation":
        assert_validation_gate(cfg, exploratory)

    if args.cutoff:
        cutoff = None if str(args.cutoff).lower() in ("none", "latest", "all") else args.cutoff
    else:
        cutoff = get(cfg, "validation.validation_end") if args.mode == "validation" else None
    history = load_history(args.data)
    if cutoff:
        history = history[history["Date"] <= pd.Timestamp(cutoff)]

    subset = _load_universe_arg(args.symbols, history)
    if subset:
        history = history[history["Symbol"].isin(subset)]

    strategies = (PROTOCOL_STRATEGIES if args.strategies == "protocol"
                  else list(REGISTRY) if args.strategies == "all"
                  else [s.strip() for s in args.strategies.split(",")])
    capitals = [args.capital] if args.capital else cfg["run"]["capitals"]

    window = (None, None)
    if args.mode == "discovery":
        window = (get(cfg, "validation.discovery_start"), get(cfg, "validation.discovery_end"))
    elif args.mode == "validation":
        window = (get(cfg, "validation.validation_start"), get(cfg, "validation.validation_end"))

    data = engine.run_comparison(cfg, history, strategies, capitals, window)
    data["mode"] = args.mode
    data["exploratory"] = exploratory
    data["data_quality"] = data_quality_report(history)

    all_trades = [t for name, per_cap in data["results"].items() if "error" not in per_cap
                  for run in per_cap.values() for t in run["trades"]]
    from protocol.features import build_panel
    panel = build_panel(history)
    data["audit"] = audit.run_all(history, panel, all_trades, cutoff or history["Date"].max(), cfg)
    if "aae_acceptance" in data["results"]:
        first_cap = next(iter(data["results"]["aae_acceptance"].values()))
        label, reason = report.verdict(first_cap, get(cfg, "validation.min_validation_trades", 150))
    else:
        label, reason = "NOT RUN", "aae_acceptance not in strategy list"
    data["verdict"] = {"label": label, "reason": reason}

    paths = report.write_outputs(data, cfg, args.outdir)
    if args.mode == "discovery":
        record_discovery_hash(cfg["_hash"])

    print(f"config hash : {cfg['_hash']}")
    print(f"universe    : {data['universe']}")
    print(f"audit       : {'PASS' if data['audit']['passed'] else 'FAIL'}")
    print(f"reports     : {paths['md']}")
    for row in report.comparison_table(data)[:12]:
        print(f"  {row['Strategy']:<24} N={row.get('N'):<5} "
              f"Win={row.get('WinRate')} Safe={row.get('SafeRate')} Exp={row.get('Expectancy')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
