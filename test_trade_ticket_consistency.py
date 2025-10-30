"""
Test consistency between entry, profit exit, and stop-loss trade tickets.
Validates that all three orders match in symbol, strikes, expiration, quantity, etc.
"""

import sys
import json
from pathlib import Path
from providers.schwab_trading import SchwabTrader


def validate_option_symbol_consistency(entry_symbol, exit_symbol, description=""):
    """Validate that two option symbols match (same underlying, exp, strike, type)"""
    print(f"  Validating {description}...")
    print(f"    Entry: {entry_symbol}")
    print(f"    Exit:  {exit_symbol}")
    
    # Both should be identical for same option
    assert entry_symbol == exit_symbol, f"Symbol mismatch: {entry_symbol} != {exit_symbol}"
    
    print(f"    ✅ Symbols match")


def test_csp_ticket_consistency():
    """Test CSP entry, profit exit, and stop-loss consistency"""
    print("\n" + "="*70)
    print("TEST 1: CSP Trade Ticket Consistency")
    print("="*70)
    
    trader = SchwabTrader(dry_run=True, export_dir="./trade_orders")
    
    # Trade parameters
    symbol = "SPY"
    expiration = "2025-11-15"
    strike = 550.0
    entry_premium = 5.50
    quantity = 2
    profit_target_pct = 50
    risk_multiplier = 2.0
    
    # Calculate exit prices
    profit_exit_price = entry_premium * (1.0 - profit_target_pct / 100.0)  # $2.75
    stop_loss_price = entry_premium * risk_multiplier  # $11.00
    
    print(f"\n📋 Trade Setup:")
    print(f"  Symbol: {symbol}")
    print(f"  Expiration: {expiration}")
    print(f"  Strike: ${strike}")
    print(f"  Quantity: {quantity} contracts")
    print(f"  Entry: SELL @ ${entry_premium}")
    print(f"  Profit Exit: BUY @ ${profit_exit_price} ({profit_target_pct}% target)")
    print(f"  Stop Loss: BUY @ ${stop_loss_price} ({risk_multiplier}x loss)")
    
    # Create all three orders
    entry_order = trader.create_cash_secured_put_order(
        symbol=symbol,
        expiration=expiration,
        strike=strike,
        quantity=quantity,
        limit_price=entry_premium,
        duration="DAY"
    )
    
    profit_exit_order = trader.create_option_order(
        symbol=symbol,
        expiration=expiration,
        strike=strike,
        option_type="PUT",
        action="BUY_TO_CLOSE",
        quantity=quantity,
        order_type="LIMIT",
        limit_price=profit_exit_price,
        duration="GTC"
    )
    
    stop_loss_order = trader.create_option_order(
        symbol=symbol,
        expiration=expiration,
        strike=strike,
        option_type="PUT",
        action="BUY_TO_CLOSE",
        quantity=quantity,
        order_type="LIMIT",
        limit_price=stop_loss_price,
        duration="GTC"
    )
    
    print(f"\n🔍 Consistency Checks:")
    
    # 1. Symbol consistency
    entry_symbol = entry_order["orderLegCollection"][0]["instrument"]["symbol"]
    profit_symbol = profit_exit_order["orderLegCollection"][0]["instrument"]["symbol"]
    stop_symbol = stop_loss_order["orderLegCollection"][0]["instrument"]["symbol"]
    
    validate_option_symbol_consistency(entry_symbol, profit_symbol, "Entry vs Profit Exit")
    validate_option_symbol_consistency(entry_symbol, stop_symbol, "Entry vs Stop Loss")
    
    # 2. Quantity consistency
    print(f"\n  Validating quantities...")
    entry_qty = entry_order["orderLegCollection"][0]["quantity"]
    profit_qty = profit_exit_order["orderLegCollection"][0]["quantity"]
    stop_qty = stop_loss_order["orderLegCollection"][0]["quantity"]
    
    assert entry_qty == quantity, f"Entry quantity mismatch: {entry_qty} != {quantity}"
    assert profit_qty == quantity, f"Profit exit quantity mismatch: {profit_qty} != {quantity}"
    assert stop_qty == quantity, f"Stop loss quantity mismatch: {stop_qty} != {quantity}"
    print(f"    ✅ All quantities = {quantity}")
    
    # 3. Action consistency (entry should be opposite of exits)
    print(f"\n  Validating actions...")
    entry_action = entry_order["orderLegCollection"][0]["instruction"]
    profit_action = profit_exit_order["orderLegCollection"][0]["instruction"]
    stop_action = stop_loss_order["orderLegCollection"][0]["instruction"]
    
    assert entry_action == "SELL_TO_OPEN", f"Entry should be SELL_TO_OPEN: {entry_action}"
    assert profit_action == "BUY_TO_CLOSE", f"Profit exit should be BUY_TO_CLOSE: {profit_action}"
    assert stop_action == "BUY_TO_CLOSE", f"Stop loss should be BUY_TO_CLOSE: {stop_action}"
    print(f"    ✅ Entry: {entry_action}")
    print(f"    ✅ Exits: {profit_action}")
    
    # 4. Price logic validation
    print(f"\n  Validating price logic...")
    entry_price = entry_order["price"]
    profit_price = profit_exit_order["price"]
    stop_price = stop_loss_order["price"]
    
    assert entry_price == entry_premium, f"Entry price mismatch"
    assert profit_price < entry_price, f"Profit exit should be less than entry: {profit_price} >= {entry_price}"
    assert stop_price > entry_price, f"Stop loss should be greater than entry: {stop_price} <= {entry_price}"
    print(f"    ✅ Entry: ${entry_price:.2f} (selling premium)")
    print(f"    ✅ Profit Exit: ${profit_price:.2f} (buying back cheaper)")
    print(f"    ✅ Stop Loss: ${stop_price:.2f} (buying back at loss)")
    
    # 5. P&L validation
    print(f"\n  Validating P&L calculations...")
    max_profit = (entry_price - profit_price) * 100 * quantity
    max_loss = (stop_price - entry_price) * 100 * quantity
    
    expected_profit = entry_premium * profit_target_pct / 100.0 * 100 * quantity
    expected_loss = entry_premium * (risk_multiplier - 1) * 100 * quantity
    
    assert abs(max_profit - expected_profit) < 0.01, f"Profit calculation off"
    assert abs(max_loss - expected_loss) < 0.01, f"Loss calculation off"
    
    print(f"    ✅ Max Profit: ${max_profit:.2f} ({profit_target_pct}% of max)")
    print(f"    ✅ Max Loss: ${max_loss:.2f} ({risk_multiplier}x max profit)")
    print(f"    ✅ Risk/Reward: 1:{max_profit/max_loss:.2f}")
    
    print(f"\n✅ CSP trade tickets are fully consistent")
    
    return (entry_order, profit_exit_order, stop_loss_order)


