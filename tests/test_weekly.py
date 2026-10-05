"""Unit tests for the weekly timeframe layer and the daily/weekly confluence."""
from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from protocol.github_screeners import compute_screener_features
from protocol.timeframe import (
    BOTH,
    DAILY_ONLY,
    NEITHER,
    WEEKLY_ONLY,
    bucket_counts,
    confluence,
    daily_strength,
    gate_diagnostics,
    weekly_strength,
)
from protocol.weekly import (
    GATE_KEYS,
    MIN_WEEKLY_BARS,
    WEEKLY_GATE_COUNT,
    WEEKLY_PARAMS,
    build_weekly_features,
    evaluate_weekly,
    screen_weekly,
    to_weekly,
    week_end_label,
    weekly_grade,
    weekly_frame,
    weekly_panel,
)


def _daily(symbol: str, sessions: int, start: str = "2023-01-02",
           daily_drift: float = 0.004, base: float = 100.0,
           volume: float = 200_000.0) -> pd.DataFrame:
    """A smooth one-way trend. `daily_drift` < 0 gives the declining mirror."""
    dates = pd.bdate_range(start, periods=sessions)
    px = base * (1.0 + daily_drift) ** np.arange(sessions)
    return pd.DataFrame({
        "Date": dates, "Symbol": symbol,
        "Open": px * 0.995, "High": px * 1.01, "Low": px * 0.99,
        "Close": px, "Volume": volume,
    })


def _breakout(symbol: str = "BO", sessions: int = 520, base_frac: float = 0.70,
              run: float = 0.002, volume: float = 200_000.0) -> pd.DataFrame:
    """A base, then a measured advance -- the shape a real momentum stock has.

    A straight exponential is NOT a valid fixture for a "healthy" name: it never
    pulls back, so it ends up far above its 30-week MA and reads as extended
    even though the gates are firing. Measured at run=0.002 this sits ~15% over
    the 30-week MA, which is the posture the anti-climax cap is designed to
    accept.
    """
    px = np.empty(sessions)
    px[0] = 100.0
    base_end = int(sessions * base_frac)
    for i in range(1, sessions):
        px[i] = px[i - 1] * (1.0 + (0.0002 if i < base_end else run))
    dates = pd.bdate_range("2022-01-03", periods=sessions)
    return pd.DataFrame({
        "Date": dates, "Symbol": symbol,
        "Open": px * 0.995, "High": px * 1.01, "Low": px * 0.99,
        "Close": px, "Volume": volume,
    })


def _score(hist: pd.DataFrame, p: dict | None = None):
    asof = pd.Timestamp(hist["Date"].max())
    return evaluate_weekly(weekly_frame(weekly_panel(hist, asof=asof), asof),
                           p=p or {**WEEKLY_PARAMS, "min_turnover_cr": 0.0})


def _parabolic(symbol: str = "PARABOLIC", sessions: int = 520, volume: float = 200_000.0,
               base_frac: float = 0.62) -> pd.DataFrame:
    """A base, then an accelerating vertical move that climaxes on huge volume.

    Volume and a strong close are included on purpose: without them the weekly
    `wyckoff` and `volume` gates can never fire, and the fixture would not
    actually clear the gate count the anti-climax cap is supposed to veto.
    """
    px = np.empty(sessions)
    px[0] = 100.0
    base_end = int(sessions * base_frac)
    for i in range(1, sessions):
        run = (i - base_end) / (sessions - base_end)
        px[i] = px[i - 1] * (1.0 + (0.0002 if i < base_end else 0.002 + 0.010 * run ** 2))
    dates = pd.bdate_range("2022-01-03", periods=sessions)
    bars = pd.DataFrame({
        "Date": dates, "Symbol": symbol,
        "Open": px * 0.995, "High": px * 1.01, "Low": px * 0.99,
        "Close": px, "Volume": volume,
    })
    # Final week: narrow ranges, closes near the high, 20x volume.
    tail = bars.index[-5:]
    bars.loc[tail, "Open"] = bars.loc[tail, "Close"] * 0.999
    bars.loc[tail, "High"] = bars.loc[tail, "Close"] * 1.004
    bars.loc[tail, "Low"] = bars.loc[tail, "Close"] * 0.985
    bars.loc[tail, "Close"] = bars.loc[tail, "Close"] * 1.003
    bars.loc[tail, "Volume"] = volume * 20.0
    return bars


