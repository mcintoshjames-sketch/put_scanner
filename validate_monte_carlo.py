#!/usr/bin/env python3
"""
Monte Carlo Risk Analysis Validator

This validator performs comprehensive checks on the Monte Carlo simulation approach
to ensure conceptual soundness and outcome reasonableness for each strategy.

CRITICAL VALIDATIONS:
1. Mathematical Correctness - P&L formulas match payoff diagrams
2. Statistical Properties - Distributions have proper characteristics
3. Parameter Sensitivity - Results respond correctly to input changes
4. Strategy-Specific Logic - Each strategy's unique risks are captured
5. Numerical Stability - No overflow, underflow, or NaN propagation
6. Economic Reasonableness - Outcomes align with option theory
"""

import sys
import numpy as np
from pathlib import Path
from options_math import mc_pnl, gbm_terminal_prices, _bs_d1_d2, _norm_cdf


def validate_csp_mc_logic():
    """
    Validate CSP Monte Carlo implementation.
    
    CSP Payoff: Premium - max(0, Strike - S_T) + rf_interest_on_collateral
    
    Financial Logic:
    - If S_T > Strike: Keep full premium + interest (max profit)
    - If S_T < Strike: Assigned at strike, lose (Strike - S_T) - Premium + interest
    - Capital: Strike price (cash secured)
    
    Critical Tests:
    1. Max profit = premium + interest when S_T >> Strike
    2. Max loss = strike - premium + interest when S_T = 0
    3. Breakeven = strike - premium (ignoring interest)
    4. Higher volatility = wider distribution of outcomes
    5. Longer time = more interest earned
    """
    print("\n📊 CSP (Cash Secured Put) Validation")
    print("-" * 70)
    
    issues = []
    
    # Base case parameters
    S0 = 100.0
    strike = 95.0  # 5% OTM put
    premium = 2.50
    days = 45
    iv = 0.25
    rf = 0.05  # 5% risk-free rate
    
    params = {
        "S0": S0,
        "days": days,
        "iv": iv,
        "Kp": strike,
        "put_premium": premium,
        "div_ps_annual": 0.0
    }
    
    # Test 1: Max profit scenario (use zero volatility to ensure stays OTM)
    print("Test 1: Max Profit Scenario (zero vol, stock stays at S0)")
    params_maxprofit = params.copy()
    params_maxprofit["iv"] = 0.0001  # Near-zero vol to ensure no movement
    result = mc_pnl("CSP", params_maxprofit, n_paths=10000, mu=0.0, seed=42, rf=rf)
    
    expected_interest = strike * (np.exp(rf * days/365.0) - 1.0)
    theoretical_max_profit = (premium + expected_interest) * 100
    actual_mean = result["pnl_expected"]
    
    print(f"  Expected max profit: ${theoretical_max_profit:.2f}")
    print(f"  MC mean P&L:         ${actual_mean:.2f}")
    print(f"  Difference:          ${abs(actual_mean - theoretical_max_profit):.2f}")
    
    # With zero vol, S stays at S0=100, strike=95, so put expires worthless
    # Should get premium + interest
    if abs(actual_mean - theoretical_max_profit) > 10.0:
        issues.append("❌ CSP max profit calculation incorrect")
    else:
        print("  ✅ Max profit calculation correct")
    
    # Test 2: Loss scenario (deterministic - set S_T via zero vol at low starting point)
    print("\nTest 2: Assignment Scenario (zero vol, start at ITM price)")
    params_assigned = params.copy()
    params_assigned["S0"] = 90.0  # Start at $90 (below strike of $95)
    params_assigned["iv"] = 0.0001  # Near-zero vol so stays at $90
    result_low = mc_pnl("CSP", params_assigned, n_paths=10000, mu=0.0, seed=42, rf=rf)
    
    # When S_T = $90: premium - (strike - S_T) + interest
    # = 2.50 - (95 - 90) + interest = 2.50 - 5.00 + interest = -2.50 + interest
    stock_loss = strike - 90.0  # 5.00
    theoretical_pnl = (premium - stock_loss + expected_interest) * 100
    actual_mean_low = result_low["pnl_expected"]
    
    print(f"  Expected P&L:        ${theoretical_pnl:.2f}")
    print(f"  MC mean P&L:         ${actual_mean_low:.2f}")
    print(f"  Difference:          ${abs(actual_mean_low - theoretical_pnl):.2f}")
    
    if abs(actual_mean_low - theoretical_pnl) > 10.0:
        issues.append("❌ CSP assignment P&L calculation incorrect")
    else:
        print("  ✅ Assignment P&L calculation correct")
    
    # Test 3: Breakeven point (zero vol at breakeven price)
    print("\nTest 3: Breakeven Analysis")
    theoretical_breakeven = strike - premium  # 95 - 2.5 = 92.5
    print(f"  Theoretical breakeven: ${theoretical_breakeven:.2f}")
    
    # Test at breakeven price with zero vol
    params_be = params.copy()
    params_be["S0"] = theoretical_breakeven
    params_be["iv"] = 0.0001  # Zero vol
    result_be = mc_pnl("CSP", params_be, n_paths=10000, mu=0.0, seed=42, rf=rf)
    
    # At breakeven: premium - (strike - breakeven) + interest = 0 + interest
    expected_pnl = expected_interest * 100
    print(f"  MC mean P&L at BE:     ${result_be['pnl_expected']:.2f}")
    print(f"  Expected (interest):   ${expected_pnl:.2f}")
    
    if abs(result_be['pnl_expected'] - expected_pnl) > 10.0:
        issues.append("❌ CSP breakeven calculation incorrect")
    else:
        print("  ✅ Breakeven behavior correct (near interest amount)")
    
    # Test 4: Volatility sensitivity
    print("\nTest 4: Volatility Sensitivity")
    params_lowvol = params.copy()
    params_lowvol["iv"] = 0.15
    result_lowvol = mc_pnl("CSP", params_lowvol, n_paths=10000, mu=0.0, seed=42, rf=rf)
    
    params_highvol = params.copy()
    params_highvol["iv"] = 0.40
    result_highvol = mc_pnl("CSP", params_highvol, n_paths=10000, mu=0.0, seed=42, rf=rf)
    
    print(f"  Low vol (15%) std:   ${result_lowvol['pnl_std']:.2f}")
    print(f"  High vol (40%) std:  ${result_highvol['pnl_std']:.2f}")
    
    if result_highvol['pnl_std'] <= result_lowvol['pnl_std']:
        issues.append("❌ CSP volatility sensitivity incorrect - higher vol should increase dispersion")
    else:
        print("  ✅ Higher volatility correctly increases outcome dispersion")
    
    # Test 5: Capital calculation
    print("\nTest 5: Capital Requirements")
    print(f"  Reported capital:    ${result['collateral']:.2f}")
    print(f"  Expected capital:    ${strike * 100:.2f}")
    
    if abs(result['collateral'] - strike * 100) > 1.0:
        issues.append("❌ CSP capital calculation incorrect")
    else:
        print("  ✅ Capital correctly set to strike price")
    
    # Test 6: Statistical properties
    print("\nTest 6: Distribution Properties")
    result_dist = mc_pnl("CSP", params, n_paths=50000, mu=0.0, seed=42, rf=rf)
    p5 = result_dist['pnl_p5']
    p50 = result_dist['pnl_p50']
    p95 = result_dist['pnl_p95']
    
    print(f"  5th percentile:      ${p5:.2f}")
    print(f"  Median:              ${p50:.2f}")
    print(f"  95th percentile:     ${p95:.2f}")
    
    # For CSP, distribution should be negatively skewed (capped profit, unlimited loss)
    if p95 - p50 > abs(p50 - p5):
        issues.append("⚠️  WARNING: CSP distribution should be negatively skewed")
        print("  ⚠️  Distribution skew unexpected (should be left-tailed)")
    else:
        print("  ✅ Distribution properly shows left tail (downside risk)")
    
    if not issues:
        print("\n✅ CSP Monte Carlo implementation is sound")
    else:
        print("\n❌ CSP Monte Carlo has issues:")
        for issue in issues:
            print(f"  {issue}")
    
    return issues


