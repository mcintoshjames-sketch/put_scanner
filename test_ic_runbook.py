#!/usr/bin/env python3
"""
Test Iron Condor Plan & Runbook Functionality

Validates that the Plan & Runbook tab correctly:
- Evaluates fit criteria (evaluate_fit)
- Generates runbook with entry/exit orders (build_runbook)

Run: python test_ic_runbook.py
"""

import sys
import pandas as pd
import warnings
warnings.filterwarnings('ignore')

# Import functions from strategy_lab
from strategy_lab import evaluate_fit, build_runbook, _fmt_usd


def test_iron_condor_evaluate_fit():
    """Test Iron Condor fit evaluation."""
    
    print("="*70)
    print("IRON CONDOR EVALUATE_FIT TEST")
    print("="*70)
    
    # Create test Iron Condor row
    row = pd.Series({
        "Ticker": "SPY",
        "Price": 570.0,
        "Days": 30,
        "Exp": "2025-11-29",
        "PutLongStrike": 540.0,
        "PutShortStrike": 550.0,
        "CallShortStrike": 590.0,
        "CallLongStrike": 600.0,
        "NetCredit": 4.0,
        "IV": 20.0,
        "OI": 500,
        "Spread%": 3.0,
        "ROI%_ann": 45.0,
        "ROI%_excess_bills": 40.0,
        "Score": 75.0
    })
    
    thresholds = {
        "min_oi": 200,
        "max_spread": 10.0,
        "min_cushion": 1.0,
        "min_otm_csp": 10.0,
        "min_otm_cc": 2.0
    }
    
    print(f"\n📋 Test Iron Condor:")
    print(f"  {row['Ticker']} @ ${row['Price']:.2f}")
    print(f"  Put Spread: ${row['PutLongStrike']:.0f}/${row['PutShortStrike']:.0f}")
    print(f"  Call Spread: ${row['CallShortStrike']:.0f}/${row['CallLongStrike']:.0f}")
    print(f"  Net Credit: ${row['NetCredit']:.2f}")
    print(f"  Days: {row['Days']}")
    
    # Run evaluate_fit
    df_fit, flags = evaluate_fit("IRON_CONDOR", row, thresholds, risk_free=0.05, div_y=0.015, bill_yield=0.05)
    
    print(f"\n✅ Fit Evaluation Results:")
    print(df_fit.to_string(index=False))
    
    print(f"\n🚩 Flags:")
    for flag, value in flags.items():
        print(f"  {flag}: {value}")
    
    # Validation checks
    print(f"\n🔍 Validation:")
    print("="*70)
    
    tests_passed = 0
    tests_total = 0
    
    # Test 1: Tenor sweet spot (30 DTE should be in 30-60 range)
    tests_total += 1
    tenor_check = df_fit[df_fit['Check'] == 'Tenor sweet spot']
    if len(tenor_check) > 0 and tenor_check.iloc[0]['Status'] == '✅':
        print(f"✅ Test 1: Tenor sweet spot check passed ({row['Days']} DTE in range)")
        tests_passed += 1
    else:
        print(f"❌ Test 1: Tenor sweet spot check failed")
    
    # Test 2: Liquidity check (OI 500 > 200, spread 3% < 10%)
    tests_total += 1
    liquidity_check = df_fit[df_fit['Check'] == 'Liquidity']
    if len(liquidity_check) > 0 and liquidity_check.iloc[0]['Status'] == '✅':
        print(f"✅ Test 2: Liquidity check passed (OI={row['OI']}, spread={row['Spread%']:.1f}%)")
        tests_passed += 1
    else:
        print(f"❌ Test 2: Liquidity check failed")
    
    # Test 3: Profit zone width check
    tests_total += 1
    profit_zone_check = df_fit[df_fit['Check'] == 'Profit zone width']
    if len(profit_zone_check) > 0:
        expected_zone = row['CallShortStrike'] - row['PutShortStrike']
        print(f"✅ Test 3: Profit zone width check found (${expected_zone:.0f})")
        tests_passed += 1
    else:
        print(f"❌ Test 3: Profit zone width check missing")
    
    # Test 4: Risk/reward ratio check
    tests_total += 1
    rr_check = df_fit[df_fit['Check'] == 'Risk/reward ratio']
    if len(rr_check) > 0:
        print(f"✅ Test 4: Risk/reward ratio check found")
        tests_passed += 1
    else:
        print(f"❌ Test 4: Risk/reward ratio check missing")
    
    # Test 5: Balanced spreads check
    tests_total += 1
    balance_check = df_fit[df_fit['Check'] == 'Balanced spreads']
    if len(balance_check) > 0 and balance_check.iloc[0]['Status'] == '✅':
        print(f"✅ Test 5: Balanced spreads check passed (both $10 wide)")
        tests_passed += 1
    else:
        print(f"❌ Test 5: Balanced spreads check failed")
    
    # Test 6: Excess vs T-bills check
    tests_total += 1
    excess_check = df_fit[df_fit['Check'] == 'Excess vs T-bills']
    if len(excess_check) > 0 and excess_check.iloc[0]['Status'] == '✅':
        print(f"✅ Test 6: Excess vs T-bills check passed")
        tests_passed += 1
    else:
        print(f"❌ Test 6: Excess vs T-bills check failed or missing")
    
    print(f"\n{'='*70}")
    print(f"EVALUATE_FIT: {tests_passed}/{tests_total} tests passed")
    
    return tests_passed, tests_total


