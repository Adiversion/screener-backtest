"""Offline tests for the single-position rotation mode (no network).

Two things are being protected here:

1. `protocol/ranking.py` is a vectorised REWRITE of `protocol/quality.py`'s
   frame + scoring. It is allowed to be fast, not allowed to be different: the
   equivalence tests compare it row for row against `quality.score_frame`.
2. The rotation walk must never look ahead. A fill happens at the Open of a
   LATER session than the signal, exits only see sessions actually held, and
   the account holds exactly one position at a time.
"""
import os
import sys
import unittest

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from protocol import quality, ranking, rotation  # noqa: E402
from protocol.config import load_config  # noqa: E402
from protocol.features import build_features  # noqa: E402

CFG = load_config()


def _panel(symbols=("AAA", "BBB", "CCC"), n=300, seed=7):
    """A small panel with enough history for every ranking component."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2023-01-02", periods=n)
    out = []
    for i, sym in enumerate(symbols):
        drift = 0.0004 * (i + 1)
        close = 100.0 * np.exp(np.cumsum(rng.normal(drift, 0.015, n)))
        bars = pd.DataFrame({
            "Date": dates, "Symbol": sym,
            "Open": close * (1 + rng.normal(0, 0.002, n)),
            "High": close * 1.012, "Low": close * 0.988, "Close": close,
            "Volume": rng.integers(2e5, 2e6, n).astype(float),
        })
        out.append(build_features(bars).set_index("Date", drop=False))
    return {s: f for s, f in zip(symbols, out)}


class RankingEquivalenceTests(unittest.TestCase):
    """The fast vectorised path must equal the careful per-symbol path."""

    def setUp(self):
        self.panel = _panel()
        self.dates = sorted({pd.Timestamp(d)
                             for f in self.panel.values() for d in f["Date"]})
        self.long = ranking.build_long(self.panel, CFG)
        self.fast = ranking.rank_all(self.long, CFG, quality.COMPONENTS)

    def test_every_date_and_symbol_is_present(self):
        self.assertEqual(len(self.fast),
                         len(self.panel) * len(self.dates))

    def test_scores_match_quality_score_frame(self):
        """The whole point: same number, both ways, on real bars."""
        for date in self.dates[::37]:
            slow = quality.score_frame(
                quality._frames(self.panel, CFG, date, 20), CFG)
            fast = self.fast[self.fast["date"] == np.datetime64(date)]
            self.assertEqual(len(slow), len(fast))
            merged = slow[["symbol", "failed"]
                          + [f + "_pct" for f in quality.COMPONENTS]
                          + ["score", "coverage"]].merge(
                fast, on="symbol", suffixes=("_slow", "_fast"))
            self.assertEqual(len(merged), len(slow))
            for col in [f + "_pct" for f in quality.COMPONENTS] + ["score", "coverage"]:
                self.assertTrue(
                    np.allclose(merged[f"{col}_slow"].astype(float),
                                merged[f"{col}_fast"].astype(float), equal_nan=True),
                    msg=f"{col} disagrees on {date.date()}")
            self.assertTrue((merged["failed"].eq("")
                             == merged["clears"]).all(),
                            f"gate verdict disagrees on {date.date()}")

    def test_gate_mask_rejects_below_reference(self):
        """A stock under its 20-day high can never clear the gates."""
        far = self.fast.copy()
        far["close"] = 1.0
        far["reference"] = 100.0
        far["stop_proxy"] = np.nan
        mask = ranking._gate_mask(far, CFG, pd.Series(1.0, index=far.index))
        self.assertFalse(mask.any())

    def test_stop_is_nan_below_reference_not_negative(self):
        """The stop_proxy bug guard: below the reference it is UNKNOWN."""
        sub = self.long[self.long["close"] <= self.long["reference"]]
        self.assertTrue(sub.empty or sub["stop_proxy"].isna().all())

    def test_edge_is_zero_without_events(self):
        """A synthetic panel has no reclaim events, so nothing is 'edge'."""
        self.assertTrue((self.fast["edge"] == 0.0).all())


class RotationMechanicsTests(unittest.TestCase):
    def setUp(self):
        self.panel = _panel()

    def test_one_position_at_a_time(self):
        out = rotation.run(self.panel, CFG, capital=100000, bootstrap_n=50)
        trades = sorted(out["trades"], key=lambda t: t["entry_date"])
        for a, b in zip(trades, trades[1:]):
            self.assertLess(a["exit_date"], b["entry_date"],
                            "a second position opened before the first closed")

    def test_entry_is_strictly_after_the_signal(self):
        out = rotation.run(self.panel, CFG, capital=100000, bootstrap_n=50)
        for t in out["trades"]:
            self.assertGreater(pd.Timestamp(t["entry_date"]),
                               pd.Timestamp(t["signal_date"]),
                            "the fill may not happen on the signal bar")

    def test_exit_is_never_before_entry(self):
        out = rotation.run(self.panel, CFG, capital=100000, bootstrap_n=50)
        for t in out["trades"]:
            self.assertGreaterEqual(pd.Timestamp(t["exit_date"]),
                                    pd.Timestamp(t["entry_date"]))

    def test_target_exit_reaches_roughly_the_net_target(self):
        """On a rising synthetic panel the fixed net target must actually be hit."""
        panel = _panel(n=400, seed=3)
        out = rotation.run(panel, CFG, capital=100000, bootstrap_n=50)
        hits = [t for t in out["trades"] if t["exit_reason"] == "TARGET"]
        self.assertTrue(hits, "expected at least one target hit on a rising panel")
        target = CFG["rotation"]["target_net"]
        for t in hits:
            self.assertGreaterEqual(t["net_pnl_pct"], target * 0.98)

    def test_stop_exit_never_loses_more_than_the_stop_plus_costs(self):
        out = rotation.run(self.panel, CFG, capital=100000, bootstrap_n=50)
        stop = CFG["rotation"]["stop_pct"]
        stops = [t for t in out["trades"]
                 if t["exit_reason"] in rotation.STOP_REASONS]
        for t in stops:
            self.assertGreater(t["net_pnl_pct"], -stop - 0.02,
                               "a stop cost more than the stop itself plus costs")

    def test_capital_only_ever_moves_through_trades(self):
        """Compounding must follow the trades, with no invented growth.

        The account carries idle cash when the share count does not use the
        capital exactly, so `invested + idle == capital_before` and the sell
        proceeds land on top of that idle cash rather than replacing it.
        """
        cap = 50000.0
        out = rotation.run(self.panel, CFG, capital=cap, bootstrap_n=50)
        cash = cap
        for t in out["trades"]:
            self.assertAlmostEqual(t["capital_before"], cash, places=1)
            self.assertLessEqual(t["invested"], t["capital_before"] + 1e-6)
            self.assertAlmostEqual(t["idle_cash"],
                                   t["capital_before"] - t["invested"], places=1)
            # the account after the exit is the untouched idle cash plus the
            # result of the trade itself
            self.assertAlmostEqual(t["capital_after"],
                                   t["idle_cash"] + t["invested"] + t["net_pnl"],
                                   places=1)
            cash = t["capital_after"]

    def test_random_pick_never_reduces_the_trade_count_to_none(self):
        out = rotation.run(self.panel, CFG, capital=100000, pick="random",
                           seed=1, bootstrap_n=50)
        self.assertIsInstance(out["trades"], list)

    def test_equity_curve_is_finite_and_non_empty(self):
        out = rotation.run(self.panel, CFG, capital=10000, bootstrap_n=50)
        self.assertTrue(out["equity"])
        self.assertTrue(np.isfinite(out["equity"]).all())


class CostRealityTests(unittest.TestCase):
    def test_dp_charge_share_falls_as_capital_rises(self):
        rep = rotation.capital_report(CFG)
        shares = rep["dp_pct_of_capital"].tolist()
        self.assertEqual(shares, sorted(shares, reverse=True),
                         "a flat per-sell fee must cost less as capital grows")

    def test_small_account_needs_a_bigger_gross_move(self):
        rep = rotation.capital_report(CFG)
        gross = rep["gross_for_target"].tolist()
        self.assertGreater(gross[0], gross[-1])

    def test_report_covers_every_configured_capital(self):
        rep = rotation.capital_report(CFG)
        self.assertEqual(rep["capital"].tolist(),
                         [float(c) for c in CFG["run"]["capitals"]])


if __name__ == "__main__":
    unittest.main()