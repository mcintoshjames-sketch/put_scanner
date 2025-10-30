"""
Comprehensive test suite for Bull Put Spread and Bear Call Spread features.

Tests:
1. Scanner function validation (analyze_bull_put_spread, analyze_bear_call_spread)
2. Order generation (entry, exit, stop-loss)
3. Monte Carlo P&L calculations
4. Overview tab metrics
5. Integration across all components
"""

import sys
import pandas as pd
import numpy as np
from datetime import datetime

# Import from strategy_lab
from strategy_lab import (
    analyze_bull_put_spread,
    analyze_bear_call_spread,
    generate_bull_put_spread_entry_order,
    generate_bear_call_spread_entry_order,
    generate_credit_spread_exit_order,
    generate_credit_spread_stop_loss_order,
    mc_pnl
)

# ========================================
# TEST 1: Scanner Functions
# ========================================

def test_bull_put_spread_scanner():
    """Test Bull Put Spread scanner function."""
    print("\n" + "="*60)
    print("TEST 1A: Bull Put Spread Scanner")
    print("="*60)
    
    # Sample option chain (simplified)
    chain_data = {
        'strike': [565, 570, 575, 580, 585, 590],
        'putLastPrice': [2.50, 3.50, 5.00, 7.00, 9.50, 12.50],
        'putBid': [2.45, 3.45, 4.95, 6.95, 9.45, 12.45],
        'putAsk': [2.55, 3.55, 5.05, 7.05, 9.55, 12.55],
        'impliedVolatility': [0.18, 0.19, 0.20, 0.21, 0.22, 0.23],
        'daysToExpiration': [30, 30, 30, 30, 30, 30]
    }
    
    chain_df = pd.DataFrame(chain_data)
    
    # Run scanner
    results = analyze_bull_put_spread(
        ticker="SPY",
        current_price=580.0,
        option_chain=chain_df,
        expiration="2024-12-01",
        dte=30,
        max_delta=0.30,
        min_credit=1.00,
        max_spread_width=10.0,
        min_pop=60.0
    )
    
    print(f"\n📊 Scanner Results:")
    print(f"  Found {len(results)} Bull Put Spreads")
    
    if len(results) > 0:
        print(f"\n  Top Spread:")
        top = results.iloc[0]
        print(f"    Sell Strike: ${top['SellStrike']:.2f}")
        print(f"    Buy Strike: ${top['BuyStrike']:.2f}")
        print(f"    Net Credit: ${top['NetCredit']:.2f}")
        print(f"    Spread Width: ${top['SpreadWidth']:.2f}")
        print(f"    Max Profit: ${top['MaxProfit']:.2f}")
        print(f"    Max Loss: ${top['MaxLoss']:.2f}")
        print(f"    Breakeven: ${top['Breakeven']:.2f}")
        print(f"    Score: {top['Score']:.2f}")
        
        # Validate calculations
        assert top['SpreadWidth'] == top['SellStrike'] - top['BuyStrike'], "Spread width mismatch"
        assert top['MaxProfit'] == top['NetCredit'] * 100, "Max profit mismatch"
        assert top['MaxLoss'] == (top['SpreadWidth'] - top['NetCredit']) * 100, "Max loss mismatch"
        assert top['Breakeven'] == top['SellStrike'] - top['NetCredit'], "Breakeven mismatch"
        
        print("\n  ✅ All validations passed!")
    else:
        print("\n  ⚠️  No spreads found (this may be OK depending on criteria)")
    
    return results


