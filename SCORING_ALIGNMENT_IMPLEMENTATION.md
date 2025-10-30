# Scoring Alignment Implementation

**Date:** October 30, 2025  
**Status:** ✅ Complete - All strategies updated

## Overview

This document describes the implementation of **Option A: Integrated Penalty Multipliers** to align aggregate ranking scores with best-practice fit criteria. Previously, opportunities could score highly based on ROI potential while failing multiple best-practice checks (tenor, volume/OI, earnings proximity, theta/gamma ratios).

## Problem Statement

**Before:** Scoring and best-practice fit evaluation were decoupled:
- Scoring happened during scan (optimizing for ROI, theta/gamma efficiency, liquidity)
- Best-practice fit evaluation happened later in UI (checking tenor, volume/OI, earnings, etc.)
- Result: High-scoring opportunities could fail many fit checks and still rank #1

**Example Misalignments:**
- 7 DTE CSP with 150% ROI scored high but failed tenor sweet spot (21-45 DTE)
- OI=500, Volume=75 (ratio=0.15) scored same as Volume=250 (ratio=0.5) 
- Earnings in 3 days not penalized in scoring
- Theta/Gamma=0.6 (below 1.0 threshold) still received 30% weight

## Solution: Integrated Penalty Multipliers

Applied **standard penalties** to base scores after calculating opportunity score:

```python
final_score = base_score × tenor_penalty × vol_penalty × earnings_penalty × tg_penalty
```

### Penalty Structure

| Check | Passing | Moderate | Poor | Hard Filter |
|-------|---------|----------|------|-------------|
| **Tenor (DTE)** | 1.0× (in sweet spot) | - | 0.70× (outside) | - |
| **Volume/OI** | 1.0× (≥0.5) | 0.85× (≥0.25) | 0.65× (< 0.25) | - |
| **Earnings** | 1.0× (safe) | 0.60× (within cycle+7d) | - | ✅ Skip if ≤3 days |
| **Theta/Gamma** | 1.0× (≥1.0) | 0.85× (≥0.5) | 0.70× (< 0.5) | - |
| **Dividend Risk** | - | - | - | ✅ Skip Collar if high |
| **IC Liquidity** | - | - | - | ✅ Skip if any leg OI < 50 |

### Hard Filters (Intolerable Risks)

Opportunities are **completely excluded** from results if:

1. **Earnings within 3 days** (CSP, CC, Bull Put, Bear Call)
   - Extreme volatility event risk
   - Assignment/execution risk too high

2. **High dividend assignment risk** (Collar only)
   - Call will likely be assigned for dividend capture
   - Dividend > call extrinsic value

3. **Extremely low liquidity on any leg** (Iron Condor only)
   - 4-leg strategy requires higher liquidity
   - Any leg with OI < 50 excluded (stricter than other strategies)

## Implementation by Strategy

### 1. Cash-Secured Put (CSP)

**Lines:** 1372-1418  
**Tenor Sweet Spot:** 21-45 DTE  
**Penalties Applied:**
- ✅ Tenor (21-45 DTE)
- ✅ Volume/OI ratio
- ✅ Earnings proximity
- ✅ Theta/Gamma ratio
- ✅ Hard filter: Earnings ≤3 days

**Base Score Formula:**
```python
score = (0.35 * roi_ann_collat +
         0.15 * cushion_sigma/3.0 +
         0.30 * theta_gamma_score +
         0.20 * liquidity_score)
```

**Example Impact:**
- 30 DTE CSP, Vol/OI=0.6, no earnings, TG=1.2: **1.0× penalty** (100% of base score)
- 7 DTE CSP, Vol/OI=0.3, no earnings, TG=0.8: **0.70 × 0.85 × 1.0 × 0.85 = 0.51×** (51% of base)
- 35 DTE CSP, earnings in 2 days: **Excluded** (hard filter)

---

### 2. Covered Call (CC)

**Lines:** 1585-1631  
**Tenor Sweet Spot:** 21-45 DTE  
**Penalties Applied:**
- ✅ Tenor (21-45 DTE)
- ✅ Volume/OI ratio
- ✅ Earnings proximity
- ✅ Theta/Gamma ratio
- ✅ Hard filter: Earnings ≤3 days

**Base Score Formula:** Same as CSP

