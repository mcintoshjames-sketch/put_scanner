# Adding a New Strategy to Strategy Lab - Best Practices Guide

## Overview
This guide documents the complete process for adding a new options strategy to the Strategy Lab application, based on lessons learned from implementing Iron Condor. Following this checklist will prevent common errors like missing strategy support in various app sections.

---

## Pre-Implementation Checklist

### 1. Strategy Research & Design
- [ ] Document strategy structure (number of legs, option types, strikes)
- [ ] Define entry conditions and screening criteria
- [ ] Document exit conditions and profit targets
- [ ] Identify risk management triggers
- [ ] Determine required data fields for scanning

### 2. Review Existing Code Patterns
- [ ] Study how CSP/CC/Collar are implemented
- [ ] Identify all locations where strategy-specific code exists
- [ ] Note conditional logic that checks strategy types
- [ ] Review test files for testing patterns

---

## Implementation Checklist

### Phase 1: Core Scanner Logic (Lines ~500-2500)

#### A. Strategy Constants & Configuration
**Location:** Top of file, strategy definitions

- [ ] Add strategy to `VALID_STRATEGIES` list/constant (if exists)
- [ ] Add strategy display name to UI mappings
- [ ] Add strategy to any strategy dropdown options

**Files to check:**
```python
# Example locations:
- Line ~100-200: Constants and configurations
- Tab definitions where strategies are listed
```

#### B. Scanning Function
**Location:** `scan_[strategy_name]()` function

- [ ] Create new `scan_YOUR_STRATEGY()` function
- [ ] Implement option chain filtering logic
- [ ] Calculate strategy-specific metrics (OTM%, ROI, Greeks)
- [ ] Generate required strike combinations
- [ ] Return DataFrame with ALL required columns
- [ ] Add proper error handling

**Required DataFrame columns:**
```python
# Standard columns needed:
- 'Ticker', 'Price', 'Exp', 'Days', 'IV'
- Strategy-specific strikes (e.g., 'PutLongStrike', 'PutShortStrike')
- 'Premium' or 'NetCredit'
- 'OTM%', 'ROI%', 'ROI%_ann'
- Greeks: 'Δ' (Delta), 'Γ' (Gamma), 'Θ' (Theta), 'Vρ' (Vega)
- 'OI' (Open Interest)
- 'PutLeg', 'CallLeg' (option symbols for legs)
```

**Common mistakes:**
- ❌ Forgetting to include all Greek columns
- ❌ Missing OTM% calculation
- ❌ Not annualizing ROI
- ❌ Incomplete strike price columns
- ❌ Missing option symbols for multi-leg strategies

#### C. UI Tab Setup
**Location:** Scanner tab section (~Lines 2500-3500)

- [ ] Add new tab to `st.tabs()` list
- [ ] Create tab content with filtering controls
- [ ] Add strategy-specific input fields (strikes, spreads, etc.)
- [ ] Include scan button and progress indicators
- [ ] Display results in dataframe
- [ ] Add column configurations for display

**Example:**
```python
# Add to tabs list:
tabs = st.tabs(["CSP", "CC", "Collar", "YOUR_STRATEGY", "Iron Condor", ...])

# In new tab:
with tabs[X]:  # X = your tab index
    st.header("Your Strategy Scanner")
    # ... filtering controls ...
    if st.button("🔍 Run Your Strategy Scan"):
        df = scan_your_strategy(...)
        st.session_state.your_strategy_results = df
```

### Phase 2: Trade Execution (Lines ~3500-4500)

#### A. Global Selection Tracking
**Location:** `_get_selected_row()` function

- [ ] Add strategy to session state checking
- [ ] Include strategy in dropdown options
- [ ] Return strategy type and selected row correctly

**Example:**
```python
def _get_selected_row():
    # ...existing strategies...
    elif selected_strategy == "YOUR_STRATEGY":
        if 'your_strategy_results' in st.session_state:
            results = st.session_state.your_strategy_results
            # ...
    return selected_strategy, selected_row
```

#### B. Order Preview Section
**Location:** Order preview button handler (~Line 4000-4125)

- [ ] Add strategy case to order creation logic
- [ ] Use appropriate `trader.create_*_order()` method
- [ ] Pass all required strikes and parameters
- [ ] Handle multi-leg structures properly

**Example:**
```python
elif selected_strategy == "YOUR_STRATEGY":
    order = trader.create_your_strategy_order(
        symbol=selected['Ticker'],
        expiration=selected['Exp'],
        # ... all required strikes ...
        quantity=int(num_contracts),
        limit_price=float(limit_price),
        duration=order_duration
    )
    strategy_type = "your_strategy"
```

