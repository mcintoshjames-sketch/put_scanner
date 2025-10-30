#!/usr/bin/env python3
"""
Expiration Safety Test Suite

Tests the expiration risk assessment and filtering mechanisms to ensure
they adequately protect users from non-standard expiration risks.

Test Coverage:
1. Date detection (3rd Friday vs weekly Friday vs non-Friday)
2. Risk level assessment per strategy
3. Action determination (ALLOW/WARN/BLOCK)
4. Liquidity-based risk escalation
5. Multi-leg strategy special handling
6. Edge cases (invalid dates, boundary conditions)
"""

import sys
from datetime import datetime, timedelta
import pandas as pd

# Import the safety function
sys.path.insert(0, '/workspaces/put_scanner')
from strategy_lab import check_expiration_risk


def print_test_header(test_name):
    """Print formatted test header."""
    print("\n" + "=" * 80)
    print(f"TEST: {test_name}")
    print("=" * 80)


def print_result(passed, message):
    """Print test result."""
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"{status}: {message}")


def assert_equal(actual, expected, field_name):
    """Assert equality and return pass/fail."""
    passed = actual == expected
    if not passed:
        print(f"  Expected {field_name}: {expected}")
        print(f"  Actual {field_name}: {actual}")
    return passed


# ============================================================================
# TEST 1: Date Detection - Standard 3rd Friday of Month
# ============================================================================
def test_third_friday_detection():
    """Test that 3rd Friday of month is correctly identified."""
    print_test_header("3rd Friday Detection")
    
    # November 2025: 3rd Friday is November 21
    # Calculate it: First day is Saturday (day 0), so first Friday is day 7
    # 2nd Friday = day 14, 3rd Friday = day 21
    test_date = "2025-11-21"
    
    # Test CSP on 3rd Friday
    result = check_expiration_risk(test_date, "CSP", open_interest=1000, bid_ask_spread_pct=2.0)
    
    tests_passed = []
    tests_passed.append(assert_equal(result["is_standard"], True, "is_standard"))
    tests_passed.append(assert_equal(result["expiration_type"], "Monthly (3rd Friday)", "expiration_type"))
    tests_passed.append(assert_equal(result["day_of_week"], "Friday", "day_of_week"))
    tests_passed.append(assert_equal(result["risk_level"], "LOW", "risk_level"))
    tests_passed.append(assert_equal(result["action"], "ALLOW", "action"))
    
    print_result(all(tests_passed), "3rd Friday correctly identified as Monthly standard with LOW risk")
    return all(tests_passed)


# ============================================================================
# TEST 2: Date Detection - Weekly Friday (not 3rd)
# ============================================================================
def test_weekly_friday_detection():
    """Test that non-3rd Friday is correctly identified as weekly."""
    print_test_header("Weekly Friday Detection")
    
    # November 2025: 1st Friday is November 7 (not 3rd Friday)
    test_date = "2025-11-07"
    
    result = check_expiration_risk(test_date, "CSP", open_interest=500, bid_ask_spread_pct=3.0)
    
    tests_passed = []
    tests_passed.append(assert_equal(result["is_standard"], True, "is_standard"))
    tests_passed.append(assert_equal(result["expiration_type"], "Weekly (Friday)", "expiration_type"))
    tests_passed.append(assert_equal(result["day_of_week"], "Friday", "day_of_week"))
    tests_passed.append(assert_equal(result["risk_level"], "MEDIUM", "risk_level"))
    tests_passed.append(assert_equal(result["action"], "WARN", "action"))
    
    print_result(all(tests_passed), "Weekly Friday correctly identified with MEDIUM risk")
    return all(tests_passed)