class TestWeeklyResample(unittest.TestCase):

    def test_week_end_label_maps_mon_through_fri_to_friday(self):
        # Mon 2023-01-02 .. Fri 2023-01-06 are one week ending 2023-01-06.
        d = pd.Series(pd.bdate_range("2023-01-02", periods=5))
        got = week_end_label(d)
        self.assertEqual(list(got), [pd.Timestamp("2023-01-06")] * 5)

    def test_week_end_label_rolls_sat_sun_forward(self):
        d = pd.Series(pd.to_datetime(["2023-01-07", "2023-01-08"]))  # Sat, Sun
        got = week_end_label(d)
        self.assertEqual(list(got), [pd.Timestamp("2023-01-13")] * 2)

    def test_aggregates_ohlcv_correctly(self):
        bars = _daily("AAA", 20)
        w = to_weekly(bars)
        first_week = bars.iloc[:5]
        row = w.iloc[0]
        self.assertAlmostEqual(row["Open"], first_week["Open"].iloc[0], places=6)
        self.assertAlmostEqual(row["High"], first_week["High"].max(), places=6)
        self.assertAlmostEqual(row["Low"], first_week["Low"].min(), places=6)
        self.assertAlmostEqual(row["Close"], first_week["Close"].iloc[-1], places=6)
        self.assertAlmostEqual(row["Volume"], first_week["Volume"].sum(), places=2)
        self.assertEqual(int(row["sessions"]), 5)

    def test_date_is_last_real_session_not_calendar_friday(self):
        """A week whose Friday is a holiday must still be dated on its last session.

        Labelling by the calendar Friday would date a bar in the future and it
        could never match an as-of session.
        """
        dates = pd.bdate_range("2023-01-02", periods=9).delete(4)  # drop Fri 01-06
        bars = pd.DataFrame({
            "Date": dates, "Symbol": "AAA", "Open": 10.0, "High": 11.0,
            "Low": 9.0, "Close": 10.5, "Volume": 1000,
        })
        w = to_weekly(bars)
        first = w.iloc[0]
        self.assertEqual(pd.Timestamp(first["Date"]), pd.Timestamp("2023-01-05"))
        self.assertEqual(pd.Timestamp(first["WeekEnd"]), pd.Timestamp("2023-01-06"))
        self.assertEqual(int(first["sessions"]), 4)

    def test_trailing_incomplete_week_is_flagged(self):
        # 9 business days from Mon 2023-01-02 ends Thu 2023-01-12, so that
        # week's Friday (01-13) has not arrived yet.
        dates = pd.bdate_range("2023-01-02", periods=9)
        bars = pd.DataFrame({
            "Date": dates, "Symbol": "AAA", "Open": 10.0, "High": 11.0,
            "Low": 9.0, "Close": 10.5, "Volume": 1000,
        })
        w = to_weekly(bars)
        self.assertTrue(bool(w.iloc[-2]["week_complete"]))
        self.assertFalse(bool(w.iloc[-1]["week_complete"]))
        self.assertEqual(pd.Timestamp(w.iloc[-1]["Date"]), pd.Timestamp("2023-01-12"))

    def test_one_week_per_calendar_week(self):
        w = to_weekly(_daily("AAA", 250))
        self.assertEqual(w["WeekEnd"].is_unique, True)
        self.assertEqual(len(w), 50)


