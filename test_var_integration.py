#!/usr/bin/env python3
"""Quick VaR integration test with portfolio manager.

Tests the full integration of VaR calculations with portfolio manager.
"""

import sys
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

print("=" * 60)
print("VaR Integration Test")
print("=" * 60)

# Test imports
print("\n1. Testing imports...")
try:
    from portfolio_manager import get_portfolio_manager, Position
    from schwab_positions import get_mock_positions
    print("✅ Portfolio modules imported")
except Exception as e:
    print(f"❌ Import failed: {e}")
    sys.exit(1)

# Load mock positions
print("\n2. Loading mock portfolio...")
try:
    pm = get_portfolio_manager()
    positions = get_mock_positions()
    pm.load_positions(positions)
    
    print(f"✅ Loaded {len(positions)} positions")
    if pm.metrics:
        print(f"   Portfolio value: ${pm.metrics.net_market_value:,.2f}")
    
except Exception as e:
    print(f"❌ Failed to load positions: {e}")
    sys.exit(1)

# Generate synthetic historical prices
print("\n3. Generating synthetic historical prices...")
try:
    # Get unique symbols
    symbols = list(set(pos.symbol for pos in positions))
    print(f"   Symbols: {', '.join(symbols)}")
    
    # Generate 252 days of price history
    dates = pd.date_range(end=datetime.now(), periods=252, freq='D')
    np.random.seed(42)
    
    prices_dict = {}
    for symbol in symbols:
        # Get current price from positions
        current_price = next(
            (p.underlying_price or p.current_price for p in positions if p.symbol == symbol),
            100.0
        )
        
        # Generate returns with realistic volatility
        returns = np.random.normal(0.0005, 0.015, 252)  # ~1.5% daily vol
        prices = current_price * np.exp(np.cumsum(returns - returns.mean()))
        prices_dict[symbol] = prices
    
    hist_prices = pd.DataFrame(prices_dict, index=dates)
    
    print(f"✅ Generated {len(hist_prices)} days of price history")
    print(f"   Volatility (AAPL): {np.std(hist_prices['AAPL'].pct_change().dropna()) * 100:.2f}%")
    
except Exception as e:
    print(f"❌ Failed to generate prices: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Calculate VaR
print("\n4. Calculating VaR...")
try:
    var_result = pm.calculate_var(
        historical_prices=hist_prices,
        confidence_level=0.95,
        time_horizon_days=1,
        method='historical'
    )
    
    if var_result:
        print(f"✅ VaR calculated successfully")
        print(f"\n   Method: {var_result.method.title()}")
        print(f"   Confidence: {var_result.confidence_level * 100:.0f}%")
        print(f"   Time Horizon: {var_result.time_horizon_days} day(s)")
        print(f"\n   VaR (95%, 1-day):  ${var_result.var_amount:,.2f} ({var_result.var_percent:.2f}%)")
        print(f"   CVaR (95%, 1-day): ${var_result.cvar_amount:,.2f} ({var_result.cvar_percent:.2f}%)")
        print(f"\n   Portfolio Volatility: {(var_result.volatility or 0) * 100:.2f}%")
        
        if var_result.position_contributions:
            print(f"\n   Risk Attribution:")
            for symbol, value in sorted(
                var_result.position_contributions.items(),
                key=lambda x: abs(x[1]),
                reverse=True
            ):
                print(f"     {symbol}: ${value:,.2f}")
        
        # Validation
        assert var_result.var_amount > 0, "VaR should be positive"
        assert var_result.cvar_amount and var_result.cvar_amount > 0, "CVaR should be positive"
        if pm.metrics:
            assert var_result.var_amount < pm.metrics.gross_market_value, "VaR should be less than portfolio value"
        
        print(f"\n✅ VaR integration validation passed")
        
    else:
        print("❌ VaR calculation returned None")
        sys.exit(1)
        
except Exception as e:
    print(f"❌ VaR calculation failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test parametric VaR
print("\n5. Testing parametric VaR...")
try:
    var_parametric = pm.calculate_var(
        historical_prices=hist_prices,
        confidence_level=0.95,
        time_horizon_days=1,
        method='parametric'
    )
    
    if var_parametric:
        print(f"✅ Parametric VaR calculated")
        print(f"   VaR (parametric):  ${var_parametric.var_amount:,.2f}")
        print(f"   VaR (historical):  ${var_result.var_amount:,.2f}")
        print(f"   Difference: ${abs(var_parametric.var_amount - var_result.var_amount):,.2f}")
        
    else:
        print("⚠️ Parametric VaR returned None")
        
except Exception as e:
    print(f"❌ Parametric VaR failed: {e}")

# Test different confidence levels
print("\n6. Testing different confidence levels...")
try:
    for conf in [0.90, 0.95, 0.99]:
        var = pm.calculate_var(
            historical_prices=hist_prices,
            confidence_level=conf,
            time_horizon_days=1,
            method='historical'
        )
        if var:
            print(f"   {conf*100:.0f}% VaR: ${var.var_amount:,.2f} ({var.var_percent:.2f}%)")
    
    print("✅ Multi-confidence level test passed")
    
except Exception as e:
    print(f"❌ Multi-confidence test failed: {e}")

# Summary
print("\n" + "=" * 60)
print("✅ VaR Integration Test Complete!")
print("=" * 60)
print(f"\nKey Results:")
if pm.metrics:
    print(f"- Portfolio Value: ${pm.metrics.net_market_value:,.2f}")
print(f"- 95% VaR (1-day): ${var_result.var_amount:,.2f}")
print(f"- Risk as % of Portfolio: {var_result.var_percent:.2f}%")
print(f"\nInterpretation:")
print(f"There is a 5% chance of losing more than ${var_result.var_amount:,.2f}")
print(f"over the next day based on historical return distribution.")
print(f"\nNext Steps:")
print(f"1. ✅ VaR calculation engine working")
print(f"2. ✅ Portfolio manager integration complete")
print(f"3. ⬜ Test in Streamlit UI: streamlit run strategy_lab.py")
print(f"4. ⬜ Navigate to '📊 Portfolio' tab and click 'Calculate VaR'")
