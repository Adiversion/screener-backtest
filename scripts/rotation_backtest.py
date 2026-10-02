#!/usr/bin/env python3
"""The INR 1,000 one-position rotation backtest (gpt6 protocol, Part B).

  python scripts/rotation_backtest.py                       # full history
  python scripts/rotation_backtest.py --start 2026-09-21 --end 2026-09-25
  python scripts/rotation_backtest.py --rolling              # rolling starts
  python scripts/rotation_backtest.py --capital 1000 --outdir reports/rotation
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from protocol import rotation  # noqa: E402
from protocol.config import get, load_config  # noqa: E402
from protocol.data import load_history  # noqa: E402

VERDICT = (
    "This is a single chronological portfolio, not the compounded return of "
    "every winning event. Fees are charged per trade; slippage is included; a "
    "gap through the stop is filled at the open (losses can exceed -7%)."
)


def _cards(m: dict) -> list[tuple[str, object]]:
    return [
        ("Final value", m.get("final_value")), ("Total return", m.get("total_return")),
        ("CAGR", m.get("cagr")), ("Max drawdown", m.get("max_drawdown")),
        ("Trades", m.get("trades")), ("Target-first", m.get("target_first_rate")),
        ("Stop-first", m.get("stop_first_rate")), ("Time exits", m.get("time_exit_rate")),
        ("Net win rate", m.get("net_win_rate")), ("Expectancy", m.get("expectancy")),
        ("Profit factor", m.get("profit_factor")), ("Total fees", m.get("total_fees")),
        ("Time in cash", m.get("time_in_cash")), ("Longest losing streak", m.get("longest_losing_streak")),
        ("Worst trade", m.get("worst_trade")), ("Ambiguous bars", m.get("ambiguous_bars")),
    ]


def _html(res: dict, rolling: pd.DataFrame | None) -> str:
    payload = {"label": res["label"], "start": res["start"], "end": res["end"],
               "initial_capital": res["initial_capital"], "final_cash": res["final_cash"],
               "metrics": res["metrics"], "equity": res["equity"],
               "rolling": rolling.to_dict("records") if rolling is not None else [],
               "verdict": VERDICT}
    blob = json.dumps(payload, default=str)
    return _TEMPLATE.replace("__DATA__", blob)


_TEMPLATE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>INR 1,000 Rotation Backtest</title>
<style>
 body{font:14px/1.5 system-ui,Segoe UI,sans-serif;margin:0;background:#0d1117;color:#e6edf3}
 header{padding:20px 26px;background:#161b22;border-bottom:1px solid #30363d}
 h1{margin:0 0 6px;font-size:22px} h2{margin:24px 0 10px;font-size:17px}
 main{padding:20px 26px;max-width:1150px;margin:auto}
 .cards{display:flex;gap:12px;flex-wrap:wrap;margin:16px 0}
 .card{flex:1 1 150px;background:#161b22;border:1px solid #30363d;border-radius:10px;padding:12px 14px}
 .card .k{color:#8b949e;font-size:12px;text-transform:uppercase}
 .card .v{font-size:19px;font-weight:600;margin-top:4px}
 .warn{padding:9px 13px;border:1px solid #9e6a03;background:#2d2305;color:#d29922;border-radius:8px;margin:12px 0}
 table{border-collapse:collapse;width:100%;margin:8px 0 18px;font-size:13px}
 th,td{border-bottom:1px solid #21262d;padding:7px 9px;text-align:left;white-space:nowrap}
 th{background:#161b22} .num{text-align:right;font-variant-numeric:tabular-nums}
 .pos{color:#3fb950}.neg{color:#f85149}
 svg{background:#161b22;border:1px solid #30363d;border-radius:10px}
</style></head><body>
<header><h1>INR 1,000 One-Position Rotation</h1><div id="sub" class="sub"></div></header>
<main>
 <div class="warn" id="wm"></div>
 <div class="cards" id="cards"></div>
 <h2>Equity curve (cash after each trade)</h2>
 <div id="chart"></div>
 <h2>Rolling-start experiments</h2>
 <div id="roll"></div>
</main>
<script>
const D = __DATA__, m = D.metrics;
const f = v => (v===null||v===undefined)?'-':v;
const col = v => (typeof v==='number'&&v>0)?'pos':((typeof v==='number'&&v<0)?'neg':'');
document.getElementById('sub').textContent = `${D.start} to ${D.end} | start INR ${D.initial_capital} | final INR ${D.final_cash}`;
document.getElementById('wm').textContent = D.verdict;
const cards = [["Final value",m.final_value],["Total return",m.total_return],["CAGR",m.cagr],
 ["Max drawdown",m.max_drawdown],["Trades",m.trades],["Target-first",m.target_first_rate],
 ["Stop-first",m.stop_first_rate],["Time exits",m.time_exit_rate],["Net win rate",m.net_win_rate],
 ["Expectancy",m.expectancy],["Profit factor",m.profit_factor],["Total fees",m.total_fees],
 ["Time in cash",m.time_in_cash],["Losing streak",m.longest_losing_streak]];
document.getElementById('cards').innerHTML = cards.map(c=>
 `<div class="card"><div class="k">${c[0]}</div><div class="v ${col(c[1])}">${f(c[1])}</div></div>`).join('');
(function(){
 const e = D.equity; if(!e.length){document.getElementById('chart').textContent='no trades';return;}
 const vals=[D.initial_capital].concat(e.map(p=>p.cash));
 const lo=Math.min(...vals),hi=Math.max(...vals),W=1060,H=260,P=40;
 const x=i=>P+i*(W-2*P)/Math.max(vals.length-1,1);
 const y=v=>H-P-(v-lo)/Math.max(hi-lo,1e-9)*(H-2*P);
 const pts=vals.map((v,i)=>`${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ');
 const zero=y(D.initial_capital);
 document.getElementById('chart').innerHTML =
  `<svg width="${W}" height="${H}"><line x1="${P}" y1="${zero}" x2="${W-P}" y2="${zero}" stroke="#30363d"/>
   <polyline points="${pts}" fill="none" stroke="#3fb950" stroke-width="2"/>
   <text x="${P}" y="20" fill="#8b949e" font-size="12">${hi}</text>
   <text x="${P}" y="${H-8}" fill="#8b949e" font-size="12">${lo}</text></svg>`;
})();
const r = D.rolling||[];
document.getElementById('roll').innerHTML = r.length
 ? `<table><thead><tr><th>Start</th><th class="num">Trades</th><th class="num">Final</th>
    <th class="num">Return</th><th class="num">CAGR</th><th class="num">MaxDD</th></tr></thead><tbody>`+
   r.map(x=>`<tr><td>${x.start}</td><td class="num">${f(x.trades)}</td><td class="num">${f(x.final_value)}</td>
    <td class="num ${col(x.total_return)}">${f(x.total_return)}</td><td class="num ${col(x.cagr)}">${f(x.cagr)}</td>
    <td class="num">${f(x.max_drawdown)}</td></tr>`).join('')+'</tbody></table>'
 : '<p>Run with --rolling to generate rolling-start experiments.</p>';
</script></body></html>"""