# ============================================================================
# TEST 3: Date Detection - Non-Standard Days (Mon-Thu)
# ============================================================================
def test_nonstandard_day_detection():
    """Test that Monday-Thursday expirations are flagged as non-standard."""
    print_test_header("Non-Standard Day Detection")
    
    test_cases = [
        ("2025-11-03", "Monday"),    # Monday
        ("2025-11-04", "Tuesday"),   # Tuesday
        ("2025-11-05", "Wednesday"), # Wednesday
        ("2025-11-06", "Thursday"),  # Thursday
    ]
    
    all_passed = True
    for test_date, expected_day in test_cases:
        result = check_expiration_risk(test_date, "CSP", open_interest=200, bid_ask_spread_pct=4.0)
        
        tests_passed = []
        tests_passed.append(assert_equal(result["is_standard"], False, f"{expected_day} is_standard"))
        tests_passed.append(assert_equal(result["day_of_week"], expected_day, f"{expected_day} day_of_week"))
        tests_passed.append("Non-Standard" in result["expiration_type"])
        tests_passed.append(result["risk_level"] in ["HIGH", "EXTREME"])
        
        if all(tests_passed):
            print_result(True, f"{expected_day} correctly flagged as non-standard")
        else:
            print_result(False, f"{expected_day} detection failed")
            all_passed = False
    
    return all_passed


# ============================================================================
# TEST 4: Strategy-Specific Risk Levels
# ============================================================================
def test_strategy_risk_levels():
    """Test that different strategies get appropriate risk levels."""
    print_test_header("Strategy-Specific Risk Levels")
    
    # Test on 3rd Friday (should be safest)
    test_date = "2025-11-21"  # 3rd Friday
    
    expected_risks = {
        "CSP": "LOW",
        "CC": "MEDIUM",
        "Collar": "MEDIUM",
        "Bull Put Spread": "MEDIUM",
        "Bear Call Spread": "MEDIUM",
        "Iron Condor": "MEDIUM"
    }
    
    all_passed = True
    for strategy, expected_risk in expected_risks.items():
        result = check_expiration_risk(test_date, strategy, open_interest=1000, bid_ask_spread_pct=2.0)
        
        if result["risk_level"] == expected_risk:
            print_result(True, f"{strategy} on 3rd Friday = {expected_risk}")
        else:
            print_result(False, f"{strategy} expected {expected_risk}, got {result['risk_level']}")
            all_passed = False
    
    return all_passed


# ============================================================================
# TEST 5: Multi-Leg Strategy on Non-Standard = EXTREME
# ============================================================================
def test_multileg_nonstandard_extreme():
    """Test that multi-leg strategies on non-standard dates are EXTREME risk."""
    print_test_header("Multi-Leg Non-Standard = EXTREME Risk")
    
    test_date = "2025-11-03"  # Monday
    multileg_strategies = ["Bull Put Spread", "Bear Call Spread", "Iron Condor"]
    
    all_passed = True
    for strategy in multileg_strategies:
        result = check_expiration_risk(test_date, strategy, open_interest=200, bid_ask_spread_pct=5.0)
        
        if result["risk_level"] == "EXTREME" and result["action"] == "BLOCK":
            print_result(True, f"{strategy} on Monday = EXTREME + BLOCK")
        else:
            print_result(False, f"{strategy} should be EXTREME + BLOCK, got {result['risk_level']} + {result['action']}")
            all_passed = False
    
    return all_passed


# ============================================================================
# TEST 6: Liquidity-Based Risk Escalation (Low OI)
# ============================================================================
def test_low_oi_escalation():
    """Test that low OI escalates risk level."""
    print_test_header("Low OI Risk Escalation")
    
    test_date = "2025-11-21"  # 3rd Friday (normally LOW for CSP)
    
    # Test with very low OI
    result_low_oi = check_expiration_risk(test_date, "CSP", open_interest=50, bid_ask_spread_pct=2.0)
    
    # Low OI should escalate from LOW to MEDIUM
    if result_low_oi["risk_level"] in ["MEDIUM", "HIGH"]:
        print_result(True, f"Low OI (50) escalated risk from LOW to {result_low_oi['risk_level']}")
        passed = True
    else:
        print_result(False, f"Low OI should escalate risk, got {result_low_oi['risk_level']}")
        passed = False
    
    # Check risk factors mention low OI
    if any("low" in factor.lower() and "oi" in factor.lower() for factor in result_low_oi["risk_factors"]):
        print_result(True, "Risk factors mention low OI")
    else:
        print_result(False, "Risk factors should mention low OI")
        passed = False
    
    return passed


