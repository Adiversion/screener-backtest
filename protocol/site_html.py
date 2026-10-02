"""Render the research site as one self-contained HTML file.

No framework, no build step, no CDN: the page has to open from a GitHub Pages
URL on a phone with no server behind it. Everything is vanilla JS against two
JSON files -- `stocks.json` for the universe and `stock/<SYM>.json` for the
gates and recent sessions of whichever stock is actually opened. The styles and
scripts live in `site_assets.py`; this module is the logic around them.

The design follows one rule from the engine itself: a rejection must never be
a dead end. Every stock gets the same treatment -- score, percentile, every
gate with its measured value, every component percentile, and the tape -- so
"No" always arrives with the reason and the numbers attached.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from protocol.site_assets import CSS, JS


def render(payload: dict[str, Any]) -> str:
    """One self-contained HTML file. No CDN, no build step, no server."""
    meta = payload.get("universe", {})
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>NSE stock research — every verdict with its evidence</title>
<style>{CSS}</style>
</head>
<body>
<header><div class="wrap">
  <h1>NSE stock research</h1>
  <div class="sub" id="asof">loading…</div>
  <input id="q" type="search" placeholder="Search any NSE symbol — e.g. CUPID, RELIANCE, MOREPENLAB"
         autocomplete="off" spellcheck="false">
  <div class="tabs">
    <div class="tab on" data-p="list">Candidates</div>
    <div class="tab" data-p="research">The research</div>
    <div class="tab" data-p="caveats">Limits</div>
  </div>
</div></header>
<main class="wrap">
  <section id="list"></section>
  <section id="result" class="hide"></section>
  <section id="stock" class="hide"></section>
  <section id="research" class="hide">
    <h2>What the engine measured about its own rules</h2>
    <div id="evidence"></div>
    <h2>How a stock is scored</h2>
    <div id="comps"></div>
  </section>
  <section id="caveats" class="hide"><div id="caveatsBody"></div></section>
</main>
<footer class="wrap">
  <div><b>{meta.get('symbols', '—')} symbols</b> · session
  <b>{payload.get('asof', '—')}</b> · <b>{payload.get('stats', {}).get('cleared', '—')}</b>
  clear every hard gate · config <code>{payload.get('config_hash', '')[:12]}</code></div>
  <div style="margin-top:6px">Every verdict on this page is a <b>RESEARCH_CANDIDATE</b>
  or a documented rejection. Nothing here is investment advice, and no participant
  identity is inferred anywhere.</div>
</footer>
<script>{JS}</script>
<script>boot();</script>
</body>
</html>"""


def write(outdir, payload: dict[str, Any], tape: dict[str, list[dict]]) -> None:
    """Write index.html, stocks.json and one detail file per symbol.

    `payload["_detail"]` holds the heavy per-symbol rows; they are split out into
    `stock/<SYMBOL>.json` together with that symbol's tape, so the index stays
    small and a visitor only downloads the stock they actually opened.
    """
    out = Path(outdir)
    (out / "stock").mkdir(parents=True, exist_ok=True)
    detail = payload.pop("_detail", {})
    (out / "index.html").write_text(render(payload), encoding="utf-8")
    (out / "stocks.json").write_text(
        json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    for sym, row in detail.items():
        body = {**row, "tape": tape.get(sym, [])}
        (out / "stock" / f"{sym}.json").write_text(
            json.dumps(body, separators=(",", ":")), encoding="utf-8")