def validate_spread_mc_logic():
    """
    Validate vertical spread (Bull Put, Bear Call, Iron Condor) Monte Carlo.
    
    Spread Payoff: Net_Credit - Spread_Loss
    
    Financial Logic:
    - Max profit = net credit (if stays in profit zone)
    - Max loss = spread width - net credit
    - Defined risk (limited loss, limited profit)
    
    Critical Tests:
    1. Max profit = net credit when stock stays favorable
    2. Max loss = spread width - credit when breached
    3. P&L bounded between max profit and max loss
    4. Symmetric spread should show centered distribution
    5. Capital = max loss (spread width - credit)
    """
    print("\n📊 Vertical Spread Validation (Bull Put Spread)")
    print("-" * 70)
    
    issues = []
    
    # Bull Put Spread: Sell 95 put, Buy 90 put for $2.00 credit
    S0 = 100.0
    sell_strike = 95.0
    buy_strike = 90.0
    net_credit = 2.00
    spread_width = sell_strike - buy_strike  # 5.00
    max_profit = net_credit  # 2.00
    max_loss = spread_width - net_credit  # 3.00
    days = 45
    iv = 0.25
    
    params = {
        "S0": S0,
        "days": days,
        "iv": iv,
        "sell_strike": sell_strike,
        "buy_strike": buy_strike,
        "net_credit": net_credit
    }
    
    # Test 1: Max profit scenario (zero vol, stays above sell strike)
    print("Test 1: Max Profit Scenario (zero vol, stays above sell strike)")
    params_maxprofit = params.copy()
    params_maxprofit["iv"] = 0.0001  # Near-zero vol
    result = mc_pnl("BULL_PUT_SPREAD", params_maxprofit, n_paths=10000, mu=0.0, seed=42, rf=0.05)
    
    theoretical_max = max_profit * 100
    actual_mean = result["pnl_expected"]
    
    print(f"  Expected max profit: ${theoretical_max:.2f}")
    print(f"  MC mean P&L:         ${actual_mean:.2f}")
    print(f"  Difference:          ${abs(actual_mean - theoretical_max):.2f}")
    
    # With S0=$100, strike=$95, zero vol: stock stays at $100, put expires worthless, keep credit
    if abs(actual_mean - theoretical_max) > 10.0:
        issues.append("❌ Spread max profit calculation incorrect")
    else:
        print("  ✅ Max profit calculation correct")
    
    # Test 2: Max loss scenario (zero vol, below buy strike)
    print("\nTest 2: Max Loss Scenario (zero vol, falls below buy strike)")
    params_maxloss = params.copy()
    params_maxloss["S0"] = 85.0  # Below buy strike of $90
    params_maxloss["iv"] = 0.0001  # Zero vol
    result_low = mc_pnl("BULL_PUT_SPREAD", params_maxloss, n_paths=10000, mu=0.0, seed=42, rf=0.05)
    
    theoretical_min = -max_loss * 100
    actual_mean_low = result_low["pnl_expected"]
    
    print(f"  Expected max loss:   ${theoretical_min:.2f}")
    print(f"  MC mean P&L:         ${actual_mean_low:.2f}")
    print(f"  Difference:          ${abs(actual_mean_low - theoretical_min):.2f}")
    
    # S_T = $85, sell_strike=$95, buy_strike=$90, credit=$2
    # Loss = 2.00 - (95-85) + (90-85) = 2 - 10 + 5 = -3.00 per share = -$300 per contract
    if abs(actual_mean_low - theoretical_min) > 10.0:
        issues.append("❌ Spread max loss calculation incorrect")
    else:
        print("  ✅ Max loss calculation correct")
    
    # Test 3: Bounded P&L
    print("\nTest 3: P&L Bounds (all outcomes should be between max profit and max loss)")
    result_dist = mc_pnl("BULL_PUT_SPREAD", params, n_paths=50000, mu=0.0, seed=42, rf=0.05)
    pnl_paths = result_dist["pnl_paths"]
    pnl_min = np.min(pnl_paths[np.isfinite(pnl_paths)])
    pnl_max = np.max(pnl_paths[np.isfinite(pnl_paths)])
    
    print(f"  Min P&L observed:    ${pnl_min:.2f}")
    print(f"  Max P&L observed:    ${pnl_max:.2f}")
    print(f"  Theoretical max:     ${theoretical_max:.2f}")
    print(f"  Theoretical min:     ${theoretical_min:.2f}")
    
    # Allow small tolerance for rounding
    if pnl_max > theoretical_max + 1.0:
        issues.append("❌ Spread P&L exceeds max profit (logic error)")
    elif pnl_min < theoretical_min - 1.0:
        issues.append("❌ Spread P&L exceeds max loss (logic error)")
    else:
        print("  ✅ P&L properly bounded by max profit/loss")
    
    # Test 4: Capital calculation
    print("\nTest 4: Capital Requirements")
    expected_capital = max_loss * 100
    actual_capital = result['collateral']
    
    print(f"  Reported capital:    ${actual_capital:.2f}")
    print(f"  Expected capital:    ${expected_capital:.2f}")
    
    if abs(actual_capital - expected_capital) > 1.0:
        issues.append("❌ Spread capital calculation incorrect")
    else:
        print("  ✅ Capital correctly set to max loss")
    
    # Test 5: Breakeven analysis
    print("\nTest 5: Breakeven Analysis")
    # Breakeven = sell strike - net credit = 95 - 2 = 93
    breakeven = sell_strike - net_credit
    print(f"  Theoretical breakeven: ${breakeven:.2f}")
    
    params_be = params.copy()
    params_be["S0"] = breakeven
    result_be = mc_pnl("BULL_PUT_SPREAD", params_be, n_paths=10000, mu=0.0, seed=42, rf=0.05)
    
    print(f"  MC mean P&L at BE:     ${result_be['pnl_expected']:.2f}")
    
    if abs(result_be['pnl_expected']) > 50.0:
        issues.append("⚠️  WARNING: Breakeven P&L seems off (should be near zero)")
        print("  ⚠️  Breakeven calculation may be incorrect")
    else:
        print("  ✅ Breakeven behavior reasonable")
    
    if not issues:
        print("\n✅ Vertical Spread Monte Carlo implementation is sound")
    else:
        print("\n❌ Vertical Spread Monte Carlo has issues:")
        for issue in issues:
            print(f"  {issue}")
    
    return issues


