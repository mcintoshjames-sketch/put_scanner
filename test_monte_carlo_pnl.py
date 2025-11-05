"""
Monte Carlo and P&L Calculation Validation Tests

Tests the core financial calculations to ensure accuracy and trustworthiness:
1. Monte Carlo simulation terminal prices (GBM)
2. CSP P&L calculations (premium - max loss + interest on collateral)
3. CC P&L calculations (stock gains + premium - call assignment)
4. Collar P&L calculations (stock + short call + long put)
5. ROI annualization logic
6. Edge cases (0 DTE, extreme volatilities, extreme prices)

Tests are designed to validate against known theoretical values and
ensure no arithmetic errors, sign flips, or unit confusion.
"""

import numpy as np
import pandas as pd
import math
from datetime import datetime, timezone
from options_math import safe_annualize_roi
import os
try:
    import pytest  # type: ignore
    _HAS_PYTEST = True
except Exception:  # pragma: no cover - local script runs
    _HAS_PYTEST = False

# This file is an integration-style suite with prints. Skip by default in CI.
if not os.getenv("RUN_INTEGRATION") and _HAS_PYTEST:
    import pytest as _pytest
    _pytest.skip("Skipping integration-style Monte Carlo suite; set RUN_INTEGRATION=1 to run.", allow_module_level=True)

# Import the functions we're testing
from strategy_lab import (
    gbm_terminal_prices,
    mc_pnl,
    bs_put_price,
    bs_call_price,
    _bs_d1_d2,
    _norm_cdf,
    expected_move
)


def test_gbm_terminal_prices():
    """Test geometric Brownian motion simulation"""
    print("\n" + "="*60)
    print("TEST 1: Geometric Brownian Motion Terminal Prices")
    print("="*60)
    
    S0 = 100.0
    mu = 0.0  # zero drift
    sigma = 0.25  # 25% annualized vol
    T = 1.0  # 1 year
    n_paths = 100000
    
    rng = np.random.default_rng(42)
    prices = gbm_terminal_prices(S0, mu, sigma, T, n_paths, rng)
    
    # Theoretical statistics for log-normal distribution
    # E[S_T] = S0 * exp(mu * T) = 100 with mu=0
    # Var[log(S_T/S0)] = sigma^2 * T = 0.25^2 * 1 = 0.0625
    
    log_returns = np.log(prices / S0)
    
    expected_mean = mu * T  # Should be ~0
    expected_std = sigma * np.sqrt(T)  # Should be ~0.25
    
    actual_mean = np.mean(log_returns)
    actual_std = np.std(log_returns)
    
    print(f"S0 = ${S0:.2f}, mu = {mu}, sigma = {sigma}, T = {T} years")
    print(f"Paths simulated: {n_paths:,}")
    print(f"\nLog-return statistics:")
    print(f"  Expected mean:  {expected_mean:.4f}")
    print(f"  Actual mean:    {actual_mean:.4f}")
    print(f"  Expected std:   {expected_std:.4f}")
    print(f"  Actual std:     {actual_std:.4f}")
    
    # Check if within 1% tolerance
    mean_error = abs(actual_mean - expected_mean)
    std_error = abs(actual_std - expected_std) / expected_std
    
    print(f"\nValidation:")
    print(f"  Mean error:     {mean_error:.6f} (should be < 0.01)")
    print(f"  Std rel error:  {std_error:.4f} (should be < 0.01)")
    
    if mean_error < 0.01 and std_error < 0.01:
        print("  ✅ GBM simulation PASS")
        return True
    else:
        print("  ❌ GBM simulation FAIL")
        return False