def test_cc_ticket_consistency():
    """Test Covered Call entry, profit exit, and stop-loss consistency"""
    print("\n" + "="*70)
    print("TEST 2: Covered Call Trade Ticket Consistency")
    print("="*70)
    
    trader = SchwabTrader(dry_run=True, export_dir="./trade_orders")
    
    # Trade parameters
    symbol = "AAPL"
    expiration = "2025-12-19"
    strike = 180.0
    entry_premium = 4.50
    quantity = 3
    profit_target_pct = 75
    risk_multiplier = 2.0
    
    profit_exit_price = entry_premium * (1.0 - profit_target_pct / 100.0)  # $1.125
    stop_loss_price = entry_premium * risk_multiplier  # $9.00
    
    print(f"\n📋 Trade Setup:")
    print(f"  Symbol: {symbol}")
    print(f"  Strike: ${strike}")
    print(f"  Quantity: {quantity} contracts ({quantity * 100} shares)")
    print(f"  Entry: SELL CALL @ ${entry_premium}")
    print(f"  Profit Exit: BUY @ ${profit_exit_price:.2f}")
    print(f"  Stop Loss: BUY @ ${stop_loss_price:.2f}")
    
    # Create orders
    entry_order = trader.create_covered_call_order(
        symbol=symbol,
        expiration=expiration,
        strike=strike,
        quantity=quantity,
        limit_price=entry_premium,
        duration="DAY"
    )
    
    profit_exit_order = trader.create_option_order(
        symbol=symbol,
        expiration=expiration,
        strike=strike,
        option_type="CALL",
        action="BUY_TO_CLOSE",
        quantity=quantity,
        order_type="LIMIT",
        limit_price=profit_exit_price,
        duration="GTC"
    )
    
    stop_loss_order = trader.create_option_order(
        symbol=symbol,
        expiration=expiration,
        strike=strike,
        option_type="CALL",
        action="BUY_TO_CLOSE",
        quantity=quantity,
        order_type="LIMIT",
        limit_price=stop_loss_price,
        duration="GTC"
    )
    
    print(f"\n🔍 Consistency Checks:")
    
    # Validate symbol consistency
    entry_symbol = entry_order["orderLegCollection"][0]["instrument"]["symbol"]
    profit_symbol = profit_exit_order["orderLegCollection"][0]["instrument"]["symbol"]
    stop_symbol = stop_loss_order["orderLegCollection"][0]["instrument"]["symbol"]
    
    validate_option_symbol_consistency(entry_symbol, profit_symbol, "Entry vs Profit Exit")
    validate_option_symbol_consistency(entry_symbol, stop_symbol, "Entry vs Stop Loss")
    
    # Validate quantities
    print(f"\n  Validating quantities...")
    assert entry_order["orderLegCollection"][0]["quantity"] == quantity
    assert profit_exit_order["orderLegCollection"][0]["quantity"] == quantity
    assert stop_loss_order["orderLegCollection"][0]["quantity"] == quantity
    print(f"    ✅ All quantities = {quantity}")
    
    # Validate option type (all should be CALL)
    print(f"\n  Validating option types...")
    assert "C0" in entry_symbol, "Entry should be CALL"
    assert "C0" in profit_symbol, "Profit exit should be CALL"
    assert "C0" in stop_symbol, "Stop loss should be CALL"
    print(f"    ✅ All are CALL options")
    
    print(f"\n✅ CC trade tickets are fully consistent")
    
    return (entry_order, profit_exit_order, stop_loss_order)


