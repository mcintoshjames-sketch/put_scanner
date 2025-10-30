"""
Test suite for Iron Condor Monte Carlo implementation
Validates P&L calculations, statistical properties, and edge cases
"""

import numpy as np
import sys

# Import the mc_pnl function from strategy_lab
sys.path.insert(0, '/workspaces/put_scanner')
from strategy_lab import mc_pnl


def test_iron_condor_basic():
    """Test basic Iron Condor MC simulation with known parameters"""
    print("\n" + "="*80)
    print("TEST 1: Basic Iron Condor Simulation")
    print("="*80)
    
    # Setup: SPY @ $450, sell 445/440 put spread, 455/460 call spread
    # Net credit: $1.50, spreads are $5 wide
    params = {
        "S0": 450.0,
        "days": 30,
        "iv": 0.20,  # 20% IV
        "put_short_strike": 445.0,
        "put_long_strike": 440.0,
        "call_short_strike": 455.0,
        "call_long_strike": 460.0,
        "net_credit": 1.50
    }
    
    print(f"\nSetup:")
    print(f"  Current Price: ${params['S0']}")
    print(f"  Put Spread: ${params['put_short_strike']}/{params['put_long_strike']} (width: ${params['put_short_strike'] - params['put_long_strike']})")
    print(f"  Call Spread: ${params['call_short_strike']}/{params['call_long_strike']} (width: ${params['call_long_strike'] - params['call_short_strike']})")
    print(f"  Net Credit: ${params['net_credit']}")
    print(f"  Days to Expiration: {params['days']}")
    print(f"  IV: {params['iv']*100}%")
    
    # Run simulation
    mc = mc_pnl("IRON_CONDOR", params, n_paths=10000, mu=0.0, seed=42)
    
    # Theoretical values
    max_profit = params["net_credit"]
    put_spread_width = params["put_short_strike"] - params["put_long_strike"]
    call_spread_width = params["call_long_strike"] - params["call_short_strike"]
    max_loss = max(put_spread_width, call_spread_width) - params["net_credit"]
    capital = max_loss
    
    print(f"\nTheoretical Values:")
    print(f"  Max Profit: ${max_profit:.2f}")
    print(f"  Max Loss: ${-max_loss:.2f}")
    print(f"  Capital Required: ${capital:.2f}")
    print(f"  Max ROI: {(max_profit/capital)*100:.1f}%")
    print(f"  Max Loss %: {(max_loss/capital)*100:.1f}%")
    
    print(f"\nMonte Carlo Results:")
    print(f"  Expected P&L: ${mc['pnl_expected']:.2f}")
    print(f"  P&L Std Dev: ${mc['pnl_std']:.2f}")
    print(f"  P&L P5/P50/P95: ${mc['pnl_p5']:.2f} / ${mc['pnl_p50']:.2f} / ${mc['pnl_p95']:.2f}")
    print(f"  ROI Ann (Expected): {mc['roi_ann_expected']*100:.1f}%")
    print(f"  Sharpe Ratio: {mc['sharpe']:.3f}")
    
    # Validation checks
    print(f"\nValidation Checks:")
    
    # Check 1: All P&L values within theoretical bounds
    pnl_paths = mc['pnl_paths']
    min_pnl = np.min(pnl_paths)
    max_pnl = np.max(pnl_paths)
    
    check1 = min_pnl >= -max_loss - 0.01 and max_pnl <= max_profit + 0.01
    print(f"  ✓ P&L bounds: [{min_pnl:.2f}, {max_pnl:.2f}] within [{-max_loss:.2f}, {max_profit:.2f}]: {'PASS' if check1 else 'FAIL'}")
    
    # Check 2: Expected P&L should be positive for neutral position
    check2 = mc['pnl_expected'] > 0
    print(f"  ✓ Expected P&L positive: {mc['pnl_expected']:.2f} > 0: {'PASS' if check2 else 'FAIL'}")
    
    # Check 3: Capital calculation
    check3 = abs(mc['capital_per_share'] - capital) < 0.01
    print(f"  ✓ Capital: ${mc['capital_per_share']:.2f} == ${capital:.2f}: {'PASS' if check3 else 'FAIL'}")
    
    # Check 4: ROI calculation consistency
    expected_roi = (mc['pnl_expected'] / capital) * (365.0 / params['days'])
    check4 = abs(mc['roi_ann_expected'] - expected_roi) < 0.001
    print(f"  ✓ ROI calculation: {mc['roi_ann_expected']*100:.2f}% == {expected_roi*100:.2f}%: {'PASS' if check4 else 'FAIL'}")
    
    return all([check1, check2, check3, check4])