def test_csp_pnl_basic():
    """Test CSP P&L calculation with basic scenario"""
    print("\n" + "="*60)
    print("TEST 2: Cash-Secured Put P&L - Basic Scenario")
    print("="*60)
    
    # Scenario: SPY at $470, sell $440 put for $3.50, 35 DTE
    S0 = 470.0
    K = 440.0
    premium = 3.50
    days = 35
    iv = 0.20  # 20% IV
    rf = 0.05  # 5% risk-free rate
    
    params = {
        "S0": S0,
        "Kp": K,
        "put_premium": premium,
        "days": days,
        "iv": iv,
        "div_ps_annual": 0.0
    }
    
    print(f"Setup: SPY @ ${S0}, Strike ${K}, Premium ${premium}, {days} DTE")
    print(f"IV: {iv*100}%, Risk-free: {rf*100}%")
    
    # Run Monte Carlo
    result = mc_pnl("CSP", params, n_paths=50000, mu=0.0, seed=42, rf=rf)
    
    # Manual calculations for validation
    T = days / 365.0
    capital_per_contract = K * 100  # $44,000
    
    # Interest earned on collateral
    interest_earned = K * (math.exp(rf * T) - 1.0)
    print(f"\nInterest on ${K} collateral for {days} days @ {rf*100}%:")
    print(f"  ${interest_earned:.2f} per share = ${interest_earned*100:.2f} per contract")
    
    # Best case: option expires worthless
    best_case_ps = premium + interest_earned
    best_case_pc = best_case_ps * 100
    
    # Worst case: stock drops to zero
    worst_case_ps = premium - K + interest_earned
    worst_case_pc = worst_case_ps * 100
    
    # Breakeven
    breakeven = K - premium - interest_earned
    
    print(f"\nTheoretical P&L boundaries:")
    print(f"  Best case (expires worthless): ${best_case_pc:.2f} per contract")
    print(f"  Worst case (stock to $0):      ${worst_case_pc:.2f} per contract")
    print(f"  Breakeven price:                ${breakeven:.2f}")
    print(f"  Capital at risk:                ${capital_per_contract:,.0f}")
    
    print(f"\nMonte Carlo results ({result['paths']:,} paths):")
    print(f"  Expected P&L:   ${result['pnl_expected']:.2f}")
    print(f"  P5:             ${result['pnl_p5']:.2f}")
    print(f"  P50 (median):   ${result['pnl_p50']:.2f}")
    print(f"  P95:            ${result['pnl_p95']:.2f}")
    print(f"  Min:            ${result['pnl_min']:.2f}")
    
    print(f"\nROI annualized:")
    print(f"  Expected: {result['roi_ann_expected']*100:.2f}%")
    print(f"  P5:       {result['roi_ann_p5']*100:.2f}%")
    print(f"  P95:      {result['roi_ann_p95']*100:.2f}%")
    
    # Validation checks
    checks_passed = True
    
    # 1. Expected P&L should be close to premium + interest (small negative skew)
    expected_theoretical = (premium + interest_earned) * 100
    if abs(result['pnl_expected'] - expected_theoretical) > expected_theoretical * 0.15:
        print(f"  ⚠️  Expected P&L differs from theoretical by >{15}%")
        checks_passed = False
    
    # 2. P95 should not exceed best case
    if result['pnl_p95'] > best_case_pc * 1.01:  # 1% tolerance
        print(f"  ❌ P95 ${result['pnl_p95']:.2f} exceeds max possible ${best_case_pc:.2f}")
        checks_passed = False
    
    # 3. Min should not be worse than worst case
    if result['pnl_min'] < worst_case_pc * 1.01:  # 1% tolerance for numerical error
        print(f"  ❌ Min ${result['pnl_min']:.2f} worse than theoretical worst ${worst_case_pc:.2f}")
        checks_passed = False
    
    # 4. Collateral should match
    if abs(result['collateral'] - capital_per_contract) > 0.01:
        print(f"  ❌ Collateral mismatch: {result['collateral']} vs {capital_per_contract}")
        checks_passed = False
    
    if checks_passed:
        print("\n  ✅ CSP P&L calculation PASS")
    else:
        print("\n  ❌ CSP P&L calculation FAIL")
    
    return checks_passed


