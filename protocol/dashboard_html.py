"""HTML template loader for the interactive quant screener dashboard.

Loads protocol/dashboard_template.html and injects the JSON payload.
Kept strictly modular and concise to adhere to the 300-line rule.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

TEMPLATE_FILE = Path(__file__).resolve().parent / "dashboard_template.html"
PAPER_TRADING_TEMPLATE = Path(__file__).resolve().parent / "paper_trading_template.html"

# Fields per candidate that paper_trading.html actually accesses.
# Candles (1500-bar OHLCV + EMAs) are the single biggest contributor to the
# 52 MB file size and are NOT used by the paper trading page — it has no chart.
_PAPER_TRADING_CANDIDATE_FIELDS = {
    "symbol", "company", "sector", "industry", "close", "high", "low",
    "stop", "target_2r", "rvol", "rs_rating", "ret20", "adr",
    "strategies", "is_extended", "framework_count",
    "deliv_pct",
}

# Top-level payload keys that paper_trading.html does not need at all.
_PAPER_TRADING_DROP_KEYS = {
    "forward_verifier",  # heavy multi-symbol verification suite
    "universe_lookup",   # full universe symbol map for inspector search
    "walk_forward",      # walk-forward fold results
    "industry_rankings", # sector momentum matrix
}


def _make_paper_trading_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a lean copy of payload stripping all chart/verifier bulk."""
    slim = {k: v for k, v in payload.items() if k not in _PAPER_TRADING_DROP_KEYS}
    # Strip candles from every candidate — they are the single biggest bloat
    lean_candidates = []
    for cand in slim.get("candidates", []):
        lean = {k: v for k, v in cand.items() if k in _PAPER_TRADING_CANDIDATE_FIELDS}
        lean_candidates.append(lean)
    slim["candidates"] = lean_candidates
    return slim


def get_dashboard_html(payload: dict[str, Any]) -> str:
    """Generate the full HTML document with embedded data payload."""
    clean_payload = {k: v for k, v in payload.items() if not k.startswith("_")}
    template = TEMPLATE_FILE.read_text(encoding="utf-8")
    json_data = json.dumps(clean_payload, ensure_ascii=False)
    return template.replace("__JSON_PAYLOAD__", json_data)


def get_paper_trading_html(payload: dict[str, Any]) -> str:
    """Generate the Paper Trading Station HTML with a lean data payload.

    Strips chart candles and unused heavy fields to keep the file under ~200 KB.
    The screener's 1,500-bar OHLCV arrays are not used by paper_trading.html,
    which has no charts — it only needs symbol metadata, prices, and framework counts.
    """
    template = PAPER_TRADING_TEMPLATE.read_text(encoding="utf-8")
    lean_payload = _make_paper_trading_payload(payload)
    json_data = json.dumps(lean_payload, ensure_ascii=False)
    return template.replace("__JSON_PAYLOAD__", json_data)


