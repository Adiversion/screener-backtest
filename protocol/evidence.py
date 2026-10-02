"""Evidence: what each strategy's rule is, and the history behind it.

The comparison tables answer "which strategy wins?". This module answers the
questions a human actually asks before risking money:

  1. Which strategies exist, and what is each one's rule?
  2. What is the historical evidence for each rule — how many times it fired,
     hit rate, expectancy, and does it beat the random null?

The per-stock "which criteria passed" report lives in `protocol.quality`.
"""
from __future__ import annotations

from typing import Any

from protocol import metrics


# --- historical evidence for a set of trades -------------------------------
def evidence_for(trades: list[dict], cfg: dict, label: str = "") -> dict[str, Any]:
    """Cohort statistics for one strategy's historical occurrences."""
    m = metrics.cohort_metrics(trades, cfg["run"]["target_net"],
                               cfg["run"]["seed"], int(cfg["run"]["bootstrap_n"]))
    ci = m.get("Expectancy_CI") or [None, None]
    return {
        "label": label, "N": m.get("N", 0),
        "win_rate": m.get("WinRate"), "safe_rate": m.get("SafeRate"),
        "tail_breach": m.get("TailBreach"),
        "expectancy": m.get("Expectancy"),
        "expectancy_ci": ci,
        "profit_factor": m.get("ProfitFactor"),
        "p25": m.get("P25"), "p75": m.get("P75"),
        "median_trade": m.get("Expectancy_median"),
        "mean_mae": m.get("MAE_mean"), "mean_mfe": m.get("MFE_mean"),
        "mean_sessions": m.get("Sessions_mean"),
        "beats_null": None,
    }


def compare_to_null(ev: dict[str, Any], null_exp: float | None) -> dict[str, Any]:
    """Honest verdict: a rule only counts if it clears the seeded random null."""
    ev = dict(ev)
    if null_exp is None or ev.get("expectancy") is None:
        ev["beats_null"] = None
        return ev
    better = ev["expectancy"] > null_exp
    ev["beats_null"] = better
    ev["null_expectancy"] = null_exp
    ev["edge_over_null"] = round(ev["expectancy"] - null_exp, 4)
    lo, hi = ev.get("expectancy_ci") or [None, None]
    ev["ci_clears_null"] = None if lo is None else bool(lo > null_exp)
    return ev


STRATEGIES = [
    ("recovered_after_rej", "AAE", "B9",
     "A breakout was rejected (close back under the prior 20-day high), then the "
     "level was reclaimed within 3 sessions. Enter on the reclaim."),
    ("pa_state_a", "PA", "State A",
     "Closed above the prior 20-day high with retention >= 0.60 and closing "
     "range >= 0.50 — the accepted-expansion state."),
    ("pa_state_b", "PA", "State B",
     "Closed above the prior 20-day high but retention or closing range not yet "
     "confirmed — pending acceptance."),
    ("pa_state_c", "PA", "State C",
     "Broke the level intraday, closed slightly below it — rejection, recovery pending."),
    ("pa_state_d", "PA", "State D",
     "Broke the level, surrendered it and closed near the low — failed acceptance "
     "(control: expected to lose)."),
    ("momentum_top", "rank", "B4", "Weekly top-20 by 60-day return."),
    ("high_52w", "rank", "B5", "Weekly top-20 by proximity to the 252-day high."),
    ("vol_breakout", "rank", "B3", "Close above the prior 20-day high with RVOL20 >= 1.5."),
    ("trend", "rank", "B6", "Close > SMA50 > SMA200, 20-day return positive, RSI14 > 50."),
    ("trap", "AAE", "B1",
     "Buys anything already up >= 15% over two sessions. The fear being tested."),
    ("cash", "AAE", "B0", "Never trades. The no-risk reference."),
    ("random", "AAE", "B0 null",
     "Seeded random (stock, session). Anything at or below this row is noise."),
]

