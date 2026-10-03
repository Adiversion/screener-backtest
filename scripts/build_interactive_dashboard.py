#!/usr/bin/env python3
"""Build interactive single-page screener web application for GitHub Pages.

Generates reports/index.html, reports/interactive_screener.html, and docs/index.html with:
1. Live Market Regime status (BULL vs DEFENSIVE) and breadth indicator.
2. Top qualified stocks with interactive capital allocation.
3. "Why it was picked" deep technical rationale matching TECHNICAL_ANALYSIS_AND_DATA_GUIDE.md.
4. Interactive search, sector, strategy, and setup badge filters.
5. All 5 screening methodologies (Protocol v2, Minervini, Qullamaggie, CANSLIM, PKScreener).
6. Forensic case study of JINDALPOLY and NSE data timing guide.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from protocol.dashboard_data import build_candidate_data  # noqa: E402
from protocol.dashboard_html import get_dashboard_html, get_paper_trading_html  # noqa: E402
from protocol.data import load_history  # noqa: E402


def build_app(data_path: str, asof_date: str = "2026-10-01", outdir: str = "reports") -> Path:
    """Build and write interactive screener and paper trading station to reports/ and docs/."""
    df = load_history(data_path)
    app_data = build_candidate_data(df, asof_date=asof_date)
    screener_html = get_dashboard_html(app_data)
    paper_html = get_paper_trading_html(app_data)

    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    target_files = [
        (out / "index.html", screener_html),
        (out / "interactive_screener.html", screener_html),
        (ROOT / "docs" / "index.html", screener_html),
        (out / "paper_trading.html", paper_html),
        (ROOT / "docs" / "paper_trading.html", paper_html),
    ]
    for p, content in target_files:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")

    print(f"Interactive website successfully built -> {out / 'index.html'} and {out / 'paper_trading.html'}")
    return out / "index.html"



def main() -> int:
    ap = argparse.ArgumentParser(description="Build Interactive Dashboard")
    ap.add_argument("--data", default=str(ROOT / "data" / "nse_all_history.parquet"))
    ap.add_argument("--asof", default="2026-10-01")
    ap.add_argument("--outdir", default=str(ROOT / "reports"))
    args = ap.parse_args()

    return 0 if build_app(args.data, asof_date=args.asof, outdir=args.outdir) else 1


if __name__ == "__main__":
    sys.exit(main())