def main() -> int:
    ap = argparse.ArgumentParser(description="INR 1000 rotation backtest")
    ap.add_argument("--config", default=None)
    ap.add_argument("--data", default=str(ROOT / "data" / "universe_history.parquet"))
    ap.add_argument("--start", default=None)
    ap.add_argument("--end", default=None)
    ap.add_argument("--capital", type=float, default=None)
    ap.add_argument("--rolling", action="store_true")
    ap.add_argument("--outdir", default=str(ROOT / "reports" / "rotation"))
    args = ap.parse_args()

    cfg = load_config(args.config)
    end = args.end or get(cfg, "validation.validation_end")
    history = load_history(args.data)
    if end:
        history = history[history["Date"] <= pd.Timestamp(end)]
    if args.start:
        history = history[history["Date"] >= pd.Timestamp(args.start)]
    if history.empty:
        print("no data in window")
        return 1

    res = rotation.run_rotation(cfg, history, capital=args.capital)
    rolling = rotation.rolling_starts(cfg, history, capital=args.capital) if args.rolling else None

    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(res["trades"]).to_csv(out / "rotation_trades.csv", index=False)
    pd.DataFrame(res["equity"]).to_csv(out / "rotation_equity.csv", index=False)
    if rolling is not None:
        rolling.to_csv(out / "rolling_starts.csv", index=False)
    (out / "rotation.json").write_text(
        json.dumps({k: v for k, v in res.items() if k != "trades"} | {
            "n_trades": len(res["trades"])}, indent=2, default=str), encoding="utf-8")
    (out / "ROTATION_BACKTEST.html").write_text(_html(res, rolling), encoding="utf-8")

    m = res["metrics"]
    md = ["# INR 1,000 One-Position Rotation", "",
          f"- window: {res['start']} -> {res['end']}",
          f"- config hash: `{cfg['_hash']}`", f"- candidate rule: `{cfg['rotation']['candidate_tag']}`",
          f"- target {cfg['rotation']['target_fraction']:.0%} / stop "
          f"{cfg['rotation']['stop_fraction']:.0%} / max hold "
          f"{cfg['rotation']['max_holding_sessions']} sessions", "",
          f"> {VERDICT}", "", "## Result", ""]
    md += [f"- **Final value:** INR {m.get('final_value')} "
           f"({m.get('total_return')} total, CAGR {m.get('cagr')})",
           f"- **Max drawdown:** {m.get('max_drawdown')}  |  **longest losing streak:** {m.get('longest_losing_streak')}",
           f"- **Trades:** {m.get('trades')}  |  target-first {m.get('target_first_rate')}  |  "
           f"stop-first {m.get('stop_first_rate')}  |  time exits {m.get('time_exit_rate')}",
           f"- **Net win rate:** {m.get('net_win_rate')}  |  expectancy {m.get('expectancy')}  |  "
           f"profit factor {m.get('profit_factor')}",
           f"- **Costs:** INR {m.get('total_fees')} total fees  |  time in cash {m.get('time_in_cash')}",
           f"- Ambiguous bars (stop & target same bar, stop-first applied): {m.get('ambiguous_bars')}"]
    if rolling is not None and not rolling.empty:
        md += ["", "## Rolling starts", "", rolling.to_markdown(index=False)]
    (out / "ROTATION_BACKTEST.md").write_text("\n".join(md), encoding="utf-8")

    for k, v in _cards(m):
        print(f"  {k:<22} {v}")
    if rolling is not None and not rolling.empty:
        print("\nRolling starts:")
        print(rolling.to_string(index=False))
    print(f"\nwrote {out / 'ROTATION_BACKTEST.html'}, {out / 'ROTATION_BACKTEST.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
