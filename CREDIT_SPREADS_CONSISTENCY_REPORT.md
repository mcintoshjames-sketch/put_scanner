# Credit Spreads Consistency Review Report
**Date**: October 30, 2025  
**Status**: ⚠️ **INCONSISTENCIES FOUND**

## Executive Summary
Found **critical inconsistencies** between Trade Runbook generation and Trade Execution UI for credit spreads. Bull Put Spread and Bear Call Spread are **missing from Trade Execution** despite having complete runbook implementations.

---

## Issue 1: Missing from Trade Execution Module ❌

### Location
**File**: `strategy_lab.py`  
**Lines**: 4738-4761 (Trade Execution strategy selection)

### Problem
The Trade Execution module only includes 4 strategies:
```python
available_strategies = []
if not df_csp.empty:
    available_strategies.append("Cash-Secured Put")
if not df_cc.empty:
    available_strategies.append("Covered Call")
if not df_collar.empty:
    available_strategies.append("Collar")
if not df_iron_condor.empty:
    available_strategies.append("Iron Condor")
# ❌ BULL_PUT_SPREAD MISSING
# ❌ BEAR_CALL_SPREAD MISSING

strategy_map = {
    "Cash-Secured Put": ("CSP", df_csp),
    "Covered Call": ("CC", df_cc),
    "Collar": ("COLLAR", df_collar),
    "Iron Condor": ("IRON_CONDOR", df_iron_condor)
    # ❌ BULL_PUT_SPREAD MISSING
    # ❌ BEAR_CALL_SPREAD MISSING
}
```

### Impact
- Users **cannot create orders** for Bull Put Spread or Bear Call Spread
- Users **cannot preview orders** for credit spreads
- Users **cannot check buying power** for credit spreads
- **Runbook is complete** but execution path is blocked

### User Experience Gap
```
User Flow:
1. Run scan → Bull Put Spread found ✅
2. View Best-Practice Fit → All checks displayed ✅
3. View Trade Runbook → Complete instructions shown ✅
4. Navigate to Trade Execution → Strategy NOT AVAILABLE ❌
```

---

## Issue 2: Missing Strategy Info Tooltips ❌

### Location
**Lines**: 4773-4780 (Strategy info display)

### Problem
```python
with col_info:
    if selected_strategy == "CSP":
        st.info("💡 **CSP**: Sell put option, collect premium, prepared to buy stock at strike")
    elif selected_strategy == "CC":
        st.info("💡 **CC**: Sell call option on owned stock, collect premium, capped upside")
    elif selected_strategy == "COLLAR":
        st.info("💡 **Collar**: Sell call + buy put for downside protection, limited upside")
    elif selected_strategy == "IRON_CONDOR":
        st.info("💡 **Iron Condor**: Sell put spread + call spread, profit if price stays in range")
    # ❌ BULL_PUT_SPREAD info missing
    # ❌ BEAR_CALL_SPREAD info missing
```

### Expected Tooltips
Based on runbook and UI captions, should include:
```python
elif selected_strategy == "BULL_PUT_SPREAD":
    st.info("💡 **Bull Put Spread**: Sell higher strike put + buy lower strike put = NET CREDIT | Defined risk, 5-10x more efficient than CSP")
elif selected_strategy == "BEAR_CALL_SPREAD":
    st.info("💡 **Bear Call Spread**: Sell lower strike call + buy higher strike call = NET CREDIT | Defined risk, no stock ownership required")
```

---

## Issue 3: Missing Contract Display Format ❌

### Location
**Lines**: 4786-4828 (Contract selection display)

### Problem
No display format defined for credit spreads:
```python
if selected_strategy == "CSP":
    df_display['display'] = (...)
elif selected_strategy == "CC":
    df_display['display'] = (...)
elif selected_strategy == "COLLAR":
    df_display['display'] = (...)
elif selected_strategy == "IRON_CONDOR":
    df_display['display'] = (...)
# ❌ BULL_PUT_SPREAD display format missing
# ❌ BEAR_CALL_SPREAD display format missing
```

### Expected Format
Based on existing patterns:
```python
elif selected_strategy == "BULL_PUT_SPREAD":
    df_display['display'] = (
        df_display['Ticker'] + " " +
        df_display['Exp'] +
        " Sell $" + df_display['SellStrike'].astype(str) +
        " / Buy $" + df_display['BuyStrike'].astype(str) + " PUT" +
        " @ $" + df_display['NetCredit'].round(2).astype(str)
    )
elif selected_strategy == "BEAR_CALL_SPREAD":
    df_display['display'] = (
        df_display['Ticker'] + " " +
        df_display['Exp'] +
        " Sell $" + df_display['SellStrike'].astype(str) +
        " / Buy $" + df_display['BuyStrike'].astype(str) + " CALL" +
        " @ $" + df_display['NetCredit'].round(2).astype(str)
    )
```

---

## Issue 4: Missing Selected Contract Metrics ❌