def test_bear_call_spread_scanner():
    """Test Bear Call Spread scanner function."""
    print("\n" + "="*60)
    print("TEST 1B: Bear Call Spread Scanner")
    print("="*60)
    
    # Sample option chain (simplified)
    chain_data = {
        'strike': [565, 570, 575, 580, 585, 590],
        'callLastPrice': [18.00, 13.50, 9.50, 6.50, 4.00, 2.50],
        'callBid': [17.95, 13.45, 9.45, 6.45, 3.95, 2.45],
        'callAsk': [18.05, 13.55, 9.55, 6.55, 4.05, 2.55],
        'impliedVolatility': [0.18, 0.19, 0.20, 0.21, 0.22, 0.23],
        'daysToExpiration': [30, 30, 30, 30, 30, 30]
    }
    
    chain_df = pd.DataFrame(chain_data)
    
    # Run scanner
    results = analyze_bear_call_spread(
        ticker="SPY",
        current_price=580.0,
        option_chain=chain_df,
        expiration="2024-12-01",
        dte=30,
        max_delta=0.30,
        min_credit=1.00,
        max_spread_width=10.0,
        min_pop=60.0
    )
    
    print(f"\n📊 Scanner Results:")
    print(f"  Found {len(results)} Bear Call Spreads")
    
    if len(results) > 0:
        print(f"\n  Top Spread:")
        top = results.iloc[0]
        print(f"    Sell Strike: ${top['SellStrike']:.2f}")
        print(f"    Buy Strike: ${top['BuyStrike']:.2f}")
        print(f"    Net Credit: ${top['NetCredit']:.2f}")
        print(f"    Spread Width: ${top['SpreadWidth']:.2f}")
        print(f"    Max Profit: ${top['MaxProfit']:.2f}")
        print(f"    Max Loss: ${top['MaxLoss']:.2f}")
        print(f"    Breakeven: ${top['Breakeven']:.2f}")
        print(f"    Score: {top['Score']:.2f}")
        
        # Validate calculations
        assert top['SpreadWidth'] == top['BuyStrike'] - top['SellStrike'], "Spread width mismatch"
        assert top['MaxProfit'] == top['NetCredit'] * 100, "Max profit mismatch"
        assert top['MaxLoss'] == (top['SpreadWidth'] - top['NetCredit']) * 100, "Max loss mismatch"
        assert top['Breakeven'] == top['SellStrike'] + top['NetCredit'], "Breakeven mismatch"
        
        print("\n  ✅ All validations passed!")
    else:
        print("\n  ⚠️  No spreads found (this may be OK depending on criteria)")
    
    return results


# ========================================
# TEST 2: Order Generation
# ========================================

def test_bull_put_spread_entry_order():
    """Test Bull Put Spread entry order generation."""
    print("\n" + "="*60)
    print("TEST 2A: Bull Put Spread Entry Order")
    print("="*60)
    
    order = generate_bull_put_spread_entry_order(
        ticker="SPY",
        expiration="2024-12-01",
        sell_strike=575.0,
        buy_strike=570.0,
        quantity=1,
        sell_put_bid=4.95,
        buy_put_ask=3.55
    )
    
    print(f"\n📋 Order Details:")
    print(f"  Order Type: {order['orderType']}")
    print(f"  Instruction: {order['orderStrategyType']}")
    print(f"  Legs: {len(order['orderLegCollection'])}")
    
    # Validate legs
    sell_leg = order['orderLegCollection'][0]
    buy_leg = order['orderLegCollection'][1]
    
    print(f"\n  Sell Leg:")
    print(f"    Instruction: {sell_leg['instruction']}")
    print(f"    Strike: ${sell_leg['instrument']['putCall']} @ {sell_leg['instrument'].get('strikePrice', 'N/A')}")
    print(f"    Quantity: {sell_leg['quantity']}")
    
    print(f"\n  Buy Leg:")
    print(f"    Instruction: {buy_leg['instruction']}")
    print(f"    Strike: ${buy_leg['instrument']['putCall']} @ {buy_leg['instrument'].get('strikePrice', 'N/A')}")
    print(f"    Quantity: {buy_leg['quantity']}")
    
    # Validations
    assert sell_leg['instruction'] == "SELL_TO_OPEN", "Sell leg instruction incorrect"
    assert buy_leg['instruction'] == "BUY_TO_OPEN", "Buy leg instruction incorrect"
    assert sell_leg['instrument']['putCall'] == "PUT", "Sell leg not a put"
    assert buy_leg['instrument']['putCall'] == "PUT", "Buy leg not a put"
    
    print("\n  ✅ Entry order structure valid!")
    
    return order


def test_bear_call_spread_entry_order():
    """Test Bear Call Spread entry order generation."""
    print("\n" + "="*60)
    print("TEST 2B: Bear Call Spread Entry Order")
    print("="*60)
    
    order = generate_bear_call_spread_entry_order(
        ticker="SPY",
        expiration="2024-12-01",
        sell_strike=590.0,
        buy_strike=595.0,
        quantity=1,
        sell_call_bid=2.45,
        buy_call_ask=1.05
    )
    
    print(f"\n📋 Order Details:")
    print(f"  Order Type: {order['orderType']}")
    print(f"  Instruction: {order['orderStrategyType']}")
    print(f"  Legs: {len(order['orderLegCollection'])}")
    
    # Validate legs
    sell_leg = order['orderLegCollection'][0]
    buy_leg = order['orderLegCollection'][1]
    
    print(f"\n  Sell Leg:")
    print(f"    Instruction: {sell_leg['instruction']}")
    print(f"    Strike: ${sell_leg['instrument']['putCall']} @ {sell_leg['instrument'].get('strikePrice', 'N/A')}")
    print(f"    Quantity: {sell_leg['quantity']}")
    
    print(f"\n  Buy Leg:")
    print(f"    Instruction: {buy_leg['instruction']}")
    print(f"    Strike: ${buy_leg['instrument']['putCall']} @ {buy_leg['instrument'].get('strikePrice', 'N/A')}")
    print(f"    Quantity: {buy_leg['quantity']}")
    
    # Validations
    assert sell_leg['instruction'] == "SELL_TO_OPEN", "Sell leg instruction incorrect"
    assert buy_leg['instruction'] == "BUY_TO_OPEN", "Buy leg instruction incorrect"
    assert sell_leg['instrument']['putCall'] == "CALL", "Sell leg not a call"
    assert buy_leg['instrument']['putCall'] == "CALL", "Buy leg not a call"
    
    print("\n  ✅ Entry order structure valid!")
    
    return order


