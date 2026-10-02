"""Multiple-testing control: Benjamini-Hochberg FDR.

The spec (`chatgpt.txt`, STATISTICAL TESTS) requires that when many hypotheses
are tested, a multiple-testing correction such as Benjamini-Hochberg FDR is
applied, and that the *full search* is reported rather than only the winners.
`config/protocol_v2.yaml` already declared this under `sensitivity:` -- the
requirement was written down and never implemented.

Why this matters concretely: this engine runs 29 strategies and a predeclared
sensitivity grid of 81 threshold combinations. At a nominal 5% level, ~1-2
"significant" results appear purely by chance. The comparison table's headline
-- "recovered_after_rej beats the null" -- was asserted from a raw bootstrap
CI without any correction for the 28 other rules that were also examined.

BH controls the False Discovery Rate: among the rejected hypotheses, the
expected proportion that are genuinely null is <= alpha. That is the right
control here because the question is not "is every rule null?" but "which of
the rules I found are real?" Bonferroni and Holm are also provided for
reference because they are more conservative and sometimes quoted.

P-values come from a normal approximation on the bootstrap statistic. That is
an approximation and is labelled as such; the bootstrap CI remains the primary
interval estimate.
"""
from __future__ import annotations

import math
from typing import Any, Sequence


def normal_p(mean: float, std: float, n: int, null_value: float = 0.0) -> float | None:
    """Two-sided p-value for H0: mean == `null_value`, via a normal approx.

    `null_value` matters enormously. Testing against 0 when every expectancy
    in the study is *negative* answers a question nobody asked and marks all
    28 strategies "significant". The meaningful null here is the seeded
    random strategy's expectancy -- "is this rule better than picking at
    random?", not "is this number non-zero?".
    """
    if n <= 1 or std <= 0:
        return None
    z = (mean - null_value) / (std / math.sqrt(n))
    return math.erfc(abs(z) / math.sqrt(2.0))


def pvalue_of(metrics: dict[str, Any], min_n: int,
              null_value: float = 0.0) -> float | None:
    """p-value for a strategy's cohort expectancy against `null_value`."""
    n = int(metrics.get("N") or 0)
    if n < min_n:
        return None
    return normal_p(float(metrics.get("Expectancy") or 0.0),
                    float(metrics.get("Std") or 0.0), n, null_value)


def benjamini_hochberg(pvalues: Sequence[float | None], alpha: float
                       ) -> tuple[list[float | None], list[bool], list[float | None]]:
    """Standard BH step-up. Returns (sorted thresholds, rejected, q-values).

    `pvalues` may contain None for untestable hypotheses; they are ignored by
    the procedure and come back as None / False in the same positions.
    """
    idx = [i for i, p in enumerate(pvalues) if p is not None]
    m = len(idx)
    thresholds: list[float | None] = [None] * len(pvalues)
    rejected = [False] * len(pvalues)
    qvalues: list[float | None] = [None] * len(pvalues)
    if m == 0:
        return thresholds, rejected, qvalues

    order = sorted(idx, key=lambda i: pvalues[i])          # ascending p
    # step-up: reject up to the largest k with p_(k) <= k/m * alpha
    k_max = 0
    for rank, i in enumerate(order, start=1):
        if pvalues[i] <= (rank / m) * alpha:
            k_max = rank
    for rank, i in enumerate(order, start=1):
        thresholds[i] = round((rank / m) * alpha, 6)
        rejected[i] = rank <= k_max
    # q-values: step-down, monotone, capped at 1
    running = 1.0
    for rank in range(m, 0, -1):
        i = order[rank - 1]
        running = min(running, pvalues[i] * m / rank)
        qvalues[i] = round(min(running, 1.0), 6)
    return thresholds, rejected, qvalues


def bonferroni(pvalues: Sequence[float | None], alpha: float) -> list[bool]:
    """Family-wise error control. More conservative than BH; for reference."""
    m = sum(1 for p in pvalues if p is not None)
    if m == 0:
        return [False] * len(pvalues)
    cut = alpha / m
    return [bool(p is not None and p <= cut) for p in pvalues]


def adjust(rows: list[dict[str, Any]], cfg: dict, alpha: float | None = None
           ) -> dict[str, Any]:
    """Attach FDR control across a list of result rows.

    Each row needs at least `name` and `p`. Rows without a usable p-value are
    carried through as untested rather than silently dropped, because the spec
    requires the FULL search to be reported, not just the winners.
    """
    inf = cfg.get("inference", {})
    a = float(alpha if alpha is not None else inf.get("alpha", 0.05))
    pvals = [r.get("p") for r in rows]
    _, rejected, q = benjamini_hochberg(pvals, a)
    bonf = bonferroni(pvals, a)
    out: list[dict[str, Any]] = []
    for row, rej, qv, bf in zip(rows, rejected, q, bonf):
        rec = dict(row)
        rec["q_value"] = qv
        rec["significant_fdr"] = rej
        rec["significant_bonferroni"] = bf
        rec["untested"] = row.get("p") is None
        out.append(rec)
    tested = [r for r in out if not r["untested"]]
    n_sig = sum(1 for r in tested if r["significant_fdr"])
    return {
        "alpha": a, "tests": len(tested), "untested": len(out) - len(tested),
        "n_significant_fdr": n_sig,
        "n_significant_bonferroni": sum(1 for r in tested if r["significant_bonferroni"]),
        "expected_false_positives": round(a * len(tested), 2),
        "results": out,
        "interpretation": (
            f"{len(tested)} hypotheses tested at FDR alpha={a}. "
            f"{n_sig} survive Benjamini-Hochberg control; roughly "
            f"{a * len(tested):.1f} would be expected to survive by chance alone."
        ),
    }


def to_markdown(payload: dict[str, Any], title: str,
                cols: list[tuple[str, str, int]] | None = None) -> str:
    """Render an `adjust()` payload. `cols` = [(key, header, align), ...]."""
    p = payload
    L = [title, "",
         f"- Hypotheses tested: **{p['tests']}** "
         f"({p['untested']} untestable and carried through unreported)",
         f"- Expected false positives at alpha={p['alpha']}: "
         f"**~{p['expected_false_positives']}**",
         f"- Survive Benjamini-Hochberg FDR: **{p['n_significant_fdr']}**",
         f"- Survive Bonferroni (reference): **{p['n_significant_bonferroni']}**", ""]
    if cols is None:
        cols = [("name", "Strategy", 0), ("N", "N", 1),
                ("expectancy", "Expectancy", 1), ("p", "p", 1),
                ("q_value", "q (BH)", 1), ("significant_fdr", "BH", 0)]
    L.append("| " + " | ".join(h for _, h, _ in cols) + " |")
    L.append("|" + "|".join("---:" if a else ":---" for _, _, a in cols) + "|")
    for r in p["results"]:
        cells = []
        for key, _, _a in cols:
            v = r.get(key)
            if v is None:
                s = "n/a"
            elif isinstance(v, bool):
                s = "**yes**" if v else "no"
            elif isinstance(v, float):
                s = f"{v:.4g}"
            else:
                s = str(v)
            cells.append(s)
        L.append("| " + " | ".join(cells) + " |")
    L += ["", f"_{p['interpretation']}_", ""]
    return "\n".join(L)