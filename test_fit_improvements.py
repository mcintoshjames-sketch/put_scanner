#!/usr/bin/env python3
"""
Test Best-Practice Fit Improvements

Validates new checks added to evaluate_fit():
- Volume/OI ratio
- Earnings proximity
- Wing distance (Iron Condor)
- Cost basis check (CC)
- New warning flags

Run: python test_fit_improvements.py
"""

import sys
import pandas as pd
import warnings
warnings.filterwarnings('ignore')

from strategy_lab import evaluate_fit


def test_volume_oi_ratio():
    """Test Volume/OI ratio check."""
    print("="*70)
    print("TEST 1: VOLUME/OI RATIO CHECK")
    print("="*70)
    
    test_cases = [
        ("High turnover", {"Volume": 1000, "OI": 1500}, "✅"),  # 0.67 ratio
        ("Moderate turnover", {"Volume": 400, "OI": 1000}, "⚠️"),  # 0.4 ratio
        ("Low turnover", {"Volume": 100, "OI": 1000}, "❌"),  # 0.1 ratio
        ("Missing volume", {"OI": 1000}, "⚠️"),  # n/a
    ]
    
    tests_passed = 0
    tests_total = len(test_cases)
    
    for name, data, expected_status in test_cases:
        row = pd.Series({
            "Ticker": "SPY",
            "Price": 570.0,
            "Days": 30,
            "Strike": 550.0,
            "Premium": 5.0,
            "OI": data.get("OI", 0),
            "Volume": data.get("Volume", float("nan")),
            "Spread%": 2.0,
            "IV": 20.0,
            "ROI%_ann": 25.0,
            "ROI%_excess_bills": 20.0,
        })
        
        thresholds = {"min_oi": 200, "max_spread": 10.0, "min_cushion": 1.0}
        df_fit, _ = evaluate_fit("CSP", row, thresholds)
        
        vol_oi_check = df_fit[df_fit['Check'] == 'Volume/OI ratio']
        if len(vol_oi_check) > 0:
            status = vol_oi_check.iloc[0]['Status']
            if status == expected_status:
                print(f"✅ {name}: {status} (expected {expected_status})")
                tests_passed += 1
            else:
                print(f"❌ {name}: {status} (expected {expected_status})")
        else:
            print(f"❌ {name}: Check not found")
    
    print(f"\nResults: {tests_passed}/{tests_total} passed\n")
    return tests_passed, tests_total


def test_earnings_proximity():
    """Test earnings proximity check."""
    print("="*70)
    print("TEST 2: EARNINGS PROXIMITY CHECK")
    print("="*70)
    
    test_cases = [
        ("Earnings during cycle", {"Days": 30, "DaysToEarnings": 15}, "⚠️", True),
        ("Earnings after expiry", {"Days": 30, "DaysToEarnings": 35}, "⚠️", False),
        ("No earnings soon", {"Days": 30, "DaysToEarnings": 60}, "✅", False),
        ("Earnings data missing", {"Days": 30, "DaysToEarnings": -1}, None, False),
    ]
    
    tests_passed = 0
    tests_total = len(test_cases)
    
    for name, data, expected_status, expect_flag in test_cases:
        row = pd.Series({
            "Ticker": "AAPL",
            "Price": 170.0,
            "Days": data["Days"],
            "Strike": 165.0,
            "Premium": 3.0,
            "OI": 500,
            "Spread%": 2.0,
            "IV": 25.0,
            "ROI%_ann": 30.0,
            "ROI%_excess_bills": 25.0,
            "DaysToEarnings": data["DaysToEarnings"],
        })
        
        thresholds = {"min_oi": 200, "max_spread": 10.0, "min_cushion": 1.0}
        df_fit, flags = evaluate_fit("CSP", row, thresholds)
        
        earnings_check = df_fit[df_fit['Check'] == 'Earnings risk']
        
        if expected_status is None:
            # Should not have the check
            if len(earnings_check) == 0:
                print(f"✅ {name}: Check correctly omitted (no data)")
                tests_passed += 1
            else:
                print(f"❌ {name}: Check should be omitted when data missing")
        else:
            if len(earnings_check) > 0:
                status = earnings_check.iloc[0]['Status']
                flag_set = flags.get("earnings_risk", False)
                
                if status == expected_status and flag_set == expect_flag:
                    print(f"✅ {name}: {status}, flag={flag_set}")
                    tests_passed += 1
                else:
                    print(f"❌ {name}: {status}/{flag_set} (expected {expected_status}/{expect_flag})")
            else:
                print(f"❌ {name}: Check not found")
    
    print(f"\nResults: {tests_passed}/{tests_total} passed\n")
    return tests_passed, tests_total


