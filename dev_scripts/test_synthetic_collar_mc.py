"""Debug Synthetic Collar MC fields specifically."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Silence logging
import logging
logging.basicConfig(level=logging.CRITICAL)
for name in ["streamlit", "yfinance"]:
    logging.getLogger(name).setLevel(logging.CRITICAL)

from strategy_analysis import analyze_synthetic_collar

print("Testing Synthetic Collar MC fix with AAPL...")

params = {
    "target_long_delta": 0.80,
    "put_delta_target": -0.15,
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
}

try:
    df = analyze_synthetic_collar("AAPL", **params)
    
    if df.empty:
        print("⚠️  No Synthetic Collar opportunities found (may be normal)")
    else:
        print(f"✓ Found {len(df)} Synthetic Collar opportunities")
        print(f"\nColumns: {list(df.columns)}")
        
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
                    sample = df[col].dropna()
                    if len(sample) > 0:
                        print(f"  Sample values: {sample.iloc[0]:.2f}, {sample.iloc[-1]:.2f if len(sample) > 1 else 'N/A'}")
        
        # Check UnifiedScore
        if "UnifiedScore" in df.columns:
            print(f"\n✓ UnifiedScore range: {df['UnifiedScore'].min():.4f} - {df['UnifiedScore'].max():.4f}")
        
        # Show first row
        print("\n=== First Row Sample ===")
        first = df.iloc[0]
        for col in ["Strategy", "Ticker", "Exp", "Days", "ROI%_ann", "MC_ROI_ann%", 
                    "MC_ExpectedPnL", "MC_PnL_p5", "Score", "UnifiedScore"]:
            if col in first.index:
                val = first[col]
                print(f"{col:20s}: {val}")
        
        print("\n✅ TEST COMPLETE")
        
except Exception as e:
    print(f"❌ ERROR: {e}")
    import traceback
    traceback.print_exc()
