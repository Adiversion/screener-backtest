"""Redundancy control: is the proposed signal just repackaged momentum?

The spec (`chatgpt.txt`) has a whole section titled CONTROL FOR REDUNDANCY,
and closes with:

    "The most important principle. Do not try to prove 'our theory works'.
     Try to answer: 'Is there information here that simpler models do not
     already contain?' ... If the answer is no, discard the complexity."

That question was never answered, and it matters more than anything else in
the repo. Every momentum baseline (momentum_top, high_52w, trend,
pra_retention_r252) sits at or below the seeded random null, while exactly
one state-machine outcome -- `recovered_after_rej` -- beats it. When every
simple model dies and one complicated survivor appears, the first thing to
establish is whether the survivor is actually new information.

Three complementary tests, cheapest first:

  1. RANK CORRELATION  - Spearman rho of each proposed feature against the
     simple baselines. |rho| >= `rho_warn` means the two are largely the same
     variable wearing different names. Reported as a matrix plus a flat list
     of offending pairs.

  2. CROSS-SECTIONAL IC - per-date Spearman correlation between each feature
     and the forward outcome, averaged over dates. Reported with the
     IC/t-stat ratio (ICIR). A feature can be uncorrelated with everything
     and still have no predictive value -- that is a separate failure.

  3. INCREMENTAL OLS   - the spec's actual question. Regress the
     cross-sectionally demeaned forward return on the controls (momentum,
     52w proximity, volume, volatility, penetration, market regime), then
     re-add the proposed feature and report the change in R-squared and the
     feature's own t-stat. If the increment is negligible, the spec says to
     discard it as an independent feature.

Everything is cross-sectional and demeaned per date, because that is the only
way to avoid a spurious result from the market moving up on every stock at
once. Outcomes are only ever read forward from the signal date.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

MOMENTUM_BASELINES = ["ret60", "ret120", "prox52", "ret20"]

# Pairs that are algebraically related BY DEFINITION, not empirically:
#   closing_disp = (Close - R)/ATR
#   retention    = (Close - R)/(High - R)
#   penetration  = (High - R)/ATR
#   => closing_disp == retention * penetration, exactly.
# Reporting a high correlation between these as "the feature repackages
# momentum" would be reporting algebra as a research finding. They are
# excluded from the verdict and reported separately as identities.
DEFINITIONAL_PAIRS = {
    frozenset({"retention", "closing_disp"}),
    frozenset({"retention", "penetration"}),
    frozenset({"closing_disp", "penetration"}),
    frozenset({"closing_disp", "atrpct"}),
}


def _is_definitional(a: str, b: str) -> bool:
    return frozenset({a, b}) in DEFINITIONAL_PAIRS


def _rank(a: np.ndarray) -> np.ndarray:
    """Average-rank transform; NaNs preserved as NaN."""
    out = np.full(len(a), np.nan)
    ok = ~np.isnan(a)
    if ok.sum() == 0:
        return out
    order = np.argsort(a[ok])
    ranks = np.empty(ok.sum(), dtype=float)
    ranks[order] = np.arange(1, ok.sum() + 1, dtype=float)
    out[ok] = ranks
    return out


def spearman(x: np.ndarray, y: np.ndarray) -> float:
    """Spearman rho on finite pairs."""
    m = ~np.isnan(x) & ~np.isnan(y)
    if m.sum() < 3:
        return float("nan")
    rx, ry = _rank(x[m]), _rank(y[m])
    sx, sy = rx.std(), ry.std()
    if sx == 0 or sy == 0:
        return float("nan")
    return float(np.mean(((rx - rx.mean()) / sx) * ((ry - ry.mean()) / sy)))


def correlation_matrix(events: pd.DataFrame, features: list[str]) -> pd.DataFrame:
    """Spearman rho between every pair of the given features."""
    cols = [f for f in features if f in events.columns]
    mat = pd.DataFrame(np.eye(len(cols)), index=cols, columns=cols, dtype=float)
    for i, a in enumerate(cols):
        for b in cols[i + 1:]:
            rho = spearman(events[a].to_numpy(float), events[b].to_numpy(float))
            mat.loc[a, b] = mat.loc[b, a] = round(rho, 4) if rho == rho else np.nan
    return mat


def redundant_pairs(events: pd.DataFrame, proposed: list[str],
                    controls: list[str], warn: float
                    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Proposed-vs-control pairs whose rank correlation exceeds `warn`.

    Returns (empirical_pairs, definitional_identities). The second list is
    kept separate so a tautology can never drive the verdict.
    """
    found: list[dict[str, Any]] = []
    taut: list[dict[str, Any]] = []
    for p in proposed:
        for c in controls:
            if p not in events.columns or c not in events.columns:
                continue
            rho = spearman(events[p].to_numpy(float), events[c].to_numpy(float))
            if not (rho == rho) or abs(rho) < warn:
                continue
            rec = {"feature": p, "control": c, "rho": round(rho, 4),
                   "verdict": "REPACKAGED" if abs(rho) >= 0.8 else "CORRELATED"}
            (taut if _is_definitional(p, c) else found).append(rec)
    return (sorted(found, key=lambda r: -abs(r["rho"])),
            sorted(taut, key=lambda r: -abs(r["rho"])))