#### C. Order Generation Section
**Location:** Generate Order Files button handler (~Line 4125-4260)

- [ ] Add entry order generation for strategy
- [ ] Implement exit order logic (profit-taking)
- [ ] Implement stop-loss order logic
- [ ] Store all orders in session state
- [ ] Add to `generated_orders` dictionary

**Common mistakes:**
- ❌ Using wrong strike price fields from DataFrame
- ❌ Forgetting to convert strings to float/int
- ❌ Not handling NET_CREDIT vs NET_DEBIT order types
- ❌ Missing exit order generation
- ❌ Forgetting stop-loss orders

#### D. Exit Order Generation
**Location:** After entry order creation (~Line 4260-4390)

- [ ] Calculate profit target price
- [ ] Create exit order (typically opposite of entry)
- [ ] Use **"GTC"** duration (not `order_duration`)
- [ ] Add profit metadata (entry premium, exit price, profit amount)
- [ ] Handle multi-leg exits properly

**Formula reference:**
```python
# For credit spreads:
exit_price = entry_credit * (1.0 - profit_capture_pct / 100.0)

# For debit spreads:
exit_credit = entry_debit * (1.0 + profit_capture_pct / 100.0)
```

#### E. Stop-Loss Order Generation
**Location:** After exit order creation (~Line 4390-4500)

- [ ] Calculate stop-loss trigger (typically 2x max profit)
- [ ] Create stop-loss order
- [ ] Use **"GTC"** duration
- [ ] Add risk metadata (max loss, multiplier, trigger price)
- [ ] Validate stop-loss is worse than entry

**Formula reference:**
```python
# For credit spreads:
stop_loss_debit = entry_credit * risk_multiplier  # e.g., 2.0x

# For debit spreads:
stop_loss_credit = entry_debit / risk_multiplier
```

### Phase 3: Trade Provider Integration (providers/schwab_trading.py)

#### A. Order Creation Methods
**Location:** `providers/schwab_trading.py`

- [ ] Create `create_your_strategy_order()` method
- [ ] Implement multi-leg structure if needed
- [ ] Set correct instruction types (BUY_TO_OPEN, SELL_TO_OPEN, etc.)
- [ ] Handle orderStrategyType (SINGLE vs BUTTERFLY, VERTICAL, etc.)
- [ ] Add validation logic

**Multi-leg order structure:**
```python
def create_your_strategy_order(self, ...):
    # Build each leg
    order = {
        "orderType": "NET_CREDIT" or "NET_DEBIT",
        "orderStrategyType": "VERTICAL" or "BUTTERFLY" or "IRON_CONDOR",
        "duration": duration,
        "price": limit_price,
        "orderLegCollection": [
            # Leg 1: Buy/Sell option 1
            {"instruction": "BUY_TO_OPEN", "quantity": quantity, ...},
            # Leg 2: Buy/Sell option 2
            {"instruction": "SELL_TO_OPEN", "quantity": quantity, ...},
            # ... more legs ...
        ]
    }
    return order
```

#### B. Exit Order Methods

- [ ] Create `create_your_strategy_exit_order()` method
- [ ] Reverse all leg instructions (BUY ↔ SELL, OPEN ↔ CLOSE)
- [ ] Use opposite order type (CREDIT ↔ DEBIT)
- [ ] Maintain same strike structure

**Example:**
```python
# Entry: SELL_TO_OPEN → Exit: BUY_TO_CLOSE
# Entry: BUY_TO_OPEN → Exit: SELL_TO_CLOSE
# Entry: NET_CREDIT → Exit: NET_DEBIT
```

### Phase 4: Risk Analysis - Monte Carlo (Lines ~5300-5600)

#### A. Monte Carlo Simulation Section
**Location:** Monte Carlo tab section

- [ ] Add strategy to drift default logic
- [ ] Implement P&L calculation function
- [ ] Handle multi-leg position structures
- [ ] Calculate max profit and max loss correctly
- [ ] Add breakeven point calculations

**Critical function:**
```python
# Add strategy case to drift defaults
if strat_choice_preview == "YOUR_STRATEGY":
    default_drift = 0.07  # or appropriate default

# Implement P&L calculation
def calc_your_strategy_pnl(S_T, strikes, premium, ...):
    """
    Calculate P&L for your strategy at expiration
    
    Args:
        S_T: Terminal stock price
        strikes: Dictionary of strike prices
        premium: Net credit/debit received/paid
        
    Returns:
        P&L per contract
    """
    # Calculate intrinsic value of each leg
    # Sum up total position value
    # Return (position_value - entry_cost) * 100
```

