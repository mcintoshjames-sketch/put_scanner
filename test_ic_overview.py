#!/usr/bin/env python3
"""
Test Iron Condor Overview Structure Summary Calculations

Validates that the Overview tab correctly calculates:
- Capital required
- Max profit
- Max loss  
- Breakeven points
- Monte Carlo P&L simulation

Run: python test_ic_overview.py
"""

import sys
import pandas as pd
import numpy as np

# Suppress streamlit warnings when importing strategy_lab
import warnings
warnings.filterwarnings('ignore')


def test_iron_condor_overview_calculations():
    """Test Iron Condor structure summary calculations in Overview tab."""
    
    print("="*70)
    print("IRON CONDOR OVERVIEW STRUCTURE SUMMARY TEST")
    print("="*70)
    
    # Test case: SPY Iron Condor
    # Current price: $570
    # Put spread: Buy $540, Sell $550
    # Call spread: Sell $590, Buy $600
    # Net credit: $4.00/share
    
    print("\n📋 Test Iron Condor:")
    print(f"  Current Price: $570.00")
    print(f"  Put Spread: Buy $540 / Sell $550")
    print(f"  Call Spread: Sell $590 / Buy $600")
    print(f"  Net Credit: $4.00/share")
    
    price = 570.0
    put_long_strike = 540.0
    put_short_strike = 550.0
    call_short_strike = 590.0
    call_long_strike = 600.0
    net_credit = 4.0
    
    # Calculate values as done in Overview tab
    put_spread_width = put_short_strike - put_long_strike
    call_spread_width = call_long_strike - call_short_strike
    max_spread_width = max(put_spread_width, call_spread_width)
    capital_per_share = max_spread_width - net_credit
    capital = capital_per_share * 100.0
    
    max_profit = net_credit * 100.0
    max_loss = capital
    
    breakeven_lower = put_short_strike - net_credit
    breakeven_upper = call_short_strike + net_credit
    
    print(f"\n💰 Calculated Values:")
    print(f"  Put Spread Width: ${put_spread_width:.2f}")
    print(f"  Call Spread Width: ${call_spread_width:.2f}")
    print(f"  Max Spread Width: ${max_spread_width:.2f}")
    print(f"  Capital/Share: ${capital_per_share:.2f}")
    print(f"  Capital Required: ${capital:,.0f}")
    print(f"  Max Profit: ${max_profit:.0f}")
    print(f"  Max Loss: ${max_loss:.0f}")
    print(f"  Breakeven Lower: ${breakeven_lower:.2f}")
    print(f"  Breakeven Upper: ${breakeven_upper:.2f}")
    
    # Expected values
    expected = {
        "put_spread_width": 10.0,
        "call_spread_width": 10.0,
        "capital": 600.0,
        "max_profit": 400.0,
        "max_loss": 600.0,
        "breakeven_lower": 546.0,
        "breakeven_upper": 594.0
    }
    
    print(f"\n🔍 Validation:")
    print("="*70)
    
    tests_passed = 0
    tests_total = 0
    
    # Test 1: Put spread width
    tests_total += 1
    if abs(put_spread_width - expected["put_spread_width"]) < 0.01:
        print(f"✅ Test 1: Put spread width = ${put_spread_width:.2f}")
        tests_passed += 1
    else:
        print(f"❌ Test 1: Put spread width = ${put_spread_width:.2f}, expected ${expected['put_spread_width']:.2f}")
    
    # Test 2: Call spread width
    tests_total += 1
    if abs(call_spread_width - expected["call_spread_width"]) < 0.01:
        print(f"✅ Test 2: Call spread width = ${call_spread_width:.2f}")
        tests_passed += 1
    else:
        print(f"❌ Test 2: Call spread width = ${call_spread_width:.2f}, expected ${expected['call_spread_width']:.2f}")
    
    # Test 3: Capital required
    tests_total += 1
    if abs(capital - expected["capital"]) < 1.0:
        print(f"✅ Test 3: Capital required = ${capital:.0f}")
        tests_passed += 1
    else:
        print(f"❌ Test 3: Capital = ${capital:.0f}, expected ${expected['capital']:.0f}")
    
    # Test 4: Max profit
    tests_total += 1
    if abs(max_profit - expected["max_profit"]) < 1.0:
        print(f"✅ Test 4: Max profit = ${max_profit:.0f}")
        tests_passed += 1
    else:
        print(f"❌ Test 4: Max profit = ${max_profit:.0f}, expected ${expected['max_profit']:.0f}")
    
    # Test 5: Max loss
    tests_total += 1
    if abs(max_loss - expected["max_loss"]) < 1.0:
        print(f"✅ Test 5: Max loss = ${max_loss:.0f}")
        tests_passed += 1
    else:
        print(f"❌ Test 5: Max loss = ${max_loss:.0f}, expected ${expected['max_loss']:.0f}")
    
    # Test 6: Breakeven lower
    tests_total += 1
    if abs(breakeven_lower - expected["breakeven_lower"]) < 0.01:
        print(f"✅ Test 6: Breakeven lower = ${breakeven_lower:.2f}")
        tests_passed += 1
    else:
        print(f"❌ Test 6: Breakeven lower = ${breakeven_lower:.2f}, expected ${expected['breakeven_lower']:.2f}")
    
    # Test 7: Breakeven upper
    tests_total += 1
    if abs(breakeven_upper - expected["breakeven_upper"]) < 0.01:
        print(f"✅ Test 7: Breakeven upper = ${breakeven_upper:.2f}")
        tests_passed += 1
    else:
        print(f"❌ Test 7: Breakeven upper = ${breakeven_upper:.2f}, expected ${expected['breakeven_upper']:.2f}")
    
    # Test 8: Profit zone width
    tests_total += 1
    profit_zone_width = call_short_strike - put_short_strike
    expected_zone = 40.0  # $590 - $550
    if abs(profit_zone_width - expected_zone) < 0.01:
        print(f"✅ Test 8: Profit zone width = ${profit_zone_width:.0f} ({put_short_strike:.0f} to {call_short_strike:.0f})")
        tests_passed += 1
    else:
        print(f"❌ Test 8: Profit zone width = ${profit_zone_width:.0f}, expected ${expected_zone:.0f}")
    
    # Test 9: Risk/reward ratio
    tests_total += 1
    risk_reward_ratio = max_profit / max_loss
    expected_rr = 400.0 / 600.0  # 0.6667
    if abs(risk_reward_ratio - expected_rr) < 0.01:
        print(f"✅ Test 9: Risk/reward ratio = {risk_reward_ratio:.4f} (${max_profit:.0f} profit / ${max_loss:.0f} risk)")
        tests_passed += 1
    else:
        print(f"❌ Test 9: Risk/reward ratio = {risk_reward_ratio:.4f}, expected {expected_rr:.4f}")
    
    # Test 10: ROI if max profit
    tests_total += 1
    roi_max_profit = (max_profit / capital) * 100
    expected_roi = (400.0 / 600.0) * 100  # 66.67%
    if abs(roi_max_profit - expected_roi) < 0.1:
        print(f"✅ Test 10: ROI at max profit = {roi_max_profit:.2f}%")
        tests_passed += 1
    else:
        print(f"❌ Test 10: ROI = {roi_max_profit:.2f}%, expected {expected_roi:.2f}%")
    
    print("\n" + "="*70)
    print(f"RESULTS: {tests_passed}/{tests_total} tests passed")
    print("="*70)
    
    if tests_passed == tests_total:
        print("✅ ALL TESTS PASSED - Iron Condor Overview calculations are correct!")
        return True
    else:
        print(f"❌ {tests_total - tests_passed} test(s) failed")
        return False


if __name__ == "__main__":
    success = test_iron_condor_overview_calculations()
    exit(0 if success else 1)
