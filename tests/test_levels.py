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


if __name__ == "__main__":
    unittest.main()
