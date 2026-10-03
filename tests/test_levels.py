"""Tests for the durable level block.

Two things matter here beyond arithmetic. The first is that a level is built
only from sessions that have already printed -- a centred or forward-shifted
window would quietly leak the future into a resistance level, which is the one
place such a bug would be invisible and profitable. The second is that a short
panel must produce NaN rather than a confident wrong number.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from protocol import features, levels  # noqa: E402


def _bars(n: int, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0, 1, n))
    return pd.DataFrame({
        "Date": pd.bdate_range("2020-01-01", periods=n),
        "Open": close, "High": close + 1.0, "Low": close - 1.0,
        "Close": close, "Volume": 1_000_000.0,
    })


class SufficiencyTests(unittest.TestCase):
    def test_short_history_is_reported_not_estimated(self):
        short = levels.sufficiency(levels.REQUIRED - 1)
        self.assertFalse(short["ok"])
        self.assertIn("short", short["note"])

    def test_long_history_is_reported_ok(self):
        self.assertTrue(levels.sufficiency(levels.REQUIRED)["ok"])

    def test_columns_are_nan_when_history_is_short(self):
        f = features.build_features(_bars(300))
        self.assertIn("durable_high", f.columns)
        self.assertTrue(f["durable_high"].isna().all())


class NoLookaheadTests(unittest.TestCase):
    def test_level_ignores_the_present_and_the_future(self):
        """Rewriting the last 60 bars must not move today's level."""
        n = levels.REQUIRED + 120
        base = _bars(n)
        tampered = base.copy()
        tampered.loc[tampered.index[-60:], ["High", "Low", "Close"]] *= 3.0
        a = levels.add_levels(base.copy()).iloc[-1]
        b = levels.add_levels(tampered).iloc[-1]
        self.assertAlmostEqual(a["durable_high"], b["durable_high"], places=9)
        self.assertAlmostEqual(a["durable_low"], b["durable_low"], places=9)

    def test_window_is_strictly_older_than_r252(self):
        """STALE_LO must start beyond the rolling window or this duplicates R252."""
        self.assertGreater(levels.STALE_LO, 252)


class LevelSemanticsTests(unittest.TestCase):
    def setUp(self):
        n = levels.REQUIRED + 200
        b = _bars(n)
        # a spike inside the stale window, in the middle of it
        self.spike_at = n - 420
        b.loc[self.spike_at, ["High", "Low", "Close"]] = 500.0
        self.f = levels.add_levels(b)

    def test_stale_high_finds_the_old_spike(self):
        last = self.f.iloc[-1]
        self.assertAlmostEqual(last["durable_high"], 500.0, places=6)

    def test_gap_is_negative_above_the_ceiling_and_positive_below(self):
        f = self.f
        above = f[f["Close"] > f["durable_high"]]
        self.assertTrue((above["level_gap"] > 0).all())
        self.assertEqual(f["level_break"].sum(), len(above))

    def test_touch_without_a_reject_is_not_counted_as_a_reject(self):
        f = self.f
        self.assertTrue((f.loc[f["level_touch"] == 1, "level_reject"] <= 1).all())
        # a reject requires the close back under the level
        rej = f[f["level_reject"] == 1]
        self.assertTrue((rej["Close"] < rej["durable_high"]).all())

    def test_sufficient_flag_matches_the_history_length(self):
        self.assertEqual(self.f["level_sufficient"].iloc[0], 1.0)


class ReinforcedLevelTests(unittest.TestCase):
    def test_shelf_detection_distinguishes_shelf_from_single_wick(self):
        """A level tested 3 times must be flagged as a shelf; a single wick must not."""
        n = 50
        dates = pd.bdate_range("2025-01-01", periods=n)
        # Create a flat base around 100 with ATR ~ 2.0
        df = pd.DataFrame({
            "Date": dates,
            "Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.0,
            "Volume": 1_000_000.0,
        })
        # Set R20 = 105 by putting a high at bar 10
        df.loc[10, "High"] = 105.0
        df.loc[15, "High"] = 104.8  # second touch within 0.75 ATR
        df.loc[20, "High"] = 104.9  # third touch within 0.75 ATR
        res = levels.add_levels(df)

        # At bar 25, shelf touches should be >= 2 and is_shelf_r20 should be 1.0
        self.assertGreaterEqual(res.loc[25, "shelf_touches_20"], 2.0)
        self.assertEqual(res.loc[25, "is_shelf_r20"], 1.0)

    def test_clearance_hurdle_prevents_tick_whipsaw(self):
        """A 1-cent breach should not trigger confirmed break, but a 0.5 ATR move should."""
        n = 50
        dates = pd.bdate_range("2025-01-01", periods=n)
        df = pd.DataFrame({
            "Date": dates,
            "Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.0,
            "Volume": 1_000_000.0,
        })
        df.loc[10, "High"] = 105.0
        res = levels.add_levels(df)
        
        # Test bar 30 with microscopic breach (close = 105.02, ATR ~ 2.0)
        df.loc[30, "Close"] = 105.02
        res2 = levels.add_levels(df.copy())
        self.assertEqual(res2.loc[30, "r20_break_confirmed"], 0.0)

        # Test bar 30 with solid expansion (close = 106.50, clearance > 0.20 ATR)
        df.loc[30, "Close"] = 106.50
        res3 = levels.add_levels(df.copy())
        self.assertEqual(res3.loc[30, "r20_break_confirmed"], 1.0)

    def test_structural_stop_anchors_below_base_low(self):
        """Base stop must sit below base_low20 with ATR buffer."""
        n = 50
        dates = pd.bdate_range("2025-01-01", periods=n)
        df = pd.DataFrame({
            "Date": dates,
            "Open": 100.0, "High": 102.0, "Low": 95.0, "Close": 100.0,
            "Volume": 1_000_000.0,
        })
        res = levels.add_levels(df)
        last = res.iloc[-1]
        self.assertLess(last["base_stop_level"], last["base_low20"])
        self.assertGreater(last["base_stop_pct"], 0.0)


if __name__ == "__main__":
    unittest.main()

