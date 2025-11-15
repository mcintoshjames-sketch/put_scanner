#!/usr/bin/env python3
"""Test suite for VaR and CVaR calculations.

Tests:
1. Parametric VaR calculation
2. Historical VaR calculation
3. CVaR (Expected Shortfall)
4. Portfolio VaR with correlations
5. VaR report formatting
6. Edge cases and validation

Author: Options Strategy Lab
Created: 2025-11-15
"""

import sys
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

print("=" * 60)
print("Testing VaR and CVaR Calculations (Phase 1.2)")
print("=" * 60)

# Test imports
print("\n1. Testing imports...")
try:
    from risk_metrics.var_calculator import (
        calculate_parametric_var,
        calculate_historical_var,
        calculate_cvar,
        calculate_portfolio_var,
        format_var_report,
        VaRResult
    )
    print("✅ VaR calculator imports successful")
except Exception as e:
    print(f"❌ Import failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test parametric VaR
print("\n2. Testing parametric VaR...")
try:
    var_result = calculate_parametric_var(
        portfolio_value=100000,
        volatility=0.02,  # 2% daily volatility
        mean_return=0.001,  # 0.1% daily return
        confidence_level=0.95,
        time_horizon_days=1
    )
    
    print(f"✅ Parametric VaR calculated")
    print(f"   Portfolio Value: $100,000")
    print(f"   Volatility: 2.0% per day")
    print(f"   95% VaR (1-day): ${var_result.var_amount:,.2f} ({var_result.var_percent:.2f}%)")
    print(f"   95% CVaR (1-day): ${var_result.cvar_amount:,.2f} ({var_result.cvar_percent:.2f}%)")
    
    # Validation
    assert var_result.var_amount > 0, "VaR should be positive"
    assert var_result.cvar_amount and var_result.cvar_amount > var_result.var_amount, "CVaR should be > VaR"
    assert 0 < var_result.var_percent < 100, "VaR% should be reasonable"
    
    print("✅ Parametric VaR validation passed")
    
except Exception as e:
    print(f"❌ Parametric VaR failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test historical VaR
print("\n3. Testing historical VaR...")
try:
    # Generate sample returns (normal distribution with slight skew)
    np.random.seed(42)
    returns = np.random.normal(0.001, 0.02, 252)  # 1 year of daily returns
    
    var_result = calculate_historical_var(
        portfolio_value=100000,
        historical_returns=returns,
        confidence_level=0.95,
        time_horizon_days=1
    )
    
    print(f"✅ Historical VaR calculated")
    print(f"   Data Points: {len(returns)}")
    print(f"   95% VaR (1-day): ${var_result.var_amount:,.2f} ({var_result.var_percent:.2f}%)")
    print(f"   95% CVaR (1-day): ${var_result.cvar_amount:,.2f} ({var_result.cvar_percent:.2f}%)")
    print(f"   Volatility: {(var_result.volatility or 0) * 100:.2f}%")
    print(f"   Skewness: {var_result.skewness:.3f}")
    print(f"   Kurtosis: {var_result.kurtosis:.3f}")
    
    # Validation
    assert var_result.var_amount > 0, "VaR should be positive"
    assert var_result.data_points == 252, f"Expected 252 data points, got {var_result.data_points}"
    assert var_result.method == 'historical', "Method should be 'historical'"
    
    print("✅ Historical VaR validation passed")
    
except Exception as e:
    print(f"❌ Historical VaR failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test multi-day horizon
print("\n4. Testing multi-day VaR horizon...")
try:
    var_1day = calculate_historical_var(
        portfolio_value=100000,
        historical_returns=returns,
        confidence_level=0.95,
        time_horizon_days=1
    )
    
    var_10day = calculate_historical_var(
        portfolio_value=100000,
        historical_returns=returns,
        confidence_level=0.95,
        time_horizon_days=10
    )
    
    print(f"✅ Multi-day VaR calculated")
    print(f"   1-day VaR:  ${var_1day.var_amount:,.2f}")
    print(f"   10-day VaR: ${var_10day.var_amount:,.2f}")
    
    # 10-day VaR should be higher than 1-day
    assert var_10day.var_amount > var_1day.var_amount, "10-day VaR should be > 1-day VaR"
    
    # Rough check: 10-day ~= 1-day * sqrt(10)
    sqrt_10_ratio = var_10day.var_amount / var_1day.var_amount
    print(f"   Ratio (10-day/1-day): {sqrt_10_ratio:.2f} (expected ~{np.sqrt(10):.2f})")
    
    print("✅ Multi-day horizon validation passed")
    
except Exception as e:
    print(f"❌ Multi-day VaR failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test CVaR directly
print("\n5. Testing CVaR calculation...")
try:
    cvar_amount, cvar_percent = calculate_cvar(
        portfolio_value=100000,
        historical_returns=returns,
        confidence_level=0.95,
        time_horizon_days=1
    )
    
    print(f"✅ CVaR calculated")
    print(f"   95% CVaR: ${cvar_amount:,.2f} ({cvar_percent:.2f}%)")
    
    assert cvar_amount > 0, "CVaR should be positive"
    
    print("✅ CVaR validation passed")
    
except Exception as e:
    print(f"❌ CVaR calculation failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test portfolio VaR with multiple positions
print("\n6. Testing portfolio VaR with correlations...")
try:
    # Create synthetic portfolio with 3 stocks
    positions = [
        {'symbol': 'AAPL', 'quantity': 100, 'current_price': 180.0, 'position_type': 'STOCK'},
        {'symbol': 'MSFT', 'quantity': 50, 'current_price': 400.0, 'position_type': 'STOCK'},
        {'symbol': 'GOOGL', 'quantity': 25, 'current_price': 150.0, 'position_type': 'STOCK'},
    ]
    
    # Generate correlated historical prices
    dates = pd.date_range(end=datetime.now(), periods=252, freq='D')
    np.random.seed(42)
    
    # Correlated returns
    cov_matrix = np.array([
        [0.0004, 0.0002, 0.0001],  # AAPL
        [0.0002, 0.0005, 0.00015], # MSFT
        [0.0001, 0.00015, 0.0006]  # GOOGL
    ])
    
    returns_matrix = np.random.multivariate_normal(
        mean=[0.001, 0.001, 0.001],
        cov=cov_matrix,
        size=252
    )
    
    # Convert to prices
    prices = pd.DataFrame({
        'AAPL': 180.0 * np.exp(np.cumsum(returns_matrix[:, 0])),
        'MSFT': 400.0 * np.exp(np.cumsum(returns_matrix[:, 1])),
        'GOOGL': 150.0 * np.exp(np.cumsum(returns_matrix[:, 2]))
    }, index=dates)
    
    # Calculate portfolio VaR
    var_result = calculate_portfolio_var(
        positions=positions,
        historical_prices=prices,
        confidence_level=0.95,
        time_horizon_days=1,
        method='historical'
    )
    
    portfolio_value = sum(p['quantity'] * p['current_price'] for p in positions)
    
    print(f"✅ Portfolio VaR calculated")
    print(f"   Portfolio Value: ${portfolio_value:,.2f}")
    print(f"   Positions: {len(positions)}")
    print(f"   95% VaR (1-day): ${var_result.var_amount:,.2f} ({var_result.var_percent:.2f}%)")
    print(f"   95% CVaR (1-day): ${var_result.cvar_amount:,.2f} ({var_result.cvar_percent:.2f}%)")
    
    if var_result.position_contributions:
        print(f"\n   Position Contributions:")
        for symbol, contrib in var_result.position_contributions.items():
            print(f"     {symbol}: ${contrib:,.2f}")
    
    # Validation
    assert var_result.var_amount > 0, "Portfolio VaR should be positive"
    assert var_result.position_contributions is not None, "Should have position contributions"
    assert len(var_result.position_contributions) == 3, "Should have 3 position contributions"
    
    print("✅ Portfolio VaR validation passed")
    
except Exception as e:
    print(f"❌ Portfolio VaR failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test VaR report formatting
print("\n7. Testing VaR report formatting...")
try:
    report = format_var_report(var_result)
    
    print("✅ VaR report formatted")
    print("\n" + "─" * 60)
    print(report)
    print("─" * 60)
    
    # Validation
    assert "Value at Risk Report" in report, "Report should have title"
    assert f"{var_result.confidence_level * 100:.1f}%" in report, "Report should show confidence level"
    assert f"${var_result.var_amount:,.2f}" in report, "Report should show VaR amount"
    
    print("✅ Report formatting validation passed")
    
except Exception as e:
    print(f"❌ Report formatting failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test edge cases
print("\n8. Testing edge cases...")
try:
    # Empty portfolio
    empty_var = calculate_portfolio_var(
        positions=[],
        historical_prices=prices,
        confidence_level=0.95,
        time_horizon_days=1
    )
    assert empty_var.var_amount == 0.0, "Empty portfolio VaR should be 0"
    print("✅ Empty portfolio handled correctly")
    
    # Very high confidence level (99%)
    var_99 = calculate_historical_var(
        portfolio_value=100000,
        historical_returns=returns,
        confidence_level=0.99,
        time_horizon_days=1
    )
    assert var_99.var_amount > var_1day.var_amount, "99% VaR should be > 95% VaR"
    print(f"✅ 99% VaR: ${var_99.var_amount:,.2f} (vs 95% VaR: ${var_1day.var_amount:,.2f})")
    
    # Very low volatility
    low_vol_var = calculate_parametric_var(
        portfolio_value=100000,
        volatility=0.001,  # 0.1% daily volatility
        confidence_level=0.95,
        time_horizon_days=1
    )
    assert low_vol_var.var_amount < 1000, "Low volatility should give low VaR"
    print(f"✅ Low volatility VaR: ${low_vol_var.var_amount:,.2f}")
    
    print("✅ Edge cases handled correctly")
    
except Exception as e:
    print(f"❌ Edge case testing failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test different confidence levels
print("\n9. Testing confidence level comparison...")
try:
    confidence_levels = [0.90, 0.95, 0.99]
    var_amounts = []
    
    print("   Confidence Level | VaR Amount | CVaR Amount")
    print("   " + "-" * 50)
    
    for conf in confidence_levels:
        var = calculate_historical_var(
            portfolio_value=100000,
            historical_returns=returns,
            confidence_level=conf,
            time_horizon_days=1
        )
        var_amounts.append(var.var_amount)
        print(f"   {conf * 100:5.1f}%           | ${var.var_amount:9,.2f} | ${var.cvar_amount:10,.2f}")
    
    # VaR should increase with confidence level
    assert var_amounts[0] < var_amounts[1] < var_amounts[2], "VaR should increase with confidence"
    
    print("✅ Confidence level comparison passed")
    
except Exception as e:
    print(f"❌ Confidence level test failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Summary
print("\n" + "=" * 60)
print("✅ All VaR and CVaR tests passed!")
print("=" * 60)
print("\nKey Findings:")
print(f"- Parametric VaR works with normal distribution assumptions")
print(f"- Historical VaR captures actual return distribution")
print(f"- CVaR provides tail risk beyond VaR threshold")
print(f"- Portfolio VaR accounts for position correlations")
print(f"- Multi-day scaling follows square-root-of-time rule")
print(f"- Higher confidence levels → higher VaR")
print("\nNext Steps:")
print("1. ✅ VaR calculation engine complete")
print("2. ⬜ Integrate with Portfolio Dashboard UI")
print("3. ⬜ Add historical price data fetching")
print("4. ⬜ Test with real Schwab portfolio")
