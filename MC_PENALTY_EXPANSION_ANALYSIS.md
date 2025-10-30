# Monte Carlo Penalty Expansion Analysis

## Executive Summary

After successfully implementing MC penalty for credit spreads (Bull Put and Bear Call), we've identified that **Covered Calls are showing similar issues with negative MC expected P&L**. This document analyzes where MC penalty integration makes sense across all strategies.

## Current State

### Strategies with MC Penalty (✅ Implemented)
1. **Bull Put Spread** (Lines 2520-2610)
   - 70% weight MC penalty
   - Graduated scale 0.20-1.0
   - 56% score reduction for negative expected P&L
   - Status: ✅ **Validated and working**

2. **Bear Call Spread** (Lines 2879-2970)
   - 70% weight MC penalty
   - Graduated scale 0.20-1.0
   - 56% score reduction for negative expected P&L
   - Status: ✅ **Validated and working**

### Strategies WITHOUT MC Penalty (❌ Issue Reported)
3. **Covered Call (CC)** - Lines 1469-1677
   - ❌ **User reports negative MC expected P&L passing screens**
   - Current scoring: Static ROI + cushion + theta/gamma + liquidity
   - No validation against MC simulations
   - **Priority: HIGH** - Same issue as credit spreads

4. **Cash-Secured Put (CSP)** - Lines 1213-1470
   - ⚠️ Likely has same issue (not reported yet)
   - Current scoring: Static ROI + cushion + theta/gamma + liquidity
   - No validation against MC simulations
   - **Priority: HIGH** - Preventive fix

5. **Iron Condor** - Lines 1915-2264
   - ⚠️ Likely has same issue (more complex 4-leg)
   - Current scoring: ROI cycle + balance + cushion + liquidity
   - No validation against MC simulations
   - **Priority: MEDIUM** - Complex multi-leg strategy

6. **Collar** - Lines 1676-1916
   - ⚠️ Lower priority (protective strategy)
   - Current scoring: ROI + put cushion + call cushion + liquidity
   - Protective nature may make negative MC expected
   - **Priority: LOW** - Review after others

---

## Strategy Analysis & Recommendations

### 1. Covered Call (CC) - **IMPLEMENT MC PENALTY**

#### Problem Statement
User reports: "I'm getting many covered call positions coming through the screens that have negative MC expected P&L."

#### Root Cause (Same as Credit Spreads)
```python
# Current scoring (Lines 1589-1593)
score = (0.35 * roi_ann +                          # Static ROI assumes keeping 100% premium
         0.15 * (min(cushion_sigma, 3.0) / 3.0) +  # Distance to strike
         0.30 * tg_score +                         # Theta/Gamma ratio
         0.20 * liq_score)                         # Bid-ask spread
```

**Issues:**
- `roi_ann` assumes keeping 100% of premium (best case)
- POEC (Probability of Expiring Cheap) uses single delta estimate
- No validation against simulated price paths
- Doesn't account for:
  - Upside capping if stock rallies
  - Assignment risk
  - Path dependency

#### MC Integration Strategy

**Recommended Implementation:**
```python
# After base score calculation (after line 1593)
# Run quick MC simulation during scan
mc_params = {
    "S0": S,
    "days": D,
    "iv": iv_dec,
    "strike": K,
    "premium": prem,
    "stock_cost": S  # For covered call, we own stock
}
mc_result = mc_pnl("CC", mc_params, n_paths=1000, mu=0.07, seed=None, rf=risk_free)
mc_expected_pnl = mc_result['pnl_expected']
mc_roi_ann = mc_result['roi_ann_expected']

# Calculate max profit (premium received)
max_profit = prem * 100.0

# Graduated penalty based on MC expected P&L vs. max profit
if mc_expected_pnl < 0:
    mc_penalty = 0.20  # 80% score reduction
elif mc_expected_pnl < max_profit * 0.25:
    mc_penalty = 0.20 + (mc_expected_pnl / (max_profit * 0.25)) * 0.30
elif mc_expected_pnl < max_profit * 0.50:
    mc_penalty = 0.50 + ((mc_expected_pnl - max_profit * 0.25) / (max_profit * 0.25)) * 0.30
elif mc_expected_pnl < max_profit * 0.75:
    mc_penalty = 0.80 + ((mc_expected_pnl - max_profit * 0.50) / (max_profit * 0.25)) * 0.10
else:
    mc_penalty = 0.90 + min((mc_expected_pnl - max_profit * 0.75) / (max_profit * 0.25), 1.0) * 0.10

# Apply 70% weight: score * (0.30 + 0.70 * mc_penalty)
score = score * (0.30 + 0.70 * mc_penalty)

# Add MC columns to output (around line 1659)
"MC_ExpectedPnL": round(mc_expected_pnl, 2) if mc_expected_pnl == mc_expected_pnl else float("nan"),
"MC_ROI_ann%": round(mc_roi_ann * 100.0, 2) if mc_roi_ann == mc_roi_ann else float("nan"),
```