def test_wing_distance():
    """Test wing distance check for Iron Condor."""
    print("="*70)
    print("TEST 3: WING DISTANCE CHECK (IRON CONDOR)")
    print("="*70)
    
    test_cases = [
        ("Wide wings", {"PL": 530, "PS": 550, "CS": 590, "CL": 610}, "✅"),  # $20 wings = ~3.5%
        ("Moderate wings", {"PL": 540, "PS": 550, "CS": 590, "CL": 600}, "⚠️"),  # $10 wings = ~1.8%
        ("Tight wings", {"PL": 548, "PS": 550, "CS": 590, "CL": 592}, "❌"),  # $2 wings = ~0.36%
    ]
    
    tests_passed = 0
    tests_total = len(test_cases)
    
    for name, strikes, expected_status in test_cases:
        row = pd.Series({
            "Ticker": "SPY",
            "Price": 570.0,
            "Days": 30,
            "PutLongStrike": strikes["PL"],
            "PutShortStrike": strikes["PS"],
            "CallShortStrike": strikes["CS"],
            "CallLongStrike": strikes["CL"],
            "NetCredit": 4.0,
            "OI": 500,
            "Spread%": 2.0,
            "IV": 20.0,
            "ROI%_ann": 35.0,
            "ROI%_excess_bills": 30.0,
        })
        
        thresholds = {"min_oi": 200, "max_spread": 10.0, "min_cushion": 1.0}
        df_fit, _ = evaluate_fit("IRON_CONDOR", row, thresholds)
        
        wing_check = df_fit[df_fit['Check'] == 'Wing distance']
        if len(wing_check) > 0:
            status = wing_check.iloc[0]['Status']
            if status == expected_status:
                print(f"✅ {name}: {status} (expected {expected_status})")
                tests_passed += 1
            else:
                print(f"❌ {name}: {status} (expected {expected_status})")
        else:
            print(f"❌ {name}: Check not found")
    
    print(f"\nResults: {tests_passed}/{tests_total} passed\n")
    return tests_passed, tests_total