**Example Impact:**
- 45 DTE CC, Vol/OI=0.4, no earnings, TG=1.5: **1.0 × 0.85 × 1.0 × 1.0 = 0.85×**
- 10 DTE CC, Vol/OI=0.2, earnings in 5 days: **0.70 × 0.65 × 0.60 = 0.27×** (73% reduction!)

---

### 3. Collar

**Lines:** 1833-1870  
**Tenor Sweet Spot:** 30-60 DTE (longer-term protection)  
**Penalties Applied:**
- ✅ Tenor (30-60 DTE)
- ✅ Volume/OI ratio (worst of call/put legs)
- ✅ Hard filter: High dividend assignment risk

**Base Score Formula:**
```python
score = (0.45 * roi_ann +
         0.25 * put_cushion/3.0 +
         0.15 * call_cushion/3.0 +
         0.15 * liquidity_score)
```

**Example Impact:**
- 45 DTE Collar, both legs Vol/OI=0.6: **1.0 × 1.0 = 1.0×** (no penalty)
- 20 DTE Collar, call Vol/OI=0.6, put Vol/OI=0.2: **0.70 × 0.65 = 0.46×** (uses worst leg)
- Ex-dividend in window, div > extrinsic: **Excluded** (hard filter)

---

### 4. Iron Condor

**Lines:** 2157-2194  
**Tenor Sweet Spot:** 30-60 DTE  
**Penalties Applied:**
- ✅ Tenor (30-60 DTE)
- ✅ Volume/OI ratio (STRICTER thresholds for 4-leg)
- ✅ Hard filter: Any leg OI < 50

**Base Score Formula:**
```python
score = (0.40 * roi_cycle +
         0.30 * balance_score +
         0.20 * cushion_score +
         0.10 * liquidity_score)
```

**Stricter Volume/OI Penalties:**
- Vol/OI ≥ 0.5: 1.0× (healthy)
- Vol/OI ≥ 0.3: 0.80× (vs 0.85× for other strategies)
- Vol/OI < 0.3: 0.55× (vs 0.65× for other strategies)

**Example Impact:**
- 50 DTE IC, all legs Vol/OI≥0.5, all OI>100: **1.0 × 1.0 = 1.0×**
- 45 DTE IC, short put Vol/OI=0.35: **1.0 × 0.80 = 0.80×**
- 40 DTE IC, short call Vol/OI=0.2: **1.0 × 0.55 = 0.55×** (stricter!)
- 30 DTE IC, put long leg OI=40: **Excluded** (hard filter)

---

### 5. Bull Put Spread

**Lines:** 2472-2524  
**Tenor Sweet Spot:** 21-45 DTE  
**Penalties Applied:**
- ✅ Tenor (21-45 DTE)
- ✅ Volume/OI ratio (short leg)
- ✅ Earnings proximity
- ✅ Theta/Gamma ratio
- ✅ Hard filter: Earnings ≤3 days

**Base Score Formula:** Same structure as CSP (with ROI capped at 1.0 for scoring)

**Example Impact:**
- 30 DTE spread, Vol/OI=0.6, no earnings, TG=1.1: **1.0×** (perfect)
- 60 DTE spread, Vol/OI=0.3, earnings in 55 days: **0.70 × 0.85 × 0.60 = 0.36×**

---

### 6. Bear Call Spread

**Lines:** 2782-2844  
**Tenor Sweet Spot:** 21-45 DTE  
**Penalties Applied:**
- ✅ Tenor (21-45 DTE)
- ✅ Volume/OI ratio (short leg)
- ✅ Earnings proximity
- ✅ Theta/Gamma ratio
- ✅ Hard filter: Earnings ≤3 days

**Base Score Formula:** Same structure as CSP (with ROI capped at 1.0 for scoring)

**Example Impact:** Same as Bull Put Spread

---

## Compound Penalty Effects

Multiple violations multiply penalties together, creating exponential degradation:

