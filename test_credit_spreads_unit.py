"""
Real unit tests for Bull Put Spread and Bear Call Spread features.

These tests validate:
1. Order structure and atomic execution protection
2. Monte Carlo P&L calculations
3. Risk metrics calculations
4. Scanner logic (with synthetic data)

Does NOT test:
- Live API calls
- Trade execution
- Real market data fetching
"""

import unittest
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import sys
import os

# Import the functions we're testing
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from strategy_lab import mc_pnl
from options_math import safe_annualize_roi


class TestOrderStructureSafety(unittest.TestCase):
    """Test that order creation methods use proper atomic execution structure."""
    
    def setUp(self):
        """Set up test fixtures."""
        from providers.schwab_trading import SchwabTrader
        self.trader = SchwabTrader()
    
    def test_bull_put_spread_order_structure(self):
        """Test that bull put spread orders have atomic execution protection."""
        order = self.trader.create_bull_put_spread_order(
            symbol="SPY",
            expiration="2025-12-19",
            sell_strike=580.0,
            buy_strike=575.0,
            quantity=1,
            limit_price=1.50
        )
        
        # Verify atomic execution structure
        self.assertEqual(order["orderType"], "NET_CREDIT", 
                        "Bull put spread must use NET_CREDIT order type")
        self.assertEqual(order["orderStrategyType"], "SINGLE",
                        "Bull put spread must use SINGLE strategy type for atomic execution")
        self.assertIn("orderLegCollection", order,
                     "Bull put spread must bundle legs in orderLegCollection")
        
        # Verify 2-leg structure
        legs = order["orderLegCollection"]
        self.assertEqual(len(legs), 2, "Bull put spread must have exactly 2 legs")
        
        # Verify leg instructions
        instructions = [leg["instruction"] for leg in legs]
        self.assertIn("SELL_TO_OPEN", instructions, "Must sell to open higher strike")
        self.assertIn("BUY_TO_OPEN", instructions, "Must buy to open lower strike")
    
    def test_bear_call_spread_order_structure(self):
        """Test that bear call spread orders have atomic execution protection."""
        order = self.trader.create_bear_call_spread_order(
            symbol="SPY",
            expiration="2025-12-19",
            sell_strike=600.0,
            buy_strike=605.0,
            quantity=1,
            limit_price=1.50
        )
        
        # Verify atomic execution structure
        self.assertEqual(order["orderType"], "NET_CREDIT",
                        "Bear call spread must use NET_CREDIT order type")
        self.assertEqual(order["orderStrategyType"], "SINGLE",
                        "Bear call spread must use SINGLE strategy type for atomic execution")
        self.assertIn("orderLegCollection", order,
                     "Bear call spread must bundle legs in orderLegCollection")
        
        # Verify 2-leg structure
        legs = order["orderLegCollection"]
        self.assertEqual(len(legs), 2, "Bear call spread must have exactly 2 legs")
        
        # Verify leg instructions
        instructions = [leg["instruction"] for leg in legs]
        self.assertIn("SELL_TO_OPEN", instructions, "Must sell to open lower strike")
        self.assertIn("BUY_TO_OPEN", instructions, "Must buy to open higher strike")
    
    def test_bull_put_spread_exit_order_structure(self):
        """Test that bull put spread exit orders have atomic execution protection."""
        order = self.trader.create_bull_put_spread_exit_order(
            symbol="SPY",
            expiration="2025-12-19",
            sell_strike=580.0,
            buy_strike=575.0,
            quantity=1,
            limit_price=0.50
        )
        
        # Verify atomic execution structure
        self.assertEqual(order["orderType"], "NET_DEBIT",
                        "Exit orders must use NET_DEBIT order type")
        self.assertEqual(order["orderStrategyType"], "SINGLE",
                        "Exit orders must use SINGLE strategy type for atomic execution")
        self.assertIn("orderLegCollection", order,
                     "Exit orders must bundle legs in orderLegCollection")
        
        # Verify closing instructions
        legs = order["orderLegCollection"]
        instructions = [leg["instruction"] for leg in legs]
        self.assertIn("BUY_TO_CLOSE", instructions, "Must close short position")
        self.assertIn("SELL_TO_CLOSE", instructions, "Must close long position")
    
    def test_bear_call_spread_exit_order_structure(self):
        """Test that bear call spread exit orders have atomic execution protection."""
        order = self.trader.create_bear_call_spread_exit_order(
            symbol="SPY",
            expiration="2025-12-19",
            sell_strike=600.0,
            buy_strike=605.0,
            quantity=1,
            limit_price=0.50
        )
        
        # Verify atomic execution structure
        self.assertEqual(order["orderType"], "NET_DEBIT",
                        "Exit orders must use NET_DEBIT order type")
        self.assertEqual(order["orderStrategyType"], "SINGLE",
                        "Exit orders must use SINGLE strategy type for atomic execution")
        self.assertIn("orderLegCollection", order,
                     "Exit orders must bundle legs in orderLegCollection")
        
        # Verify closing instructions
        legs = order["orderLegCollection"]
        instructions = [leg["instruction"] for leg in legs]
        self.assertIn("BUY_TO_CLOSE", instructions, "Must close short position")
        self.assertIn("SELL_TO_CLOSE", instructions, "Must close long position")


