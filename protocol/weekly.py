"""Weekly-timeframe layer: daily OHLCV -> weekly bars -> weekly confluence gates.

Why this exists
---------------
Several of the frameworks in `protocol/frameworks.py` were *designed* on weekly
charts. Stan Weinstein's primary trend filter is the 30-week moving average,
Nicolas Darvas drew his boxes on weekly bars, and O'Neil/CANSLIM reads a weekly
base and then a daily pivot. The production engine evaluates every framework on
daily bars, so a name that is structurally strong week-over-week but simply has
not printed a daily pivot yet is invisible to it. This module is the weekly
view the daily engine is missing.

Point-in-time discipline
------------------------
* A weekly bar is labelled by the LAST ACTUAL TRADING SESSION it contains, not
  by the calendar Friday, so it can be matched against an as-of session the same
  way a daily bar can. (Indian holidays routinely make a week end on a
  Thursday; labelling by Friday would date the bar in the future.)
* Reference levels are shifted by one week, so a breakout must clear a level
  that existed BEFORE the current week printed.
* The in-progress week is dropped by default. A weekly close that has not
  happened yet is not a signal, and treating a half-formed week as a close
  would let a mid-week wick masquerade as a weekly breakout. Pass
  `include_partial=True` to opt in, and the `week_complete` column records
  which bars were affected either way.
* Thresholds are weekly-native. Nothing here reuses a daily cut-off: a "20-day"
  high is a 20-WEEK high here (about 100 sessions), because the horizon, not
  the arithmetic, is what the methodology asks for.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from protocol.github_screeners import ScreenerResult

WEEKS_PER_YEAR = 52

# 52 weekly bars are needed for the 52-week high/low, plus a bar or two of
# slack so the shifted reference levels are populated.
MIN_WEEKLY_BARS = 55

_AGG = {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}

# Every weekly cut-off in one place, so a scan is reproducible and testable.
WEEKLY_PARAMS: dict[str, float] = {
    "ma_short": 10,        # ~50 sessions
    "ma_primary": 30,      # ~150 sessions; Weinstein's own filter
    "ma_long": 40,         # ~200 sessions
    "min_gates": 6,        # of 12, for "weekly strong"
    "rs_min": 75.0,        # cross-sectional weekly momentum percentile
    "prox52_floor": 0.70,  # must sit in the top 30% of its 52-week range
    "rvol13_min": 1.20,    # weekly volume vs the prior 13 weeks
    "rsi_lo": 50.0,        # strong, not yet exhausted
    "rsi_hi": 80.0,
    "range20w_max": 0.35,  # weekly base tightness (a weekly analogue of 18%)
    "range20w_solid": 0.60,  # wider ceiling for the Darvas gate
    "ext_ma30_max": 0.20,  # anti-climax
    "ext_ma30_tight": 0.15,  # tighter anti-chase for the dedicated gate
    # HARD cap, applied outside the gate count. A name more than this far above
    # its 30-week MA is disqualified from "weekly strong" outright, mirroring
    # the daily engine's `quality.max_ext_sma50` cap in scripts/decisions.py.
    # Without it a stock up 100% in 13 weeks clears 9 of 12 gates and grades
    # A+ -- which is the opposite of the quality screen this is for. The
    # `extension` gate alone is not enough, because it is one vote of twelve.
    "max_ext_ma30": 0.20,
    "closing_range_min": 0.65,  # Wyckoff: upper 35% of the week's range
    "up_weeks26_min": 0.55,  # share of rising weeks over ~6 months
    "min_turnover_cr": 0.5,
}

# (gate key, human label). Order is the order the gates are reported in.
WEEKLY_GATES: tuple[tuple[str, str], ...] = (
    ("weinstein", "Weinstein Stage 2 (30w/40w)"),
    ("minervini", "Minervini weekly base"),
    ("rs_leader", "Weekly RS leader"),
    ("darvas", "Darvas weekly box"),
    ("vcp", "Weekly VCP contraction"),
    ("wyckoff", "Wyckoff weekly absorption"),
    ("high52", "52-week high breakout"),
    ("structure", "Weekly trend structure"),
    ("mom_skip", "13-4 weekly momentum"),
    ("rsi_health", "Weekly RSI healthy"),
    ("extension", "Anti-extension (above, not over-stretched from 30w)"),
    ("volume", "Weekly volume confirm"),
)

GATE_KEYS: tuple[str, ...] = tuple(k for k, _ in WEEKLY_GATES)
WEEKLY_GATE_COUNT = len(WEEKLY_GATES)
GRADE_CUTS = (("A+", 9), ("A", 8), ("B", 7), ("C", 6))


def week_end_label(dates: pd.Series) -> pd.Series:
    """Friday of the ISO week containing each date.

    Mon-Fri map to that week's Friday. Sat/Sun belong to the *following* week
    under W-FRI resampling semantics, so they roll forward. NSE equity sessions
    are Mon-Fri, so the Sat/Sun branch is defensive only.
    """
    dow = dates.dt.dayofweek
    offset = np.where(dow < 5, 4 - dow, 11 - dow)
    return dates + pd.to_timedelta(offset, unit="D")


def to_weekly(bars: pd.DataFrame) -> pd.DataFrame:
    """Aggregate daily OHLCV to one row per symbol-week.

    `Date` becomes the last real session in the week; `WeekEnd` is the
    calendar Friday. `week_complete` is False only for a week whose Friday has
    not yet been reached by the data, i.e. the in-progress trailing week.
    """
    b = bars.copy()
    b["Date"] = pd.to_datetime(b["Date"]).dt.normalize()
    b = b.sort_values(["Symbol", "Date"])
    b["_wk"] = week_end_label(b["Date"])
    # pandas agg() can only reduce existing columns, so the per-session count
    # rides along as a constant unit column.
    b["_one"] = 1
    last_session = b["Date"].max()

    out = (b.groupby(["Symbol", "_wk"], sort=True)
             .agg({**_AGG, "Date": "last", "_one": "sum"})
             .reset_index())
    out = out.rename(columns={"_wk": "WeekEnd", "_one": "sessions"})
    out["week_complete"] = out["WeekEnd"] <= last_session
    return (out.sort_values(["Symbol", "Date"]).reset_index(drop=True))


def build_weekly_features(wbars: pd.DataFrame) -> pd.DataFrame:
    """Weekly-native features for one symbol's weekly bars."""
    df = wbars.sort_values("Date").reset_index(drop=True).copy()
    close, high, low, openp = df["Close"], df["High"], df["Low"], df["Open"]
    vol = df["Volume"].astype("float64")

    prev_close = close.shift(1)
    tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()],
                   axis=1).max(axis=1)
    df["w_atr14"] = tr.ewm(alpha=1.0 / 14, adjust=False, min_periods=14).mean()
    df["w_atrpct"] = df["w_atr14"] / close

    # Volume against the PRIOR 13 weeks (~a quarter), current week excluded
    # from its own baseline -- the same shift the daily rvol20 uses.
    df["w_rvol13"] = vol / vol.rolling(13, min_periods=13).mean().shift(1)
    df["w_turnover13"] = (close * vol).rolling(13, min_periods=13).mean()
    # Mean turnover per SESSION over the same 13 weeks (65 sessions), so the
    # liquidity floor means the same thing here as `turnover20` does on the
    # daily side. Without this a weekly mean turnover would read ~5x too high
    # and the floor would be far looser than the daily scan's.
    df["w_turnover13_daily"] = df["w_turnover13"] / 5.0

    # Reference levels, each shifted one week so a breakout clears a level that
    # existed before this week printed.
    df["w_r10"] = high.rolling(10, min_periods=10).max().shift(1)
    df["w_r20"] = high.rolling(20, min_periods=20).max().shift(1)
    df["w_r40"] = high.rolling(40, min_periods=40).max().shift(1)
    df["w_high52"] = high.rolling(WEEKS_PER_YEAR, min_periods=WEEKS_PER_YEAR).max().shift(1)
    df["w_low52"] = low.rolling(WEEKS_PER_YEAR, min_periods=WEEKS_PER_YEAR).min().shift(1)

    df["wma10"] = close.rolling(10, min_periods=10).mean()
    df["wma30"] = close.rolling(30, min_periods=30).mean()
    df["wma40"] = close.rolling(40, min_periods=40).mean()
    df["w_ma30_slope"] = df["wma30"] / df["wma30"].shift(4) - 1.0
    df["w_ext_ma30"] = (close - df["wma30"]) / df["wma30"]
    df["w_stage2"] = (close > df["wma30"]) & (df["wma30"] > df["wma40"])

    df["wret4"] = close / close.shift(4) - 1.0
    df["wret13"] = close / close.shift(13) - 1.0
    df["wret26"] = close / close.shift(26) - 1.0
    df["wret52"] = close / close.shift(52) - 1.0
    # 13-4: skip the most recent month. The academic standard for weekly
    # momentum, because the last few weeks carry short-term reversal.
    df["w_mom_13_4"] = close.shift(4) / close.shift(13) - 1.0
    df["w_rs_raw"] = (0.4 * df["wret52"] + 0.2 * df["wret26"]
                      + 0.2 * df["wret13"] + 0.2 * df["wret4"])

    rng = (high - low)
    df["w_closing_range"] = np.where(rng > 0, (close - low) / rng, np.nan)
    df["w_adr13"] = (rng / close).rolling(13, min_periods=13).mean()
    l10 = low.rolling(10, min_periods=10).min().shift(1)
    l20 = low.rolling(20, min_periods=20).min().shift(1)
    df["w_range10w"] = np.where(close > 0, (df["w_r10"] - l10) / close, np.nan)
    df["w_range20w"] = np.where(close > 0, (df["w_r20"] - l20) / close, np.nan)
    df["w_prox52"] = close / df["w_high52"]
    df["w_up_weeks26"] = (close > close.shift(1)).rolling(26, min_periods=26).mean()

    delta = close.diff()
    avg_gain = delta.clip(lower=0.0).ewm(alpha=1.0 / 14, adjust=False, min_periods=14).mean()
    avg_loss = (-delta).clip(lower=0.0).ewm(alpha=1.0 / 14, adjust=False, min_periods=14).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    df["w_rsi14"] = pd.Series(np.where(avg_loss > 0, 100.0 - 100.0 / (1.0 + rs), 100.0),
                              index=df.index).where(avg_gain.notna(), np.nan)
    return df


