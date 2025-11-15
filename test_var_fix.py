#!/usr/bin/env python3
"""Quick test of VaR fix with Black-Scholes repricing."""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from risk_metrics.var_calculator import calculate_portfolio_var

# Test case: NVDA long call similar to user's position
# 1 contract, 12/12/25 expiry, $260 strike, current spot ~$190, premium $0.31/share

def test_nvda_call_var():
    """Test VaR for NVDA call option - should show reasonable loss < full premium."""
    
    # Position details matching user's actual position
    positions = [{
        'symbol': 'NVDA',
        'quantity': 1,  # 1 contract long
        'underlying_price': 190.0,
        'option_price': 0.31,  # $0.31 per share = $31 total
        'position_type': 'CALL',
        'market_value': 31.0,  # 1 * 0.31 * 100
        'delta': 0.1,  # Rough estimate for OTM call
        'strike': 260.0,
        'expiration': '2025-12-12'
    }]
    
    # Generate synthetic historical data for NVDA
    # Use realistic volatility: mean daily return near 0%, std dev ~2%
    np.random.seed(42)
    n_days = 252
    dates = pd.date_range(end=datetime.now(), periods=n_days, freq='D')
    
    # Simulate returns: mean=0%, std=2% daily
    returns = np.random.normal(0.0, 0.02, n_days)
    
    # Add some tail events (5% of days have larger moves)
    n_tail = int(0.05 * n_days)
    tail_indices = np.random.choice(n_days, n_tail, replace=False)
    returns[tail_indices] *= 2.5  # Amplify tail moves
    
    # Convert to prices (starting at $190)
    prices = 190.0 * np.cumprod(1 + returns)
    
    historical_prices = pd.DataFrame({'NVDA': prices}, index=dates)
    
    print("=" * 70)
    print("NVDA CALL OPTION VaR TEST")
    print("=" * 70)
    print(f"\nPosition Details:")
    print(f"  Underlying: NVDA @ ${positions[0]['underlying_price']:.2f}")
    print(f"  Strike: ${positions[0]['strike']:.2f}")
    print(f"  Expiration: {positions[0]['expiration']}")
    print(f"  Contracts: {positions[0]['quantity']}")
    print(f"  Premium: ${positions[0]['option_price']:.2f}/share = ${positions[0]['market_value']:.2f} total")
    print(f"  Delta: {positions[0]['delta']:.2f}")
    print(f"  Position Type: {positions[0]['position_type']}")
    
    print(f"\nHistorical Data:")
    print(f"  Days: {n_days}")
    print(f"  Price range: ${prices.min():.2f} - ${prices.max():.2f}")
    print(f"  Mean daily return: {returns.mean()*100:.2f}%")
    print(f"  Std dev daily return: {returns.std()*100:.2f}%")
    print(f"  95th percentile loss return: {np.percentile(-returns, 95)*100:.2f}%")
    
    # Calculate VaR
    result = calculate_portfolio_var(
        positions=positions,
        historical_prices=historical_prices,
        confidence_level=0.95,
        time_horizon_days=1,
        method='historical'
    )
    
    # Calculate portfolio value
    portfolio_value = sum(abs(p['quantity']) * p.get('option_price', p['underlying_price']) * 
                         (100 if p['position_type'] in ['CALL', 'PUT'] else 1) 
                         for p in positions)
    
    print(f"\n{'='*70}")
    print(f"VaR RESULTS (95% confidence, 1-day horizon)")
    print(f"{'='*70}")
    print(f"Portfolio Value:     ${portfolio_value:.2f}")
    print(f"VaR (dollar):        ${result.var_amount:.2f}")
    print(f"VaR (percent):       {result.var_percent:.2f}%")
    print(f"CVaR (dollar):       ${result.cvar_amount:.2f}")
    print(f"CVaR (percent):      {result.cvar_percent:.2f}%")
    
    # Validation checks
    print(f"\n{'='*70}")
    print(f"VALIDATION CHECKS")
    print(f"{'='*70}")
    
    issues = []
    
    # Check 1: VaR should be less than premium paid
    if result.var_amount >= positions[0]['market_value']:
        issues.append(f"❌ VaR (${result.var_amount:.2f}) >= premium (${positions[0]['market_value']:.2f})")
    else:
        print(f"✅ VaR (${result.var_amount:.2f}) < premium (${positions[0]['market_value']:.2f})")
    
    # Check 2: VaR should be > 0 (not zero risk)
    if result.var_amount <= 0:
        issues.append(f"❌ VaR is zero or negative: ${result.var_amount:.2f}")
    else:
        print(f"✅ VaR is positive: ${result.var_amount:.2f}")
    
    # Check 3: VaR% should be reasonable (not 100%)
    if result.var_percent >= 99.0:
        issues.append(f"❌ VaR% too high: {result.var_percent:.2f}%")
    else:
        print(f"✅ VaR% is reasonable: {result.var_percent:.2f}%")
    
    # Check 4: CVaR should be >= VaR
    if result.cvar_amount is not None and result.cvar_amount < result.var_amount:
        issues.append(f"❌ CVaR (${result.cvar_amount:.2f}) < VaR (${result.var_amount:.2f})")
    elif result.cvar_amount is not None:
        print(f"✅ CVaR (${result.cvar_amount:.2f}) >= VaR (${result.var_amount:.2f})")
    
    # Check 5: For OTM long call, expect VaR in range $5-$25 (not full $31)
    if result.var_amount < 5.0 or result.var_amount > 28.0:
        issues.append(f"⚠️  VaR outside expected range $5-$28: ${result.var_amount:.2f}")
    else:
        print(f"✅ VaR in expected range: ${result.var_amount:.2f}")
    
    if issues:
        print(f"\n❌ FOUND {len(issues)} ISSUE(S):")
        for issue in issues:
            print(f"  {issue}")
        return False
    else:
        print(f"\n✅ ALL CHECKS PASSED!")
        return True


if __name__ == '__main__':
    success = test_nvda_call_var()
    exit(0 if success else 1)
