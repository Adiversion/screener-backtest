"""Unit tests for corporate events, regulatory surveillance, and dashboard data."""
from __future__ import annotations

import unittest
from protocol.corporate_events import (
    get_corporate_audit,
    load_board_meetings_map,
    load_corporate_actions_map,
    load_surveillance_map,
)


class TestCorporateEvents(unittest.TestCase):

    def test_surveillance_loader(self):
        surv = load_surveillance_map()
        self.assertIsInstance(surv, dict)
        if "VENUSREM" in surv:
            self.assertEqual(surv["VENUSREM"]["series"], "BE")
            self.assertEqual(surv["VENUSREM"]["band"], "5")

    def test_corporate_audit_venusrem(self):
        audit = get_corporate_audit("VENUSREM")
        self.assertEqual(audit["series"], "BE")
        self.assertTrue(audit["is_t2t"])
        self.assertIn("BE SERIES", " ".join(audit["badges"]))
        self.assertIn("upfront delivery", audit["warning_text"])

    def test_corporate_audit_dynamatech(self):
        audit = get_corporate_audit("DYNAMATECH")
        self.assertEqual(audit["series"], "EQ")
        self.assertFalse(audit["is_t2t"])
        self.assertEqual(audit["circuit_band"], "20")

    def test_board_meetings_and_actions(self):
        bm = load_board_meetings_map()
        ca = load_corporate_actions_map()
        self.assertIsInstance(bm, dict)
        self.assertIsInstance(ca, dict)
        if "DMART" in bm:
            audit = get_corporate_audit("DMART")
            self.assertTrue(audit["has_earnings_soon"])
            self.assertIn("EARNINGS", " ".join(audit["badges"]))


if __name__ == "__main__":
    unittest.main()
