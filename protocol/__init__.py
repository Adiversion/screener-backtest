"""Acceptance-After-Expansion backtest engine (strategy-agnostic)."""
from protocol import strategies as _core  # noqa: F401  (registers core strategies)
from protocol import strategies_rank as _rank  # noqa: F401  (registers rank strategies)
from protocol import strategies_pra as _pra  # noqa: F401  (registers PRA strategies)
from protocol import strategies_pa as _pa  # noqa: F401  (registers PA strategies)
from protocol import strategies_evidence as _ev  # noqa: F401  (registers IC-backed strategies)

__all__ = ["config", "features", "states", "filters", "simulator",
           "metrics", "strategies", "strategies_pra", "strategies_pa",
           "strategies_evidence", "pra",
           "pa", "screen", "quality", "evidence", "engine", "report",
           "report_html", "audit", "data"]