#### B. Test Different Scenarios

- [ ] Profit scenario (within profit zone)
- [ ] Loss scenario (outside strikes)
- [ ] Breakeven scenarios
- [ ] Maximum profit scenario
- [ ] Maximum loss scenario

### Phase 5: Position Overview (Lines ~5600-5800)

#### A. Overview Tab Integration
**Location:** Overview tab section

- [ ] Add strategy to overview display logic
- [ ] Show all leg details (strikes, types, quantities)
- [ ] Display max profit and max loss correctly
- [ ] Show breakeven points
- [ ] Include probability calculations if applicable

**Common mistakes:**
- ❌ Not handling missing strategy case (returns None/error)
- ❌ Displaying wrong strike prices
- ❌ Incorrect max profit/loss calculations
- ❌ Missing breakeven point display

#### B. Position Diagram

- [ ] Add visual representation of strategy
- [ ] Show P&L curve at expiration
- [ ] Mark breakeven points
- [ ] Highlight profit/loss zones
- [ ] Display current stock price marker

### Phase 6: Testing & Validation

#### A. Unit Tests
**Location:** `test_*.py` files

- [ ] Create `test_your_strategy.py` or add to existing test file
- [ ] Test scanning function with various inputs
- [ ] Test order generation (entry, exit, stop-loss)
- [ ] Test P&L calculations at various price points
- [ ] Test edge cases (zero premium, extreme strikes)
- [ ] Validate all required DataFrame columns present

**Test structure:**
```python
def test_your_strategy_scanner():
    """Test strategy scanner returns valid results"""
    results = scan_your_strategy(...)
    assert not results.empty
    assert 'Ticker' in results.columns
    assert 'NetCredit' in results.columns
    # ... all required columns ...

def test_your_strategy_order_generation():
    """Test entry order creation"""
    order = trader.create_your_strategy_order(...)
    assert order['orderType'] in ['NET_CREDIT', 'NET_DEBIT']
    assert len(order['orderLegCollection']) == EXPECTED_LEGS
    # ... validate each leg ...

def test_your_strategy_exit_order():
    """Test exit order creation"""
    exit_order = trader.create_your_strategy_exit_order(...)
    # Validate reversed instructions
    # Validate opposite order type

def test_your_strategy_stop_loss():
    """Test stop-loss order creation"""
    stop_order = trader.create_your_strategy_order(...)
    # Validate stop trigger price
    # Validate GTC duration

def test_your_strategy_pnl():
    """Test P&L calculation accuracy"""
    pnl = calc_your_strategy_pnl(...)
    # Test profit scenario
    # Test loss scenario
    # Test max profit
    # Test max loss
```

#### B. Integration Tests

- [ ] Test full workflow: Scan → Select → Generate Orders → Preview
- [ ] Test order consistency (entry/exit/stop-loss match)
- [ ] Test Monte Carlo simulation runs without errors
- [ ] Test Overview tab displays correctly
- [ ] Verify all three orders can be previewed with Schwab API

**Create consistency test:**
```python
def test_your_strategy_consistency():
    """Test all orders for strategy are consistent"""
    # Generate entry, exit, stop-loss
    # Verify symbols match
    # Verify quantities match
    # Verify strikes match
    # Verify order types are correct
```

#### C. Manual Testing Checklist

- [ ] Run scanner with various tickers and parameters
- [ ] Verify all columns display correctly in DataFrame
- [ ] Select a contract and generate all three orders
- [ ] Download each order and inspect JSON
- [ ] Preview each order with Schwab API (if available)
- [ ] Check Monte Carlo simulation with strategy
- [ ] Verify Overview tab shows complete information
- [ ] Test with edge cases (low premium, wide spreads, etc.)

### Phase 7: Documentation

#### A. Code Documentation

- [ ] Add docstrings to all new functions
- [ ] Document parameter types and return values
- [ ] Include example usage in docstrings
- [ ] Add inline comments for complex logic

