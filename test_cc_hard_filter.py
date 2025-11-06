#!/usr/bin/env python3
"""
Test that CC hard filter rejects negative MC expected P&L.
"""

import sys
import pandas as pd
sys.path.insert(0, "/workspaces/put_scanner")

from strategy_lab import analyze_cc
import config

def test_cc_hard_filter():
    """Test that negative MC P&L opportunities are now filtered out."""
    
    print("\n" + "="*80)
    print("Testing Covered Call Hard Filter for Negative MC Expected P&L")
    print("="*80)
    
    # Use tight parameters that previously showed negative MC P&L
    # Near-the-money strikes (1-2% OTM) tend to have negative expected value
    ticker = "SPY"
    min_otm = 0.005  # 0.5% OTM minimum (near-the-money)
    days_limit = 30
    min_roi = 0.01  # Low ROI threshold to catch borderline cases
    
    print(f"\nScan Parameters:")
    print(f"  Ticker: {ticker}")
    print(f"  Min OTM: {min_otm*100:.1f}%")
    print(f"  Days Limit: {days_limit}")
    print(f"  Min ROI: {min_roi*100:.1f}%")
    
    print("\nRunning scan...")
    results = analyze_cc(
        ticker=ticker,
        days_limit=days_limit,
        min_otm=min_otm,
        min_oi=50,
        max_spread=0.05,
        min_roi=min_roi,
        earn_window=3,
        risk_free=0.045,  # 4.5% risk-free rate
        include_dividends=True
    )
    
    if results.empty:
        print("\n⚠️ No results found - this could indicate:")
        print("   1. Hard filter is working (all near-the-money CCs had negative MC P&L)")
        print("   2. No options meet the criteria")
        print("   3. Market conditions have changed")
        return
    
    print(f"\nFound {len(results)} Covered Call opportunities")
    print("\nAnalyzing MC Expected P&L distribution:")
    
    # Check that ALL results have positive MC expected P&L
    negative_count = 0
    positive_count = 0
    nan_count = 0
    
    mc_pnls = []
    
    for idx, row in results.iterrows():
        mc_pnl = row.get('MC_ExpectedPnL', float('nan'))
        
        if pd.isna(mc_pnl):  # NaN check
            nan_count += 1
        elif mc_pnl < 0:
            negative_count += 1
            print(f"  ❌ NEGATIVE FOUND: {row['Symbol']} {row['Strike']} {row['Expiration']}: MC P&L = ${mc_pnl:.2f}")
        else:
            positive_count += 1
            mc_pnls.append(mc_pnl)
    
    print(f"\n{'='*80}")
    print(f"MC Expected P&L Distribution:")
    print(f"  Positive: {positive_count} ({positive_count/len(results)*100:.1f}%)")
    print(f"  Negative: {negative_count} ({negative_count/len(results)*100:.1f}%)")
    print(f"  NaN: {nan_count} ({nan_count/len(results)*100:.1f}%)")
    
    if mc_pnls:
        print(f"\nPositive MC P&L Statistics:")
        print(f"  Minimum: ${min(mc_pnls):.2f}")
        print(f"  Average: ${sum(mc_pnls)/len(mc_pnls):.2f}")
        print(f"  Maximum: ${max(mc_pnls):.2f}")
    
    print(f"\n{'='*80}")
    if negative_count == 0 and positive_count > 0:
        print("✅ SUCCESS: Hard filter working correctly!")
        print("   All opportunities have positive MC expected P&L")
    elif negative_count > 0:
        print("❌ FAILURE: Hard filter not working!")
        print(f"   Found {negative_count} opportunities with negative MC P&L")
    elif positive_count == 0:
        print("⚠️ INCONCLUSIVE: No positive opportunities found")
        print("   This could indicate all near-the-money CCs have negative expected value")
    
    print(f"{'='*80}\n")
    
    # Show a few examples
    if not results.empty:
        print("\nSample Opportunities (first 5):")
        print(f"{'Symbol':<8} {'Strike':<8} {'OTM%':<8} {'Days':<6} {'ROI%':<8} {'MC_ExpPnL':<12} {'Score':<8}")
        print("-" * 80)
        for idx, row in results.head(5).iterrows():
            sym = row['Symbol']
            strike = row['Strike']
            otm_pct = row.get('OTM%', 0) * 100
            days = row.get('Days', 0)
            roi = row.get('ROI_Annual%', 0)
            mc_pnl = row.get('MC_ExpectedPnL', float('nan'))
            score = row.get('Score', 0)
            
            mc_pnl_str = f"${mc_pnl:.2f}" if not pd.isna(mc_pnl) else "NaN"
            
            print(f"{sym:<8} ${strike:<7.2f} {otm_pct:<7.2f}% {days:<6} {roi:<7.1f}% {mc_pnl_str:<12} {score:<7.1f}")

if __name__ == "__main__":
    import pandas as pd
    test_cc_hard_filter()