def weekly_panel(history: pd.DataFrame, *, asof: pd.Timestamp | str | None = None,
                 include_partial: bool = False) -> dict[str, pd.DataFrame]:
    """Weekly feature panel keyed by symbol, each frame sorted by Date.

    Symbols without `MIN_WEEKLY_BARS` completed weekly bars are dropped, since
    the 52-week high/low simply does not exist for them.
    """
    cutoff = pd.Timestamp(asof).normalize() if asof is not None else None
    weekly = to_weekly(history)
    if cutoff is not None:
        weekly = weekly[weekly["Date"] <= cutoff]
    if not include_partial:
        weekly = weekly[weekly["week_complete"]]

    panel: dict[str, pd.DataFrame] = {}
    for symbol, bars in weekly.groupby("Symbol", sort=False):
        if len(bars) < MIN_WEEKLY_BARS:
            continue
        panel[str(symbol)] = build_weekly_features(bars)
    return panel


def weekly_frame(panel: dict[str, pd.DataFrame], asof: pd.Timestamp | str,
                 *, include_partial: bool = False) -> pd.DataFrame:
    """One cross-sectional row per symbol at `asof`, with `wrs_rating` ranked.

    Mirrors `github_screeners.compute_screener_features`: same as-of session
    filter, same cross-sectional percentile for relative strength.
    """
    cutoff = pd.Timestamp(asof).normalize()
    rows = []
    for symbol, frame in panel.items():
        sub = frame[frame["Date"] <= cutoff]
        if sub.empty:
            continue
        last = sub.iloc[-1]
        if not include_partial and not bool(last.get("week_complete", True)):
            # The most recent completed week is what we score; a partial
            # trailing week is not a weekly close.
            done = sub[sub["week_complete"]] if "week_complete" in sub.columns else sub
            if done.empty:
                continue
            last = done.iloc[-1]
        rows.append({"Symbol": symbol, **last.to_dict()})

    out = pd.DataFrame(rows)
    if not out.empty and "w_rs_raw" in out.columns:
        out["wrs_rating"] = (out["w_rs_raw"].rank(pct=True) * 100).round(1)
    return out


