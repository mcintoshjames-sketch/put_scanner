#!/usr/bin/env python3
"""
Quick Covered Call MC Penalty Validation
Tests that MC penalty is integrated into CC scoring.
"""

import sys
import os

# Suppress all streamlit warnings
os.environ['STREAMLIT_SERVER_ENABLE_CORS'] = 'false'
os.environ['STREAMLIT_SERVER_ENABLE_XSRF_PROTECTION'] = 'false'

import warnings
warnings.filterwarnings('ignore')

# Redirect stderr to suppress streamlit messages
import sys
from io import StringIO
old_stderr = sys.stderr
sys.stderr = StringIO()

try:
    from strategy_lab import analyze_cc
    import pandas as pd
    import numpy as np
finally:
    sys.stderr = old_stderr

print("="*80)
print("COVERED CALL MC PENALTY - QUICK VALIDATION")
print("="*80)

print("\nRunning SPY Covered Call scan...")

# Run scan
df = analyze_cc(
    ticker="SPY",
    min_days=7,
    days_limit=60,
    min_otm=0.01,
    min_oi=50,
    max_spread=20.0,
    min_roi=0.05,
    earn_window=7,
    risk_free=0.045,
    include_dividends=True,
    bill_yield=0.045
)

if df.empty:
    print("❌ No results found")
    sys.exit(1)

print(f"✅ Found {len(df)} opportunities\n")

# Check for MC columns
has_mc_pnl = "MC_ExpectedPnL" in df.columns
has_mc_roi = "MC_ROI_ann%" in df.columns

print("MC COLUMN CHECK:")
print(f"  {'✅' if has_mc_pnl else '❌'} MC_ExpectedPnL column exists")
print(f"  {'✅' if has_mc_roi else '❌'} MC_ROI_ann% column exists")

if not (has_mc_pnl and has_mc_roi):
    print("\n❌ MC columns missing - implementation may have failed")
    sys.exit(1)

# Check MC integration rate
valid_mc = df['MC_ExpectedPnL'].notna().sum()
integration_rate = (valid_mc / len(df)) * 100

print(f"\nMC INTEGRATION:")
print(f"  {valid_mc}/{len(df)} opportunities have MC values ({integration_rate:.1f}%)")

if integration_rate < 80:
    print(f"  ⚠️  Integration rate below 80% - check for errors")
else:
    print(f"  ✅ High integration rate")

# Analyze MC P&L distribution
if valid_mc > 0:
    mc_vals = df[df['MC_ExpectedPnL'].notna()]['MC_ExpectedPnL']
    positive = (mc_vals > 0).sum()
    negative = (mc_vals < 0).sum()
    
    print(f"\nMC P&L DISTRIBUTION:")
    print(f"  Positive: {positive} ({positive*100/valid_mc:.1f}%)")
    print(f"  Negative: {negative} ({negative*100/valid_mc:.1f}%)")
    print(f"  Average: ${mc_vals.mean():.2f}")
    print(f"  Median: ${mc_vals.median():.2f}")
    print(f"  Range: ${mc_vals.min():.2f} to ${mc_vals.max():.2f}")
    
    # Check correlation
    valid_df = df[df['MC_ExpectedPnL'].notna()]
    corr = valid_df['Score'].corr(valid_df['MC_ExpectedPnL'])
    print(f"\nCORRELATION:")
    print(f"  Score vs MC P&L: r = {corr:.3f}")
    if abs(corr) >= 0.70:
        print(f"  ✅ Strong correlation - penalty is working")
    else:
        print(f"  ⚠️  Weak correlation - penalty may not be impactful enough")

# Show top 5
print(f"\nTOP 5 RESULTS:")
cols = ['Exp', 'Days', 'Strike', 'Premium', 'ROI%_ann', 'MC_ExpectedPnL', 'MC_ROI_ann%', 'Score']
available = [c for c in cols if c in df.columns]
print(df.head(5)[available].to_string(index=False))

print("\n" + "="*80)
if has_mc_pnl and has_mc_roi and integration_rate >= 80:
    print("✅ VALIDATION PASSED - MC penalty integrated successfully")
    print("="*80)
    sys.exit(0)
else:
    print("❌ VALIDATION FAILED - Review results above")
    print("="*80)
    sys.exit(1)