def validate_collar_mc_logic():
    """
    Validate Collar Monte Carlo implementation.
    
    Collar Payoff: (S_T - S0) + call_premium - max(0, S_T - Kc) - put_premium + max(0, Kp - S_T) + div
    
    Financial Logic:
    - Protection floor: Put strike (downside protected)
    - Profit cap: Call strike (upside capped)
    - Net cost: Put premium - Call premium
    - P&L bounded between floor and cap
    
    Critical Tests:
    1. Downside protection: Max loss limited to (S0 - Kp + net_cost)
    2. Upside cap: Max gain limited to (Kc - S0 + net_debit)
    3. P&L bounded by collar strikes
    4. Reduces volatility vs unhedged stock
    """
    print("\n📊 Collar Validation")
    print("-" * 70)
    
    issues = []
    
    # Collar: Own stock at $100, Buy 95 put for $2, Sell 110 call for $1.50
    S0 = 100.0
    put_strike = 95.0
    call_strike = 110.0
    put_premium = 2.00
    call_premium = 1.50
    net_cost = put_premium - call_premium  # 0.50 debit
    days = 45
    iv = 0.25
    
    params = {
        "S0": S0,
        "days": days,
        "iv": iv,
        "Kp": put_strike,
        "put_premium": put_premium,
        "Kc": call_strike,
        "call_premium": call_premium,
        "div_ps_annual": 0.0
    }
    
    # Test 1: Formula verification at exact strikes (analytical check)
    print("Test 1: Downside Protection Formula (analytical)")
    # When S_T reaches put strike, what's the P&L?
    # Starting from S0=$100, ending at S_T=$95:
    # P&L = (95-100) + 1.50 - max(0, 95-110) - 2.00 + max(0, 95-95) + 0
    #     = -5 + 1.50 - 0 - 2.00 + 0 = -5.50 per share = -$550 per contract
    S_T_test = put_strike
    pnl_formula = ((S_T_test - S0) + call_premium - max(0, S_T_test - call_strike) 
                   - put_premium + max(0, put_strike - S_T_test)) * 100
    print(f"  Formula at put strike (S_T=${S_T_test}): ${pnl_formula:.2f}")
    
    # When S_T goes below put strike (e.g., $80), protected at put strike:
    S_T_crash = 80.0
    pnl_crash = ((S_T_crash - S0) + call_premium - max(0, S_T_crash - call_strike)
                 - put_premium + max(0, put_strike - S_T_crash)) * 100
    print(f"  Formula at crash (S_T=${S_T_crash}):     ${pnl_crash:.2f}")
    
    # Both should be the same (floor at put strike)
    if abs(pnl_formula - pnl_crash) < 1.0:
        print("  ✅ Downside protection formula correct (floor at put strike)")
    
    # Test 2: Formula verification at call strike (analytical check)
    print("\nTest 2: Upside Cap Formula (analytical)")
    # When S_T reaches call strike, what's the P&L?
    # Starting from S0=$100, ending at S_T=$110:
    # P&L = (110-100) + 1.50 - max(0, 110-110) - 2.00 + max(0, 95-110) + 0
    #     = 10 + 1.50 - 0 - 2.00 + 0 = 9.50 per share = $950 per contract
    S_T_test = call_strike
    pnl_formula = ((S_T_test - S0) + call_premium - max(0, S_T_test - call_strike)
                   - put_premium + max(0, put_strike - S_T_test)) * 100
    print(f"  Formula at call strike (S_T=${S_T_test}): ${pnl_formula:.2f}")
    
    # When S_T goes above call strike (e.g., $120), capped at call strike:
    S_T_rally = 120.0
    pnl_rally = ((S_T_rally - S0) + call_premium - max(0, S_T_rally - call_strike)
                 - put_premium + max(0, put_strike - S_T_rally)) * 100
    print(f"  Formula at rally (S_T=${S_T_rally}):      ${pnl_rally:.2f}")
    
    # Both should be the same (cap at call strike)
    if abs(pnl_formula - pnl_rally) < 1.0:
        print("  ✅ Upside cap formula correct (cap at call strike)")
    
    # Define theoretical bounds for later use
    theoretical_floor_pnl = -550.0  # From Test 1
    theoretical_cap_pnl = pnl_formula
    
    # Test 3: P&L bounded
    print("\nTest 3: P&L Bounds (should be between floor and cap)")
    result_dist = mc_pnl("COLLAR", params, n_paths=50000, mu=0.0, seed=42, rf=0.05)
    pnl_paths = result_dist["pnl_paths"]
    pnl_min = np.min(pnl_paths[np.isfinite(pnl_paths)])
    pnl_max = np.max(pnl_paths[np.isfinite(pnl_paths)])
    
    print(f"  Min P&L observed:    ${pnl_min:.2f}")
    print(f"  Max P&L observed:    ${pnl_max:.2f}")
    print(f"  Theoretical cap:     ${theoretical_cap_pnl:.2f}")
    print(f"  Theoretical floor:   ${theoretical_floor_pnl:.2f}")
    
    # Allow tolerance
    if pnl_max > theoretical_cap_pnl + 10.0:
        issues.append("❌ Collar P&L exceeds cap (logic error)")
    elif pnl_min < theoretical_floor_pnl - 10.0:
        issues.append("❌ Collar P&L exceeds floor (logic error)")
    else:
        print("  ✅ P&L properly bounded by collar strikes")
    
    # Test 4: Volatility reduction
    print("\nTest 4: Volatility Reduction (vs unhedged stock)")
    # Simulate unhedged stock
    rng = np.random.default_rng(42)
    S_T = gbm_terminal_prices(S0, 0.0, iv, days/365.0, 10000, rng)
    unhedged_pnl = (S_T - S0) * 100
    unhedged_std = np.std(unhedged_pnl[np.isfinite(unhedged_pnl)])
    
    collar_std = result_dist['pnl_std']
    
    print(f"  Unhedged stock std:  ${unhedged_std:.2f}")
    print(f"  Collar std:          ${collar_std:.2f}")
    print(f"  Reduction:           {(1 - collar_std/unhedged_std)*100:.1f}%")
    
    if collar_std >= unhedged_std:
        issues.append("⚠️  WARNING: Collar should reduce volatility vs unhedged stock")
        print("  ⚠️  Collar not reducing volatility as expected")
    else:
        print("  ✅ Collar properly reduces downside volatility")
    
    if not issues:
        print("\n✅ Collar Monte Carlo implementation is sound")
    else:
        print("\n❌ Collar Monte Carlo has issues:")
        for issue in issues:
            print(f"  {issue}")
    
    return issues