def test_iron_condor_ticket_consistency():
    """Test Iron Condor entry, profit exit, and stop-loss consistency"""
    print("\n" + "="*70)
    print("TEST 3: Iron Condor Trade Ticket Consistency (4-Leg)")
    print("="*70)
    
    trader = SchwabTrader(dry_run=True, export_dir="./trade_orders")
    
    # Trade parameters
    symbol = "SPY"
    expiration = "2025-11-21"
    long_put = 540.0
    short_put = 545.0
    short_call = 575.0
    long_call = 580.0
    entry_credit = 2.50
    quantity = 1
    profit_target_pct = 50
    risk_multiplier = 2.0
    
    profit_exit_debit = entry_credit * (1.0 - profit_target_pct / 100.0)  # $1.25
    stop_loss_debit = entry_credit * risk_multiplier  # $5.00
    
    print(f"\n📋 Trade Setup:")
    print(f"  Symbol: {symbol}")
    print(f"  Put Spread: ${long_put}/${short_put}")
    print(f"  Call Spread: ${short_call}/${long_call}")
    print(f"  Entry: NET CREDIT ${entry_credit}")
    print(f"  Profit Exit: NET DEBIT ${profit_exit_debit}")
    print(f"  Stop Loss: NET DEBIT ${stop_loss_debit}")
    
    # Create orders
    entry_order = trader.create_iron_condor_order(
        symbol=symbol,
        expiration=expiration,
        long_put_strike=long_put,
        short_put_strike=short_put,
        short_call_strike=short_call,
        long_call_strike=long_call,
        quantity=quantity,
        limit_price=entry_credit,
        duration="DAY"
    )
    
    profit_exit_order = trader.create_iron_condor_exit_order(
        symbol=symbol,
        expiration=expiration,
        long_put_strike=long_put,
        short_put_strike=short_put,
        short_call_strike=short_call,
        long_call_strike=long_call,
        quantity=quantity,
        limit_price=profit_exit_debit,
        duration="GTC"
    )
    
    stop_loss_order = trader.create_iron_condor_exit_order(
        symbol=symbol,
        expiration=expiration,
        long_put_strike=long_put,
        short_put_strike=short_put,
        short_call_strike=short_call,
        long_call_strike=long_call,
        quantity=quantity,
        limit_price=stop_loss_debit,
        duration="GTC"
    )
    
    print(f"\n🔍 Consistency Checks:")
    
    # Validate leg count
    print(f"\n  Validating leg counts...")
    assert len(entry_order["orderLegCollection"]) == 4, "Entry should have 4 legs"
    assert len(profit_exit_order["orderLegCollection"]) == 4, "Profit exit should have 4 legs"
    assert len(stop_loss_order["orderLegCollection"]) == 4, "Stop loss should have 4 legs"
    print(f"    ✅ All orders have 4 legs")
    
    # Validate all leg symbols match
    print(f"\n  Validating leg symbols...")
    entry_legs = entry_order["orderLegCollection"]
    profit_legs = profit_exit_order["orderLegCollection"]
    stop_legs = stop_loss_order["orderLegCollection"]
    
    for i, leg_name in enumerate(["Long Put", "Short Put", "Short Call", "Long Call"]):
        entry_sym = entry_legs[i]["instrument"]["symbol"]
        profit_sym = profit_legs[i]["instrument"]["symbol"]
        stop_sym = stop_legs[i]["instrument"]["symbol"]
        
        print(f"    {leg_name}:")
        print(f"      Entry:  {entry_sym}")
        print(f"      Profit: {profit_sym}")
        print(f"      Stop:   {stop_sym}")
        
        assert entry_sym == profit_sym, f"{leg_name} symbol mismatch (entry vs profit)"
        assert entry_sym == stop_sym, f"{leg_name} symbol mismatch (entry vs stop)"
        print(f"      ✅ Match")
    
    # Validate actions are reversed for exits
    print(f"\n  Validating leg actions...")
    entry_actions = [leg["instruction"] for leg in entry_legs]
    profit_actions = [leg["instruction"] for leg in profit_legs]
    stop_actions = [leg["instruction"] for leg in stop_legs]
    
    expected_entry = ["BUY_TO_OPEN", "SELL_TO_OPEN", "SELL_TO_OPEN", "BUY_TO_OPEN"]
    expected_exit = ["SELL_TO_CLOSE", "BUY_TO_CLOSE", "BUY_TO_CLOSE", "SELL_TO_CLOSE"]
    
    assert entry_actions == expected_entry, f"Entry actions incorrect: {entry_actions}"
    assert profit_actions == expected_exit, f"Profit exit actions incorrect: {profit_actions}"
    assert stop_actions == expected_exit, f"Stop loss actions incorrect: {stop_actions}"
    print(f"    ✅ Entry actions: {entry_actions}")
    print(f"    ✅ Exit actions: {profit_actions}")
    
    # Validate order types
    print(f"\n  Validating order types...")
    assert entry_order["orderType"] == "NET_CREDIT", "Entry should be NET_CREDIT"
    assert profit_exit_order["orderType"] == "NET_DEBIT", "Profit exit should be NET_DEBIT"
    assert stop_loss_order["orderType"] == "NET_DEBIT", "Stop loss should be NET_DEBIT"
    print(f"    ✅ Entry: NET_CREDIT")
    print(f"    ✅ Exits: NET_DEBIT")
    
    # Validate price logic
    print(f"\n  Validating price logic...")
    entry_price = entry_order["price"]
    profit_price = profit_exit_order["price"]
    stop_price = stop_loss_order["price"]
    
    assert profit_price < entry_price, f"Profit exit debit should be less than entry credit"
    assert stop_price > entry_price, f"Stop loss debit should be greater than entry credit"
    print(f"    ✅ Entry Credit: ${entry_price:.2f}")
    print(f"    ✅ Profit Debit: ${profit_price:.2f} (paying less to close)")
    print(f"    ✅ Stop Debit: ${stop_price:.2f} (paying more to close)")
    
    # Validate P&L
    print(f"\n  Validating P&L calculations...")
    max_profit = (entry_price - profit_price) * 100
    max_loss = (stop_price - entry_price) * 100
    
    print(f"    ✅ Max Profit: ${max_profit:.2f}")
    print(f"    ✅ Max Loss: ${max_loss:.2f}")
    print(f"    ✅ Risk/Reward: 1:{max_profit/max_loss:.2f}")
    
    print(f"\n✅ Iron Condor trade tickets are fully consistent (all 4 legs)")
    
    return (entry_order, profit_exit_order, stop_loss_order)


