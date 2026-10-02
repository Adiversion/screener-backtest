"""Offline tests for the end-of-day rotation screen."""
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
            {"symbol": "AAA", "tag": "ORGANIC", "penetration": 2.0, "retention": 0.8},
            {"symbol": "BBB", "tag": "ORGANIC", "penetration": 0.5, "retention": 0.7},
            {"symbol": "CCC", "tag": "TRAP_RISK", "penetration": 0.1, "retention": 0.9},
        ])
        picks = screen.rank_rotation(rows, CFG, top=2)
        self.assertEqual(picks["symbol"].tolist(), ["BBB", "AAA"])

    def test_story_stays_in_cash_without_candidates(self):
        rows = pd.DataFrame([{"symbol": "X", "tag": "NO_SETUP", "date": "2026-10-01"}])
        self.assertTrue(any("STAY IN CASH" in ln for ln in screen.story(rows, CFG)))


if __name__ == "__main__":
    unittest.main()