### Location
**Lines**: 4853-4875 (Selected contract details display)

### Problem
```python
if selected_strategy == "CSP":
    cols_info[1].metric("Strike", f"${selected['Strike']:.2f}")
    cols_info[2].metric("Premium", f"${selected['Premium']:.2f}")
    cols_info[3].metric("ROI (ann)", f"{selected['ROI%_ann']:.1f}%")
# ... other strategies ...
elif selected_strategy == "IRON_CONDOR":
    # 4-leg display with put/call spreads
# ❌ BULL_PUT_SPREAD metrics missing
# ❌ BEAR_CALL_SPREAD metrics missing
```

### Expected Metrics Display
```python
elif selected_strategy == "BULL_PUT_SPREAD":
    st.write("**Bull Put Spread (2-leg):**")
    col_s1, col_s2 = st.columns(2)
    col_s1.metric("Sell Put", f"${selected['SellStrike']:.2f}")
    col_s2.metric("Buy Put", f"${selected['BuyStrike']:.2f}")
    col_c1, col_c2 = st.columns(2)
    col_c1.metric("Net Credit", f"${selected['NetCredit']:.2f}")
    col_c2.metric("ROI (ann)", f"{selected['ROI%_ann']:.1f}%")

elif selected_strategy == "BEAR_CALL_SPREAD":
    st.write("**Bear Call Spread (2-leg):**")
    col_s1, col_s2 = st.columns(2)
    col_s1.metric("Sell Call", f"${selected['SellStrike']:.2f}")
    col_s2.metric("Buy Call", f"${selected['BuyStrike']:.2f}")
    col_c1, col_c2 = st.columns(2)
    col_c1.metric("Net Credit", f"${selected['NetCredit']:.2f}")
    col_c2.metric("ROI (ann)", f"{selected['ROI%_ann']:.1f}%")
```

---

## Issue 5: Missing Order Preview Logic ❌

### Location
**Lines**: 4904-4924 (Order preview section)

### Problem
```python
if selected_strategy == "CSP":
    # CSP preview
elif selected_strategy == "CC":
    # CC preview
elif selected_strategy == "COLLAR":
    # Collar preview
elif selected_strategy == "IRON_CONDOR":
    # Iron Condor preview
# ❌ BULL_PUT_SPREAD preview missing
# ❌ BEAR_CALL_SPREAD preview missing
```

### Expected Order Preview
```python
elif selected_strategy == "BULL_PUT_SPREAD":
    col_a, col_b = st.columns(2)
    col_a.write(f"**Action:** 2-LEG CREDIT SPREAD (Bull Put)")
    spread_width = selected['SellStrike'] - selected['BuyStrike']
    max_risk = (spread_width - selected['NetCredit']) * 100 * num_contracts
    col_b.write(f"**Max Risk:** ${max_risk:,.2f}")
    st.write(f"**Max Credit:** ${limit_price * 100 * num_contracts:,.2f}")

elif selected_strategy == "BEAR_CALL_SPREAD":
    col_a, col_b = st.columns(2)
    col_a.write(f"**Action:** 2-LEG CREDIT SPREAD (Bear Call)")
    spread_width = selected['BuyStrike'] - selected['SellStrike']
    max_risk = (spread_width - selected['NetCredit']) * 100 * num_contracts
    col_b.write(f"**Max Risk:** ${max_risk:,.2f}")
    st.write(f"**Max Credit:** ${limit_price * 100 * num_contracts:,.2f}")
```

---

## Issue 6: Missing Buying Power Calculation ❌

### Location
**Lines**: 4950+ (Buying power check logic)

### Problem
Based on read context, buying power calculation includes:
- CSP: `required = selected['Strike'] * 100 * num_contracts`
- CC, Collar, Iron Condor: Similar calculations
- ❌ No buying power logic for credit spreads

### Expected Logic
```python
elif selected_strategy == "BULL_PUT_SPREAD":
    spread_width = selected['SellStrike'] - selected['BuyStrike']
    max_loss = spread_width - selected['NetCredit']
    required = max_loss * 100 * num_contracts

elif selected_strategy == "BEAR_CALL_SPREAD":
    spread_width = selected['BuyStrike'] - selected['SellStrike']
    max_loss = spread_width - selected['NetCredit']
    required = max_loss * 100 * num_contracts
```

---

## Terminology Consistency Review ✅

### Runbook vs UI Captions - CONSISTENT
Checked terminology across components:

| Component | Bull Put Spread | Bear Call Spread |
|-----------|----------------|------------------|
| **Tab Header** | "Bull Put Spread (Defined Risk Credit Spread)" | "Bear Call Spread (Defined Risk Credit Spread)" |
| **Caption** | "SELL higher strike put + BUY lower strike put = NET CREDIT" | "SELL lower strike call + BUY higher strike call = NET CREDIT" |
| **Runbook Title** | "RUNBOOK — BULL PUT SPREAD" | "RUNBOOK — BEAR CALL SPREAD" |
| **Runbook Entry** | "Sell to Open ... PUT (short put)" / "Buy to Open ... PUT (long put)" | "Sell to Open ... CALL (short call)" / "Buy to Open ... CALL (long call)" |
| **Max Profit** | "Net credit received" | "Net credit received" |
| **Max Loss** | "Spread width − net credit" | "Spread width − net credit" |
| **Breakeven** | "Sell strike − net credit" | "Sell strike + net credit" |

