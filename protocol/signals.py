"""The TradeSignal contract shared by every strategy and the simulator.

A strategy's only job is to turn the feature panel into signals. All exit
mechanics, fees and accounting live in the simulator, so strategies are
directly comparable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd


@dataclass
class TradeSignal:
    strategy: str
    symbol: str
    signal_date: pd.Timestamp
    entry_date: pd.Timestamp
    expected_entry: float
    stop: float | None = None          # absolute structural stop
    stop_pct: float | None = None      # alternative: fraction below entry
    meta: dict[str, Any] = field(default_factory=dict)

    def meta_row(self) -> dict[str, Any]:
        return {**self.meta, "strategy": self.strategy, "symbol": self.symbol}