def test_csp_pnl_edge_cases():
    """Test CSP P&L with edge cases"""
    print("\n" + "="*60)
    print("TEST 3: CSP P&L - Edge Cases")
    print("="*60)
    
    all_pass = True
    
    # Edge case 1: 1 DTE (minimum allowed)
    print("\nEdge Case 1: 1 DTE (minimum time)")
    params_1dte = {
        "S0": 100.0,
        "Kp": 95.0,
        "put_premium": 0.50,
        "days": 1,
        "iv": 0.30,
        "div_ps_annual": 0.0
    }
    
    try:
        result = mc_pnl("CSP", params_1dte, n_paths=10000, mu=0.0, seed=42, rf=0.05)
        print(f"  Expected P&L: ${result['pnl_expected']:.2f}")
        print(f"  Collateral: ${result['collateral']:.0f}")
        
        # Should have minimal interest (1/365 of a year)
        expected_interest = 95.0 * (math.exp(0.05 * 1/365) - 1.0) * 100
        print(f"  Interest earned: ~${expected_interest:.2f}")
        
        if result['pnl_expected'] > 0:
            print("  ✅ 1 DTE calculation works")
        else:
            print("  ⚠️  1 DTE P&L unexpected")
            all_pass = False
    except Exception as e:
        print(f"  ❌ 1 DTE calculation failed: {e}")
        all_pass = False
    
    # Edge case 2: Very high IV
    print("\nEdge Case 2: Very high IV (200%)")
    params_highiv = {
        "S0": 100.0,
        "Kp": 90.0,
        "put_premium": 5.00,
        "days": 30,
        "iv": 2.00,  # 200% IV
        "div_ps_annual": 0.0
    }
    
    try:
        result = mc_pnl("CSP", params_highiv, n_paths=10000, mu=0.0, seed=42, rf=0.05)
        print(f"  Expected P&L: ${result['pnl_expected']:.2f}")
        print(f"  P5 to P95 range: ${result['pnl_p5']:.2f} to ${result['pnl_p95']:.2f}")
        
        # High IV should produce wide P&L distribution
        pnl_range = result['pnl_p95'] - result['pnl_p5']
        if pnl_range > 1000:  # Should be wide with 200% IV
            print(f"  ✅ High IV produces wide distribution (${pnl_range:.0f})")
        else:
            print(f"  ⚠️  High IV distribution unexpectedly narrow")
            all_pass = False
    except Exception as e:
        print(f"  ❌ High IV calculation failed: {e}")
        all_pass = False
    
    # Edge case 3: ITM put (testing loss scenarios)
    print("\nEdge Case 3: ITM put (starting in the money)")
    params_itm = {
        "S0": 95.0,  # Stock below strike
        "Kp": 100.0,
        "put_premium": 6.00,  # Less than intrinsic value of $5
        "days": 14,
        "iv": 0.25,
        "div_ps_annual": 0.0
    }
    
    try:
        result = mc_pnl("CSP", params_itm, n_paths=10000, mu=0.0, seed=42, rf=0.05)
        print(f"  Expected P&L: ${result['pnl_expected']:.2f}")
        
        # ITM put should have higher probability of assignment
        # Expected P&L should account for high loss probability
        intrinsic = (100.0 - 95.0) * 100  # $500
        premium_collected = 6.00 * 100  # $600
        
        print(f"  Initial intrinsic value: ${intrinsic:.0f}")
        print(f"  Premium collected: ${premium_collected:.0f}")
        
        if result['pnl_expected'] < premium_collected:
            print("  ✅ ITM put shows realistic loss exposure")
        else:
            print("  ⚠️  ITM put P&L seems optimistic")
            all_pass = False
    except Exception as e:
        print(f"  ❌ ITM put calculation failed: {e}")
        all_pass = False
    
    if all_pass:
        print("\n  ✅ All edge cases PASS")
    else:
        print("\n  ❌ Some edge cases FAIL")
    
    return all_pass