class TestMonteCarloPnL(unittest.TestCase):
    """Test Monte Carlo P&L calculations for credit spreads."""
    
    def test_bull_put_spread_max_profit(self):
        """Test that bull put spread can achieve max profit (net credit) when price stays above short strike."""
        params = {
            "S0": 600.0,           # Stock price well above strikes
            "days": 30,
            "iv": 0.20,
            "sell_strike": 580.0,  # Short put strike
            "buy_strike": 575.0,   # Long put strike
            "net_credit": 1.50     # Premium collected
        }
        
        # Run MC with zero drift and low volatility to keep price stable
        result = mc_pnl("BULL_PUT_SPREAD", params, n_paths=10000, mu=0.0, seed=42, rf=0.0)
        
        # Max profit should be net credit per share * 100
        max_profit_expected = 1.50 * 100
        
        # Most paths should achieve near-max profit since price starts well OTM
        p50 = result["pnl_p50"]
        self.assertGreater(p50, max_profit_expected * 0.8,
                          "Median P&L should be close to max profit when price is far OTM")
    
    def test_bull_put_spread_max_loss(self):
        """Test that bull put spread has correct max loss (spread width - net credit)."""
        params = {
            "S0": 570.0,           # Stock price below both strikes
            "days": 30,
            "iv": 0.01,            # Very low vol to keep price pinned
            "sell_strike": 580.0,
            "buy_strike": 575.0,
            "net_credit": 1.50
        }
        
        # Run MC with zero drift and low volatility
        result = mc_pnl("BULL_PUT_SPREAD", params, n_paths=10000, mu=0.0, seed=42, rf=0.0)
        
        # Max loss = (spread_width - net_credit) * 100
        spread_width = 580.0 - 575.0  # 5.0
        max_loss_expected = (spread_width - 1.50) * 100  # 3.50 * 100 = 350
        
        # When price is below both strikes, loss should approach max loss
        p5 = result["pnl_p5"]
        self.assertLess(p5, 0, "P5 should show losses when price is below strikes")
        self.assertGreater(p5, -max_loss_expected * 1.1,
                          "Losses should not exceed max loss significantly")
    
    def test_bull_put_spread_capital_requirement(self):
        """Test that capital requirement equals max loss."""
        params = {
            "S0": 590.0,
            "days": 30,
            "iv": 0.20,
            "sell_strike": 580.0,
            "buy_strike": 575.0,
            "net_credit": 1.50
        }
        
        result = mc_pnl("BULL_PUT_SPREAD", params, n_paths=1000, mu=0.0, seed=42, rf=0.0)
        
        # Capital = max loss = (spread_width - net_credit) * 100
        expected_capital = (5.0 - 1.50) * 100  # 350
        
        self.assertAlmostEqual(result["collateral"], expected_capital, places=2,
                              msg="Capital requirement should equal max loss")
    
    def test_bear_call_spread_max_profit(self):
        """Test that bear call spread can achieve max profit (net credit) when price stays below short strike."""
        params = {
            "S0": 580.0,           # Stock price well below strikes
            "days": 30,
            "iv": 0.20,
            "sell_strike": 600.0,  # Short call strike
            "buy_strike": 605.0,   # Long call strike
            "net_credit": 1.50     # Premium collected
        }
        
        result = mc_pnl("BEAR_CALL_SPREAD", params, n_paths=10000, mu=0.0, seed=42, rf=0.0)
        
        # Max profit should be net credit per share * 100
        max_profit_expected = 1.50 * 100
        
        # Most paths should achieve near-max profit since price starts well OTM
        p50 = result["pnl_p50"]
        self.assertGreater(p50, max_profit_expected * 0.8,
                          "Median P&L should be close to max profit when price is far OTM")
    
    def test_bear_call_spread_max_loss(self):
        """Test that bear call spread has correct max loss (spread width - net credit)."""
        params = {
            "S0": 610.0,           # Stock price above both strikes
            "days": 30,
            "iv": 0.01,            # Very low vol to keep price pinned
            "sell_strike": 600.0,
            "buy_strike": 605.0,
            "net_credit": 1.50
        }
        
        result = mc_pnl("BEAR_CALL_SPREAD", params, n_paths=10000, mu=0.0, seed=42, rf=0.0)
        
        # Max loss = (spread_width - net_credit) * 100
        spread_width = 605.0 - 600.0  # 5.0
        max_loss_expected = (spread_width - 1.50) * 100  # 3.50 * 100 = 350
        
        # When price is above both strikes, loss should approach max loss
        p5 = result["pnl_p5"]
        self.assertLess(p5, 0, "P5 should show losses when price is above strikes")
        self.assertGreater(p5, -max_loss_expected * 1.1,
                          "Losses should not exceed max loss significantly")
    
    def test_bear_call_spread_capital_requirement(self):
        """Test that capital requirement equals max loss."""
        params = {
            "S0": 590.0,
            "days": 30,
            "iv": 0.20,
            "sell_strike": 600.0,
            "buy_strike": 605.0,
            "net_credit": 1.50
        }
        
        result = mc_pnl("BEAR_CALL_SPREAD", params, n_paths=1000, mu=0.0, seed=42, rf=0.0)
        
        # Capital = max loss = (spread_width - net_credit) * 100
        expected_capital = (5.0 - 1.50) * 100  # 350
        
        self.assertAlmostEqual(result["collateral"], expected_capital, places=2,
                              msg="Capital requirement should equal max loss")
    
    def test_roi_calculations(self):
        """Test that ROI calculations are mathematically correct."""
        params = {
            "S0": 590.0,
            "days": 45,
            "iv": 0.20,
            "sell_strike": 580.0,
            "buy_strike": 575.0,
            "net_credit": 2.00
        }
        
        result = mc_pnl("BULL_PUT_SPREAD", params, n_paths=10000, mu=0.0, seed=42, rf=0.0)
        
        # Manual calculation
        # Max profit = 2.00 * 100 = 200
        # Capital = (5.0 - 2.0) * 100 = 300
        # ROI cycle = 200 / 300 = 0.6667 = 66.67%
        # ROI annualized = (1 + 0.6667) ^ (365/45) - 1
        
        expected_roi_cycle = 200.0 / 300.0
        expected_roi_ann = float(safe_annualize_roi(expected_roi_cycle, 45.0))
        
        # The p95 should be close to max ROI for OTM spreads
        p95_roi = result["roi_ann_p95"]
        self.assertGreater(p95_roi, expected_roi_ann * 0.5,
                          "P95 ROI should be significant for profitable scenarios")
    
    def test_monte_carlo_determinism(self):
        """Test that MC simulations are deterministic with fixed seed."""
        params = {
            "S0": 590.0,
            "days": 30,
            "iv": 0.20,
            "sell_strike": 580.0,
            "buy_strike": 575.0,
            "net_credit": 1.50
        }
        
        result1 = mc_pnl("BULL_PUT_SPREAD", params, n_paths=1000, mu=0.0, seed=12345, rf=0.0)
        result2 = mc_pnl("BULL_PUT_SPREAD", params, n_paths=1000, mu=0.0, seed=12345, rf=0.0)
        
        self.assertAlmostEqual(result1["pnl_p50"], result2["pnl_p50"], places=6,
                              msg="MC should be deterministic with fixed seed")
        self.assertAlmostEqual(result1["pnl_p5"], result2["pnl_p5"], places=6,
                              msg="MC should be deterministic with fixed seed")


