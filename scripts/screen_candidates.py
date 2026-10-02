#!/usr/bin/env python3
"""End-of-day rotation screen + interactive dashboard.

  python scripts/screen_candidates.py                      # latest session
  python scripts/screen_candidates.py --asof 2026-09-25 --top 5
  python scripts/screen_candidates.py --symbols CUPID,MARINE,WELSPUNLIV
  python scripts/screen_candidates.py --no-html

Tags every symbol ORGANIC / PENDING / TRAP_RISK / REJECTED / NO_SETUP /
ILLIQUID and names the stock to rotate into. Writes reports/ROTATION.md,
reports/rotation.csv and a self-contained reports/dashboard.html.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from protocol import screen  # noqa: E402
from protocol.config import get, load_config  # noqa: E402
from protocol.data import load_history  # noqa: E402
from protocol.features import build_panel  # noqa: E402

TAG_COLORS = {
    "ORGANIC": "#1a7f37", "PENDING": "#9a6700", "TRAP_RISK": "#b42318",
    "REJECTED": "#8250df", "NO_SETUP": "#57606a", "ILLIQUID": "#8c959f",
}


def _trim(history: pd.DataFrame, lookback: int) -> pd.DataFrame:
    return (history.sort_values("Date").groupby("Symbol", sort=False)
            .tail(lookback).reset_index(drop=True))


def _dashboard(rows: pd.DataFrame, picks: pd.DataFrame, story: list[str],
               report_path: Path) -> str:
    strategies = []
    if report_path.exists():
        data = json.loads(report_path.read_text(encoding="utf-8"))
        for name, per_cap in (data.get("results") or {}).items():
            if "error" in per_cap:
                continue
            run = next(iter(per_cap.values()))
            m, p = run.get("metrics", {}), run.get("portfolio", {})
            strategies.append({
                "strategy": name, "N": m.get("N", 0), "win": m.get("WinRate"),
                "safe": m.get("SafeRate"), "exp": m.get("Expectancy"),
                "pf": m.get("ProfitFactor"), "cagr": p.get("CAGR"),
                "maxdd": p.get("max_dd")})
        strategies.sort(key=lambda r: (r["exp"] is not None, r["exp"]), reverse=True)
    payload = {
        "asof": rows["date"].max() if not rows.empty else None,
        "story": story, "picks": picks.to_dict("records"),
        "rows": rows.sort_values(["tag", "symbol"]).to_dict("records"),
        "strategies": strategies,
    }
    blob = json.dumps(payload, default=str)
    return _HTML.replace("__DATA__", blob)


_HTML = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>NSE Rotation Dashboard</title>
<style>
 body{font:14px/1.5 system-ui,Segoe UI,sans-serif;margin:0;background:#0d1117;color:#e6edf3}
 header{padding:18px 24px;background:#161b22;border-bottom:1px solid #30363d}
 h1{margin:0 0 4px;font-size:20px} .sub{color:#8b949e}
 main{padding:20px 24px;max-width:1200px;margin:auto}
 .call{margin:12px 0 20px;padding:14px 16px;border:1px solid #30363d;border-radius:10px;background:#161b22}
 .call b{color:#3fb950}
 .tag{display:inline-block;padding:2px 8px;border-radius:999px;color:#fff;font-size:12px}
 table{border-collapse:collapse;width:100%;margin:8px 0 26px;font-size:13px}
 th,td{border-bottom:1px solid #21262d;padding:7px 9px;text-align:left}
 th{position:sticky;top:0;background:#161b22;cursor:pointer}
 tr:hover td{background:#161b22}
 input,select{background:#0d1117;color:#e6edf3;border:1px solid #30363d;border-radius:6px;padding:6px 9px}
 .num{text-align:right;font-variant-numeric:tabular-nums}
</style></head><body>
<header><h1>NSE Rotation Dashboard</h1><div class="sub" id="sub"></div></header>
<main>
 <div class="call" id="call"></div>
 <h2>Candidate board</h2>
 <div style="margin-bottom:10px"><input id="q" placeholder="filter symbol..." style="width:220px">
 <select id="tagf"><option value="">all tags</option></select></div>
 <table id="cand"><thead><tr>
  <th data-k="symbol">Symbol</th><th data-k="tag">Tag</th><th data-k="state">State</th>
  <th data-k="close" class="num">Close</th><th data-k="reference" class="num">Ref</th>
  <th data-k="rvol20" class="num">RVOL20</th><th data-k="closing_range" class="num">CloseRange</th>
  <th data-k="retention" class="num">Retention</th><th data-k="penetration" class="num">Penetr.</th>
  <th data-k="stop_proxy" class="num">RiskToRef</th></tr></thead><tbody></tbody></table>
 <h2>Strategy benchmark</h2>
 <table id="strat"><thead><tr><th>Strategy</th><th class="num">N</th><th class="num">WinRate</th>
  <th class="num">SafeRate</th><th class="num">Expectancy</th><th class="num">PF</th>
  <th class="num">CAGR</th><th class="num">MaxDD</th></tr></thead><tbody></tbody></table>
</main>
<script>
const D = __DATA__;
const CO = {ORGANIC:'#1a7f37',PENDING:'#9a6700',TRAP_RISK:'#b42318',REJECTED:'#8250df',NO_SETUP:'#57606a',ILLIQUID:'#8c959f'};
const f = v => (v===null||v===undefined) ? '-' : v;
document.getElementById('sub').textContent = 'Session ' + f(D.asof) + ' | ' +
  (D.picks.length ? 'rotate into ' + D.picks[0].symbol : 'stay in cash');
document.getElementById('call').innerHTML = D.story.map(s=>'<div>'+s+'</div>').join('');
const tags = [...new Set(D.rows.map(r=>r.tag))];
const sel = document.getElementById('tagf');
tags.forEach(t=>{const o=document.createElement('option');o.value=t;o.textContent=t;sel.appendChild(o);});
function renderCand(){
  const q = document.getElementById('q').value.toUpperCase();
  const tf = sel.value;
  document.querySelector('#cand tbody').innerHTML = D.rows
    .filter(r=>(!q||r.symbol.includes(q)) && (!tf||r.tag===tf))
    .map(r=>`<tr><td><b>${r.symbol}</b></td>
      <td><span class="tag" style="background:${CO[r.tag]||'#57606a'}">${r.tag}</span></td>
      <td>${f(r.state)}</td><td class="num">${f(r.close)}</td><td class="num">${f(r.reference)}</td>
      <td class="num">${f(r.rvol20)}</td><td class="num">${f(r.closing_range)}</td>
      <td class="num">${f(r.retention)}</td><td class="num">${f(r.penetration)}</td>
      <td class="num">${f(r.stop_proxy)}</td></tr>`).join('');
}
document.getElementById('q').oninput = renderCand; sel.onchange = renderCand; renderCand();
document.querySelector('#strat tbody').innerHTML = D.strategies.map(s=>`<tr>
  <td>${s.strategy}</td><td class="num">${f(s.N)}</td><td class="num">${f(s.win)}</td>
  <td class="num">${f(s.safe)}</td><td class="num">${f(s.exp)}</td><td class="num">${f(s.pf)}</td>
  <td class="num">${f(s.cagr)}</td><td class="num">${f(s.maxdd)}</td></tr>`).join('');
</script></body></html>"""


