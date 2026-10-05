"""Rendering and conclusion-derivation for the validation milestone.

Kept apart from `scripts/validate.py` so the CLI stays a thin orchestrator and
every source file stays under the 300-line house rule.

The rule that matters here: a verdict must never be kinder than the evidence.
"Not repackaged momentum" is not a pass; if a feature is uncorrelated with
momentum but explains nothing either, the honest conclusion is that it should
be discarded -- which is exactly what the source spec instructs.
"""
from __future__ import annotations

from typing import Any

from protocol import crosssec, dataqc, inference


def _redundancy_md(red: dict[str, Any]) -> list[str]:
    L = ["## 2. Redundancy control — is the signal just repackaged momentum?", ""]
    if red.get("error"):
        return L + [f"_{red['error']}_", ""]
    L += [f"- Events tested: **{red['N']}** across **{red['N_dates']}** dates",
          f"- Verdict: **{red['verdict']}**",
          f"- _What that means:_ {red.get('verdict_meaning', '')}",
          f"- Proposed features adding information beyond the controls: "
          f"**{red['n_incremental']}**",
          f"- Proposed/control pairs with |rho| >= {red['rho_warn']}: "
          f"**{red['n_redundant_pairs']}**", ""]
    if red.get("ols"):
        L += ["### Does each proposed feature survive the controls?", "",
              "| Feature | Verdict | R2 controls only | R2 + feature | dR2 | t |",
              "|---|---|---|---|---|---|"]
        for o in red["ols"]:
            if o.get("verdict") == "INCONCLUSIVE":
                L.append(f"| `{o['feature']}` | INCONCLUSIVE | | | | "
                         f"_{o.get('reason', '')}_ |")
                continue
            L.append(f"| `{o['feature']}` | {o['verdict']} | "
                     f"{o['r2_controls_only']} | {o['r2_with_feature']} | "
                     f"{o['delta_r2']} | {o['t_stat']} |")
        L.append("")
    if red.get("redundant_pairs"):
        L += ["### Repackaged pairs", "",
              "| Proposed | Simple baseline | Spearman rho | Verdict |", "|---|---|---|---|"]
        L += [f"| `{p['feature']}` | `{p['control']}` | {p['rho']} | {p['verdict']} |"
               for p in red["redundant_pairs"][:15]]
        L.append("")
    if red.get("definitional_identities"):
        L += ["### Excluded as definitional identities, not findings", "",
              "These pairs are algebraically related by construction "
              "(`closing_disp == retention x penetration`), so a high correlation "
              "between them is arithmetic, not evidence. They are excluded from "
              "the verdict above.", "", "| A | B | Spearman rho |", "|---|---|---|"]
        L += [f"| `{p['feature']}` | `{p['control']}` | {p['rho']} |"
               for p in red["definitional_identities"][:15]]
        L.append("")
    if red.get("ic"):
        L += ["### Cross-sectional information coefficient vs forward outcome", "",
              "| Feature | Dates | IC mean | ICIR | t | % dates positive |",
              "|---|---|---|---|---|---|"]
        L += [f"| `{i['feature']}` | {i['N_dates']} | {i['ic_mean']} | {i['icir']} | "
              f"{i['t_stat']} | {i['pct_dates_positive']} |" for i in red["ic"]]
        L.append("")
    return L


def _inference_md(inf: dict[str, Any]) -> list[str]:
    L = ["## 3. Multiple-testing control — Benjamini-Hochberg FDR", ""]
    if not inf.get("results"):
        return L + ["_No strategy results available. Run `scripts/run_backtest.py` "
                    "first (this pass consumes `reports/report.json`)._", ""]
    if inf.get("null_note"):
        L += [f"> **The null being tested:** {inf['null_note']}", ""]
    L.append(inference.to_markdown(inf, "", [
        ("name", "Strategy", 0), ("N", "N", 1), ("expectancy", "Expectancy", 1),
        ("p", "p", 1), ("q_value", "q (BH)", 1),
        ("significant_fdr", "BH", 0), ("significant_bonferroni", "Bonferroni", 0)]))
    return L