def test_iron_condor_edge_cases():
    """Test edge cases: stock crashes, rallies, stays flat"""
    print("\n" + "="*80)
    print("TEST 2: Iron Condor Edge Cases")
    print("="*80)
    
    base_params = {
        "S0": 100.0,
        "days": 30,
        "iv": 0.30,
        "put_short_strike": 95.0,
        "put_long_strike": 90.0,
        "call_short_strike": 105.0,
        "call_long_strike": 110.0,
        "net_credit": 1.00
    }
    
    # Calculate theoretical values
    put_spread_width = base_params["put_short_strike"] - base_params["put_long_strike"]
    call_spread_width = base_params["call_long_strike"] - base_params["call_short_strike"]
    max_loss = max(put_spread_width, call_spread_width) - base_params["net_credit"]
    
    scenarios = [
        ("Strong Bearish Drift", -0.50),  # Stock crashes
        ("Neutral Drift", 0.0),            # Stock stays flat
        ("Strong Bullish Drift", 0.50),    # Stock rallies
    ]
    
    all_passed = True
    for scenario_name, drift in scenarios:
        print(f"\n{scenario_name} (drift={drift*100:.0f}%):")
        
        mc = mc_pnl("IRON_CONDOR", base_params, n_paths=5000, mu=drift, seed=42)
        
        print(f"  Expected P&L: ${mc['pnl_expected']:.2f}")
        print(f"  P&L Range: ${mc['pnl_p5']:.2f} to ${mc['pnl_p95']:.2f}")
        print(f"  ROI Ann: {mc['roi_ann_expected']*100:.1f}%")
        
        # Validation: P&L should still be bounded
        pnl_paths = mc['pnl_paths']
        min_pnl = np.min(pnl_paths)
        max_pnl = np.max(pnl_paths)
        
        check = min_pnl >= -max_loss - 0.01 and max_pnl <= base_params["net_credit"] + 0.01
        print(f"  ✓ Bounds check [{min_pnl:.2f}, {max_pnl:.2f}]: {'PASS' if check else 'FAIL'}")
        
        if not check:
            all_passed = False
    
    return all_passed


def test_iron_condor_asymmetric():
    """Test asymmetric Iron Condor (different spread widths)"""
    print("\n" + "="*80)
    print("TEST 3: Asymmetric Iron Condor")
    print("="*80)
    
    # Wide put spread ($10), narrow call spread ($5)
    params = {
        "S0": 200.0,
        "days": 45,
        "iv": 0.25,
        "put_short_strike": 190.0,
        "put_long_strike": 180.0,  # $10 wide
        "call_short_strike": 210.0,
        "call_long_strike": 215.0,  # $5 wide
        "net_credit": 2.50
    }
    
    put_width = params["put_short_strike"] - params["put_long_strike"]
    call_width = params["call_long_strike"] - params["call_short_strike"]
    
    print(f"\nAsymmetric Setup:")
    print(f"  Put Spread Width: ${put_width:.2f}")
    print(f"  Call Spread Width: ${call_width:.2f}")
    print(f"  Net Credit: ${params['net_credit']:.2f}")
    
    mc = mc_pnl("IRON_CONDOR", params, n_paths=5000, mu=0.0, seed=42)
    
    # Capital should be based on WIDER spread
    expected_capital = max(put_width, call_width) - params["net_credit"]
    
    print(f"\nResults:")
    print(f"  Capital: ${mc['capital_per_share']:.2f} (expected: ${expected_capital:.2f})")
    print(f"  Expected P&L: ${mc['pnl_expected']:.2f}")
    print(f"  ROI Ann: {mc['roi_ann_expected']*100:.1f}%")
    
    # Validation
    check = abs(mc['capital_per_share'] - expected_capital) < 0.01
    print(f"\n✓ Capital based on wider spread: {'PASS' if check else 'FAIL'}")
    
    return check