def main() -> int:
    ap = argparse.ArgumentParser(description="End-of-day rotation screen")
    ap.add_argument("--config", default=None)
    ap.add_argument("--data", default=str(ROOT / "data" / "universe_history.parquet"))
    ap.add_argument("--asof", default=None)
    ap.add_argument("--lookback", type=int, default=320)
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--symbols", default="all")
    ap.add_argument("--outdir", default=str(ROOT / "reports"))
    ap.add_argument("--no-html", action="store_true")
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

    rows = screen.screen(build_panel(_trim(history, args.lookback)), cfg, asof)
    rows = rows[rows["tag"] != "ILLIQUID"].copy() if not rows.empty else rows
    picks = screen.rank_rotation(rows, cfg, top=args.top)
    lines = screen.story(rows, cfg)

    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)
    rows.sort_values("tag").to_csv(out / "rotation.csv", index=False)
    counts = rows["tag"].value_counts().to_dict() if not rows.empty else {}
    md = ["# Rotation Screen", "", f"- as-of: {asof.date()}",
          f"- tags: {counts}", "", "## Call", ""]
    md += [f"- {ln}" for ln in lines]
    md += ["", "## Shortlist", "",
           picks[["rank", "symbol", "tag", "close", "reference", "rvol20", "retention",
                  "penetration", "stop_proxy"]].to_markdown(index=False)
           if not picks.empty else "_(no ORGANIC candidate)_"]
    (out / "ROTATION.md").write_text("\n".join(md), encoding="utf-8")
    if not args.no_html:
        (out / "dashboard.html").write_text(
            _dashboard(rows, picks, lines, out / "report.json"), encoding="utf-8")

    for ln in lines:
        print(ln)
    if not picks.empty:
        print("\nRotation shortlist:")
        for _, r in picks.iterrows():
            print(f"  {int(r['rank'])}. {r['symbol']:<12} close={r['close']} "
                  f"ref={r['reference']} rvol={r['rvol20']} risk={r['stop_proxy']}")
    print(f"\nwrote {out / 'ROTATION.md'}, {out / 'rotation.csv'}"
          + ("" if args.no_html else f", {out / 'dashboard.html'}"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