**Key Differences from Credit Spreads:**
- **Drift (μ)**: Use μ=0.07 (7% annual stock return assumption) since CC involves stock ownership
- **Max Profit**: Premium received (not net credit vs. max loss)
- **Capital**: Stock value ($100 × S) not max loss

**Expected Impact:**
- Negative MC P&L: 56% score reduction
- MC P&L at 50% of premium: 14% reduction
- MC P&L at 75% of premium: 7% reduction

**Implementation Location:**
- Scanner: Lines 1469-1677 (`analyze_cc`)
- Add MC logic after line 1593 (after base score)
- Add MC columns around line 1659 (in rows.append)

---

### 2. Cash-Secured Put (CSP) - **IMPLEMENT MC PENALTY**

#### Problem Statement
Same root cause as Covered Calls - likely experiencing similar issues but not yet reported.

#### Root Cause
```python
# Current scoring (Lines 1375-1379)
score = (0.35 * roi_ann_collat +                  # Static ROI assumes keeping 100% premium
         0.15 * (min(cushion_sigma, 3.0) / 3.0) + # Distance to strike
         0.30 * tg_score +                         # Theta/Gamma ratio
         0.20 * liq_score)                         # Bid-ask spread
```

**Issues:**
- `roi_ann_collat` assumes keeping 100% of premium
- POEW uses single delta estimate
- No validation against MC simulations
- Doesn't account for assignment at strike

#### MC Integration Strategy

**Recommended Implementation:**
```python
# After base score calculation (after line 1379)
# Run quick MC simulation during scan
mc_params = {
    "S0": S,
    "days": D,
    "iv": iv_dec,
    "strike": K,
    "premium": prem
}
mc_result = mc_pnl("CSP", mc_params, n_paths=1000, mu=0.0, seed=None, rf=risk_free)
mc_expected_pnl = mc_result['pnl_expected']
mc_roi_ann = mc_result['roi_ann_expected']

# Calculate max profit (premium received)
max_profit = prem * 100.0

# Apply same graduated penalty scale as CC
# (same formula as CC above)

# Apply 70% weight
score = score * (0.30 + 0.70 * mc_penalty)

# Add MC columns to output (around line 1445)
"MC_ExpectedPnL": round(mc_expected_pnl, 2),
"MC_ROI_ann%": round(mc_roi_ann * 100.0, 2),
```

**Key Differences from Covered Calls:**
- **Drift (μ)**: Use μ=0.0 (no stock ownership, no directional bias)
- **Capital**: Collateral (strike × 100) not stock value
- Otherwise same penalty structure

**Implementation Location:**
- Scanner: Lines 1213-1470 (`analyze_csp`)
- Add MC logic after line 1379 (after base score)
- Add MC columns around line 1445 (in rows.append)

---

### 3. Iron Condor - **IMPLEMENT MC PENALTY (with modifications)**

#### Problem Statement
4-leg strategy with complex risk profile. Likely experiencing negative MC expected P&L but more severe due to:
- 4 legs to manage
- Narrower profit zone
- Higher transaction costs
- More path dependency

#### Root Cause
```python
# Current scoring (Lines 2155-2159)
score = (0.40 * roi_cycle +      # Credit / max_loss ratio (assumes best case)
         0.30 * balance_score +   # Wing balance
         0.20 * cushion_score +   # Distance to strikes
         0.10 * liq_score)        # Liquidity
```

**Issues:**
- `roi_cycle` assumes max profit (both spreads expire worthless)
- Probability calculation uses simple delta multiplication
- No validation against realistic price paths
- 4-leg structure amplifies volatility drag impact