def to_markdown(v: dict[str, Any]) -> str:
    L = ["# Validation milestone — the four tests the spec demanded", "",
         f"- Generated: config hash `{v['config_hash'][:12]}`",
         f"- Universe: {v['universe']['symbols']} symbols, "
         f"{v['universe']['sessions']} sessions "
         f"({v['universe']['from']} → {v['universe']['to']})",
         f"- No-lookahead audit: **{'PASS' if v['audit_passed'] else 'FAIL'}**",
         "", "---", "",
         dataqc.to_markdown(v["dataqc"]), "---"]
    L += _redundancy_md(v["redundancy"])
    L += ["---"] + _inference_md(v["inference"])
    L += ["---", crosssec.to_markdown(v["crosssec"]), "---",
          "## 5. What this means", ""]
    L += [f"- {x}" for x in v["conclusions"]]
    L += ["", "> These are research results, not investment advice. Candidates "
          "are `HISTORICAL_CANDIDATE`, never \"BUY\".", ""]
    return "\n".join(L)


def conclusions(v: dict[str, Any]) -> list[str]:
    """Plain-English findings. Never softer than the evidence allows."""
    out: list[str] = []
    dq = v["dataqc"]
    if dq["artefact_bars"]:
        out.append(
            f"Data integrity: {dq['artefact_bars']} bars sit on a persistent volume "
            f"level shift, of which {dq['confirmed_split_bars']} match a real split "
            f"ratio; {dq['price_gap_bars']} unadjusted price discontinuities. Any "
            f"shift breaks rvol20 comparability across that date.")
    else:
        out.append("Data integrity: no volume regime shifts or price discontinuities.")

    red = v["redundancy"]
    ols = red.get("ols") or []
    if red.get("error"):
        out.append(f"Redundancy: {red['error']}")
    elif ols and red.get("n_inconclusive") == len(ols):
        out.append("Redundancy: every incremental test was INCONCLUSIVE — no verdict.")
    elif red["verdict"] == "INDEPENDENT":
        out.append(f"Redundancy: the proposed features are neither repackaged momentum "
                   f"nor inert — {red['n_incremental']} add real information.")
    elif red["verdict"] == "REPACKAGED":
        out.append("Redundancy: **the proposed features are largely repackaged "
                   "momentum.** The spec says discard the complexity in that case.")
    elif red["verdict"] == "NO_INCREMENTAL_INFORMATION":
        out.append("Redundancy: **no proposed feature adds information beyond the "
                   "simple momentum/volume controls.** They are not repackaged — they "
                   "are simply not predictive. The spec says discard the complexity.")
    elif red["verdict"] == "PARTLY INCREMENTAL":
        inc = [o["feature"] for o in ols if o.get("verdict") == "INCREMENTAL"]
        out.append(f"Redundancy: only {', '.join(inc) or 'none'} add information "
                   f"beyond the simple baselines; the rest should be dropped.")
    else:
        out.append("Redundancy: too few events to conclude — reported as INCONCLUSIVE.")

    inf = v["inference"]
    if inf.get("results"):
        out.append(f"Multiple testing: {inf['tests']} strategies tested against the "
                   f"seeded random null ({inf.get('null_expectancy')}); "
                   f"{inf['n_significant_fdr']} survive FDR control versus an expected "
                   f"~{inf['expected_false_positives']} false positives.")

    cs = v["crosssec"]
    if not cs.get("error") and cs.get("best"):
        b = cs["best"]
        edge = b.get("vs_universe_mean") or 0.0
        out.append(f"Cross-sectional: the best basket (`{b['score']}` top {b['top']}) "
                   f"beat the equal-weight universe by {edge} per rebalance "
                   f"(gross, before costs). Ranking "
                   f"{'added' if edge > 0 else 'did NOT add'} value.")
    return out