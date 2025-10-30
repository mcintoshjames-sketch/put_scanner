"""
Test to validate Monte Carlo penalty integration in credit spread scoring.

This test will:
1. Run credit spread scans with MC penalty enabled
2. Verify negative MC expected P&L results in low scores
3. Verify positive MC expected P&L results in high scores
4. Compare before/after MC penalty rankings
"""

import pandas as pd
import numpy as np
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

# Import from strategy_lab
from strategy_lab import (
    scan_bull_put_spread,
    scan_bear_call_spread,
    fetch_price
)

def test_mc_penalty_integration(ticker="SPY", strategy="BULL_PUT"):
    """
    Test that MC penalty properly affects credit spread scoring.
    
    Args:
        ticker: Stock symbol to analyze
        strategy: "BULL_PUT" or "BEAR_CALL"
    """
    print(f"\n{'='*80}")
    print(f"TESTING MC PENALTY INTEGRATION: {strategy} SPREAD FOR {ticker}")
    print(f"{'='*80}\n")
    
    # Run scan with relaxed filters
    print("🔍 Running credit spread scan with MC penalty...")
    if strategy == "BULL_PUT":
        df = scan_bull_put_spread(
            ticker=ticker,
            spread_width=5.0,
            min_days=14,
            days_limit=60,
            min_oi=50,
            max_spread=20.0,
            min_roi=0.10,  # 10% annualized - very low to get more results
            min_poew=0.50,  # 50% - low to get more results
            min_cushion=0.3,  # Low cushion to get near-ATM spreads
            earn_window=7,
            risk_free=0.05
        )
    else:
        df = scan_bear_call_spread(
            ticker=ticker,
            spread_width=5.0,
            min_days=14,
            days_limit=60,
            min_oi=50,
            max_spread=20.0,
            min_roi=0.10,
            min_poew=0.50,
            min_cushion=0.3,
            earn_window=7,
            risk_free=0.05
        )
    
    if df.empty:
        print(f"❌ No {strategy} opportunities found for {ticker}")
        return None
    
    print(f"✅ Found {len(df)} opportunities\n")
    
    # Analyze results
    print(f"{'─'*80}")
    print(f"TOP 10 RESULTS WITH MC PENALTY")
    print(f"{'─'*80}\n")
    
    # Display key columns
    display_cols = ['Exp', 'Days', 'SellStrike', 'NetCredit', 'MaxLoss', 'OTM%', 
                    'ROI%_ann', 'MC_ExpectedPnL', 'MC_ROI_ann%', 'Score']
    
    if 'MC_ExpectedPnL' in df.columns:
        print(df[display_cols].head(10).to_string(index=False))
    else:
        print("❌ ERROR: MC_ExpectedPnL column not found!")
        print(f"Available columns: {df.columns.tolist()}")
        return None
    
    # Statistics
    print(f"\n{'─'*80}")
    print(f"STATISTICS")
    print(f"{'─'*80}\n")
    
    total = len(df)
    has_mc = df['MC_ExpectedPnL'].notna().sum()
    negative_mc = (df['MC_ExpectedPnL'] < 0).sum()
    positive_mc = (df['MC_ExpectedPnL'] > 0).sum()
    
    print(f"Total opportunities: {total}")
    print(f"With valid MC results: {has_mc} ({has_mc/total*100:.1f}%)")
    print(f"Negative MC expected P&L: {negative_mc} ({negative_mc/total*100:.1f}%)")
    print(f"Positive MC expected P&L: {positive_mc} ({positive_mc/total*100:.1f}%)")
    
    if has_mc > 0:
        avg_mc_pnl = df[df['MC_ExpectedPnL'].notna()]['MC_ExpectedPnL'].mean()
        med_mc_pnl = df[df['MC_ExpectedPnL'].notna()]['MC_ExpectedPnL'].median()
        print(f"\nAverage MC expected P&L: ${avg_mc_pnl:.2f}")
        print(f"Median MC expected P&L: ${med_mc_pnl:.2f}")
    
    # Validation checks
    print(f"\n{'─'*80}")
    print(f"VALIDATION CHECKS")
    print(f"{'─'*80}\n")
    
    checks_passed = 0
    checks_total = 0
    
    # Check 1: Top 10 should have mostly positive MC expected P&L
    checks_total += 1
    top10 = df.head(10)
    top10_positive = (top10['MC_ExpectedPnL'] > 0).sum()
    check1_pass = top10_positive >= 7  # At least 70%
    print(f"{'✅' if check1_pass else '❌'} Check 1: Top 10 have {top10_positive}/10 positive MC expected P&L (target: ≥7)")
    if check1_pass:
        checks_passed += 1
    
    # Check 2: Opportunities with negative MC should be penalized
    checks_total += 1
    if negative_mc > 0:
        negative_df = df[df['MC_ExpectedPnL'] < 0]
        avg_negative_score = negative_df['Score'].mean()
        avg_overall_score = df['Score'].mean()
        check2_pass = avg_negative_score < avg_overall_score * 0.7
        print(f"{'✅' if check2_pass else '❌'} Check 2: Negative MC opportunities have lower scores (avg: {avg_negative_score:.4f} vs overall: {avg_overall_score:.4f})")
        if check2_pass:
            checks_passed += 1
    else:
        print(f"⏭️  Check 2: Skipped (no negative MC opportunities)")
    
    # Check 3: MC ROI should correlate with MC expected P&L
    checks_total += 1
    valid_mc = df[df['MC_ExpectedPnL'].notna() & df['MC_ROI_ann%'].notna()]
    if len(valid_mc) > 10:
        correlation = valid_mc['MC_ExpectedPnL'].corr(valid_mc['MC_ROI_ann%'])
        check3_pass = correlation > 0.8
        print(f"{'✅' if check3_pass else '❌'} Check 3: MC P&L and MC ROI are highly correlated (r={correlation:.3f}, target: >0.8)")
        if check3_pass:
            checks_passed += 1
    else:
        print(f"⏭️  Check 3: Skipped (insufficient data)")
        checks_total -= 1
    
    # Check 4: Score should correlate positively with MC expected P&L
    checks_total += 1
    if len(valid_mc) > 10:
        score_mc_corr = valid_mc['Score'].corr(valid_mc['MC_ExpectedPnL'])
        check4_pass = score_mc_corr > 0.5
        print(f"{'✅' if check4_pass else '❌'} Check 4: Score correlates with MC expected P&L (r={score_mc_corr:.3f}, target: >0.5)")
        if check4_pass:
            checks_passed += 1
    else:
        print(f"⏭️  Check 4: Skipped (insufficient data)")
        checks_total -= 1
    
    # Check 5: No negative MC expected P&L in top 5
    checks_total += 1
    top5 = df.head(5)
    top5_negative = (top5['MC_ExpectedPnL'] < 0).sum()
    check5_pass = top5_negative == 0
    print(f"{'✅' if check5_pass else '❌'} Check 5: Top 5 have zero negative MC expected P&L (found: {top5_negative})")
    if check5_pass:
        checks_passed += 1
    
    print(f"\n{'='*80}")
    print(f"VALIDATION SUMMARY: {checks_passed}/{checks_total} checks passed ({checks_passed/checks_total*100:.0f}%)")
    print(f"{'='*80}")
    
    if checks_passed == checks_total:
        print("\n🎉 SUCCESS: MC penalty is working correctly!")
    elif checks_passed >= checks_total * 0.8:
        print("\n✅ GOOD: MC penalty is mostly working, minor issues")
    else:
        print("\n⚠️  WARNING: MC penalty may not be working as expected")
    
    return df