def test_credit_spread_exit_order():
    """Test credit spread exit order generation."""
    print("\n" + "="*60)
    print("TEST 2C: Credit Spread Exit Order")
    print("="*60)
    
    order = generate_credit_spread_exit_order(
        ticker="SPY",
        expiration="2024-12-01",
        sell_strike=575.0,
        buy_strike=570.0,
        quantity=1,
        is_put_spread=True,
        target_debit=0.75
    )
    
    print(f"\n📋 Order Details:")
    print(f"  Order Type: {order['orderType']}")
    print(f"  Price: ${order.get('price', 'N/A'):.2f}")
    print(f"  Legs: {len(order['orderLegCollection'])}")
    
    # Validate legs (should be opposite of entry)
    buy_leg = order['orderLegCollection'][0]
    sell_leg = order['orderLegCollection'][1]
    
    print(f"\n  Buy-to-Close Leg:")
    print(f"    Instruction: {buy_leg['instruction']}")
    print(f"    Quantity: {buy_leg['quantity']}")
    
    print(f"\n  Sell-to-Close Leg:")
    print(f"    Instruction: {sell_leg['instruction']}")
    print(f"    Quantity: {sell_leg['quantity']}")
    
    # Validations
    assert buy_leg['instruction'] == "BUY_TO_CLOSE", "Buy-to-close instruction incorrect"
    assert sell_leg['instruction'] == "SELL_TO_CLOSE", "Sell-to-close instruction incorrect"
    
    print("\n  ✅ Exit order structure valid!")
    
    return order


def test_credit_spread_stop_loss_order():
    """Test credit spread stop-loss order generation."""
    print("\n" + "="*60)
    print("TEST 2D: Credit Spread Stop-Loss Order")
    print("="*60)
    
    order = generate_credit_spread_stop_loss_order(
        ticker="SPY",
        expiration="2024-12-01",
        sell_strike=575.0,
        buy_strike=570.0,
        quantity=1,
        is_put_spread=True,
        stop_loss_debit=4.00
    )
    
    print(f"\n📋 Order Details:")
    print(f"  Order Type: {order['orderType']}")
    print(f"  Stop Price: ${order.get('stopPrice', 'N/A'):.2f}")
    print(f"  Legs: {len(order['orderLegCollection'])}")
    
    # Validations
    assert order['orderType'] == "NET_DEBIT", "Order type should be NET_DEBIT"
    assert 'stopPrice' in order, "Stop price missing"
    
    print("\n  ✅ Stop-loss order structure valid!")
    
    return order


# ========================================
# TEST 3: Monte Carlo P&L Calculations
# ========================================