**Example:**
```python
def scan_your_strategy(
    tickers: List[str],
    min_dte: int,
    max_dte: int,
    wing_width: float,
    min_credit: float,
    **kwargs
) -> pd.DataFrame:
    """
    Scan for Your Strategy opportunities.
    
    This strategy involves [describe structure]. Entry creates a net
    [credit/debit] with defined risk and limited profit potential.
    
    Args:
        tickers: List of underlying symbols to scan
        min_dte: Minimum days to expiration
        max_dte: Maximum days to expiration
        wing_width: Width between strikes (e.g., $5)
        min_credit: Minimum net credit to collect ($)
        
    Returns:
        DataFrame with columns:
        - Standard: Ticker, Price, Exp, Days, IV
        - Strikes: Strike1, Strike2, Strike3, Strike4
        - Metrics: NetCredit, OTM%, ROI%, ROI%_ann
        - Greeks: Δ, Γ, Θ, Vρ
        - Symbols: Leg1, Leg2, Leg3, Leg4
        
    Example:
        >>> results = scan_your_strategy(
        ...     tickers=['SPY', 'QQQ'],
        ...     min_dte=30,
        ...     max_dte=45,
        ...     wing_width=5.0,
        ...     min_credit=0.50
        ... )
    """
```

#### B. User Documentation

- [ ] Add strategy to README.md
- [ ] Create strategy-specific guide (e.g., `YOUR_STRATEGY_GUIDE.md`)
- [ ] Document scanning parameters and what they mean
- [ ] Include example trades with screenshots
- [ ] Document risk management approach
- [ ] Add to strategy comparison table

**Documentation structure:**
```markdown
# Your Strategy Guide

## Overview
[Brief description of strategy structure and use cases]

## When to Use
- Market condition 1
- Market condition 2
- Risk profile needed

## Scanning Parameters
- **Parameter 1**: Description and typical values
- **Parameter 2**: Description and typical values

## Entry Rules
1. Rule 1
2. Rule 2

## Exit Rules
1. Profit target: X% of max profit
2. Stop loss: Y× max profit loss
3. Time-based: Exit at Z DTE

## Example Trade
[Detailed walkthrough with numbers]

## Risk Management
- Max profit: [formula]
- Max loss: [formula]
- Breakeven: [formula]

## Common Mistakes
- Mistake 1 and how to avoid
- Mistake 2 and how to avoid
```

#### C. Update Existing Documentation

- [ ] Update main README with new strategy
- [ ] Update USER_GUIDE.md with new strategy workflow
- [ ] Update QUICKSTART guides
- [ ] Add to any strategy comparison documents
- [ ] Update test documentation

---

## Common Pitfalls & Solutions

### 1. Missing Strategy in Dictionary/Mapping
**Problem:** Strategy works in scanner but not in trade execution
**Solution:** Search codebase for all strategy conditionals:
```bash
grep -r "CSP\|CC\|COLLAR" strategy_lab.py | grep -i "if\|elif"
```
Add your strategy to ALL conditional blocks.

### 2. Wrong DataFrame Columns
**Problem:** "KeyError: 'Strike'" when selecting contract
**Solution:** Ensure scan function returns ALL columns that trade execution expects:
- Check what fields are accessed in `selected['FieldName']`
- Add those fields to scanner output
- Use consistent naming (e.g., 'NetCredit' not 'Credit')

### 3. Order Generation Fails
**Problem:** Order preview or generation throws error
**Solution:** 
- Verify all strikes convert to float: `float(selected['Strike'])`
- Check all required fields exist in selected row
- Ensure order method exists in SchwabTrader class
- Validate order structure matches Schwab API format

### 4. Monte Carlo Crashes
**Problem:** "KeyError" or "TypeError" in Monte Carlo tab
**Solution:**
- Add strategy to drift default logic
- Implement P&L calculation function
- Handle case where strategy data missing
- Return 0 or None gracefully for unsupported scenarios

### 5. Preview Button Does Nothing
**Problem:** Preview button clicked but no result
**Solution:**
- Ensure orders stored in `st.session_state.generated_orders`
- Check preview button has unique key
- Verify preview result stored in `st.session_state.preview_results`
- Add `st.rerun()` after successful preview

### 6. Exit Orders Wrong Duration
**Problem:** Exit orders use DAY instead of GTC
**Solution:** Always hardcode exit and stop-loss orders to `"GTC"`:
```python
duration="GTC"  # NOT duration=order_duration
```

### 7. Inconsistent Order Quantities
**Problem:** Entry has 1 contract, exit has 2
**Solution:** Use same `quantity` variable for all orders:
```python
quantity = int(num_contracts)  # Define once
# Use in entry, exit, and stop-loss
```

