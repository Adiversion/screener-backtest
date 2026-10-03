#!/usr/bin/env python3
"""Build interactive single-page screener web application for GitHub Pages.

Generates reports/index.html and reports/interactive_screener.html with:
1. Live Market Regime status (BULL vs DEFENSIVE) and breadth indicator.
2. Top qualified stocks with interactive capital allocation (fixed Rs. 100,000 per stock).
3. "Why it was picked" expandable technical rationale.
4. Interactive search & sector filters.
5. All 5 screening methodologies (Protocol v2, Minervini, Qullamaggie, CANSLIM, PKScreener).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from protocol.data import load_history  # noqa: E402
from protocol.github_screeners import (  # noqa: E402
    compute_screener_features,
    screen_canslim,
    screen_minervini,
    screen_pkscreener_vcp,
    screen_protocol_v2,
    screen_qullamaggie,
)
from protocol.regime import compute_market_regime, get_regime_at  # noqa: E402
from protocol.sector import get_sector  # noqa: E402


def build_app(data_path: str, asof_date: str = "2026-10-01", outdir: str = "reports") -> Path:
    df = load_history(data_path)
    asof = pd.Timestamp(asof_date)
    reg = get_regime_at(df, asof)
    feat = compute_screener_features(df, asof)

    # Screen all strategies
    p_proto = screen_protocol_v2(feat, top_n=15, min_turnover_cr=1.0)
    p_miner = screen_minervini(feat, top_n=15, min_turnover_cr=1.0)
    p_qulla = screen_qullamaggie(feat, top_n=15, min_turnover_cr=1.0)
    p_cansl = screen_canslim(feat, top_n=15, min_turnover_cr=1.0)
    p_vcp = screen_pkscreener_vcp(feat, top_n=15, min_turnover_cr=1.0)

    groups = [("Protocol Fortified", p_proto), ("Minervini Template", p_miner),
              ("Qullamaggie Breakout", p_qulla), ("CANSLIM Pivot", p_cansl), ("PKScreener VCP", p_vcp)]
    candidates: dict[str, dict] = {}
    for group_name, picks in groups:
        for rank, p in enumerate(picks, 1):
            if p.symbol not in candidates:
                sec = get_sector(p.symbol)
                # Compute recommended stop (invalidation stop or 2x ATR)
                atr = p.adr20 * p.close if hasattr(p, "adr20") else p.close * 0.03
                stop = max(p.close - 2.0 * atr, p.close * 0.92)
                candidates[p.symbol] = {
                    "symbol": p.symbol, "sector": sec, "close": round(p.close, 2),
                    "rvol": round(p.rvol20, 2), "ret20": round(p.ret20 * 100, 1),
                    "adr": round(p.adr20 * 100, 1), "ext50": round(p.ext_sma50 * 100, 1),
                    "stop": round(stop, 2), "stop_pct": round((p.close - stop) / p.close * 100, 1),
                    "strategies": [group_name], "primary_rank": rank,
                    "reason": f"Stage 2 uptrend (Close > SMA50 > SMA200), RVOL {p.rvol20:.1f}x, 20d return {p.ret20*100:+.1f}%, extension {p.ext_sma50*100:+.1f}% within 20% cap."
                }
            else:
                candidates[p.symbol]["strategies"].append(group_name)

    cand_list = sorted(candidates.values(), key=lambda x: (len(x["strategies"]), -x["ret20"]), reverse=True)

    app_data = {
        "asof": str(asof.date()),
        "regime": {
            "name": reg.get("regime", "UNKNOWN"), "action": reg.get("action", "CASH"),
            "index": reg.get("ew_close", 0.0), "sma20": reg.get("sma20", 0.0),
            "breadth": reg.get("pct_above_sma20", 0.0), "message": reg.get("message", "")
        },
        "candidates": cand_list,
        "default_capital_per_stock": 100000,
    }

    html = generate_html(app_data)
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    for p in [out / "index.html", out / "interactive_screener.html", ROOT / "docs" / "index.html"]:
        p.parent.mkdir(parents=True, exist_ok=True); p.write_text(html, encoding="utf-8")
    print(f"Interactive website built -> {out / 'index.html'} and docs/index.html")
    return out / "index.html"


def generate_html(data: dict) -> str:
    json_payload = json.dumps(data)
    return HTML_TEMPLATE.replace("__JSON_PAYLOAD__", json_payload)


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>NSE Quant Screener & Allocation Engine</title>
<style>
  :root { --bg: #090d16; --card: #131b2e; --border: #222f4c; --text: #f0f6fc; --muted: #8b9bb4; --accent: #388bfd; --green: #238636; --green-bg: #0e2a1b; --red: #f85149; --red-bg: #351314; }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif; background: var(--bg); color: var(--text); padding: 20px; line-height: 1.5; }
  .container { max-width: 1240px; margin: 0 auto; }
  header { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 16px; margin-bottom: 24px; border-bottom: 1px solid var(--border); padding-bottom: 16px; }
  h1 { font-size: 1.5rem; font-weight: 700; letter-spacing: -0.02em; }
  .badge { padding: 4px 10px; border-radius: 20px; font-size: 0.75rem; font-weight: 600; text-transform: uppercase; }
  .badge.defensive { background: var(--red-bg); color: var(--red); border: 1px solid var(--red); }
  .badge.bull { background: var(--green-bg); color: var(--green); border: 1px solid var(--green); }
  .regime-banner { background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 16px 20px; margin-bottom: 24px; display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 16px; }
  .regime-stats { display: flex; gap: 24px; } .stat-label { font-size: 0.75rem; color: var(--muted); text-transform: uppercase; } .stat-val { font-size: 1.1rem; font-weight: 700; font-feature-settings: "tnum"; }
  .controls { display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 20px; align-items: center; }
  input[type="text"], select { background: var(--card); border: 1px solid var(--border); color: var(--text); padding: 10px 14px; border-radius: 8px; font-size: 0.9rem; outline: none; }
  .search-box { flex: 1; min-width: 240px; }
  .capital-box { display: flex; align-items: center; gap: 8px; background: var(--card); border: 1px solid var(--border); padding: 6px 12px; border-radius: 8px; font-size: 0.85rem; }
  .capital-box input { width: 110px; background: transparent; border: none; color: #58a6ff; font-weight: 700; font-size: 1rem; outline: none; text-align: right; }
  table { width: 100%; border-collapse: collapse; background: var(--card); border: 1px solid var(--border); border-radius: 10px; overflow: hidden; }
  th, td { padding: 12px 16px; text-align: left; border-bottom: 1px solid var(--border); font-size: 0.88rem; }
  th { background: #16223b; color: var(--muted); font-weight: 600; text-transform: uppercase; font-size: 0.72rem; letter-spacing: 0.05em; }
  td.num { text-align: right; font-feature-settings: "tnum"; font-variant-numeric: tabular-nums; } tr:hover { background: #1a2640; }
  .sym { font-weight: 700; color: #58a6ff; cursor: pointer; text-decoration: underline; text-decoration-color: #58a6ff44; }
  .sector-pill { font-size: 0.75rem; color: var(--muted); background: #0f1626; padding: 2px 8px; border-radius: 4px; }
  .shares-val { font-weight: 700; color: #3fb950; } .strat-tag { display: inline-block; font-size: 0.7rem; padding: 1px 6px; border-radius: 4px; background: #21262d; margin-right: 4px; color: #c9d1d9; }
  .modal { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.7); backdrop-filter: blur(4px); align-items: center; justify-content: center; z-index: 100; }
  .modal.open { display: flex; } .modal-content { background: var(--card); border: 1px solid var(--border); border-radius: 12px; width: 90%; max-width: 580px; padding: 24px; box-shadow: 0 20px 40px rgba(0,0,0,0.5); }
  .modal-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; } .close-btn { cursor: pointer; font-size: 1.5rem; color: var(--muted); }
  .rationale-row { margin-bottom: 12px; font-size: 0.9rem; color: #c9d1d9; }
</style>
</head>
<body>
<div class="container">
  <header>
    <div>
      <h1>NSE Quantitative Screener & Allocation Engine</h1>
      <p style="color:var(--muted);font-size:0.85rem">Active Session: <b id="asofDate"></b> · Built for Next-Day Market Execution</p>
    </div>
    <div id="regimeBadge" class="badge"></div>
  </header>

  <div class="regime-banner">
    <div>
      <div class="stat-label">Market Directive</div>
      <div id="regimeMsg" style="font-weight:600;font-size:0.95rem;margin-top:2px;"></div>
    </div>
    <div class="regime-stats">
      <div><div class="stat-label">Breadth (% > SMA20)</div><div class="stat-val" id="breadthVal"></div></div>
      <div><div class="stat-label">Equal-Weight Index</div><div class="stat-val" id="mktIndexVal"></div></div>
      <div><div class="stat-label">Market 20d SMA</div><div class="stat-val" id="mktSmaVal"></div></div>
    </div>
  </div>

  <div class="controls">
    <input type="text" id="searchBox" class="search-box" placeholder="Search stock or sector... (e.g. JINDALPOLY, Construction, Pharma)"/>
    <select id="sectorFilter"><option value="">All Sectors</option></select>
    <select id="strategyFilter">
      <option value="">All Strategies</option>
      <option value="Protocol Fortified">Protocol Fortified</option>
      <option value="Minervini Template">Minervini Template</option>
      <option value="Qullamaggie Breakout">Qullamaggie Breakout</option>
      <option value="CANSLIM Pivot">CANSLIM Pivot</option>
      <option value="PKScreener VCP">PKScreener VCP</option>
    </select>
    <div class="capital-box">
      <span>Cap / Stock: ₹</span>
      <input type="number" id="capInput" value="100000" step="10000"/>
    </div>
  </div>

  <div style="overflow-x:auto;">
    <table>
      <thead>
        <tr>
          <th>#</th>
          <th>Symbol / Sector</th>
          <th>Matched Frameworks</th>
          <th class="num">Close (₹)</th>
          <th class="num">Stop Loss (₹)</th>
          <th class="num">Shares (₹100k)</th>
          <th class="num">Infusion (₹)</th>
          <th class="num">Max Risk (₹)</th>
          <th class="num">RVOL</th>
          <th class="num">20d Return</th>
        </tr>
      </thead>
      <tbody id="tableBody"></tbody>
    </table>
  </div>
</div>

<div id="infoModal" class="modal">
  <div class="modal-content">
    <div class="modal-header">
      <h2 id="modalSym" style="font-size:1.3rem;"></h2>
      <div class="close-btn" onclick="closeModal()">&times;</div>
    </div>
    <div id="modalBody"></div>
  </div>
</div>

<script>
const D = __JSON_PAYLOAD__;

document.getElementById('asofDate').textContent = D.asof;
const regBadge = document.getElementById('regimeBadge');
regBadge.textContent = D.regime.name + ' (' + D.regime.action + ')';
regBadge.className = 'badge ' + (D.regime.name === 'BULL' ? 'bull' : 'defensive');

document.getElementById('regimeMsg').textContent = D.regime.message;
document.getElementById('breadthVal').textContent = D.regime.breadth + '%';
document.getElementById('mktIndexVal').textContent = D.regime.index;
document.getElementById('mktSmaVal').textContent = D.regime.sma20;

// Populate sector dropdown
const sectors = [...new Set(D.candidates.map(c => c.sector).filter(Boolean))].sort();
const secSel = document.getElementById('sectorFilter');
sectors.forEach(s => { const o = document.createElement('option'); o.value = s; o.textContent = s; secSel.appendChild(o); });

function render() {
  const q = document.getElementById('searchBox').value.trim().toLowerCase();
  const sec = document.getElementById('sectorFilter').value;
  const strat = document.getElementById('strategyFilter').value;
  const cap = parseFloat(document.getElementById('capInput').value) || 100000;

  const filtered = D.candidates.filter(c => {
    const matchesQ = !q || c.symbol.toLowerCase().includes(q) || c.sector.toLowerCase().includes(q);
    const matchesSec = !sec || c.sector === sec;
    const matchesStrat = !strat || c.strategies.includes(strat);
    return matchesQ && matchesSec && matchesStrat;
  });

  const tb = document.getElementById('tableBody');
  tb.innerHTML = filtered.map((c, i) => {
    const shares = Math.floor(cap / c.close);
    const infusion = (shares * c.close).toLocaleString('en-IN', {maximumFractionDigits: 0});
    const risk = (shares * (c.close - c.stop)).toLocaleString('en-IN', {maximumFractionDigits: 0});
    const stratTags = c.strategies.map(s => `<span class="strat-tag">${s}</span>`).join('');
    return `<tr>
      <td>${i + 1}</td>
      <td>
        <span class="sym" onclick="openModal('${c.symbol}')">${c.symbol}</span><br/>
        <span class="sector-pill">${c.sector}</span>
      </td>
      <td>${stratTags}</td>
      <td class="num">₹${c.close.toFixed(2)}</td>
      <td class="num" style="color:var(--red)">₹${c.stop.toFixed(2)} <small>(-${c.stop_pct}%)</small></td>
      <td class="num"><span class="shares-val">${shares}</span></td>
      <td class="num">₹${infusion}</td>
      <td class="num">₹${risk}</td>
      <td class="num">${c.rvol.toFixed(1)}x</td>
      <td class="num" style="color:${c.ret20 >= 0 ? '#3fb950' : '#f85149'}">${c.ret20 >= 0 ? '+' : ''}${c.ret20}%</td>
    </tr>`;
  }).join('');
}

function openModal(sym) {
  const c = D.candidates.find(x => x.symbol === sym);
  if (!c) return;
  document.getElementById('modalSym').textContent = c.symbol + ' — ' + c.sector;
  document.getElementById('modalBody').innerHTML = `
    <div class="rationale-row"><b>Why It Was Picked:</b> ${c.reason}</div>
    <div class="rationale-row"><b>Frameworks:</b> ${c.strategies.join(', ')}</div>
    <div class="rationale-row"><b>50-day SMA Extension:</b> ${c.ext50 > 0 ? '+' : ''}${c.ext50}% (Strict &le;20% Gate Cleared)</div>
    <div class="rationale-row"><b>Relative Volume (RVOL):</b> ${c.rvol}x institutional thrust</div>
    <div class="rationale-row"><b>Average Daily Range (ADR):</b> ${c.adr}% volatility expansion</div>
    <div class="rationale-row"><b>Suggested Trailing Stop:</b> ₹${c.stop} (-${c.stop_pct}% from entry)</div>
  `;
  document.getElementById('infoModal').classList.add('open');
}

function closeModal() {
  document.getElementById('infoModal').classList.remove('open');
}

document.getElementById('searchBox').oninput = render;
document.getElementById('sectorFilter').onchange = render;
document.getElementById('strategyFilter').onchange = render;
document.getElementById('capInput').oninput = render;
render();
</script>
</body>
</html>"""


def main() -> int:
    ap = argparse.ArgumentParser(description="Build Interactive Dashboard")
    ap.add_argument("--data", default=str(ROOT / "data" / "nse_all_history.parquet"))
    ap.add_argument("--asof", default="2026-10-01")
    ap.add_argument("--outdir", default=str(ROOT / "reports"))
    args = ap.parse_args()

    return 0 if build_app(args.data, asof_date=args.asof, outdir=args.outdir) else 1


if __name__ == "__main__":
    sys.exit(main())
