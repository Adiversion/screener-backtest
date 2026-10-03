"""Unit tests for protocol.staged_execution (USIC Champion Staged Exit Simulator)."""
import unittest
import numpy as np
import pandas as pd
from protocol.staged_execution import simulate_staged_trade, evaluate_staged_execution


class TestStagedExecution(unittest.TestCase):
    def test_target_hit_and_breakeven(self):
        # Entry at 100. Target +7.5% = 107.5. Initial stop 95.
        # Day 1: High hits 108 -> Half 1 locked at +7.5% profit, stop raised to 100.
        # Day 2: Low pulls back to 99 -> Half 2 stopped out at 100 (breakeven).
        # Net return should be approximately 0.5 * 7.5% + 0.5 * 0% = +3.75% (A solid WIN!).
        opens = np.array([100.0, 105.0, 102.0])
        highs = np.array([108.0, 106.0, 103.0])
        lows = np.array([99.0, 98.0, 97.0])
        closes = np.array([105.0, 100.0, 98.0])

        res = simulate_staged_trade(
            opens, highs, lows, closes,
            stop_pct=0.05, target_multiple=1.5, cost_bps=0.0
        )
        self.assertTrue(res["target1_hit"])
        self.assertTrue(res["is_staged_win"])
        self.assertAlmostEqual(res["staged_ret"], 0.0375, places=3)
        # Note: Static 3-day hold would be (98 - 100)/100 = -2% (a LOSS!)
        self.assertFalse(res["is_static_win"])

    def test_initial_stop_hit(self):
        # Entry at 100. High never reaches 107.5. Low plunges to 94 (violates 95 stop).
        opens = np.array([100.0, 96.0])
        highs = np.array([101.0, 97.0])
        lows = np.array([94.0, 93.0])
        closes = np.array([95.0, 94.0])

        res = simulate_staged_trade(
            opens, highs, lows, closes,
            stop_pct=0.05, target_multiple=1.5, cost_bps=0.0
        )
        self.assertFalse(res["target1_hit"])
        self.assertFalse(res["is_staged_win"])
        self.assertAlmostEqual(res["staged_ret"], -0.05, places=3)

    def test_evaluate_staged_execution(self):
        dates = pd.bdate_range("2024-01-01", periods=30)
        history = pd.DataFrame({
            "Date": dates,
            "Symbol": "STOCK1",
            "Open": np.linspace(100, 120, 30),
            "High": np.linspace(102, 125, 30),
            "Low": np.linspace(99, 118, 30),
            "Close": np.linspace(101, 122, 30),
            "Volume": 100000,
        })
        trades = pd.DataFrame([{"Date": dates[0], "Symbol": "STOCK1"}])
        metrics = evaluate_staged_execution(trades, history, horizon_days=15)
        self.assertIn("staged_win_rate", metrics)
        self.assertIn("win_rate_boost", metrics)
        self.assertIn("profit_factor", metrics)
        self.assertIn("mathematical_expectancy_pct", metrics)


if __name__ == "__main__":
    unittest.main()
