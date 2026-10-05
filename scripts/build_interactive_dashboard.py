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
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from protocol.dashboard_data import build_candidate_data  # noqa: E402
from protocol.dashboard_html import get_dashboard_html, get_paper_trading_html  # noqa: E402
from protocol.data import load_history  # noqa: E402


def make_redirect_html(target_file: str) -> str:
    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta http-equiv="refresh" content="0; url=../{target_file}">
  <script>window.location.replace('../{target_file}' + window.location.search + window.location.hash);</script>
</head>
<body style="background:#0b0f19;"></body>
</html>"""


def make_404_html() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Redirecting • ASTRA QUANT</title>
  <script>
    (function() {
      var path = window.location.pathname.toLowerCase();
      var query = window.location.search || '';
      var hash = window.location.hash || '';
      
      if (path.includes('paper_trading')) {
        window.location.replace('paper_trading.html' + query + hash);
      } else if (path.includes('screener')) {
        window.location.replace('screener.html' + query + hash);
      } else if (path.includes('inspector')) {
        window.location.replace('inspector.html' + query + hash);
      } else if (path.includes('macro')) {
        window.location.replace('macro.html' + query + hash);
      } else if (path.includes('verifier')) {
        window.location.replace('verifier.html' + query + hash);
      } else {
        window.location.replace('index.html' + query + hash);
      }
    })();
  </script>
</head>
<body style="background:#0b0f19;color:#94a3b8;font-family:'JetBrains Mono',monospace,sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;">
  <div style="text-align:center;">
    <div style="font-size:2rem;margin-bottom:12px;color:#38bdf8;">⟁</div>
    <div style="font-size:0.9rem;letter-spacing:0.05em;color:#e2e8f0;">ROUTING TO ASTRA QUANT MODULE...</div>
  </div>
</body>
</html>"""


def build_app(data_path: str, asof_date: str = "2026-10-01", outdir: str = "reports") -> Path:
    """Build and write interactive screener and paper trading station to reports/ and docs/."""
    df = load_history(data_path)
    app_data = build_candidate_data(df, asof_date=asof_date)
    screener_html = get_dashboard_html(app_data)
    paper_html = get_paper_trading_html(app_data)

    out = Path(outdir)
    # relative path -> content. The same set is written to reports/ (the build
    # output) and docs/ (the GitHub Pages root), so the two never drift apart.
    files: list[tuple[Path, str]] = [
        (Path("index.html"), screener_html),
        (Path("interactive_screener.html"), screener_html),
        (Path("screener.html"), screener_html),
        (Path("macro.html"), screener_html),
        (Path("inspector.html"), screener_html),
        (Path("verifier.html"), screener_html),
        (Path("paper_trading.html"), paper_html),
        (Path("404.html"), make_404_html()),
    ]
    # Directory-style clean URL handlers (/screener/, /macro/, ...).
    for section in ("screener", "macro", "inspector", "verifier", "paper_trading"):
        files.append((Path(section) / "index.html", make_redirect_html(f"{section}.html")))

    for root in (out, ROOT / "docs"):
        for rel, content in files:
            target = root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")

    chart_lib = ROOT / "protocol" / "lightweight-charts.standalone.production.js"
    if chart_lib.exists():
        for root in (out, ROOT / "docs"):
            root.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(chart_lib, root / chart_lib.name)

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
