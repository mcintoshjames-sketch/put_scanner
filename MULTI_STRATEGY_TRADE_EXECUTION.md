# Multi-Strategy Trade Execution Feature

## Overview

The Trade Execution module now supports **all four strategies**: Cash-Secured Puts (CSP), Covered Calls (CC), Collars, and Iron Condors. This enables you to trade any strategy directly from scan results with proper multi-leg order support.

## Supported Strategies

### 1. Cash-Secured Put (CSP) - 1 Leg
- **Action**: SELL TO OPEN put option
- **Collateral**: Strike price × 100 × contracts
- **Premium**: Credit received upfront
- **Risk**: Obligated to buy stock at strike if assigned

### 2. Covered Call (CC) - 1 Leg  
- **Action**: SELL TO OPEN call option
- **Requirement**: Must own 100 shares per contract
- **Premium**: Credit received upfront
- **Risk**: Stock called away if price rises above strike

### 3. Collar - 2 Legs
- **Action**: SELL TO OPEN call + BUY TO OPEN put
- **Requirement**: Must own 100 shares per contract
- **Net Cost**: Call premium - put premium (can be credit or debit)
- **Purpose**: Downside protection with limited upside

### 4. Iron Condor - 4 Legs
- **Action**: BUY put + SELL put + SELL call + BUY call
- **Net Credit**: Premium received from selling spreads
- **Max Risk**: Max(spread widths) - net credit
- **Purpose**: Profit from range-bound price action

## Feature Workflow

### Step 1: Run Scan
1. Configure scan parameters in the **Scan** tab
2. Run scan to populate results for all strategies
3. Results are stored in separate dataframes:
   - `df_csp` - Cash-Secured Puts
   - `df_cc` - Covered Calls
   - `df_collar` - Collars
   - `df_iron_condor` - Iron Condors

### Step 2: Select Strategy
1. Navigate to **Trade Execution** section
2. Select strategy from dropdown (only shows strategies with results)
3. View strategy-specific information tooltip
4. Contract list updates to show relevant strategy results

### Step 3: Select Contract
Contract display varies by strategy:

**CSP/CC**:
```
AAPL 2025-12-19 $180.00 PUT @ $3.50
```

**Collar**:
```
AAPL 2025-12-19 CALL $200.00 / PUT $160.00 @ $1.50
```

**Iron Condor**:
```
SPY 2025-12-19 P: $540.00/$550.00 C: $590.00/$600.00 @ $2.50
```

### Step 4: Configure Order
- **Contracts**: Number of contracts (1-100)
- **Duration**: DAY or GTC
- **Limit Price**: 
  - CSP/CC: Premium to receive per share
  - Collar/IC: Net credit per share

### Step 5: Order Preview
View strategy-specific details:

**CSP**:
- Action: SELL TO OPEN
- Collateral Required
- Max Premium

**CC**:
- Action: SELL TO OPEN  
- Stock Required (100 shares/contract)
- Max Premium

**Collar**:
- Action: SELL CALL + BUY PUT
- Stock Required
- Net Credit/Debit

**Iron Condor**:
- Action: 4-LEG CREDIT SPREAD
- Max Risk (calculated)
- Max Credit

### Step 6: Verify & Execute

Three action buttons:

#### 💰 Check Buying Power
- Calculates required capital based on strategy
- Queries Schwab API for account balances
- Shows available vs. required capital
- **CSP**: Strike × 100 × contracts
- **CC**: $0 (stock ownership verified separately)
- **Collar**: Cost of put - call premium
- **IC**: Max spread width - net credit

#### 🔍 Preview Order
- Submits order to Schwab preview API
- Returns detailed order information:
  - Commission costs
  - Estimated total amount
  - Buying power impact
  - Margin requirements
  - Any warnings or alerts
- Order is **NOT placed**, only previewed

#### 📥 Generate Order File
- Creates JSON order file in `./trade_orders/`
- Files named: `{strategy}_{ticker}_{timestamp}.json`
- Contains:
  - Full order payload
  - Scanner metadata (IV, delta, theta, etc.)
  - Timestamp and account info
- Can be reviewed and manually submitted later

## Order Structure Examples

### Collar Order (2-leg)
```json
{
  "orderType": "NET_CREDIT",
  "session": "NORMAL",
  "duration": "GTC",
  "price": 1.50,
  "orderLegCollection": [
    {
      "instruction": "SELL_TO_OPEN",
      "quantity": 1,
      "instrument": {
        "symbol": "AAPL  251219C00200000",
        "assetType": "OPTION"
      }
    },
    {
      "instruction": "BUY_TO_OPEN",
      "quantity": 1,
      "instrument": {
        "symbol": "AAPL  251219P00160000",
        "assetType": "OPTION"
      }
    }
  ]
}
```

### Iron Condor Order (4-leg)
```json
{
  "orderType": "NET_CREDIT",
  "session": "NORMAL",
  "duration": "DAY",
  "price": 2.50,
  "orderLegCollection": [
    {
      "instruction": "BUY_TO_OPEN",
      "quantity": 1,
      "instrument": {
        "symbol": "SPY   251219P00540000",
        "assetType": "OPTION"
      }
    },
    {
      "instruction": "SELL_TO_OPEN",
      "quantity": 1,
      "instrument": {
        "symbol": "SPY   251219P00550000",
        "assetType": "OPTION"
      }
    },
    {
      "instruction": "SELL_TO_OPEN",
      "quantity": 1,
      "instrument": {
        "symbol": "SPY   251219C00590000",
        "assetType": "OPTION"
      }
    },
    {
      "instruction": "BUY_TO_OPEN",
      "quantity": 1,
      "instrument": {
        "symbol": "SPY   251219C00600000",
        "assetType": "OPTION"
      }
    }
  ]
}
```

