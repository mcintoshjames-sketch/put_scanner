"""Diagnose why Synthetic Collar MC fields are missing - check prelim score gating."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Silence most logging but allow stderr
import logging
logging.basicConfig(level=logging.WARNING)

# Temporarily patch _maybe_mc to log gating decisions
original_maybe_mc = None

def patched_maybe_mc(strategy_name, mc_params, *, rf, mu, prelim_score, perf_cfg, exp_counter):
    """Instrumented version that logs gating decisions."""
    pre_min = perf_cfg.get("pre_mc_score_min")
    cap = perf_cfg.get("max_mc_per_exp")
    count = exp_counter.get("count", 0)
    
    gated_by_score = False
    gated_by_cap = False
    
    if pre_min is not None and isinstance(prelim_score, (int, float)):
        if prelim_score < float(pre_min):
            gated_by_score = True
            
    if cap is not None and count >= cap:
        gated_by_cap = True
    
    if strategy_name == "SYNTHETIC_COLLAR":
        if gated_by_score:
            print(f"  GATED by score: prelim={prelim_score:.4f} < threshold={pre_min}", file=sys.stderr)
        elif gated_by_cap:
            print(f"  GATED by cap: count={count} >= cap={cap}", file=sys.stderr)
        else:
            print(f"  ✓ Running MC: prelim={prelim_score:.4f}, count={count}/{cap}", file=sys.stderr)
    
    return original_maybe_mc(strategy_name, mc_params, rf=rf, mu=mu, 
                            prelim_score=prelim_score, perf_cfg=perf_cfg, 
                            exp_counter=exp_counter)

# Monkey-patch before importing
from strategy_analysis import _maybe_mc as orig_mc
original_maybe_mc = orig_mc
import strategy_analysis
strategy_analysis._maybe_mc = patched_maybe_mc

from strategy_analysis import analyze_synthetic_collar

print("=" * 70)
print("Synthetic Collar MC Gating Diagnostic")
print("=" * 70)

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
    print("\nTesting with AAPL...")
    df = analyze_synthetic_collar("AAPL", **params)
    
    if df.empty:
        print("\n⚠️  No Synthetic Collar opportunities found")
        print("   This could mean:")
        print("   - No suitable LEAPS calls available")
        print("   - No matching short-term short calls")
        print("   - All candidates filtered by liquidity/spread requirements")
    else:
        print(f"\n✓ Found {len(df)} Synthetic Collar opportunities")
        
        # Check MC columns
        mc_cols = ["MC_ExpectedPnL", "MC_ROI_ann%", "MC_PnL_p5"]
        for col in mc_cols:
            if col in df.columns:
                non_null = df[col].notna().sum()
                if non_null == 0:
                    print(f"\n❌ {col}: ALL VALUES ARE NaN")
                    print(f"   → MC was gated or failed for all candidates")
                else:
                    print(f"\n✓ {col}: {non_null}/{len(df)} populated")
        
        # Show prelim scores
        if "Score" in df.columns:
            print(f"\nPreliminary Score distribution:")
            print(f"  Min:  {df['Score'].min():.4f}")
            print(f"  Max:  {df['Score'].max():.4f}")
            print(f"  Mean: {df['Score'].mean():.4f}")
            
except Exception as e:
    print(f"\n❌ ERROR: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 70)