def test_cc_pnl_basic():
    """Test Covered Call P&L calculation"""
    print("\n" + "="*60)
    print("TEST 4: Covered Call P&L - Basic Scenario")
    print("="*60)
    
    # Scenario: AAPL at $175, sell $180 call for $2.50, 30 DTE, $1.00 dividend
    S0 = 175.0
    K = 180.0
    premium = 2.50
    days = 30
    iv = 0.25
    div_annual = 4.00  # $4/year = $1/quarter
    
    params = {
        "S0": S0,
        "Kc": K,
        "call_premium": premium,
        "days": days,
        "iv": iv,
        "div_ps_annual": div_annual
    }
    
    print(f"Setup: AAPL @ ${S0}, Strike ${K}, Premium ${premium}, {days} DTE")
    print(f"Dividend: ${div_annual}/year, IV: {iv*100}%")
    
    # Use realistic equity drift (7% annual)
    result = mc_pnl("CC", params, n_paths=50000, mu=0.07, seed=42, rf=0.05)
    
    # Manual validation
    T = days / 365.0
    div_period = div_annual * T
    capital = S0 * 100  # $17,500
    
    # Best case: stock at strike (max profit)
    best_case_ps = (K - S0) + premium + div_period
    best_case_pc = best_case_ps * 100
    
    # Worst case: stock to zero
    worst_case_ps = -S0 + premium + div_period
    worst_case_pc = worst_case_ps * 100
    
    print(f"\nTheoretical P&L boundaries:")
    print(f"  Best case (called away at strike): ${best_case_pc:.2f}")
    print(f"  Worst case (stock to $0):          ${worst_case_pc:.2f}")
    print(f"  Dividend this period:               ${div_period*100:.2f} per contract")
    print(f"  Capital invested:                   ${capital:,.0f}")
    
    print(f"\nMonte Carlo results ({result['paths']:,} paths):")
    print(f"  Expected P&L:   ${result['pnl_expected']:.2f}")
    print(f"  P5:             ${result['pnl_p5']:.2f}")
    print(f"  P50 (median):   ${result['pnl_p50']:.2f}")
    print(f"  P95:            ${result['pnl_p95']:.2f}")
    
    print(f"\nROI annualized:")
    print(f"  Expected: {result['roi_ann_expected']*100:.2f}%")
    print(f"  P5:       {result['roi_ann_p5']*100:.2f}%")
    print(f"  P95:      {result['roi_ann_p95']*100:.2f}%")
    
    # Validation
    checks_passed = True
    
    # 1. P95 should not exceed max profit
    if result['pnl_p95'] > best_case_pc * 1.01:
        print(f"  ❌ P95 exceeds theoretical max")
        checks_passed = False
    
    # 2. Expected should be positive with 7% drift
    # With positive drift, stock gains + premium + dividend should yield positive expected
    if result['pnl_expected'] < 0:
        print(f"  ⚠️  Expected P&L negative even with 7% drift")
        checks_passed = False
    
    # 3. Capital should match
    if abs(result['collateral'] - capital) > 0.01:
        print(f"  ❌ Capital mismatch")
        checks_passed = False
    
    if checks_passed:
        print("\n  ✅ CC P&L calculation PASS")
    else:
        print("\n  ❌ CC P&L calculation FAIL")
    
    return checks_passed


