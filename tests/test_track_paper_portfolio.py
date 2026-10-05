"""Tests for headless paper portfolio tracker and USIC execution daemon."""
import tempfile
import unittest
from pathlib import Path

from scripts.track_paper_portfolio import (
    evaluate_staged_positions,
    load_portfolio,
    save_portfolio,
)


class TestTrackPaperPortfolio(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.portfolio_file = Path(self.temp_dir.name) / "test_portfolio.json"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_save_and_load_portfolio_local(self):
        port = {
            "initialCapital": 1000000.0,
            "cash": 900000.0,
            "positions": [{"symbol": "SYRMA", "shares": 100, "buyPrice": 1000.0, "stopPrice": 950.0}],
            "closedTrades": []
        }
        save_portfolio(port, self.portfolio_file, sync_cloud=False)
        loaded = load_portfolio(self.portfolio_file, sync_cloud=False)
        self.assertEqual(loaded["cash"], 900000.0)
        self.assertEqual(len(loaded["positions"]), 1)
        self.assertEqual(loaded["positions"][0]["symbol"], "SYRMA")

    def test_cloudflare_kv_cloud_sync(self):
        test_key = "unit_test_probe"
        port = {
            "initialCapital": 1000000.0,
            "cash": 950000.0,
            "positions": [{"symbol": "INFY", "shares": 10, "buyPrice": 1500.0, "stopPrice": 1400.0}],
            "closedTrades": []
        }
        # Save to Cloudflare KV Edge
        save_portfolio(port, self.portfolio_file, sync_cloud=True, key=test_key)
        # Load from Cloudflare KV Edge
        cloud_loaded = load_portfolio(self.portfolio_file, sync_cloud=True, key=test_key)
        self.assertEqual(cloud_loaded["cash"], 950000.0)
        self.assertEqual(cloud_loaded["positions"][0]["symbol"], "INFY")

    def test_stop_loss_trigger(self):
        port = {
            "initialCapital": 1000000.0,
            "cash": 900000.0,
            "positions": [{
                "symbol": "SYRMA",
                "shares": 100,
                "buyPrice": 1000.0,
                "stopPrice": 950.0,
                "initialStopPrice": 950.0,
                "target1Price": 1075.0,
                "scaledOut": False
            }],
            "closedTrades": []
        }
        prices = {"SYRMA": 940.0}
        updated, events = evaluate_staged_positions(port, prices)
        self.assertEqual(len(updated["positions"]), 0)
        self.assertEqual(len(updated["closedTrades"]), 1)
        self.assertEqual(updated["closedTrades"][0]["symbol"], "SYRMA")
        self.assertEqual(updated["closedTrades"][0]["pnl"], -6000.0)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["action"], "STOP")

    def test_target1_scale_out_and_breakeven_raise(self):
        """A single +8% tick runs the whole risk engine, in rule order.

        The guardian polls every 15 minutes, so it cannot assume another tick is
        coming: one evaluation applies every rule in sequence. The breakeven
        shield lifts the stop to entry, the trailing stop then locks profit
        above it (1000 + (1080 - 1000) * 0.55 = 1044), and the +1.5R target
        scales out half the position. The stop therefore ends ABOVE breakeven.
        """
        port = {
            "initialCapital": 1000000.0,
            "cash": 900000.0,
            "positions": [{
                "symbol": "DIXON",
                "shares": 100,
                "buyPrice": 1000.0,
                "stopPrice": 950.0,
                "initialStopPrice": 950.0,
                "target1Price": 1075.0,
                "target2Price": 1125.0,
                "scaledOut": False
            }],
            "closedTrades": []
        }
        prices = {"DIXON": 1080.0}
        updated, events = evaluate_staged_positions(port, prices)
        # Should retain remaining 50 shares
        self.assertEqual(len(updated["positions"]), 1)
        pos = updated["positions"][0]
        self.assertEqual(pos["shares"], 50)
        self.assertTrue(pos["scaledOut"])
        # Raised to breakeven, then trailed to lock the move (above entry).
        self.assertEqual(pos["stopPrice"], 1044.0)
        self.assertGreater(pos["stopPrice"], pos["buyPrice"])
        self.assertEqual(len(updated["closedTrades"]), 1)
        self.assertEqual(updated["closedTrades"][0]["shares"], 50)
        self.assertEqual(updated["closedTrades"][0]["pnl"], 4000.0)
        # Every rule that fired is reported, in evaluation order.
        self.assertEqual([e["action"] for e in events],
                         ["BREAKEVEN_SHIELD", "TRAIL_UPDATE", "TARGET1"])

    def test_target1_scale_out_raises_stop_above_breakeven(self):
        """Target 1 alone scales out half and lifts the stop to breakeven+0.5%.

        Price sits below both the +2% shield and the +3.5% peak trailing
        thresholds, so the +1.5R scale-out is the only action taken.
        """
        port = {
            "initialCapital": 1000000.0,
            "cash": 900000.0,
            "positions": [{
                "symbol": "DIXON",
                "shares": 100,
                "buyPrice": 1000.0,
                "stopPrice": 950.0,
                "initialStopPrice": 950.0,
                "target1Price": 1005.0,
                "target2Price": 1125.0,
                "scaledOut": False
            }],
            "closedTrades": []
        }
        updated, events = evaluate_staged_positions(port, {"DIXON": 1010.0})
        pos = updated["positions"][0]
        self.assertEqual(pos["shares"], 50)
        self.assertTrue(pos["scaledOut"])
        self.assertEqual(pos["stopPrice"], 1005.0)  # Breakeven + 0.5%
        self.assertEqual(len(updated["closedTrades"]), 1)
        self.assertEqual(updated["closedTrades"][0]["shares"], 50)
        self.assertEqual(updated["closedTrades"][0]["pnl"], 500.0)
        self.assertEqual([e["action"] for e in events], ["TARGET1"])


if __name__ == "__main__":
    unittest.main()