def test_collar_ticket_consistency():
    """Test Collar entry, profit exit, and stop-loss consistency"""
    print("\n" + "="*70)
    print("TEST 4: Collar Trade Ticket Consistency (2-Leg)")
    print("="*70)
    
    trader = SchwabTrader(dry_run=True, export_dir="./trade_orders")
    
    # Trade parameters
    symbol = "TSLA"
    expiration = "2025-12-05"
    call_strike = 250.0
    put_strike = 220.0
    call_premium = 5.00
    put_cost = 3.00
    net_credit = call_premium - put_cost
    quantity = 1
    
    print(f"\n📋 Trade Setup:")
    print(f"  Symbol: {symbol}")
    print(f"  Call Strike: ${call_strike}")
    print(f"  Put Strike: ${put_strike}")
    print(f"  Call Premium: ${call_premium} (sell)")
    print(f"  Put Cost: ${put_cost} (buy)")
    print(f"  Net Credit: ${net_credit}")
    
    # Create entry order (collar)
    entry_order = trader.create_collar_order(
        symbol=symbol,
        expiration=expiration,
        call_strike=call_strike,
        put_strike=put_strike,
        quantity=quantity,
        limit_price=net_credit,
        duration="DAY"
    )
    
    # Create exit orders (close both legs)
    call_exit_price = call_premium * 0.5  # 50% profit on call
    put_exit_price = put_cost * 0.5  # Recover 50% of put cost
    
    call_exit_order = trader.create_option_order(
        symbol=symbol,
        expiration=expiration,
        strike=call_strike,
        option_type="CALL",
        action="BUY_TO_CLOSE",
        quantity=quantity,
        order_type="LIMIT",
        limit_price=call_exit_price,
        duration="GTC"
    )
    
    put_exit_order = trader.create_option_order(
        symbol=symbol,
        expiration=expiration,
        strike=put_strike,
        option_type="PUT",
        action="SELL_TO_CLOSE",
        quantity=quantity,
        order_type="LIMIT",
        limit_price=put_exit_price,
        duration="GTC"
    )
    
    # Create stop-loss for call (if it doubles)
    call_stop_loss = call_premium * 2.0
    
    call_stop_order = trader.create_option_order(
        symbol=symbol,
        expiration=expiration,
        strike=call_strike,
        option_type="CALL",
        action="BUY_TO_CLOSE",
        quantity=quantity,
        order_type="LIMIT",
        limit_price=call_stop_loss,
        duration="GTC"
    )
    
    print(f"\n🔍 Consistency Checks:")
    
    # Validate leg count
    print(f"\n  Validating leg counts...")
    assert len(entry_order["orderLegCollection"]) == 2, "Entry should have 2 legs"
    print(f"    ✅ Entry has 2 legs (call + put)")
    
    # Extract symbols
    entry_legs = entry_order["orderLegCollection"]
    entry_call_sym = entry_legs[0]["instrument"]["symbol"]
    entry_put_sym = entry_legs[1]["instrument"]["symbol"]
    
    exit_call_sym = call_exit_order["orderLegCollection"][0]["instrument"]["symbol"]
    exit_put_sym = put_exit_order["orderLegCollection"][0]["instrument"]["symbol"]
    stop_call_sym = call_stop_order["orderLegCollection"][0]["instrument"]["symbol"]
    
    # Validate call leg consistency
    print(f"\n  Validating call leg...")
    print(f"    Entry: {entry_call_sym}")
    print(f"    Exit:  {exit_call_sym}")
    print(f"    Stop:  {stop_call_sym}")
    assert entry_call_sym == exit_call_sym, "Call exit symbol mismatch"
    assert entry_call_sym == stop_call_sym, "Call stop symbol mismatch"
    assert "C0" in entry_call_sym, "Should be CALL option"
    print(f"    ✅ Call leg consistent")
    
    # Validate put leg consistency
    print(f"\n  Validating put leg...")
    print(f"    Entry: {entry_put_sym}")
    print(f"    Exit:  {exit_put_sym}")
    assert entry_put_sym == exit_put_sym, "Put exit symbol mismatch"
    assert "P0" in entry_put_sym, "Should be PUT option"
    print(f"    ✅ Put leg consistent")
    
    # Validate actions
    print(f"\n  Validating actions...")
    entry_call_action = entry_legs[0]["instruction"]
    entry_put_action = entry_legs[1]["instruction"]
    
    assert entry_call_action == "SELL_TO_OPEN", "Call should be SELL_TO_OPEN"
    assert entry_put_action == "BUY_TO_OPEN", "Put should be BUY_TO_OPEN"
    assert call_exit_order["orderLegCollection"][0]["instruction"] == "BUY_TO_CLOSE"
    assert put_exit_order["orderLegCollection"][0]["instruction"] == "SELL_TO_CLOSE"
    assert call_stop_order["orderLegCollection"][0]["instruction"] == "BUY_TO_CLOSE"
    
    print(f"    ✅ Entry: SELL call, BUY put")
    print(f"    ✅ Exit: BUY call, SELL put")
    print(f"    ✅ Stop: BUY call")
    
    print(f"\n✅ Collar trade tickets are fully consistent (2 legs + stop)")
    
    return (entry_order, call_exit_order, put_exit_order, call_stop_order)


