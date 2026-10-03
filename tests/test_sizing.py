"""Unit tests for volatility risk-parity position sizing and capital infusion."""
from __future__ import annotations

import unittest
from protocol.sizing import compute_volatility_allocation, allocate_portfolio_capital


class TestVolatilitySizing(unittest.TestCase):

    def test_risk_parity_high_vs_low_vol(self):
        # Total portfolio: Rs. 100,000. Risk per trade: 1% = Rs. 1,000.
        total_cap = 100000.0

        # High volatility stock: Price Rs. 100, ATR Rs. 10 (Stop dist = 2x ATR = Rs. 20)
        alloc_high = compute_volatility_allocation("HIVOL", 100.0, 10.0, total_cap, risk_per_trade_pct=0.01)
        # Low volatility stock: Price Rs. 100, ATR Rs. 2 (Stop dist = 2x ATR = Rs. 4)
        alloc_low = compute_volatility_allocation("LOWVOL", 100.0, 2.0, total_cap, risk_per_trade_pct=0.01)

        # High vol stock should get fewer shares than low vol stock
        self.assertLess(alloc_high.shares, alloc_low.shares)
        # Dollar risk should be roughly equal (approx Rs. 1000)
        self.assertAlmostEqual(alloc_high.risk_rupees, 1000.0, delta=100.0)

    def test_max_position_cap(self):
        # Extremely low ATR would naively want huge capital, capped at 20%
        total_cap = 100000.0
        alloc = compute_volatility_allocation("TINYVOL", 10.0, 0.05, total_cap, max_capital_per_stock_pct=0.20)
        self.assertLessEqual(alloc.capital_allocated, 20500.0)
        self.assertEqual(alloc.reason, "CAPPED_BY_MAX_POSITION")

    def test_portfolio_allocation_budget(self):
        total_cap = 100000.0
        candidates = [
            {"symbol": f"SYM_{i}", "entry_price": 200.0 + i * 50, "atr14": 10.0 + i}
            for i in range(15)
        ]
        allocs, remaining = allocate_portfolio_capital(candidates, total_cap, risk_per_trade_pct=0.01)
        total_used = sum(a.capital_allocated for a in allocs)
        self.assertLessEqual(total_used, total_cap)
        self.assertAlmostEqual(total_used + remaining, total_cap, places=2)
        self.assertGreater(len(allocs), 0)


if __name__ == "__main__":
    unittest.main()
