"""HTML template loader for the interactive quant screener dashboard.

Loads protocol/dashboard_template.html and injects the JSON payload.
Kept strictly modular and concise to adhere to the 300-line rule.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

TEMPLATE_FILE = Path(__file__).resolve().parent / "dashboard_template.html"
PAPER_TRADING_TEMPLATE = Path(__file__).resolve().parent / "paper_trading_template.html"


def get_dashboard_html(payload: dict[str, Any]) -> str:
    """Generate the full HTML document with embedded data payload."""
    template = TEMPLATE_FILE.read_text(encoding="utf-8")
    json_data = json.dumps(payload, ensure_ascii=False)
    return template.replace("__JSON_PAYLOAD__", json_data)


def get_paper_trading_html(payload: dict[str, Any]) -> str:
    """Generate the full Paper Trading Station HTML with embedded data payload."""
    template = PAPER_TRADING_TEMPLATE.read_text(encoding="utf-8")
    json_data = json.dumps(payload, ensure_ascii=False)
    return template.replace("__JSON_PAYLOAD__", json_data)