def test_quantity_scaling():
    """Test that all orders scale correctly with quantity changes"""
    print("\n" + "="*70)
    print("TEST 5: Quantity Scaling Consistency")
    print("="*70)
    
    trader = SchwabTrader(dry_run=True, export_dir="./trade_orders")
    
    quantities = [1, 2, 5, 10]
    
    print(f"\nTesting CSP orders with varying quantities...")
    
    for qty in quantities:
        print(f"\n  Quantity: {qty} contracts")
        
        entry = trader.create_cash_secured_put_order(
            symbol="SPY",
            expiration="2025-11-15",
            strike=550.0,
            quantity=qty,
            limit_price=5.50,
            duration="DAY"
        )
        
        profit_exit = trader.create_option_order(
            symbol="SPY",
            expiration="2025-11-15",
            strike=550.0,
            option_type="PUT",
            action="BUY_TO_CLOSE",
            quantity=qty,
            order_type="LIMIT",
            limit_price=2.75,
            duration="GTC"
        )
        
        stop_loss = trader.create_option_order(
            symbol="SPY",
            expiration="2025-11-15",
            strike=550.0,
            option_type="PUT",
            action="BUY_TO_CLOSE",
            quantity=qty,
            order_type="LIMIT",
            limit_price=11.00,
            duration="GTC"
        )
        
        # Validate all quantities match
        entry_qty = entry["orderLegCollection"][0]["quantity"]
        profit_qty = profit_exit["orderLegCollection"][0]["quantity"]
        stop_qty = stop_loss["orderLegCollection"][0]["quantity"]
        
        assert entry_qty == qty, f"Entry quantity mismatch"
        assert profit_qty == qty, f"Profit exit quantity mismatch"
        assert stop_qty == qty, f"Stop loss quantity mismatch"
        
        print(f"    ✅ All orders have quantity {qty}")
    
    print(f"\n✅ Quantity scaling is consistent across all order types")


