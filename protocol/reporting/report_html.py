"""Self-contained HTML report renderer.

Turns the same payload that drives `REPORT.md` / `report.json` into a single
dynamic HTML file (no server, no CDN): KPI cards, a sortable/filterable
strategy table, an expectancy bar chart and the no-lookahead audit block.
Everything is inline so the file can be opened or shared as-is.
"""
from __future__ import annotations

import json
from typing import Any

WATERMARK = ("DEGRADED-DATA RUN: no delivery/surveillance/calendar data, "
             "adjusted OHLCV only.")


def _caps(data: dict) -> list[str]:
    for per_cap in data.get("results", {}).values():
        if isinstance(per_cap, dict) and "error" not in per_cap:
            return list(per_cap.keys())
    return []


def _row(name: str, per_cap: dict, cap: str) -> dict[str, Any]:
    run = per_cap.get(cap, {}) if isinstance(per_cap, dict) else {}
    m = run.get("metrics", {}) or {}
    p = run.get("portfolio", {}) or {}
    return {
        "strategy": name, "N": m.get("N", 0), "win": m.get("WinRate"),
        "safe": m.get("SafeRate"), "tail": m.get("TailBreach"),
        "exp": m.get("Expectancy"), "pf": m.get("ProfitFactor"),
        "dd": p.get("max_dd"), "cagr": p.get("CAGR"),
        "tpy": p.get("trades_per_year"),
    }


def build_payload(data: dict) -> dict[str, Any]:
    """Compact, JSON-safe view of the run (never includes per-trade rows)."""
    caps = _caps(data)
    cap = caps[0] if caps else "1000"
    rows = []
    for name, per_cap in data.get("results", {}).items():
        if not isinstance(per_cap, dict) or "error" in per_cap:
            rows.append({"strategy": name, "N": 0, "error": str(
                (per_cap or {}).get("error", "error"))})
            continue
        rows.append(_row(name, per_cap, cap))
    rows.sort(key=lambda r: (r.get("exp") is not None, r.get("exp") or -9), reverse=True)
    sensitivity = []
    for name, per_cap in data.get("results", {}).items():
        if not isinstance(per_cap, dict) or "error" in per_cap:
            continue
        for c, run in per_cap.items():
            m = run.get("metrics", {}) or {}
            sensitivity.append({"strategy": name, "capital": c, "N": m.get("N", 0),
                                "exp": m.get("Expectancy"), "win": m.get("WinRate"),
                                "safe": m.get("SafeRate")})
    return {
        "config_hash": data.get("config_hash"), "window": data.get("window"),
        "universe": data.get("universe"), "benchmark": data.get("benchmark"),
        "audit": data.get("audit"), "verdict": data.get("verdict"),
        "mode": data.get("mode"), "data_quality": data.get("data_quality"),
        "capital": cap, "rows": rows, "sensitivity": sensitivity,
        "watermark": WATERMARK,
    }


