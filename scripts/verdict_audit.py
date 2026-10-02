#!/usr/bin/env python3
"""Does the ranking actually rank? Measure the verdict against the outcome.

    python scripts/verdict_audit.py
    python scripts/verdict_audit.py --session 2026-09-30 --top 30

A single stock that rises after a REJECT proves nothing in either direction --
it is one draw. This scores every symbol on every session, then measures what
actually followed, bucketed three ways:

  1. by score decile  -- the ranking's own claim
  2. by gate verdict  -- the screen's claim, and a much stronger one
  3. by one named session, in full -- how a screen is really used

Writes reports/VERDICT.md, reports/verdict.json and reports/verdict_deciles.csv.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from protocol import verdict  # noqa: E402
from protocol.config import load_config  # noqa: E402
from protocol.data import load_history  # noqa: E402
from protocol.features import build_panel  # noqa: E402

CAVEATS = [
    "Forward returns are outcomes measured after the verdict. Every score was "
    "computed from data through its own session, so nothing leaks backwards.",
    "The gate-clearing group is SMALL and self-selected: those are exactly the "
    "sessions where the engine said 'act'. Read the event count before the "
    "percentage -- a strong-looking rate on a few dozen events is noise.",
    "Survivorship is not controlled: the universe is today's listed NSE cash "
    "equities, so names that were delisted are absent entirely.",
    "The score weights were fitted to 5-day forward returns on this same "
    "sample. A decile table measured on the fitting sample flatters it; the "
    "walk-forward folds in protocol/crosssec.py are the honest comparison.",
]


def main() -> int:
    ap = argparse.ArgumentParser(description="Is the ranking a ranking?")
    ap.add_argument("--config", default=None)
    ap.add_argument("--data", default=str(ROOT / "data" / "nse_all_history.parquet"))
    ap.add_argument("--session", default=None,
                    help="one decision bar to audit in full, e.g. 2026-09-30")
    ap.add_argument("--horizon", type=int, default=20)
    ap.add_argument("--session-horizon", type=int, default=1,
                    help="forward days for the single-session audit; the last "
                         "few sessions have no 20-day outcome yet, so the "
                         "session view defaults to next-day")
    ap.add_argument("--top", type=int, default=25)
    ap.add_argument("--buckets", type=int, default=10)
    ap.add_argument("--outdir", default=str(ROOT / "reports"))
    args = ap.parse_args()

    cfg = load_config(args.config)
    history = load_history(args.data)
    if history.empty:
        print("no data")
        return 1
    print(f"scoring {history['Symbol'].nunique()} symbols over "
          f"{history['Date'].nunique()} sessions …", flush=True)
    panel = build_panel(history)
    df = verdict.build(panel, cfg)

    deciles = verdict.decile_table(df, args.horizon, args.buckets)
    mono = verdict.monotonicity(deciles, args.horizon)
    verdicts = verdict.verdict_table(df, args.horizon)
    session = (verdict.session_audit(df, pd.Timestamp(args.session),
                                      args.session_horizon, args.top)
               if args.session else None)

    passing = verdicts[verdicts["group"].str.startswith("CLEARS")]
    extra = ""
    if not passing.empty and passing.iloc[0].get("events"):
        r = passing.iloc[0]
        extra = (f" Names clearing every gate averaged {r['fwd20']} over "
                 f"{int(r['events'])} events with a {r['win_rate']} win rate.")

    payload = {
        "symbols": int(history["Symbol"].nunique()),
        "events": int(len(df)),
        "from": str(pd.Timestamp(df["date"].min()).date()),
        "to": str(pd.Timestamp(df["date"].max()).date()),
        "horizon": args.horizon,
        "summary": mono["verdict"] + extra,
        "monotonicity": mono,
        "deciles": deciles, "verdicts": verdicts, "session": session,
        "caveats": CAVEATS,
    }

    print("\n" + mono["verdict"] + extra)
    print(f"\n{'decile':<8}{'events':>10}{'score':>9}{'fwd5':>9}{'fwd20':>9}{'vs univ':>10}")
    for _, r in deciles.iterrows():
        print(f"{r.name:<8}{int(r['events']):>10,}{r['score_mean']:>9.4f}"
              f"{r.get('fwd5'):>9.4f}{r.get('fwd20'):>9.4f}{r['excess']:>10.4f}")
    print(f"\n{'group':<24}{'events':>9}{'fwd5':>9}{'fwd20':>9}{'win':>8}{'worst':>9}")
    for _, r in verdicts.iterrows():
        if not r.get("events"):
            print(f"{r['group']:<24}{0:>9}")
            continue
        print(f"{r['group']:<24}{int(r['events']):>9,}{r['fwd5']:>9.4f}"
              f"{r['fwd20']:>9.4f}{r['win_rate']:>8.3f}{r['mae_mean']:>9.4f}")
    if session is not None and not session.empty:
        print(f"\nsession {pd.Timestamp(args.session).date()}, "
              f"+{args.session_horizon}d outcome — top {len(session)} by score:")
        print(session.head(args.top).to_string(index=False))

    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "VERDICT.md").write_text(verdict.to_markdown(payload), encoding="utf-8")
    deciles.to_csv(out / "verdict_deciles.csv")
    serial = {k: (v.to_dict("records") if isinstance(v, pd.DataFrame)
                  else v) for k, v in payload.items() if k != "session"}
    (out / "verdict.json").write_text(json.dumps(serial, indent=2, default=str),
                                      encoding="utf-8")
    print(f"\nwrote {out / 'VERDICT.md'}, {out / 'verdict.json'}, "
          f"{out / 'verdict_deciles.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())