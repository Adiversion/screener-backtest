"""Tests for the delivery-data path (F4 activation)."""
import os
import sys
import unittest

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from protocol import data, filters  # noqa: E402
from protocol.config import load_config  # noqa: E402
from protocol.features import build_features  # noqa: E402

CFG = load_config()


def _bars(n=60, deliv=True):
    d = {
        "Date": pd.bdate_range("2024-01-01", periods=n), "Symbol": "X",
        "Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.0, "Volume": 5000.0,
    }
    if deliv:
        d["DelivPct"] = 40.0
        d["DelivQty"] = 1000.0
        d["Trades"] = 100.0
    return pd.DataFrame(d)


class DeliveryFeatureTests(unittest.TestCase):
    def test_features_present_when_delivery_columns_exist(self):
        feat = build_features(_bars(deliv=True))
        self.assertTrue(feat["deliv_pct"].notna().all())
        self.assertAlmostEqual(feat["deliv_pct"].iloc[-1], 0.40, places=9)
        self.assertAlmostEqual(feat["deliv_pct_rel"].iloc[-1], 1.0, places=9)
        self.assertAlmostEqual(feat["avg_trade_size"].iloc[-1], 50.0, places=9)

    def test_features_are_na_without_delivery_columns(self):
        feat = build_features(_bars(deliv=False))
        for col in ("deliv_pct", "deliv_pct_rel", "deliv_rvol20", "avg_trade_size", "ats_rel"):
            self.assertTrue(feat[col].isna().all(), col)

    def test_aliases_do_not_lowercase_delivery_names(self):
        df = pd.DataFrame({
            "Date": pd.bdate_range("2024-01-01", periods=3), "Symbol": "X",
            "Open": 1.0, "High": 1.0, "Low": 1.0, "Close": 1.0, "Volume": 1.0,
            "DELIV_PCT": 12.0, "NO_OF_TRADES": 5.0})
        out = data._normalise(df)
        self.assertIn("DelivPct", out.columns)
        self.assertIn("Trades", out.columns)


class DeliveryFilterTests(unittest.TestCase):
    def test_f4_is_none_without_data(self):
        d = _bars(deliv=False)
        feat = build_features(d).reset_index(drop=True)
        self.assertIsNone(filters._delivery_weak(feat, len(feat) - 1, CFG["filters"]))

    def test_f4_flags_weak_delivery(self):
        feat = build_features(_bars(deliv=True)).reset_index(drop=True)
        weak = feat.copy()
        weak["deliv_pct_rel"] = 0.5
        self.assertTrue(filters._delivery_weak(weak, len(weak) - 1, CFG["filters"]))
        strong = feat.copy()
        strong["deliv_pct_rel"] = 1.5
        self.assertFalse(filters._delivery_weak(strong, len(strong) - 1, CFG["filters"]))

    def test_f4_nan_is_unknown_not_true(self):
        feat = build_features(_bars(deliv=True)).reset_index(drop=True)
        feat["deliv_pct_rel"] = np.nan
        self.assertIsNone(filters._delivery_weak(feat, len(feat) - 1, CFG["filters"]))


if __name__ == "__main__":
    unittest.main()
