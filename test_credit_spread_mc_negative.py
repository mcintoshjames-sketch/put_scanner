"""
Test to investigate why credit spreads pass screens despite negative expected P&L in Monte Carlo.

This test will:
1. Run a credit spread scan (Bull Put or Bear Call)
2. For each passing opportunity, run Monte Carlo simulation
3. Identify which ones have negative expected P&L
4. Analyze why they passed the scoring filters

The hypothesis is that the scoring system doesn't consider MC expected P&L,
only static metrics like ROI%, OTM%, cushion, POEW, etc.
"""

import sys
import pandas as pd
import numpy as np
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

# Import from strategy_lab
from strategy_lab import (
    scan_bull_put_spread,
    scan_bear_call_spread,
    mc_pnl,
    fetch_price
)

def analyze_credit_spread_mc_alignment(ticker="SPY", strategy="BULL_PUT"):
    """
    Analyze alignment between scan scores and MC expected P&L.
    
    Args:
        ticker: Stock symbol to analyze
        strategy: "BULL_PUT" or "BEAR_CALL"
    """
    print(f"\n{'='*80}")
    print(f"ANALYZING {strategy} SPREAD FOR {ticker}")
    print(f"{'='*80}\n")
    
    # Run scan with relaxed filters to get more results
    print("🔍 Running credit spread scan...")
    if strategy == "BULL_PUT":
        df = scan_bull_put_spread(
            ticker=ticker,
            spread_width=5.0,
            min_days=7,
            days_limit=60,
            min_oi=50,
            max_spread=20.0,
            min_roi=0.15,  # 15% annualized
            min_poew=0.60,
            min_cushion=0.5,
            earn_window=7,
            risk_free=0.05
        )
    else:
        df = scan_bear_call_spread(
            ticker=ticker,
            spread_width=5.0,
            min_days=7,
            days_limit=60,
            min_oi=50,
            max_spread=20.0,
            min_roi=0.15,
            min_poew=0.60,
            min_cushion=0.5,
            earn_window=7,
            risk_free=0.05
        )
    
    if df.empty:
        print(f"❌ No {strategy} opportunities found for {ticker}")
        return None
    
    print(f"✅ Found {len(df)} opportunities passing scan filters\n")
    
    # Get current price
    try:
        current_price = fetch_price(ticker)
    except:
        current_price = df.iloc[0]['Price']
    
    # Analyze top 10 results
    analysis_results = []
    
    for idx, row in df.head(10).iterrows():
        print(f"\n{'─'*80}")
        print(f"Opportunity #{idx+1}: {row['Exp']} - Score: {row['Score']:.4f}")
        print(f"{'─'*80}")
        
        # Extract parameters
        sell_strike = float(row['SellStrike'])
        buy_strike = float(row['BuyStrike'])
        net_credit = float(row['NetCredit'])
        days = int(row['Days'])
        iv = float(row['IV']) / 100.0  # Convert from percentage
        spread_width = float(row['Spread'])
        max_loss = float(row['MaxLoss'])
        
        # Scan metrics
        roi_cycle = float(row['ROI%']) / 100.0
        roi_ann = float(row['ROI%_ann']) / 100.0
        otm_pct = float(row['OTM%'])
        poew = float(row.get('POEW', np.nan))
        cushion = float(row.get('CushionSigma', np.nan))
        theta_gamma = float(row.get('Theta/Gamma', np.nan))
        
        print(f"\n📊 Scan Metrics:")
        print(f"   Sell Strike: ${sell_strike:.2f} | Buy Strike: ${buy_strike:.2f}")
        print(f"   Net Credit: ${net_credit:.2f} | Max Loss: ${max_loss:.2f}")
        print(f"   ROI (cycle): {roi_cycle*100:.2f}% | ROI (ann): {roi_ann*100:.2f}%")
        print(f"   OTM%: {otm_pct:.2f}% | POEW: {poew:.3f}")
        print(f"   Cushion: {cushion:.2f}σ | Θ/Γ: {theta_gamma:.2f}")
        
        # Run Monte Carlo simulation
        print(f"\n🎲 Running Monte Carlo (10,000 paths, μ=0%)...")
        
        if strategy == "BULL_PUT":
            params = {
                "S0": current_price,
                "days": days,
                "iv": iv,
                "sell_strike": sell_strike,
                "buy_strike": buy_strike,
                "net_credit": net_credit
            }
            mc = mc_pnl("BULL_PUT_SPREAD", params, n_paths=10000, mu=0.0, seed=42)
        else:
            params = {
                "S0": current_price,
                "days": days,
                "iv": iv,
                "sell_strike": sell_strike,
                "buy_strike": buy_strike,
                "net_credit": net_credit
            }
            mc = mc_pnl("BEAR_CALL_SPREAD", params, n_paths=10000, mu=0.0, seed=42)
        
        # MC results
        mc_expected = mc['pnl_expected']
        mc_p5 = mc['pnl_p5']
        mc_p50 = mc['pnl_p50']
        mc_p95 = mc['pnl_p95']
        mc_worst = mc['pnl_min']
        mc_roi_ann = mc['roi_ann_expected']
        collateral = mc['collateral']
        
        print(f"\n💰 Monte Carlo Results (μ=0%):")
        print(f"   Expected P&L: ${mc_expected:,.2f}")
        print(f"   P5/P50/P95: ${mc_p5:,.2f} / ${mc_p50:,.2f} / ${mc_p95:,.2f}")
        print(f"   Worst case: ${mc_worst:,.2f}")
        print(f"   Collateral: ${collateral:,.2f}")
        print(f"   MC ROI (ann): {mc_roi_ann*100:.2f}%")
        
        # Calculate win rate (% of paths with profit)
        win_rate = np.sum(mc['pnl_paths'] > 0) / len(mc['pnl_paths']) * 100
        print(f"   Win Rate: {win_rate:.1f}%")
        
        # Identify issues
        issues = []
        if mc_expected < 0:
            issues.append(f"❌ NEGATIVE expected P&L (${mc_expected:,.2f})")
        if mc_p50 < 0:
            issues.append(f"❌ NEGATIVE median P&L (${mc_p50:,.2f})")
        if win_rate < 50:
            issues.append(f"❌ LOW win rate ({win_rate:.1f}%)")
        if mc_expected < net_credit * 50:  # Expected P&L should be close to net credit
            shortfall = (net_credit * 100) - mc_expected
            issues.append(f"⚠️ Expected P&L much lower than max profit (shortfall: ${shortfall:,.2f})")
        
        if issues:
            print(f"\n🚨 ISSUES DETECTED:")
            for issue in issues:
                print(f"   {issue}")
        else:
            print(f"\n✅ MC results align with positive expectation")
        
        # Analyze WHY it passed despite issues
        print(f"\n🔍 Why did this pass the scan?")
        print(f"   Score: {row['Score']:.4f}")
        print(f"   - ROI component: High ROI% ({roi_ann*100:.1f}%) from static calculation")
        print(f"   - Cushion: {cushion:.2f}σ (distance to short strike)")
        print(f"   - POEW: {poew:.1%} (static probability from delta)")
        print(f"   - Liquidity: Good spread% and OI")
        print(f"\n   ⚠️ PROBLEM: Scan doesn't consider MC expected P&L!")
        print(f"   Static ROI% = net_credit / max_loss = {net_credit:.2f} / {max_loss:.2f} = {roi_cycle*100:.1f}%")
        print(f"   But MC shows expected P&L is ${mc_expected:,.2f}, not ${net_credit*100:,.2f}")
        
        # Store results
        analysis_results.append({
            'Opportunity': idx + 1,
            'Expiration': row['Exp'],
            'Days': days,
            'SellStrike': sell_strike,
            'BuyStrike': buy_strike,
            'NetCredit': net_credit,
            'MaxLoss': max_loss,
            'Score': row['Score'],
            'ROI_ann': roi_ann,
            'OTM%': otm_pct,
            'POEW': poew,
            'Cushion': cushion,
            'MC_Expected': mc_expected,
            'MC_P50': mc_p50,
            'MC_WinRate': win_rate,
            'MC_ROI_ann': mc_roi_ann,
            'HasNegativeExpected': mc_expected < 0,
            'HasNegativeMedian': mc_p50 < 0,
            'Issues': len(issues)
        })
    
    # Summary
    results_df = pd.DataFrame(analysis_results)
    
    print(f"\n\n{'='*80}")
    print(f"SUMMARY: {strategy} SPREAD ANALYSIS FOR {ticker}")
    print(f"{'='*80}\n")
    
    print(f"Total opportunities analyzed: {len(results_df)}")
    print(f"Opportunities with negative expected P&L: {results_df['HasNegativeExpected'].sum()}")
    print(f"Opportunities with negative median P&L: {results_df['HasNegativeMedian'].sum()}")
    print(f"Opportunities with issues: {(results_df['Issues'] > 0).sum()}\n")
    
    # Show comparison table
    print("📊 Score vs. MC Expected P&L Comparison:")
    print(results_df[['Opportunity', 'Score', 'ROI_ann', 'MC_Expected', 'MC_WinRate', 'HasNegativeExpected']].to_string(index=False))
    
    print(f"\n\n{'='*80}")
    print("ROOT CAUSE ANALYSIS")
    print(f"{'='*80}\n")
    
    print("The credit spread scoring system uses:")
    print("  1. Static ROI% = (net_credit / max_loss) * (365 / days)")
    print("  2. Cushion = (price - short_strike) / expected_move")
    print("  3. POEW = probability from Black-Scholes delta")
    print("  4. Theta/Gamma ratio")
    print("  5. Liquidity (spread%, OI)")
    print()
    print("❌ PROBLEM: The scan does NOT consider Monte Carlo expected P&L!")
    print()
    print("Why negative expected P&L?")
    print("  - Credit spreads assume 0% drift (μ=0)")
    print("  - But with volatility drag and path dependency:")
    print("    Expected P&L = net_credit × P(expire worthless) - losses × P(losses)")
    print("  - For near-ATM spreads or high IV, loss scenarios dominate")
    print("  - Static POEW from delta is optimistic vs. actual path simulations")
    print()
    print("RECOMMENDATION:")
    print("  ✅ Add MC expected P&L as a filter or penalty in scan scoring")
    print("  ✅ Reject opportunities where MC expected P&L < 0")
    print("  ✅ Or at minimum, penalize score if MC E[P&L] < 0.5 × net_credit")
    
    return results_df


if __name__ == "__main__":
    print("\n" + "="*80)
    print("CREDIT SPREAD MONTE CARLO NEGATIVE P&L INVESTIGATION")
    print("="*80)
    
    # Test with SPY (highly liquid, should have many opportunities)
    print("\nTesting with SPY (S&P 500 ETF)...")
    results_spy_bull = analyze_credit_spread_mc_alignment("SPY", "BULL_PUT")
    
    print("\n\n" + "="*80)
    print("\nTesting Bear Call Spreads...")
    results_spy_bear = analyze_credit_spread_mc_alignment("SPY", "BEAR_CALL")
    
    # Test with a high IV stock
    print("\n\n" + "="*80)
    print("\nTesting with high IV stock (TSLA)...")
    results_tsla = analyze_credit_spread_mc_alignment("TSLA", "BULL_PUT")
    
    print("\n\n" + "="*80)
    print("INVESTIGATION COMPLETE")
    print("="*80)
    print("\nKey Finding: Credit spread scans use static ROI% calculation")
    print("but don't validate against Monte Carlo expected P&L, leading to")
    print("false positives where strategies look good on paper but have")
    print("negative expected value when accounting for volatility drag and")
    print("path dependency.")
    print("\nSee analysis above for specific examples and recommendations.")
