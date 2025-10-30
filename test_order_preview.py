"""
Test Schwab API preview functionality for entry, profit exit, and stop-loss orders.
Validates that all three order types can be previewed via the Schwab API.
"""

import sys
from providers.schwab_trading import SchwabTrader


def test_csp_entry_preview():
    """Test CSP entry order preview"""
    print("\n" + "="*70)
    print("TEST 1: CSP Entry Order Preview")
    print("="*70)
    
    trader = SchwabTrader(dry_run=True, export_dir="./trade_orders")
    
    # Create entry order
    entry_order = trader.create_cash_secured_put_order(
        symbol="SPY",
        expiration="2025-11-15",
        strike=550.0,
        quantity=1,
        limit_price=5.50,
        duration="DAY"
    )
    
    print(f"\n📋 Entry Order Created:")
    print(f"  Action: SELL TO OPEN")
    print(f"  Symbol: SPY 251115P550")
    print(f"  Quantity: 1")
    print(f"  Limit: $5.50")
    
    # Validate order structure
    assert entry_order is not None, "Entry order should be created"
    assert 'orderLegCollection' in entry_order, "Order should have legs"
    assert len(entry_order['orderLegCollection']) == 1, "CSP should have 1 leg"
    
    leg = entry_order['orderLegCollection'][0]
    assert leg['instruction'] == 'SELL_TO_OPEN', "CSP entry should be SELL_TO_OPEN"
    assert leg['instrument']['assetType'] == 'OPTION', "Should be option"
    assert leg['quantity'] == 1, "Quantity should match"
    
    print(f"✅ Entry order structure is valid for preview")
    
    # Note: Actual preview requires Schwab API credentials
    print(f"💡 Order ready for Schwab API preview_order() call")


def test_csp_exit_preview():
    """Test CSP profit exit order preview"""
    print("\n" + "="*70)
    print("TEST 2: CSP Profit Exit Order Preview")
    print("="*70)
    
    trader = SchwabTrader(dry_run=True, export_dir="./trade_orders")
    
    # Create exit order (50% profit target)
    entry_premium = 5.50
    profit_target_pct = 50
    exit_price = entry_premium * (1.0 - profit_target_pct / 100.0)  # $2.75
    
    exit_order = trader.create_option_order(
        symbol="SPY",
        expiration="2025-11-15",
        strike=550.0,
        option_type="PUT",
        action="BUY_TO_CLOSE",
        quantity=1,
        order_type="LIMIT",
        limit_price=exit_price,
        duration="GTC"
    )
    
    print(f"\n📋 Exit Order Created:")
    print(f"  Action: BUY TO CLOSE")
    print(f"  Symbol: SPY 251115P550")
    print(f"  Quantity: 1")
    print(f"  Limit: ${exit_price} (50% profit)")
    print(f"  Duration: GTC")
    
    # Validate order structure
    assert exit_order is not None, "Exit order should be created"
    assert 'orderLegCollection' in exit_order, "Order should have legs"
    assert len(exit_order['orderLegCollection']) == 1, "Exit should have 1 leg"
    
    leg = exit_order['orderLegCollection'][0]
    assert leg['instruction'] == 'BUY_TO_CLOSE', "Exit should be BUY_TO_CLOSE"
    assert leg['quantity'] == 1, "Quantity should match"
    assert exit_order['duration'] == 'GTC', "Should be GTC"
    
    print(f"✅ Exit order structure is valid for preview")
    print(f"💡 Order ready for Schwab API preview_order() call")


