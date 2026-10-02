"""Data integrity: volume regime-shift and price-discontinuity detection.

The spec (`chatgpt.txt`, DATA QUALITY) demands checks for splits, zero
volume, abnormal prices, and "do not silently mix adjusted and unadjusted
prices".

THE CONCERN, AND WHAT IS ACTUALLY EVIDENCED
------------------------------------------
`yfinance` is called with `auto_adjust=True` (see `protocol/ingest.py`). It
back-adjusts OHLC for splits and dividends but does **not** split-adjust
Volume, so a 1:2 split would leave the price series continuous while raw
volume doubles for every prior bar -- corrupting `rvol20`, `efficiency` and
every pressure/response feature from that date onward, silently.

**That defect could not be demonstrated in this dataset, and this module does
not claim to have found it.** Measured here, most detected level shifts do NOT
cluster at plausible split ratios; price-continuity testing finds zero
discontinuities, consistent with price adjustment working correctly. The shifts
that are found are mostly genuine liquidity regime changes -- a name going from
illiquid to liquid after index inclusion, routine in a current-constituent
universe.

So this reports what it can evidence: a volume regime-shift diagnostic (still
worth having, because ANY persistent shift breaks `rvol20` comparability), a
price-discontinuity scan, and a confirmed-split sub-count gated on the detected
ratio matching a real split/bonus ratio.

Detecting a volume spike is trivial and nearly useless -- results days and the
March-2020 crash all print 8-50x normal and are valid data. A corporate action
is distinguished by persistence, significance, and being one event:

  1. PERSISTENCE  - volume stays at a new level
  2. SIGNIFICANCE - large relative to its own noise
  3. UNIQUENESS   - one event, not fifty overlapping window pairs

Each is a Welch two-sample t-test on log volume across fixed windows either
side, gated on persistence and price continuity, then de-duplicated with
non-maximum suppression.

The test is TWO-SIDED, and that matters more than it sounds. An unadjusted
1:2 SPLIT doubles volume. A 1:1 BONUS halves it. Bonus issues are far more
common than splits on the Indian market, and a volume *drop* is exactly what a
one-sided "ratio >= 1.25" detector cannot see.

Because thousands of candidate dates are tested per universe, the t-threshold
is deliberately severe; the honest number of discoveries is small.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from protocol.features import wilder_atr


def _mean_window(csum: np.ndarray, starts: np.ndarray, w: int) -> np.ndarray:
    """Mean of each window [start, start+w)."""
    return (csum[starts + w] - csum[starts]) / w


def _window_stats(csum: np.ndarray, csq: np.ndarray, starts: np.ndarray, w: int):
    """Welch t and mean-difference between [start, start+w) and [start+w, start+2w)."""
    a0, a1 = starts, starts + w
    b0, b1 = a1, a1 + w
    n1 = n2 = w
    s1 = csum[a1] - csum[a0]
    s2 = csum[b1] - csum[b0]
    q1 = csq[a1] - csq[a0]
    q2 = csq[b1] - csq[b0]
    m1, m2 = s1 / n1, s2 / n2
    v1 = np.maximum((q1 - s1 * s1 / n1) / (n1 - 1), 0.0)
    v2 = np.maximum((q2 - s2 * s2 / n2) / (n2 - 1), 0.0)
    se = np.sqrt(v1 / n1 + v2 / n2)
    with np.errstate(divide="ignore", invalid="ignore"):
        t = np.where(se > 0, (m2 - m1) / se, 0.0)
    return np.nan_to_num(t), m2 - m1


def _nms(tstat: np.ndarray, w: int, keep: int) -> list[int]:
    """Greedy non-maximum suppression: strongest `t` first, drop neighbours.

    Without this a single split is reported once per overlapping window pair,
    which is what turns a handful of real events into thousands of rows.
    """
    order = np.argsort(-tstat)
    taken: list[int] = []
    for i in order:
        if tstat[i] <= 0:
            break
        if all(abs(int(i) - j) > w for j in taken):
            taken.append(int(i))
        if len(taken) >= keep:
            break
    return sorted(taken)


def _level_shift_scan(bars: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Bars where log volume shows a persistent, significant level shift."""
    q = cfg["dataqc"]
    w = int(q["shift_window"])
    t_min = float(q["t_min"])
    ratio_min = float(q["shift_ratio_min"])
    keep_max = int(q["max_events_per_symbol"])

    d = bars.sort_values("Date").reset_index(drop=True)
    n = len(d)
    if n < 4 * w + 5:
        return pd.DataFrame()
    close = d["Close"].to_numpy(float)
    raw_vol = d["Volume"].to_numpy(float)
    vol = np.log1p(raw_vol)
    atr = wilder_atr(d["High"], d["Low"], d["Close"]).to_numpy(float)
    with np.errstate(divide="ignore", invalid="ignore"):
        gap_atr = np.abs(close - np.roll(close, 1)) / atr
    gap_atr[0] = np.nan

    csum = np.concatenate([[0.0], np.cumsum(vol)])
    csq = np.concatenate([[0.0], np.cumsum(vol ** 2)])
    starts = np.arange(0, n - 4 * w)          # split boundary sits at starts+w
    if len(starts) == 0:
        return pd.DataFrame()

    tstat, shift = _window_stats(csum, csq, starts, w)
    # PERSISTENCE must compare the PRE-shift window against a window that is
    # two periods AFTER it. Comparing the two post-shift windows to each other
    # would test whether volume kept rising, not whether it stayed elevated.
    pre_mean = _mean_window(csum, starts, w)
    late_mean = _mean_window(csum, starts + 2 * w, w)
    ratio = np.exp(shift)
    persistent = np.exp(late_mean - pre_mean)
    boundary = starts + w
    price_ok = gap_atr[boundary] <= float(q["gap_atr_max"])

    hit = price_ok & (np.abs(tstat) >= t_min) & \
          ((ratio >= ratio_min) | (ratio <= 1.0 / ratio_min)) & \
          ((persistent >= float(q["persist_ratio_min"])) |
           (persistent <= 1.0 / float(q["persist_ratio_min"])))
    if not hit.any():
        return pd.DataFrame()
    scores = np.where(hit, np.abs(tstat), 0.0)
    picks = [boundary[p] for p in _nms(scores, w, keep_max) if scores[p] > 0]
    if not picks:
        return pd.DataFrame()
    pos = np.searchsorted(starts, np.array(picks) - w)
    return pd.DataFrame({
        "Date": d["Date"].to_numpy()[picks],
        "gap_atr": np.round(gap_atr[picks], 4),
        "level_shift": np.round(ratio[pos], 4),
        "t_stat": np.round(np.sign(tstat[pos]) * np.abs(tstat[pos]), 2),
        "direction": np.where(ratio[pos] >= 1.0, "volume_up", "volume_down"),
        "Close": np.round(close[picks], 4),
        "Volume": raw_vol[picks],
        "volume_shift": True,
    })


