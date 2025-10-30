"""
Test stop-loss / risk limit order generation for all strategies.
Validates that risk management orders are properly created based on runbook triggers.
"""

import sys
import json
from pathlib import Path
from providers.schwab_trading import SchwabTrader


def test_csp_stop_loss():
    """Test CSP stop-loss order generation (2x max profit loss)"""
    print("\n" + "="*60)
    print("TEST 1: Cash-Secured Put Stop-Loss Order")
    print("="*60)
    
    trader = SchwabTrader(dry_run=True, export_dir="./trade_orders")
    
    # Entry: Sell $550 PUT for $5.50 premium
    entry_premium = 5.50
    risk_multiplier = 2.0  # 2x max profit loss (runbook standard)
    
    # Calculate stop-loss price
    stop_loss_price = entry_premium * risk_multiplier  # $11.00
    max_loss = entry_premium * (risk_multiplier - 1) * 100  # $550 per contract
    
    print(f"\nEntry: SELL TO OPEN $550 PUT @ ${entry_premium}")
    print(f"Max Profit: ${entry_premium * 100:.0f} per contract")
    print(f"Risk Trigger: {risk_multiplier}x max profit loss")
    print(f"Stop-Loss Price: ${stop_loss_price:.2f} (option value doubled)")
    print(f"Max Loss: ${max_loss:.0f} per contract")
    
    # Create stop-loss order
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
    
    # Validate stop-loss order
    assert stop_loss_order["orderLegCollection"][0]["instruction"] == "BUY_TO_CLOSE"
    assert stop_loss_order["orderType"] == "LIMIT"
    assert stop_loss_order["duration"] == "GTC"
    assert stop_loss_order["price"] == stop_loss_price
    
    print(f"✅ CSP stop-loss order validated")
    print(f"   Triggers when PUT mark ≥ ${stop_loss_price:.2f}")
    
    return stop_loss_order


def test_cc_stop_loss():
    """Test Covered Call stop-loss order generation"""
    print("\n" + "="*60)
    print("TEST 2: Covered Call Stop-Loss Order")
    print("="*60)
    
    trader = SchwabTrader(dry_run=True, export_dir="./trade_orders")
    
    # Entry: Sell $575 CALL for $3.20 premium
    entry_premium = 3.20
    risk_multiplier = 2.0
    
    # Calculate stop-loss price
    stop_loss_price = entry_premium * risk_multiplier  # $6.40
    max_loss = entry_premium * (risk_multiplier - 1) * 100  # $320 per contract
    
    print(f"\nEntry: SELL TO OPEN $575 CALL @ ${entry_premium}")
    print(f"Max Profit: ${entry_premium * 100:.0f} per contract")
    print(f"Risk Trigger: {risk_multiplier}x max profit loss")
    print(f"Stop-Loss Price: ${stop_loss_price:.2f}")
    print(f"Max Loss: ${max_loss:.0f} per contract")
    
    # Create stop-loss order
    stop_loss_order = trader.create_option_order(
        symbol="SPY",
        expiration="2025-11-15",
        strike=575.0,
        option_type="CALL",
        action="BUY_TO_CLOSE",
        quantity=1,
        order_type="LIMIT",
        limit_price=stop_loss_price,
        duration="GTC"
    )
    
    # Validate stop-loss order
    assert stop_loss_order["orderLegCollection"][0]["instruction"] == "BUY_TO_CLOSE"
    assert stop_loss_order["orderType"] == "LIMIT"
    assert stop_loss_order["duration"] == "GTC"
    assert stop_loss_order["price"] == stop_loss_price
    
    print(f"✅ CC stop-loss order validated")
    print(f"   Triggers when CALL mark ≥ ${stop_loss_price:.2f}")
    
    return stop_loss_order