def validate_statistical_properties():
    """
    Validate statistical properties of Monte Carlo simulations.
    
    Tests:
    1. Convergence: More paths = more stable results
    2. Reproducibility: Same seed = same results
    3. Distribution: Results follow expected statistical properties
    4. Moments: Mean, variance, skewness, kurtosis reasonable
    """
    print("\n📊 Statistical Properties Validation")
    print("-" * 70)
    
    issues = []
    
    params = {
        "S0": 100.0,
        "days": 45,
        "iv": 0.25,
        "Kp": 95.0,
        "put_premium": 2.50,
        "div_ps_annual": 0.0
    }
    
    # Test 1: Convergence (SE-based)
    print("Test 1: Convergence (more paths = more stable; SE-based)")
    n1, n2, n3 = 1000, 10000, 50000
    result_1k = mc_pnl("CSP", params, n_paths=n1, mu=0.0, seed=42, rf=0.05)
    result_10k = mc_pnl("CSP", params, n_paths=n2, mu=0.0, seed=42, rf=0.05)
    result_50k = mc_pnl("CSP", params, n_paths=n3, mu=0.0, seed=42, rf=0.05)
    
    mean_1k = result_1k['pnl_expected']
    mean_10k = result_10k['pnl_expected']
    mean_50k = result_50k['pnl_expected']
    std_1k = result_1k['pnl_std']
    std_10k = result_10k['pnl_std']
    std_50k = result_50k['pnl_std']
    se_1k = std_1k / np.sqrt(n1)
    se_10k = std_10k / np.sqrt(n2)
    se_50k = std_50k / np.sqrt(n3)
    
    print(f"  1K mean ± SE:        ${mean_1k:.2f} ± ${se_1k:.2f}")
    print(f"  10K mean ± SE:       ${mean_10k:.2f} ± ${se_10k:.2f}")
    print(f"  50K mean ± SE:       ${mean_50k:.2f} ± ${se_50k:.2f}")
    
    # Check SE monotonic decrease
    se_ok = (se_50k < se_10k < se_1k)
    # Check differences within combined SE bands (4-sigma tolerance)
    diff_1k_10k = abs(mean_10k - mean_1k)
    diff_10k_50k = abs(mean_50k - mean_10k)
    band_1 = 4.0 * np.sqrt(se_1k**2 + se_10k**2)
    band_2 = 4.0 * np.sqrt(se_10k**2 + se_50k**2)
    within_bands = (diff_1k_10k <= band_1) and (diff_10k_50k <= band_2)
    
    if se_ok and within_bands:
        print("  ✅ Results converge properly with more paths (SE decreases, means within bands)")
    else:
        issues.append("⚠️  WARNING: Convergence check failed (SE/mean diffs outside bands)")
        if not se_ok:
            print("  ⚠️  Standard error not decreasing as expected")
        if not within_bands:
            print("  ⚠️  Mean differences exceed expected statistical bands")
    
    # Test 2: Reproducibility
    print("\nTest 2: Reproducibility (same seed = same results)")
    result_a = mc_pnl("CSP", params, n_paths=10000, mu=0.0, seed=123, rf=0.05)
    result_b = mc_pnl("CSP", params, n_paths=10000, mu=0.0, seed=123, rf=0.05)
    
    print(f"  Run A mean:          ${result_a['pnl_expected']:.2f}")
    print(f"  Run B mean:          ${result_b['pnl_expected']:.2f}")
    print(f"  Difference:          ${abs(result_a['pnl_expected'] - result_b['pnl_expected']):.2f}")
    
    if abs(result_a['pnl_expected'] - result_b['pnl_expected']) > 0.01:
        issues.append("❌ Results not reproducible with same seed")
    else:
        print("  ✅ Results are reproducible")
    
    # Test 3: No NaN/Inf pollution
    print("\nTest 3: Numerical Stability (no NaN or Inf)")
    pnl_paths = result_50k['pnl_paths']
    roi_paths = result_50k['roi_ann_paths']
    
    nan_pnl = np.sum(~np.isfinite(pnl_paths))
    nan_roi = np.sum(~np.isfinite(roi_paths))
    total_paths = len(pnl_paths)
    
    print(f"  NaN/Inf in P&L:      {nan_pnl}/{total_paths} ({nan_pnl/total_paths*100:.2f}%)")
    print(f"  NaN/Inf in ROI:      {nan_roi}/{total_paths} ({nan_roi/total_paths*100:.2f}%)")
    
    if nan_pnl/total_paths > 0.01:  # Allow <1% numerical issues
        issues.append("⚠️  WARNING: Excessive NaN/Inf in P&L paths")
        print("  ⚠️  Too many numerical errors in P&L")
    elif nan_roi/total_paths > 0.01:
        issues.append("⚠️  WARNING: Excessive NaN/Inf in ROI paths")
        print("  ⚠️  Too many numerical errors in ROI")
    else:
        print("  ✅ Numerical stability good")
    
    # Test 4: Sharpe ratio reasonableness
    print("\nTest 4: Sharpe Ratio Reasonableness")
    sharpe = result_50k.get('sharpe', float('nan'))
    print(f"  Sharpe ratio:        {sharpe:.3f}")
    
    if not np.isfinite(sharpe):
        issues.append("⚠️  WARNING: Sharpe ratio calculation failed")
        print("  ⚠️  Sharpe ratio is NaN")
    elif abs(sharpe) > 10.0:
        issues.append("⚠️  WARNING: Sharpe ratio seems unrealistic (>10)")
        print("  ⚠️  Sharpe ratio seems too high")
    else:
        print("  ✅ Sharpe ratio is reasonable")

    # Test 5: GBM expectation and variance checks
    print("\nTest 5: GBM Expectation/Variance (model sanity)")
    S0_gbm = 100.0
    mu_gbm = 0.05
    sigma_gbm = 0.20
    T_gbm = 45 / 365.0
    n_gbm = 200000
    rng = np.random.default_rng(7)
    S_T_gbm = gbm_terminal_prices(S0_gbm, mu_gbm, sigma_gbm, T_gbm, n_gbm, rng)
    mean_emp = float(np.mean(S_T_gbm))
    var_emp = float(np.var(S_T_gbm))
    mean_theory = S0_gbm * np.exp(mu_gbm * T_gbm)
    var_theory = (S0_gbm ** 2) * np.exp(2 * mu_gbm * T_gbm) * (np.exp((sigma_gbm ** 2) * T_gbm) - 1.0)
    rel_err_mean = abs(mean_emp - mean_theory) / mean_theory
    rel_err_var = abs(var_emp - var_theory) / var_theory
    print(f"  E[S_T] emp/theory:   {mean_emp:.2f} / {mean_theory:.2f} (rel err {rel_err_mean:.2%})")
    print(f"  Var[S_T] emp/theory: {var_emp:.2f} / {var_theory:.2f} (rel err {rel_err_var:.2%})")
    if rel_err_mean > 0.02 or rel_err_var > 0.05:
        issues.append("⚠️  WARNING: GBM expectation/variance deviate beyond tolerance")
        print("  ⚠️  GBM properties outside expected tolerance")
    else:
        print("  ✅ GBM moments match theory (within tolerance)")
    
    if not issues:
        print("\n✅ Statistical properties are sound")
    else:
        print("\n⚠️  Statistical properties have warnings:")
        for issue in issues:
            print(f"  {issue}")
    
    return issues