# ============================================================================
# TEST 7: Wide Spread Risk Escalation
# ============================================================================
def test_wide_spread_escalation():
    """Test that wide bid-ask spread escalates risk level."""
    print_test_header("Wide Spread Risk Escalation")
    
    test_date = "2025-11-21"  # 3rd Friday
    
    # Test with extremely wide spread
    result_wide = check_expiration_risk(test_date, "CSP", open_interest=1000, bid_ask_spread_pct=15.0)
    
    # Wide spread should escalate risk
    if result_wide["risk_level"] in ["MEDIUM", "HIGH"]:
        print_result(True, f"Wide spread (15%) escalated risk to {result_wide['risk_level']}")
        passed = True
    else:
        print_result(False, f"Wide spread should escalate risk, got {result_wide['risk_level']}")
        passed = False
    
    # Check risk factors mention spread
    if any("spread" in factor.lower() for factor in result_wide["risk_factors"]):
        print_result(True, "Risk factors mention wide spread")
    else:
        print_result(False, "Risk factors should mention spread")
        passed = False
    
    return passed


# ============================================================================
# TEST 8: Action Determination Logic
# ============================================================================
def test_action_determination():
    """Test that actions (ALLOW/WARN/BLOCK) are correctly assigned."""
    print_test_header("Action Determination")
    
    test_cases = [
        # (date, strategy, oi, spread, expected_action)
        ("2025-11-21", "CSP", 1000, 2.0, "ALLOW"),           # 3rd Friday, good liquidity
        ("2025-11-07", "CSP", 500, 3.0, "WARN"),             # Weekly Friday
        ("2025-11-03", "CSP", 200, 4.0, "WARN"),             # Monday but single-leg
        ("2025-11-03", "Iron Condor", 200, 4.0, "BLOCK"),    # Monday + multi-leg
        ("2025-11-03", "Bull Put Spread", 50, 8.0, "BLOCK"), # Monday + low OI + spread
    ]
    
    all_passed = True
    for test_date, strategy, oi, spread, expected_action in test_cases:
        result = check_expiration_risk(test_date, strategy, oi, spread)
        
        if result["action"] == expected_action:
            print_result(True, f"{strategy} on {test_date} (OI={oi}) → {expected_action}")
        else:
            print_result(False, f"{strategy} expected {expected_action}, got {result['action']}")
            all_passed = False
    
    return all_passed


# ============================================================================
# TEST 9: Edge Cases
# ============================================================================
def test_edge_cases():
    """Test edge cases and boundary conditions."""
    print_test_header("Edge Cases")
    
    all_passed = True
    
    # Test 1: Invalid date format
    result = check_expiration_risk("invalid-date", "CSP", 1000, 2.0)
    if result["risk_level"] == "EXTREME" and result["action"] == "BLOCK":
        print_result(True, "Invalid date format returns EXTREME + BLOCK")
    else:
        print_result(False, "Invalid date should return EXTREME + BLOCK")
        all_passed = False
    
    # Test 2: Zero OI
    result = check_expiration_risk("2025-11-21", "CSP", 0, 2.0)
    # Should still process but may have warnings
    if result["risk_level"] in ["LOW", "MEDIUM"]:  # Some risk but not extreme
        print_result(True, "Zero OI handled gracefully")
    else:
        print_result(False, f"Zero OI unexpected risk: {result['risk_level']}")
        all_passed = False
    
    # Test 3: Zero spread
    result = check_expiration_risk("2025-11-21", "CSP", 1000, 0.0)
    if result["risk_level"] == "LOW":
        print_result(True, "Zero spread handled gracefully")
    else:
        print_result(False, "Zero spread should not escalate risk")
        all_passed = False
    
    # Test 4: Extreme OI (very high)
    result = check_expiration_risk("2025-11-21", "CSP", 50000, 0.5)
    if result["risk_level"] == "LOW" and result["action"] == "ALLOW":
        print_result(True, "Very high OI keeps LOW risk")
    else:
        print_result(False, "Very high OI should be LOW risk")
        all_passed = False
    
    return all_passed


