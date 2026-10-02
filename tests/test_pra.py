"""Offline tests for the Pressure-Response-Acceptance event study."""
import os
import sys
import unittest

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from protocol import pra  # noqa: E402
from protocol.config import load_config  # noqa: E402
from protocol.features import build_features  # noqa: E402

CFG = load_config()


def _bars(close_path, vol=None):
    n = len(close_path)
    close = np.array(close_path, dtype=float)
    return pd.DataFrame({
        "Date": pd.bdate_range("2024-01-01", periods=n), "Symbol": "X",
        "Open": close, "High": close * 1.01, "Low": close * 0.99,
        "Close": close, "Volume": vol if vol is not None else np.full(n, 1000.0),
    })


class PRATests(unittest.TestCase):
    def test_no_lookahead_event_uses_only_past(self):
        bars = _bars([100 + i * 0.1 for i in range(60)])
        feat = build_features(bars)
        ev = pra.classify_events(feat, CFG, "X")
        # an event on day T must be recomputable from data <= T
        trunc = build_features(bars.iloc[:40])
        ev2 = pra.classify_events(trunc, CFG, "X")
        self.assertEqual(list(ev["event_class"].iloc[:len(ev2)]) if len(ev2) else [],
                         list(ev2["event_class"]))

    def test_strong_retention_classification(self):
        path = [100] * 30 + [100, 103, 106]
        vol = [1000] * 30 + [3000, 800, 1200]
        feat = build_features(_bars(path, vol))
        ev = pra.classify_events(feat, CFG, "X")
        self.assertTrue((ev["event_class"] == "STRONG_RETENTION").any())

    def test_outcomes_and_ablation(self):
        bars = _bars([100 + (i % 3) for i in range(120)])
        feat = build_features(bars)
        ev = pra.attach_outcomes(feat, pra.classify_events(feat, CFG, "X"), CFG)
        self.assertIn("fwd_ret_1", ev.columns)
        self.assertIn("resolution", ev.columns)
        self.assertFalse(pra.outcome_table(ev, CFG).empty)
        self.assertEqual(len(pra.ablation_table(ev, CFG)), 6)

    def test_empty_events_safe(self):
        feat = build_features(_bars([100] * 10))
        out = pra.run_event_study({"X": feat}, CFG)
        self.assertTrue(out["events"].empty or "event_class" in out["events"])


if __name__ == "__main__":
    unittest.main()
