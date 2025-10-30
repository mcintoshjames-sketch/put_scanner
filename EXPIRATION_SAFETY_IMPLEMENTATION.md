# Expiration Safety Implementation

## Overview
Implemented comprehensive safety mechanisms to protect against non-standard expiration risks based on Schwab's "non-standard expiration date" warnings.

## What Are Non-Standard Expirations?

**Standard Expirations:**
- **Monthly**: 3rd Friday of each month (lowest risk)
- **Weekly**: Any other Friday (medium risk)

**Non-Standard Expirations:**
- Options expiring on **Monday, Tuesday, Wednesday, or Thursday**
- Often have poor liquidity, wider spreads, and unpredictable assignment behavior

## Risk Assessment System

### Risk Levels by Strategy

| Strategy | Standard (3rd Fri) | Weekly (Fri) | Non-Standard (Mon-Thu) |
|----------|-------------------|--------------|------------------------|
| **CSP** | LOW | MEDIUM | HIGH |
| **Covered Call** | MEDIUM | HIGH | HIGH |
| **Collar** | MEDIUM | HIGH | HIGH |
| **Bull Put Spread** | MEDIUM | HIGH | EXTREME |
| **Bear Call Spread** | MEDIUM | HIGH | EXTREME |
| **Iron Condor** | MEDIUM | HIGH | EXTREME |

### Risk Factors Evaluated

1. **Day of Week**: Friday = good, Mon-Thu = bad
2. **Expiration Type**: 3rd Friday > other Friday > non-Friday
3. **Open Interest**: < 100 = very risky, < 500 = risky, < 1000 = moderate (for non-standard)
4. **Bid-Ask Spread**: > 10% = extreme, > 5% = high, > 3% = moderate
5. **Strategy Complexity**: Single-leg < 2-leg < 4-leg

## Implementation Details

### 1. Core Safety Function

**Location:** `strategy_lab.py` lines 565-754

```python
def check_expiration_risk(expiration_str: str, strategy: str, 
                          open_interest: int = 0, bid_ask_spread_pct: float = 0.0) -> dict
```

**Returns:**
- `is_standard`: Boolean (True if Friday expiration)
- `expiration_type`: "Monthly (3rd Friday)", "Weekly (Friday)", or "Non-Standard (Day)"
- `day_of_week`: The actual day name
- `risk_level`: "LOW", "MEDIUM", "HIGH", or "EXTREME"
- `action`: "ALLOW", "WARN", or "BLOCK"
- `warning_message`: Human-readable warning
- `risk_factors`: List of specific concerns

### 2. Scanner Integration

**All 6 scanners updated:**
- CSP (lines 1386-1396)
- Covered Call (lines 1562-1572)
- Collar (lines 1751-1761)
- Iron Condor (lines 2039-2049)
- Bull Put Spread (lines 2324-2334)
- Bear Call Spread (lines 2626-2636)

**Added columns to results:**
- `ExpType`: "Monthly (3rd Friday)", "Weekly (Friday)", or "Non-Standard"
- `ExpRisk`: "LOW", "MEDIUM", "HIGH", or "EXTREME"
- `ExpAction`: "ALLOW", "WARN", or "BLOCK"

### 3. UI Safety Controls

**Sidebar Settings (lines 4185-4213):**

```python
# Expiration Safety section
allow_nonstandard = st.checkbox(
    "Include non-standard expirations (higher risk)",
    value=False,  # BLOCKED by default
    help="Non-standard = Mon/Tue/Wed/Thu. Risks: poor liquidity, assignment issues"
)

block_high_risk_multileg = st.checkbox(
    "Block high-risk multi-leg on non-standard dates",
    value=True,  # ENABLED by default
    help="Automatically block spreads and Iron Condors on non-standard expirations"
)
```

### 4. Automatic Filtering

**Location:** Lines 4596-4668

**Behavior:**
- **By default** (`allow_nonstandard=False`):
  - Filters out all "BLOCK" actions
  - Shows user how many were filtered
  - Displays info banner explaining why

- **With multi-leg protection** (`block_high_risk_multileg=True`):
  - Iron Condors: Only shows "ALLOW" actions (no warnings, no blocks)
  - Bull/Bear Spreads: Allows "ALLOW" + low-risk "WARN" only
  - CSP/CC/Collar: Allows "ALLOW" + "WARN" (more lenient)

### 5. Visual Warnings in Results

**Each strategy tab shows:**

#### CSP Tab (lines 4795-4806)
- Warning for non-standard expirations
- Shows count of affected positions
- Explains liquidity and exit risks

#### CC Tab (lines 4834-4848)
- **HIGH RISK** warning for Covered Calls
- Explains early assignment risk
- Notes dividend date conflicts
- Recommends Friday-only expirations

#### Collar Tab (lines 4875-4887)
- 2-leg strategy warning
- Notes both legs must have liquidity
- Recommends OI > 1,000 for both legs

#### Iron Condor Tab (lines 4912-4932)
- 🚨 **EXTREME RISK** error banner
- Strongest warning language
- "DO NOT TRADE" recommendation
- Explains 4-leg liquidity disaster
- Shows blocked count

#### Bull Put / Bear Call Spreads (lines 4963-4975, 5009-5021)
- 2-leg spread warning
- Partial fill risk
- Recommends OI > 500, spread < 3%

### 6. Results Display Enhancements

