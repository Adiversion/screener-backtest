"""Offline tests for the Price-Acceptance state machine (no network)."""
import os
import sys
import unittest

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from protocol import pa  # noqa: E402
from protocol.config import load_config  # noqa: E402
from protocol.features import build_features  # noqa: E402
from protocol.strategies import REGISTRY  # noqa: E402

CFG = load_config()


def _open_cfg() -> dict:
    """Config with the PDF liquidity/session gate removed for synthetic bars."""
    return {**CFG, "liquidity": {"min_sessions": 0, "min_turnover20": 0.0, "min_price": 0.0}}


def _base(n=60, base=100.0, vol=5000.0):
    return pd.DataFrame({
        "Date": pd.bdate_range("2024-01-01", periods=n), "Symbol": "X",
        "Open": base, "High": base + 1.0, "Low": base - 1.0,
        "Close": base, "Volume": vol,
    })


def _append(bars, o, h, l, c, v):
    row = pd.DataFrame({"Date": [bars["Date"].iloc[-1] + pd.offsets.BDay(1)], "Symbol": ["X"],
                        "Open": [o], "High": [h], "Low": [l], "Close": [c], "Volume": [v]})
    return pd.concat([bars, row], ignore_index=True)


class StateTests(unittest.TestCase):
    def test_state_a_accepted_expansion(self):
        # penetrate R20 with volume, close near the high (strong retention/CR)
        bars = _append(_base(), 101.0, 106.0, 100.0, 105.5, 40000.0)
        states = pa.classify_states(build_features(bars), _open_cfg(), "X")
        self.assertIn("A_ACCEPTED_EXPANSION", set(states["state"]))

    def test_state_d_failed_acceptance(self):
        # penetrate R20 then surrender it, closing near the low
        bars = _append(_base(), 101.0, 110.0, 99.0, 99.5, 40000.0)
        states = pa.classify_states(build_features(bars), _open_cfg(), "X")
        self.assertIn("D_FAILED_ACCEPTANCE", set(states["state"]))

    def test_no_state_without_penetration(self):
        bars = _append(_base(), 100.0, 100.5, 99.0, 100.0, 60000.0)
        states = pa.classify_states(build_features(bars), _open_cfg(), "X")
        self.assertTrue(states.empty or (states["penetration"] > 0).all())

    def test_liquidity_mask_excludes_small_names(self):
        bars = _base(vol=100.0)  # ~Rs 10k turnover, far below the gate
        feat = build_features(bars)
        self.assertFalse(bool(pa.liquid_mask(feat, CFG).any()))

    def test_min_sessions_gate(self):
        bars = _append(_base(n=40), 101.0, 106.0, 100.0, 105.5, 40000.0)
        states = pa.classify_states(build_features(bars), CFG, "X")
        self.assertTrue(states.empty)  # < 252 sessions of history


class StrategyRegistrationTests(unittest.TestCase):
    def test_expected_strategies_registered(self):
        for name in ("pa_state_a", "pa_state_b", "pa_state_c", "pa_state_d",
                     "m1_momentum_composite", "n1_eod_momentum",
                     "n2_consolidation_breakout", "n3_absorption",
                     "n4_effort_result_discrepancy"):
            self.assertIn(name, REGISTRY, name)


if __name__ == "__main__":
    unittest.main()