| Violations | Penalty Combination | Final Multiplier | Effective Reduction |
|------------|---------------------|------------------|---------------------|
| None | 1.0 × 1.0 × 1.0 × 1.0 | **1.00×** | 0% |
| Bad tenor only | 0.70 × 1.0 × 1.0 × 1.0 | **0.70×** | 30% |
| Bad tenor + stale OI | 0.70 × 0.65 × 1.0 × 1.0 | **0.46×** | 54% |
| Bad tenor + stale OI + earnings | 0.70 × 0.65 × 0.60 × 1.0 | **0.27×** | 73% |
| All 4 violations | 0.70 × 0.65 × 0.60 × 0.70 | **0.19×** | **81%** |

**Result:** Opportunities with multiple violations are heavily penalized and drop in rankings, while clean opportunities maintain high scores.

## Testing Recommendations

Run scans across all strategies and verify:

1. **Score Distribution:** Do scores now cluster around fit-passing opportunities?
2. **Top-10 Rankings:** Do top-ranked opportunities pass most/all fit checks?
3. **Fit Violations:** Are opportunities with ❌ markers ranked lower than ✅ markers?
4. **Edge Cases:**
   - 7 DTE CSP (outside tenor) should rank below 30 DTE with same ROI
   - Vol/OI=0.1 should rank significantly lower than Vol/OI=0.6
   - Earnings in 5 days should score lower than earnings in 60 days
   - TG=0.4 should score lower than TG=1.2

## Expected Outcomes

### Before Implementation
```
Rank  Ticker  Strategy  Score   DTE  Vol/OI  TG    Tenor  Liquidity  Earnings
1     AAPL    CSP       0.845   7    0.15    0.6   ⚠️      ⚠️         ✅
2     MSFT    CSP       0.823   12   0.08    1.2   ⚠️      ❌         ⚠️
3     NVDA    CSP       0.802   35   0.65    1.5   ✅      ✅         ✅
```

### After Implementation
```
Rank  Ticker  Strategy  Score   DTE  Vol/OI  TG    Tenor  Liquidity  Earnings  Penalties Applied
1     NVDA    CSP       0.802   35   0.65    1.5   ✅      ✅         ✅        1.0 × 1.0 × 1.0 × 1.0 = 1.00×
2     AAPL    CSP       0.359   7    0.15    0.6   ⚠️      ⚠️         ✅        0.70 × 0.65 × 1.0 × 0.70 = 0.32×
3     MSFT    CSP       0.333   12   0.08    1.2   ⚠️      ❌         ⚠️        0.70 × 0.65 × 0.60 × 1.0 = 0.27×
```

**Clean opportunity (NVDA) now ranks #1, risky opportunities (AAPL, MSFT) drop significantly.**

## Code Changes Summary

| File | Lines Modified | Changes |
|------|----------------|---------|
| `strategy_lab.py` | 1372-1418 | CSP: Added 4 penalties + hard filter |
| `strategy_lab.py` | 1585-1631 | CC: Added 4 penalties + hard filter |
| `strategy_lab.py` | 1833-1870 | Collar: Added 2 penalties + hard filter |
| `strategy_lab.py` | 2157-2194 | Iron Condor: Added 2 stricter penalties + hard filter |
| `strategy_lab.py` | 2472-2524 | Bull Put: Added 4 penalties + hard filter |
| `strategy_lab.py` | 2782-2844 | Bear Call: Added 4 penalties + hard filter |

**Total:** ~240 lines added across 6 strategies

## Benefits

1. ✅ **Alignment:** Scores now reflect both opportunity AND quality
2. ✅ **Transparency:** Users see why some opportunities rank lower (multiple penalties applied)
3. ✅ **Flexibility:** High-risk/high-reward opportunities still appear (not filtered), just ranked lower
4. ✅ **Consistency:** All strategies use same penalty philosophy
5. ✅ **Safety:** Intolerable risks (earnings ≤3 days, dividend assignment, extreme illiquidity) hard-filtered

## Next Steps

1. ✅ Implementation complete (all 6 strategies)
2. ✅ Syntax validation passed
3. ⏳ **Test with real scans** - verify score alignment with fit criteria
4. 🔲 **User feedback** - confirm rankings feel "right"
5. 🔲 **Fine-tuning** - adjust penalty magnitudes if needed (currently standard 15-40% reductions)

---

**Questions or Issues?** Check:
- `evaluate_fit()` (lines 2771-3001) for best-practice criteria definitions
- Individual strategy scanners for penalty implementation details
- Test scans with known "clean" vs "risky" tickers to validate alignment