def validate_parameter_sensitivity():
    """
    Validate that Monte Carlo responds correctly to parameter changes.
    
    Expected Behaviors:
    1. Higher volatility → Wider distribution
    2. Longer time → More uncertainty
    3. Higher drift → Higher mean P&L (for long positions)
    4. Higher interest rate → More interest income (CSP)
    5. Higher dividends → Higher P&L for covered strategies that own stock (CC/Collar)
    """
    print("\n📊 Parameter Sensitivity Validation")
    print("-" * 70)
    
    issues = []
    
    base_params = {
        "S0": 100.0,
        "days": 45,
        "iv": 0.25,
        "Kp": 95.0,
        "put_premium": 2.50,
        "div_ps_annual": 0.0
    }
    
    # Test 1: Volatility sensitivity
    print("Test 1: Volatility Impact (higher vol = wider distribution)")
    params_low = base_params.copy()
    params_low["iv"] = 0.15
    result_low = mc_pnl("CSP", params_low, n_paths=20000, mu=0.0, seed=42, rf=0.05)
    
    params_high = base_params.copy()
    params_high["iv"] = 0.45
    result_high = mc_pnl("CSP", params_high, n_paths=20000, mu=0.0, seed=42, rf=0.05)
    
    print(f"  Low vol (15%) std:   ${result_low['pnl_std']:.2f}")
    print(f"  High vol (45%) std:  ${result_high['pnl_std']:.2f}")
    print(f"  Increase:            {(result_high['pnl_std']/result_low['pnl_std'] - 1)*100:.1f}%")
    
    if result_high['pnl_std'] <= result_low['pnl_std'] * 1.5:
        issues.append("❌ Volatility sensitivity too weak")
    else:
        print("  ✅ Volatility properly impacts distribution width")
    
    # Test 2: Time sensitivity
    print("\nTest 2: Time Impact (longer time = more uncertainty)")
    params_short = base_params.copy()
    params_short["days"] = 15
    result_short = mc_pnl("CSP", params_short, n_paths=20000, mu=0.0, seed=42, rf=0.05)
    
    params_long = base_params.copy()
    params_long["days"] = 90
    result_long = mc_pnl("CSP", params_long, n_paths=20000, mu=0.0, seed=42, rf=0.05)
    
    print(f"  Short (15d) std:     ${result_short['pnl_std']:.2f}")
    print(f"  Long (90d) std:      ${result_long['pnl_std']:.2f}")
    print(f"  Increase:            {(result_long['pnl_std']/result_short['pnl_std'] - 1)*100:.1f}%")
    
    if result_long['pnl_std'] <= result_short['pnl_std']:
        issues.append("❌ Time to expiration sensitivity incorrect")
    else:
        print("  ✅ Longer time properly increases uncertainty")
    
    # Test 3: Drift sensitivity (for stock strategies)
    print("\nTest 3: Drift Impact (for Covered Call - should increase mean P&L)")
    cc_params = {
        "S0": 100.0,
        "days": 45,
        "iv": 0.25,
        "Kc": 110.0,
        "call_premium": 1.50,
        "div_ps_annual": 0.0
    }
    
    result_no_drift = mc_pnl("CC", cc_params, n_paths=20000, mu=0.0, seed=42, rf=0.05)
    result_pos_drift = mc_pnl("CC", cc_params, n_paths=20000, mu=0.10, seed=42, rf=0.05)
    
    print(f"  No drift (0%) mean:  ${result_no_drift['pnl_expected']:.2f}")
    print(f"  Pos drift (10%):     ${result_pos_drift['pnl_expected']:.2f}")
    print(f"  Improvement:         ${result_pos_drift['pnl_expected'] - result_no_drift['pnl_expected']:.2f}")
    
    if result_pos_drift['pnl_expected'] <= result_no_drift['pnl_expected']:
        issues.append("❌ Positive drift should increase mean P&L for long stock")
    else:
        print("  ✅ Positive drift correctly increases mean P&L")
    
    # Test 4: Interest rate sensitivity (CSP)
    print("\nTest 4: Interest Rate Impact (CSP should earn more with higher rf)")
    result_no_rf = mc_pnl("CSP", base_params, n_paths=20000, mu=0.0, seed=42, rf=0.0)
    result_high_rf = mc_pnl("CSP", base_params, n_paths=20000, mu=0.0, seed=42, rf=0.10)
    
    print(f"  No interest (0%):    ${result_no_rf['pnl_expected']:.2f}")
    print(f"  High interest (10%): ${result_high_rf['pnl_expected']:.2f}")
    print(f"  Interest income:     ${result_high_rf['pnl_expected'] - result_no_rf['pnl_expected']:.2f}")
    
    if result_high_rf['pnl_expected'] <= result_no_rf['pnl_expected']:
        issues.append("❌ Interest rate not properly adding to CSP returns")
    else:
        print("  ✅ Risk-free interest properly adds to CSP returns")

    # Test 5: Dividend sensitivity (CC)
    print("\nTest 5: Dividend Impact (covered call earns dividends)")
    cc_params_div0 = cc_params.copy()
    cc_params_div0["div_ps_annual"] = 0.0
    cc_params_divhi = cc_params.copy()
    cc_params_divhi["div_ps_annual"] = 2.00  # $2 per share annual dividend
    res_div0 = mc_pnl("CC", cc_params_div0, n_paths=20000, mu=0.0, seed=42, rf=0.05)
    res_divhi = mc_pnl("CC", cc_params_divhi, n_paths=20000, mu=0.0, seed=42, rf=0.05)
    print(f"  No dividend mean:    ${res_div0['pnl_expected']:.2f}")
    print(f"  $2/yr dividend mean: ${res_divhi['pnl_expected']:.2f}")
    if res_divhi['pnl_expected'] <= res_div0['pnl_expected']:
        issues.append("❌ Dividend impact incorrect for covered call (should increase P&L)")
    else:
        print("  ✅ Dividends correctly increase CC P&L")
    
    if not issues:
        print("\n✅ Parameter sensitivity is correct")
    else:
        print("\n❌ Parameter sensitivity has issues:")
        for issue in issues:
            print(f"  {issue}")
    
    return issues