def test_collar_pnl_basic():
    """Test Collar P&L calculation"""
    print("\n" + "="*60)
    print("TEST 5: Collar P&L - Basic Scenario")
    print("="*60)
    
    # Scenario: Stock at $100, sell $105 call for $2, buy $95 put for $1.50
    S0 = 100.0
    Kc = 105.0  # Call strike
    Kp = 95.0   # Put strike
    call_prem = 2.00
    put_prem = 1.50
    days = 45
    iv = 0.30
    div_annual = 2.00
    
    params = {
        "S0": S0,
        "Kc": Kc,
        "Kp": Kp,
        "call_premium": call_prem,
        "put_premium": put_prem,
        "days": days,
        "iv": iv,
        "div_ps_annual": div_annual
    }
    
    net_credit = call_prem - put_prem
    
    print(f"Setup: Stock @ ${S0}")
    print(f"  Sell ${Kc} call for ${call_prem}")
    print(f"  Buy ${Kp} put for ${put_prem}")
    print(f"  Net credit: ${net_credit} per share")
    print(f"  {days} DTE, Dividend: ${div_annual}/year")
    
    # Use realistic equity drift (7% annual)
    result = mc_pnl("COLLAR", params, n_paths=50000, mu=0.07, seed=42, rf=0.05)
    
    # Manual validation
    T = days / 365.0
    div_period = div_annual * T
    capital = S0 * 100
    
    # Max profit: stock at call strike
    max_profit_ps = (Kc - S0) + net_credit + div_period
    max_profit_pc = max_profit_ps * 100
    
    # Max loss: stock at put strike
    max_loss_ps = (Kp - S0) + net_credit + div_period
    max_loss_pc = max_loss_ps * 100
    
    print(f"\nTheoretical P&L boundaries:")
    print(f"  Max profit (stock at ${Kc}):  ${max_profit_pc:.2f}")
    print(f"  Max loss (stock at ${Kp}):    ${max_loss_pc:.2f}")
    print(f"  Protected range:               ${Kp:.0f} to ${Kc:.0f}")
    print(f"  Capital invested:              ${capital:,.0f}")
    
    print(f"\nMonte Carlo results ({result['paths']:,} paths):")
    print(f"  Expected P&L:   ${result['pnl_expected']:.2f}")
    print(f"  P5:             ${result['pnl_p5']:.2f}")
    print(f"  P50 (median):   ${result['pnl_p50']:.2f}")
    print(f"  P95:            ${result['pnl_p95']:.2f}")
    
    print(f"\nROI annualized:")
    print(f"  Expected: {result['roi_ann_expected']*100:.2f}%")
    
    # Validation
    checks_passed = True
    
    # 1. P95 should not exceed max profit
    if result['pnl_p95'] > max_profit_pc * 1.02:  # 2% tolerance
        print(f"  ❌ P95 ${result['pnl_p95']:.2f} exceeds max profit ${max_profit_pc:.2f}")
        checks_passed = False
    
    # 2. P5 should not be worse than max loss
    if result['pnl_p5'] < max_loss_pc * 1.02:  # 2% tolerance (loss is negative)
        print(f"  ❌ P5 ${result['pnl_p5']:.2f} worse than max loss ${max_loss_pc:.2f}")
        checks_passed = False
    
    # 3. Collar should have bounded risk
    pnl_range = result['pnl_p95'] - result['pnl_p5']
    expected_range = max_profit_pc - max_loss_pc
    if abs(pnl_range - expected_range) > expected_range * 0.2:  # 20% tolerance
        print(f"  ⚠️  P&L range differs significantly from theoretical")
        checks_passed = False
    
    if checks_passed:
        print("\n  ✅ Collar P&L calculation PASS")
    else:
        print("\n  ❌ Collar P&L calculation FAIL")
    
    return checks_passed


def test_roi_annualization():
    """Test ROI annualization logic"""
    print("\n" + "="*60)
    print("TEST 6: ROI Annualization Logic")
    print("="*60)
    
    # Test cases: (pnl_per_contract, capital, days) -> expected_annual_roi
    test_cases = [
        (350, 44000, 35, "CSP: $350 profit on $44k in 35 days"),
        (250, 17500, 30, "CC: $250 profit on $17.5k in 30 days"),
        (100, 10000, 7, "Short DTE: $100 on $10k in 7 days"),
        (500, 50000, 365, "Full year: $500 on $50k in 365 days"),
    ]
    
    all_pass = True
    
    for pnl, capital, days, desc in test_cases:
        cycle_roi = pnl / capital
        # Use shared helper for stable and consistent annualization
        annual_roi = float(safe_annualize_roi(cycle_roi, days))
        annual_pct = annual_roi * 100.0
        
        print(f"\n{desc}")
        print(f"  P&L: ${pnl}, Capital: ${capital:,}, Days: {days}")
        print(f"  Cycle ROI: {cycle_roi*100:.2f}%")
        print(f"  Annualized ROI: {annual_pct:.2f}%")
        
        # Sanity checks
        if days < 365:
            # Short-term positions should annualize higher
            if annual_roi < cycle_roi:
                print(f"  ❌ Annualized ROI should be > cycle ROI for <365 days")
                all_pass = False
        elif days == 365:
            # Should be approximately equal
            if abs(annual_roi - cycle_roi) > 0.001:
                print(f"  ❌ Annual ROI should equal cycle ROI for 365 days")
                all_pass = False
        
        # Check for reasonable values (not infinity or negative)
        if not (0 <= annual_pct <= 10000):  # Cap at 10,000% for sanity
            print(f"  ❌ Annualized ROI outside reasonable range")
            all_pass = False
        else:
            print(f"  ✅ Annualization calculation valid")
    
    if all_pass:
        print("\n  ✅ All ROI annualization tests PASS")
    else:
        print("\n  ❌ Some ROI annualization tests FAIL")
    
    return all_pass


