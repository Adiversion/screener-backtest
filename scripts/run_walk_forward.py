#!/usr/bin/env python3
"""Run expanding walk-forward out-of-sample validation across NSE equities.

Executes:
1. 3 Expanding Walk-Forward Folds (2018-2021 -> 2022 Bear, 2018-2022 -> 2023 Recovery, 2018-2023 -> 2024-2026 Expansion).
2. Purged train/test boundaries with execution lag (t+1 Open).
3. Realistic 25 bps round-trip transaction costs and statutory fees.
4. Deflated Sharpe Ratio (DSR) discounting multiple testing.
5. Parameter stability plateau check across volume thresholds [1.2x, 1.4x, 1.6x].
6. Outputs reports/walk_forward_report.json and a formatted summary table.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from protocol.data import load_history  # noqa: E402
from protocol.walk_forward import run_walk_forward_evaluation  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Run Walk-Forward Out-of-Sample Validation")
    ap.add_argument("--data", default=str(ROOT / "data" / "nse_all_history.parquet"))
    ap.add_argument("--rvol", type=float, default=1.4)
    ap.add_argument("--cost-bps", type=float, default=25.0)
    ap.add_argument("--out", default=str(ROOT / "reports" / "walk_forward_report.json"))
    args = ap.parse_args()

    print(f"Loading panel data from {args.data}...")
    df = load_history(args.data)
    print(f"Loaded {len(df):,} bars across {df['Symbol'].nunique()} active symbols.")

    print("\nExecuting Expanding Purged Walk-Forward Evaluation...")
    wf = run_walk_forward_evaluation(df, rvol_thresh=args.rvol, cost_bps=args.cost_bps)

    out_p = Path(args.out)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_text(json.dumps(wf, indent=2), encoding="utf-8")
    print(f"Saved full validation payload to {out_p}")

    print("\n" + "=" * 80)
    print("EXPANDING PURGED WALK-FORWARD & DEFLATED SHARPE VALIDATION SCORECARD")
    print("=" * 80)
    print(f"In-Sample (IS) Win Rate:           {wf['in_sample_win_rate']:.1f}%")
    print(f"Out-of-Sample (OOS) Win Rate:      {wf['out_of_sample_win_rate']:.1f}%")
    print(f"Win Rate Retention:                {wf['win_rate_retention']:.1f}% (IS -> OOS)")
    print(f"Out-of-Sample Profit Factor:       {wf['out_of_sample_profit_factor']:.2f}")
    print(f"Worst Fold OOS Win Rate:           {wf['worst_fold_win_rate']:.1f}%")
    print(f"Deflated Sharpe Ratio (DSR):       {wf['deflated_sharpe_ratio']:.2f}")
    print(f"Total Out-of-Sample Trades:        {wf['total_out_of_sample_trades']:,}")
    print(f"Cost Friction Basis:               {wf['cost_basis']}")
    print(f"Parameter Stability Plateau:       {wf['parameter_stability']}")
    print(f"Final Institutional Verdict:       {wf['verdict']}")
    print("=" * 80)

    print("\nFold Breakdown:")
    for f in wf["folds"]:
        print(f"  • {f['fold_name']} ({f['regime_type']}):")
        print(f"      Train: {f['train_period']} -> IS WR: {f['is_win_rate']:.1f}%")
        print(f"      Test:  {f['test_period']}  -> OOS WR: {f['oos_win_rate']:.1f}% | PF: {f['oos_profit_factor']:.2f} | Trades: {f['oos_trades']}")

    print("\nParameter Stability Plateau (RVOL Threshold Audit):")
    for row in wf["plateau_table"]:
        print(f"  • RVOL >= {row['rvol_threshold']}: Win Rate = {row['win_rate']:.1f}% | Profit Factor = {row['profit_factor']:.2f}")

    print("\n" + "=" * 80 + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
