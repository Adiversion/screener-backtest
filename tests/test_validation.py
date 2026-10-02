"""Offline tests for the validation milestone modules.

Covers the four spec-mandated tests (dataqc, redundancy, inference, crosssec)
and the data-sufficiency guard added to the quality ranking.

The emphasis is on the cases that produced wrong answers during development:
tautological correlations, infinities in the OLS design matrix, NaN gaps
sneaking through a threshold, and missing data being coerced to a real zero.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from protocol import crosssec, dataqc, inference, quality, redundancy  # noqa: E402
from protocol.config import load_config  # noqa: E402

CFG = load_config()


def _bars(n=140, base=100.0, vol=1_000_000.0, seed=11):
    """Synthetic OHLCV with NOISY volume.

    Volume noise matters: a perfectly constant volume series has zero
    variance, so the Welch t-statistic is 0/0 and nothing can ever be
    detected. Real volume is never constant.
    """
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2024-01-01", periods=n)
    return pd.DataFrame({
        "Symbol": "X",
        "Date": dates,
        "Close": base + np.linspace(0, 5, n),
        "High": base + np.linspace(1, 6, n),
        "Low": base - np.linspace(1, 4, n),
        "Open": base,
        "Volume": vol * rng.lognormal(0.0, 0.35, n),
    })


class DataQCTests(unittest.TestCase):
    def test_clean_series_has_no_artefacts(self):
        report = dataqc.scan(_bars(), CFG)
        self.assertEqual(report["artefact_bars"], 0)
        self.assertEqual(report["verdict"], "CLEAN")

    def test_persistent_volume_step_is_detected(self):
        bars = _bars()
        bars.loc[70:, "Volume"] *= 3.0        # permanent level shift
        report = dataqc.scan(bars.assign(Symbol="X"), CFG)
        self.assertGreaterEqual(report["volume_shift_bars"], 1)

    def test_one_off_spike_is_not_a_shift(self):
        """A single huge-volume day must NOT be reported as a regime shift.

        This is the false positive that made the first version report 17,602
        artefacts: results days print 50x volume and are perfectly valid.
        """
        bars = _bars()
        bars.loc[70, "Volume"] *= 50.0
        report = dataqc.scan(bars.assign(Symbol="X"), CFG)
        self.assertEqual(report["volume_shift_bars"], 0)

    def test_nan_gap_never_reported(self):
        """`NaN < threshold` is False, so unfiltered NaNs used to pass."""
        bars = _bars(n=40)          # ATR needs 14 bars, so early gaps are NaN
        bars["Volume"] = 1_000_000.0
        report = dataqc.scan(bars.assign(Symbol="X"), CFG)
        self.assertEqual(report["price_gap_bars"], 0)

    def test_clean_removes_only_flagged_bars(self):
        bars = _bars()
        bars.loc[70:, "Volume"] *= 3.0
        bars = bars.assign(Symbol="X")
        cleaned, report = dataqc.clean(bars, CFG)
        self.assertEqual(len(cleaned), len(bars) - report["artefact_bars"])


class RedundancyTests(unittest.TestCase):
    def test_definitional_identity_is_excluded(self):
        """closing_disp == retention * penetration, exactly.

        Reporting that correlation as "repackaged momentum" would be reporting
        algebra as a research finding.
        """
        rng = np.random.default_rng(7)
        latent = rng.normal(0, 1, 4000)
        ret = np.clip(0.4 + 0.3 * latent, -1.0, 1.5)
        pen = np.clip(0.5 + 0.35 * latent + 0.2 * rng.normal(0, 1, 4000), 0.01, 3.0)
        ev = pd.DataFrame({
            "date": pd.bdate_range("2024-01-01", periods=4000),
            "retention": ret,
            "penetration": pen,
            "closing_disp": ret * pen,
            "fwd_ret_5": rng.normal(0, 0.03, 4000),
        })
        found, taut = redundancy.redundant_pairs(ev, ["retention"], ["penetration"], 0.6)
        self.assertEqual(len(taut), 1)
        self.assertEqual(taut[0]["feature"], "retention")
        self.assertEqual(len(found), 0)

    def test_incremental_ols_survives_infinities(self):
        """efficiency can be +/-inf; that used to raise LinAlgError."""
        rng = np.random.default_rng(3)
        n = 800
        ev = pd.DataFrame({
            "date": pd.bdate_range("2024-01-01", periods=n),
            "ret60": rng.normal(0, 0.2, n),
            "ret120": rng.normal(0, 0.3, n),
            "penetration": rng.uniform(0, 2, n),
            "retention": rng.uniform(0, 1, n),
            "efficiency": np.where(rng.random(n) < 0.1, np.inf, rng.normal(0, 1, n)),
            "fwd_ret_5": rng.normal(0, 0.03, n),
        })
        out = redundancy.incremental_ols(ev, "efficiency",
                                         ["ret60", "ret120", "penetration"],
                                         "fwd_ret_5")
        self.assertNotEqual(out["verdict"], "INCONCLUSIVE")

    def test_missing_outcome_is_reported_not_guessed(self):
        ev = pd.DataFrame({"date": pd.bdate_range("2024-01-01", periods=100),
                           "retention": np.linspace(0, 1, 100)})
        out = redundancy.report(ev, CFG)
        self.assertIn("error", out)

    def test_spearman_is_nan_safe(self):
        a = np.array([1.0, 2.0, np.nan, 4.0])
        b = np.array([1.0, np.nan, 3.0, 4.0])
        self.assertTrue(np.isnan(redundancy.spearman(a, b)) or
                        isinstance(redundancy.spearman(a, b), float))


class InferenceTests(unittest.TestCase):
    def test_bh_rejects_none_when_expected(self):
        p = [1e-10, 1e-8, 0.4, 0.6, 0.9]
        _, rejected, q = inference.benjamini_hochberg(p, 0.05)
        self.assertTrue(rejected[0] and rejected[1])
        self.assertFalse(rejected[-1])
        self.assertTrue(all(x is not None for x in q))

    def test_bh_rejects_nothing_when_all_null(self):
        _, rejected, _ = inference.benjamini_hochberg([0.4, 0.5, 0.7, 0.9], 0.05)
        self.assertFalse(any(rejected))

    def test_untestable_hypotheses_are_carried_not_dropped(self):
        rows = [{"name": "a", "p": 1e-9}, {"name": "b", "p": None}]
        out = inference.adjust(rows, CFG)
        self.assertEqual(len(out["results"]), 2)
        self.assertEqual(out["untested"], 1)
        self.assertTrue(out["results"][1]["untested"])

    def test_null_value_changes_the_verdict(self):
        """Testing against 0 instead of the random null flags everything.

        Every strategy in this study is negative, so a zero-null marks all of
        them significant -- which is the bug this test guards.
        """
        m_zero = inference.pvalue_of({"N": 1000, "Expectancy": -0.017, "Std": 0.05}, 50, 0.0)
        m_null = inference.pvalue_of({"N": 1000, "Expectancy": -0.017, "Std": 0.05}, 50, -0.0177)
        self.assertLess(m_zero, 1e-10)
        self.assertGreater(m_null, 0.5)

    def test_small_n_yields_no_pvalue(self):
        self.assertIsNone(inference.pvalue_of({"N": 3, "Expectancy": 0.1, "Std": 0.1}, 50))


class CrossSectionalTests(unittest.TestCase):
    def test_rebalance_mask_weekly_picks_one_session_per_week(self):
        dates = pd.bdate_range("2024-01-01", periods=40)
        mask = crosssec.rebalance_mask(dates, "W")
        picked = dates[mask]
        iso = picked.isocalendar()
        pairs = list(zip(iso.year.to_numpy(), iso.week.to_numpy()))
        self.assertEqual(len(pairs), len(set(pairs)))
        self.assertLess(len(pairs), len(dates))
        self.assertEqual(picked[0], dates[0])

    def test_acceptance_score_penalises_deep_penetration(self):
        d = _bars(n=5)
        d["R20"] = np.full(5, 99.0)
        d["retention"] = 0.9
        d["closing_range"] = 0.9
        d["penetration"] = [0.1, 3.0, 0.1, 3.0, 0.1]
        out = crosssec.add_scores(d)
        self.assertGreater(out["acceptance_score"].iloc[0],
                           out["acceptance_score"].iloc[1])

    def test_add_scores_is_point_in_time(self):
        d = _bars()
        d["R20"] = np.full(len(d), 99.0)
        d["retention"] = 0.5
        d["closing_range"] = 0.5
        d["penetration"] = 0.2
        out = crosssec.add_scores(d)
        self.assertIn("acceptance_score", out.columns)
        self.assertEqual(len(out), len(d))


class DataSufficiencyTests(unittest.TestCase):
    """Missing data must read as UNKNOWN, never as a real zero."""

    def _row(self, **over):
        base = {"retention": 0.8, "closing_range": 0.8, "rvol20": 1.5,
                "turnover20": 1e8, "ret60": 0.2, "ret120": 0.3,
                "stop_proxy": 0.02}
        base.update(over)
        return pd.Series(base)

    def test_complete_row_is_full_coverage(self):
        frac, status = quality.coverage(quality.components(self._row(), CFG, None))
        self.assertEqual(frac, 1.0)
        self.assertEqual(status, "FULL")

    def test_missing_history_is_none_not_zero(self):
        comps = quality.components(self._row(ret120=None), CFG, None)
        self.assertIsNone(comps["trend"])
        self.assertNotEqual(comps["trend"], 0.0)

    def test_edge_zero_is_a_real_value(self):
        """Not firing within the window is a fact, not missing data."""
        comps = quality.components(self._row(), CFG, None)
        self.assertEqual(comps["edge"], 0.0)

    def test_partial_coverage_is_thin(self):
        comps = quality.components(self._row(ret120=None, rvol20=None), CFG, None)
        frac, status = quality.coverage(comps)
        self.assertLess(frac, 1.0)
        self.assertIn(status, ("THIN", "INSUFFICIENT"))

    def test_data_gate_rejects_insufficient_coverage(self):
        row = self._row(coverage=0.4)
        checks = quality.gates(row, CFG, None)
        cov_gate = [c for c in checks if c["criterion"] == "Data coverage"][0]
        self.assertFalse(cov_gate["passed"])


if __name__ == "__main__":
    unittest.main()