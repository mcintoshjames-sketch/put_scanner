# Strategy Scoring Calibration

## Overview
All strategies now use comparable scoring formulas that output values in the **0-1 range**, making cross-strategy comparisons meaningful.

## Scoring Formulas

### Cash-Secured Put (CSP)
```python
score = (0.35 * roi_ann_collat +           # Fractional ROI (0.10 = 10% annual)
         0.15 * cushion_normalized +        # 0-1 (cushion_sigma / 3.0)
         0.30 * theta_gamma_score +         # 0-1 (optimal range 0.8-3.0)
         0.20 * liquidity_score)            # 0-1 (based on spread%)
```
- **ROI component**: Uses fractional value (e.g., 0.35 × 0.10 = 0.035 for 10% ROI)
- **Total max**: ~0.35 + 0.15 + 0.30 + 0.20 = **1.00**

### Covered Call (CC)
```python
score = (0.35 * roi_ann +                  # Fractional ROI (0.10 = 10% annual)
         0.15 * cushion_normalized +        # 0-1 (cushion_sigma / 3.0)
         0.30 * theta_gamma_score +         # 0-1 (optimal range 0.8-3.0)
         0.20 * liquidity_score)            # 0-1 (based on spread%)
```
- **ROI component**: Uses fractional value (e.g., 0.35 × 0.10 = 0.035 for 10% ROI)
- **Total max**: ~0.35 + 0.15 + 0.30 + 0.20 = **1.00**

### Collar
```python
score = (0.45 * roi_ann +                  # Fractional ROI (0.05 = 5% annual)
         0.25 * put_cushion / 3.0 +         # 0-0.25 (normalized to 3 sigma)
         0.15 * call_cushion / 3.0 +        # 0-0.15 (normalized to 3 sigma)
         0.15 * liquidity_score)            # 0-1 (based on spreads)
```
- **ROI component**: Uses fractional value (e.g., 0.45 × 0.05 = 0.0225 for 5% ROI)
- **Total max**: ~0.45 × 0.05 + 0.25 + 0.15 + 0.15 = **0.57** (Collars have lower ROI)

### Iron Condor (FIXED)
```python
score = (0.40 * roi_cycle +                # Fractional per-cycle ROI (0.32 = 32%)
         0.30 * balance_score +             # 0-1 (wing symmetry)
         0.20 * cushion_score +             # 0-1 (min cushion / 3.0)
         0.10 * liquidity_score)            # 0-1 (based on spreads)
```
- **ROI component**: Uses fractional per-cycle ROI (e.g., 0.40 × 0.32 = 0.128 for 32% per cycle)
- **Total max**: ~0.40 × 0.50 + 0.30 + 0.20 + 0.10 = **0.80** (ICs emphasize balance/cushion)

## The Bug (FIXED)

**Before fix:**
```python
score = (0.40 * roi_ann + ...)  # roi_ann = 7.77 for 777% annualized
```
- Score component from ROI: 0.40 × 7.77 = **3.108**
- Total score: **> 3.0** (way out of range!)

**After fix:**
```python
score = (0.40 * roi_cycle + ...)  # roi_cycle = 0.32 for 32% per cycle
```
- Score component from ROI: 0.40 × 0.32 = **0.128**
- Total score: **0.0 - 0.8** (properly calibrated)

## Score Interpretation

| Score Range | Interpretation |
|------------|----------------|
| 0.6 - 1.0  | Excellent opportunity (high ROI, good risk metrics, liquid) |
| 0.4 - 0.6  | Good opportunity (solid metrics across the board) |
| 0.2 - 0.4  | Fair opportunity (acceptable but not ideal) |
| 0.0 - 0.2  | Marginal opportunity (barely meets criteria) |

## Strategy-Specific Notes

### CSP & Covered Call
- Emphasis on **theta/gamma ratio** (30% weight) for short-term income
- ROI component: 35% weight
- Sweet spot: 10-45 DTE with theta/gamma ratio 0.8-3.0

### Collar
- Emphasis on **ROI** (45% weight) since collars have lower premiums
- Cushion components: 40% combined weight (protection is key)
- Typically lower scores due to defensive nature

### Iron Condor
- Emphasis on **balance** (30% weight) - symmetric wings are critical
- Emphasis on **cushion** (20% weight) - probability of staying in range
- ROI component: 40% weight (credit/risk ratio)
- Moderate scores (0.3-0.6 typical) due to balanced risk/reward

## Comparison Tab

When viewing the Compare tab, scores are now directly comparable:
- A CSP with score 0.55 is roughly equivalent to an IC with score 0.50
- Higher scores indicate better opportunities **within their risk profile**
- Consider strategy-specific factors (capital requirements, directional exposure, etc.)