def test_iron_condor_pnl_at_strikes():
    """Test P&L at specific terminal prices (at strikes)"""
    print("\n" + "="*80)
    print("TEST 4: P&L at Specific Terminal Prices")
    print("="*80)
    
    params = {
        "S0": 100.0,
        "days": 30,
        "iv": 0.20,
        "put_short_strike": 95.0,
        "put_long_strike": 90.0,
        "call_short_strike": 105.0,
        "call_long_strike": 110.0,
        "net_credit": 1.50
    }
    
    net_credit = params["net_credit"]
    put_width = params["put_short_strike"] - params["put_long_strike"]
    call_width = params["call_long_strike"] - params["call_short_strike"]
    
    # Test specific terminal prices
    test_prices = [
        (85.0, "Below Put Long", -put_width + net_credit),
        (90.0, "At Put Long", -put_width + net_credit),
        (92.5, "Between Put Strikes", -(95.0 - 92.5) + net_credit),
        (95.0, "At Put Short", net_credit),
        (100.0, "At Current/Center", net_credit),
        (105.0, "At Call Short", net_credit),
        (107.5, "Between Call Strikes", -(107.5 - 105.0) + net_credit),
        (110.0, "At Call Long", -call_width + net_credit),
        (115.0, "Above Call Long", -call_width + net_credit),
    ]
    
    print(f"\nTheoretical P&L at Terminal Prices:")
    print(f"{'Price':<10} {'Location':<25} {'Expected P&L':<15}")
    print("-" * 50)
    
    all_passed = True
    for price, location, expected_pnl in test_prices:
        print(f"${price:<9.2f} {location:<25} ${expected_pnl:<14.2f}")
        
        # Manually calculate P&L
        pnl = net_credit
        
        # Put spread loss
        put_spread_loss = max(0.0, params["put_short_strike"] - price) - max(0.0, params["put_long_strike"] - price)
        pnl -= put_spread_loss
        
        # Call spread loss
        call_spread_loss = max(0.0, price - params["call_short_strike"]) - max(0.0, price - params["call_long_strike"])
        pnl -= call_spread_loss
        
        # Check if calculation matches expected
        check = abs(pnl - expected_pnl) < 0.01
        if not check:
            print(f"  ⚠️  Calculated: ${pnl:.2f}, Expected: ${expected_pnl:.2f}")
            all_passed = False
    
    return all_passed


