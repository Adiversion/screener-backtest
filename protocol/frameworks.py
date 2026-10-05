"""Canonical registry of the independent screening frameworks.

Both `scripts/decisions.py` and `protocol/dashboard_data.py` need "run every
framework against one feature frame and keep the label each result came from".
Keeping the list here means a new screener is added once, and the two callers
can never drift apart (they previously disagreed on labels such as "CANSLIM
Setup" vs "CANSLIM Pivot").
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from protocol.github_screeners import (
    ScreenerResult,
    screen_canslim,
    screen_connors_rsi_pullback,
    screen_darvas_box,
    screen_institutional_delivery,
    screen_minervini,
    screen_pkscreener_vcp,
    screen_protocol_v2,
    screen_qullamaggie,
    screen_relative_strength,
    screen_sector_momentum_leader,
    screen_stan_weinstein,
    screen_turtle_trading,
    screen_wyckoff_closing_range,
)

# (label, screener, optional-kwarg). `needs` names the one extra argument a
# screener requires beyond the common `top_n` / `min_turnover_cr` pair.
FRAMEWORKS: tuple[tuple[str, Any, str | None], ...] = (
    ("Protocol Fortified", screen_protocol_v2, None),
    ("Relative Strength Leader", screen_relative_strength, None),
    ("Minervini Template", screen_minervini, None),
    ("Stan Weinstein Stage 2", screen_stan_weinstein, None),
    ("Qullamaggie Breakout", screen_qullamaggie, None),
    ("CANSLIM Pivot", screen_canslim, None),
    ("PKScreener VCP", screen_pkscreener_vcp, None),
    ("Turtle Trading", screen_turtle_trading, None),
    ("Darvas Box", screen_darvas_box, None),
    ("Wyckoff Closing Range", screen_wyckoff_closing_range, None),
    ("Sector Momentum Leader", screen_sector_momentum_leader, "ind_df"),
    ("Institutional Delivery Absorption", screen_institutional_delivery, "deliv_map"),
    ("Connors RSI Pullback", screen_connors_rsi_pullback, None),
)

FRAMEWORK_COUNT = len(FRAMEWORKS)


def run_frameworks(
    feat: pd.DataFrame,
    *,
    top_n: int = 60,
    min_turnover_cr: float = 0.5,
    ind_df: pd.DataFrame | None = None,
    deliv_map: dict[str, float] | None = None,
    include_delivery: bool = True,
) -> list[tuple[str, list[ScreenerResult]]]:
    """Run every framework against one feature frame, in canonical order.

    Returns `(label, picks)` pairs. Set `include_delivery=False` for callers
    without delivery data; Sector Momentum degrades to its Stage-2 fallback when
    `ind_df` is None.
    """
    common: dict[str, Any] = {"top_n": top_n, "min_turnover_cr": min_turnover_cr}
    out: list[tuple[str, list[ScreenerResult]]] = []
    for label, screener, needs in FRAMEWORKS:
        if needs == "deliv_map" and not include_delivery:
            continue
        if needs == "ind_df":
            picks = screener(feat, ind_df=ind_df, **common)
        elif needs == "deliv_map":
            picks = screener(feat, deliv_map=deliv_map, **common)
        else:
            picks = screener(feat, **common)
        out.append((label, picks))
    return out


def load_delivery_map(asof: pd.Timestamp,
                      data_dir: str | Path | None = None) -> dict[str, float]:
    """`symbol -> delivery %` for one session, or `{}` when unavailable.

    Delivery history is optional; a missing or unreadable file is a normal state
    (the engine flags the delivery gate as unavailable rather than zero-filling),
    so this never raises.
    """
    base = Path(data_dir) if data_dir is not None else \
        Path(__file__).resolve().parent.parent / "data"
    path = base / "delivery_history.parquet"
    if not path.exists():
        return {}
    try:
        ddf = pd.read_parquet(path)
        ddf["Date"] = pd.to_datetime(ddf["Date"]).dt.normalize()
        dsub = ddf[ddf["Date"] == pd.Timestamp(asof).normalize()]
        return dict(zip(dsub["Symbol"].astype(str), dsub["DelivPct"].astype(float)))
    except Exception:
        return {}
