#!/usr/bin/env python3
"""
Diagnose why Covered Calls show negative MC P&L
"""
import os
os.environ['STREAMLIT_SERVER_ENABLE_CORS'] = 'false'
os.environ['STREAMLIT_SERVER_ENABLE_XSRF_PROTECTION'] = 'false'

import warnings
warnings.filterwarnings('ignore')
import sys
from io import StringIO
old_stderr = sys.stderr
sys.stderr = StringIO()

try:
    from strategy_lab import analyze_cc, mc_pnl
    import numpy as np
finally:
    sys.stderr = old_stderr

print("="*80)
print("COVERED CALL NEGATIVE MC P&L DIAGNOSTIC")
print("="*80)

# Test different scenarios
scenarios = [
    ("Far OTM (5%+)", {'min_otm': 0.05, 'days_limit': 45}),
    ("Moderate OTM (2-5%)", {'min_otm': 0.02, 'days_limit': 45}),
    ("Near OTM (1-2%)", {'min_otm': 0.01, 'days_limit': 30}),
    ("Very Near (<1%)", {'min_otm': 0.005, 'days_limit': 21}),
]

print("\nTesting SPY Covered Calls with different OTM levels...\n")

for name, params in scenarios:
    print(f"{name}:")
    df = analyze_cc(
        'SPY',
        min_days=7,
        days_limit=params['days_limit'],
        min_otm=params['min_otm'],
        min_oi=100,
        max_spread=15.0,
        min_roi=0.05,
        earn_window=7,
        risk_free=0.045,
        include_dividends=True,
        bill_yield=0.045
    )
    
    if not df.empty:
        valid = df[df['MC_ExpectedPnL'].notna()]
        if len(valid) > 0:
            neg = (valid['MC_ExpectedPnL'] < 0).sum()
            pos = (valid['MC_ExpectedPnL'] > 0).sum()
            print(f"  Results: {len(df)} total, {len(valid)} with MC")
            print(f"  Negative MC P&L: {neg}/{len(valid)} ({neg*100/len(valid):.1f}%)")
            print(f"  Positive MC P&L: {pos}/{len(valid)} ({pos*100/len(valid):.1f}%)")
            print(f"  Avg MC P&L: ${valid['MC_ExpectedPnL'].mean():.2f}")
            print(f"  Median MC P&L: ${valid['MC_ExpectedPnL'].median():.2f}")
            
            if len(valid) > 0:
                # Show details of most negative
                worst_idx = valid['MC_ExpectedPnL'].idxmin()
                worst = df.loc[worst_idx]
                print(f"  Worst case: Strike ${worst['Strike']:.0f}, OTM {worst['OTM%']:.2f}%, " +
                      f"{worst['Days']}D, Premium ${worst['Premium']:.2f}, MC P&L ${worst['MC_ExpectedPnL']:.2f}")
        else:
            print(f"  Results: {len(df)} total, 0 with MC")
    else:
        print(f"  No results")
    print()

# Deep dive into a specific case
print("="*80)
print("DEEP DIVE: Manual MC Calculation")
print("="*80)

# Simulate a typical CC scenario
S0 = 575.0  # SPY price
strike = 580.0  # ~1% OTM
premium = 3.50  # ~$350/contract
days = 21
iv = 0.15
div_annual = 6.50  # SPY dividend ~$6.50/year

print(f"\nScenario: SPY @ ${S0}, Sell {days}D ${strike} Call for ${premium}")
print(f"OTM: {((strike/S0)-1)*100:.2f}%, IV: {iv*100:.0f}%, Annual Div: ${div_annual}")

# Run MC simulation with mu=0.07
mc_params = {
    "S0": S0,
    "days": days,
    "iv": iv,
    "Kc": strike,
    "call_premium": premium,
    "div_ps_annual": div_annual
}

print(f"\nMC Simulation (1000 paths, μ=7%):")
result_7pct = mc_pnl("CC", mc_params, n_paths=1000, mu=0.07, seed=42, rf=0.045)
print(f"  Expected P&L: ${result_7pct['pnl_expected']:.2f}/contract")
print(f"  Std Dev: ${result_7pct['pnl_std']:.2f}")
print(f"  Min: ${result_7pct['pnl_min']:.2f}")
print(f"  Max: ${result_7pct['pnl_max']:.2f}")

# Also try with mu=0 to see the difference
print(f"\nMC Simulation (1000 paths, μ=0% for comparison):")
result_0pct = mc_pnl("CC", mc_params, n_paths=1000, mu=0.0, seed=42, rf=0.045)
print(f"  Expected P&L: ${result_0pct['pnl_expected']:.2f}/contract")
print(f"  Std Dev: ${result_0pct['pnl_std']:.2f}")
print(f"  Min: ${result_0pct['pnl_min']:.2f}")
print(f"  Max: ${result_0pct['pnl_max']:.2f}")

# Break down the P&L components
print(f"\nP&L Component Analysis:")
print(f"  Max premium collected: ${premium * 100:.2f}")
print(f"  Expected dividend ({days}D): ${div_annual * (days/365) * 100:.2f}")
print(f"  Stock cost (per share): ${S0:.2f}")
print(f"  Breakeven stock price: ${S0 - premium:.2f}")
print(f"  Max profit if not called: ${premium * 100:.2f} + stock gains")
print(f"  Max profit if called: ${(strike - S0 + premium) * 100:.2f}")

print("\n" + "="*80)
print("KEY INSIGHT:")
print("If you're seeing negative MC P&L, possible causes:")
print("1. Strikes too close to current price (high assignment risk)")
print("2. Premium too small relative to upside capping")
print("3. High IV means wide price swings → more assignment")
print("4. Short DTE means less time for stock appreciation")
print("="*80)
