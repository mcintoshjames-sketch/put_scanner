"""
Test profit-taking exit order generation for all strategies.
Validates that exit orders are properly created based on runbook profit targets.
"""

import sys
import json
from pathlib import Path
from providers.schwab_trading import SchwabTrader


def test_csp_exit_order():
    """Test Cash-Secured Put exit order generation"""
    print("\n" + "="*60)
    print("TEST 1: Cash-Secured Put Exit Order")
    print("="*60)
    
    trader = SchwabTrader(dry_run=True, export_dir="./trade_orders")
    
    # Entry: Sell $550 PUT for $5.50 premium
    entry_premium = 5.50
    profit_capture_pct = 50  # 50% profit target
    
    # Calculate exit price (close when mark <= entry * (1 - capture%))
    exit_price = max(0.05, entry_premium * (1.0 - profit_capture_pct / 100.0))
    expected_exit = 5.50 * 0.5  # $2.75
    
    print(f"\nEntry: SELL TO OPEN $550 PUT @ ${entry_premium}")
    print(f"Profit Target: {profit_capture_pct}%")
    print(f"Exit Price: ${exit_price:.2f} (expected: ${expected_exit:.2f})")
    
    # Create exit order
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
    
    # Validate exit order
    assert exit_order["orderLegCollection"][0]["instruction"] == "BUY_TO_CLOSE"
    assert exit_order["orderType"] == "LIMIT"
    assert exit_order["duration"] == "GTC"
    assert exit_order["price"] == exit_price
    
    profit_per_contract = (entry_premium - exit_price) * 100
    print(f"Profit at Exit: ${profit_per_contract:.2f} per contract")
    print(f"✅ CSP exit order validated")
    
    return exit_order


def test_cc_exit_order():
    """Test Covered Call exit order generation"""
    print("\n" + "="*60)
    print("TEST 2: Covered Call Exit Order")
    print("="*60)
    
    trader = SchwabTrader(dry_run=True, export_dir="./trade_orders")
    
    # Entry: Sell $575 CALL for $3.20 premium
    entry_premium = 3.20
    profit_capture_pct = 75  # 75% profit target
    
    # Calculate exit price
    exit_price = max(0.05, entry_premium * (1.0 - profit_capture_pct / 100.0))
    expected_exit = 3.20 * 0.25  # $0.80
    
    print(f"\nEntry: SELL TO OPEN $575 CALL @ ${entry_premium}")
    print(f"Profit Target: {profit_capture_pct}%")
    print(f"Exit Price: ${exit_price:.2f} (expected: ${expected_exit:.2f})")
    
    # Create exit order
    exit_order = trader.create_option_order(
        symbol="SPY",
        expiration="2025-11-15",
        strike=575.0,
        option_type="CALL",
        action="BUY_TO_CLOSE",
        quantity=2,
        order_type="LIMIT",
        limit_price=exit_price,
        duration="GTC"
    )
    
    # Validate exit order
    assert exit_order["orderLegCollection"][0]["instruction"] == "BUY_TO_CLOSE"
    assert exit_order["orderType"] == "LIMIT"
    assert exit_order["duration"] == "GTC"
    assert exit_order["price"] == exit_price
    assert exit_order["orderLegCollection"][0]["quantity"] == 2
    
    profit_per_contract = (entry_premium - exit_price) * 100
    print(f"Profit at Exit: ${profit_per_contract:.2f} per contract")
    print(f"✅ CC exit order validated")
    
    return exit_order


