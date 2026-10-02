"""Offline tests for the end-of-day candidate screen."""
import os
import sys
import unittest

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from protocol import screen  # noqa: E402
from protocol.config import load_config  # noqa: E402

CFG = load_config()


class TagTests(unittest.TestCase):
    def test_organic_when_contained_volume(self):
        self.assertEqual(screen.tag_state("A_ACCEPTED_EXPANSION", 3.0, 0.8, CFG), "ORGANIC")

    def test_trap_when_climactic_spike(self):
        self.assertEqual(screen.tag_state("A_ACCEPTED_EXPANSION", 9.0, 0.3, CFG), "TRAP_RISK")

    def test_pending_and_rejected_and_failed(self):
        self.assertEqual(screen.tag_state("B_PENDING_ACCEPTANCE", 2.0, 0.7, CFG), "PENDING")
        self.assertEqual(screen.tag_state("C_REJECTION_RECOVERY_PENDING", 2.0, 0.5, CFG), "REJECTED")
        self.assertEqual(screen.tag_state("D_FAILED_ACCEPTANCE", 4.0, 0.1, CFG), "TRAP_RISK")
        self.assertEqual(screen.tag_state(None, None, None, CFG), "NO_SETUP")

    def test_rank_prefers_least_extended(self):
        rows = pd.DataFrame([
            {"symbol": "AAA", "tag": "ORGANIC", "penetration": 2.0, "retention": 0.8, "stop_proxy": 0.02},
            {"symbol": "BBB", "tag": "ORGANIC", "penetration": 0.5, "retention": 0.7, "stop_proxy": 0.03},
            {"symbol": "CCC", "tag": "TRAP_RISK", "penetration": 0.1, "retention": 0.9, "stop_proxy": 0.01},
        ])
        picks = screen.rank_candidates(rows, CFG, top=2)
        self.assertEqual(picks["symbol"].tolist(), ["BBB", "AAA"])

    def test_rank_drops_candidates_with_too_wide_a_stop(self):
        rows = pd.DataFrame([
            {"symbol": "WIDE", "tag": "ORGANIC", "penetration": 0.1, "retention": 0.9,
             "stop_proxy": 0.25},
            {"symbol": "TIGHT", "tag": "ORGANIC", "penetration": 0.4, "retention": 0.7,
             "stop_proxy": 0.04},
        ])
        picks = screen.rank_candidates(rows, CFG, top=5)
        self.assertEqual(picks["symbol"].tolist(), ["TIGHT"])

    def test_story_is_empty_without_candidates(self):
        rows = pd.DataFrame([{"symbol": "X", "tag": "NO_SETUP", "date": "2026-10-01"}])
        self.assertTrue(any("Watchlist: empty" in ln for ln in screen.story(rows, CFG)))


if __name__ == "__main__":
    unittest.main()
