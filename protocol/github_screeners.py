"""Codified GitHub momentum screeners for comparative benchmarking.

Independent implementations of prominent open-source momentum frameworks,
each reduced to a single boolean gate plus a ranking score:

1.  Relative Strength Leader (O'Neil / Mansfield RS)
2.  Minervini Trend Template (SEPA)
3.  Qullamaggie Breakout & High Tight Flag
4.  CANSLIM Pivot Breakout (O'Neil)
5.  PKScreener Volatility Contraction Pattern
6.  Protocol v2 Fortified (regime-gated house engine)
7.  Stan Weinstein Stage 2 Base Breakout
8.  Turtle Trading Donchian Breakout
9.  Darvas Box Theory
10. Wyckoff Closing Range Absorption
11. Sector Momentum Leader (industry tailwind)
12. Connors RSI Mean-Reversion Pullback
13. Institutional Demat Delivery Absorption

Every screener follows the same shape: slice to the liquid universe, build a
boolean mask, score the survivors, then project the top-N into `ScreenerResult`
rows. `_liquid_universe` and `_top_results` hold the two halves that never
change, so each screener below is only its own gate and its own score.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class ScreenerResult:
    screener_name: str
    symbol: str
    close: float
    rvol20: float
    ret20: float
    adr20: float
    ext_sma50: float
    score: float


def _liquid_universe(df: pd.DataFrame, min_turnover_cr: float) -> pd.DataFrame:
    """Liquid slice: names whose 20-session turnover clears the floor.

    `min_turnover_cr` is in INR crore; `turnover20` is stored in rupees.
    """
    return df[df["turnover20"] >= min_turnover_cr * 1e7].copy()


def _top_results(name: str, passed: pd.DataFrame, top_n: int) -> list[ScreenerResult]:
    """Rank a screened frame by `score` and project the top-N into results."""
    ranked = passed.sort_values("score", ascending=False).head(top_n)
    return [
        ScreenerResult(name, r["Symbol"], r["Close"], r["rvol20"],
                       r["ret20"], r["adr20"], r["ext_sma50"], r["score"])
        for _, r in ranked.iterrows()
    ]


def compute_screener_features(sub_history: pd.DataFrame,
                              asof_date: pd.Timestamp | str) -> pd.DataFrame:
    """Compute point-in-time technical indicators for every active symbol."""
    asof = pd.Timestamp(asof_date).normalize()
    dated = sub_history.assign(_date=pd.to_datetime(sub_history["Date"]).dt.normalize())
    filtered = dated[dated["_date"] <= asof]
    active_symbols = set(filtered.loc[filtered["_date"] == asof, "Symbol"])

    records = []
    for sym, group in filtered[filtered["Symbol"].isin(active_symbols)].groupby("Symbol"):
        if len(group) < 200:
            continue

        c = group["Close"].to_numpy()
        o = group["Open"].to_numpy()
        h = group["High"].to_numpy()
        l = group["Low"].to_numpy()
        v = group["Volume"].to_numpy()

        close_now = c[-1]
        sma50 = float(np.mean(c[-50:]))
        sma150 = float(np.mean(c[-150:]))
        sma200 = float(np.mean(c[-200:]))
        sma200_1m = float(np.mean(c[-222:-22])) if len(c) >= 222 else sma200

        s_c = pd.Series(c)
        ema10 = float(s_c.ewm(span=10, adjust=False).mean().iloc[-1])
        ema20 = float(s_c.ewm(span=20, adjust=False).mean().iloc[-1])

        # Adaptive volume baseline: mean and median resist outlier spikes.
        vol_mean20 = float(np.mean(v[-21:-1])) if len(v) >= 21 else float(np.mean(v))
        vol_med20 = float(np.median(v[-21:-1])) if len(v) >= 21 else vol_mean20
        vol_mean50 = float(np.mean(v[-51:-1])) if len(v) >= 51 else vol_mean20
        rvol20_mean = float(v[-1] / vol_mean20) if vol_mean20 > 0 else 0.0
        rvol20_med = float(v[-1] / vol_med20) if vol_med20 > 0 else 0.0
        rvol20 = max(rvol20_mean, rvol20_med)
        rvol50 = float(v[-1] / vol_mean50) if vol_mean50 > 0 else 0.0

        r10 = float(np.max(h[-11:-1])) if len(h) >= 11 else float(h[-1])
        r20 = float(np.max(h[-21:-1])) if len(h) >= 21 else float(h[-1])
        r60 = float(np.max(h[-61:-1])) if len(h) >= 61 else float(h[-1])
        l20 = float(np.min(l[-21:-1])) if len(l) >= 21 else float(l[-1])
        l60 = float(np.min(l[-61:-1])) if len(l) >= 61 else float(l[-1])
        h52 = float(np.max(h[-253:-1])) if len(h) >= 253 else float(np.max(h[:-1]))
        l52 = float(np.min(l[-253:-1])) if len(l) >= 253 else float(np.min(l[:-1]))

        adr20 = float(np.mean((h[-20:] - l[-20:]) / c[-20:]))
        turnover20 = float(np.mean(c[-20:] * v[-20:]))
        ret20 = float(c[-1] / c[-21] - 1.0) if len(c) >= 21 else 0.0
        ret60 = float(c[-1] / c[-61] - 1.0) if len(c) >= 61 else 0.0
        ret120 = float(c[-1] / c[-121] - 1.0) if len(c) >= 121 else ret60
        ret252 = float(c[-1] / c[-253] - 1.0) if len(c) >= 253 else ret120
        rs_raw = 0.4 * ret252 + 0.2 * ret120 + 0.2 * ret60 + 0.2 * ret20

        # Volume dry-up over the prior three sessions vs the 20-day average.
        pre_vol_min = (float(np.min(v[-4:-1]) / vol_mean20)
                       if len(v) >= 4 and vol_mean20 > 0 else 1.0)
        range20 = float((r20 - l20) / close_now)
        range60 = float((r60 - l60) / close_now)

        # Multi-touch resistance shelf: prior 20 sessions within 0.75 ATR of R20.
        atr_est = max(adr20 * close_now, 0.01)
        prior_h20 = h[-21:-1] if len(h) >= 21 else h[:-1]
        shelf_band_lo = r20 - 0.75 * atr_est
        shelf_touches = (int(np.sum((prior_h20 >= shelf_band_lo) & (prior_h20 <= r20 + 0.5 * atr_est)))
                         if len(prior_h20) > 0 else 0)
        clearance_atr = float((close_now - r20) / atr_est)

        crsi = _connors_rsi(c)
        records.append({
            "Symbol": sym, "Close": close_now, "Open": o[-1], "High": h[-1],
            "Low": l[-1], "Volume": v[-1], "sma50": sma50, "sma150": sma150,
            "sma200": sma200, "sma200_1m": sma200_1m, "ema10": ema10, "ema20": ema20,
            "rvol20": rvol20, "rvol50": rvol50, "rvol20_median": rvol20_med,
            "r10": r10, "r20": r20, "h52": h52, "l52": l52, "adr20": adr20,
            "turnover20": turnover20, "ret20": ret20, "ret60": ret60,
            "ret120": ret120, "ret252": ret252, "rs_raw": rs_raw,
            "pre_vol_min": pre_vol_min, "range20": range20, "range60": range60,
            "ext_sma50": (close_now - sma50) / sma50 if sma50 > 0 else 0.0,
            "shelf_touches_20": shelf_touches, "is_shelf_r20": int(shelf_touches >= 2),
            "clearance_atr": clearance_atr, "base_low20": l20,
            "crsi": round(crsi, 1),
        })

    res_df = pd.DataFrame(records)
    if not res_df.empty and "rs_raw" in res_df.columns:
        res_df["rs_rating"] = (res_df["rs_raw"].rank(pct=True) * 100).round(1)
    return res_df


def _connors_rsi(closes: np.ndarray) -> float:
    """Connors RSI = (RSI(3) + RSI(streak, 2) + PercentRank(1d return, 100)) / 3.

    Returns the neutral 50.0 when there is not enough history.
    """
    if len(closes) < 105:
        return 50.0

    diff = np.diff(closes)
    gain = np.maximum(diff, 0.0)
    loss = np.maximum(-diff, 0.0)
    rs3 = float(np.mean(gain[-3:])) / float(np.mean(loss[-3:])) \
        if np.mean(loss[-3:]) > 0 else 100.0
    rsi3 = 100.0 - 100.0 / (1.0 + rs3)

    # Consecutive up/down streak, then RSI(2) applied to the streak series.
    streak = np.zeros(len(closes), dtype=float)
    for i in range(1, len(closes)):
        if closes[i] > closes[i - 1]:
            streak[i] = streak[i - 1] + 1.0 if streak[i - 1] > 0 else 1.0
        elif closes[i] < closes[i - 1]:
            streak[i] = streak[i - 1] - 1.0 if streak[i - 1] < 0 else -1.0
    s_diff = np.diff(streak)
    s_gain = np.maximum(s_diff, 0.0)
    s_loss = np.maximum(-s_diff, 0.0)
    s_avg_loss = float(np.mean(s_loss[-2:]))
    s_rs = float(np.mean(s_gain[-2:])) / s_avg_loss if s_avg_loss > 0 else 100.0
    rsi_streak = 100.0 - 100.0 / (1.0 + s_rs)

    ret1d = diff[-100:] / closes[-101:-1]
    pct_rank = float(np.sum(ret1d < ret1d[-1]) / len(ret1d) * 100.0)
    return float(np.clip((rsi3 + rsi_streak + pct_rank) / 3.0, 0.0, 100.0))


def screen_relative_strength(df: pd.DataFrame, top_n: int = 10,
                             min_turnover_cr: float = 1.0) -> list[ScreenerResult]:
    """Relative Strength Leader (O'Neil / Mansfield RS)."""
    sub = _liquid_universe(df, min_turnover_cr)
    mask = (
        (sub["Close"] > sub["sma50"]) & (sub["sma50"] > sub["sma200"]) &
        (sub["rs_rating"] >= 80.0) & (sub["ext_sma50"] <= 0.25) &
        (sub["rvol20"] >= 1.0) & (sub["ret60"] > 0)
    )
    passed = sub[mask].copy()
    passed["score"] = passed["rs_rating"] * 0.7 + np.clip(passed["rvol20"], 0.5, 3.0) * 10.0
    return _top_results("RELATIVE_STRENGTH", passed, top_n)


def screen_minervini(df: pd.DataFrame, top_n: int = 10,
                     min_turnover_cr: float = 1.0) -> list[ScreenerResult]:
    """Minervini Trend Template & contraction screener (SEPA framework)."""
    sub = _liquid_universe(df, min_turnover_cr)
    mask = (
        (sub["Close"] > sub["sma150"]) & (sub["Close"] > sub["sma200"]) &
        (sub["sma150"] > sub["sma200"]) &
        (sub["sma200"] >= sub["sma200_1m"] * 0.99) &
        (sub["sma50"] > sub["sma150"]) & (sub["sma50"] > sub["sma200"]) &
        (sub["Close"] > sub["sma50"]) &
        (sub["Close"] >= 1.30 * sub["l52"]) & (sub["Close"] >= 0.75 * sub["h52"]) &
        (sub["ext_sma50"] <= 0.25) & (sub["ret20"] > 0)
    )
    passed = sub[mask].copy()
    tightness = 1.0 / (passed["range20"] + 0.05)
    passed["score"] = (passed["ret60"] * 0.4 + passed["ret20"] * 0.3) * tightness
    return _top_results("MINERVINI_TEMPLATE", passed, top_n)


def screen_qullamaggie(df: pd.DataFrame, top_n: int = 10,
                       min_turnover_cr: float = 1.0) -> list[ScreenerResult]:
    """Qullamaggie High Tight Flag & breakout screener."""
    sub = _liquid_universe(df, min_turnover_cr)
    mask = (
        (sub["ema10"] > sub["ema20"]) & (sub["ema20"] > sub["sma50"]) &
        (sub["adr20"] >= 0.035) &                 # High daily volatility (ADR% >= 3.5%)
        (sub["Close"] > sub["r10"]) &             # Pivot breakout
        (sub["rvol20"] >= 1.4) &                  # Volume thrust
        ((sub["Close"] - sub["ema10"]) / sub["ema10"] <= 0.08) &  # Anti-chase
        ((sub["ret60"] >= 0.15) | (sub["ret120"] >= 0.25))        # Prior thrust leg
    )
    passed = sub[mask].copy()
    passed["score"] = passed["adr20"] * passed["rvol20"] * (1.0 + passed["ret20"])
    return _top_results("QULLAMAGGIE_BREAKOUT", passed, top_n)


def screen_canslim(df: pd.DataFrame, top_n: int = 10,
                   min_turnover_cr: float = 1.0) -> list[ScreenerResult]:
    """O'Neil CANSLIM pivot breakout screener."""
    sub = _liquid_universe(df, min_turnover_cr)
    mask = (
        (sub["Close"] > sub["sma50"]) & (sub["sma50"] > sub["sma200"]) &
        (sub["Close"] >= 0.85 * sub["h52"]) &     # Within 15% of the 52w high
        (sub["Close"] > sub["r20"]) &             # Fresh 20-day breakout
        (sub["Close"] <= 1.05 * sub["r20"]) &     # Anti-chase: <= 5% above pivot
        (sub["rvol50"] >= 1.4) &                  # Volume >= 1.4x 50-day average
        (sub["rs_rating"] >= 70.0) & (sub["ret60"] > 0)
    )
    passed = sub[mask].copy()
    passed["score"] = passed["rs_rating"] * (passed["rvol50"] / 2.0)
    return _top_results("CANSLIM_PIVOT", passed, top_n)


def screen_pkscreener_vcp(df: pd.DataFrame, top_n: int = 10,
                          min_turnover_cr: float = 1.0) -> list[ScreenerResult]:
    """PKScreener Volatility Contraction Pattern screener."""
    sub = _liquid_universe(df, min_turnover_cr)
    mask = (
        (sub["Close"] > sub["sma50"]) & (sub["sma50"] > sub["sma200"]) &
        (sub["range20"] < sub["range60"] * 0.85) &  # Volatility contraction
        (sub["pre_vol_min"] <= 0.75) &              # Volume dry-up
        (sub["Close"] > sub["r10"]) &               # Breakout of the contraction
        (sub["rvol20"] >= 1.25) & (sub["ret60"] > 0)
    )
    passed = sub[mask].copy()
    # Contraction expansion ratio, floored against division by zero on flat bases.
    passed["score"] = (passed["range60"] / np.maximum(passed["range20"], 0.03)) * passed["rvol20"]
    return _top_results("PKSCREENER_VCP", passed, top_n)


def screen_protocol_v2(df: pd.DataFrame, top_n: int = 10,
                       min_turnover_cr: float = 1.0) -> list[ScreenerResult]:
    """Protocol v2 Fortified screener (regime + sector cap + climax guard + shelf)."""
    sub = _liquid_universe(df, min_turnover_cr)
    mask = (
        (sub["Close"] > sub["sma50"]) & (sub["sma50"] > sub["sma200"]) &
        (sub["ext_sma50"] <= 0.20) &       # Anti-climax cap: <= 20% above the 50 SMA
        (sub["Close"] > sub["r20"]) &
        (sub["clearance_atr"] >= 0.10) &   # ATR clearance hurdle against false wicks
        (sub["ret20"] > 0)
    )
    passed = sub[mask].copy()
    shelf_bonus = np.clip(passed["shelf_touches_20"], 0, 4) * 0.10
    passed["score"] = (passed["ret20"] * 0.35 + (passed["rvol20"] / 5.0) * 0.35
                       + (passed["adr20"] * 10.0) * 0.15 + shelf_bonus)
    return _top_results("PROTOCOL_V2", passed, top_n)


def screen_stan_weinstein(df: pd.DataFrame, top_n: int = 10,
                          min_turnover_cr: float = 1.0) -> list[ScreenerResult]:
    """Stan Weinstein Stage 2 base breakout (150-day SMA inception)."""
    sub = _liquid_universe(df, min_turnover_cr)
    mask = (
        (sub["Close"] > sub["sma150"]) & (sub["sma150"] >= sub["sma200"]) &
        (sub["Close"] > sub["r20"]) & (sub["rvol20"] >= 1.4) &
        (sub["rs_rating"] >= 65.0) & (sub["ext_sma50"] <= 0.25) & (sub["ret20"] > 0)
    )
    passed = sub[mask].copy()
    passed["score"] = passed["rs_rating"] * (passed["rvol20"] / 2.0)
    return _top_results("STAN_WEINSTEIN_STAGE2", passed, top_n)


def screen_turtle_trading(df: pd.DataFrame, top_n: int = 10,
                          min_turnover_cr: float = 1.0) -> list[ScreenerResult]:
    """Turtle trading Donchian channel breakout (20d high, 10d low stop)."""
    sub = _liquid_universe(df, min_turnover_cr)
    mask = (
        (sub["Close"] > sub["sma50"]) & (sub["sma50"] > sub["sma200"]) &
        (sub["Close"] > sub["r20"]) & (sub["rvol20"] >= 1.2) &
        (sub["ext_sma50"] <= 0.25) & (sub["ret20"] > 0)
    )
    passed = sub[mask].copy()
    passed["score"] = (passed["ret20"] * 0.5 + (passed["rvol20"] / 3.0) * 0.5) \
        / np.maximum(passed["adr20"], 0.01)
    return _top_results("TURTLE_TRADING", passed, top_n)


def screen_darvas_box(df: pd.DataFrame, top_n: int = 10,
                      min_turnover_cr: float = 1.0) -> list[ScreenerResult]:
    """Darvas Box theory breakout (tight consolidation ceiling expansion)."""
    sub = _liquid_universe(df, min_turnover_cr)
    mask = (
        (sub["Close"] > sub["sma50"]) & (sub["sma50"] > sub["sma200"]) &
        (sub["Close"] >= 0.85 * sub["h52"]) & (sub["range20"] <= 0.18) &
        (sub["Close"] > sub["r20"]) & (sub["rvol20"] >= 1.3) & (sub["ext_sma50"] <= 0.25)
    )
    passed = sub[mask].copy()
    passed["score"] = (1.0 / np.maximum(passed["range20"], 0.04)) \
        * passed["rvol20"] * (1.0 + passed["ret20"])
    return _top_results("DARVAS_BOX", passed, top_n)


def screen_wyckoff_closing_range(df: pd.DataFrame, top_n: int = 10,
                                 min_turnover_cr: float = 1.0) -> list[ScreenerResult]:
    """Wyckoff closing-range absorption screener.

    A closing range >= 65% means the stock closed in the upper 35% of the day's
    high-low range: institutional demand absorbing offered supply. Combined with
    RVOL >= 1.4x it confirms genuine accumulation rather than drift.
    """
    sub = _liquid_universe(df, min_turnover_cr)
    if sub.empty:
        return []

    rng = sub["High"] - sub["Low"]
    # Closing range: 0 = closed at the low, 1 = closed at the high.
    cr = ((sub["Close"] - sub["Low"]) / np.maximum(rng, 0.01)).clip(0.0, 1.0)
    mask = (
        (sub["Close"] > sub["sma50"]) & (sub["sma50"] > sub["sma200"]) &
        (cr >= 0.65) &                # Upper 35% of the day's range
        (sub["rvol20"] >= 1.4) &      # Volume thrust confirms absorption
        (sub["ext_sma50"] <= 0.20) &  # Anti-chase
        (sub["Close"] > sub["r20"]) & (sub["ret20"] > 0)
    )
    passed = sub[mask].copy()
    passed["cr"] = cr[mask]
    passed["score"] = (passed["cr"] * 40.0
                       + np.clip(passed["rvol20"], 1.0, 4.0) * 15.0
                       + passed["rs_rating"] * 0.25)
    return _top_results("WYCKOFF_CLOSING_RANGE", passed, top_n)


def screen_sector_momentum_leader(
    df: pd.DataFrame,
    top_n: int = 10,
    min_turnover_cr: float = 1.0,
    ind_df: Any | None = None,
) -> list[ScreenerResult]:
    """Sector momentum leader (group-driven institutional tailwind).

    Roughly half of a stock's move is driven by its industry group (O'Neil;
    Fama-French industry momentum, Moskowitz & Grinblatt 1999). This screener
    keeps only names whose industry RS rank is >= the 60th percentile, so the
    macro sector is a buyer rather than a headwind. Without an industry frame it
    degrades gracefully to plain Stage-2 relative strength.
    """
    sub = _liquid_universe(df, min_turnover_cr)
    has_sectors = ind_df is not None and not getattr(ind_df, "empty", True)
    if sub.empty or not has_sectors:
        mask = (
            (sub["Close"] > sub["sma50"]) & (sub["sma50"] > sub["sma200"]) &
            (sub["rs_rating"] >= 70.0) & (sub["Close"] > sub["r20"]) &
            (sub["rvol20"] >= 1.2) & (sub["ret20"] > 0) & (sub["ext_sma50"] <= 0.25)
        )
        passed = sub[mask].copy()
        passed["score"] = passed["rs_rating"] * 0.6 + np.clip(passed["rvol20"], 1.0, 3.0) * 8.0
        return _top_results("SECTOR_MOMENTUM_LEADER", passed, top_n)

    from protocol.sector import get_sector_map  # lazy: avoids a sector import cycle

    ind_rank_map: dict[str, float] = {}
    if "Industry" in ind_df.columns and "rank_pct" in ind_df.columns:
        for _, irow in ind_df.iterrows():
            ind_rank_map[str(irow["Industry"])] = float(irow["rank_pct"])

    sector_of = get_sector_map()
    passed = sub[
        (sub["Close"] > sub["sma50"]) & (sub["sma50"] > sub["sma200"]) &
        (sub["Close"] > sub["r20"]) & (sub["rvol20"] >= 1.2) &
        (sub["ret20"] > 0) & (sub["ext_sma50"] <= 0.25)
    ].copy()
    if passed.empty:
        return []

    passed["industry"] = passed["Symbol"].map(lambda s: sector_of.get(str(s), ""))
    passed["ind_rank"] = passed["industry"].map(lambda i: ind_rank_map.get(i, 50.0))
    passed = passed[passed["ind_rank"] >= 60.0]  # Sector outside the top 40%
    if passed.empty:
        return []

    passed["score"] = (passed["ind_rank"] * 0.50        # Sector RS rank (primary signal)
                       + passed["rs_rating"] * 0.30     # Stock RS within the market
                       + np.clip(passed["rvol20"], 1.0, 3.0) * 5.0)
    return _top_results("SECTOR_MOMENTUM_LEADER", passed, top_n)


def screen_connors_rsi_pullback(df: pd.DataFrame, top_n: int = 10,
                                min_turnover_cr: float = 1.0) -> list[ScreenerResult]:
    """Connors RSI mean-reversion pullback screener.

    Buys the dip inside an established Stage-2 uptrend: CRSI <= 25 marks an acute
    panic flush, with an anti-collapse guard so freefall breakdowns are excluded
    and an RS floor so only genuine leaders qualify. Relaxes slightly to CRSI <=
    32 when the strict gate finds nothing.
    """
    sub = _liquid_universe(df, min_turnover_cr)
    if sub.empty or "crsi" not in sub.columns:
        return []

    mask = (
        (sub["Close"] > sub["sma200"]) & (sub["sma50"] > sub["sma200"]) &
        (sub["crsi"] <= 25.0) & (sub["ext_sma50"] >= -0.15) & (sub["rs_rating"] >= 55.0)
    )
    passed = sub[mask].copy()
    if passed.empty:
        passed = sub[
            (sub["Close"] > sub["sma200"]) & (sub["crsi"] <= 32.0) &
            (sub["ext_sma50"] >= -0.15) & (sub["rs_rating"] >= 50.0)
        ].copy()
    if passed.empty:
        return []

    passed["score"] = (100.0 - passed["crsi"]) * 0.70 + passed["rs_rating"] * 0.30
    return _top_results("CONNORS_RSI_PULLBACK", passed, top_n)


def screen_institutional_delivery(
    df: pd.DataFrame,
    top_n: int = 10,
    min_turnover_cr: float = 1.0,
    deliv_map: dict[str, float] | None = None,
) -> list[ScreenerResult]:
    """Institutional demat delivery absorption screener.

    Keeps names where shares are physically delivered into demat accounts
    (delivery % >= 50) rather than intraday churn, inside a Stage-2 trend with a
    volume thrust and no chase extension. Falls back to delivery >= 40% when the
    strict gate finds nothing.
    """
    sub = _liquid_universe(df, min_turnover_cr)
    if sub.empty:
        return []

    dmap = deliv_map or {}
    sub["deliv_pct"] = sub["Symbol"].map(lambda s: dmap.get(str(s), 0.0))
    mask = (
        (sub["Close"] > sub["sma50"]) & (sub["sma50"] > sub["sma200"]) &
        (sub["deliv_pct"] >= 50.0) & (sub["rvol20"] >= 1.2) &
        (sub["ext_sma50"] <= 0.25) & (sub["ret20"] > 0)
    )
    passed = sub[mask].copy()
    if passed.empty:
        passed = sub[
            (sub["Close"] > sub["sma50"]) & (sub["sma50"] > sub["sma200"]) &
            (sub["deliv_pct"] >= 40.0) & (sub["rvol20"] >= 1.1) & (sub["ext_sma50"] <= 0.25)
        ].copy()
    if passed.empty:
        return []

    passed["score"] = (passed["deliv_pct"] * 0.50
                       + np.clip(passed["rvol20"], 1.0, 4.0) * 10.0
                       + passed["rs_rating"] * 0.20)
    return _top_results("INSTITUTIONAL_DELIVERY", passed, top_n)
