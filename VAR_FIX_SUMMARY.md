# VaR Calculation Fix - Black-Scholes Option Repricing

## Problem Summary

The VaR calculation was showing unrealistic results for long option positions:
- **Issue**: VaR = $31 (100% of portfolio) for a single NVDA call option
- **Root Cause**: Delta-linear approximation (`P&L = delta × 100 × S × r`) hit the artificial loss cap for any market move > 1.6%
- **Impact**: More than 5% of historical days exceeded this threshold, causing the 95th percentile VaR to always equal the full premium paid

## Solution Implemented

Replaced delta-linear approximation with **full Black-Scholes option repricing**:

### Mathematical Approach
```
For each historical return scenario r:
1. Calculate new underlying price: S₁ = S₀(1 + r)
2. Adjust time to expiration: T₁ = T₀ - 1/252 years
3. Reprice option: C₁ = BS(S₁, K, T₁, rf, σ)
4. Compute P&L: ΔP&L = (C₁ - C₀) × 100 × quantity
```

### Key Components Added

**Black-Scholes Pricing Functions** (`var_calculator.py`):
- `_bs_call_price(S, K, T, r, sigma)`: Call option pricing using norm.cdf()
- `_bs_put_price(S, K, T, r, sigma)`: Put option pricing using norm.cdf()
- `_implied_vol_call_simple(C0, S, K, T, r)`: IV solver for calls with bisection search
- `_implied_vol_put_simple(P0, S, K, T, r)`: IV solver for puts with bisection search

**VaR Calculation Updates**:
- Solve for implied volatility σ from current option price
- Reprice option under each historical scenario using Black-Scholes
- Natural loss bounding (option prices can't go below zero)
- Removed artificial loss caps - no longer needed

## Results

**Before Fix**:
```
Portfolio Value: $31.00
VaR (1-day, 95%): $31.00 (100.00% of portfolio)
```

**After Fix**:
```
Portfolio Value: $31.00
VaR (1-day, 95%): $15.80 (50.96% of portfolio)
CVaR (1-day, 95%): $18.84 (60.79% of portfolio)
```

## Validation

Created `test_var_fix.py` with comprehensive checks:
- ✅ VaR < full premium paid
- ✅ VaR > 0 (positive risk)
- ✅ VaR% < 100% (reasonable percentage)
- ✅ CVaR ≥ VaR (coherent risk measure)
- ✅ VaR in expected range ($5-$28 for OTM call)

## Technical Details

**Constants**:
- Risk-free rate: 3% (0.03)
- Trading days per year: 252
- Contract multiplier: 100 shares per option

**Implied Volatility Solver**:
- Method: Bisection search (20 iterations)
- Range: 1% - 300% volatility
- Convergence: ±$0.01 price accuracy
- Fallback: 30% default volatility

**Option Repricing**:
- Stocks: Linear P&L = quantity × price × return
- Options: Non-linear P&L using Black-Scholes
- Time decay: T reduced by 1/252 years per day
- No position-level or portfolio-level loss caps

## Files Modified

1. **`risk_metrics/var_calculator.py`**:
   - Added Black-Scholes pricing functions (lines 36-168)
   - Rewrote `calculate_portfolio_var()` option handling (lines 600-650)
   - Removed artificial loss capping logic
   - Added proper IV solving and option repricing

2. **`test_var_fix.py`** (new):
   - Comprehensive test suite for VaR calculation
   - Tests NVDA call scenario matching user's position
   - Validates all risk metrics with assertions

## Next Steps

1. ✅ **Completed**: Black-Scholes repricing implementation
2. ✅ **Completed**: Validation testing
3. **Pending**: Update integration tests (`test_var_integration.py`)
4. **Pending**: Test with live Schwab positions in UI
5. **Pending**: Git commit all changes

## Usage Example

```python
from risk_metrics.var_calculator import calculate_portfolio_var

positions = [{
    'symbol': 'NVDA',
    'quantity': 1,  # Long 1 contract
    'underlying_price': 190.0,
    'option_price': 0.31,  # $31 total
    'position_type': 'CALL',
    'strike': 260.0,
    'expiration': '2025-12-12'
}]

result = calculate_portfolio_var(
    positions=positions,
    historical_prices=historical_df,
    confidence_level=0.95,
    time_horizon_days=1
)

print(f"VaR (95%, 1-day): ${result.var_amount:.2f}")
# Output: VaR (95%, 1-day): $15.80
```

## References

- Black, F., & Scholes, M. (1973). "The Pricing of Options and Corporate Liabilities"
- Hull, J. C. (2018). "Options, Futures, and Other Derivatives" (10th ed.)
- JP Morgan RiskMetrics (1996)

---
**Status**: ✅ Fixed and Validated  
**Date**: 2025-01-15  
**Tested**: NVDA call option ($31 position → VaR $15.80 vs previous $31.00)
