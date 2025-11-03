# Schwab Options Approval Fix

## Problem Identified

Your orders were being rejected by Schwab with the error: **"The account is not approved for this level of options trading."**

This happened because the app was creating **single-leg SELL_TO_OPEN orders** for both:
- **Covered Calls** (SELL_TO_OPEN call)
- **Cash-Secured Puts** (SELL_TO_OPEN put)

**Why Schwab rejects these:**
When Schwab sees a single-leg SELL_TO_OPEN order with no context, it treats it as a **naked short option**, which requires **Level 4 options approval**. The system doesn't automatically know you intend it to be a covered call (Level 1) or cash-secured put (Level 1).

## Schwab Options Approval Levels

- **Level 1**: Covered Calls & Cash-Secured Puts *(what you're approved for)*
  - Covered Call: Must own 100 shares per contract
  - Cash-Secured Put: Must have cash collateral (~strike × 100 × quantity)
  
- **Level 2**: Long Options (buying calls/puts)

- **Level 3**: Spreads (defined risk strategies)

- **Level 4**: Naked/Uncovered Options *(you need this for Schwab to accept single-leg shorts)*

## Solutions Implemented

### 1. Pre-Flight Position Verification

Added `check_stock_position()` method that:
- Queries your Schwab account for current stock holdings
- Verifies you own sufficient shares BEFORE submitting covered call orders
- Shows clear error if shares are missing:
  ```
  ❌ Covered Call Requirement Not Met: No AAPL shares found in account. 
  You must own 500 shares to write covered calls.
  
  Schwab will reject this as a 'naked short call' which requires Level 4 
  options approval.
  ```

### 2. Pre-Flight Buying Power Check

Added `check_buying_power()` method that:
- Verifies sufficient cash/margin for cash-secured puts
- Warns if buying power is insufficient
- Shows current vs. required buying power

### 3. Enhanced Order Documentation

Updated `create_covered_call_order()` and `create_cash_secured_put_order()` with clear warnings:

```python
"""
IMPORTANT: This creates a single-leg SELL_TO_OPEN order. For Schwab to approve
this as a covered call (Level 1 options approval), you MUST already own the 
underlying shares in your account:
- 1 contract requires 100 shares
- 5 contracts require 500 shares, etc.

If you don't own the shares, Schwab will reject this as a "naked short call"
which requires Level 4 options approval.
"""
```

### 4. UI Warnings

Added prominent info boxes in the UI:
- **For Covered Calls**: Shows you must own X shares
- **For Cash-Secured Puts**: Shows required cash amount
- Appears right after contract selection, before order preview

### 5. Automatic Validation

When you click "Preview Order", the app now:
1. Checks if you own the required stock (for CCs)
2. Checks if you have sufficient buying power (for CSPs)
3. **Blocks the order** with a clear error if requirements aren't met
4. Shows ✅ success message if everything checks out
5. Only then submits to Schwab's preview API

## What You Need To Do

### For Covered Calls:
1. **Buy the underlying stock first** (100 shares per contract)
2. Wait for the purchase to settle (typically T+1 for stocks)
3. Then sell the covered calls

**Example**: To sell 5 covered calls on AAPL:
- You must own 500 shares of AAPL
- The app will verify this before allowing the order

### For Cash-Secured Puts:
1. Ensure you have sufficient **cash or margin** in your account
2. Required amount ≈ strike price × 100 × number of contracts
3. Example: 5 contracts at $50 strike = ~$25,000 needed

## Alternative Solution (Future Enhancement)

If you want to avoid the requirement of owning shares first, we could implement:

**Buy-Write Orders** (2-leg simultaneous execution):
- Leg 1: BUY 100 shares of stock
- Leg 2: SELL 1 call option

This is a true covered call in a single order, recognized as Level 1 by Schwab.

However, this requires:
- More complex order structure
- Higher capital requirement (buying stock + option margin)
- Different execution mechanics

Let me know if you want this implemented!

## Testing Recommendations

1. **Test with small position first**: Try 1 contract to verify everything works
2. **Check your account**: Verify share count before attempting covered calls
3. **Review error messages**: The app will tell you exactly what's missing
4. **Use "Check Buying Power"**: Click this button before previewing orders

## Files Changed

- `providers/schwab_trading.py`: Added `check_stock_position()` and `check_buying_power()` methods
- `strategy_lab.py`: Added pre-flight validation and UI warnings
- Documentation in order creation methods

## Next Steps

1. Restart the Streamlit app to load the changes
2. Run a scan
3. Select a contract
4. Click "Preview Order"
5. The app will now verify your positions before submitting to Schwab
6. If you see errors, buy the required shares first, then retry

---

**Note**: This fix ensures the app properly validates your account state BEFORE submitting to Schwab, preventing rejections and providing clear guidance on what's needed.