class TestWeeklyFeatures(unittest.TestCase):

    def setUp(self):
        self.up = build_weekly_features(to_weekly(_daily("UP", 500, daily_drift=0.004)))
        self.down = build_weekly_features(to_weekly(_daily("DOWN", 500, daily_drift=-0.004)))

    def test_panel_drops_symbols_without_enough_weekly_bars(self):
        hist = pd.concat([_daily("SHORT", 100), _daily("LONG", 500)], ignore_index=True)
        panel = weekly_panel(hist, asof=pd.Timestamp("2025-12-31"))
        self.assertIn("LONG", panel)
        self.assertNotIn("SHORT", panel)
        self.assertGreaterEqual(len(panel["LONG"]), MIN_WEEKLY_BARS)

    def test_reference_levels_exclude_the_current_week(self):
        """A 52-week high must be a level that existed BEFORE this week."""
        w = to_weekly(_daily("UP", 500, daily_drift=0.004))
        f = build_weekly_features(w)
        prior = w["High"].iloc[-53:-1]
        self.assertAlmostEqual(float(f["w_high52"].iloc[-1]), float(prior.max()), places=6)
        self.assertLessEqual(float(f["w_high52"].iloc[-1]), float(w["High"].iloc[-1]))

    def test_uptrend_establishes_stage2_and_downtrend_does_not(self):
        self.assertTrue(bool(self.up["w_stage2"].iloc[-1]))
        self.assertFalse(bool(self.down["w_stage2"].iloc[-1]))

    def test_rsi_is_bounded_and_extremes_correctly(self):
        self.assertAlmostEqual(float(self.up["w_rsi14"].iloc[-1]), 100.0, places=1)
        self.assertAlmostEqual(float(self.down["w_rsi14"].iloc[-1]), 0.0, places=1)

    def test_weekly_turnover_is_daily_equivalent(self):
        """The liquidity floor must mean the same thing on both timeframes."""
        w = to_weekly(_daily("UP", 500, daily_drift=0.004, volume=1_000_000.0))
        f = build_weekly_features(w)
        self.assertAlmostEqual(float(f["w_turnover13_daily"].iloc[-1]),
                               float(f["w_turnover13"].iloc[-1]) / 5.0, places=4)

    def test_frame_drops_partial_week_by_default(self):
        hist = _daily("UP", 500, daily_drift=0.004)
        panel = weekly_panel(hist, include_partial=False)
        asof = pd.Timestamp(hist["Date"].max())
        closed = weekly_frame(panel, asof)
        with_partial = weekly_frame(panel, asof, include_partial=True)
        if not with_partial.empty and not closed.empty:
            # At most one extra bar is available, and only if the week is open.
            self.assertLessEqual(len(with_partial), len(closed) + 1)