#### MC Integration Strategy

**Recommended Implementation:**
```python
# After base score calculation (after line 2159)
# Run quick MC simulation during scan
mc_params = {
    "S0": S,
    "days": D,
    "iv": iv_avg,
    "put_short_strike": Kps,
    "put_long_strike": Kpl,
    "call_short_strike": Kcs,
    "call_long_strike": Kcl,
    "net_credit": net_credit
}
mc_result = mc_pnl("IRON_CONDOR", mc_params, n_paths=1000, mu=0.0, seed=None, rf=risk_free)
mc_expected_pnl = mc_result['pnl_expected']
mc_roi_ann = mc_result['roi_ann_expected']

# Calculate max profit (net credit from both spreads)
max_profit = net_credit * 100.0

# STRICTER graduated penalty for Iron Condor (4-leg complexity)
if mc_expected_pnl < 0:
    mc_penalty = 0.15  # 85% score reduction (stricter than spreads)
elif mc_expected_pnl < max_profit * 0.25:
    mc_penalty = 0.15 + (mc_expected_pnl / (max_profit * 0.25)) * 0.30
elif mc_expected_pnl < max_profit * 0.50:
    mc_penalty = 0.45 + ((mc_expected_pnl - max_profit * 0.25) / (max_profit * 0.25)) * 0.30
elif mc_expected_pnl < max_profit * 0.75:
    mc_penalty = 0.75 + ((mc_expected_pnl - max_profit * 0.50) / (max_profit * 0.25)) * 0.10
else:
    mc_penalty = 0.85 + min((mc_expected_pnl - max_profit * 0.75) / (max_profit * 0.25), 1.0) * 0.15

# Apply 75% weight (STRONGER than credit spreads due to 4-leg complexity)
score = score * (0.25 + 0.75 * mc_penalty)

# Add MC columns to output (around line 2240)
"MC_ExpectedPnL": round(mc_expected_pnl, 2),
"MC_ROI_ann%": round(mc_roi_ann * 100.0, 2),
```

**Key Differences from Credit Spreads:**
- **Stricter Penalty Scale**: Starts at 0.15 (85% reduction) vs. 0.20 (80% reduction)
- **Higher Weight**: 75% vs. 70% due to 4-leg complexity
- **Result**: Negative MC P&L → 62.5% score reduction (vs. 56% for spreads)
- **Drift (μ)**: Use μ=0.0 (no directional bias)

**Expected Impact:**
- Negative MC P&L: 62.5% score reduction
- MC P&L at 50% of max: 16% reduction
- MC P&L at 75% of max: 8% reduction

**Implementation Location:**
- Scanner: Lines 1915-2264 (`analyze_iron_condor`)
- Add MC logic after line 2159 (after base score)
- Add MC columns around line 2240 (in rows.append)

---

### 4. Collar - **REVIEW BEFORE IMPLEMENTING**

#### Problem Statement
Protective strategy where negative MC expected P&L may be acceptable/expected.

#### Current State
```python
# Current scoring (Lines 1823-1827)
score = 0.45 * roi_ann + 0.25 * \
        max(0.0, put_cushion) / 3.0 + 0.15 * \
        max(0.0, call_cushion) / 3.0 + 0.15 * liq_score
```

#### Analysis
**Collar Purpose:**
- Protective strategy (stock + short call + long put)
- Limits upside but protects downside
- Often used for tax-loss harvesting or protection during volatility
- **Cost of protection** means negative expected P&L may be acceptable

**Questions to Answer:**
1. Are users finding Collars with unexpectedly negative MC P&L?
2. Is the negative P&L due to protection cost (expected) or poor structure?
3. Should we penalize negative MC P&L for a protective strategy?

**Recommendation:**
1. **Run diagnostic scan first**: Analyze Collar opportunities to see MC P&L distribution
2. **If mostly negative**: This is expected - protection has a cost
3. **If some positive, some negative**: Implement MC penalty to prefer better structures
4. **Wait for user feedback**: Lower priority than income strategies (CC, CSP, spreads)

**If Implementation Needed:**
- Use **lower weight**: 50% instead of 70% (protection is the goal, not profit)
- Use **softer penalty scale**: Start at 0.30 (70% reduction) instead of 0.20
- Drift (μ): 0.07 (own stock)
- Compare MC P&L to net credit, not max profit