**All result tables now show:**
- `ExpType` column: Quick visual of expiration type
- `ExpRisk` column: LOW/MEDIUM/HIGH/EXTREME badge
- Enhanced captions explaining expiration risk
- Recommendations in help text

## Safety Thresholds

### Default Blocking Rules

| Strategy | Action | Condition |
|----------|--------|-----------|
| All | BLOCK | Non-Friday + OI < 100 |
| All | BLOCK | Non-Friday + Spread > 10% |
| CC | BLOCK | Non-Friday (assignment risk) |
| Iron Condor | BLOCK | Non-Friday (extreme liquidity) |
| Spreads | BLOCK | Non-Friday + HIGH risk |

### Warning Rules

| Strategy | Action | Condition |
|----------|--------|-----------|
| CSP | WARN | Weekly Friday or Non-Friday |
| CC | WARN | Weekly Friday |
| Collar | WARN | Any non-standard |
| Spreads | WARN | Weekly Friday |

## User Experience

### Recommended Settings (Default)
```
✅ allow_nonstandard = False
✅ block_high_risk_multileg = True
```
**Result:** Maximum protection, only standard expirations shown

### Advanced User Settings
```
⚠️ allow_nonstandard = True
✅ block_high_risk_multileg = True
```
**Result:** See warnings but still blocks Iron Condors on non-standard dates

### Expert Mode (Not Recommended)
```
❌ allow_nonstandard = True
❌ block_high_risk_multileg = False
```
**Result:** See everything, user responsible for checking ExpRisk column

## Risk Communication

### UI Elements

1. **Info Banner** (when filtering active):
   - Shows count of blocked items per strategy
   - Explains why items were blocked
   - Directs to sidebar to change settings

2. **Strategy-Specific Warnings**:
   - Color-coded: ⚠️ Yellow for WARN, 🚨 Red for BLOCK
   - Lists specific risk factors
   - Provides actionable recommendations

3. **Column Tooltips**:
   - ExpType: Explains standard vs non-standard
   - ExpRisk: Defines risk levels
   - Captions: Contextual guidance

## Testing Recommendations

### Test Cases to Verify

1. **Standard 3rd Friday** (e.g., 2025-11-21):
   - ✅ Should show as "Monthly (3rd Friday)"
   - ✅ ExpRisk should be LOW for CSP, MEDIUM for CC/spreads
   - ✅ ExpAction should be ALLOW

2. **Weekly Friday** (e.g., 2025-11-07):
   - ✅ Should show as "Weekly (Friday)"
   - ✅ ExpRisk should be MEDIUM for CSP, HIGH for CC
   - ✅ ExpAction should be WARN

3. **Monday Expiration** (e.g., 2025-11-03):
   - ✅ Should show as "Non-Standard (Monday)"
   - ✅ ExpRisk should be HIGH for CSP/CC, EXTREME for spreads
   - ✅ ExpAction should be BLOCK

4. **Filtering Behavior**:
   - ✅ With `allow_nonstandard=False`, Monday expiration should not appear
   - ✅ Info banner should show "X blocked"
   - ✅ With `allow_nonstandard=True`, Monday should appear with red warning

5. **Multi-Leg Protection**:
   - ✅ Iron Condor on Monday should be BLOCKED even with `allow_nonstandard=True`
   - ✅ Only bypass with both checkboxes disabled

## Benefits

1. **Protects Users**: Prevents trading illiquid, high-risk expirations by default
2. **Educational**: Explains WHY certain expirations are risky
3. **Flexible**: Advanced users can override with informed consent
4. **Graduated**: Different risk levels for different strategy complexities
5. **Visual**: Color-coding and icons make risks immediately apparent
6. **Actionable**: Specific recommendations (e.g., "use OI > 500")

## Integration with Existing Features

- ✅ Compatible with earnings filter
- ✅ Works with all 6 strategy scanners
- ✅ Integrates with Trade Execution module
- ✅ Preserved all existing columns and functionality
- ✅ No breaking changes to API or data structures

## Future Enhancements

1. **Trade Execution Integration**: Block non-standard in order preview
2. **Expiration Calendar View**: Visual calendar showing standard vs non-standard dates
3. **Historical Analysis**: Track fill quality on standard vs non-standard
4. **Smart Defaults**: Auto-adjust OI/spread thresholds for non-standard
5. **Broker Integration**: Pull actual assignment statistics from Schwab API

## Files Modified

- `strategy_lab.py`: All changes contained in single file
  - Lines 565-754: Core safety function
  - Lines 1386-1396, 1562-1572, 1751-1761, 2039-2049, 2324-2334, 2626-2636: Scanner integration
  - Lines 4185-4213: UI controls
  - Lines 4596-4668: Filtering logic
  - Lines 4795-5021: Results display with warnings

## Documentation

- This file (`EXPIRATION_SAFETY_IMPLEMENTATION.md`)
- Inline code comments in `strategy_lab.py`
- Help text in UI checkboxes and tooltips
- Captions in result tables

---

## Summary

**The system now provides comprehensive protection against Schwab's "non-standard expiration" warnings by:**
1. ✅ Detecting non-standard dates automatically
2. ✅ Assessing risk based on strategy complexity
3. ✅ Blocking dangerous combinations by default
4. ✅ Warning users about moderate-risk scenarios
5. ✅ Explaining WHY each expiration is risky
6. ✅ Providing actionable guidance (OI thresholds, spread limits)
7. ✅ Allowing advanced users to override with informed consent

**Default behavior = SAFE**: Only standard Friday expirations are shown unless user explicitly enables non-standard dates.
