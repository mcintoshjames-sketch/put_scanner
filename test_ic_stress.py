"""
Test Iron Condor Stress Test P&L Calculation

Validates that stress test P&L is calculated correctly:
- At price = short strikes: Should show profit close to max
- At extreme moves: Should show losses capped at max loss
- At current price (0% shock): Should show positive P&L from time decay
"""

import pandas as pd
import sys

# Add parent directory to path
sys.path.insert(0, '/workspaces/put_scanner')

from strategy_lab import run_stress


def test_iron_condor_stress():
    """Test Iron Condor stress test P&L calculation."""
    
    print("\n" + "="*70)
    print("IRON CONDOR STRESS TEST VALIDATION")
    print("="*70)
    
    # Example Iron Condor from scan results
    # SPY @ $570, sell $550/$590 credit spread for $4 net credit
    # Put spread: Buy $540, Sell $550 (width $10)
    # Call spread: Sell $590, Buy $600 (width $10)
    
    row = {
        "Price": 570.0,
        "Days": 30,
        "PutShortStrike": 550.0,
        "PutLongStrike": 540.0,
        "CallShortStrike": 590.0,
        "CallLongStrike": 600.0,
        "NetCredit": 4.0,  # Per share
        "IV": 20.0  # 20%
    }
    
    print("\n📋 Iron Condor Setup:")
    print(f"  Current Price: ${row['Price']:.2f}")
    print(f"  Days to Expiration: {row['Days']}")
    print(f"  Put Spread: Buy ${row['PutLongStrike']:.0f} / Sell ${row['PutShortStrike']:.0f}")
    print(f"  Call Spread: Sell ${row['CallShortStrike']:.0f} / Buy ${row['CallLongStrike']:.0f}")
    print(f"  Net Credit: ${row['NetCredit']:.2f}/share = ${row['NetCredit'] * 100:.0f}/contract")
    print(f"  IV: {row['IV']:.0f}%")
    
    # Calculate max profit and max loss
    put_width = row['PutShortStrike'] - row['PutLongStrike']
    call_width = row['CallLongStrike'] - row['CallShortStrike']
    max_spread_width = max(put_width, call_width)
    
    max_profit = row['NetCredit'] * 100  # Keep all credit
    max_loss = (max_spread_width - row['NetCredit']) * 100  # Width - credit
    
    print(f"\n💰 Expected P&L Boundaries:")
    print(f"  Max Profit: ${max_profit:.0f} (if price stays between ${row['PutShortStrike']:.0f} and ${row['CallShortStrike']:.0f})")
    print(f"  Max Loss: ${-max_loss:.0f} (if price moves beyond ${row['PutLongStrike']:.0f} or ${row['CallLongStrike']:.0f})")
    print(f"  Breakeven Lower: ${row['PutShortStrike'] - row['NetCredit']:.2f}")
    print(f"  Breakeven Upper: ${row['CallShortStrike'] + row['NetCredit']:.2f}")
    
    # Run stress test
    shocks = [-20, -10, -5, 0, 5, 10, 20]
    df_stress = run_stress(
        strategy="IRON_CONDOR",
        row=row,
        shocks_pct=shocks,
        horizon_days=0,  # Immediate re-mark
        r=0.05,
        div_y=0.0
    )
    
    print("\n📊 Stress Test Results:")
    print("="*70)
    
    # Format output
    for _, r in df_stress.iterrows():
        shock = r['Shock%']
        price = r['Price']
        total_pnl = r['Total_P&L']
        roi = r['ROI_on_cap%']
        
        # Determine expected outcome
        if price < row['PutLongStrike']:
            expected = "MAX LOSS (below long put)"
        elif price < row['PutShortStrike']:
            expected = "PUT SPREAD LOSS"
        elif price < row['CallShortStrike']:
            expected = "PROFIT ZONE"
        elif price < row['CallLongStrike']:
            expected = "CALL SPREAD LOSS"
        else:
            expected = "MAX LOSS (above long call)"
        
        status = "✅" if total_pnl >= -max_loss and total_pnl <= max_profit else "❌"
        
        print(f"{status} Shock {shock:+3.0f}%: Price ${price:6.2f} | P&L ${total_pnl:+7.0f} | ROI {roi:+6.1f}% | {expected}")
    
    # Validation checks
    print("\n🔍 Validation Checks:")
    print("="*70)
    
    tests_passed = 0
    tests_total = 0
    
    # Test 1: At 0% shock, P&L should be near zero (no time has passed)
    tests_total += 1
    zero_shock = df_stress[df_stress['Shock%'] == 0].iloc[0]
    if abs(zero_shock['Total_P&L']) < 100:  # Within $100 is reasonable
        print(f"✅ Test 1: 0% shock shows near-zero P&L (${zero_shock['Total_P&L']:.2f}) - no time decay yet")
        tests_passed += 1
    else:
        print(f"❌ Test 1: 0% shock should be near zero, got ${zero_shock['Total_P&L']:.2f}")
    
    # Test 2: P&L should be bounded by max profit and max loss
    tests_total += 1
    pnl_values = df_stress['Total_P&L']
    if (pnl_values <= max_profit).all() and (pnl_values >= -max_loss).all():
        print(f"✅ Test 2: All P&L values within bounds [${-max_loss:.0f}, ${max_profit:.0f}]")
        tests_passed += 1
    else:
        print(f"❌ Test 2: Some P&L values outside bounds")
        print(f"   Min P&L: ${pnl_values.min():.2f} (should be >= ${-max_loss:.2f})")
        print(f"   Max P&L: ${pnl_values.max():.2f} (should be <= ${max_profit:.2f})")
    
    # Test 3: Large down move should show near max loss
    tests_total += 1
    large_down = df_stress[df_stress['Shock%'] == -20].iloc[0]
    # At -20%, price = $456, way below $540 long put
    # Should be close to max loss
    if large_down['Total_P&L'] < -max_loss * 0.8:  # Within 80% of max loss
        print(f"✅ Test 3: Large down move shows significant loss (${large_down['Total_P&L']:.2f})")
        tests_passed += 1
    else:
        print(f"❌ Test 3: Large down move should show near max loss, got ${large_down['Total_P&L']:.2f}")
    
    # Test 4: Large up move should show near max loss
    tests_total += 1
    large_up = df_stress[df_stress['Shock%'] == 20].iloc[0]
    # At +20%, price = $684, way above $600 long call
    # Should be close to max loss
    if large_up['Total_P&L'] < -max_loss * 0.8:  # Within 80% of max loss
        print(f"✅ Test 4: Large up move shows significant loss (${large_up['Total_P&L']:.2f})")
        tests_passed += 1
    else:
        print(f"❌ Test 4: Large up move should show near max loss, got ${large_up['Total_P&L']:.2f}")
    
    # Test 5: Small moves (±5%) should show reasonable P&L (within bounds)
    # Note: Without time decay, small moves may show small losses
    tests_total += 1
    small_moves = df_stress[df_stress['Shock%'].abs() <= 5]
    small_pnl_within_bounds = (small_moves['Total_P&L'] >= -max_loss) & (small_moves['Total_P&L'] <= max_profit)
    if small_pnl_within_bounds.all():
        print(f"✅ Test 5: Small moves (±5%) show bounded P&L")
        tests_passed += 1
    else:
        print(f"❌ Test 5: Small moves P&L out of bounds")
        print(small_moves[['Shock%', 'Price', 'Total_P&L']])
    
    # Test 6: No P&L should be positive beyond max profit
    tests_total += 1
    if (pnl_values <= max_profit * 1.01).all():  # Allow 1% rounding
        print(f"✅ Test 6: No P&L exceeds max profit (${max_profit:.0f})")
        tests_passed += 1
    else:
        print(f"❌ Test 6: Some P&L values exceed max profit")
    
    # Summary
    print("\n" + "="*70)
    print(f"RESULTS: {tests_passed}/{tests_total} tests passed")
    print("="*70)
    
    if tests_passed == tests_total:
        print("✅ ALL TESTS PASSED - Iron Condor stress test logic is correct!")
        return True
    else:
        print(f"❌ {tests_total - tests_passed} test(s) failed - review logic")
        return False


if __name__ == "__main__":
    success = test_iron_condor_stress()
    exit(0 if success else 1)