def test_csp_stop_loss_preview():
    """Test CSP stop-loss order preview"""
    print("\n" + "="*70)
    print("TEST 3: CSP Stop-Loss Order Preview")
    print("="*70)
    
    trader = SchwabTrader(dry_run=True, export_dir="./trade_orders")
    
    # Create stop-loss order (2x loss limit)
    entry_premium = 5.50
    risk_multiplier = 2.0
    stop_loss_price = entry_premium * risk_multiplier  # $11.00
    
    stop_loss_order = trader.create_option_order(
        symbol="SPY",
        expiration="2025-11-15",
        strike=550.0,
        option_type="PUT",
        action="BUY_TO_CLOSE",
        quantity=1,
        order_type="LIMIT",
        limit_price=stop_loss_price,
        duration="GTC"
    )
    
    print(f"\n📋 Stop-Loss Order Created:")
    print(f"  Action: BUY TO CLOSE")
    print(f"  Symbol: SPY 251115P550")
    print(f"  Quantity: 1")
    print(f"  Limit: ${stop_loss_price} (2x loss limit)")
    print(f"  Duration: GTC")
    
    # Validate order structure
    assert stop_loss_order is not None, "Stop-loss order should be created"
    assert 'orderLegCollection' in stop_loss_order, "Order should have legs"
    assert len(stop_loss_order['orderLegCollection']) == 1, "Stop-loss should have 1 leg"
    
    leg = stop_loss_order['orderLegCollection'][0]
    assert leg['instruction'] == 'BUY_TO_CLOSE', "Stop-loss should be BUY_TO_CLOSE"
    assert leg['quantity'] == 1, "Quantity should match"
    assert stop_loss_order['duration'] == 'GTC', "Should be GTC"
    
    print(f"✅ Stop-loss order structure is valid for preview")
    print(f"💡 Order ready for Schwab API preview_order() call")


def test_iron_condor_all_orders_preview():
    """Test Iron Condor entry, exit, and stop-loss preview"""
    print("\n" + "="*70)
    print("TEST 4: Iron Condor All Orders Preview")
    print("="*70)
    
    trader = SchwabTrader(dry_run=True, export_dir="./trade_orders")
    
    # Entry order (NET CREDIT)
    entry_order = trader.create_iron_condor_order(
        symbol="SPY",
        expiration="2025-11-21",
        long_put_strike=540.0,
        short_put_strike=545.0,
        short_call_strike=575.0,
        long_call_strike=580.0,
        quantity=1,
        limit_price=2.50,
        duration="DAY"
    )
    
    print(f"\n📋 Entry Order Created (NET CREDIT):")
    print(f"  Legs: 4 (Buy Put 540, Sell Put 545, Sell Call 575, Buy Call 580)")
    print(f"  Net Credit: $2.50")
    
    assert len(entry_order['orderLegCollection']) == 4, "IC should have 4 legs"
    print(f"✅ Entry order (4-leg) ready for preview")
    
    # Exit order (NET DEBIT)
    entry_credit = 2.50
    profit_target_pct = 50
    exit_debit = entry_credit * (1.0 - profit_target_pct / 100.0)  # $1.25
    
    exit_order = trader.create_iron_condor_exit_order(
        symbol="SPY",
        expiration="2025-11-21",
        long_put_strike=540.0,
        short_put_strike=545.0,
        short_call_strike=575.0,
        long_call_strike=580.0,
        quantity=1,
        limit_price=exit_debit,
        duration="GTC"
    )
    
    print(f"\n📋 Exit Order Created (NET DEBIT):")
    print(f"  Legs: 4 (reversed actions)")
    print(f"  Net Debit: ${exit_debit} (50% profit)")
    
    assert len(exit_order['orderLegCollection']) == 4, "IC exit should have 4 legs"
    print(f"✅ Exit order (4-leg) ready for preview")
    
    # Stop-loss order (NET DEBIT)
    risk_multiplier = 2.0
    stop_loss_debit = entry_credit * risk_multiplier  # $5.00
    
    stop_loss_order = trader.create_iron_condor_exit_order(
        symbol="SPY",
        expiration="2025-11-21",
        long_put_strike=540.0,
        short_put_strike=545.0,
        short_call_strike=575.0,
        long_call_strike=580.0,
        quantity=1,
        limit_price=stop_loss_debit,
        duration="GTC"
    )
    
    print(f"\n📋 Stop-Loss Order Created (NET DEBIT):")
    print(f"  Legs: 4 (reversed actions)")
    print(f"  Net Debit: ${stop_loss_debit} (2x loss limit)")
    
    assert len(stop_loss_order['orderLegCollection']) == 4, "IC stop should have 4 legs"
    print(f"✅ Stop-loss order (4-leg) ready for preview")
    
    print(f"\n💡 All 3 Iron Condor orders ready for Schwab API preview")


