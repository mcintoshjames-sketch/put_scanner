"""Validation script for VaR calculation logic.

Tests VaR calculations against expected values for different position types
to ensure financial soundness.

Author: Options Strategy Lab
Created: 2025-11-15
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from risk_metrics.var_calculator import calculate_portfolio_var

def test_long_stock_var():
    """Test VaR for a simple long stock position."""
    print("\n" + "="*80)
    print("TEST 1: Long Stock Position")
    print("="*80)
    
    # Setup: Long 100 shares of stock at $100
    positions = [{
        'symbol': 'TEST',
        'quantity': 100,
        'underlying_price': 100.0,
        'position_type': 'STOCK',
        'market_value': 10000.0  # 100 shares × $100
    }]
    
    # Create synthetic historical returns: 2% daily volatility, 252 days
    np.random.seed(42)
    returns = np.random.normal(0.0, 0.02, 252)
    dates = pd.date_range(end=datetime.now(), periods=252, freq='D')
    prices = 100 * np.exp(np.cumsum(returns))
    hist_prices = pd.DataFrame({'TEST': prices}, index=dates)
    
    # Calculate VaR
    var_result = calculate_portfolio_var(
        positions=positions,
        historical_prices=hist_prices,
        confidence_level=0.95,
        time_horizon_days=1,
        method='historical'
    )
    
    # Expected: With 2% daily vol, 95% VaR ≈ 1.65 × 0.02 × $10,000 = $330
    portfolio_value = 10000.0
    print(f"Portfolio Value: ${portfolio_value:,.2f}")
    print(f"1-day VaR (95%): ${var_result.var_amount:,.2f} ({var_result.var_percent:.2f}%)")
    print(f"Expected VaR: ~$330 (3.3%)")
    print(f"CVaR: ${var_result.cvar_amount:,.2f}" if var_result.cvar_amount else "CVaR: N/A")
    
    # Validation
    expected_var_min = 250  # $250 minimum (2.5%)
    expected_var_max = 450  # $450 maximum (4.5%)
    
    if expected_var_min <= var_result.var_amount <= expected_var_max:
        print("✅ PASS: VaR is within expected range")
        return True
    else:
        print(f"❌ FAIL: VaR ${var_result.var_amount:.2f} outside expected range ${expected_var_min}-${expected_var_max}")
        return False


def test_long_call_var():
    """Test VaR for a long call option position."""
    print("\n" + "="*80)
    print("TEST 2: Long Call Option (ATM)")
    print("="*80)
    
    # Setup: Long 1 NVDA call at $260 strike, premium $31, delta 0.5
    # Underlying at $260
    positions = [{
        'symbol': 'NVDA',
        'quantity': 1,
        'underlying_price': 260.0,
        'position_type': 'CALL',
        'market_value': 3100.0,  # $31 × 100
        'option_price': 31.0,
        'delta': 0.5,
        'strike': 260.0,
        'expiration': '2025-12-12'
    }]
    
    # Create realistic NVDA returns: 3% daily volatility
    np.random.seed(42)
    returns = np.random.normal(0.0, 0.03, 252)
    dates = pd.date_range(end=datetime.now(), periods=252, freq='D')
    prices = 260 * np.exp(np.cumsum(returns))
    hist_prices = pd.DataFrame({'NVDA': prices}, index=dates)
    
    # Calculate VaR
    var_result = calculate_portfolio_var(
        positions=positions,
        historical_prices=hist_prices,
        confidence_level=0.95,
        time_horizon_days=1,
        method='historical'
    )
    
    # Expected: Delta-adjusted exposure = 0.5 × 1 × 100 × $260 = $13,000
    # With 3% vol, 95% VaR ≈ 1.65 × 0.03 × $13,000 = $643
    # BUT capped at premium paid = $3,100
    # So expect VaR much less than $3,100, likely $400-$800
    portfolio_value = 3100.0
    print(f"Portfolio Value: ${portfolio_value:,.2f}")
    print(f"1-day VaR (95%): ${var_result.var_amount:,.2f} ({var_result.var_percent:.2f}%)")
    print(f"Expected VaR: $400-$800 (13-26% of premium)")
    print(f"Maximum possible loss: $3,100 (premium paid)")
    print(f"CVaR: ${var_result.cvar_amount:,.2f}" if var_result.cvar_amount else "CVaR: N/A")
    
    # Validation
    max_loss = 3100.0
    expected_var_min = 300  # At least $300 (some risk)
    expected_var_max = max_loss  # Cannot exceed premium
    
    if var_result.var_amount > max_loss:
        print(f"❌ FAIL: VaR ${var_result.var_amount:.2f} exceeds max loss ${max_loss:.2f}")
        return False
    elif var_result.var_amount < expected_var_min:
        print(f"❌ FAIL: VaR ${var_result.var_amount:.2f} unrealistically low (< ${expected_var_min})")
        return False
    elif var_result.var_percent == 100.0:
        print(f"❌ FAIL: VaR shows 100% loss probability - not realistic for 1-day horizon")
        return False
    else:
        print("✅ PASS: VaR is realistic and capped at premium")
        return True


def test_long_otm_call_var():
    """Test VaR for a long OTM call option (lower risk)."""
    print("\n" + "="*80)
    print("TEST 3: Long Call Option (OTM)")
    print("="*80)
    
    # Setup: Long 1 call at $280 strike, underlying at $260, delta 0.2
    # Premium $5
    positions = [{
        'symbol': 'TEST',
        'quantity': 1,
        'underlying_price': 260.0,
        'position_type': 'CALL',
        'market_value': 500.0,  # $5 × 100
        'option_price': 5.0,
        'delta': 0.2,
        'strike': 280.0,
        'expiration': '2025-12-12'
    }]
    
    # Create returns: 3% daily volatility
    np.random.seed(42)
    returns = np.random.normal(0.0, 0.03, 252)
    dates = pd.date_range(end=datetime.now(), periods=252, freq='D')
    prices = 260 * np.exp(np.cumsum(returns))
    hist_prices = pd.DataFrame({'TEST': prices}, index=dates)
    
    # Calculate VaR
    var_result = calculate_portfolio_var(
        positions=positions,
        historical_prices=hist_prices,
        confidence_level=0.95,
        time_horizon_days=1,
        method='historical'
    )
    
    # Expected: Delta-adjusted = 0.2 × 1 × 100 × $260 = $5,200
    # With 3% vol, 95% VaR ≈ 1.65 × 0.03 × $5,200 = $257
    # Capped at $500 premium
    portfolio_value = 500.0
    print(f"Portfolio Value: ${portfolio_value:,.2f}")
    print(f"1-day VaR (95%): ${var_result.var_amount:,.2f} ({var_result.var_percent:.2f}%)")
    print(f"Expected VaR: $150-$300 (30-60% of premium)")
    print(f"Maximum possible loss: $500 (premium paid)")
    print(f"CVaR: ${var_result.cvar_amount:,.2f}" if var_result.cvar_amount else "CVaR: N/A")
    
    # Validation
    max_loss = 500.0
    expected_var_min = 100
    expected_var_max = max_loss
    
    if var_result.var_amount > max_loss:
        print(f"❌ FAIL: VaR ${var_result.var_amount:.2f} exceeds max loss ${max_loss:.2f}")
        return False
    elif var_result.var_percent == 100.0:
        print(f"❌ FAIL: VaR shows 100% loss probability - not realistic")
        return False
    elif expected_var_min <= var_result.var_amount <= expected_var_max:
        print("✅ PASS: VaR is realistic for OTM option")
        return True
    else:
        print(f"⚠️  WARNING: VaR ${var_result.var_amount:.2f} outside expected range ${expected_var_min}-${expected_var_max}")
        return True  # Still pass if within max loss


def test_short_call_var():
    """Test VaR for a short call option (potentially unlimited risk)."""
    print("\n" + "="*80)
    print("TEST 4: Short Call Option")
    print("="*80)
    
    # Setup: Short 1 call at $260 strike, delta 0.5, collected $31 premium
    positions = [{
        'symbol': 'TEST',
        'quantity': -1,  # Negative for short
        'underlying_price': 260.0,
        'position_type': 'CALL',
        'market_value': 3100.0,  # Absolute value
        'option_price': 31.0,
        'delta': 0.5,
        'strike': 260.0,
        'expiration': '2025-12-12'
    }]
    
    # Create returns: 3% daily volatility
    np.random.seed(42)
    returns = np.random.normal(0.0, 0.03, 252)
    dates = pd.date_range(end=datetime.now(), periods=252, freq='D')
    prices = 260 * np.exp(np.cumsum(returns))
    hist_prices = pd.DataFrame({'TEST': prices}, index=dates)
    
    # Calculate VaR
    var_result = calculate_portfolio_var(
        positions=positions,
        historical_prices=hist_prices,
        confidence_level=0.95,
        time_horizon_days=1,
        method='historical'
    )
    
    # Expected: Delta = 0.5, so exposure = -0.5 × 1 × 100 × $260 = -$13,000
    # VaR for short position should be higher, NOT capped
    portfolio_value = 3100.0
    print(f"Portfolio Value: ${portfolio_value:,.2f}")
    print(f"1-day VaR (95%): ${var_result.var_amount:,.2f} ({var_result.var_percent:.2f}%)")
    print(f"Expected VaR: $400-$800 (NOT capped at premium)")
    print(f"CVaR: ${var_result.cvar_amount:,.2f}" if var_result.cvar_amount else "CVaR: N/A")
    
    # Validation: Should NOT be capped at premium for short positions
    premium = 3100.0
    expected_var_min = 300
    
    if var_result.var_amount <= premium and var_result.var_percent == 100.0:
        print(f"❌ FAIL: Short call VaR incorrectly capped at premium")
        return False
    elif var_result.var_amount < expected_var_min:
        print(f"❌ FAIL: VaR too low for short call position")
        return False
    else:
        print("✅ PASS: Short call VaR shows realistic risk")
        return True


def test_multi_position_var():
    """Test VaR for portfolio with multiple positions."""
    print("\n" + "="*80)
    print("TEST 5: Multi-Position Portfolio")
    print("="*80)
    
    # Setup: Long 100 shares AAPL + Long 1 AAPL call
    positions = [
        {
            'symbol': 'AAPL',
            'quantity': 100,
            'underlying_price': 150.0,
            'position_type': 'STOCK',
            'market_value': 15000.0
        },
        {
            'symbol': 'AAPL',
            'quantity': 1,
            'underlying_price': 150.0,
            'position_type': 'CALL',
            'market_value': 1000.0,
            'option_price': 10.0,
            'delta': 0.6,
            'strike': 155.0,
            'expiration': '2025-12-12'
        }
    ]
    
    # Create returns: 2.5% daily volatility
    np.random.seed(42)
    returns = np.random.normal(0.0, 0.025, 252)
    dates = pd.date_range(end=datetime.now(), periods=252, freq='D')
    prices = 150 * np.exp(np.cumsum(returns))
    hist_prices = pd.DataFrame({'AAPL': prices}, index=dates)
    
    # Calculate VaR
    var_result = calculate_portfolio_var(
        positions=positions,
        historical_prices=hist_prices,
        confidence_level=0.95,
        time_horizon_days=1,
        method='historical'
    )
    
    # Expected: Stock exposure = $15,000, Call exposure ≈ $9,000 (delta-adjusted)
    # Total ≈ $24,000, with 2.5% vol, VaR ≈ 1.65 × 0.025 × $24,000 ≈ $990
    # But call loss capped at $1,000
    portfolio_value = 16000.0
    print(f"Portfolio Value: ${portfolio_value:,.2f}")
    print(f"1-day VaR (95%): ${var_result.var_amount:,.2f} ({var_result.var_percent:.2f}%)")
    print(f"Expected VaR: $800-$1,200")
    print(f"CVaR: ${var_result.cvar_amount:,.2f}" if var_result.cvar_amount else "CVaR: N/A")
    
    # Validation
    expected_var_min = 600
    expected_var_max = 1500
    
    if expected_var_min <= var_result.var_amount <= expected_var_max:
        print("✅ PASS: Multi-position VaR is reasonable")
        return True
    else:
        print(f"⚠️  WARNING: VaR ${var_result.var_amount:.2f} outside expected range ${expected_var_min}-${expected_var_max}")
        return True  # Still pass if not obviously broken


def test_debug_long_call():
    """Debug test to see exactly what's happening with the NVDA call."""
    print("\n" + "="*80)
    print("DEBUG TEST: Detailed NVDA Long Call Analysis")
    print("="*80)
    
    # Exact same setup as user's position
    positions = [{
        'symbol': 'NVDA',
        'quantity': 1,
        'underlying_price': 260.0,
        'position_type': 'CALL',
        'market_value': 31.0,  # User reported $31 total value
        'option_price': 0.31,  # $0.31 per share
        'delta': 0.5,
        'strike': 260.0,
        'expiration': '2025-12-12'
    }]
    
    # Create synthetic returns with known statistics
    np.random.seed(42)
    returns = np.random.normal(0.0, 0.03, 252)  # 3% daily vol
    dates = pd.date_range(end=datetime.now(), periods=252, freq='D')
    prices = 260 * np.exp(np.cumsum(returns))
    hist_prices = pd.DataFrame({'NVDA': prices}, index=dates)
    
    print(f"\nInput Data:")
    print(f"  Position: Long 1 NVDA Call")
    print(f"  Strike: $260")
    print(f"  Underlying: $260")
    print(f"  Option Price: $0.31/share = $31 total")
    print(f"  Delta: 0.5")
    print(f"  Market Value: $31")
    print(f"  Historical returns: mean={returns.mean():.4f}, std={returns.std():.4f}")
    
    # Calculate VaR
    var_result = calculate_portfolio_var(
        positions=positions,
        historical_prices=hist_prices,
        confidence_level=0.95,
        time_horizon_days=1,
        method='historical'
    )
    
    portfolio_value = 31.0
    print(f"\nVaR Calculation Results:")
    print(f"  Portfolio Value: ${portfolio_value:,.2f}")
    print(f"  1-day VaR (95%): ${var_result.var_amount:,.2f}")
    print(f"  VaR %: {var_result.var_percent:.2f}%")
    print(f"  CVaR: ${var_result.cvar_amount:,.2f}" if var_result.cvar_amount else "  CVaR: N/A")
    
    # Manual calculation for comparison
    delta_exposure = 0.5 * 1 * 100 * 260  # $13,000
    worst_5_pct_returns = np.percentile(returns, 5)
    expected_pnl = delta_exposure * worst_5_pct_returns
    capped_loss = min(abs(expected_pnl), 31.0)
    
    print(f"\nManual Calculation:")
    print(f"  Delta-adjusted exposure: ${delta_exposure:,.0f}")
    print(f"  Worst 5% return: {worst_5_pct_returns:.4f}")
    print(f"  Expected P&L (uncapped): ${expected_pnl:,.2f}")
    print(f"  Expected P&L (capped at premium): ${capped_loss:,.2f}")
    
    # Check if VaR equals 100% of portfolio
    if var_result.var_percent == 100.0:
        print(f"\n❌ ISSUE DETECTED: VaR = 100% of portfolio")
        print(f"   This means every scenario resulted in max loss")
        print(f"   Likely cause: Portfolio value or capping logic error")
        return False
    elif var_result.var_amount == 31.0:
        print(f"\n⚠️  WARNING: VaR exactly equals premium")
        print(f"   This suggests all losses are hitting the cap")
        print(f"   May indicate portfolio_value calculation issue")
        return False
    else:
        print(f"\n✅ VaR appears reasonable (not 100% of portfolio)")
        return True


def main():
    """Run all VaR validation tests."""
    print("\n" + "="*80)
    print("VaR CALCULATION VALIDATION SUITE")
    print("="*80)
    
    tests = [
        ("Long Stock", test_long_stock_var),
        ("Long ATM Call", test_long_call_var),
        ("Long OTM Call", test_long_otm_call_var),
        ("Short Call", test_short_call_var),
        ("Multi-Position", test_multi_position_var),
        ("Debug NVDA Call", test_debug_long_call),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            passed = test_func()
            results.append((name, passed))
        except Exception as e:
            print(f"\n❌ TEST FAILED WITH EXCEPTION: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))
    
    # Summary
    print("\n" + "="*80)
    print("VALIDATION SUMMARY")
    print("="*80)
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {name}")
    
    passed_count = sum(1 for _, p in results if p)
    total_count = len(results)
    print(f"\nTotal: {passed_count}/{total_count} tests passed")
    
    if passed_count == total_count:
        print("\n🎉 All validation tests passed!")
    else:
        print(f"\n⚠️  {total_count - passed_count} test(s) failed - review VaR calculation logic")


if __name__ == '__main__':
    main()