_HTML = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Screener Backtest Report</title>
<style>
 body{font:14px/1.5 system-ui,Segoe UI,sans-serif;margin:0;background:#0d1117;color:#e6edf3}
 header{padding:20px 26px;background:#161b22;border-bottom:1px solid #30363d}
 h1{margin:0 0 6px;font-size:22px} h2{margin:26px 0 10px;font-size:17px}
 main{padding:20px 26px;max-width:1250px;margin:auto}
 .warn{padding:9px 13px;border:1px solid #9e6a03;background:#2d2305;color:#d29922;border-radius:8px;margin:12px 0}
 .cards{display:flex;gap:12px;flex-wrap:wrap;margin:16px 0}
 .card{flex:1 1 150px;background:#161b22;border:1px solid #30363d;border-radius:10px;padding:12px 14px}
 .card .k{color:#8b949e;font-size:12px;text-transform:uppercase;letter-spacing:.04em}
 .card .v{font-size:20px;font-weight:600;margin-top:4px}
 table{border-collapse:collapse;width:100%;margin:8px 0 18px;font-size:13px}
 th,td{border-bottom:1px solid #21262d;padding:7px 9px;text-align:left;white-space:nowrap}
 th{position:sticky;top:0;background:#161b22;cursor:pointer;user-select:none}
 tr:hover td{background:#161b22}
 .num{text-align:right;font-variant-numeric:tabular-nums}
 .pos{color:#3fb950} .neg{color:#f85149}
 .bar{height:9px;border-radius:4px;background:#30363d;position:relative;min-width:60px}
 .bar>span{position:absolute;top:0;bottom:0;border-radius:4px}
 input,select{background:#0d1117;color:#e6edf3;border:1px solid #30363d;border-radius:6px;padding:6px 9px}
 code{background:#161b22;padding:1px 5px;border-radius:4px}
</style></head><body>
<header><h1>Screener Backtest - Strategy Comparison</h1><div id="sub" class="sub"></div></header>
<main>
 <div class="warn" id="wm"></div>
 <div class="cards" id="cards"></div>
 <h2>Strategy comparison</h2>
 <div style="margin-bottom:10px"><input id="q" placeholder="filter strategy..." style="width:240px">
 <select id="f"><option value="">all</option><option value="pos">expectancy &gt; 0</option>
 <option value="neg">expectancy &lt;= 0</option></select></div>
 <table id="t"><thead><tr>
  <th data-k="strategy">Strategy</th><th data-k="N" class="num">N</th>
  <th class="num">Expectancy</th><th data-k="win" class="num">WinRate</th>
  <th data-k="safe" class="num">SafeRate</th><th data-k="tail" class="num">TailBreach</th>
  <th data-k="pf" class="num">PF</th><th data-k="dd" class="num">MaxDD</th>
  <th data-k="cagr" class="num">CAGR</th></tr></thead><tbody></tbody></table>
 <h2>Capital sensitivity</h2>
 <table id="s"><thead><tr><th>Strategy</th><th>Capital</th><th class="num">N</th>
  <th class="num">Expectancy</th><th class="num">WinRate</th><th class="num">SafeRate</th></tr></thead>
  <tbody></tbody></table>
 <h2>No-lookahead audit</h2><div id="audit"></div>
</main>
<script>
const D = __DATA__;
const f = v => (v===null||v===undefined)?'-':v;
const col = v => (typeof v==='number' && v>0)?'pos':((typeof v==='number'&&v<0)?'neg':'');
document.getElementById('wm').textContent = D.watermark;
const u = D.universe||{}, b = D.benchmark||{};
document.getElementById('sub').textContent =
  `config ${(D.config_hash||'').slice(0,12)} | ${u.symbols||'?'} symbols | ${u.sessions||'?'} sessions | ${u.from||'?'} to ${u.to||'?'}`;
const cards = [['Universe',(u.symbols||0)+' sym'],['Sessions',u.sessions||0],
  ['B&H mean',f(b.mean_return)],['Audit',(D.audit&&D.audit.passed)?'PASS':'FAIL'],
  ['Strategies',D.rows.length]];
document.getElementById('cards').innerHTML = cards.map(c=>
  `<div class="card"><div class="k">${c[0]}</div><div class="v">${c[1]}</div></div>`).join('');
const maxAbs = Math.max(1e-9, ...D.rows.map(r=>Math.abs(r.exp||0)));
function bar(v){const w=Math.abs(v||0)/maxAbs*100;const c=(v||0)>=0?'#3fb950':'#f85149';
  return `<div class="bar"><span style="width:${w}%;background:${c};${(v||0)<0?'right:50%;left:auto':''}"></span></div>`;}
function render(){
  const q=document.getElementById('q').value.toUpperCase();
  const mode=document.getElementById('f').value;
  document.querySelector('#t tbody').innerHTML = D.rows
   .filter(r=>(!q||(r.strategy||'').toUpperCase().includes(q)) &&
     (mode==='' || (mode==='pos'&&(r.exp||0)>0) || (mode==='neg'&&(r.exp||0)<=0)))
   .map(r=>`<tr><td><b>${r.strategy}</b></td><td class="num">${f(r.N)}</td>
     <td class="num ${col(r.exp)}">${f(r.exp)} ${bar(r.exp)}</td>
     <td class="num">${f(r.win)}</td><td class="num">${f(r.safe)}</td>
     <td class="num">${f(r.tail)}</td><td class="num">${f(r.pf)}</td>
     <td class="num">${f(r.dd)}</td><td class="num">${f(r.cagr)}</td></tr>`).join('');
}
document.getElementById('q').oninput=render; document.getElementById('f').onchange=render; render();
document.querySelector('#s tbody').innerHTML = D.sensitivity.map(r=>
  `<tr><td>${r.strategy}</td><td>${r.capital}</td><td class="num">${f(r.N)}</td>
   <td class="num ${col(r.exp)}">${f(r.exp)}</td><td class="num">${f(r.win)}</td>
   <td class="num">${f(r.safe)}</td></tr>`).join('');
const a = D.audit||{};
document.getElementById('audit').innerHTML =
  `<p><b>passed: ${a.passed}</b></p><ul>` + (a.tests||[]).map(t=>
   `<li>${t.test}: ${t.pass?'PASS':'FAIL'} <code>${JSON.stringify(
     Object.fromEntries(Object.entries(t).filter(([k])=>!['test','pass'].includes(k))))}</code></li>`).join('') + '</ul>';
</script></body></html>"""


def render(data: dict) -> str:
    payload = build_payload(data)
    return _HTML.replace("__DATA__", json.dumps(payload, default=str))
