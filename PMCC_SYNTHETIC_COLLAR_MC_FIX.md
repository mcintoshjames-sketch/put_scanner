# PMCC & Synthetic Collar MC/EVPenalty Fix

## Problem Summary

PMCC and Synthetic Collar strategies in the Compare list were missing:
- `MC_ExpectedPnL` 
- `MC_ROI_ann%`
- `MC_PnL_p5`
- `EVPenalty` column (blank)

This caused these strategies to:
1. Not be penalized for negative Monte Carlo expected value
2. Have neutral tail risk (0.5) instead of actual p5 downside
3. Potentially rank too favorably compared to other strategies with negative MC EV

## Root Causes Found

### 1. NameError Bug in MC Computation (CRITICAL)
**Location**: `strategy_analysis.py` lines ~1131 and ~1360

Both `analyze_pmcc` and `analyze_synthetic_collar` had:
```python
try:
    prelim = score  # ❌ BUG: 'score' not yet defined!
    mc = _maybe_mc("PMCC", mc_params, rf=risk_free, mu=0.0, 
                   prelim_score=prelim, perf_cfg=perf_cfg, exp_counter={"count":0})
    mc_expected = mc.get("pnl_expected", float("nan"))
    mc_roi_ann = mc.get("roi_ann_expected", float("nan"))
    mc_p5 = mc.get("pnl_p5", float("nan"))
except Exception:
    mc_expected = float("nan"); mc_roi_ann = float("nan"); mc_p5 = float("nan")

score = unified_risk_reward_score(...)  # ← score defined AFTER MC call
```

**Impact**: 
- `prelim = score` raised `NameError` (undefined variable)
- Exception handler silently caught it and set all MC fields to NaN
- Monte Carlo **never actually ran** for PMCC/Synthetic Collar
- All MC columns were NaN, making them invisible to EVPenalty logic

### 2. Missing Ex-Dividend Initialization (SECONDARY)
**Location**: `strategy_analysis.py` Synthetic Collar analyzer

`next_ex_date` and `next_div` were referenced in ex-dividend guard logic but never initialized, causing potential `NameError` in that section as well.

PMCC had it but duplicated the call twice.

## Fixes Applied

### Fix 1: Remove Premature `prelim = score` Reference
Changed both PMCC and Synthetic Collar analyzers:
```python
try:
    # Pass None for prelim_score since we compute score after MC
    mc = _maybe_mc("PMCC", mc_params, rf=risk_free, mu=0.0, 
                   prelim_score=None, perf_cfg=perf_cfg, exp_counter={"count":0})
    mc_expected = mc.get("pnl_expected", float("nan"))
    mc_roi_ann = mc.get("roi_ann_expected", float("nan"))
    mc_p5 = mc.get("pnl_p5", float("nan"))
except Exception:
    mc_expected = float("nan"); mc_roi_ann = float("nan"); mc_p5 = float("nan")
```

**Rationale**: `_maybe_mc` already handles `prelim_score=None` gracefully (no pre-score filtering), so MC will run unconditionally for these strategies.

### Fix 2: Initialize Ex-Dividend Variables
Added to both analyzers before the short-leg loop:
```python
# Initialize ex-dividend info for assignment risk checks
next_ex_date, next_div = estimate_next_ex_div(stock)
```

## Verification Steps

### 1. Run Diagnostic Script
```bash
cd /workspaces/put_scanner
source .venv/bin/activate
python dev_scripts/diagnose_mc_fields.py
```

Expected output:
- ✓ MC_ExpectedPnL: non-null values present
- ✓ MC_ROI_ann%: non-null values present
- ✓ MC_PnL_p5: non-null values present
- ✓ UnifiedScore: computed and in range
- ✓ Rows with negative MC_ExpectedPnL: count shown

### 2. Check Compare Tab in UI
After running a scan with PMCC/Synthetic Collar:
1. Navigate to **Compare** tab
2. Verify PMCC/Synthetic Collar rows show:
   - Populated `MC_ExpectedPnL` values
   - Populated `MC_ROI_ann%` values
   - Populated `MC_PnL_p5` values (likely negative)
   - `Tail(p5%)` column shows percentage (not blank)
   - `EVPenalty` shows "NEG_EV" for rows with `MC_ExpectedPnL < 0`
3. Verify UnifiedScore ranking includes MC penalty (scores lower for negative EV)

## Technical Context

### How MC Fields Flow Through
1. **Strategy Analyzer** (`analyze_pmcc`, `analyze_synthetic_collar`):
   - Calls `_maybe_mc(...)` → returns dict with `pnl_expected`, `roi_ann_expected`, `pnl_p5`
   - Maps to DataFrame columns: `MC_ExpectedPnL`, `MC_ROI_ann%`, `MC_PnL_p5`
   - Calls `apply_unified_score(df)` → computes `UnifiedScore` with NEG_MC_PENALTY_FACTOR

2. **Compare Builder** (`compare_utils.build_compare_dataframe`):
   - Selects columns including MC fields for each strategy
   - Concatenates all strategy DataFrames
   - Returns unified DataFrame with MC columns preserved

3. **Compare Tab** (`strategy_lab.py` tab 9):
   - Computes `Tail(p5%) = (MC_PnL_p5 / CapitalAtRisk) * 100`
   - Computes `EVPenalty = "NEG_EV" if MC_ExpectedPnL < 0 else ""`
   - Sorts by `UnifiedScore` (which already includes MC penalty)

### Why This Bug Was Silent
- Python's try/except caught the `NameError` without logging
- MC fields defaulted to NaN (not an error state)
- UI showed blank cells (NaN renders as empty)
- Scoring still worked (fell back to deterministic ROI)
- No warnings or errors surfaced to user

## Files Modified
- `/workspaces/put_scanner/strategy_analysis.py`:
  - Fixed PMCC MC call (line ~1131)
  - Fixed Synthetic Collar MC call (line ~1360)
  - Added ex-dividend initialization in both analyzers

## Diagnostic Script Created
- `/workspaces/put_scanner/dev_scripts/diagnose_mc_fields.py`:
  - Tests PMCC and Synthetic Collar analyzers directly
  - Reports MC column presence and population
  - Shows sample values and negative EV counts

## Next Steps
1. Run diagnostic script to confirm MC is now computing
2. Test in UI with PMCC/Synthetic Collar scan
3. Verify EVPenalty and Tail(p5%) columns populate correctly
4. Compare ranking before/after fix (negative EV strategies should rank lower)

## Related Documentation
- Monte Carlo implementation: `options_math.py` → `mc_pnl()`
- Scoring logic: `scoring_utils.py` → `compute_unified_score()`
- Performance gating: `strategy_analysis.py` → `_maybe_mc()`
- Compare builder: `compare_utils.py` → `build_compare_dataframe()`
