"""Offline tests for market regime and sector diversification."""
import os
import sys
import unittest
import pandas as pd
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from protocol import regime, sector  # noqa: E402


class RegimeTests(unittest.TestCase):
    def test_regime_classification(self):
        dates = pd.bdate_range("2024-01-01", periods=60)
        dfs = []
        # Create an artificial universe of 5 stocks in an uptrend
        for s in ["S1", "S2", "S3", "S4", "S5"]:
            dfs.append(pd.DataFrame({
                "Date": dates,
                "Symbol": s,
                "Close": np.linspace(100, 150, 60),
                "Open": 100.0, "High": 150.0, "Low": 95.0, "Volume": 1000.0
            }))
        history = pd.concat(dfs, ignore_index=True)
        mkt = regime.compute_market_regime(history)
        self.assertFalse(mkt.empty)
        # Should be classified as BULL when in a strong steady uptrend
        last_reg = mkt["regime"].iloc[-1]
        self.assertEqual(last_reg, "BULL")

    def test_get_regime_at(self):
        dates = pd.bdate_range("2024-01-01", periods=30)
        history = pd.DataFrame({
            "Date": dates,
            "Symbol": "TEST",
            "Close": np.linspace(100, 80, 30),  # downtrend
            "Open": 100.0, "High": 105.0, "Low": 75.0, "Volume": 1000.0
        })
        info = regime.get_regime_at(history, dates[-1])
        self.assertIn("regime", info)
        self.assertIn(info["regime"], ("DEFENSIVE", "NEUTRAL", "BULL"))


class SectorTests(unittest.TestCase):
    def test_get_sector(self):
        sec = sector.get_sector("BAJAJ-AUTO")
        self.assertEqual(sec, "Automobile and Auto Components")

    def test_apply_sector_diversification(self):
        picks = pd.DataFrame([
            {"symbol": "BAJAJ-AUTO", "score": 0.90},  # Auto
            {"symbol": "HEROMOTOCO", "score": 0.85},  # Auto (should be capped)
            {"symbol": "WELSPUNLIV", "score": 0.80},  # Textiles
            {"symbol": "TCS", "score": 0.75},         # IT
        ])
        div = sector.apply_sector_diversification(picks, max_per_sector=1, top=3)
        self.assertEqual(len(div), 3)
        # HEROMOTOCO should be dropped because BAJAJ-AUTO already occupies the Auto slot
        symbols = div["symbol"].tolist()
        self.assertIn("BAJAJ-AUTO", symbols)
        self.assertNotIn("HEROMOTOCO", symbols)
        self.assertIn("WELSPUNLIV", symbols)
        self.assertIn("TCS", symbols)

    def test_industry_momentum(self):
        feat = pd.DataFrame([
            {"Symbol": "BAJAJ-AUTO", "ret60": 0.15, "Close": 1000.0},
            {"Symbol": "TCS", "ret60": -0.05, "Close": 3500.0},
            {"Symbol": "WELSPUNLIV", "ret60": 0.25, "Close": 150.0},
        ])
        ind_df = sector.compute_industry_momentum(feat)
        self.assertFalse(ind_df.empty)
        self.assertIn("rank_pct", ind_df.columns)
        self.assertIn("tier", ind_df.columns)

        tw = sector.get_symbol_industry_momentum("BAJAJ-AUTO", ind_df)
        self.assertEqual(tw["industry"], "Automobile and Auto Components")
        self.assertIn("rs_rank", tw)
        self.assertIn("is_tailwind", tw)


if __name__ == "__main__":
    unittest.main()
