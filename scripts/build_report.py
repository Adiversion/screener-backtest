#!/usr/bin/env python3
"""Rebuild the report bundle (slim JSON + Markdown + HTML) from report.json.

  python scripts/build_report.py                    # uses reports/report.json
  python scripts/build_report.py --report other.json --outdir reports

Useful after a long backtest: re-renders the HTML/Markdown and strips the
per-trade rows out of report.json without re-running the strategies.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from protocol.reporting import report  # noqa: E402
from protocol.config import load_config  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Rebuild the report bundle")
    ap.add_argument("--report", default=str(ROOT / "reports" / "report.json"))
    ap.add_argument("--config", default=None)
    ap.add_argument("--outdir", default=str(ROOT / "reports"))
    args = ap.parse_args()

    src = Path(args.report)
    if not src.exists():
        print(f"missing {src}; run scripts/run_backtest.py first")
        return 1
    data = json.loads(src.read_text(encoding="utf-8"))
    if "results" not in data:
        print("report.json has no 'results' block")
        return 1
    paths = report.write_outputs(data, load_config(args.config), args.outdir)
    print(f"json : {paths['json']}")
    print(f"md   : {paths['md']}")
    print(f"html : {paths['html']}")
    print(f"csv  : {paths['csv']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
