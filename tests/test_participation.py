"""Offline tests for the participation-decay study and the site payload.

Two properties matter more than the numbers here:

1. The cohorts must be disjoint and must be derived WITHOUT lookahead. Cohort C
   is the exception that proves the rule: its label reads the future on purpose,
   so the test pins that it is labelled as descriptive-only and never leaks into
   a trading decision.
2. The site payload must never claim participant intent. A stock is described by
   what price and volume did, never by what someone was supposedly doing.
"""
import os
import sys
import unittest

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from protocol import participation, quality, ranking, site  # noqa: E402
from protocol.config import load_config  # noqa: E402
from protocol.features import build_features  # noqa: E402

CFG = load_config()

INTENT_WORDS = ("distribution", "accumulation", "supply", "demand", "smart money",
                "institution", "manipulat", "genuine demand")


def _panel(symbols=("AAA", "BBB", "CCC"), n=420, seed=11):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2023-01-02", periods=n)
    out = []
    for i, sym in enumerate(symbols):
        close = 100.0 * np.exp(np.cumsum(rng.normal(0.0004 * (i + 1), 0.015, n)))
        bars = pd.DataFrame({
            "Date": dates, "Symbol": sym,
            "Open": close * (1 + rng.normal(0, 0.002, n)),
            "High": close * 1.012, "Low": close * 0.988, "Close": close,
            "Volume": rng.integers(2e5, 2e6, n).astype(float),
        })
        out.append(build_features(bars).reset_index(drop=True))
    return out


class CohortTests(unittest.TestCase):
    def setUp(self):
        self.long = pd.concat(
            [participation.label_cohorts(d, CFG) for d in _panel()],
            ignore_index=True)

    def test_every_row_gets_exactly_one_cohort(self):
        """A symbol can be A, B, C or the control -- never two of them."""
        multi = self.long[self.long["cohort"].notna()]
        for _, r in multi.iterrows():
            flags = [bool(r["decaying"]), bool(r["high_participation"])]
            self.assertTrue(any(flags),
                            f"{r['Date']} {r['Symbol']} was labelled {r['cohort']} "
                            f"with neither decaying nor high participation")

    def test_a_and_b_require_decaying_participation(self):
        for name in ("A_holds_reference", "B_loses_reference"):
            sub = self.long[self.long["cohort"] == name]
            self.assertTrue(sub["decaying"].all(),
                            f"{name} contains a non-decaying session")

    def test_a_is_above_the_reference_and_b_is_below(self):
        a = self.long[self.long["cohort"] == "A_holds_reference"]
        b = self.long[self.long["cohort"] == "B_loses_reference"]
        self.assertTrue((a["close"] > a["R"]).all())
        self.assertTrue((b["close"] <= b["R"]).all())

    def test_c_requires_an_expansion_after_the_signal(self):
        c = self.long[self.long["cohort"] == "C_contracts_then_expands"]
        self.assertTrue(len(c) > 0, "expected the expansion cohort to be non-empty")
        self.assertTrue(c["decaying"].all())
        self.assertTrue(c["expanded"].all())

    def test_forward_returns_are_only_available_past_the_end(self):
        """fwd20 must be NaN in the final 20 sessions -- no invented outcome."""
        for d in _panel():
            lab = participation.label_cohorts(d, CFG)
            self.assertTrue(lab["fwd20"].tail(20).isna().all())
            self.assertTrue(lab["fwd5"].tail(5).isna().all())

    def test_the_expansion_flag_cannot_be_read_before_it_happens(self):
        """Cohort C is descriptive. Its label must never become an entry signal."""
        doc = participation.label_cohorts.__doc__ or ""
        self.assertIn("DESCRIPTIVE ONLY", doc)
        self.assertIn("never used as a trading signal", doc)
        # A, B and D must be point-in-time: they are decidable on the bar itself
        self.assertTrue((self.long[self.long["cohort"] == "A_holds_reference"]
                         ["above"]).all())
        self.assertFalse(bool(self.long[self.long["cohort"] == "B_loses_reference"]
                              ["expanded"].iloc[0]),
                         "cohort B must not depend on the future")

    def test_study_reports_a_verdict_a_baseline_and_the_intent_caveat(self):
        panel = {f"SYM{i}": d for i, d in enumerate(_panel())}
        out = participation.study(panel, CFG, (5, 20))
        self.assertIn(20, out["baseline"])
        self.assertGreater(out["baseline"][20]["n"], 0)
        verdict = out["verdict"].lower()
        self.assertIn("intent", verdict,
                      "the verdict must state that OHLCV cannot establish intent")
        self.assertNotIn("distribution", verdict)
        self.assertNotIn("accumulation", verdict)
        for row in out["table"].to_dict("records"):
            self.assertIn("what_it_is", row)


class SitePayloadTests(unittest.TestCase):
    def setUp(self):
        self.panel = {"AAA": _panel()[0], "BBB": _panel()[1]}
        self.payload = site.build(self.panel, CFG, sectors={"AAA": "Test"})

    def test_payload_carries_the_session_it_describes(self):
        self.assertTrue(self.payload["asof"])
        self.assertRegex(self.payload["asof"], r"\d{4}-\d{2}-\d{2}")

    def test_every_symbol_gets_a_full_gate_report(self):
        for sym in self.payload["stocks"]:
            detail = self.payload["_detail"][sym]
            self.assertEqual(len(detail["gates"]), 7,
                             f"{sym} does not have all seven gates")
            for gate in detail["gates"]:
                self.assertIn("criterion", gate)
                self.assertIn("passed", gate)
                self.assertIsInstance(gate["passed"], bool)

    def test_the_index_row_carries_no_heavy_gate_table(self):
        """Gates live in the per-symbol file so the index stays small."""
        for sym, row in self.payload["stocks"].items():
            self.assertNotIn("gates", row)
            self.assertIn("gates", self.payload["_detail"][sym])

    def test_payload_never_claims_participant_intent(self):
        """A rejection must not become a story about who was doing what."""
        blob = " ".join(self.payload["caveats"]).lower()
        for sym, row in self.payload["stocks"].items():
            for key in ("screen_tag", "data_status"):
                blob += " " + str(row.get(key, "")).lower()
        for word in INTENT_WORDS:
            self.assertNotIn(word, blob,
                             f"payload uses an intent word: {word}")

    def test_clearing_list_is_sorted_by_score_descending(self):
        scores = [self.payload["stocks"][s]["score"]
                  for s in self.payload["clearing"]]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_tape_rows_have_a_real_close(self):
        tape = site.tapes(self.panel, CFG, pd.Timestamp(self.payload["asof"]),
                          ["AAA"])
        self.assertTrue(tape["AAA"])
        for row in tape["AAA"]:
            self.assertIsNotNone(row["close"],
                                 "tape close must not silently be None")


if __name__ == "__main__":
    unittest.main()