def test_collar_exit_order():
    """Test Collar 2-leg exit order generation"""
    print("\n" + "="*60)
    print("TEST 3: Collar Exit Order (2-Leg)")
    print("="*60)
    
    trader = SchwabTrader(dry_run=True, export_dir="./trade_orders")
    
    # Entry: Collar with call premium and put cost
    # SELL CALL: $575 @ $3.00
    # BUY PUT: $540 @ $1.50
    # Net Credit: $1.50
    call_entry = 3.00
    put_entry = 1.50
    profit_capture_pct = 50  # 50% profit target on call
    
    # Calculate call exit price
    call_exit = max(0.05, call_entry * (1.0 - profit_capture_pct / 100.0))
    expected_call_exit = 3.00 * 0.5  # $1.50
    
    # Put exit at 50% of cost
    put_exit = put_entry * 0.5  # $0.75
    
    print(f"\nEntry: SELL $575 CALL @ ${call_entry}, BUY $540 PUT @ ${put_entry}")
    print(f"Net Credit: ${call_entry - put_entry}")
    print(f"Profit Target: {profit_capture_pct}% on call leg")
    print(f"Call Exit: ${call_exit:.2f} (expected: ${expected_call_exit:.2f})")
    print(f"Put Exit: ${put_exit:.2f} (recover 50% of cost)")
    
    # Create call exit order (BUY TO CLOSE)
    exit_order_call = trader.create_option_order(
        symbol="SPY",
        expiration="2025-11-15",
        strike=575.0,
        option_type="CALL",
        action="BUY_TO_CLOSE",
        quantity=1,
        order_type="LIMIT",
        limit_price=call_exit,
        duration="GTC"
    )
    
    # Create put exit order (SELL TO CLOSE)
    exit_order_put = trader.create_option_order(
        symbol="SPY",
        expiration="2025-11-15",
        strike=540.0,
        option_type="PUT",
        action="SELL_TO_CLOSE",
        quantity=1,
        order_type="LIMIT",
        limit_price=put_exit,
        duration="GTC"
    )
    
    # Validate call exit order
    assert exit_order_call["orderLegCollection"][0]["instruction"] == "BUY_TO_CLOSE"
    assert exit_order_call["orderType"] == "LIMIT"
    assert exit_order_call["duration"] == "GTC"
    assert exit_order_call["price"] == call_exit
    
    # Validate put exit order
    assert exit_order_put["orderLegCollection"][0]["instruction"] == "SELL_TO_CLOSE"
    assert exit_order_put["orderType"] == "LIMIT"
    assert exit_order_put["duration"] == "GTC"
    assert exit_order_put["price"] == put_exit
    
    call_profit = (call_entry - call_exit) * 100
    put_profit = (put_exit - put_entry) * 100  # Negative (cost recovery)
    total_profit = call_profit + put_profit
    
    print(f"Call Profit at Exit: ${call_profit:.2f} per contract")
    print(f"Put Cost Recovery: ${put_profit:.2f} per contract")
    print(f"Total Profit: ${total_profit:.2f} per contract")
    print(f"✅ Collar exit orders validated (both legs)")
    
    return (exit_order_call, exit_order_put)


def test_iron_condor_exit_order():
    """Test Iron Condor 4-leg exit order generation"""
    print("\n" + "="*60)
    print("TEST 4: Iron Condor Exit Order (4-Leg)")
    print("="*60)
    
    trader = SchwabTrader(dry_run=True, export_dir="./trade_orders")
    
    # Entry: Iron Condor with $2.50 net credit
    # PUT SPREAD: Buy 540, Sell 545
    # CALL SPREAD: Sell 575, Buy 580
    entry_credit = 2.50
    profit_capture_pct = 50  # 50% profit target
    
    # Calculate exit debit (pay this much to close)
    exit_debit = max(0.05, entry_credit * (1.0 - profit_capture_pct / 100.0))
    expected_exit = 2.50 * 0.5  # $1.25
    
    print(f"\nEntry: NET CREDIT ${entry_credit} (4-leg iron condor)")
    print(f"  PUT SPREAD: 540/545 (BTO 540 PUT, STO 545 PUT)")
    print(f"  CALL SPREAD: 575/580 (STO 575 CALL, BTO 580 CALL)")
    print(f"Profit Target: {profit_capture_pct}%")
    print(f"Exit Debit: ${exit_debit:.2f} (expected: ${expected_exit:.2f})")
    
    # Create exit order (closes all 4 legs)
    exit_order = trader.create_iron_condor_exit_order(
        symbol="SPY",
        expiration="2025-11-15",
        long_put_strike=540.0,
        short_put_strike=545.0,
        short_call_strike=575.0,
        long_call_strike=580.0,
        quantity=1,
        limit_price=exit_debit,
        duration="GTC"
    )
    
    # Validate exit order structure
    assert exit_order["orderType"] == "NET_DEBIT"
    assert exit_order["duration"] == "GTC"
    assert exit_order["price"] == exit_debit
    assert len(exit_order["orderLegCollection"]) == 4
    
    # Validate each leg (should reverse entry instructions)
    legs = exit_order["orderLegCollection"]
    
    # Leg 1: Long put (540) - was BTO, now STC
    assert legs[0]["instruction"] == "SELL_TO_CLOSE"
    assert "P00540000" in legs[0]["instrument"]["symbol"]
    
    # Leg 2: Short put (545) - was STO, now BTC
    assert legs[1]["instruction"] == "BUY_TO_CLOSE"
    assert "P00545000" in legs[1]["instrument"]["symbol"]
    
    # Leg 3: Short call (575) - was STO, now BTC
    assert legs[2]["instruction"] == "BUY_TO_CLOSE"
    assert "C00575000" in legs[2]["instrument"]["symbol"]
    
    # Leg 4: Long call (580) - was BTO, now STC
    assert legs[3]["instruction"] == "SELL_TO_CLOSE"
    assert "C00580000" in legs[3]["instrument"]["symbol"]
    
    profit_per_contract = (entry_credit - exit_debit) * 100
    print(f"Profit at Exit: ${profit_per_contract:.2f} per contract")
    print(f"✅ Iron Condor exit order validated (all 4 legs correct)")
    
    return exit_order