def test_expected_move():
    """Test expected move calculation"""
    print("\n" + "="*60)
    print("TEST 7: Expected Move (Sigma Cushion) Calculation")
    print("="*60)
    
    # Expected move = S * sigma * sqrt(T)
    test_cases = [
        (100.0, 0.20, 30, "Stock $100, 20% IV, 30 days"),
        (470.0, 0.25, 45, "SPY $470, 25% IV, 45 days"),
        (50.0, 0.50, 14, "High IV $50 stock, 50% IV, 14 days"),
    ]
    
    all_pass = True
    
    for S, sigma, days, desc in test_cases:
        T = days / 365.0
        exp_mv = expected_move(S, sigma, T)
        
        # Manual calculation
        expected = S * sigma * math.sqrt(T)
        
        print(f"\n{desc}")
        print(f"  Expected 1σ move: ${exp_mv:.2f}")
        print(f"  Manual calc:      ${expected:.2f}")
        
        # Check match
        if abs(exp_mv - expected) < 0.01:
            print(f"  ✅ Calculation correct")
        else:
            print(f"  ❌ Mismatch in calculation")
            all_pass = False
        
        # Check sigma cushion for a put
        strike = S * 0.90  # 10% OTM
        cushion = (S - strike) / exp_mv
        print(f"  For ${strike:.2f} strike (10% OTM):")
        print(f"    Sigma cushion: {cushion:.2f}σ")
        
        if cushion > 0:
            print(f"    ✅ Cushion positive for OTM put")
        else:
            print(f"    ❌ Cushion should be positive")
            all_pass = False
    
    if all_pass:
        print("\n  ✅ All expected move tests PASS")
    else:
        print("\n  ❌ Some expected move tests FAIL")
    
    return all_pass


def main():
    """Run all tests"""
    print("="*60)
    print("MONTE CARLO & P&L CALCULATION VALIDATION TEST SUITE")
    print("="*60)
    print("\nThis test suite validates the core financial calculations")
    print("in the options income strategy lab.")
    print("\nTests include:")
    print("  1. GBM terminal price simulation")
    print("  2. CSP P&L calculations")
    print("  3. CSP edge cases")
    print("  4. Covered Call P&L")
    print("  5. Collar P&L")
    print("  6. ROI annualization")
    print("  7. Expected move / sigma cushion")
    
    results = []
    
    # Run all tests
    results.append(("GBM Simulation", test_gbm_terminal_prices()))
    results.append(("CSP P&L Basic", test_csp_pnl_basic()))
    results.append(("CSP Edge Cases", test_csp_pnl_edge_cases()))
    results.append(("CC P&L Basic", test_cc_pnl_basic()))
    results.append(("Collar P&L Basic", test_collar_pnl_basic()))
    results.append(("ROI Annualization", test_roi_annualization()))
    results.append(("Expected Move", test_expected_move()))
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{test_name:.<40} {status}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED - Monte Carlo and P&L calculations are TRUSTWORTHY")
        return 0
    else:
        print(f"\n⚠️  {total - passed} TEST(S) FAILED - Review calculations before trading")
        return 1


if __name__ == "__main__":
    exit(main())