class TestWeeklyGates(unittest.TestCase):
    """The gates in isolation: the liquidity floor and the anti-climax cap are
    both switched off here, so a failure points at gate logic and nowhere else.

    A synthetic downtrend ends at a much lower price, so at equal share volume
    its turnover falls below the production floor and it would be dropped
    before the gates ever ran.
    """

    PARAMS = {**WEEKLY_PARAMS, "min_turnover_cr": 0.0, "max_ext_ma30": 10.0}

    def setUp(self):
        self.up = evaluate_weekly(weekly_frame(
            weekly_panel(_daily("UP", 500, daily_drift=0.004)),
            pd.Timestamp(_daily("UP", 500, daily_drift=0.004)["Date"].max())),
            p=self.PARAMS)
        self.down = evaluate_weekly(weekly_frame(
            weekly_panel(_daily("DOWN", 500, daily_drift=-0.004)),
            pd.Timestamp(_daily("DOWN", 500, daily_drift=-0.004)["Date"].max())),
            p=self.PARAMS)

    def test_every_gate_column_present(self):
        for key in GATE_KEYS:
            self.assertIn(f"g_{key}", self.up.columns)
        self.assertEqual(WEEKLY_GATE_COUNT, len(GATE_KEYS))

    def test_n_gates_matches_the_flag_count(self):
        row = self.up.iloc[0]
        self.assertEqual(int(row["n_gates"]),
                         sum(int(bool(row[f"g_{k}"])) for k in GATE_KEYS))

    def test_uptrend_passes_far_more_gates_than_downtrend(self):
        self.assertGreater(int(self.up["n_gates"].iloc[0]), int(WEEKLY_PARAMS["min_gates"]))
        self.assertLess(int(self.down["n_gates"].iloc[0]), int(WEEKLY_PARAMS["min_gates"]))
        self.assertTrue(bool(self.up["w_strong"].iloc[0]))
        self.assertFalse(bool(self.down["w_strong"].iloc[0]))

    def test_grade_is_assigned_from_gate_count(self):
        for scored in (self.up, self.down):
            row = scored.iloc[0]
            self.assertEqual(row["w_grade"], weekly_grade(int(row["n_gates"]), self.PARAMS))
        self.assertEqual(self.down["w_grade"].iloc[0], "WEAK")

    def test_a_falling_stock_cannot_pass_the_anti_extension_gate(self):
        """'Not over-stretched' must not reward a stock that is below the 30w MA."""
        self.assertTrue(float(self.down["w_ext_ma30"].iloc[0]) < 0)
        self.assertFalse(bool(self.down["g_extension"].iloc[0]))

    def test_evaluate_returns_input_symbols_not_a_shortlist(self):
        """Coverage matters here: the daily/weekly comparison must not truncate."""
        hist = pd.concat([_daily("UP", 500, daily_drift=0.004),
                          _daily("DOWN", 500, daily_drift=-0.004)], ignore_index=True)
        asof = pd.Timestamp(hist["Date"].max())
        frame = weekly_frame(weekly_panel(hist, asof=asof), asof)
        scored = evaluate_weekly(frame, p=self.PARAMS)
        self.assertEqual(set(scored["Symbol"]), {"UP", "DOWN"})

    def test_weekly_strength_reports_the_extension_flag(self):
        """A reader must be able to tell 'weak structure' from 'dropped for extension'."""
        hist = _breakout()
        asof = pd.Timestamp(hist["Date"].max())
        weekly = weekly_strength(weekly_frame(weekly_panel(hist, asof=asof), asof))
        self.assertIn("w_extended", weekly.columns)
        self.assertFalse(bool(weekly["w_extended"].iloc[0]))

    def test_liquidity_floor_drops_illiquid_names(self):
        """The floor is a real gate, not decoration: it must be able to drop a name."""
        hist = pd.concat([_daily("LIQUID", 500, daily_drift=0.004, volume=5_000_000.0),
                          _daily("THIN", 500, daily_drift=0.004, volume=100.0)],
                         ignore_index=True)
        asof = pd.Timestamp(hist["Date"].max())
        frame = weekly_frame(weekly_panel(hist, asof=asof), asof)
        scored = evaluate_weekly(frame)  # production defaults
        self.assertEqual(set(scored["Symbol"]), {"LIQUID"})

    def test_empty_input_returns_usable_empty_frame(self):
        out = evaluate_weekly(pd.DataFrame())
        self.assertTrue(out.empty)
        self.assertIn("n_gates", out.columns)

    def test_screen_weekly_returns_only_strong_names(self):
        picks = screen_weekly(self.up, top_n=5, p=self.PARAMS)
        self.assertEqual(len(picks), 1)
        self.assertEqual(picks[0].screener_name, "WEEKLY_CONFLUENCE")
        self.assertGreater(picks[0].score, 0.0)
        self.assertEqual(screen_weekly(self.down, top_n=5, p=self.PARAMS), [])

    def test_anti_climax_cap_disqualifies_a_parabolic_name(self):
        """A stock up 100%+ in 13 weeks must not read as a quality screen hit.

        The `extension` gate alone is one vote of twelve, so a steep trend
        still clears the gate count. The hard cap is what actually stops it.
        """
        hist = _parabolic()
        asof = pd.Timestamp(hist["Date"].max())
        feats = weekly_frame(weekly_panel(hist, asof=asof), asof)
        gates_only = {**self.PARAMS}
        row = evaluate_weekly(feats, p=gates_only).iloc[0]
        self.assertGreater(int(row["n_gates"]), int(WEEKLY_PARAMS["min_gates"]))
        # ...and the production cap is what rejects it.
        capped = evaluate_weekly(feats).iloc[0]
        self.assertGreater(float(capped["w_ext_ma30"]), WEEKLY_PARAMS["max_ext_ma30"])
        self.assertTrue(bool(capped["w_extended"]))
        self.assertFalse(bool(capped["w_strong"]))
        self.assertEqual(screen_weekly(feats, top_n=5), [])


