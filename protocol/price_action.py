"""Price action candidate board loader for the interactive dashboard.

Loads the raw session breakout candidates, tag distributions (ORGANIC, TRAP_RISK,
PENDING, REJECTED), story narrative, and strategy benchmarks from reports/
or data/ directories.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent


def _sanitize(val: Any) -> Any:
    """Recursively convert float NaNs and Infs to None for valid JSON serialization."""
    if isinstance(val, float):
        if np.isnan(val) or np.isinf(val):
            return None
        return val
    if isinstance(val, dict):
        return {k: _sanitize(v) for k, v in val.items()}
    if isinstance(val, list):
        return [_sanitize(v) for v in val]
    return val


def load_price_action_board() -> dict[str, Any]:
    """Load price action candidate board data with fallback mechanisms."""
    # 1. Try parsing embedded JSON from dashboard.html
    for html_path in (ROOT / "reports" / "dashboard.html", ROOT / "docs" / "dashboard.html"):
        if html_path.exists():
            try:
                text = html_path.read_text(encoding="utf-8")
                m = re.search(r"const D = ({.*?});", text, re.DOTALL)
                if m:
                    data = json.loads(m.group(1))
                    if data.get("picks") or data.get("rows"):
                        return _sanitize(data)
            except Exception:
                pass

    # 2. Fallback: Parse candidates.csv and CANDIDATES.md directly
    picks: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    story: list[str] = []
    asof: str | None = None

    for csv_path in (ROOT / "reports" / "candidates.csv", ROOT / "data" / "candidates.csv"):
        if csv_path.exists():
            try:
                df = pd.read_csv(csv_path)
                if not df.empty:
                    asof = str(df["date"].max())
                    df_clean = df.where(pd.notna(df), None)
                    rows = df_clean.to_dict(orient="records")
                    organic = df[df["tag"] == "ORGANIC"].copy()
                    if not organic.empty:
                        organic = organic.sort_values(
                            by=["retention", "penetration", "rvol20"],
                            ascending=[False, False, False]
                        ).head(5)
                        organic["rank"] = range(1, len(organic) + 1)
                        picks = organic.where(pd.notna(organic), None).to_dict(orient="records")
            except Exception:
                pass
            break

    for md_path in (ROOT / "reports" / "CANDIDATES.md", ROOT / "data" / "CANDIDATES.md"):
        if md_path.exists():
            try:
                for line in md_path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line.startswith("- ") and not line.startswith("- as-of") and not line.startswith("- tags:"):
                        story.append(line[2:])
            except Exception:
                pass
            break

    return _sanitize({
        "asof": asof,
        "story": story,
        "picks": picks,
        "rows": rows,
        "strategies": [],
    })