def test_cost_basis_check():
    """Test cost basis check for Covered Call."""
    print("="*70)
    print("TEST 4: COST BASIS CHECK (COVERED CALL)")
    print("="*70)
    
    test_cases = [
        ("Strike above basis", {"Strike": 175, "CostBasis": 170}, "✅", False),
        ("Strike below basis", {"Strike": 165, "CostBasis": 170}, "❌", True),
        ("Strike at basis", {"Strike": 170, "CostBasis": 170}, "✅", False),
        ("No cost basis data", {"Strike": 175}, None, False),
    ]
    
    tests_passed = 0
    tests_total = len(test_cases)
    
    for name, data, expected_status, expect_flag in test_cases:
        row = pd.Series({
            "Ticker": "AAPL",
            "Price": 170.0,
            "Days": 30,
            "Strike": data["Strike"],
            "Premium": 3.0,
            "OI": 500,
            "Spread%": 2.0,
            "IV": 25.0,
            "ROI%_ann": 30.0,
            "ROI%_excess_bills": 25.0,
            "CostBasis": data.get("CostBasis", float("nan")),
        })
        
        thresholds = {"min_oi": 200, "max_spread": 10.0, "min_cushion": 1.0}
        df_fit, flags = evaluate_fit("CC", row, thresholds)
        
        basis_check = df_fit[df_fit['Check'] == 'Strike vs cost basis']
        
        if expected_status is None:
            # Should not have the check
            if len(basis_check) == 0:
                print(f"✅ {name}: Check correctly omitted (no data)")
                tests_passed += 1
            else:
                print(f"❌ {name}: Check should be omitted when data missing")
        else:
            if len(basis_check) > 0:
                status = basis_check.iloc[0]['Status']
                flag_set = flags.get("below_cost_basis", False)
                
                if status == expected_status and flag_set == expect_flag:
                    print(f"✅ {name}: {status}, flag={flag_set}")
                    tests_passed += 1
                else:
                    print(f"❌ {name}: {status}/{flag_set} (expected {expected_status}/{expect_flag})")
            else:
                print(f"❌ {name}: Check not found")
    
    print(f"\nResults: {tests_passed}/{tests_total} passed\n")
    return tests_passed, tests_total


def test_new_flags():
    """Test that new flags are properly set."""
    print("="*70)
    print("TEST 5: NEW FLAGS VALIDATION")
    print("="*70)
    
    # Test earnings_risk flag
    row_earnings = pd.Series({
        "Ticker": "NVDA",
        "Price": 500.0,
        "Days": 30,
        "Strike": 490.0,
        "Premium": 10.0,
        "OI": 1000,
        "Spread%": 2.0,
        "IV": 35.0,
        "ROI%_ann": 40.0,
        "ROI%_excess_bills": 35.0,
        "DaysToEarnings": 10,  # Earnings during cycle
    })
    
    thresholds = {"min_oi": 200, "max_spread": 10.0}
    _, flags = evaluate_fit("CSP", row_earnings, thresholds)
    
    tests_passed = 0
    tests_total = 2
    
    if flags.get("earnings_risk", False):
        print("✅ earnings_risk flag set correctly")
        tests_passed += 1
    else:
        print("❌ earnings_risk flag not set")
    
    # Test below_cost_basis flag
    row_cc = pd.Series({
        "Ticker": "TSLA",
        "Price": 250.0,
        "Days": 30,
        "Strike": 245.0,  # Below cost basis
        "Premium": 5.0,
        "OI": 800,
        "Spread%": 2.0,
        "IV": 40.0,
        "ROI%_ann": 30.0,
        "ROI%_excess_bills": 25.0,
        "CostBasis": 260.0,  # Cost basis above strike
    })
    
    _, flags = evaluate_fit("CC", row_cc, thresholds)
    
    if flags.get("below_cost_basis", False):
        print("✅ below_cost_basis flag set correctly")
        tests_passed += 1
    else:
        print("❌ below_cost_basis flag not set")
    
    print(f"\nResults: {tests_passed}/{tests_total} passed\n")
    return tests_passed, tests_total


if __name__ == "__main__":
    print("\n" + "="*70)
    print("BEST-PRACTICE FIT IMPROVEMENTS TEST SUITE")
    print("="*70 + "\n")
    
    # Run all tests
    results = []
    results.append(test_volume_oi_ratio())
    results.append(test_earnings_proximity())
    results.append(test_wing_distance())
    results.append(test_cost_basis_check())
    results.append(test_new_flags())
    
    # Summary
    total_passed = sum(r[0] for r in results)
    total_tests = sum(r[1] for r in results)
    
    print("="*70)
    print(f"OVERALL RESULTS: {total_passed}/{total_tests} tests passed")
    print("="*70)
    
    if total_passed == total_tests:
        print("✅ ALL TESTS PASSED - Best-practice fit improvements working correctly!")
        exit(0)
    else:
        print(f"❌ {total_tests - total_passed} test(s) failed")
        exit(1)