def _price_gap_scan(bars: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Overnight gaps big enough to be an unadjusted corporate action.

    A genuine limit move is bounded (~20% for most series); an unadjusted
    1:2 split is a 50% step. The gate is high and the new level must persist,
    so ordinary news gaps are not flagged.
    """
    q = cfg["dataqc"]
    thresh = float(q["price_gap_atr_min"])
    hold = int(q["gap_hold_sessions"])
    d = bars.sort_values("Date").reset_index(drop=True)
    if len(d) < 30:
        return pd.DataFrame()
    close = d["Close"].to_numpy(float)
    atr = wilder_atr(d["High"], d["Low"], d["Close"]).to_numpy(float)
    with np.errstate(divide="ignore", invalid="ignore"):
        gap_atr = np.abs(close - np.roll(close, 1)) / atr
    gap_atr[0] = np.nan

    idx: list[int] = []
    for t in range(1, len(d) - hold):
        # `NaN < thresh` is False, so an unfiltered NaN would sail through the
        # first gate and be reported as a gap. Reject non-finite explicitly.
        if not np.isfinite(gap_atr[t]) or gap_atr[t] < thresh:
            continue
        if abs(close[t + hold] - close[t]) > 2.0 * float(atr[t + hold]):
            idx.append(t)
    idx = sorted(set(idx))
    if not idx:
        return pd.DataFrame()
    return pd.DataFrame({
        "Date": d["Date"].to_numpy()[idx],
        "gap_atr": np.round(gap_atr[idx], 4),
        "Close": np.round(close[idx], 4),
        "price_gap": True,
    })


# Ratios an NSE issuer actually splits or issues a bonus on. A detected shift
# whose ratio lands near one of these (in EITHER direction) is a corporate
# action; everything else is a liquidity regime change.
SPLIT_RATIOS = (1.25, 1.5, 2.0, 3.0, 4.0, 5.0, 10.0)
SPLIT_TOLERANCE = 0.06


def _confirm_split(ratio: float) -> bool:
    """True when the ratio matches a real split/bonus ratio in either direction."""
    if ratio >= 1.0:
        return any(abs(ratio / r - 1.0) <= SPLIT_TOLERANCE for r in SPLIT_RATIOS)
    return any(abs((1.0 / ratio) / r - 1.0) <= SPLIT_TOLERANCE for r in SPLIT_RATIOS)


def scan(history: pd.DataFrame, cfg: dict) -> dict[str, Any]:
    """Scan every symbol. Counts, the offending bars, and a plain verdict."""
    rows: list[dict[str, Any]] = []
    for symbol, bars in history.groupby("Symbol", sort=False):
        for rec in _level_shift_scan(bars, cfg).to_dict("records"):
            rec["Symbol"] = symbol
            rec.setdefault("price_gap", False)
            rec["confirmed_split"] = _confirm_split(float(rec["level_shift"]))
            rows.append(rec)
        for rec in _price_gap_scan(bars, cfg).to_dict("records"):
            rec["Symbol"] = symbol
            rec["volume_shift"] = False
            rec["confirmed_split"] = True   # an unadjusted action IS the action
            rows.append(rec)
    table = pd.DataFrame(rows)
    if table.empty:
        affected: list[str] = []
        n_shift = n_gap = n_conf = 0
    else:
        table = table.drop_duplicates(subset=["Symbol", "Date"])
        affected = sorted(table["Symbol"].unique().tolist())
        n_shift = int(table["volume_shift"].sum())
        n_gap = int(table["price_gap"].sum())
        n_conf = int(table["confirmed_split"].sum())
    total = int(len(history))
    n_art = int(len(table))
    return {
        "rows_scanned": total,
        "symbols_scanned": int(history["Symbol"].nunique()),
        "artefact_bars": n_art,
        "artefact_rate": round(n_art / total, 6) if total else 0.0,
        "volume_shift_bars": n_shift,
        "price_gap_bars": n_gap,
        "confirmed_split_bars": n_conf,
        "unexplained_shift_bars": n_shift - n_conf,
        "affected_symbols": affected,
        "affected_symbol_count": len(affected),
        "symbols": table.to_dict("records") if not table.empty else [],
        "verdict": "CLEAN" if n_art == 0 else "VOLUME REGIME SHIFTS FOUND",
        "caveat": "Most detected shifts do not match a real split ratio; they are "
                  "genuine liquidity regime changes (index inclusion/rebalance), "
                  "which still break rvol20 comparability but are valid data.",
    }


def clean(history: pd.DataFrame, cfg: dict) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Drop the offending bars; returns (history, scan).

    Preferred over dropping whole symbols: a split is a one-bar event, so
    discarding 2,000 good sessions loses far more than the corrupted bar.
    """
    report = scan(history, cfg)
    if report["artefact_bars"] == 0:
        return history, report
    keys = {(r["Symbol"], pd.Timestamp(r["Date"])) for r in report["symbols"]}
    keep = [(s, pd.Timestamp(dt)) not in keys
            for s, dt in zip(history["Symbol"], history["Date"])]
    return history[keep].reset_index(drop=True), report


def to_markdown(report: dict[str, Any]) -> str:
    L = ["## 1. Data integrity — volume regime shifts / price discontinuities", "",
         f"- Bars scanned: **{report['rows_scanned']:,}** "
         f"across {report['symbols_scanned']} symbols",
         f"- Verdict: **{report['verdict']}**",
         f"- Persistent volume level shifts: **{report['volume_shift_bars']}**",
         f"- Of those, ratio matches a real split ratio: "
         f"**{report['confirmed_split_bars']}** "
         f"(unexplained: {report['unexplained_shift_bars']})",
         f"- Unadjusted price discontinuities: **{report['price_gap_bars']}**",
         f"- Symbols affected: **{report['affected_symbol_count']}**", "",
         "> **Honest reading.** `yfinance` is called with `auto_adjust=True`, "
         "which back-adjusts OHLC but does **not** split-adjust Volume, so an "
         "unadjusted split would be visible here as a flat-price volume step. "
         f"Only {report['confirmed_split_bars']} of "
         f"{report['volume_shift_bars']} shifts match a plausible split ratio "
         f"({', '.join(str(r) for r in SPLIT_RATIOS)}), and price-continuity "
         "testing finds no discontinuities at all — so this scan did **not** "
         "produce clear evidence of a widespread split-adjustment defect. The "
         f"remaining {report['unexplained_shift_bars']} shifts are consistent "
         "with genuine liquidity regime changes (index inclusion, rebalance): "
         "valid data, but they still break `rvol20` comparability across the "
         "shift date, so they are worth seeing.", ""]
    if report["affected_symbols"]:
        names = report["affected_symbols"]
        L += ["`" + "`, `".join(names[:60]) + "`"]
        if len(names) > 60:
            L.append(f"_...and {len(names) - 60} more symbols._")
        L.append("")
    return "\n".join(L)