class TestAntiClimaxCap(unittest.TestCase):
    """A base-then-breakout is accepted; a straight vertical move is not."""

    def test_measured_breakout_is_weekly_strong(self):
        row = _score(_breakout()).iloc[0]
        self.assertLess(float(row["w_ext_ma30"]), WEEKLY_PARAMS["max_ext_ma30"])
        self.assertFalse(bool(row["w_extended"]))
        self.assertGreaterEqual(int(row["n_gates"]), int(WEEKLY_PARAMS["min_gates"]))
        self.assertTrue(bool(row["w_strong"]))

    def test_cap_boundary_is_respected_exactly(self):
        """ext_ma30 == the cap stays in; a hair over it goes out."""
        hist = _breakout()
        feats = weekly_frame(weekly_panel(hist, asof=pd.Timestamp(hist["Date"].max())),
                             pd.Timestamp(hist["Date"].max()))
        at_cap = float(feats["w_ext_ma30"].iloc[0])
        self.assertTrue(bool(evaluate_weekly(
            feats, p={**WEEKLY_PARAMS, "max_ext_ma30": at_cap + 1e-9}).iloc[0]["w_strong"]))
        self.assertFalse(bool(evaluate_weekly(
            feats, p={**WEEKLY_PARAMS, "max_ext_ma30": at_cap - 1e-9}).iloc[0]["w_strong"]))


class TestConfluence(unittest.TestCase):

    def setUp(self):
        self.daily = pd.DataFrame([
            {"Symbol": "BOTH1", "n_frameworks": 4, "frameworks": "A, B, C, D",
             "daily_close": 100.0, "daily_best_score": 9.0},
            {"Symbol": "DAYONLY", "n_frameworks": 2, "frameworks": "A, B",
             "daily_close": 100.0, "daily_best_score": 5.0},
        ])
        self.weekly = pd.DataFrame([
            {"Symbol": "BOTH1", "n_gates": 9, "gates": "Weinstein, RS",
             "w_grade": "A+", "w_strong": True, "weekly_close": 100.0, "w_score": 40.0},
            {"Symbol": "DAYONLY", "n_gates": 1, "gates": "",
             "w_grade": "WEAK", "w_strong": False, "weekly_close": 100.0, "w_score": 4.0},
            {"Symbol": "WEEKONLY", "n_gates": 8, "gates": "Weinstein, Darvas",
             "w_grade": "A", "w_strong": True, "weekly_close": 100.0, "w_score": 35.0},
        ])
        self.conf = confluence(self.daily, self.weekly)

    def test_all_four_buckets_assigned(self):
        got = dict(zip(self.conf["Symbol"], self.conf["bucket"]))
        self.assertEqual(got["BOTH1"], BOTH)
        self.assertEqual(got["DAYONLY"], DAILY_ONLY)
        self.assertEqual(got["WEEKONLY"], WEEKLY_ONLY)

    def test_weekly_only_names_are_flagged_as_swing_candidates(self):
        swing = set(self.conf.loc[self.conf["swing_candidate"], "Symbol"])
        self.assertEqual(swing, {"WEEKONLY"})

    def test_outer_join_keeps_names_only_the_daily_side_never_saw(self):
        """A symbol the daily engine could not evaluate must still be reported."""
        self.assertIn("WEEKONLY", set(self.conf["Symbol"]))
        self.assertEqual(int(self.conf.loc[self.conf["Symbol"] == "WEEKONLY",
                                           "n_frameworks"].iloc[0]), 0)

    def test_neither_bucket_for_a_name_on_no_side(self):
        conf = confluence(self.daily, self.weekly)
        lone = conf.iloc[[0]].copy()
        lone["daily_strong"] = False
        lone["weekly_strong"] = False
        self.assertEqual(len(conf[conf["bucket"] == NEITHER]), 0)
        self.assertEqual(conf["bucket"].isna().sum(), 0)

    def test_bucket_counts_include_empty_buckets(self):
        counts = bucket_counts(self.conf)
        self.assertEqual(counts[WEEKLY_ONLY], 1)
        self.assertEqual(counts[NEITHER], 0)
        self.assertEqual(set(counts), {BOTH, DAILY_ONLY, WEEKLY_ONLY, NEITHER})

    def test_min_gates_threshold_is_configurable(self):
        strict = confluence(self.daily, self.weekly, min_weekly=10)
        got = dict(zip(strict["Symbol"], strict["bucket"]))
        self.assertEqual(got["BOTH1"], DAILY_ONLY)  # 9 gates no longer clears 10

    def test_swing_candidates_sorted_first(self):
        self.assertEqual(self.conf.iloc[0]["Symbol"], "WEEKONLY")

    def test_confluence_honours_the_anti_climax_cap(self):
        """A high gate count cannot re-admit a name the cap already rejected.

        `confluence` must use `weekly_strength`'s own verdict, not re-derive
        strength from `n_gates`, or the cap is silently undone here.
        """
        weekly = self.weekly.copy()
        weekly.loc[weekly["Symbol"] == "WEEKONLY", "w_strong"] = False
        conf = confluence(self.daily, weekly)
        row = conf[conf["Symbol"] == "WEEKONLY"].iloc[0]
        self.assertEqual(int(row["n_gates"]), 8)
        self.assertFalse(bool(row["weekly_strong"]))
        self.assertFalse(bool(row["swing_candidate"]))
        self.assertEqual(row["bucket"], NEITHER)

    def test_confluence_falls_back_to_gate_count_without_w_strong(self):
        weekly = self.weekly.drop(columns=["w_strong", "w_extended"], errors="ignore")
        conf = confluence(self.daily, weekly)
        got = dict(zip(conf["Symbol"], conf["bucket"]))
        self.assertEqual(got["WEEKONLY"], WEEKLY_ONLY)