CAVEATS = [
    "Prices are adjusted OHLCV only; no delivery % in the main price file.",
    "No price-band / ASM / GSM surveillance lists, no corporate-action calendar, "
    "so trap filters F4/F6/F9/F10 are unavailable and flagged, never zero-filled.",
    "History starts 2018, so the protocol's 2015-2020 discovery window is not covered.",
    "The universe is today's Nifty-500 constituents, so this is a current-constituent "
    "backtest, not a survivorship-controlled historical one.",
    "Event-level results allow many simultaneous trades, so no single-account "
    "CAGR/MaxDD is reported unless trades genuinely do not overlap.",
]


def to_markdown(payload: dict[str, Any]) -> str:
    ev = payload["evidence"]
    u = payload["universe"]
    L = [
        "# Decision trail — which stocks, why, and on what evidence", "",
        f"- As of: **{payload['asof']}**  |  config hash `{payload['config_hash'][:12]}`",
        f"- Universe: {u['symbols']} symbols, {u['sessions']} sessions "
        f"({u['from']} → {u['to']})",
        f"- No-lookahead audit: **{'PASS' if payload['audit_passed'] else 'FAIL'}**",
        "", "## 1. The one-line answer", "", f"**{payload['headline']}**", "",
        "## 2. What you would buy today", "",
    ]
    if payload["today"]:
        L += ["| Rank | Stock | Score | Close | 52w high | ATR% | 120d | RVOL20 | Turnover (20d) | Why |",
              "|---|---|---|---|---|---|---|---|---|---|"]
        for t in payload["today"]:
            L.append(f"| {t['rank']} | **{t['symbol']}** | {t['score']} | {t['close']} | "
                     f"{t.get('prox52')} | {t.get('atrpct')} | "
                     f"{t.get('ret120')} | {t.get('rvol20')} | "
                     f"{round(float(t.get('turnover20') or 0)):,} | {t['reason']} |")
    else:
        L.append("_No stock cleared every hard gate today._")
    L += ["", "## 3. What each name is made of", "",
          "| Component | Weight | Measures | Why it matters |", "|---|---|---|---|"]
    for c in payload["components"]:
        L.append(f"| {c['label']} | {c['weight']} | {c['measures']} | {c['why']} |")
    L += ["", "### Hard gates — a stock must clear all of these to be ranked", "",
          "| Gate | Threshold | Why |", "|---|---|---|"]
    for g in payload["rule_chain"]:
        L.append(f"| {g['criterion']} | `{g['threshold']}` | {g['meaning']} |")
    s = payload.get("sufficiency") or {}
    if s:
        L += ["", f"Excluded for **lack of data**: {s.get('insufficient', 0)} symbols; "
                  f"**partial data** (ranked, flagged THIN): {s.get('thin', 0)}; "
                  f"full data: {s.get('full', 0)}. {s.get('note', '')}"]
    L += ["", "## 4. Strategies in this engine", "",
          "| Strategy | Family | Baseline | Rule |", "|---|---|---|---|"]
    for name, fam, base, rule in payload["strategies"]:
        L.append(f"| `{name}` | {fam} | {base} | {rule} |")
    L += ["", "## 5. The historical evidence behind the rules", "",
          "| Strategy | N | Hit +15% | No stop | Worse than -7% | Avg net/trade | 95% CI | PF | vs null |",
          "|---|---|---|---|---|---|---|---|---|"]
    for e in ev:
        ci = e.get("expectancy_ci") or [None, None]
        cic = f"{ci[0]} to {ci[1]}"
        vs = {True: "**beats**", False: "below null", None: "n/a"}[e.get("beats_null")]
        L.append(f"| `{e['label']}` | {e['N']} | {e['win_rate']} | {e['safe_rate']} | "
                 f"{e['tail_breach']} | {e['expectancy']} | {cic} | "
                 f"{e['profit_factor']} | {vs} |")
    L += ["", "## 6. What this does and does not prove", ""]
    L += [f"- {c}" for c in payload["caveats"]]
    L += ["", "Nothing here is investment advice. Candidates are labelled "
          "`RESEARCH_CANDIDATE`, never \"BUY\"."]
    return "\n".join(L)