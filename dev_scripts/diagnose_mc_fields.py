"""Diagnose MC field presence in PMCC and Synthetic Collar strategy outputs.

This script runs small scans for PMCC and SYNTHETIC_COLLAR strategies and inspects
whether MC_ExpectedPnL, MC_ROI_ann%, and MC_PnL_p5 columns are present and populated.
"""

import sys
import os
import pandas as pd

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Suppress Streamlit warnings
import logging
logging.getLogger().setLevel(logging.CRITICAL)
for name in ["streamlit", "streamlit.runtime", "streamlit.runtime.scriptrunner_utils", "streamlit.runtime.caching"]:
    logger = logging.getLogger(name)
    logger.setLevel(logging.CRITICAL)
    logger.disabled = True

from strategy_analysis import analyze_pmcc, analyze_synthetic_collar


def diagnose_strategy(name: str, analyzer_func, ticker: str, params: dict):
    """Run analyzer and report MC field status."""
    print(f"\n{'='*60}")
    print(f"Strategy: {name}")
    print(f"Ticker: {ticker}")
    print(f"{'='*60}")
    
    try:
        df = analyzer_func(ticker, **params)
        
        if df.empty:
            print("❌ DataFrame is EMPTY")
            return
        
        print(f"✓ Returned {len(df)} rows")
        print(f"✓ Columns: {list(df.columns)}")
        
        # Check MC columns
        mc_cols = ["MC_ExpectedPnL", "MC_ROI_ann%", "MC_PnL_p5"]
        for col in mc_cols:
            if col not in df.columns:
                print(f"❌ Missing column: {col}")
            else:
                non_null = df[col].notna().sum()
                if non_null == 0:
                    print(f"⚠️  Column {col} exists but ALL values are NaN")
                else:
                    print(f"✓ Column {col}: {non_null}/{len(df)} non-null values")
                    sample_val = df[col].dropna().iloc[0] if non_null > 0 else None
                    print(f"  Sample value: {sample_val}")
        
        # Check UnifiedScore
        if "UnifiedScore" in df.columns:
            non_null = df["UnifiedScore"].notna().sum()
            print(f"✓ UnifiedScore: {non_null}/{len(df)} non-null")
            if non_null > 0:
                print(f"  Range: {df['UnifiedScore'].min():.4f} - {df['UnifiedScore'].max():.4f}")
        else:
            print("❌ Missing UnifiedScore column")
        
        # Check EVPenalty logic
        if "MC_ExpectedPnL" in df.columns:
            neg_ev_count = (df["MC_ExpectedPnL"] < 0).sum()
            print(f"✓ Rows with negative MC_ExpectedPnL: {neg_ev_count}/{len(df)}")
        
        # Show first row details
        print("\nFirst row sample:")
        first = df.iloc[0]
        for col in ["Strategy", "Ticker", "Exp", "ROI%_ann", "MC_ROI_ann%", 
                    "MC_ExpectedPnL", "MC_PnL_p5", "Score", "UnifiedScore"]:
            if col in first.index:
                print(f"  {col}: {first[col]}")
        
    except Exception as e:
        print(f"❌ Error running analyzer: {e}")
        import traceback
        traceback.print_exc()


def main():
    print("MC Field Diagnostic for PMCC and Synthetic Collar")
    print("="*60)
    
    # PMCC params
    pmcc_params = {
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
        "pmcc_long_leg_min_oi": 50,
        "pmcc_long_leg_max_spread": 15.0,
    }
    
    # Synthetic Collar params
    syn_params = {
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
        "syn_min_floor_sigma": 1.0,
        "syn_min_buffer_days": 120,
        "syn_avoid_exdiv": True,
        "syn_long_leg_min_oi": 50,
        "syn_long_leg_max_spread": 15.0,
        "syn_put_leg_min_oi": 50,
        "syn_put_leg_max_spread": 15.0,
    }
    
    # Test with liquid tickers
    test_tickers = ["AAPL", "SPY", "MSFT"]
    
    for ticker in test_tickers:
        diagnose_strategy("PMCC", analyze_pmcc, ticker, pmcc_params)
        print("\n")
        diagnose_strategy("SYNTHETIC_COLLAR", analyze_synthetic_collar, ticker, syn_params)
        print("\n" + "="*60)
        # Only test one ticker for now to keep output manageable
        break
    
    print("\n✅ Diagnostic complete")


if __name__ == "__main__":
    main()