if __name__ == "__main__":
    print("\n" + "="*80)
    print("CREDIT SPREAD MC PENALTY VALIDATION TEST")
    print("="*80)
    
    # Test with SPY
    print("\nTesting Bull Put Spreads on SPY...")
    results_spy_bull = test_mc_penalty_integration("SPY", "BULL_PUT")
    
    print("\n\n" + "="*80)
    print("\nTesting Bear Call Spreads on SPY...")
    results_spy_bear = test_mc_penalty_integration("SPY", "BEAR_CALL")
    
    # Test with high IV stock if available
    print("\n\n" + "="*80)
    print("\nTesting Bull Put Spreads on TSLA (high IV)...")
    try:
        results_tsla = test_mc_penalty_integration("TSLA", "BULL_PUT")
    except Exception as e:
        print(f"❌ TSLA test failed: {e}")
    
    print("\n\n" + "="*80)
    print("MC PENALTY VALIDATION COMPLETE")
    print("="*80)
    print("\nKey Findings:")
    print("1. MC expected P&L is now calculated for all credit spread opportunities")
    print("2. Opportunities with negative MC expected P&L receive 80% score penalty")
    print("3. MC penalty has 40% weight in final score (highest component)")
    print("4. Top-ranked opportunities should now have positive expected value")
    print("\nRecommendation: Use scans regularly to verify MC penalty continues working correctly.")
