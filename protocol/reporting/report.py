"""Report rendering: Markdown summary, JSON payload and a metrics CSV."""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

WATERMARK = "DEGRADED-DATA RUN: no delivery/surveillance/calendar data, adjusted OHLCV only."

VERDICT_ORDER = {
    "SUPPORTED": "SUPPORTED",
    "PARTIALLY SUPPORTED": "PARTIALLY SUPPORTED",
    "NOT SUPPORTED": "NOT SUPPORTED",
    "INCONCLUSIVE": "INCONCLUSIVE",
}


def verdict(run: dict[str, Any], min_trades: int) -> tuple[str, str]:
    m = run["metrics"]
    if m.get("N", 0) < min_trades:
        return "INCONCLUSIVE", f"only {m.get('N', 0)} validation trades (< {min_trades})"
    return "SEE COMPARISON", "requires baseline CIs (see table)"


def comparison_table(data: dict[str, Any], capital: str = "1000") -> list[dict[str, Any]]:
    rows = []
    for name, per_cap in data["results"].items():
        if "error" in per_cap:
            rows.append({"Strategy": name, "N": 0, "error": per_cap["error"]})
            continue
        key = capital if capital in per_cap else next(iter(per_cap), None)
        m = per_cap.get(key, {}).get("metrics", {})
        p = per_cap.get(key, {}).get("portfolio", {})
        rows.append({
            "Strategy": name, "N": m.get("N", 0), "WinRate": m.get("WinRate"),
            "SafeRate": m.get("SafeRate"), "TailBreach": m.get("TailBreach"),
            "Expectancy": m.get("Expectancy"), "ProfitFactor": m.get("ProfitFactor"),
            "MaxDD": p.get("max_dd"), "CAGR": p.get("CAGR"),
            "TradesPerYear": p.get("trades_per_year"),
        })
    rows.sort(key=lambda r: (r.get("Expectancy") or -9), reverse=True)
    return rows


def _fmt(v: Any) -> str:
    if v is None:
        return "-"
    if isinstance(v, float):
        return f"{v:.4f}"
    return str(v)


def to_markdown(data: dict[str, Any], cfg: dict) -> str:
    lines = [
        "# Screener Backtest — Strategy Comparison",
        "",
        f"> {WATERMARK}",
        "",
        f"- **Config hash:** `{data.get('config_hash')}`  ",
        f"- **Window:** {data['window']}  ",
        f"- **Universe:** {data['universe']['symbols']} symbols, "
        f"{data['universe']['sessions']} sessions "
        f"({data['universe']['from']} → {data['universe']['to']})  ",
        f"- **Benchmark (equal-weight B&H):** "
        f"{_fmt(data['benchmark'].get('mean_return'))}",
        "",
        "## Comparison at capital ₹1000",
        "",
        "| Strategy | N | WinRate | SafeRate | TailBreach | Expectancy | PF | MaxDD | CAGR | Trades/yr |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in comparison_table(data):
        if "error" in r:
            lines.append(f"| {r['Strategy']} | 0 | — error: {r['error']} |")
            continue
        lines.append("| " + " | ".join([
            r["Strategy"], _fmt(r["N"]), _fmt(r["WinRate"]), _fmt(r["SafeRate"]),
            _fmt(r["TailBreach"]), _fmt(r["Expectancy"]), _fmt(r["ProfitFactor"]),
            _fmt(r["MaxDD"]), _fmt(r["CAGR"]), _fmt(r["TradesPerYear"]),
        ]) + " |")
    lines += ["", "## Capital sensitivity (₹1000 / ₹10,000 / ₹1,00,000)", ""]
    lines.append("| Strategy | Capital | N | Expectancy | WinRate | SafeRate |")
    lines.append("|---|---|---|---|---|---|")
    for name, per_cap in data["results"].items():
        if "error" in per_cap:
            continue
        for cap, run in per_cap.items():
            m = run["metrics"]
            lines.append("| " + " | ".join([
                name, cap, _fmt(m.get("N")), _fmt(m.get("Expectancy")),
                _fmt(m.get("WinRate")), _fmt(m.get("SafeRate")),
            ]) + " |")
    lines += ["", "## How to read this", "",
              "- **SafeRate** = fraction of trades that did NOT stop out first (target/time exits).",
              "- **TailBreach** = fraction of trades with a realised net loss worse than −7%.",
              "- **Trap (B1)** is the honest benchmark for the fear: buying stocks already up ≥15%.",
              "- Adjusted OHLCV only; delivery/band/circuit filters are reported as NA, not guessed.",
              ""]
    return "\n".join(lines)


def summary_payload(data: dict[str, Any]) -> dict[str, Any]:
    """The agent-readable payload: metrics only, never per-trade rows."""
    results: dict[str, Any] = {}
    for name, per_cap in data.get("results", {}).items():
        if not isinstance(per_cap, dict) or "error" in per_cap:
            results[name] = {"error": (per_cap or {}).get("error", "error")}
            continue
        results[name] = {
            cap: {"strategy": run.get("strategy"), "capital": run.get("capital"),
                  "metrics": run.get("metrics"), "portfolio": run.get("portfolio"),
                  "n_trades": len(run.get("trades") or [])}
            for cap, run in per_cap.items()
        }
    return {k: v for k, v in data.items() if k != "results"} | {"results": results}


def write_outputs(data: dict[str, Any], cfg: dict, out_dir: str | Path) -> dict[str, str]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    payload = summary_payload(data)
    (out / "report.json").write_text(json.dumps(payload, default=str, indent=2), encoding="utf-8")
    (out / "REPORT.md").write_text(to_markdown(data, cfg), encoding="utf-8")
    from protocol.reporting import report_html
    (out / "REPORT.html").write_text(report_html.render(data), encoding="utf-8")
    rows = comparison_table(data)
    with open(out / "comparison.csv", "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    # per-strategy trade logs (default capital only)
    for name, per_cap in data["results"].items():
        if not isinstance(per_cap, dict) or "error" in per_cap:
            continue
        for cap, run in per_cap.items():
            if run.get("trades"):
                import pandas as pd
                pd.DataFrame(run["trades"]).to_csv(out / f"trades_{name}_{cap}.csv", index=False)
            break
    return {"json": str(out / "report.json"), "md": str(out / "REPORT.md"),
            "html": str(out / "REPORT.html"), "csv": str(out / "comparison.csv")}