# ============================================================================
# TEST 10: Risk Factor Reporting
# ============================================================================
def test_risk_factor_reporting():
    """Test that appropriate risk factors are reported."""
    print_test_header("Risk Factor Reporting")
    
    # Test non-standard day
    result = check_expiration_risk("2025-11-03", "CSP", 100, 5.0)
    
    expected_factors = [
        ("Monday", lambda f: "Monday" in f),
        ("Low OI", lambda f: "oi" in f.lower() and "100" in f),
        ("Spread", lambda f: "spread" in f.lower() and "5" in f),
    ]
    
    all_passed = True
    for factor_name, check_func in expected_factors:
        if any(check_func(f) for f in result["risk_factors"]):
            print_result(True, f"Risk factors include: {factor_name}")
        else:
            print_result(False, f"Risk factors should include: {factor_name}")
            print(f"  Actual factors: {result['risk_factors']}")
            all_passed = False
    
    return all_passed


# ============================================================================
# TEST 11: Warning Message Clarity
# ============================================================================
def test_warning_messages():
    """Test that warning messages are clear and actionable."""
    print_test_header("Warning Message Clarity")
    
    test_cases = [
        ("2025-11-21", "CSP", 1000, 2.0, "✅"),  # Should have checkmark
        ("2025-11-07", "CSP", 500, 3.0, "⚠️"),  # Should have warning
        ("2025-11-03", "Iron Condor", 100, 5.0, "⛔"), # Should have block
    ]
    
    all_passed = True
    for test_date, strategy, oi, spread, expected_icon in test_cases:
        result = check_expiration_risk(test_date, strategy, oi, spread)
        message = result["warning_message"]
        
        if expected_icon in message:
            print_result(True, f"Message includes {expected_icon}: {message}")
        else:
            print_result(False, f"Message should include {expected_icon}: {message}")
            all_passed = False
    
    return all_passed


# ============================================================================
# TEST 12: Consistency Across Strategies
# ============================================================================
def test_strategy_consistency():
    """Test that similar strategies have consistent risk assessments."""
    print_test_header("Strategy Consistency")
    
    # Bull Put and Bear Call should have same risk level (both 2-leg spreads)
    test_date = "2025-11-03"  # Monday
    
    bull_put = check_expiration_risk(test_date, "Bull Put Spread", 200, 4.0)
    bear_call = check_expiration_risk(test_date, "Bear Call Spread", 200, 4.0)
    
    if bull_put["risk_level"] == bear_call["risk_level"]:
        print_result(True, f"Bull Put and Bear Call have same risk: {bull_put['risk_level']}")
        passed = True
    else:
        print_result(False, f"Bull Put={bull_put['risk_level']}, Bear Call={bear_call['risk_level']}")
        passed = False
    
    if bull_put["action"] == bear_call["action"]:
        print_result(True, f"Both have same action: {bull_put['action']}")
    else:
        print_result(False, f"Actions differ: {bull_put['action']} vs {bear_call['action']}")
        passed = False
    
    return passed