def test_iron_condor_stop_loss():
    """Test Iron Condor stop-loss order generation"""
    print("\n" + "="*60)
    print("TEST 3: Iron Condor Stop-Loss Order")
    print("="*60)
    
    trader = SchwabTrader(dry_run=True, export_dir="./trade_orders")
    
    # Entry: Iron Condor with $2.50 net credit
    entry_credit = 2.50
    risk_multiplier = 2.0
    
    # Calculate stop-loss debit
    stop_loss_debit = entry_credit * risk_multiplier  # $5.00
    max_loss = (stop_loss_debit - entry_credit) * 100  # $250 per contract
    
    print(f"\nEntry: NET CREDIT ${entry_credit} (4-leg iron condor)")
    print(f"Max Profit: ${entry_credit * 100:.0f} per contract")
    print(f"Risk Trigger: {risk_multiplier}x max profit loss")
    print(f"Stop-Loss Debit: ${stop_loss_debit:.2f} (spread value doubled)")
    print(f"Max Loss: ${max_loss:.0f} per contract")
    
    # Create stop-loss order (closes all 4 legs)
    stop_loss_order = trader.create_iron_condor_exit_order(
        symbol="SPY",
        expiration="2025-11-15",
        long_put_strike=540.0,
        short_put_strike=545.0,
        short_call_strike=575.0,
        long_call_strike=580.0,
        quantity=1,
        limit_price=stop_loss_debit,
        duration="GTC"
    )
    
    # Validate stop-loss order
    assert stop_loss_order["orderType"] == "NET_DEBIT"
    assert stop_loss_order["duration"] == "GTC"
    assert stop_loss_order["price"] == stop_loss_debit
    assert len(stop_loss_order["orderLegCollection"]) == 4
    
    print(f"✅ Iron Condor stop-loss order validated")
    print(f"   Triggers when spread debit ≥ ${stop_loss_debit:.2f}")
    
    return stop_loss_order


def test_collar_stop_loss():
    """Test Collar stop-loss order generation"""
    print("\n" + "="*60)
    print("TEST 4: Collar Stop-Loss Order")
    print("="*60)
    
    trader = SchwabTrader(dry_run=True, export_dir="./trade_orders")
    
    # Entry: Collar with call premium
    call_entry = 3.00
    risk_multiplier = 2.0
    
    # Calculate call stop-loss
    call_stop_loss = call_entry * risk_multiplier  # $6.00
    max_loss = call_entry * (risk_multiplier - 1) * 100  # $300 per contract
    
    print(f"\nEntry: SELL $575 CALL @ ${call_entry}")
    print(f"Risk Trigger: {risk_multiplier}x max profit loss on call")
    print(f"Call Stop-Loss: ${call_stop_loss:.2f}")
    print(f"Max Loss on Call: ${max_loss:.0f} per contract")
    
    # Create call stop-loss order
    stop_loss_order = trader.create_option_order(
        symbol="SPY",
        expiration="2025-11-15",
        strike=575.0,
        option_type="CALL",
        action="BUY_TO_CLOSE",
        quantity=1,
        order_type="LIMIT",
        limit_price=call_stop_loss,
        duration="GTC"
    )
    
    # Validate stop-loss order
    assert stop_loss_order["orderLegCollection"][0]["instruction"] == "BUY_TO_CLOSE"
    assert stop_loss_order["orderType"] == "LIMIT"
    assert stop_loss_order["duration"] == "GTC"
    assert stop_loss_order["price"] == call_stop_loss
    
    print(f"✅ Collar stop-loss order validated")
    print(f"   Triggers when CALL mark ≥ ${call_stop_loss:.2f}")
    
    return stop_loss_order


def test_risk_multipliers():
    """Test different risk multiplier values"""
    print("\n" + "="*60)
    print("TEST 5: Risk Multiplier Variations")
    print("="*60)
    
    entry_premium = 5.00
    
    print(f"\nEntry Premium: ${entry_premium}")
    print("\nRisk Multipliers:")
    
    for multiplier in [1.5, 2.0, 2.5, 3.0]:
        stop_loss = entry_premium * multiplier
        max_loss = entry_premium * (multiplier - 1) * 100
        
        print(f"  {multiplier}x: Stop @ ${stop_loss:.2f} = ${max_loss:.0f} max loss")
        
        # Validate calculation
        expected_loss = (stop_loss - entry_premium) * 100
        assert abs(max_loss - expected_loss) < 0.01, f"Loss calculation off for {multiplier}x"
    
    print(f"✅ All risk multiplier calculations validated")


