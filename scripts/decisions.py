#!/usr/bin/env python3
"""Decision trail: which stocks, which criteria, and the history behind them.

  python scripts/decisions.py
  python scripts/decisions.py --top 15 --asof 2026-09-25
  python scripts/decisions.py --symbols CUPID,MARINE,WELSPUNLIV

Writes reports/DECISIONS.md (readable) and reports/decisions.json (agent
readable):

  1. the blended quality score and what each component means,
  2. the hard gates a stock must clear,
  3. today's ranked names with the reason for each,
  4. every strategy in the engine and its rule,
  5. the historical evidence per strategy (cohort size, hit rate, expectancy
     with a 95% CI, and whether it beats the seeded random null).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from protocol import audit, engine, evidence, quality  # noqa: E402
from protocol.config import get, load_config  # noqa: E402
from protocol.data import data_quality_report, load_history  # noqa: E402
from protocol.features import build_panel  # noqa: E402
from protocol.simulator import prepare  # noqa: E402

DEFAULT_SET = ["recovered_after_rej", "pa_state_a", "trap", "random"]


def main() -> int:
    ap = argparse.ArgumentParser(description="Which stocks, which criteria, what evidence")
    ap.add_argument("--config", default=None)
    ap.add_argument("--data", default=str(ROOT / "data" / "universe_history.parquet"))
    ap.add_argument("--asof", default=None)
    ap.add_argument("--capital", type=float, default=1000.0)
    ap.add_argument("--strategies", default=",".join(DEFAULT_SET))
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--symbols", default="all")
    ap.add_argument("--outdir", default=str(ROOT / "reports"))
    args = ap.parse_args()

    cfg = load_config(args.config)
    asof = pd.Timestamp(args.asof or get(cfg, "validation.validation_end"))
    history = load_history(args.data)
    if args.symbols != "all":
        syms = [s.strip().upper() for s in args.symbols.split(",")]
        history = history[history["Symbol"].isin(syms)]
    history = history[history["Date"] <= asof]
    if history.empty:
        print("no data on/before", asof.date())
        return 1

    panel = build_panel(history)

    # ---- 1. today's ranked names -------------------------------------------
    picks = quality.rank(panel, cfg, asof, top=args.top)
    today = []
    for _, r in picks.iterrows():
        item = {k: r[k] for k in (
            "rank", "symbol", "date", "close", "reference", "rvol20", "atrpct",
            "prox52", "efficiency", "ret20", "ret120", "turnover20",
            "penetration", "stop_proxy", "score", "coverage", "data_status",
            "candidates", "edge", "edge_age_days") if k in picks.columns}
        item["reason"] = quality.reason(r, cfg)
        item["gates"] = list(r["gates"])
        today.append(item)

    # ---- 2. historical evidence per strategy -------------------------------
    bars = {s: b.sort_values("Date").reset_index(drop=True)
            for s, b in history.groupby("Symbol")}
    arrays = {s: prepare(b) for s, b in bars.items()}
    names = [s.strip() for s in args.strategies.split(",") if s.strip()]
    ev_rows, null_exp = [], None
    for name in names:
        run = engine.run_strategy(name, panel, bars, cfg, args.capital, (None, None),
                                  None, arrays)
        e = evidence.evidence_for(run["trades"], cfg, label=name)
        if name == "random":
            null_exp = e["expectancy"]
        ev_rows.append(e)
    for e in ev_rows:
        e.update(evidence.compare_to_null(e, null_exp))

    winners = [e for e in ev_rows if e.get("beats_null")]
    if today:
        best = winners[0] if winners else max(
            ev_rows, key=lambda x: x.get("expectancy") or -9)
        headline = (
            f"{today[0]['symbol']} ranks first today (quality score {today[0]['score']}). "
            f"The rule with the best evidence is `{best['label']}`: it has fired "
            f"{best['N']} times historically and averages {best['expectancy']} net per "
            f"trade versus {null_exp} for the seeded random null — "
            f"{'it beats the null' if best.get('beats_null') else 'it does NOT beat the null'}.")
    else:
        headline = ("No stock cleared every hard gate today. That is a real answer: "
                    "the engine is saying there is nothing worth buying right now.")

    components_meta = [{
        "name": field, "label": label, "measures": measures, "why": why,
        "sign": sign, "weight": cfg["quality"]["weights"].get(field),
    } for field, (label, sign, measures, why) in quality.COMPONENTS.items()]
    components_meta.append({
        "name": "edge", "label": "Reclaimed-reference pattern", "sign": 1,
        "measures": "the recovered_after_rej pattern fired recently",
        "why": "the only registered rule that ever beat the random null, but "
               "never independently validated, so the weight is held small",
        "weight": quality.EDGE_WEIGHT,
    })

    payload = {
        "asof": str(asof.date()), "config_hash": cfg["_hash"],
        "universe": {"symbols": int(history["Symbol"].nunique()),
                     "sessions": int(history["Date"].nunique()),
                     "from": str(history["Date"].min().date()),
                     "to": str(history["Date"].max().date())},
        "audit_passed": bool(audit.static_scan()["pass"]),
        "data_quality": data_quality_report(history),
        "headline": headline, "today": today, "components": components_meta,
        "rule_chain": today[0]["gates"] if today else quality.gates(pd.Series(dtype=object), cfg),
        "sufficiency": quality.data_sufficiency_report(panel, cfg, asof),
        "strategies": evidence.STRATEGIES, "evidence": ev_rows,
        "caveats": evidence.CAVEATS,
    }

    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "DECISIONS.md").write_text(evidence.to_markdown(payload), encoding="utf-8")
    (out / "decisions.json").write_text(json.dumps(payload, indent=2, default=str),
                                        encoding="utf-8")

    print(payload["headline"])
    if today:
        print()
        for t in today:
            print(f"  {t['rank']:>2}. {t['symbol']:<12} score={t['score']:.2f}  {t['reason']}")
    print()
    print(f"{'strategy':<24}{'N':>8}{'expectancy':>12}{' 95% CI':>24}{'  vs null':>10}")
    for e in ev_rows:
        ci = e.get("expectancy_ci") or ["", ""]
        print(f"{e['label']:<24}{e['N']:>8}{str(e['expectancy']):>12}"
              f"{str(ci[0]) + ' to ' + str(ci[1]):>24}{str(e.get('beats_null')):>10}")
    print(f"\nwrote {out / 'DECISIONS.md'}, {out / 'decisions.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())