## Technical Implementation

### Backend (schwab_trading.py)

New methods added:

```python
create_collar_order(
    symbol, expiration, call_strike, put_strike, 
    quantity, limit_price, duration
)
```
- Creates 2-leg order: sell call + buy put
- Calculates net credit/debit
- Sets order type to NET_CREDIT or NET_DEBIT

```python
create_iron_condor_order(
    symbol, expiration, 
    long_put_strike, short_put_strike,
    short_call_strike, long_call_strike,
    quantity, limit_price, duration
)
```
- Creates 4-leg order with proper leg ordering
- Buy lower put, sell higher put
- Sell lower call, buy higher call
- Order type: NET_CREDIT

### Frontend (strategy_lab.py)

#### Strategy Selection
- Dynamic dropdown showing only strategies with scan results
- Strategy info tooltips for user education
- `selected_strategy` variable drives all downstream logic

#### Contract Display
- Strategy-specific display formatting
- Shows relevant strikes and prices
- Handles multi-strike strategies (Collar, IC)

#### Order Creation Logic
```python
if selected_strategy == "CSP":
    order = trader.create_cash_secured_put_order(...)
elif selected_strategy == "CC":
    order = trader.create_covered_call_order(...)
elif selected_strategy == "COLLAR":
    order = trader.create_collar_order(...)
elif selected_strategy == "IRON_CONDOR":
    order = trader.create_iron_condor_order(...)
```

#### Buying Power Calculation
- Strategy-specific capital requirements
- Handles both credit and debit scenarios
- Supports option spreads with defined risk

## Safety Features

### Earnings Protection
- Warns if earnings within configured threshold (default: 14 days)
- Shows severity based on proximity:
  - **Red Alert**: Earnings today
  - **Error**: Within threshold (before)
  - **Warning**: Recent report (after)
- Educational explainer about earnings risks

### Order Validation
- Validates order structure before submission
- Checks for missing required fields
- Warns about GTC orders
- Prevents invalid multi-leg combinations

### Test Mode
- All orders exported to JSON files first
- No direct API submission
- Manual review before execution
- Safety for production use

## Testing

Run validation tests:
```bash
python test_multi_leg_orders.py
```

Expected output:
```
✅ All tests passed!

Order Summary:
- CSP: 1 leg(s)
- Covered Call: 1 leg(s)  
- Collar: 2 leg(s)
- Iron Condor: 4 leg(s)
```

## Future Enhancements

### Planned Features
1. **Live order submission** - Direct API execution (currently test mode only)
2. **Order status tracking** - Monitor pending/filled orders
3. **Position management** - Close/roll existing positions
4. **Advanced order types** - Stop loss, trailing stops
5. **Batch order submission** - Multiple orders at once
6. **Order templates** - Save common configurations

### Potential Improvements
- Automatic position size calculation
- Portfolio-level risk management
- Order history and analytics
- Paper trading simulation mode
- Real-time P&L tracking

## Known Limitations

1. **Test Mode Only**: Orders are exported to JSON, not submitted to Schwab API (safety feature)
2. **Stock Ownership**: CC and Collar strategies don't verify stock ownership (user responsibility)
3. **Single Account**: Supports one account ID at a time
4. **No Portfolio View**: Can't see existing positions
5. **Manual Execution**: Generated JSON files must be manually submitted

## Support & Documentation

- **Schwab API Docs**: https://developer.schwab.com/
- **Order JSON Format**: See Schwab API documentation
- **Option Symbol Format**: `SYMBOL  YYMMDDC/PSTRIKE` (6-char padded symbol)
- **Test Files**: `./trade_orders/*.json` for review

## Troubleshooting

### "No scan results available"
- Run a scan first in the Scan tab
- Ensure filters aren't too restrictive
- Check that options data is loading

### "Schwab provider not active"
- Set `OPTIONS_PROVIDER=schwab` in environment
- Configure Schwab API credentials
- Verify token is valid and not expired

### "Order validation failed"
- Check strike prices are in logical order
- Verify expiration date format (YYYY-MM-DD)
- Ensure quantity is positive integer

### "Insufficient buying power"
- Check account balances in Schwab
- Verify capital calculation for strategy type
- Consider reducing contract quantity

## Examples

### Example 1: Trading a Cash-Secured Put
1. Scan finds: AAPL 2025-12-19 $180 PUT @ $3.50
2. Select "Cash-Secured Put" strategy
3. Select contract from list
4. Set 2 contracts, GTC, limit $3.50
5. Check buying power: Need $36,000 (180 × 100 × 2)
6. Preview order with Schwab API
7. Generate order file for review
8. Manually submit if satisfied

### Example 2: Trading an Iron Condor
1. Scan finds: SPY Iron Condor $540/$550 P, $590/$600 C @ $2.50
2. Select "Iron Condor" strategy  
3. Select contract showing all 4 strikes
4. Set 5 contracts, DAY, limit $2.50
5. Check buying power: Need $3,750 (max spread $10 - credit $2.50 × 100 × 5)
6. Preview order with Schwab API (4-leg order)
7. Generate order file
8. Review JSON structure
9. Submit when ready

## Conclusion

The multi-strategy Trade Execution feature provides a complete workflow from scanning to order creation for all four major option strategies. With built-in safety features, earnings protection, and test mode, it's designed for both learning and production use.

**Status**: ✅ **Fully Implemented and Tested**
**Commit**: `6946893` - "Add multi-strategy support to Trade Execution"
**Date**: October 30, 2025