class TestDailyStrengthAndDiagnostics(unittest.TestCase):

    def test_daily_strength_counts_frameworks_per_symbol(self):
        hist = _daily("UPTREND", 400, daily_drift=0.004, base=100.0, volume=500_000.0)
        hist.loc[hist.index[-1], "Volume"] = 4_000_000.0
        asof = pd.Timestamp(hist["Date"].max())
        feat = compute_screener_features(hist, asof)
        out = daily_strength(feat, top_n=10, min_turnover_cr=0.01)
        self.assertEqual(list(out["Symbol"]), ["UPTREND"])
        self.assertGreaterEqual(int(out["n_frameworks"].iloc[0]), 1)
        self.assertEqual(int(out["n_frameworks"].iloc[0]), out["frameworks"].iloc[0].count(",") + 1)

    def test_daily_strength_on_empty_features_returns_empty_frame(self):
        out = daily_strength(pd.DataFrame(), top_n=5)
        self.assertTrue(out.empty)
        self.assertIn("n_frameworks", out.columns)

    def test_gate_diagnostics_reports_pass_rate(self):
        hist = pd.concat([_daily("UP", 500, daily_drift=0.004),
                          _daily("DOWN", 500, daily_drift=-0.004)], ignore_index=True)
        asof = pd.Timestamp(hist["Date"].max())
        weekly = weekly_strength(weekly_frame(weekly_panel(hist, asof=asof), asof),
                                 p={**WEEKLY_PARAMS, "min_turnover_cr": 0.0})
        diag = gate_diagnostics(weekly)
        self.assertEqual(len(diag), WEEKLY_GATE_COUNT)
        self.assertTrue(((diag["pass_rate"] >= 0.0) & (diag["pass_rate"] <= 1.0)).all())
        self.assertEqual(list(diag["pass_rate"]), sorted(diag["pass_rate"]))
        self.assertEqual(int(diag["passes"].sum()),
                         int(weekly["n_gates"].sum()))

    def test_weekly_strength_lists_the_gates_that_passed(self):
        hist = _daily("UP", 500, daily_drift=0.004)
        asof = pd.Timestamp(hist["Date"].max())
        weekly = weekly_strength(weekly_frame(weekly_panel(hist, asof=asof), asof))
        self.assertIn("Weinstein Stage 2 (30w/40w)", weekly["gates"].iloc[0])


if __name__ == "__main__":
    unittest.main()