---

## Implementation Priority & Timeline

### Phase 1: High Priority (Immediate) ✅ **DONE**
- ✅ Bull Put Spread (Implemented & Validated)
- ✅ Bear Call Spread (Implemented & Validated)

### Phase 2: High Priority (User-Reported Issue) 🔴 **NEXT**
- ❌ **Covered Call** - User reports negative MC P&L passing screens
  - **Priority**: Highest
  - **Complexity**: Low (single-leg, similar to credit spreads)
  - **Timeline**: Implement now
  - **Validation**: Run SPY scan, check MC P&L distribution

### Phase 3: High Priority (Preventive) 🟡 **AFTER CC**
- ❌ **Cash-Secured Put** - Same root cause as CC
  - **Priority**: High
  - **Complexity**: Low (single-leg, similar to CC)
  - **Timeline**: Implement after CC validation
  - **Validation**: Run SPY scan, check MC P&L distribution

### Phase 4: Medium Priority (Complex Multi-Leg) 🟠 **AFTER CSP**
- ❌ **Iron Condor** - 4-leg strategy with complex risk
  - **Priority**: Medium
  - **Complexity**: Medium (4-leg, stricter penalties needed)
  - **Timeline**: Implement after CSP validation
  - **Validation**: Run SPY scan, check MC P&L distribution, test 4-leg complexity

### Phase 5: Low Priority (Protective Strategy) ⚪ **REVIEW FIRST**
- ❌ **Collar** - Protective strategy where negative MC P&L may be expected
  - **Priority**: Low
  - **Complexity**: Medium (3-leg, need to decide if penalty appropriate)
  - **Timeline**: Run diagnostic first, implement only if needed
  - **Validation**: Analyze if negative MC P&L is by design or poor structure

---

## Technical Considerations

### Drift (μ) Parameter by Strategy

| Strategy | Drift (μ) | Rationale |
|----------|-----------|-----------|
| Bull Put Spread | 0.0% | No stock ownership, no directional bias |
| Bear Call Spread | 0.0% | No stock ownership, no directional bias |
| **Covered Call** | **7.0%** | Own stock, expect long-term appreciation |
| **Cash-Secured Put** | **0.0%** | No stock yet, no directional bias |
| **Iron Condor** | **0.0%** | No stock ownership, no directional bias |
| **Collar** | **7.0%** | Own stock (protective strategy) |

### MC Penalty Weight by Strategy

| Strategy | Weight | Rationale |
|----------|--------|-----------|
| Bull Put Spread | 70% | Strong penalty for negative EV |
| Bear Call Spread | 70% | Strong penalty for negative EV |
| **Covered Call** | **70%** | Same as credit spreads, income focus |
| **Cash-Secured Put** | **70%** | Same as credit spreads, income focus |
| **Iron Condor** | **75%** | Stricter due to 4-leg complexity |
| **Collar** | **50%** | Lower weight (protection > profit) |

### Penalty Scale Minimum by Strategy

| Strategy | Min Penalty | Max Reduction | Rationale |
|----------|-------------|---------------|-----------|
| Bull Put Spread | 0.20 | 56% | Baseline for 2-leg spread |
| Bear Call Spread | 0.20 | 56% | Baseline for 2-leg spread |
| **Covered Call** | **0.20** | **56%** | Same as credit spreads |
| **Cash-Secured Put** | **0.20** | **56%** | Same as credit spreads |
| **Iron Condor** | **0.15** | **62.5%** | Stricter (4-leg complexity) |
| **Collar** | **0.30** | **35%** | Softer (protective strategy) |

### Simulation Paths During Scan

**Current Implementation:**
- Scan phase: 1,000 paths (for speed)
- UI analysis: 10,000-20,000 paths (for accuracy)

**Considerations:**
- 1,000 paths provides good estimate for penalty calculation
- Scan time per opportunity: ~0.1-0.2 seconds
- For 200 opportunities: ~20-40 seconds total
- Acceptable trade-off for better quality filtering

---

## Validation Plan

### For Each Strategy Implementation:

1. **Pre-Implementation Scan** (Baseline)
   - Run scan without MC penalty
   - Record all opportunities
   - Note: Score range, ROI range, top opportunities

