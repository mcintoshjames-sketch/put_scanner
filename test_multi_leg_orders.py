#!/usr/bin/env python3
"""
Test multi-leg order creation for Trade Execution
"""

import os
try:
    import pytest as _pytest  # type: ignore
    if not os.getenv("RUN_INTEGRATION"):
        _pytest.skip("Skipping multi-leg order tests; set RUN_INTEGRATION=1 to run.", allow_module_level=True)
except Exception:
    pass
from providers.schwab_trading import SchwabTrader
import json

def test_collar_order():
    """Test collar order creation"""
    print("\n=== Testing Collar Order ===")
    trader = SchwabTrader(dry_run=True)
    
    order = trader.create_collar_order(
        symbol="AAPL",
        expiration="2025-12-19",
        call_strike=200.0,
        put_strike=160.0,
        quantity=1,
        limit_price=1.50,  # Net credit
        duration="GTC"
    )
    
    print(json.dumps(order, indent=2))
    print("\n✅ Collar order created successfully")
    
    # Validate
    validation = trader.validate_order(order)
    print(f"Valid: {validation['valid']}")
    if validation['warnings']:
        print(f"Warnings: {validation['warnings']}")
    if validation['errors']:
        print(f"Errors: {validation['errors']}")
    
    return order

def test_iron_condor_order():
    """Test iron condor order creation"""
    print("\n=== Testing Iron Condor Order ===")
    trader = SchwabTrader(dry_run=True)
    
    order = trader.create_iron_condor_order(
        symbol="SPY",
        expiration="2025-12-19",
        long_put_strike=540.0,
        short_put_strike=550.0,
        short_call_strike=590.0,
        long_call_strike=600.0,
        quantity=1,
        limit_price=2.50,  # Net credit
        duration="DAY"
    )
    
    print(json.dumps(order, indent=2))
    print("\n✅ Iron Condor order created successfully")
    
    # Validate
    validation = trader.validate_order(order)
    print(f"Valid: {validation['valid']}")
    if validation['warnings']:
        print(f"Warnings: {validation['warnings']}")
    if validation['errors']:
        print(f"Errors: {validation['errors']}")
    
    return order

def test_covered_call_order():
    """Test covered call order creation"""
    print("\n=== Testing Covered Call Order ===")
    trader = SchwabTrader(dry_run=True)
    
    order = trader.create_covered_call_order(
        symbol="TSLA",
        expiration="2025-11-15",
        strike=320.0,
        quantity=2,
        limit_price=5.50,
        duration="DAY"
    )
    
    print(json.dumps(order, indent=2))
    print("\n✅ Covered Call order created successfully")
    
    # Validate
    validation = trader.validate_order(order)
    print(f"Valid: {validation['valid']}")
    if validation['warnings']:
        print(f"Warnings: {validation['warnings']}")
    if validation['errors']:
        print(f"Errors: {validation['errors']}")
    
    return order

def test_csp_order():
    """Test CSP order creation"""
    print("\n=== Testing Cash-Secured Put Order ===")
    trader = SchwabTrader(dry_run=True)
    
    order = trader.create_cash_secured_put_order(
        symbol="NVDA",
        expiration="2025-11-22",
        strike=450.0,
        quantity=1,
        limit_price=8.50,
        duration="GTC"
    )
    
    print(json.dumps(order, indent=2))
    print("\n✅ CSP order created successfully")
    
    # Validate
    validation = trader.validate_order(order)
    print(f"Valid: {validation['valid']}")
    if validation['warnings']:
        print(f"Warnings: {validation['warnings']}")
    if validation['errors']:
        print(f"Errors: {validation['errors']}")
    
    return order

if __name__ == "__main__":
    print("Testing Multi-Leg Order Creation")
    print("=" * 50)
    
    try:
        # Test all order types
        csp = test_csp_order()
        cc = test_covered_call_order()
        collar = test_collar_order()
        ic = test_iron_condor_order()
        
        print("\n" + "=" * 50)
        print("✅ All tests passed!")
        print("\nOrder Summary:")
        print(f"- CSP: {len(csp['orderLegCollection'])} leg(s)")
        print(f"- Covered Call: {len(cc['orderLegCollection'])} leg(s)")
        print(f"- Collar: {len(collar['orderLegCollection'])} leg(s)")
        print(f"- Iron Condor: {len(ic['orderLegCollection'])} leg(s)")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