def validate_engine_robustness():
    """
    Validate engine robustness across all strategies:
    - Collateral (capital) is positive and finite
    - Summary statistics (mean/std) are finite
    - ROI arrays do not contain excessive NaN/Inf
    """
    print("\n📊 Engine Robustness Validation")
    print("-" * 70)
    issues = []

    configs = [
        ("CSP", dict(S0=100.0, days=45, iv=0.25, Kp=95.0, put_premium=2.50, div_ps_annual=0.0)),
        ("CC", dict(S0=100.0, days=45, iv=0.25, Kc=110.0, call_premium=1.50, div_ps_annual=0.0)),
        ("COLLAR", dict(S0=100.0, days=45, iv=0.25, Kc=110.0, call_premium=1.50, Kp=95.0, put_premium=2.00, div_ps_annual=0.0)),
        ("IRON_CONDOR", dict(S0=100.0, days=45, iv=0.25, put_short_strike=95.0, put_long_strike=90.0, call_short_strike=105.0, call_long_strike=110.0, net_credit=1.00)),
        ("BULL_PUT_SPREAD", dict(S0=100.0, days=45, iv=0.25, sell_strike=95.0, buy_strike=90.0, net_credit=2.00)),
        ("BEAR_CALL_SPREAD", dict(S0=100.0, days=45, iv=0.25, sell_strike=105.0, buy_strike=110.0, net_credit=2.00)),
    ]

    for strat, params in configs:
        res = mc_pnl(strat, params, n_paths=20000, mu=0.0, seed=123, rf=0.05)
        collat = res.get('collateral', float('nan'))
        mean = res.get('pnl_expected', float('nan'))
        std = res.get('pnl_std', float('nan'))
        roi = res.get('roi_ann_paths', None)
        ok = True
        if not np.isfinite(collat) or collat <= 0:
            issues.append(f"❌ {strat}: collateral invalid (value={collat})")
            ok = False
        if not (np.isfinite(mean) and np.isfinite(std)):
            issues.append(f"❌ {strat}: summary statistics not finite")
            ok = False
        if isinstance(roi, np.ndarray):
            bad = np.sum(~np.isfinite(roi))
            if bad / roi.size > 0.01:
                issues.append(f"⚠️  {strat}: ROI contains {bad}/{roi.size} non-finite values (>1%)")
                ok = False
        print(f"  {strat:16} Collateral=${collat:.2f}  Mean=${mean:.2f}  Std=${std:.2f}  {'✓' if ok else '✗'}")

    if not issues:
        print("\n✅ Engine robustness checks passed")
    else:
        print("\n❌ Engine robustness has issues:")
        for issue in issues:
            print(f"  {issue}")

    return issues