def test_collar_all_orders_preview():
    """Test Collar entry, exit, and stop-loss preview"""
    print("\n" + "="*70)
    print("TEST 5: Collar All Orders Preview")
    print("="*70)
    
    trader = SchwabTrader(dry_run=True, export_dir="./trade_orders")
    
    # Entry order (2-leg: sell call, buy put)
    entry_order = trader.create_collar_order(
        symbol="TSLA",
        expiration="2025-12-05",
        call_strike=250.0,
        put_strike=220.0,
        quantity=1,
        limit_price=2.00,
        duration="DAY"
    )
    
    print(f"\n📋 Entry Order Created:")
    print(f"  Legs: 2 (Sell Call 250, Buy Put 220)")
    print(f"  Net Credit: $2.00")
    
    assert len(entry_order['orderLegCollection']) == 2, "Collar should have 2 legs"
    print(f"✅ Entry order (2-leg) ready for preview")
    
    # Exit orders (2 separate orders)
    call_entry = 5.00
    profit_target_pct = 75
    call_exit_price = call_entry * (1.0 - profit_target_pct / 100.0)  # $1.25
    
    exit_order_call = trader.create_option_order(
        symbol="TSLA",
        expiration="2025-12-05",
        strike=250.0,
        option_type="CALL",
        action="BUY_TO_CLOSE",
        quantity=1,
        order_type="LIMIT",
        limit_price=call_exit_price,
        duration="GTC"
    )
    
    print(f"\n📋 Call Exit Order Created:")
    print(f"  Action: BUY TO CLOSE")
    print(f"  Limit: ${call_exit_price} (75% profit)")
    
    assert exit_order_call is not None, "Call exit should be created"
    print(f"✅ Call exit order ready for preview")
    
    put_cost = 3.00
    put_exit_price = put_cost * (1.0 - profit_target_pct / 100.0)  # $0.75
    
    exit_order_put = trader.create_option_order(
        symbol="TSLA",
        expiration="2025-12-05",
        strike=220.0,
        option_type="PUT",
        action="SELL_TO_CLOSE",
        quantity=1,
        order_type="LIMIT",
        limit_price=put_exit_price,
        duration="GTC"
    )
    
    print(f"\n📋 Put Exit Order Created:")
    print(f"  Action: SELL TO CLOSE")
    print(f"  Limit: ${put_exit_price} (75% profit)")
    
    assert exit_order_put is not None, "Put exit should be created"
    print(f"✅ Put exit order ready for preview")
    
    # Stop-loss (call only)
    risk_multiplier = 2.0
    call_stop_loss = call_entry * risk_multiplier  # $10.00
    
    stop_loss_order = trader.create_option_order(
        symbol="TSLA",
        expiration="2025-12-05",
        strike=250.0,
        option_type="CALL",
        action="BUY_TO_CLOSE",
        quantity=1,
        order_type="LIMIT",
        limit_price=call_stop_loss,
        duration="GTC"
    )
    
    print(f"\n📋 Stop-Loss Order Created:")
    print(f"  Action: BUY TO CLOSE (call)")
    print(f"  Limit: ${call_stop_loss} (2x loss limit)")
    
    assert stop_loss_order is not None, "Stop-loss should be created"
    print(f"✅ Stop-loss order ready for preview")
    
    print(f"\n💡 All 4 Collar orders ready for Schwab API preview")
    print(f"   (1 entry, 2 exits, 1 stop-loss)")


if __name__ == "__main__":
    print("="*70)
    print("ORDER PREVIEW TEST SUITE")
    print("="*70)
    print("\nValidating that all order types can be previewed with Schwab API")
    print("Note: These tests validate order structure only.")
    print("Actual API preview requires Schwab credentials.\n")
    
    try:
        test_csp_entry_preview()
        test_csp_exit_preview()
        test_csp_stop_loss_preview()
        test_iron_condor_all_orders_preview()
        test_collar_all_orders_preview()
        
        print("\n" + "="*70)
        print("✅ ALL ORDER PREVIEW TESTS PASSED (5/5)")
        print("="*70)
        print("\nAll order types validated:")
        print("  ✓ CSP - Entry, profit exit, stop-loss")
        print("  ✓ Iron Condor - Entry (4-leg), exit (4-leg), stop-loss (4-leg)")
        print("  ✓ Collar - Entry (2-leg), exits (2 orders), stop-loss")
        print("\n🎯 All orders are properly structured for Schwab API preview")
        print("💡 Use the Streamlit UI preview buttons to test with real API")
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
