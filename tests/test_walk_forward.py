"""Unit tests for the Expanding Purged Walk-Forward & Deflated Sharpe Validation Engine."""
from __future__ import annotations

import unittest
import numpy as np
import pandas as pd

from protocol.walk_forward import (
    WalkForwardFold,
    compute_deflated_sharpe,
    run_walk_forward_evaluation,
    simulate_breakout_trades,
    summarize_trades,
)


class TestWalkForwardValidation(unittest.TestCase):

    def setUp(self):
        # Generate 3 years of daily synthetic stock price action
        dates = pd.date_range("2021-01-01", "2024-06-01", freq="B")
        records = []
        base_px = 100.0

        for i, d in enumerate(dates):
            # Introduce periodic breakout spikes every 40 sessions
            is_bo = (i % 40 == 35)
            px = base_px * (1.0 + 0.001 * i + (0.05 if is_bo else 0.0))
            vol = 500000 if is_bo else 100000

            records.append({
                "Date": d,
                "Symbol": "SYNTH_LEADER",
                "Open": px * 0.99,
                "High": px * 1.02,
                "Low": px * 0.98,
                "Close": px,
                "Volume": vol,
            })

        self.df = pd.DataFrame(records)

    def test_deflated_sharpe(self):
        # Positive returns array
        rets = np.array([0.02, -0.01, 0.03, 0.015, -0.005, 0.025, 0.01, -0.012, 0.04])
        res = compute_deflated_sharpe(rets, num_trials=9)
        self.assertIn("sharpe", res)
        self.assertIn("deflated_sharpe", res)
        self.assertIn("p_value", res)
        self.assertGreater(res["sharpe"], 0.0)

    def test_simulate_breakout_trades(self):
        trades = simulate_breakout_trades(self.df, rvol_thresh=1.2, cost_bps=25.0)
        self.assertIsInstance(trades, list)
        self.assertGreater(len(trades), 0)
        t = trades[0]
        self.assertEqual(t["symbol"], "SYNTH_LEADER")
        self.assertIn("return_pct", t)
        self.assertIn("is_win", t)

    def test_summarize_trades(self):
        mock_trades = [
            {"return_pct": 10.0, "r_multiple": 2.0, "is_win": True},
            {"return_pct": -4.0, "r_multiple": -0.8, "is_win": False},
            {"return_pct": 12.0, "r_multiple": 2.4, "is_win": True},
        ]
        summary = summarize_trades(mock_trades)
        self.assertEqual(summary["total_trades"], 3)
        self.assertAlmostEqual(summary["win_rate"], 66.7, places=1)
        self.assertGreater(summary["profit_factor"], 1.0)

    def test_walk_forward_evaluation(self):
        custom_folds = [
            WalkForwardFold(
                "Synthetic Fold 1", "Expansion Regime",
                "2021-01-01", "2022-12-31",
                "2023-01-01", "2024-05-30"
            )
        ]
        wf = run_walk_forward_evaluation(self.df, folds=custom_folds, rvol_thresh=1.2, cost_bps=25.0)
        self.assertIn("in_sample_win_rate", wf)
        self.assertIn("out_of_sample_win_rate", wf)
        self.assertIn("plateau_table", wf)
        self.assertIn("verdict", wf)
        self.assertEqual(len(wf["folds"]), 1)


if __name__ == "__main__":
    unittest.main()