def gate_masks(feat: pd.DataFrame, p: dict[str, float] | None = None) -> dict[str, pd.Series]:
    """The 12 weekly confluence gates as boolean Series over one cross-section."""
    p = {**WEEKLY_PARAMS, **(p or {})}
    close = feat["Close"]
    rs = feat["wrs_rating"] if "wrs_rating" in feat.columns else pd.Series(50.0, index=feat.index)
    return {
        "weinstein": (feat["w_stage2"] & (feat["w_ma30_slope"] > 0)
                      & (close > feat["wma10"])),
        "minervini": (close >= 1.25 * feat["w_low52"])
                     & (feat["w_prox52"] >= p["prox52_floor"])
                     & (feat["w_ext_ma30"] <= p["ext_ma30_max"]),
        "rs_leader": (rs >= p["rs_min"]) & (feat["wret13"] > 0),
        "darvas": (feat["w_range20w"] <= p["range20w_solid"])
                  & (close > feat["w_r20"]) & (feat["w_prox52"] >= 0.80),
        "vcp": (feat["w_range10w"] < feat["w_range20w"] * 0.90) & (close > feat["wma30"]),
        "wyckoff": (feat["w_closing_range"] >= p["closing_range_min"])
                   & (feat["w_rvol13"] >= p["rvol13_min"]),
        "high52": close >= 0.97 * feat["w_high52"],
        "structure": (feat["w_up_weeks26"] >= p["up_weeks26_min"]) & (close > feat["wma40"]),
        "mom_skip": feat["w_mom_13_4"] > 0,
        "rsi_health": feat["w_rsi14"].between(p["rsi_lo"], p["rsi_hi"]),
        "extension": (feat["w_ext_ma30"] > 0) & (feat["w_ext_ma30"] <= p["ext_ma30_tight"]),
        "volume": feat["w_rvol13"] >= p["rvol13_min"],
    }