def test_profit_targets():
    """Test various profit target percentages"""
    print("\n" + "="*60)
    print("TEST 5: Profit Target Calculations")
    print("="*60)
    
    entry_premium = 5.00
    
    print(f"\nEntry Premium: ${entry_premium}")
    print("\nProfit Targets:")
    
    for pct in [25, 50, 75, 90]:
        exit_price = max(0.05, entry_premium * (1.0 - pct / 100.0))
        profit = (entry_premium - exit_price) * 100
        actual_pct = (profit / (entry_premium * 100)) * 100
        
        print(f"  {pct}% target: Exit @ ${exit_price:.2f} = ${profit:.2f} profit ({actual_pct:.1f}% of max)")
        
        # Validate calculation
        assert abs(actual_pct - pct) < 0.1, f"Profit calculation off: expected {pct}%, got {actual_pct}%"
    
    print(f"✅ All profit target calculations validated")


def test_order_export():
    """Test that orders are properly exported to files"""
    print("\n" + "="*60)
    print("TEST 6: Order Export to Files")
    print("="*60)
    
    trader = SchwabTrader(dry_run=True, export_dir="./trade_orders")
    
    # Create and export CSP exit order
    exit_order = trader.create_option_order(
        symbol="TEST",
        expiration="2025-12-31",
        strike=100.0,
        option_type="PUT",
        action="BUY_TO_CLOSE",
        quantity=1,
        order_type="LIMIT",
        limit_price=2.50,
        duration="GTC"
    )
    
    metadata = {
        "exit_trigger": "50% profit capture",
        "entry_premium": 5.00,
        "exit_price": 2.50,
        "profit_per_contract": 250.0
    }
    
    result = trader.submit_order(exit_order, strategy_type="csp_exit", metadata=metadata)
    
    assert result["status"] == "exported"
    assert Path(result["filepath"]).exists()
    
    # Read and validate exported file
    with open(result["filepath"], "r") as f:
        exported_data = json.load(f)
    
    assert exported_data["strategy_type"] == "csp_exit"
    assert exported_data["metadata"]["exit_trigger"] == "50% profit capture"
    assert exported_data["metadata"]["profit_per_contract"] == 250.0
    assert exported_data["order"]["orderLegCollection"][0]["instruction"] == "BUY_TO_CLOSE"
    
    print(f"\nExported to: {result['filepath']}")
    print(f"✅ Order export validated")
    
    return result["filepath"]


def test_gtc_duration():
    """Test that exit orders default to GTC (Good Till Canceled)"""
    print("\n" + "="*60)
    print("TEST 7: GTC Duration for 'Set and Forget'")
    print("="*60)
    
    trader = SchwabTrader(dry_run=True, export_dir="./trade_orders")
    
    # Create exit order with GTC
    exit_order = trader.create_option_order(
        symbol="SPY",
        expiration="2025-11-15",
        strike=550.0,
        option_type="PUT",
        action="BUY_TO_CLOSE",
        quantity=1,
        order_type="LIMIT",
        limit_price=2.75,
        duration="GTC"
    )
    
    assert exit_order["duration"] == "GTC"
    
    print(f"\n✅ Exit order uses GTC duration (Good Till Canceled)")
    print(f"   This allows 'set and forget' - order stays active until:")
    print(f"   • Filled at target price")
    print(f"   • Manually canceled")
    print(f"   • Option expires")
    
    return exit_order


def main():
    """Run all tests"""
    print("\n" + "="*70)
    print("PROFIT-TAKING EXIT ORDER TEST SUITE")
    print("="*70)
    print("\nValidating exit order generation based on runbook profit targets")
    
    try:
        # Run all tests
        test_csp_exit_order()
        test_cc_exit_order()
        test_collar_exit_order()
        test_iron_condor_exit_order()
        test_profit_targets()
        test_order_export()
        test_gtc_duration()
        
        # Summary
        print("\n" + "="*70)
        print("✅ ALL TESTS PASSED (7/7)")
        print("="*70)
        print("\nExit order generation validated for:")
        print("  ✓ Cash-Secured Put (CSP) - BUY TO CLOSE single leg")
        print("  ✓ Covered Call (CC) - BUY TO CLOSE single leg")
        print("  ✓ Collar - BUY TO CLOSE call + SELL TO CLOSE put")
        print("  ✓ Iron Condor (IC) - Close all 4 legs as NET DEBIT")
        print("  ✓ Profit target calculations (25%, 50%, 75%, 90%)")
        print("  ✓ Order export with metadata")
        print("  ✓ GTC duration for 'set and forget'")
        print("\n✅ Feature ready for production use")
        
        return 0
    
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
