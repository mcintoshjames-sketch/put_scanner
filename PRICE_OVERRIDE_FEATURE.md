# Price Override Feature Documentation

## Overview
The price override feature allows users to recalculate risk metrics using current market prices when executing trades, without needing to re-run the entire scan.

## Use Case
**Real-world scenario:**
1. User runs scan and identifies an attractive option opportunity
2. User navigates to broker to execute
3. Stock/option price has moved since scan
4. User needs to re-analyze with actual available prices before executing

## Implementation (Tab 5: Monte Carlo)

### Location
- **File:** `strategy_lab.py`
- **Lines:** ~2607-2693 (Price Override UI)
- **Lines:** ~2700-2703 (Variable assignment)
- **Lines:** ~2712, 2721, 2730, 2771, 2780, 2789 (MC parameter building)

### Features

#### 1. Stock Price Override
- **Checkbox:** "Override stock price"
- **Input:** Number input showing scan price as reference
- **Display:** Shows percentage change from scan price
- **Default:** Uses original scan price if unchecked

#### 2. Premium Override
- **Checkbox:** "Override premium"
- **Input:** Number input showing scan premium as reference
- **Display:** Shows percentage change from scan premium
- **Default:** Uses original scan premium if unchecked

#### 3. Real-time Metric Updates
When either override is active, displays updated:
- **CSP:** OTM% and ROI% (annualized) with delta from scan values
- **CC:** OTM% and ROI% (annualized) with delta from scan values
- **Collar:** (future enhancement)

#### 4. Monte Carlo Recalculation
All MC simulations use overridden prices:
- `S0 = execution_price` (overridden stock price)
- `put_premium/call_premium = execution_premium` (overridden premium)
- All risk metrics (P&L distribution, VaR, expected value) recalculate automatically

### UI Design
```
💰 Price Override (for live execution) [Collapsible Expander]
├── Column 1: Stock Price Override
│   ├── Checkbox: "Override stock price"
│   ├── Input: Current price (shows scan price)
│   └── Caption: Change percentage
├── Column 2: Premium Override
│   ├── Checkbox: "Override premium"
│   ├── Input: Current premium (shows scan premium)
│   └── Caption: Change percentage
└── Column 3: Updated Metrics (conditional)
    ├── OTM% (with delta)
    └── ROI% annualized (with delta)
```

### Session State Keys
- `use_custom_stock_price_mc`: Boolean for stock price override
- `custom_stock_price_mc`: Overridden stock price value
- `use_custom_premium_mc`: Boolean for premium override
- `custom_premium_value_mc`: Overridden premium value

### Code Logic
```python
# Extract original values
original_price = float(row["Price"])
original_premium = float(row.get("Premium", row.get("CallPrem", 0.0)))

# Get override values if checked
if use_custom_price:
    custom_stock_price = [user input]
else:
    custom_stock_price = original_price

# Use overridden values in MC
execution_price = custom_stock_price if 'custom_stock_price' in locals() else original_price
execution_premium = custom_premium if 'custom_premium' in locals() else original_premium

# Build MC params with execution prices
params = dict(
    S0=execution_price,  # Uses override
    put_premium=execution_premium,  # Uses override
    # ... other params
)
```

## Benefits
1. **Speed:** No need to re-run expensive scans when price moves
2. **Accuracy:** Use actual execution prices for risk analysis
3. **Flexibility:** Override price, premium, or both independently
4. **Transparency:** Shows deltas between scan and execution prices
5. **Real-time:** Instant recalculation of all risk metrics

## Strategy-Specific Behavior

### Cash-Secured Put (CSP)
- **Stock price override:** Updates OTM%, breach probability, MC simulations
- **Premium override:** Updates ROI%, P&L distributions, expected value
- **Both:** Comprehensive recalculation of all risk metrics

### Covered Call (CC)
- **Stock price override:** Updates OTM%, assignment risk, MC simulations
- **Premium override:** Updates ROI%, P&L distributions, income analysis
- **Both:** Full risk recalculation

### Collar (future enhancement)
- **Stock price override:** Updates protection effectiveness
- **Call/Put premium override:** Updates net cost/credit
- **Both:** Comprehensive collar analysis update

## Future Enhancements

### Near-term (Phase 3)
1. **Extend to other tabs:**
   - Plan & Runbook tab (order ticket)
   - Stress Test tab (scenario analysis)
   - Overview tab (summary metrics)

2. **Add premium override for Collar:**
   - Separate inputs for call and put premiums
   - Net credit/debit recalculation

3. **Add preset scenarios:**
   - "Stock up 1%"
   - "Stock down 1%"
   - "Premium increased 5%"
   - One-click scenario testing

### Long-term (Phase 4)
1. **Live price feed integration:**
   - Real-time price updates from Polygon
   - Auto-refresh override fields
   - Alert when price moves significantly

2. **Fill comparison:**
   - Compare scan price vs actual fill
   - Track slippage across positions
   - Historical fill quality analysis

3. **Bracket orders:**
   - Set limit price for entry
   - Auto-recalculate if limit fills
   - Show risk at different fill prices

## Testing Checklist
- [ ] CSP: Override stock price down, verify OTM% increases
- [ ] CSP: Override premium up, verify ROI% increases
- [ ] CSP: Override both, verify metrics consistent
- [ ] CC: Override stock price up, verify OTM% decreases
- [ ] CC: Override premium down, verify ROI% decreases
- [ ] CC: Override both, verify metrics consistent
- [ ] Verify MC simulations use override prices
- [ ] Test extreme price moves (>10%)
- [ ] Verify deltas calculate correctly
- [ ] Check edge case: price = strike
- [ ] Validate all UI elements responsive

## Performance Impact
- **Minimal:** Only adds conditional UI rendering
- **No backend changes:** Same MC functions, different inputs
- **Session state:** 4 additional keys per tab (negligible memory)
- **Rendering:** Expander collapsed by default (no impact when unused)

## Code Quality
- **Compiles:** ✅ Validated with `python3 -m py_compile`
- **Consistent:** Uses same patterns as existing override features
- **Documented:** Inline comments explain logic
- **Maintainable:** Clear variable names, modular structure
- **Robust:** Handles missing data gracefully (fallbacks for Collar)

## Version History
- **v1.0 (2025-01-20):** Initial implementation in Monte Carlo tab
  - Stock price override
  - Premium override
  - Real-time metric updates
  - Full MC recalculation

## Related Files
- `strategy_lab.py`: Main implementation
- `OPTIMIZATION_OPPORTUNITIES.md`: Phase 2 context
- `USER_GUIDE.md`: User-facing documentation
- `README.md`: High-level feature overview
