"""Offline tests for the INR 1,000 rotation experiment."""
import os
import sys
import unittest

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from protocol import rotation  # noqa: E402
from protocol.config import load_config  # noqa: E402
from protocol.features import build_features  # noqa: E402

CFG = load_config()


def _open_cfg() -> dict:
    c = {k: v for k, v in CFG.items()}
    c["liquidity"] = {"min_sessions": 0, "min_turnover20": 0.0, "min_price": 0.0}
    return c


def _bars():
    base = pd.DataFrame({
        "Date": pd.bdate_range("2024-01-01", periods=60), "Symbol": "X",
        "Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.0, "Volume": 5000.0})
    row = pd.DataFrame({"Date": [base["Date"].iloc[-1] + pd.offsets.BDay(1)], "Symbol": ["X"],
                        "Open": [101.0], "High": [106.0], "Low": [100.0],
                        "Close": [105.5], "Volume": [20000.0]})
    return pd.concat([base, row], ignore_index=True)


class LedgerCfgTests(unittest.TestCase):
    def test_rotation_run_cfg_disables_momentum_fail(self):
        sim = rotation.rotation_run_cfg(CFG)
        self.assertEqual(sim["run"]["hold_sessions"], CFG["rotation"]["max_holding_sessions"])
        self.assertLess(sim["run"]["momentum_fail_mfe"], 0.0)
        self.assertEqual(CFG["run"]["momentum_fail_mfe"], 0.05)  # original untouched

    def test_build_candidates_tags_organic(self):
        feat = build_features(_bars()).set_index("Date", drop=False)
        cands = rotation.build_candidates({"X": feat}, _open_cfg())
        self.assertFalse(cands.empty)
        self.assertEqual(cands.iloc[0]["tag"], "ORGANIC")
        self.assertEqual(int(cands.iloc[0]["rank"]), 1)
        self.assertIn("close", cands.columns)

    def test_summarize_empty_portfolio(self):
        m = rotation.summarize([], 1000.0, 1000.0, pd.DatetimeIndex(["2024-01-01"]))
        self.assertEqual(m["trades"], 0)
        self.assertEqual(m["total_return"], 0.0)
        self.assertEqual(m["time_in_cash"], 1.0)

    def test_summarize_rates_and_streak(self):
        trades = [
            {"net_pnl_pct": 0.15, "exit_reason": "TARGET", "net_pnl": 150.0, "sessions_held": 3,
             "entry_date": pd.Timestamp("2024-01-02"), "exit_date": pd.Timestamp("2024-01-05"),
             "costs": 18.0, "ambiguous": False},
            {"net_pnl_pct": -0.09, "exit_reason": "GAP_STOP", "net_pnl": -85.0, "sessions_held": 2,
             "entry_date": pd.Timestamp("2024-01-08"), "exit_date": pd.Timestamp("2024-01-09"),
             "costs": 16.0, "ambiguous": True},
        ]
        sessions = pd.bdate_range("2024-01-01", periods=10)
        m = rotation.summarize(trades, 1065.0, 1000.0, sessions)
        self.assertEqual(m["trades"], 2)
        self.assertEqual(m["target_first_rate"], 0.5)
        self.assertEqual(m["stop_first_rate"], 0.5)
        self.assertEqual(m["ambiguous_bars"], 1)
        self.assertEqual(m["total_fees"], 34.0)
        self.assertEqual(m["longest_losing_streak"], 1)
        self.assertLess(m["time_in_cash"], 1.0)


if __name__ == "__main__":
    unittest.main()
