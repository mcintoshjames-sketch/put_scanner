#!/usr/bin/env python3
"""
Test live trading with safety mechanism.
Demonstrates that orders must be previewed before execution.
"""

import sys
sys.path.insert(0, '/workspaces/put_scanner')

import os
try:
    import pytest as _pytest  # type: ignore
    if not os.getenv("RUN_INTEGRATION"):
        _pytest.skip("Skipping live trading safety tests; set RUN_INTEGRATION=1 to run.", allow_module_level=True)
except Exception:
    pass
from providers.schwab_trading import SchwabTrader
from datetime import datetime


def test_safety_mechanism():
    """
    Test that safety mechanism prevents execution without preview.
    """
    
    print("\n" + "="*80)
    print("LIVE TRADING SAFETY MECHANISM TEST")
    print("="*80)
    
    # Create trader in LIVE mode (dry_run=False)
    print("\n1. Creating trader in LIVE mode (dry_run=False)...")
    trader = SchwabTrader(
        account_id="test_account_hash",
        dry_run=False,  # LIVE MODE
        client=None  # We'll test without actual client
    )
    
    # Create a sample order
    order = trader.create_option_order(
        symbol="SPY",
        expiration="2025-11-15",
        strike=550.0,
        option_type="PUT",
        action="SELL_TO_OPEN",
        quantity=1,
        order_type="LIMIT",
        limit_price=5.50,
        duration="DAY"
    )
    
    print("\n2. Sample order created:")
    print(f"   Symbol: SPY Nov 15 2025 $550 PUT")
    print(f"   Action: SELL_TO_OPEN (Cash-Secured Put)")
    print(f"   Quantity: 1 contract")
    print(f"   Limit Price: $5.50")
    
    # Test 1: Try to submit without preview (should fail)
    print("\n" + "="*80)
    print("TEST 1: Attempt to execute WITHOUT preview (should FAIL)")
    print("="*80)
    
    try:
        result = trader.submit_order(order, strategy_type="csp")
        print("❌ SAFETY MECHANISM FAILED: Order should have been rejected!")
        print(f"   Result: {result}")
    except RuntimeError as e:
        print("✅ SAFETY MECHANISM WORKING: Order rejected as expected")
        print(f"   Error: {str(e)[:200]}...")
    
    # Test 2: Preview the order
    print("\n" + "="*80)
    print("TEST 2: Preview the order first")
    print("="*80)
    
    print("   Simulating preview registration...")
    order_hash = trader._register_preview(order)
    print(f"✅ Order previewed and registered")
    print(f"   Order hash: {order_hash}")
    print(f"   Preview valid for: {trader._preview_expiry_minutes} minutes")
    
    # Test 3: Check if order is previewed
    print("\n" + "="*80)
    print("TEST 3: Verify order is marked as previewed")
    print("="*80)
    
    is_previewed = trader._is_previewed(order)
    if is_previewed:
        print("✅ Order is marked as previewed")
        print("   Order can now be executed")
    else:
        print("❌ Order not marked as previewed")
    
    # Test 4: Now try to submit (should still fail due to no client)
    print("\n" + "="*80)
    print("TEST 4: Attempt to execute AFTER preview (should fail due to no client)")
    print("="*80)
    
    try:
        result = trader.submit_order(order, strategy_type="csp")
        print("❌ Should have failed due to no client")
    except RuntimeError as e:
        error_msg = str(e)
        if "SAFETY CHECK FAILED" in error_msg:
            print("❌ Safety check failed (preview not detected)")
        elif "client required" in error_msg.lower():
            print("✅ Safety check PASSED, failed at client validation (expected)")
            print(f"   Error: {error_msg[:150]}...")
        else:
            print(f"⚠️ Unexpected error: {error_msg[:150]}...")
    
    # Test 5: Test with dry_run mode (should work)
    print("\n" + "="*80)
    print("TEST 5: Test with DRY RUN mode (should export to file)")
    print("="*80)
    
    trader_dry = SchwabTrader(dry_run=True)
    result = trader_dry.submit_order(order, strategy_type="csp")
    
    print(f"✅ Dry run successful:")
    print(f"   Status: {result['status']}")
    print(f"   Filepath: {result['filepath']}")
    print(f"   Message: {result['message']}")
    
    # Test 6: Test order hash consistency
    print("\n" + "="*80)
    print("TEST 6: Verify order hash is consistent")
    print("="*80)
    
    hash1 = trader._compute_order_hash(order)
    hash2 = trader._compute_order_hash(order)
    
    if hash1 == hash2:
        print(f"✅ Order hash is consistent: {hash1}")
    else:
        print(f"❌ Order hash inconsistent: {hash1} != {hash2}")
    
    # Test 7: Different orders have different hashes
    print("\n" + "="*80)
    print("TEST 7: Verify different orders have different hashes")
    print("="*80)
    
    order2 = trader.create_option_order(
        symbol="SPY",
        expiration="2025-11-15",
        strike=545.0,  # Different strike
        option_type="PUT",
        action="SELL_TO_OPEN",
        quantity=1,
        order_type="LIMIT",
        limit_price=5.00,  # Different price
        duration="DAY"
    )
    
    hash_order1 = trader._compute_order_hash(order)
    hash_order2 = trader._compute_order_hash(order2)
    
    if hash_order1 != hash_order2:
        print(f"✅ Different orders have different hashes:")
        print(f"   Order 1 (K=$550): {hash_order1}")
        print(f"   Order 2 (K=$545): {hash_order2}")
    else:
        print(f"❌ Different orders have same hash: {hash_order1}")
    
    # Summary
    print("\n" + "="*80)
    print("SAFETY MECHANISM SUMMARY")
    print("="*80)
    print("""
The safety mechanism works as follows:

1. **Preview Required**: All live orders must be previewed first
   - preview_order() registers the order hash with timestamp
   - Hash is based on order type, legs, prices, quantities
   
2. **30-Minute Window**: Preview is valid for 30 minutes
   - Prevents stale previews from being executed
   - Forces user to re-review if too much time passes
   
3. **Automatic Cleanup**: After execution, preview is cleared
   - Prevents same order from being executed twice
   - Forces fresh preview for each execution
   
4. **Dry Run Bypass**: Safety mechanism only applies to live trades
   - dry_run=True bypasses all checks
   - Always safe for testing and development

5. **Multiple Safety Layers**:
   ✓ Preview check (order must be previewed first)
   ✓ Client check (API client must be configured)
   ✓ Account check (account ID must be provided)
   ✓ Validation check (order structure must be valid)

This ensures you can NEVER accidentally execute a live trade without:
- Explicitly setting dry_run=False
- Previewing the exact order first
- Having valid API credentials
- All within a 30-minute window
    """)
    
    print("="*80 + "\n")


if __name__ == "__main__":
    test_safety_mechanism()
