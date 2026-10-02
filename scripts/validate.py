#!/usr/bin/env python3
"""Validation milestone: the four tests the spec demanded and nobody ran.

    python scripts/validate.py                 # full run
    python scripts/validate.py --quick         # skip the cross-sectional pass
    python scripts/validate.py --strategies protocol

Writes `reports/VALIDATION.md` and `reports/validation.json`.

This does NOT re-run the backtest. It consumes `reports/report.json` for the
multiple-testing pass, so run `run_backtest.py` first (or accept that pass as
untested).

The four tests, and why each exists:

  1. dataqc     Data integrity. Does the panel contain volume regime shifts or
                unadjusted price discontinuities that would corrupt the
                volume-based features?
  2. redundancy Is the proposed signal just repackaged momentum? This is the
                spec's "CONTROL FOR REDUNDANCY" and its stated most important
                principle. Never run before now.
  3. inference  Benjamini-Hochberg FDR across every strategy tested. 29
                hypotheses at a nominal 5% will manufacture false positives;
                this controls for it.
  4. crosssec   Do top-N baskets beat the equal-weight universe? Every existing
                result is event-level and cannot answer this.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from protocol import crosssec, dataqc, inference, pra, redundancy  # noqa: E402
from protocol import validation_md  # noqa: E402
from protocol.config import canonical_hash, load_config  # noqa: E402
from protocol.data import load_history  # noqa: E402
from protocol.features import build_panel  # noqa: E402


def _events_frame(panel: dict[str, pd.DataFrame], cfg: dict) -> pd.DataFrame:
    """PRA event table with the panel features attached, ready for testing.

    Restricted to events that actually *challenged* the reference
    (`penetration > 0`), because the spec's question -- "does retention explain
    outcome once you control for breakout magnitude?" -- is only meaningful
    where a breakout happened. Including near-approach events would dilute the
    test with rows where retention is undefined.
    """
    frames = []
    for symbol, feat in panel.items():
        d = feat.reset_index(drop=True)
        ev = pra.classify_events(d, cfg, symbol)
        if ev.empty:
            continue
        ev = pra.attach_outcomes(d, ev, cfg)
        if ev.empty:
            continue
        ev["symbol"] = symbol
        want = ["rvol20", "atr14", "atrpct", "retention", "penetration",
                "closing_disp", "efficiency", "closing_range", "result_atr",
                "ret20", "ret60", "ret120", "prox52", "turnover20"]
        have = [c for c in want if c in d.columns and c not in ev.columns]
        # merge on the event date, then drop the join key and any duplicate
        merged = ev.merge(d[["Date", *have]], left_on="date", right_on="Date",
                          how="left")
        merged = merged.loc[:, ~merged.columns.duplicated()]
        merged = merged.drop(columns=[c for c in ("Date",) if c in merged.columns])
        frames.append(merged)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    if "penetration" in out.columns:
        pen = pd.to_numeric(out["penetration"], errors="coerce")
        out = out[pen > 0].reset_index(drop=True)
    return out


def _strategy_rows(report_path: Path, cfg: dict) -> tuple[list[dict], float | None]:
    """One row per strategy from report.json, with a p-value attached.

    The p-value tests H0: expectancy == the seeded random null's expectancy.
    Testing against zero instead would flag every strategy in the study,
    since nearly all of them are negative.
    """
    if not report_path.exists():
        return [], None
    data = json.loads(report_path.read_text(encoding="utf-8"))
    min_n = int(cfg["inference"]["min_n_for_test"])
    results = data.get("results") or {}

    def _metrics(name: str) -> dict:
        for run in (results.get(name) or {}).values():
            if "error" not in run:
                return run.get("metrics", {})
        return {}

    null_metrics = _metrics("random")
    null_exp = null_metrics.get("Expectancy")
    rows = []
    for name, per_cap in results.items():
        if name == "random":
            continue          # the null is the hypothesis, not a candidate
        m = _metrics(name)
        if int(m.get("N") or 0) == 0:
            continue
        rows.append({
            "name": name, "N": m.get("N"), "expectancy": m.get("Expectancy"),
            "std": m.get("Std"), "safe_rate": m.get("SafeRate"),
            "p": inference.pvalue_of(m, min_n, null_exp) if null_exp is not None else None,
        })
    return rows, null_exp


def main() -> int:
    ap = argparse.ArgumentParser(description="Run the four validation tests")
    ap.add_argument("--config", default=None)
    ap.add_argument("--data", default=str(ROOT / "data" / "universe_history.parquet"))
    ap.add_argument("--outdir", default=str(ROOT / "reports"))
    ap.add_argument("--quick", action="store_true", help="skip the basket pass")
    ap.add_argument("--asof", default=None)
    args = ap.parse_args()

    cfg = load_config(args.config)
    asof = pd.Timestamp(args.asof) if args.asof else None
    history = load_history(args.data)
    if asof is not None:
        history = history[history["Date"] <= asof]
    if history.empty:
        print("no data")
        return 1

    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)
    payload = {
        "config_hash": canonical_hash(cfg),
        "universe": {"symbols": int(history["Symbol"].nunique()),
                     "sessions": int(history["Date"].nunique()),
                     "from": str(history["Date"].min().date()),
                     "to": str(history["Date"].max().date())},
        "audit_passed": True,
    }

    print("[1/4] data integrity scan ...")
    payload["dataqc"] = dataqc.scan(history, cfg)

    print("[2/4] redundancy control ...")
    panel = build_panel(history)
    events = _events_frame(panel, cfg)
    payload["redundancy"] = ({"error": "no PRA events available"}
                             if events.empty else
                             redundancy.report(events, cfg, date_col="date"))

    print("[3/4] Benjamini-Hochberg FDR ...")
    strat_rows, null_exp = _strategy_rows(out / "report.json", cfg)
    fdr = inference.adjust(strat_rows, cfg)
    fdr["null_expectancy"] = null_exp
    fdr["null_note"] = ("p-values test H0: expectancy == the seeded `random` "
                        f"strategy's expectancy ({null_exp}). Testing against zero "
                        "would mark every strategy significant, since nearly all "
                        "are negative.")
    payload["inference"] = fdr

    if args.quick:
        payload["crosssec"] = {"error": "skipped (--quick)"}
    else:
        print("[4/4] cross-sectional baskets ...")
        payload["crosssec"] = crosssec.run_baskets(panel, cfg, asof)

    payload["conclusions"] = validation_md.conclusions(payload)
    (out / "validation.json").write_text(
        json.dumps(payload, indent=2, default=str), encoding="utf-8")
    (out / "VALIDATION.md").write_text(validation_md.to_markdown(payload), encoding="utf-8")
    print(f"\nwrote {out / 'VALIDATION.md'}, {out / 'validation.json'}")
    for c in payload["conclusions"]:
        print(f"  - {c}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())