### 8. Stop-Loss Not Generated
**Problem:** Only entry and exit orders created
**Solution:** Check `generate_stop_loss` checkbox state and implement logic:
```python
if generate_stop_loss:
    # Create stop-loss order
    # Store in session state
```

---

## Testing Workflow

### Step-by-Step Testing Process

1. **Unit Test Scanner**
   ```bash
   python3 -c "from strategy_lab import scan_your_strategy; print(scan_your_strategy(...))"
   ```

2. **Test Order Creation**
   ```bash
   python3 test_your_strategy.py
   ```

3. **Manual UI Test**
   - Run scanner
   - Select contract
   - Generate orders
   - Preview each order
   - Download orders
   - Check JSON structure

4. **Monte Carlo Test**
   - Select contract
   - Run Monte Carlo simulation
   - Verify P&L curve makes sense
   - Check max profit/loss match expectations

5. **Consistency Test**
   ```bash
   python3 test_trade_ticket_consistency.py
   ```

6. **Integration Test**
   - Full workflow from scan to order submission
   - Test with different tickers
   - Test with different parameter combinations
   - Verify all edge cases

---

## Code Review Checklist

Before committing your changes:

### Completeness
- [ ] All 7 phases implemented
- [ ] No hardcoded values (use variables/constants)
- [ ] All error cases handled
- [ ] All session state properly managed

### Code Quality
- [ ] No duplicate code (use functions)
- [ ] Consistent naming conventions
- [ ] Proper indentation and formatting
- [ ] No commented-out code left behind

### Testing
- [ ] All unit tests pass
- [ ] Integration tests pass
- [ ] Manual testing completed
- [ ] Edge cases tested

### Documentation
- [ ] All functions have docstrings
- [ ] User guide updated
- [ ] README updated
- [ ] Comments added for complex logic

### Git Hygiene
- [ ] Meaningful commit messages
- [ ] Separate commits for each phase
- [ ] No unrelated changes included
- [ ] No merge conflicts

---

## Quick Reference: Files to Update

For every new strategy, touch these files:

1. **strategy_lab.py** - Main application logic
   - Scanner function (~500-2500)
   - UI tabs (~2500-3500)
   - Trade execution (~3500-4900)
   - Monte Carlo (~5300-5600)
   - Overview (~5600-5800)

2. **providers/schwab_trading.py** - Order creation
   - Add `create_your_strategy_order()`
   - Add `create_your_strategy_exit_order()`

3. **Test Files**
   - `test_your_strategy.py` - New test file
   - `test_trade_ticket_consistency.py` - Add strategy cases
   - `test_order_preview.py` - Add strategy validation

4. **Documentation**
   - `README.md` - Add strategy overview
   - `YOUR_STRATEGY_GUIDE.md` - Create detailed guide
   - `USER_GUIDE.md` - Update workflow section
   - `ADDING_NEW_STRATEGY_GUIDE.md` - Update this guide!

---

## Example: Iron Condor Implementation Lessons

### What Went Wrong
1. ❌ Initially forgot to add to Monte Carlo drift logic → MC used wrong default
2. ❌ Forgot to add to Overview tab → Showed "No data" when IC selected
3. ❌ Initially used 2 legs instead of 4 → Exit orders incomplete
4. ❌ Missed stop-loss generation for IC → Only entry/exit created
5. ❌ Didn't update tests → No validation of IC orders

### What Went Right
1. ✅ Created separate exit order method for IC
2. ✅ Properly handled NET_CREDIT and NET_DEBIT order types
3. ✅ Implemented comprehensive P&L calculation
4. ✅ Added detailed scanner with all spreads
5. ✅ Documented thoroughly after implementation

### Key Learnings
- **Search first, code second**: Grep for existing strategies before coding
- **Test incrementally**: Don't wait until end to test
- **Document as you go**: Write docs while details are fresh
- **Use checklists**: This guide exists because of Iron Condor mistakes!

---

## Summary

Adding a new strategy requires touching **7 phases** across **multiple files**. Use this checklist to ensure complete implementation:

1. ✅ Scanner logic with all columns
2. ✅ Trade execution (entry, exit, stop-loss)
3. ✅ Order provider methods
4. ✅ Monte Carlo simulation
5. ✅ Position overview
6. ✅ Comprehensive testing
7. ✅ Complete documentation

**Pro Tip**: Copy this checklist into a GitHub Issue when implementing a new strategy, then check off items as you complete them. This ensures nothing is forgotten!

---

**Last Updated**: October 30, 2025  
**Based on**: Iron Condor implementation experience  
**Contributors**: Lessons learned from real implementation mistakes