def ic_series(events: pd.DataFrame, feature: str, outcome: str,
              date_col: str = "date") -> pd.Series:
    """Per-date cross-sectional Spearman IC between feature and outcome."""
    if feature not in events.columns or outcome not in events.columns:
        return pd.Series(dtype=float)
    out: dict[Any, float] = {}
    for date, grp in events.groupby(date_col):
        ic = spearman(grp[feature].to_numpy(float), grp[outcome].to_numpy(float))
        if ic == ic:
            out[date] = ic
    return pd.Series(out, dtype=float)


def ic_report(events: pd.DataFrame, features: list[str], outcome: str,
              date_col: str = "date") -> list[dict[str, Any]]:
    """IC mean, ICIR and t-stat per feature. ICIR = IC_mean / IC_std."""
    out: list[dict[str, Any]] = []
    for f in features:
        ic = ic_series(events, f, outcome, date_col)
        n = int(len(ic))
        if n < 20:
            out.append({"feature": f, "N_dates": n, "ic_mean": None,
                        "icir": None, "t_stat": None,
                        "pct_dates_positive": None})
            continue
        m, s = float(ic.mean()), float(ic.std(ddof=1))
        icir = m / s if s > 0 else None
        out.append({
            "feature": f, "N_dates": n,
            "ic_mean": round(m, 5), "ic_std": round(s, 5),
            "icir": round(icir, 4) if icir is not None else None,
            "t_stat": round(icir * np.sqrt(n), 2) if icir is not None else None,
            "pct_dates_positive": round(float((ic > 0).mean()), 4),
        })
    return out


def _ols(y: np.ndarray, X: np.ndarray) -> tuple[np.ndarray, float]:
    """OLS via least squares; returns (coefficients, R^2).

    Sanitises first: ratio features such as `efficiency` can be +/-inf, and
    a single inf makes `lstsq` raise "SVD did not converge" rather than
    returning a bad fit.
    """
    y = np.nan_to_num(y, nan=0.0, posinf=0.0, neginf=0.0)
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    ss_tot = float(((y - y.mean()) ** 2).sum())
    ss_res = float((resid ** 2).sum())
    r2 = 0.0 if ss_tot <= 0 else 1.0 - ss_res / ss_tot
    return beta, r2


def _demean_by_date(events: pd.DataFrame, cols: list[str], outcome: str,
                    date_col: str = "date") -> pd.DataFrame:
    """Cross-sectionally demean -- kills any common market move."""
    d = events.copy()
    grp = d.groupby(date_col)
    for c in cols + [outcome]:
        if c in d.columns:
            d[c] = d[c] - grp[c].transform("mean")
    return d