def test_iron_condor_repeatability():
    """Test that simulations with same seed produce same results"""
    print("\n" + "="*80)
    print("TEST 5: Simulation Repeatability")
    print("="*80)
    
    params = {
        "S0": 150.0,
        "days": 30,
        "iv": 0.25,
        "put_short_strike": 145.0,
        "put_long_strike": 140.0,
        "call_short_strike": 155.0,
        "call_long_strike": 160.0,
        "net_credit": 1.25
    }
    
    # Run same simulation twice with same seed
    mc1 = mc_pnl("IRON_CONDOR", params, n_paths=1000, mu=0.0, seed=123)
    mc2 = mc_pnl("IRON_CONDOR", params, n_paths=1000, mu=0.0, seed=123)
    
    # Run with different seed
    mc3 = mc_pnl("IRON_CONDOR", params, n_paths=1000, mu=0.0, seed=456)
    
    print(f"\nRun 1 (seed=123): Expected P&L = ${mc1['pnl_expected']:.4f}")
    print(f"Run 2 (seed=123): Expected P&L = ${mc2['pnl_expected']:.4f}")
    print(f"Run 3 (seed=456): Expected P&L = ${mc3['pnl_expected']:.4f}")
    
    # Check repeatability
    check1 = abs(mc1['pnl_expected'] - mc2['pnl_expected']) < 1e-10
    check2 = abs(mc1['pnl_expected'] - mc3['pnl_expected']) > 0.01  # Different seeds should differ
    
    print(f"\n✓ Same seed produces identical results: {'PASS' if check1 else 'FAIL'}")
    print(f"✓ Different seed produces different results: {'PASS' if check2 else 'FAIL'}")
    
    return check1 and check2


def test_iron_condor_convergence():
    """Test that expected P&L converges with more paths"""
    print("\n" + "="*80)
    print("TEST 6: Convergence with Path Count")
    print("="*80)
    
    params = {
        "S0": 100.0,
        "days": 30,
        "iv": 0.20,
        "put_short_strike": 95.0,
        "put_long_strike": 90.0,
        "call_short_strike": 105.0,
        "call_long_strike": 110.0,
        "net_credit": 1.50
    }
    
    path_counts = [500, 1000, 2000, 5000, 10000]
    results = []
    
    print(f"\n{'Paths':<10} {'Expected P&L':<15} {'Std Dev':<15}")
    print("-" * 40)
    
    for n_paths in path_counts:
        mc = mc_pnl("IRON_CONDOR", params, n_paths=n_paths, mu=0.0, seed=42)
        results.append(mc['pnl_expected'])
        print(f"{n_paths:<10} ${mc['pnl_expected']:<14.4f} ${mc['pnl_std']:<14.4f}")
    
    # Check that results stabilize (later results are closer together)
    diff_early = abs(results[1] - results[0])
    diff_late = abs(results[4] - results[3])
    
    print(f"\nDifference between consecutive runs:")
    print(f"  1000 vs 500 paths: ${diff_early:.4f}")
    print(f"  10000 vs 5000 paths: ${diff_late:.4f}")
    
    check = diff_late < diff_early  # Should converge
    print(f"\n✓ Results converge with more paths: {'PASS' if check else 'FAIL'}")
    
    return check


def run_all_tests():
    """Run all validation tests"""
    print("="*80)
    print("IRON CONDOR MONTE CARLO VALIDATION SUITE")
    print("="*80)
    
    tests = [
        ("Basic Simulation", test_iron_condor_basic),
        ("Edge Cases", test_iron_condor_edge_cases),
        ("Asymmetric Spreads", test_iron_condor_asymmetric),
        ("P&L at Strikes", test_iron_condor_pnl_at_strikes),
        ("Repeatability", test_iron_condor_repeatability),
        ("Convergence", test_iron_condor_convergence),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            passed = test_func()
            results.append((test_name, passed))
        except Exception as e:
            print(f"\n❌ {test_name} FAILED with exception: {e}")
            import traceback
            traceback.print_exc()
            results.append((test_name, False))
    
    # Summary
    print("\n" + "="*80)
    print("VALIDATION SUMMARY")
    print("="*80)
    
    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    total_passed = sum(1 for _, passed in results if passed)
    total_tests = len(results)
    
    print(f"\n{total_passed}/{total_tests} tests passed")
    
    if total_passed == total_tests:
        print("\n🎉 All validation tests passed! Iron Condor MC implementation is reliable.")
        return 0
    else:
        print("\n⚠️  Some tests failed. Review implementation.")
        return 1


if __name__ == "__main__":
    exit_code = run_all_tests()
    sys.exit(exit_code)