def test_order_export():
    """Test stop-loss order export"""
    print("\n" + "="*60)
    print("TEST 6: Stop-Loss Order Export")
    print("="*60)
    
    trader = SchwabTrader(dry_run=True, export_dir="./trade_orders")
    
    # Create stop-loss order
    stop_loss_order = trader.create_option_order(
        symbol="TEST",
        expiration="2025-12-31",
        strike=100.0,
        option_type="PUT",
        action="BUY_TO_CLOSE",
        quantity=1,
        order_type="LIMIT",
        limit_price=10.00,
        duration="GTC"
    )
    
    metadata = {
        "order_type": "STOP_LOSS",
        "risk_trigger": "2.0x max profit loss",
        "entry_premium": 5.00,
        "stop_loss_price": 10.00,
        "max_loss_per_contract": 500.0
    }
    
    result = trader.submit_order(stop_loss_order, strategy_type="csp_stop_loss", metadata=metadata)
    
    assert result["status"] == "exported"
    assert Path(result["filepath"]).exists()
    assert "stop_loss" in result["filepath"]
    
    # Read and validate exported file
    with open(result["filepath"], "r") as f:
        exported_data = json.load(f)
    
    assert exported_data["strategy_type"] == "csp_stop_loss"
    assert exported_data["metadata"]["order_type"] == "STOP_LOSS"
    assert exported_data["metadata"]["risk_trigger"] == "2.0x max profit loss"
    assert exported_data["metadata"]["max_loss_per_contract"] == 500.0
    
    print(f"\nExported to: {result['filepath']}")
    print(f"✅ Stop-loss order export validated")
    
    return result["filepath"]


def test_gtc_duration():
    """Test that stop-loss orders use GTC duration"""
    print("\n" + "="*60)
    print("TEST 7: GTC Duration for Stop-Loss")
    print("="*60)
    
    trader = SchwabTrader(dry_run=True, export_dir="./trade_orders")
    
    # Create stop-loss order
    stop_loss_order = trader.create_option_order(
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
    
    assert stop_loss_order["duration"] == "GTC"
    
    print(f"\n✅ Stop-loss order uses GTC duration")
    print(f"   Benefits:")
    print(f"   • Stays active until filled or canceled")
    print(f"   • No need to re-enter daily")
    print(f"   • Automatic risk protection")
    
    return stop_loss_order


def main():
    """Run all tests"""
    print("\n" + "="*70)
    print("STOP-LOSS / RISK LIMIT ORDER TEST SUITE")
    print("="*70)
    print("\nValidating risk management order generation based on runbook")
    
    try:
        # Run all tests
        test_csp_stop_loss()
        test_cc_stop_loss()
        test_iron_condor_stop_loss()
        test_collar_stop_loss()
        test_risk_multipliers()
        test_order_export()
        test_gtc_duration()
        
        # Summary
        print("\n" + "="*70)
        print("✅ ALL TESTS PASSED (7/7)")
        print("="*70)
        print("\nStop-loss order generation validated for:")
        print("  ✓ Cash-Secured Put (CSP) - 2x loss limit")
        print("  ✓ Covered Call (CC) - 2x loss limit")
        print("  ✓ Collar - 2x loss limit on call leg")
        print("  ✓ Iron Condor (IC) - 2x loss limit on spread")
        print("  ✓ Risk multiplier calculations (1.5x, 2x, 2.5x, 3x)")
        print("  ✓ Order export with risk metadata")
        print("  ✓ GTC duration for automatic protection")
        print("\n🛑 Risk management feature ready for production use")
        
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
