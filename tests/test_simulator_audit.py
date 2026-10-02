"""Offline tests for the simulator, cost model, metrics and audit."""
import os
import sys
import unittest

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from protocol import audit, metrics  # noqa: E402
from protocol.config import canonical_hash, load_config  # noqa: E402
from protocol.costs import CostModel, shares_affordable  # noqa: E402
from protocol.simulator import simulate  # noqa: E402
from protocol.signals import TradeSignal  # noqa: E402

CFG = load_config()
MODEL = CostModel.from_config(CFG)


def bar(date, o, h, l, c):
    return {"Date": pd.Timestamp(date), "Open": o, "High": h, "Low": l, "Close": c, "Volume": 1e6, "Symbol": "X"}


def bars(days):
    return pd.DataFrame(days)


class CostTests(unittest.TestCase):
    def test_target_solves_to_net_pnl(self):
        shares = 10
        target = MODEL.target_price(100.0, shares, 0.15)
        self.assertAlmostEqual(MODEL.net_pnl_pct(100.0, target, shares), 0.15, places=6)

    def test_affordable_respects_buy_costs(self):
        self.assertGreaterEqual(shares_affordable(1000.0, 100.0, MODEL), 9)

    def test_hash_is_deterministic(self):
        cfg = load_config()
        self.assertEqual(canonical_hash({k: v for k, v in cfg.items() if not k.startswith("_")}), cfg["_hash"])


class SimulatorTests(unittest.TestCase):
    def _sig(self, stop=None, expected=100.0, entry="2024-01-03", stop_pct=0.07):
        return TradeSignal("t", "X", pd.Timestamp("2024-01-02"), pd.Timestamp(entry),
                           expected, stop=stop, stop_pct=stop_pct, meta={})

    def test_target_hit(self):
        target = MODEL.target_price(100.0, 9, 0.15)
        b = bars([bar("2024-01-02", 100, 101, 99, 100), bar("2024-01-03", 100, 150, 95, 120)])
        t = simulate(self._sig(), b, CFG, MODEL, 1000.0)
        self.assertEqual(t["exit_reason"], "TARGET")

    def test_gap_skip(self):
        b = bars([bar("2024-01-02", 100, 101, 99, 100), bar("2024-01-03", 120, 121, 119, 120)])
        t = simulate(self._sig(), b, CFG, MODEL, 1000.0)
        self.assertTrue(t.get("skipped"))
        self.assertEqual(t["exit_reason"], "SKIP_GAP")

    def test_stop_hit(self):
        b = bars([bar("2024-01-02", 100, 101, 99, 100), bar("2024-01-03", 100, 101, 90, 92)])
        t = simulate(self._sig(stop=95.0), b, CFG, MODEL, 1000.0)
        self.assertEqual(t["exit_reason"], "STOP")
        self.assertLess(t["net_pnl_pct"], 0)

    def test_same_day_stop_and_target_prefers_stop(self):
        target = MODEL.target_price(100.0, 9, 0.15)
        b = bars([bar("2024-01-02", 100, 101, 99, 100), bar("2024-01-03", 100, target + 10, 90, 100)])
        t = simulate(self._sig(stop=95.0), b, CFG, MODEL, 1000.0)
        self.assertEqual(t["exit_reason"], "STOP")


class MetricsTests(unittest.TestCase):
    def test_basic_rates(self):
        trades = [{"net_pnl_pct": 0.16, "exit_reason": "TARGET", "skipped": False, "mae": -0.01, "mfe": 0.18, "sessions_held": 3},
                  {"net_pnl_pct": -0.08, "exit_reason": "STOP", "skipped": False, "mae": -0.08, "mfe": 0.01, "sessions_held": 2}]
        m = metrics.cohort_metrics(trades, 0.15, 1, 200)
        self.assertEqual(m["N"], 2)
        self.assertAlmostEqual(m["WinRate"], 0.5)
        self.assertAlmostEqual(m["SafeRate"], 0.5)
        self.assertAlmostEqual(m["TailBreach"], 0.5)

    def test_portfolio_compounds(self):
        trades = [{"net_pnl_pct": 0.15, "exit_reason": "TARGET", "skipped": False,
                   "entry_date": pd.Timestamp("2024-01-01"), "exit_date": pd.Timestamp("2024-01-05")}]
        p = metrics.portfolio(trades, 1000.0, 0.15)
        self.assertAlmostEqual(p["final"], 1150.0)


class AuditTests(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(0)
        rows = []
        for sym in ("A", "B"):
            for i in range(120):
                c = 100 + np.cumsum(rng.normal(0, 1, 120))[i]
                rows.append({"Date": pd.bdate_range("2024-01-01", periods=120)[i], "Symbol": sym,
                             "Open": c, "High": c + 1, "Low": c - 1, "Close": c,
                             "Volume": float(rng.integers(1000, 5000))})
        self.hist = pd.DataFrame(rows)

    def test_truncation_and_shuffle_pass(self):
        self.assertTrue(audit.truncation_test(self.hist, 20, 0)["pass"])
        self.assertTrue(audit.shuffle_future_test(self.hist, 10, 0)["pass"])

    def test_static_scan_passes(self):
        self.assertTrue(audit.static_scan()["pass"])

    def test_cutoff(self):
        self.assertTrue(audit.cutoff_test({"A": self.hist[self.hist.Symbol == "A"]}, self.hist["Date"].max())["pass"])


if __name__ == "__main__":
    unittest.main()