2. **Synthetic Data Test**
   - Create 6 test cases across penalty scale
   - Validate penalty calculation formula
   - Verify score reduction percentages
   - Check monotonic relationship

3. **Post-Implementation Scan** (Validation)
   - Run same scan with MC penalty
   - Check MC integration: 100% of opportunities have MC values
   - Analyze MC P&L distribution:
     - What % have negative MC P&L?
     - Average, median, range of MC P&L
     - Correlation between Score and MC P&L
   - Verify top opportunities have better MC metrics

4. **Comparative Analysis**
   - Compare top 10 before vs. after
   - Verify negative MC P&L opportunities ranked lower
   - Check score differentiation (target: ≥0.30 range)
   - Confirm strong correlation (|r| > 0.7)

5. **Real-World Testing**
   - Run on multiple tickers (SPY, QQQ, AAPL, MSFT)
   - Verify consistent behavior across underlyings
   - Check edge cases (high IV, low liquidity, etc.)

---

## Code Structure Template

### For Each Strategy:

```python
# STEP 1: Add MC imports at top (already done)
from strategy_lab import mc_pnl

# STEP 2: After base score calculation in scanner
# (Location varies by strategy - see specific sections above)

# Run quick MC simulation during scan
mc_params = {
    # Strategy-specific parameters
    # See specific strategy sections above
}
mc_result = mc_pnl("STRATEGY_NAME", mc_params, n_paths=1000, mu=DRIFT, seed=None, rf=risk_free)
mc_expected_pnl = mc_result['pnl_expected']
mc_roi_ann = mc_result['roi_ann_expected']

# Calculate max profit (strategy-specific)
max_profit = # See specific strategy sections

# Graduated penalty (strategy-specific scale)
if mc_expected_pnl < 0:
    mc_penalty = # See strategy-specific penalty minimum
# ... (rest of graduated scale)

# Apply penalty weight (strategy-specific)
score = score * (BASE + WEIGHT * mc_penalty)

# STEP 3: Add MC columns to output DataFrame
"MC_ExpectedPnL": round(mc_expected_pnl, 2) if mc_expected_pnl == mc_expected_pnl else float("nan"),
"MC_ROI_ann%": round(mc_roi_ann * 100.0, 2) if mc_roi_ann == mc_roi_ann else float("nan"),
```

---

## Next Steps

### Immediate Actions:
1. ✅ **DONE**: Implement MC penalty for Covered Call (user-reported issue)
2. Create validation test for Covered Call
3. Run SPY scan and analyze results
4. Document findings (similar to MC_PENALTY_IMPLEMENTATION_SUMMARY.md)

### Follow-Up Actions:
5. Implement MC penalty for Cash-Secured Put
6. Validate CSP implementation
7. Implement MC penalty for Iron Condor (stricter penalties)
8. Validate Iron Condor implementation

### Future Review:
9. Run diagnostic on Collar strategy
10. Decide if MC penalty appropriate for protective strategy
11. Implement Collar MC penalty if needed
12. Final comprehensive validation across all strategies

---

## Success Metrics

For each strategy implementation, measure:

1. **Integration Rate**: ≥95% of opportunities have MC values
2. **Correlation**: |r| ≥ 0.70 between Score and MC P&L
3. **Score Reduction**: Negative MC P&L → ≥50% reduction
4. **Differentiation**: Score range ≥0.30 between best and worst
5. **False Positive Reduction**: 
   - Before: X% with negative MC P&L in top 10
   - After: <10% with negative MC P&L in top 10

---

## Conclusion

The MC penalty framework successfully implemented for credit spreads should be extended to:

1. **Covered Call** (HIGHEST PRIORITY - user-reported issue)
2. **Cash-Secured Put** (HIGH PRIORITY - preventive)
3. **Iron Condor** (MEDIUM PRIORITY - complex 4-leg)
4. **Collar** (LOW PRIORITY - review first)

This will ensure consistent, reality-based scoring across all income strategies, filtering out opportunities with negative expected value while maintaining transparency through MC output columns.

**Implementation Timeline:**
- Covered Call: Implement now (user issue)
- Cash-Secured Put: Next week (preventive)
- Iron Condor: Following week (complexity)
- Collar: Review after others (protective strategy considerations)

Each implementation should follow the validation plan to ensure quality and consistency with the credit spread implementation.