# ============================================================================
# TEST 13: Real-World Scenario Testing
# ============================================================================
def test_real_world_scenarios():
    """Test realistic trading scenarios."""
    print_test_header("Real-World Scenarios")
    
    scenarios = [
        {
            "name": "SPY 3rd Friday CSP (ideal)",
            "date": "2025-12-19",  # 3rd Friday
            "strategy": "CSP",
            "oi": 10000,
            "spread": 1.0,
            "expected_action": "ALLOW",
            "expected_risk": "LOW"
        },
        {
            "name": "AAPL Weekly CC (acceptable)",
            "date": "2025-11-07",  # Weekly Friday
            "strategy": "CC",
            "oi": 2000,
            "spread": 2.5,
            "expected_action": "WARN",
            "expected_risk": "HIGH"
        },
        {
            "name": "QQQ Monday Iron Condor (dangerous)",
            "date": "2025-11-03",  # Monday
            "strategy": "Iron Condor",
            "oi": 500,
            "spread": 4.0,
            "expected_action": "BLOCK",
            "expected_risk": "EXTREME"
        },
        {
            "name": "Small-cap Wednesday CSP (poor liquidity)",
            "date": "2025-11-05",  # Wednesday
            "strategy": "CSP",
            "oi": 50,
            "spread": 8.0,
            "expected_action": "WARN",
            "expected_risk": "HIGH"
        },
    ]
    
    all_passed = True
    for scenario in scenarios:
        result = check_expiration_risk(
            scenario["date"],
            scenario["strategy"],
            scenario["oi"],
            scenario["spread"]
        )
        
        action_match = result["action"] == scenario["expected_action"]
        risk_match = result["risk_level"] == scenario["expected_risk"]
        
        if action_match and risk_match:
            print_result(True, f"{scenario['name']}: {result['action']}/{result['risk_level']}")
        else:
            print_result(False, f"{scenario['name']} failed")
            print(f"  Expected: {scenario['expected_action']}/{scenario['expected_risk']}")
            print(f"  Got: {result['action']}/{result['risk_level']}")
            all_passed = False
    
    return all_passed


# ============================================================================
# MAIN TEST RUNNER
# ============================================================================
def run_all_tests():
    """Run all test suites and report results."""
    print("\n" + "=" * 80)
    print("EXPIRATION SAFETY TEST SUITE")
    print("=" * 80)
    print(f"Test Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    
    tests = [
        ("3rd Friday Detection", test_third_friday_detection),
        ("Weekly Friday Detection", test_weekly_friday_detection),
        ("Non-Standard Day Detection", test_nonstandard_day_detection),
        ("Strategy-Specific Risk Levels", test_strategy_risk_levels),
        ("Multi-Leg Non-Standard = EXTREME", test_multileg_nonstandard_extreme),
        ("Low OI Risk Escalation", test_low_oi_escalation),
        ("Wide Spread Risk Escalation", test_wide_spread_escalation),
        ("Action Determination", test_action_determination),
        ("Edge Cases", test_edge_cases),
        ("Risk Factor Reporting", test_risk_factor_reporting),
        ("Warning Message Clarity", test_warning_messages),
        ("Strategy Consistency", test_strategy_consistency),
        ("Real-World Scenarios", test_real_world_scenarios),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            passed = test_func()
            results.append((test_name, passed, None))
        except Exception as e:
            print(f"\n❌ EXCEPTION in {test_name}: {e}")
            import traceback
            traceback.print_exc()
            results.append((test_name, False, str(e)))
    
    # Summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    
    passed_count = sum(1 for _, passed, _ in results if passed)
    total_count = len(results)
    
    for test_name, passed, error in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {test_name}")
        if error:
            print(f"    Error: {error}")
    
    print("=" * 80)
    print(f"TOTAL: {passed_count}/{total_count} tests passed ({passed_count/total_count*100:.1f}%)")
    print("=" * 80)
    
    if passed_count == total_count:
        print("\n🎉 ALL TESTS PASSED! Expiration safety mechanisms are working correctly.")
        return 0
    else:
        print(f"\n⚠️  {total_count - passed_count} TEST(S) FAILED. Review implementation.")
        return 1


if __name__ == "__main__":
    exit_code = run_all_tests()
    sys.exit(exit_code)