**Status**: ✅ All terminology is consistent across runbook and UI

### Strike Naming - CONSISTENT
| Component | Short Strike Field | Long Strike Field |
|-----------|-------------------|-------------------|
| **DataFrame** | `SellStrike` | `BuyStrike` |
| **Runbook** | References "Sell strike" | References "Buy strike" |
| **Display Logic** | Would use `SellStrike` | Would use `BuyStrike` |

**Status**: ✅ Field names match between data and display

---

## Impact Assessment

### Severity: **HIGH** 🔴
- Blocks actual trading for credit spreads
- Complete feature gap despite full backend implementation
- Misleading UX (runbook suggests execution is possible)

### Affected Users
- ✅ Can scan for credit spreads
- ✅ Can view results in tabs
- ✅ Can compare strategies
- ✅ Can view best-practice checks
- ✅ Can view trade runbook
- ❌ **CANNOT execute trades** (missing from Trade Execution UI)
- ❌ **CANNOT preview orders**
- ❌ **CANNOT check buying power**

### Business Impact
- **Incomplete feature** (70% done, 30% missing)
- **User frustration** (runbook promises execution that isn't available)
- **Support tickets** likely from confused users

---

## Recommended Fix Priority

### Priority 1: Add to Trade Execution Selection (CRITICAL)
- Add Bull Put Spread and Bear Call Spread to `available_strategies` list
- Add both to `strategy_map` dictionary
- **Estimated Lines**: 4 lines to add

### Priority 2: Add Strategy Info Tooltips (HIGH)
- Add info tooltips for both credit spreads
- **Estimated Lines**: 4 lines to add

### Priority 3: Add Contract Display Format (HIGH)
- Add display string formatting for contract selection
- **Estimated Lines**: ~16 lines to add (8 per strategy)

### Priority 4: Add Selected Contract Metrics (HIGH)
- Add metric display for selected credit spread contracts
- **Estimated Lines**: ~20 lines to add (10 per strategy)

### Priority 5: Add Order Preview Logic (HIGH)
- Add order preview display for both strategies
- **Estimated Lines**: ~14 lines to add (7 per strategy)

### Priority 6: Add Buying Power Calculation (HIGH)
- Add buying power calculation logic
- **Estimated Lines**: ~8 lines to add (4 per strategy)

### Priority 7: Add Order Creation Logic (CRITICAL)
- Add actual order creation for Schwab API
- **Estimated Lines**: Unknown (need to review existing order creation code)

**Total Estimated Additions**: ~66+ lines of code

---

## Testing Checklist

### After Fix Implementation:
- [ ] Bull Put Spread appears in Trade Execution strategy selector
- [ ] Bear Call Spread appears in Trade Execution strategy selector
- [ ] Info tooltips display correctly for both strategies
- [ ] Contract selection shows proper format (Sell/Buy strikes + credit)
- [ ] Selected contract metrics display correctly
- [ ] Order preview calculates max risk correctly
- [ ] Buying power check returns correct value
- [ ] Order creation generates valid Schwab API request
- [ ] Integration test: Full flow from scan → runbook → execution

---

## Code Locations Summary

| Feature | File | Line Range | Status |
|---------|------|-----------|--------|
| Strategy Selection | strategy_lab.py | 4738-4761 | ❌ Missing credit spreads |
| Strategy Info Tooltips | strategy_lab.py | 4773-4780 | ❌ Missing credit spreads |
| Contract Display Format | strategy_lab.py | 4786-4828 | ❌ Missing credit spreads |
| Selected Contract Metrics | strategy_lab.py | 4853-4875 | ❌ Missing credit spreads |
| Order Preview | strategy_lab.py | 4904-4924 | ❌ Missing credit spreads |
| Buying Power Calculation | strategy_lab.py | 4950+ | ❌ Missing credit spreads |
| Trade Runbook Generation | strategy_lab.py | 3002-3098 | ✅ Complete |
| Best-Practice Fit | strategy_lab.py | 2750-2834 | ✅ Complete |
| Stress Test | strategy_lab.py | 3276-3352 | ✅ Complete |

---

## Conclusion

**Summary**: Credit spreads have complete backend implementation (scanning, analysis, runbook, stress test) but are **completely missing from Trade Execution UI**. This creates a broken user experience where users can research trades but cannot execute them.

**Recommendation**: Implement all 7 priorities above to achieve feature parity with other strategies.

**Risk**: If not fixed, credit spread feature appears incomplete and may confuse/frustrate users who see comprehensive analysis but cannot trade.