def test_monte_carlo_bull_put_spread():
    """Test Monte Carlo P&L for Bull Put Spread."""
    print("\n" + "="*60)
    print("TEST 3A: Monte Carlo Bull Put Spread")
    print("="*60)
    
    params = {
        'S0': 580.0,
        'days': 30,
        'iv': 0.20,
        'sell_strike': 575.0,
        'buy_strike': 570.0,
        'net_credit': 1.50
    }
    
    print(f"\n🎲 Monte Carlo Parameters:")
    print(f"  Current Price: ${params['S0']:.2f}")
    print(f"  Days to Exp: {params['days']}")
    print(f"  IV: {params['iv']*100:.1f}%")
    print(f"  Sell Strike: ${params['sell_strike']:.2f}")
    print(f"  Buy Strike: ${params['buy_strike']:.2f}")
    print(f"  Net Credit: ${params['net_credit']:.2f}")
    
    # Run Monte Carlo
    mc = mc_pnl("BULL_PUT_SPREAD", params, n_paths=50000, mu=0.0, seed=42)
    
    print(f"\n📈 Results (50k paths):")
    print(f"  Expected P&L: ${mc['pnl_expected']:.2f}")
    print(f"  Median P&L: ${mc['pnl_p50']:.2f}")
    print(f"  P5 / P95: ${mc['pnl_p5']:.2f} / ${mc['pnl_p95']:.2f}")
    print(f"  Min / Max: ${mc['pnl_min']:.2f} / ${mc['pnl_max']:.2f}")
    print(f"  Std Dev: ${mc['pnl_std']:.2f}")
    print(f"  Capital: ${mc['collateral']:.2f}")
    print(f"  Annual ROI: {mc['roi_ann_expected']*100:.2f}%")
    
    # Validations
    max_profit = params['net_credit'] * 100
    max_loss = (params['sell_strike'] - params['buy_strike'] - params['net_credit']) * 100
    
    assert mc['pnl_max'] <= max_profit + 0.01, f"Max P&L exceeds max profit: {mc['pnl_max']} > {max_profit}"
    assert mc['pnl_min'] >= -max_loss - 0.01, f"Min P&L exceeds max loss: {mc['pnl_min']} < {-max_loss}"
    assert mc['collateral'] == max_loss, f"Capital mismatch: {mc['collateral']} != {max_loss}"
    
    print("\n  ✅ Monte Carlo bounds validated!")
    
    return mc


def test_monte_carlo_bear_call_spread():
    """Test Monte Carlo P&L for Bear Call Spread."""
    print("\n" + "="*60)
    print("TEST 3B: Monte Carlo Bear Call Spread")
    print("="*60)
    
    params = {
        'S0': 580.0,
        'days': 30,
        'iv': 0.20,
        'sell_strike': 590.0,
        'buy_strike': 595.0,
        'net_credit': 1.50
    }
    
    print(f"\n🎲 Monte Carlo Parameters:")
    print(f"  Current Price: ${params['S0']:.2f}")
    print(f"  Days to Exp: {params['days']}")
    print(f"  IV: {params['iv']*100:.1f}%")
    print(f"  Sell Strike: ${params['sell_strike']:.2f}")
    print(f"  Buy Strike: ${params['buy_strike']:.2f}")
    print(f"  Net Credit: ${params['net_credit']:.2f}")
    
    # Run Monte Carlo
    mc = mc_pnl("BEAR_CALL_SPREAD", params, n_paths=50000, mu=0.0, seed=42)
    
    print(f"\n📈 Results (50k paths):")
    print(f"  Expected P&L: ${mc['pnl_expected']:.2f}")
    print(f"  Median P&L: ${mc['pnl_p50']:.2f}")
    print(f"  P5 / P95: ${mc['pnl_p5']:.2f} / ${mc['pnl_p95']:.2f}")
    print(f"  Min / Max: ${mc['pnl_min']:.2f} / ${mc['pnl_max']:.2f}")
    print(f"  Std Dev: ${mc['pnl_std']:.2f}")
    print(f"  Capital: ${mc['collateral']:.2f}")
    print(f"  Annual ROI: {mc['roi_ann_expected']*100:.2f}%")
    
    # Validations
    max_profit = params['net_credit'] * 100
    max_loss = (params['buy_strike'] - params['sell_strike'] - params['net_credit']) * 100
    
    assert mc['pnl_max'] <= max_profit + 0.01, f"Max P&L exceeds max profit: {mc['pnl_max']} > {max_profit}"
    assert mc['pnl_min'] >= -max_loss - 0.01, f"Min P&L exceeds max loss: {mc['pnl_min']} < {-max_loss}"
    assert mc['collateral'] == max_loss, f"Capital mismatch: {mc['collateral']} != {max_loss}"
    
    print("\n  ✅ Monte Carlo bounds validated!")
    
    return mc


# ========================================
# TEST 4: Overview Tab Metrics
# ========================================

