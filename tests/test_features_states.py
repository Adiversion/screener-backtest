"""Offline tests for A3 features and the A4 state machine (no network)."""
import os
import sys
import unittest

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from protocol import states  # noqa: E402
from protocol.config import load_config  # noqa: E402
from protocol.features import build_features  # noqa: E402


def flat_bars(n=40, base=100.0, vol=1000.0):
    return pd.DataFrame({
        "Date": pd.bdate_range("2024-01-01", periods=n),
        "Symbol": "TEST", "Open": base, "High": base + 1.0,
        "Low": base - 1.0, "Close": base, "Volume": vol,
    })


def breakout_bars():
    bars = flat_bars(30)
    d0 = pd.DataFrame({
        "Date": [bars["Date"].iloc[-1] + pd.offsets.BDay(1)], "Symbol": ["TEST"],
        "Open": [101.0], "High": [104.0], "Low": [99.5], "Close": [103.0], "Volume": [3000.0]})
    hold = pd.DataFrame({
        "Date": [d0["Date"].iloc[0] + pd.offsets.BDay(1), d0["Date"].iloc[0] + pd.offsets.BDay(2)],
        "Symbol": ["TEST", "TEST"], "Open": [102.0, 103.0],
        "High": [102.5, 105.5], "Low": [101.0, 103.0], "Close": [101.5, 105.0],
        "Volume": [500.0, 800.0]})
    return pd.concat([bars, d0, hold], ignore_index=True)


class FeatureTests(unittest.TestCase):
    def test_r20_excludes_current_bar(self):
        bars = flat_bars(30)
        bars.loc[bars.index[-1], "High"] = 200.0
        feat = build_features(bars)
        self.assertEqual(feat["R20"].iloc[-1], 101.0)  # yesterday's max, not 200

    def test_retention_formula(self):
        bars = breakout_bars()
        feat = build_features(bars)
        row = feat.iloc[-3]  # D0
        expected = (row["Close"] - row["R20"]) / (row["High"] - row["R20"])
        self.assertAlmostEqual(row["retention"], expected, places=6)

    def test_rvol_uses_trailing_mean(self):
        bars = flat_bars(30)
        bars.loc[bars.index[-1], "Volume"] = 3000.0
        feat = build_features(bars)
        self.assertAlmostEqual(feat["rvol20"].iloc[-1], 3.0, places=6)

    def test_delivery_features_are_na(self):
        feat = build_features(flat_bars(30))
        self.assertTrue(feat["deliv_pct_rel"].isna().all())


class StateMachineTests(unittest.TestCase):
    def setUp(self):
        self.cfg = load_config()

    def test_acceptance_trigger_is_candidate(self):
        feat = build_features(breakout_bars())
        events = states.find_events(feat, self.cfg)
        labels = [e["label"] for e in events]
        self.assertIn("CANDIDATE", labels)
        cand = next(e for e in events if e["label"] == "CANDIDATE")
        self.assertLessEqual(cand["stop_distance"], self.cfg["state2"]["stop_distance_max"])

    def test_rejection_when_close_below_reference(self):
        bars = breakout_bars()
        bars.loc[bars.index[-2], "Close"] = 99.0  # D0+1 closes below R20
        bars.loc[bars.index[-2], "Low"] = 98.0
        feat = build_features(bars)
        events = states.find_events(feat, self.cfg)
        self.assertTrue(any(e["label"] in {"RECOVERED_AFTER_REJ", "CONTINUED_FAILURE"} for e in events))

    def test_no_breakout_without_volume(self):
        bars = flat_bars(30)
        d0 = pd.DataFrame({"Date": [bars["Date"].iloc[-1] + pd.offsets.BDay(1)], "Symbol": ["TEST"],
                           "Open": [101.0], "High": [104.0], "Low": [99.5], "Close": [103.0],
                           "Volume": [1000.0]})
        feat = build_features(pd.concat([bars, d0], ignore_index=True))
        self.assertEqual(states.find_events(feat, self.cfg), [])


if __name__ == "__main__":
    unittest.main()
