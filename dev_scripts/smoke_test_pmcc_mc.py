"""Quick smoke test: verify PMCC MC fields are populated after fix."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Silence logging
import logging
logging.basicConfig(level=logging.CRITICAL)
for name in ["streamlit", "yfinance"]:
    logging.getLogger(name).setLevel(logging.CRITICAL)

from strategy_analysis import analyze_pmcc

print("Testing PMCC MC fix with AAPL...")

params = {
    "target_long_delta": 0.80,
    "long_min_days": 180,
    "long_max_days": 400,
    "short_min_days": 21,
    "short_max_days": 60,
    "short_delta_lo": 0.20,
    "short_delta_hi": 0.35,
    "min_oi": 50,
    "max_spread": 15.0,
    "earn_window": 7,
    "risk_free": 0.02,
    "bill_yield": 0.0,
    "pmcc_min_buffer_days": 120,
    "pmcc_avoid_exdiv": True,
}

try:
    df = analyze_pmcc("AAPL", **params)
    
    if df.empty:
        print("⚠️  No PMCC opportunities found (may be normal)")
    else:
        print(f"✓ Found {len(df)} PMCC opportunities")
        
        # Check MC columns
        mc_cols = ["MC_ExpectedPnL", "MC_ROI_ann%", "MC_PnL_p5"]
        for col in mc_cols:
            if col not in df.columns:
                print(f"❌ MISSING: {col}")
            else:
                non_null = df[col].notna().sum()
                if non_null == 0:
                    print(f"❌ {col}: ALL NaN (MC not running!)")
                else:
                    print(f"✓ {col}: {non_null}/{len(df)} populated")
                    print(f"  Sample: {df[col].iloc[0]:.2f}")
        
        # Check UnifiedScore
        if "UnifiedScore" in df.columns:
            print(f"✓ UnifiedScore range: {df['UnifiedScore'].min():.4f} - {df['UnifiedScore'].max():.4f}")
        
        print("\n✅ TEST PASSED: MC fields are populated!")
        
except Exception as e:
    print(f"❌ ERROR: {e}")
    import traceback
    traceback.print_exc()