def weekly_grade(n_gates: int, p: dict[str, float] | None = None) -> str:
    p = {**WEEKLY_PARAMS, **(p or {})}
    for label, cut in GRADE_CUTS:
        if n_gates >= cut:
            return label
    return "WEAK" if n_gates < p["min_gates"] else "C"


def evaluate_weekly(feat: pd.DataFrame, *, top_n: int = 20,
                    p: dict[str, float] | None = None) -> pd.DataFrame:
    """Score every symbol in a weekly cross-section: gate flags, count, grade.

    Returns one row per symbol including the `g_*` gate columns, so a caller can
    see *why* a name passed rather than only how many gates it cleared.
    """
    p = {**WEEKLY_PARAMS, **(p or {})}
    out = feat.copy()
    if out.empty:
        for k in GATE_KEYS:
            out[f"g_{k}"] = pd.Series(dtype=bool)
        for c in ("n_gates", "w_score", "w_grade", "w_strong", "w_extended"):
            out[c] = pd.Series(dtype="float64" if c not in ("w_grade",) else object)
        return out

    liquid = out[out["w_turnover13_daily"] >= p["min_turnover_cr"] * 1e7]
    if not liquid.empty:
        out = liquid

    masks = gate_masks(out, p)
    for key, mask in masks.items():
        out[f"g_{key}"] = mask.fillna(False).astype(bool)
    out["n_gates"] = sum(out[f"g_{k}"].astype(int) for k in GATE_KEYS)
    # Anti-climax cap. Reported as its own column so a reader can see that a
    # high-gate name was dropped for extension rather than for weak structure.
    out["w_extended"] = out["w_ext_ma30"] > p["max_ext_ma30"]
    out["w_strong"] = (out["n_gates"] >= p["min_gates"]) & ~out["w_extended"]
    out["w_grade"] = [weekly_grade(int(n), p) for n in out["n_gates"]]

    rs = out["wrs_rating"] if "wrs_rating" in out.columns else 0.0
    out["w_score"] = (rs * 0.25
                      + np.clip(out["w_rvol13"], 0.0, 3.0) * 8.0
                      + np.clip(out["wret13"], -0.5, 1.0) * 20.0
                      + np.clip(out["wret52"], -1.0, 2.0) * 8.0
                      + np.clip(out["w_prox52"], 0.0, 1.2) * 20.0)
    return out


def screen_weekly(feat: pd.DataFrame, *, top_n: int = 20,
                  p: dict[str, float] | None = None) -> list:
    """Weekly-strong names as `ScreenerResult` rows, best score first.

    The four display fields are aliased onto their weekly meanings so this can
    reuse the daily `_top_results` projection unchanged: rvol20 <- 13-week
    relative volume, ret20 <- 13-week return, adr20 <- 13-week average daily
    range, ext_sma50 <- extension over the 30-week MA.
    """
    p = {**WEEKLY_PARAMS, **(p or {})}
    scored = evaluate_weekly(feat, p=p)
    if scored.empty:
        return []
    passed = scored[scored["w_strong"]].sort_values("w_score", ascending=False).head(top_n)
    return [
        ScreenerResult("WEEKLY_CONFLUENCE", r["Symbol"], r["Close"], r["w_rvol13"],
                       r["wret13"], r["w_adr13"], r["w_ext_ma30"], r["w_score"])
        for _, r in passed.iterrows()
    ]