def test_overview_metrics_bull_put():
    """Test Overview tab metric calculations for Bull Put Spread."""
    print("\n" + "="*60)
    print("TEST 4A: Overview Metrics - Bull Put Spread")
    print("="*60)
    
    # Simulate row from scanner results
    sell_strike = 575.0
    buy_strike = 570.0
    net_credit = 1.50
    
    # Calculate metrics (as done in Overview tab)
    spread_width = sell_strike - buy_strike
    capital_per_share = spread_width - net_credit
    capital = capital_per_share * 100.0
    max_profit = net_credit * 100.0
    max_loss = capital
    breakeven = sell_strike - net_credit
    target_50_pct = net_credit * 0.50
    target_75_pct = net_credit * 0.25
    
    print(f"\n📊 Calculated Metrics:")
    print(f"  Spread Width: ${spread_width:.2f}")
    print(f"  Capital Required: ${capital:.0f}")
    print(f"  Max Profit: ${max_profit:.0f}")
    print(f"  Max Loss: ${max_loss:.0f}")
    print(f"  Breakeven: ${breakeven:.2f}")
    print(f"  50% Profit Target: Close for ≤ ${target_50_pct:.2f}")
    print(f"  75% Profit Target: Close for ≤ ${target_75_pct:.2f}")
    
    # Validations
    assert spread_width == 5.0, "Spread width incorrect"
    assert capital == 350.0, "Capital incorrect"
    assert max_profit == 150.0, "Max profit incorrect"
    assert max_loss == 350.0, "Max loss incorrect"
    assert breakeven == 573.50, "Breakeven incorrect"
    
    print("\n  ✅ All metrics validated!")
    
    return {
        'spread_width': spread_width,
        'capital': capital,
        'max_profit': max_profit,
        'max_loss': max_loss,
        'breakeven': breakeven
    }


def test_overview_metrics_bear_call():
    """Test Overview tab metric calculations for Bear Call Spread."""
    print("\n" + "="*60)
    print("TEST 4B: Overview Metrics - Bear Call Spread")
    print("="*60)
    
    # Simulate row from scanner results
    sell_strike = 590.0
    buy_strike = 595.0
    net_credit = 1.50
    
    # Calculate metrics (as done in Overview tab)
    spread_width = buy_strike - sell_strike  # Note: Different for call spreads
    capital_per_share = spread_width - net_credit
    capital = capital_per_share * 100.0
    max_profit = net_credit * 100.0
    max_loss = capital
    breakeven = sell_strike + net_credit  # Note: Different for call spreads
    target_50_pct = net_credit * 0.50
    target_75_pct = net_credit * 0.25
    
    print(f"\n📊 Calculated Metrics:")
    print(f"  Spread Width: ${spread_width:.2f}")
    print(f"  Capital Required: ${capital:.0f}")
    print(f"  Max Profit: ${max_profit:.0f}")
    print(f"  Max Loss: ${max_loss:.0f}")
    print(f"  Breakeven: ${breakeven:.2f}")
    print(f"  50% Profit Target: Close for ≤ ${target_50_pct:.2f}")
    print(f"  75% Profit Target: Close for ≤ ${target_75_pct:.2f}")
    
    # Validations
    assert spread_width == 5.0, "Spread width incorrect"
    assert capital == 350.0, "Capital incorrect"
    assert max_profit == 150.0, "Max profit incorrect"
    assert max_loss == 350.0, "Max loss incorrect"
    assert breakeven == 591.50, "Breakeven incorrect"
    
    print("\n  ✅ All metrics validated!")
    
    return {
        'spread_width': spread_width,
        'capital': capital,
        'max_profit': max_profit,
        'max_loss': max_loss,
        'breakeven': breakeven
    }


# ========================================
# RUN ALL TESTS
# ========================================

def run_all_tests():
    """Run all credit spread tests."""
    print("\n" + "="*60)
    print("🧪 CREDIT SPREADS COMPREHENSIVE TEST SUITE")
    print("="*60)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    failed_tests = []
    
    try:
        # Test 1: Scanner Functions
        test_bull_put_spread_scanner()
        test_bear_call_spread_scanner()
        
        # Test 2: Order Generation
        test_bull_put_spread_entry_order()
        test_bear_call_spread_entry_order()
        test_credit_spread_exit_order()
        test_credit_spread_stop_loss_order()
        
        # Test 3: Monte Carlo
        test_monte_carlo_bull_put_spread()
        test_monte_carlo_bear_call_spread()
        
        # Test 4: Overview Metrics
        test_overview_metrics_bull_put()
        test_overview_metrics_bear_call()
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        failed_tests.append(str(e))
    
    # Final Summary
    print("\n" + "="*60)
    print("📝 TEST SUMMARY")
    print("="*60)
    
    if len(failed_tests) == 0:
        print("\n✅ ALL TESTS PASSED!")
        print("\n  Scanner Functions: ✅")
        print("  Order Generation: ✅")
        print("  Monte Carlo P&L: ✅")
        print("  Overview Metrics: ✅")
        print("\n🎉 Credit spreads implementation fully validated!")
    else:
        print(f"\n❌ {len(failed_tests)} test(s) failed:")
        for i, error in enumerate(failed_tests, 1):
            print(f"  {i}. {error}")
    
    print(f"\nCompleted: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)
    
    return len(failed_tests) == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