def test_iron_condor_build_runbook():
    """Test Iron Condor runbook generation."""
    
    print("\n" + "="*70)
    print("IRON CONDOR BUILD_RUNBOOK TEST")
    print("="*70)
    
    # Create test Iron Condor row
    row = pd.Series({
        "Ticker": "SPY",
        "Price": 570.0,
        "Days": 30,
        "Exp": "2025-11-29",
        "PutLongStrike": 540.0,
        "PutShortStrike": 550.0,
        "CallShortStrike": 590.0,
        "CallLongStrike": 600.0,
        "NetCredit": 4.0
    })
    
    print(f"\n📋 Test Iron Condor:")
    print(f"  {row['Ticker']} @ ${row['Price']:.2f}")
    print(f"  Expiration: {row['Exp']}")
    print(f"  Strikes: P ${row['PutLongStrike']:.0f}/${row['PutShortStrike']:.0f} | C ${row['CallShortStrike']:.0f}/${row['CallLongStrike']:.0f}")
    print(f"  Net Credit: ${row['NetCredit']:.2f}")
    
    # Generate runbook
    runbook = build_runbook("IRON_CONDOR", row, contracts=2, capture_pct=0.70)
    
    print(f"\n📄 Generated Runbook:")
    print("="*70)
    print(runbook)
    print("="*70)
    
    # Validation checks
    print(f"\n🔍 Validation:")
    print("="*70)
    
    tests_passed = 0
    tests_total = 0
    
    # Test 1: Contains ticker and strategy
    tests_total += 1
    if "SPY" in runbook and "IRON CONDOR" in runbook:
        print(f"✅ Test 1: Runbook contains ticker and strategy")
        tests_passed += 1
    else:
        print(f"❌ Test 1: Missing ticker or strategy")
    
    # Test 2: Contains all 4 leg strikes
    tests_total += 1
    has_strikes = all(str(int(strike)) in runbook for strike in [540, 550, 590, 600])
    if has_strikes:
        print(f"✅ Test 2: All 4 strikes present (540/550/590/600)")
        tests_passed += 1
    else:
        print(f"❌ Test 2: Missing strike prices")
    
    # Test 3: Contains entry orders (BTO/STO for all 4 legs)
    tests_total += 1
    has_entry = "Buy to Open" in runbook and "Sell to Open" in runbook
    leg_count = runbook.count("Buy to Open") + runbook.count("Sell to Open")
    if has_entry and leg_count >= 4:
        print(f"✅ Test 3: Contains entry orders for 4 legs")
        tests_passed += 1
    else:
        print(f"❌ Test 3: Missing or incomplete entry orders")
    
    # Test 4: Contains NET CREDIT order type
    tests_total += 1
    if "NET CREDIT" in runbook:
        print(f"✅ Test 4: Specifies NET CREDIT order type")
        tests_passed += 1
    else:
        print(f"❌ Test 4: Missing NET CREDIT specification")
    
    # Test 5: Contains profit-taking triggers
    tests_total += 1
    if "PROFIT" in runbook and "70%" in runbook:
        print(f"✅ Test 5: Contains profit-taking triggers (70% capture)")
        tests_passed += 1
    else:
        print(f"❌ Test 5: Missing profit-taking triggers")
    
    # Test 6: Contains risk close-out triggers
    tests_total += 1
    if "RISK CLOSE" in runbook and "breakeven" in runbook.lower():
        print(f"✅ Test 6: Contains risk close-out triggers")
        tests_passed += 1
    else:
        print(f"❌ Test 6: Missing risk close-out triggers")
    
    # Test 7: Contains breakeven prices
    tests_total += 1
    be_lower = 550 - 4  # 546
    be_upper = 590 + 4  # 594
    if f"${be_lower:.2f}" in runbook and f"${be_upper:.2f}" in runbook:
        print(f"✅ Test 7: Contains breakeven prices (${be_lower:.2f} and ${be_upper:.2f})")
        tests_passed += 1
    else:
        print(f"❌ Test 7: Missing breakeven prices")
    
    # Test 8: Contains max profit and max loss
    tests_total += 1
    max_profit = 4.0 * 100  # $400
    max_loss = (10 - 4) * 100  # $600
    if "Max profit" in runbook and "Max loss" in runbook:
        print(f"✅ Test 8: Contains max profit and max loss calculations")
        tests_passed += 1
    else:
        print(f"❌ Test 8: Missing max profit/loss")
    
    # Test 9: Contains exit orders for all 4 legs
    tests_total += 1
    has_exit = "STC" in runbook and "BTC" in runbook
    if has_exit:
        print(f"✅ Test 9: Contains exit orders (BTC/STC)")
        tests_passed += 1
    else:
        print(f"❌ Test 9: Missing exit orders")
    
    # Test 10: Contains adjustment strategies
    tests_total += 1
    if "ADJUSTMENTS" in runbook or "roll" in runbook.lower():
        print(f"✅ Test 10: Contains adjustment strategies")
        tests_passed += 1
    else:
        print(f"❌ Test 10: Missing adjustment strategies")
    
    print(f"\n{'='*70}")
    print(f"BUILD_RUNBOOK: {tests_passed}/{tests_total} tests passed")
    
    return tests_passed, tests_total


if __name__ == "__main__":
    # Run both tests
    fit_passed, fit_total = test_iron_condor_evaluate_fit()
    runbook_passed, runbook_total = test_iron_condor_build_runbook()
    
    total_passed = fit_passed + runbook_passed
    total_tests = fit_total + runbook_total
    
    print("\n" + "="*70)
    print(f"OVERALL RESULTS: {total_passed}/{total_tests} tests passed")
    print("="*70)
    
    if total_passed == total_tests:
        print("✅ ALL TESTS PASSED - Iron Condor Plan & Runbook working correctly!")
        exit(0)
    else:
        print(f"❌ {total_tests - total_passed} test(s) failed")
        exit(1)
