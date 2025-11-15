#!/usr/bin/env python3
"""Test script for Portfolio Risk Management Phase 1.1.

Tests:
1. Portfolio manager position loading and metrics
2. Greeks aggregation by underlying
3. Risk alerts generation
4. Mock positions for testing
5. DataFrame formatting

Usage:
  python test_portfolio.py           # Unit tests with mock data
  python test_schwab_integration.py  # Integration tests with real Schwab API

Author: Options Strategy Lab
Created: 2025-11-15
"""

import sys
import os
from datetime import datetime, timezone

# Test mode configuration
USE_MOCK_DATA = True  # Set to False to test with real Schwab API

# Test imports
print("=" * 60)
print("Testing Portfolio Risk Management Phase 1.1")
print(f"Mode: {'UNIT TESTS (Mock Data)' if USE_MOCK_DATA else 'INTEGRATION (Real Schwab)'}")
print("=" * 60)

print("\n1. Testing imports...")
try:
    from portfolio_manager import Position, PortfolioMetrics, PortfolioManager, get_portfolio_manager
    print("✅ portfolio_manager imports successful")
except Exception as e:
    print(f"❌ portfolio_manager import failed: {e}")
    sys.exit(1)

try:
    from schwab_positions import get_mock_positions, _parse_schwab_position
    print("✅ schwab_positions imports successful")
except Exception as e:
    print(f"❌ schwab_positions import failed: {e}")
    sys.exit(1)

print("\n2. Testing mock positions...")
try:
    mock_positions = get_mock_positions()
    print(f"✅ Created {len(mock_positions)} mock positions")
    
    for i, pos in enumerate(mock_positions):
        print(f"\n   Position {i+1}:")
        print(f"   - Symbol: {pos.symbol}")
        print(f"   - Type: {pos.position_type}")
        print(f"   - Quantity: {pos.quantity}")
        print(f"   - Delta: {pos.delta:.2f}")
        print(f"   - Value: ${pos.market_value:,.2f}")
        
except Exception as e:
    print(f"❌ Mock positions failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n3. Testing PortfolioManager...")
try:
    pm = get_portfolio_manager()
    pm.load_positions(mock_positions)
    print(f"✅ Loaded {len(pm.positions)} positions")
    
    if pm.metrics:
        print(f"\n   Portfolio Metrics:")
        print(f"   - Total Delta: {pm.metrics.total_delta:.2f}")
        print(f"   - Total Gamma: {pm.metrics.total_gamma:.4f}")
        print(f"   - Total Vega: {pm.metrics.total_vega:.2f}")
        print(f"   - Total Theta: {pm.metrics.total_theta:.2f}")
        print(f"   - Net Value: ${pm.metrics.net_market_value:,.2f}")
        print(f"   - Gross Exposure: ${pm.metrics.gross_market_value:,.2f}")
        print(f"   - Positions: {pm.metrics.num_positions}")
        print(f"   - Underlyings: {pm.metrics.num_underlyings}")
        print(f"   - Max Position %: {pm.metrics.max_position_pct:.1f}%")
    else:
        print("❌ No metrics calculated")
        
except Exception as e:
    print(f"❌ PortfolioManager failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n4. Testing metrics summary...")
try:
    summary = pm.get_metrics_summary()
    print("✅ Metrics summary:")
    for key, value in summary.items():
        print(f"   - {key}: {value}")
        
except Exception as e:
    print(f"❌ Metrics summary failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n5. Testing Greeks by underlying...")
try:
    greeks_df = pm.get_greeks_by_underlying()
    print(f"✅ Greeks aggregated for {len(greeks_df)} underlyings")
    print("\n" + greeks_df.to_string(index=False))
    
except Exception as e:
    print(f"❌ Greeks aggregation failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n6. Testing position details DataFrame...")
try:
    pos_df = pm.get_positions_df()
    print(f"✅ Position details for {len(pos_df)} positions")
    print("\n" + pos_df.to_string(index=False))
    