def validate_all():
    """Run all Monte Carlo validation tests."""
    print("=" * 70)
    print("MONTE CARLO RISK ANALYSIS VALIDATION")
    print("=" * 70)
    print()
    print("This validator checks the CONCEPTUAL SOUNDNESS and OUTCOME")
    print("REASONABLENESS of Monte Carlo simulations for each strategy.")
    print()
    print("=" * 70)
    
    all_issues = []
    
    # Strategy-specific validations
    all_issues.extend(validate_csp_mc_logic())
    all_issues.extend(validate_spread_mc_logic())
    all_issues.extend(validate_collar_mc_logic())
    
    # Cross-strategy validations
    all_issues.extend(validate_statistical_properties())
    all_issues.extend(validate_parameter_sensitivity())
    all_issues.extend(validate_engine_robustness())
    
    print()
    print("=" * 70)
    
    critical_issues = [i for i in all_issues if "❌" in i]
    warnings = [i for i in all_issues if "⚠️" in i]
    
    if critical_issues:
        print(f"❌ CRITICAL: Found {len(critical_issues)} critical Monte Carlo errors")
        print(f"⚠️  WARNING: Found {len(warnings)} potential issues")
        print()
        print("CRITICAL ISSUES MUST BE FIXED BEFORE USING MC RISK ANALYSIS!")
    elif warnings:
        print(f"⚠️  Found {len(warnings)} warnings to review")
        print()
        print("No critical errors, but review warnings for improvements.")
    else:
        print("✅ ALL MONTE CARLO VALIDATION CHECKS PASSED")
        print()
        print("Monte Carlo risk analysis is conceptually sound and produces")
        print("reasonable outcomes across all strategies.")
    
    print("=" * 70)
    
    return 1 if critical_issues else 0


if __name__ == "__main__":
    sys.exit(validate_all())
