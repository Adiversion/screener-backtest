"""Unit tests for protocol.sniper_mode (Ultra-Conviction 65%+ Breakout Filter)."""
import unittest
import pandas as pd
from protocol.sniper_mode import evaluate_sniper_gates, screen_sniper_mode


class TestSniperMode(unittest.TestCase):
    def test_evaluate_sniper_gates_pass(self):
        row = pd.Series({
            "Symbol": "TEST_WINNER",
            "Close": 120.0,
            "High": 122.0,
            "Low": 115.0,
            "sma50": 110.0,
            "sma200": 95.0,
            "rs_rating": 92.0,
            "rvol20": 2.2,
            "ext_sma50": 0.09,
            "range20": 0.08,
            "r20": 118.0,
        })
        audit = evaluate_sniper_gates(row, deliv_pct=58.0, ind_rank=85.0)
        self.assertEqual(audit.passed_gates, 7)
        self.assertTrue(audit.is_sniper)
        self.assertGreater(audit.score, 70.0)

    def test_evaluate_sniper_gates_fail(self):
        row = pd.Series({
            "Symbol": "TEST_LAGGARD",
            "Close": 80.0,
            "High": 85.0,
            "Low": 75.0,
            "sma50": 90.0,
            "sma200": 100.0,
            "rs_rating": 25.0,
            "rvol20": 0.6,
            "ext_sma50": -0.11,
            "range20": 0.35,
            "r20": 92.0,
        })
        audit = evaluate_sniper_gates(row, deliv_pct=22.0, ind_rank=15.0)
        self.assertFalse(audit.is_sniper)
        self.assertLess(audit.passed_gates, 3)

    def test_screen_sniper_mode(self):
        feat = pd.DataFrame([
            {
                "Symbol": "TOP_PICK",
                "Close": 125.0,
                "High": 126.0,
                "Low": 120.0,
                "sma50": 110.0,
                "sma200": 95.0,
                "rs_rating": 90.0,
                "rvol20": 2.0,
                "ext_sma50": 0.13,
                "range20": 0.09,
                "r20": 122.0,
                "turnover20": 5e7,
                "ret20": 0.08,
                "adr20": 0.03,
            },
            {
                "Symbol": "POOR_PICK",
                "Close": 50.0,
                "High": 55.0,
                "Low": 48.0,
                "sma50": 60.0,
                "sma200": 70.0,
                "rs_rating": 30.0,
                "rvol20": 0.5,
                "ext_sma50": -0.15,
                "range20": 0.30,
                "r20": 65.0,
                "turnover20": 5e7,
                "ret20": -0.05,
                "adr20": 0.05,
            }
        ])
        results = screen_sniper_mode(feat, top_n=5)
        self.assertTrue(len(results) >= 1)
        self.assertEqual(results[0].symbol, "TOP_PICK")
        self.assertEqual(results[0].screener_name, "SNIPER_MODE_65")


if __name__ == "__main__":
    unittest.main()
