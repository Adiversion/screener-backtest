"""Acceptance-After-Expansion backtest engine (strategy-agnostic)."""
from protocol import strategies as _core  # noqa: F401  (registers core strategies)
from protocol import strategies_rank as _rank  # noqa: F401  (registers rank strategies)
from protocol import strategies_pra as _pra  # noqa: F401  (registers PRA strategies)
from protocol import strategies_pa as _pa  # noqa: F401  (registers PA strategies)

__all__ = ["config", "features", "states", "filters", "simulator",
           "metrics", "strategies", "strategies_pra", "strategies_pa", "pra",
           "pa", "engine", "report", "audit", "data"]
