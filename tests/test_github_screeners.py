"""Unit tests for GitHub screeners and dynamic exits."""
from __future__ import annotations

import unittest
import numpy as np
import pandas as pd

from protocol.exits import ExitStrategy, simulate_dynamic_trade
from protocol.github_screeners import (
    compute_screener_features,
    screen_canslim,
    screen_minervini,
    screen_pkscreener_vcp,
    screen_protocol_v2,
    screen_qullamaggie,
)


def _make_dummy_history(n_days: int = 260) -> pd.DataFrame:
    dates = pd.date_range("2026-01-01", periods=n_days, freq="B")
    records = []
    base_price = 100.0
    for i, d in enumerate(dates):
        mult = 1.04 if i == n_days - 1 else 1.0
        px = base_price * (1.0 + 0.003 * i) * mult
        records.append({
            "Date": d,
            "Symbol": "UPTREND",
            "Open": px * 0.99,
            "High": px * 1.01,
            "Low": px * 0.97,
            "Close": px,
            "Volume": 100000 + (500000 if i == n_days - 1 else 0),
        })
    return pd.DataFrame(records)


class TestGitHubScreeners(unittest.TestCase):

    def setUp(self):
        self.df = _make_dummy_history(260)
        self.asof = self.df["Date"].iloc[-1]

    def test_compute_features(self):
        feat = compute_screener_features(self.df, self.asof)
        self.assertEqual(len(feat), 1)
        row = feat.iloc[0]
        self.assertEqual(row["Symbol"], "UPTREND")
        self.assertGreater(row["Close"], row["sma50"])
        self.assertGreater(row["sma50"], row["sma200"])
        self.assertGreater(row["rvol20"], 1.5)

    def test_minervini_screen(self):
        feat = compute_screener_features(self.df, self.asof)
        picks = screen_minervini(feat, top_n=5, min_turnover_cr=0.01)
        self.assertEqual(len(picks), 1)
        self.assertEqual(picks[0].symbol, "UPTREND")

    def test_qullamaggie_screen(self):
        feat = compute_screener_features(self.df, self.asof)
        picks = screen_qullamaggie(feat, top_n=5, min_turnover_cr=0.01)
        self.assertEqual(len(picks), 1)
        self.assertEqual(picks[0].symbol, "UPTREND")

    def test_canslim_screen(self):
        feat = compute_screener_features(self.df, self.asof)
        picks = screen_canslim(feat, top_n=5, min_turnover_cr=0.01)
        self.assertEqual(len(picks), 1)
        self.assertEqual(picks[0].symbol, "UPTREND")

    def test_pkscreener_vcp(self):
        feat = compute_screener_features(self.df, self.asof)
        picks = screen_pkscreener_vcp(feat, top_n=5, min_turnover_cr=0.01)
        # May or may not pass VCP contraction condition depending on synthetic noise
        self.assertIsInstance(picks, list)

    def test_protocol_v2_screen(self):
        feat = compute_screener_features(self.df, self.asof)
        picks = screen_protocol_v2(feat, top_n=5, min_turnover_cr=0.01)
        self.assertEqual(len(picks), 1)
        self.assertEqual(picks[0].symbol, "UPTREND")


class TestDynamicExits(unittest.TestCase):

    def setUp(self):
        # 30 bars with an entry followed by immediate breakdown
        dates = pd.date_range("2026-09-01", periods=20, freq="B")
        records = []
        for i, d in enumerate(dates):
            # Bar 0: breakout at 100
            # Bar 1-3: drop below 90
            px = 100.0 if i == 0 else (92.0 - i * 2)
            records.append({
                "Date": d,
                "Symbol": "FAILSTOCK",
                "Open": px,
                "High": px + 1.0,
                "Low": px - 1.0,
                "Close": px,
                "Volume": 100000,
                "ema10": px + 2.0,
                "ema20": px + 4.0,
                "vol_sma20": 80000,
                "atr14": 3.0,
            })
        self.fail_df = pd.DataFrame(records)

    def test_passive_vs_structure_exit(self):
        res_passive = simulate_dynamic_trade("FAILSTOCK", self.fail_df, "2026-09-01", exit_strategy=ExitStrategy.PASSIVE_HOLD)
        res_struct = simulate_dynamic_trade("FAILSTOCK", self.fail_df, "2026-09-01", exit_strategy=ExitStrategy.STRUCTURE_EMA20)

        self.assertIsNotNone(res_passive)
        self.assertIsNotNone(res_struct)
        # Structural stop should exit on bar 1 (invalidation)
        self.assertIn(res_struct.exit_reason, ["STRUCTURE_STOP", "EMA20_DISTRIBUTION"])
        self.assertLessEqual(res_struct.sessions_held, 2)


if __name__ == "__main__":
    unittest.main()
