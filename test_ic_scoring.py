#!/usr/bin/env python3
"""Test Iron Condor scoring calibration"""

import sys
sys.path.insert(0, '/workspaces/put_scanner')

# Suppress Streamlit warnings
import warnings
warnings.filterwarnings('ignore')

from strategy_lab import analyze_iron_condor

print("Testing Iron Condor scoring calibration...")
print("=" * 60)

result = analyze_iron_condor(
    'SPY',
    min_days=10,
    days_limit=60,
    min_oi=50,
    max_spread=25.0,
    min_roi=0.01,
    min_cushion=0.0,
    earn_window=7,
    risk_free=0.05,
    spread_width_put=5.0,
    spread_width_call=5.0,
    target_delta_short=0.16,
    bill_yield=0.05
)

print(f'\nFound {len(result)} Iron Condors for SPY\n')

if not result.empty:
    print(result[['Exp', 'Days', 'ROI%_ann', 'Score']].to_string(index=False))
    print(f"\nScore range: {result['Score'].min():.4f} - {result['Score'].max():.4f}")
    print(f"Average score: {result['Score'].mean():.4f}")
else:
    print("No Iron Condors found")