def test_duration_consistency():
    """Test that durations are set correctly (DAY for entry, GTC for exits)"""
    print("\n" + "="*70)
    print("TEST 6: Duration Settings Consistency")
    print("="*70)
    
    trader = SchwabTrader(dry_run=True, export_dir="./trade_orders")
    
    print(f"\nCreating CSP orders with different durations...")
    
    # Entry should use DAY (or whatever user specifies)
    entry = trader.create_cash_secured_put_order(
        symbol="SPY",
        expiration="2025-11-15",
        strike=550.0,
        quantity=1,
        limit_price=5.50,
        duration="DAY"
    )
    
    # Exits should always use GTC for "set and forget"
    profit_exit = trader.create_option_order(
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
    
    stop_loss = trader.create_option_order(
        symbol="SPY",
        expiration="2025-11-15",
        strike=550.0,
        option_type="PUT",
        action="BUY_TO_CLOSE",
        quantity=1,
        order_type="LIMIT",
        limit_price=11.00,
        duration="GTC"
    )
    
    print(f"\n  Entry Duration: {entry['duration']}")
    assert entry["duration"] == "DAY", "Entry should be DAY"
    print(f"    ✅ Entry uses DAY (executes today or expires)")
    
    print(f"\n  Profit Exit Duration: {profit_exit['duration']}")
    assert profit_exit["duration"] == "GTC", "Profit exit should be GTC"
    print(f"    ✅ Profit exit uses GTC (stays active)")
    
    print(f"\n  Stop Loss Duration: {stop_loss['duration']}")
    assert stop_loss["duration"] == "GTC", "Stop loss should be GTC"
    print(f"    ✅ Stop loss uses GTC (stays active)")
    
    print(f"\n✅ Duration settings are correct for 'set and forget' workflow")


def main():
    """Run all consistency tests"""
    print("\n" + "="*70)
    print("TRADE TICKET CONSISTENCY TEST SUITE")
    print("="*70)
    print("\nValidating that entry, profit exit, and stop-loss orders are")
    print("consistent in symbols, strikes, quantities, actions, and prices")
    
    try:
        # Run all tests
        test_csp_ticket_consistency()
        test_cc_ticket_consistency()
        test_iron_condor_ticket_consistency()
        test_collar_ticket_consistency()
        test_quantity_scaling()
        test_duration_consistency()
        
        # Summary
        print("\n" + "="*70)
        print("✅ ALL CONSISTENCY TESTS PASSED (6/6)")
        print("="*70)
        print("\nTrade ticket consistency validated for:")
        print("  ✓ CSP - Entry, profit exit, stop-loss all match")
        print("  ✓ CC - Entry, profit exit, stop-loss all match")
        print("  ✓ Iron Condor - All 4 legs match across 3 orders")
        print("  ✓ Collar - 2 legs + stop-loss all match")
        print("  ✓ Quantity scaling - All orders scale correctly")
        print("  ✓ Duration settings - DAY for entry, GTC for exits")
        print("\n🎯 Trade tickets are production-ready and internally consistent")
        
        return 0
    
    except AssertionError as e:
        print(f"\n❌ CONSISTENCY TEST FAILED: {e}")
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
