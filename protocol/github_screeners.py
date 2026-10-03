"""Codified GitHub Momentum Screeners for Comparative Benchmarking.

Implementations of prominent open-source quant and momentum screeners:
1. Minervini Trend Template (RyanJHamby/stock-screener, icedevil2001)
2. Qullamaggie Breakout & High Tight Flag (axidzz/Qullamaggie-Setups)
3. CANSLIM Growth / Pivot Breakout (William O'Neil)
4. PKScreener Volatility Contraction Pattern (pkjmesra/PKScreener)
5. Protocol v2 Fortified Screener (Our current regime-gated engine)
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


def compute_screener_features(sub_history: pd.DataFrame, asof_date: pd.Timestamp | str) -> pd.DataFrame:
    """Computes technical indicators for all symbols up to asof_date."""
    asof = pd.Timestamp(asof_date).normalize()
    filtered = sub_history[pd.to_datetime(sub_history["Date"]).dt.normalize() <= asof].copy()
    active_symbols = set(filtered[pd.to_datetime(filtered["Date"]).dt.normalize() == asof]["Symbol"])

    records = []
    # Process only active symbols
    for sym, group in filtered[filtered["Symbol"].isin(active_symbols)].groupby("Symbol"):
        if len(group) < 200:
            continue
        c = group["Close"].values
        o = group["Open"].values
        h = group["High"].values
        l = group["Low"].values
        v = group["Volume"].values

        close_now = c[-1]
        sma50 = float(np.mean(c[-50:]))
        sma150 = float(np.mean(c[-150:]))
        sma200 = float(np.mean(c[-200:]))
        sma200_1m = float(np.mean(c[-222:-22])) if len(c) >= 222 else sma200

        # Exponential moving averages
        s_c = pd.Series(c)
        ema10 = float(s_c.ewm(span=10, adjust=False).mean().iloc[-1])
        ema20 = float(s_c.ewm(span=20, adjust=False).mean().iloc[-1])

        # Volume and range features
        vol_mean20 = float(np.mean(v[-21:-1])) if len(v) >= 21 else float(np.mean(v))
        vol_mean50 = float(np.mean(v[-51:-1])) if len(v) >= 51 else vol_mean20
        rvol20 = float(v[-1] / vol_mean20) if vol_mean20 > 0 else 0.0
        rvol50 = float(v[-1] / vol_mean50) if vol_mean50 > 0 else 0.0

        r10 = float(np.max(h[-11:-1])) if len(h) >= 11 else float(h[-1])
        r20 = float(np.max(h[-21:-1])) if len(h) >= 21 else float(h[-1])
        r60 = float(np.max(h[-61:-1])) if len(h) >= 61 else float(h[-1])
        l20 = float(np.min(l[-21:-1])) if len(l) >= 21 else float(l[-1])
        l60 = float(np.min(l[-61:-1])) if len(l) >= 61 else float(l[-1])

        h52 = float(np.max(h[-253:-1])) if len(h) >= 253 else float(np.max(h[:-1]))
        l52 = float(np.min(l[-253:-1])) if len(l) >= 253 else float(np.min(l[:-1]))

        # ADR & Volatility Contraction
        adr20 = float(np.mean((h[-20:] - l[-20:]) / c[-20:]))
        turnover20 = float(np.mean(c[-20:] * v[-20:]))
        ret20 = float((c[-1] / c[-21]) - 1.0) if len(c) >= 21 else 0.0
        ret60 = float((c[-1] / c[-61]) - 1.0) if len(c) >= 61 else 0.0
        ret120 = float((c[-1] / c[-121]) - 1.0) if len(c) >= 121 else ret60
        ret252 = float((c[-1] / c[-253]) - 1.0) if len(c) >= 253 else ret120
        rs_raw = 0.4 * ret252 + 0.2 * ret120 + 0.2 * ret60 + 0.2 * ret20

        # Base volume dry up (prior 3 sessions minimum volume vs 20d avg)
        pre_vol_min = float(np.min(v[-4:-1]) / vol_mean20) if len(v) >= 4 and vol_mean20 > 0 else 1.0
        range20 = float((r20 - l20) / close_now)
        range60 = float((r60 - l60) / close_now)

        # Multi-touch resistance shelf: prior 20 sessions touching within 0.75 ATR
        atr_est = max(adr20 * close_now, 0.01)
        prior_h20 = h[-21:-1] if len(h) >= 21 else h[:-1]
        shelf_band_lo = r20 - 0.75 * atr_est
        shelf_touches = int(np.sum((prior_h20 >= shelf_band_lo) & (prior_h20 <= r20 + 0.5 * atr_est))) if len(prior_h20) > 0 else 0
        clearance_atr = float((close_now - r20) / atr_est)

        records.append({
            "Symbol": sym, "Close": close_now, "Open": o[-1], "High": h[-1], "Low": l[-1],
            "Volume": v[-1], "sma50": sma50, "sma150": sma150, "sma200": sma200,
            "sma200_1m": sma200_1m, "ema10": ema10, "ema20": ema20, "rvol20": rvol20,
            "rvol50": rvol50, "r10": r10, "r20": r20, "h52": h52, "l52": l52,
            "adr20": adr20, "turnover20": turnover20, "ret20": ret20, "ret60": ret60,
            "ret120": ret120, "ret252": ret252, "rs_raw": rs_raw,
            "pre_vol_min": pre_vol_min, "range20": range20, "range60": range60,
            "ext_sma50": (close_now - sma50) / sma50 if sma50 > 0 else 0.0,
            "shelf_touches_20": shelf_touches, "is_shelf_r20": int(shelf_touches >= 2),
            "clearance_atr": clearance_atr, "base_low20": l20,
        })
    res_df = pd.DataFrame(records)
    if not res_df.empty and "rs_raw" in res_df.columns:
        res_df["rs_rating"] = (res_df["rs_raw"].rank(pct=True) * 100).round(1)
    return res_df


def screen_relative_strength(df: pd.DataFrame, top_n: int = 10, min_turnover_cr: float = 1.0) -> list[ScreenerResult]:
    """Comparative Relative Strength Leader Screener (William O'Neil / Mansfield RS)."""
    sub = df[df["turnover20"] >= min_turnover_cr * 1e7].copy()
    m = (
        (sub["Close"] > sub["sma50"]) & (sub["sma50"] > sub["sma200"]) &
        (sub["rs_rating"] >= 80.0) &
        (sub["ext_sma50"] <= 0.25) &
        (sub["rvol20"] >= 1.0) &
        (sub["ret60"] > 0)
    )
    passed = sub[m].copy()
    # Steel: Composite rank weighting RS power (70%) and institutional volume commitment (30%)
    passed["score"] = passed["rs_rating"] * 0.7 + np.clip(passed["rvol20"], 0.5, 3.0) * 10.0
    ranked = passed.sort_values("score", ascending=False).head(top_n)
    return [
        ScreenerResult("RELATIVE_STRENGTH", r["Symbol"], r["Close"], r["rvol20"], r["ret20"], r["adr20"], r["ext_sma50"], r["score"])
        for _, r in ranked.iterrows()
    ]


def screen_minervini(df: pd.DataFrame, top_n: int = 10, min_turnover_cr: float = 1.0) -> list[ScreenerResult]:
    """Mark Minervini Trend Template & Contraction Screener (SEPA Framework)."""
    sub = df[df["turnover20"] >= min_turnover_cr * 1e7].copy()
    m = (
        (sub["Close"] > sub["sma150"]) & (sub["Close"] > sub["sma200"]) &
        (sub["sma150"] > sub["sma200"]) &
        (sub["sma200"] >= sub["sma200_1m"] * 0.99) &
        (sub["sma50"] > sub["sma150"]) & (sub["sma50"] > sub["sma200"]) &
        (sub["Close"] > sub["sma50"]) &
        (sub["Close"] >= 1.30 * sub["l52"]) &
        (sub["Close"] >= 0.75 * sub["h52"]) &
        (sub["ext_sma50"] <= 0.25) &
        (sub["ret20"] > 0)
    )
    passed = sub[m].copy()
    # Steel: Rank by tight base contraction proximity + smooth multi-month momentum
    tightness = 1.0 / (passed["range20"] + 0.05)
    passed["score"] = (passed["ret60"] * 0.4 + passed["ret20"] * 0.3) * tightness
    ranked = passed.sort_values("score", ascending=False).head(top_n)
    return [
        ScreenerResult("MINERVINI_TEMPLATE", r["Symbol"], r["Close"], r["rvol20"], r["ret20"], r["adr20"], r["ext_sma50"], r["score"])
        for _, r in ranked.iterrows()
    ]


def screen_qullamaggie(df: pd.DataFrame, top_n: int = 10, min_turnover_cr: float = 1.0) -> list[ScreenerResult]:
    """Kristjan Qullamaggie High Tight Flag & Breakout Screener."""
    sub = df[df["turnover20"] >= min_turnover_cr * 1e7].copy()
    m = (
        (sub["ema10"] > sub["ema20"]) & (sub["ema20"] > sub["sma50"]) &
        (sub["adr20"] >= 0.035) &  # High daily volatility asset (ADR% >= 3.5%)
        (sub["Close"] > sub["r10"]) &  # Pivot breakout
        (sub["rvol20"] >= 1.4) &  # Volume thrust
        ((sub["Close"] - sub["ema10"]) / sub["ema10"] <= 0.08) &  # Tight to 10 EMA (anti-chase)
        ((sub["ret60"] >= 0.15) | (sub["ret120"] >= 0.25))  # Steel: Mandatory prior momentum thrust leg
    )
    passed = sub[m].copy()
    # Steel: Momentum explosion factor * Volume thrust
    passed["score"] = passed["adr20"] * passed["rvol20"] * (1.0 + passed["ret20"])
    ranked = passed.sort_values("score", ascending=False).head(top_n)
    return [
        ScreenerResult("QULLAMAGGIE_BREAKOUT", r["Symbol"], r["Close"], r["rvol20"], r["ret20"], r["adr20"], r["ext_sma50"], r["score"])
        for _, r in ranked.iterrows()
    ]


def screen_canslim(df: pd.DataFrame, top_n: int = 10, min_turnover_cr: float = 1.0) -> list[ScreenerResult]:
    """William O'Neil CANSLIM Pivot Breakout Screener."""
    sub = df[df["turnover20"] >= min_turnover_cr * 1e7].copy()
    m = (
        (sub["Close"] > sub["sma50"]) & (sub["sma50"] > sub["sma200"]) &
        (sub["Close"] >= 0.85 * sub["h52"]) &  # Within 15% of 52-week high
        (sub["Close"] > sub["r20"]) &  # Fresh 20-day high breakout
        (sub["Close"] <= 1.05 * sub["r20"]) &  # Anti-chasing: <= 5% above pivot
        (sub["rvol50"] >= 1.4) &  # Volume surge >= 1.4x 50-day average
        (sub["rs_rating"] >= 70.0) &  # Steel: O'Neil RS leadership criterion
        (sub["ret60"] > 0)
    )
    passed = sub[m].copy()
    # Steel: Reward breakout volume conviction * Relative Strength ranking
    passed["score"] = passed["rs_rating"] * (passed["rvol50"] / 2.0)
    ranked = passed.sort_values("score", ascending=False).head(top_n)
    return [
        ScreenerResult("CANSLIM_PIVOT", r["Symbol"], r["Close"], r["rvol20"], r["ret20"], r["adr20"], r["ext_sma50"], r["score"])
        for _, r in ranked.iterrows()
    ]


def screen_pkscreener_vcp(df: pd.DataFrame, top_n: int = 10, min_turnover_cr: float = 1.0) -> list[ScreenerResult]:
    """PKScreener Volatility Contraction Pattern Screener (pkjmesra/PKScreener)."""
    sub = df[df["turnover20"] >= min_turnover_cr * 1e7].copy()
    m = (
        (sub["Close"] > sub["sma50"]) & (sub["sma50"] > sub["sma200"]) &
        (sub["range20"] < sub["range60"] * 0.85) &  # Volatility contraction
        (sub["pre_vol_min"] <= 0.75) &  # Volume dry-up in prior sessions
        (sub["Close"] > sub["r10"]) &  # Breakout of tight contraction
        (sub["rvol20"] >= 1.25) &
        (sub["ret60"] > 0)
    )
    passed = sub[m].copy()
    # Steel: Safe contraction expansion ratio (no singularity/div-by-zero on flat bases)
    contraction_ratio = passed["range60"] / np.maximum(passed["range20"], 0.03)
    passed["score"] = contraction_ratio * passed["rvol20"]
    ranked = passed.sort_values("score", ascending=False).head(top_n)
    return [
        ScreenerResult("PKSCREENER_VCP", r["Symbol"], r["Close"], r["rvol20"], r["ret20"], r["adr20"], r["ext_sma50"], r["score"])
        for _, r in ranked.iterrows()
    ]


def screen_protocol_v2(df: pd.DataFrame, top_n: int = 10, min_turnover_cr: float = 1.0) -> list[ScreenerResult]:
    """Our Protocol v2 Fortified Screener (Regime + Sector Cap + Climax Guard + Multi-Touch Shelf)."""
    sub = df[df["turnover20"] >= min_turnover_cr * 1e7].copy()
    m = (
        (sub["Close"] > sub["sma50"]) & (sub["sma50"] > sub["sma200"]) &
        (sub["ext_sma50"] <= 0.20) &  # Anti-climax extension cap (<= 20% above 50 SMA)
        (sub["Close"] > sub["r20"]) &
        (sub["clearance_atr"] >= 0.10) &  # Steel: ATR clearance hurdle against false wicks
        (sub["ret20"] > 0)
    )
    passed = sub[m].copy()
    # Steel: Blended score rewarding ATR clearance, volume thrust, ADR quality, and shelf consolidation touches
    shelf_bonus = np.clip(passed["shelf_touches_20"], 0, 4) * 0.10
    passed["score"] = passed["ret20"] * 0.35 + (passed["rvol20"] / 5.0) * 0.35 + (passed["adr20"] * 10.0) * 0.15 + shelf_bonus
    ranked = passed.sort_values("score", ascending=False).head(top_n)
    return [
        ScreenerResult("PROTOCOL_V2", r["Symbol"], r["Close"], r["rvol20"], r["ret20"], r["adr20"], r["ext_sma50"], r["score"])
        for _, r in ranked.iterrows()
    ]


def screen_stan_weinstein(df: pd.DataFrame, top_n: int = 10, min_turnover_cr: float = 1.0) -> list[ScreenerResult]:
    """Stan Weinstein Stage 2 Base Breakout Screener (30-Week / 150d SMA Inception)."""
    sub = df[df["turnover20"] >= min_turnover_cr * 1e7].copy()
    m = (
        (sub["Close"] > sub["sma150"]) & (sub["sma150"] >= sub["sma200"]) &
        (sub["Close"] > sub["r20"]) &  # Breaking out above Stage 1 base ceiling
        (sub["rvol20"] >= 1.4) &  # Heavy volume expansion into Stage 2
        (sub["rs_rating"] >= 65.0) &  # Mansfield RS outperformance
        (sub["ext_sma50"] <= 0.25) &  # Early in trend, inside strict anti-chase gate
        (sub["ret20"] > 0)
    )
    passed = sub[m].copy()
    passed["score"] = passed["rs_rating"] * (passed["rvol20"] / 2.0)
    ranked = passed.sort_values("score", ascending=False).head(top_n)
    return [
        ScreenerResult("STAN_WEINSTEIN_STAGE2", r["Symbol"], r["Close"], r["rvol20"], r["ret20"], r["adr20"], r["ext_sma50"], r["score"])
        for _, r in ranked.iterrows()
    ]