class TestRiskMetrics(unittest.TestCase):
    """Test risk metric calculations."""
    
    def test_breakeven_calculation_bull_put_spread(self):
        """Test that breakeven is calculated correctly for bull put spreads."""
        # Breakeven = Short Strike - Net Credit
        sell_strike = 580.0
        net_credit = 1.50
        expected_breakeven = sell_strike - net_credit  # 578.50
        
        # Run MC to verify breakeven region
        params = {
            "S0": expected_breakeven,  # Price at breakeven
            "days": 30,
            "iv": 0.01,  # Low vol to keep price stable
            "sell_strike": sell_strike,
            "buy_strike": 575.0,
            "net_credit": net_credit
        }
        
        result = mc_pnl("BULL_PUT_SPREAD", params, n_paths=10000, mu=0.0, seed=42, rf=0.0)
        
        # At breakeven, expected P&L should be close to zero
        expected_pnl = result["pnl_expected"]
        self.assertAlmostEqual(expected_pnl, 0.0, delta=20.0,
                              msg="Expected P&L at breakeven should be near zero")
    
    def test_breakeven_calculation_bear_call_spread(self):
        """Test that breakeven is calculated correctly for bear call spreads."""
        # Breakeven = Short Strike + Net Credit
        sell_strike = 600.0
        net_credit = 1.50
        expected_breakeven = sell_strike + net_credit  # 601.50
        
        # Run MC to verify breakeven region
        params = {
            "S0": expected_breakeven,  # Price at breakeven
            "days": 30,
            "iv": 0.01,  # Low vol to keep price stable
            "sell_strike": sell_strike,
            "buy_strike": 605.0,
            "net_credit": net_credit
        }
        
        result = mc_pnl("BEAR_CALL_SPREAD", params, n_paths=10000, mu=0.0, seed=42, rf=0.0)
        
        # At breakeven, expected P&L should be close to zero
        expected_pnl = result["pnl_expected"]
        self.assertAlmostEqual(expected_pnl, 0.0, delta=20.0,
                              msg="Expected P&L at breakeven should be near zero")
    
    def test_probability_of_profit_estimate(self):
        """Test that we can estimate probability of profit from MC results."""
        params = {
            "S0": 590.0,
            "days": 30,
            "iv": 0.20,
            "sell_strike": 580.0,
            "buy_strike": 575.0,
            "net_credit": 1.50
        }
        
        result = mc_pnl("BULL_PUT_SPREAD", params, n_paths=50000, mu=0.0, seed=42, rf=0.0)
        
        # Calculate probability of profit
        profitable_paths = np.sum(result["pnl_paths"] > 0)
        total_paths = len(result["pnl_paths"])
        prob_profit = profitable_paths / total_paths
        
        # For OTM spread, probability of profit should be high
        self.assertGreater(prob_profit, 0.5,
                          "Probability of profit should be >50% for OTM credit spread")