except Exception as e:
    print(f"❌ Position details failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n7. Testing risk alerts...")
try:
    alerts = pm.check_risk_alerts()
    print(f"✅ Generated {len(alerts)} risk alerts:")
    if alerts:
        for alert in alerts:
            print(f"   {alert}")
    else:
        print("   (no alerts for mock portfolio)")
        
except Exception as e:
    print(f"❌ Risk alerts failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n8. Testing global portfolio manager singleton...")
try:
    pm2 = get_portfolio_manager()
    assert pm2 is pm, "Singleton not working"
    print("✅ Singleton pattern working correctly")
    
except Exception as e:
    print(f"❌ Singleton test failed: {e}")
    sys.exit(1)

print("\n9. Testing empty portfolio...")
try:
    # Clear the singleton's positions to test empty state
    pm_empty = get_portfolio_manager()
    pm_empty.load_positions([])
    
    assert pm_empty.metrics is not None, "Metrics should exist for empty portfolio"
    assert pm_empty.metrics.num_positions == 0, "Should have 0 positions"
    assert pm_empty.metrics.total_delta == 0.0, "Delta should be 0"
    
    summary = pm_empty.get_metrics_summary()
    greeks_df = pm_empty.get_greeks_by_underlying()
    pos_df = pm_empty.get_positions_df()
    alerts = pm_empty.check_risk_alerts()
    
    print("✅ Empty portfolio handled correctly")
    
    # Restore mock positions for subsequent tests
    pm_empty.load_positions(mock_positions)
    
except Exception as e:
    print(f"❌ Empty portfolio test failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n10. Testing high-risk scenarios...")
try:
    # Create positions with high concentration
    high_risk_positions = [
        Position(
            symbol='AAPL',
            quantity=1000,  # Large position
            position_type='STOCK',
            current_price=180.00,
            underlying_price=180.00,
            delta=1000.0,  # High delta
            gamma=0.0,
            vega=0.0,
            theta=0.0,
            market_value=180000.0,
            cost_basis=170000.0,
            unrealized_pnl=10000.0,
            account_id='TEST',
            retrieved_at=datetime.now(timezone.utc)
        ),
        Position(
            symbol='AAPL',
            quantity=10,
            position_type='CALL',
            strike=185.0,
            expiration='2025-01-17',
            current_price=5.00,
            underlying_price=180.00,
            delta=0.50,
            gamma=0.50,  # High gamma
            vega=0.30,
            theta=-0.10,
            market_value=5000.0,
            cost_basis=4000.0,
            unrealized_pnl=1000.0,
            account_id='TEST',
            retrieved_at=datetime.now(timezone.utc)
        )
    ]
    
    pm_risk = get_portfolio_manager()
    pm_risk.load_positions(high_risk_positions)
    
    risk_alerts = pm_risk.check_risk_alerts()
    print(f"✅ High-risk scenario generated {len(risk_alerts)} alerts:")
    for alert in risk_alerts:
        print(f"   {alert}")
    
    # Verify alerts contain expected warnings
    alert_text = " ".join(risk_alerts)
    assert "delta" in alert_text.lower() or "gamma" in alert_text.lower(), \
        "Should warn about delta/gamma"
    
    print("✅ Risk detection working correctly")
    
except Exception as e:
    print(f"❌ High-risk scenario test failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 60)
print("✅ All Portfolio Risk Management tests passed!")
print("=" * 60)
print("\nNext steps:")
print("1. Start Streamlit app: streamlit run strategy_lab.py")
print("2. Navigate to '📊 Portfolio' tab")
print("3. Check 'Use Mock Data' to see demo portfolio")
print("4. Verify metrics, Greeks, and alerts display correctly")
print("\nFor Schwab integration:")
print("1. Configure PROVIDER='schwab' in config.py")
print("2. Authenticate with Schwab API")
print("3. Uncheck 'Use Mock Data' to load real positions")