def incremental_ols(events: pd.DataFrame, feature: str, controls: list[str],
                    outcome: str, date_col: str = "date") -> dict[str, Any]:
    """Does `feature` add anything once the controls are in the model?"""
    need = [feature, outcome, *controls]
    cols = [c for c in need if c in events.columns]
    if feature not in cols or outcome not in cols or len(controls) < 2:
        return {"feature": feature, "verdict": "INCONCLUSIVE",
                "reason": "required columns missing"}
    usable = events.replace([np.inf, -np.inf], np.nan).dropna(subset=cols)
    usable = usable[np.isfinite(usable[cols].to_numpy(float)).all(axis=1)]
    if len(usable) < 50:
        return {"feature": feature, "verdict": "INCONCLUSIVE",
                "reason": f"only {len(usable)} complete rows"}
    ctrls = [c for c in controls if c in usable.columns and c != feature]
    d = _demean_by_date(usable, cols, outcome, date_col)
    y = d[outcome].to_numpy(float)
    Xc = np.column_stack([np.ones(len(d))] + [d[c].to_numpy(float) for c in ctrls])
    Xf = np.column_stack([Xc, d[feature].to_numpy(float)])
    _, r2_base = _ols(y, Xc)
    beta, r2_full = _ols(y, Xf)
    # t-stat of the added feature
    resid = y - Xf @ beta
    dof = max(len(y) - Xf.shape[1], 1)
    sigma2 = float((resid ** 2).sum()) / dof
    try:
        cov = sigma2 * np.linalg.pinv(Xf.T @ Xf)
        se = float(np.sqrt(cov[-1, -1]))
    except np.linalg.LinAlgError:
        se = float("nan")
    t = float(beta[-1] / se) if se and se == se and se > 0 else None
    incr = r2_full - r2_base
    return {
        "feature": feature, "verdict": "INCREMENTAL" if abs(incr) >= 0.005 else
                                         "NO_INCREMENT",
        "N": int(len(d)), "N_dates": int(d[date_col].nunique()),
        "r2_controls_only": round(r2_base, 5),
        "r2_with_feature": round(r2_full, 5),
        "delta_r2": round(incr, 6),
        "coefficient": round(float(beta[-1]), 6),
        "t_stat": round(t, 2) if t is not None else None,
        "controls": ctrls,
    }


def report(events: pd.DataFrame, cfg: dict, outcome: str | None = None,
            date_col: str = "date") -> dict[str, Any]:
    """Run all three tests and give the single honest verdict."""
    r = cfg["redundancy"]
    outcome = outcome or r["outcome"]
    proposed = list(r["proposed"])
    controls = list(r["controls"])
    seen: list[str] = []
    for f in (*proposed, *controls, *MOMENTUM_BASELINES):
        if f in events.columns and f not in seen:
            seen.append(f)
    features = seen
    if outcome not in events.columns:
        return {"error": f"outcome column `{outcome}` not present in the event table"}
    n = int(len(events))
    matrix = correlation_matrix(events, features)
    pairs, tautologies = redundant_pairs(events, proposed, controls, float(r["rho_warn"]))
    ics = ic_report(events, features, outcome, date_col)
    ols = [incremental_ols(events, f, controls, outcome, date_col) for f in proposed]

    incremental = [o for o in ols if o.get("verdict") == "INCREMENTAL"]
    inconclusive = [o for o in ols if o.get("verdict") == "INCONCLUSIVE"]
    # Verdict logic, in the spec's order of concern. "Not repackaged" is NOT
    # the same as "worth keeping": a feature that is uncorrelated with
    # momentum but explains nothing either is worthless, and the spec says to
    # discard the complexity. Only an actual R2 increment earns INDEPENDENT.
    if n < int(r["min_obs"]):
        verdict = "INCONCLUSIVE"
    elif inconclusive and len(inconclusive) == len(ols):
        verdict = "INCONCLUSIVE"
    elif incremental:
        verdict = "PARTLY INCREMENTAL" if pairs else "INDEPENDENT"
    elif pairs:
        verdict = "REPACKAGED"
    else:
        verdict = "NO_INCREMENTAL_INFORMATION"
    return {
        "N": n, "N_dates": int(events[date_col].nunique()) if date_col in events else 0,
        "outcome": outcome, "verdict": verdict,
        "verdict_meaning": {
            "INDEPENDENT": "proposed features are not repackaged momentum AND add "
                           "information beyond the controls",
            "PARTLY INCREMENTAL": "some proposed features add information; the "
                                  "correlated ones should be dropped",
            "REPACKAGED": "proposed features are largely repackaged momentum",
            "NO_INCREMENTAL_INFORMATION": "proposed features are not repackaged, but "
                                          "they explain nothing the controls do not "
                                          "already explain. The spec says discard the "
                                          "complexity.",
            "INCONCLUSIVE": "not enough observations to conclude",
        }[verdict],
        "rho_warn": float(r["rho_warn"]),
        "matrix": matrix.round(4).to_dict(), "features": features,
        "redundant_pairs": pairs,
        "definitional_identities": tautologies,
        "ic": ics, "ols": ols,
        "n_redundant_pairs": len(pairs),
        "n_definitional": len(tautologies),
        "n_incremental": len(incremental),
        "n_inconclusive": len(inconclusive),
    }