class TestEdgeCases(unittest.TestCase):
    """Test edge cases and error handling."""
    
    def test_zero_credit_spread(self):
        """Test handling of zero net credit (should not be tradeable)."""
        params = {
            "S0": 590.0,
            "days": 30,
            "iv": 0.20,
            "sell_strike": 580.0,
            "buy_strike": 575.0,
            "net_credit": 0.0  # No credit
        }
        
        result = mc_pnl("BULL_PUT_SPREAD", params, n_paths=1000, mu=0.0, seed=42, rf=0.0)
        
        # With zero credit, if price stays above short strike, both expire worthless
        # P&L = 0 (no credit received, no loss). P50 should be <= 0.
        # Tail risk (P5) should show losses when price drops between strikes
        self.assertLessEqual(result["pnl_p50"], 0,
                            "Zero credit spread median should be zero or negative")
        self.assertLess(result["pnl_p5"], 0,
                       "Zero credit spread should show tail risk losses")
    
    def test_very_short_expiration(self):
        """Test spreads with very short expiration."""
        params = {
            "S0": 590.0,
            "days": 1,  # 1 day to expiration
            "iv": 0.20,
            "sell_strike": 580.0,
            "buy_strike": 575.0,
            "net_credit": 1.50
        }
        
        result = mc_pnl("BULL_PUT_SPREAD", params, n_paths=1000, mu=0.0, seed=42, rf=0.0)
        
        # Should still calculate correctly
        self.assertIsNotNone(result["pnl_p50"])
        self.assertTrue(np.isfinite(result["pnl_p50"]))
    
    def test_wide_spread(self):
        """Test spreads with wide strike spacing."""
        params = {
            "S0": 590.0,
            "days": 30,
            "iv": 0.20,
            "sell_strike": 580.0,
            "buy_strike": 550.0,  # 30-point wide spread
            "net_credit": 5.00
        }
        
        result = mc_pnl("BULL_PUT_SPREAD", params, n_paths=1000, mu=0.0, seed=42, rf=0.0)
        
        # Capital should reflect wide spread
        # Max loss = (30 - 5) * 100 = 2500
        expected_capital = (30.0 - 5.0) * 100
        self.assertAlmostEqual(result["collateral"], expected_capital, places=2,
                              msg="Capital should reflect wide spread width")


def run_tests():
    """Run all tests and print results."""
    print("="*70)
    print("CREDIT SPREADS UNIT TEST SUITE")
    print("="*70)
    print()
    
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestOrderStructureSafety))
    suite.addTests(loader.loadTestsFromTestCase(TestMonteCarloPnL))
    suite.addTests(loader.loadTestsFromTestCase(TestRiskMetrics))
    suite.addTests(loader.loadTestsFromTestCase(TestEdgeCases))
    
    # Run tests with verbose output
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Print summary
    print()
    print("="*70)
    print("TEST SUMMARY")
    print("="*70)
    print(f"Tests run: {result.testsRun}")
    print(f"Successes: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print()
    
    if result.wasSuccessful():
        print("✅ ALL TESTS PASSED")
    else:
        print("❌ SOME TESTS FAILED")
        if result.failures:
            print("\nFailures:")
            for test, traceback in result.failures:
                print(f"  - {test}")
        if result.errors:
            print("\nErrors:")
            for test, traceback in result.errors:
                print(f"  - {test}")
    
    print("="*70)
    
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(run_tests())
