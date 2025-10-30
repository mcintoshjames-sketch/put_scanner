# Order Preview Feature# Order Preview Feature



## Overview## Overview

The Strategy Lab now supports previewing **all three order types** (entry, profit exit, and stop-loss) using the Schwab API before submission. This allows you to validate orders, check commissions, and review buying power requirements before actually placing trades.The Order Preview feature allows you to test trade orders with Schwab API **without actually placing them**. This provides a safe intermediate step between dry-run (JSON export only) and live trading.



## Feature Summary## What Is Order Preview?

Order preview POSTs your order to Schwab's `previewOrder` endpoint and returns detailed information about what would happen if the order were placed, including:

### What's New

- **Individual Preview Buttons**: Each order type (entry, exit, stop-loss) now has its own 🔍 Preview button- **Estimated Commission & Fees**: Exact cost to execute the order

- **Schwab API Integration**: Real-time preview using Schwab's preview API endpoint- **Order Value**: Total credit/debit amount

- **Comprehensive Order Coverage**: Works for all 4 strategies (CSP, CC, Collar, Iron Condor)- **Buying Power Effect**: How the order impacts your account's buying power

- **Detailed Preview Information**: Shows commission, costs, buying power impact, and margin requirements- **Margin Requirements**: Collateral needed for the position

- **Warning Messages**: Any issues or concerns from Schwab

### Previous Limitation- **Order Confirmation Details**: Exactly how Schwab will process the order

Previously, only the **entry order** could be previewed via a single button. Exit and stop-loss orders had to be downloaded and manually checked.

## Why Use Order Preview?

### Current Capability

Now you can preview:### Safety Benefits

1. **Entry Order** - Before initial trade submission✅ **No Risk**: Preview doesn't place actual trades  

2. **Profit Exit Order** - Before setting your profit target✅ **Real Data**: Get actual Schwab estimates (not simulated)  

3. **Stop-Loss Order** - Before setting your risk limit✅ **Validate Orders**: Catch errors before risking capital  

✅ **Check Costs**: See exact commission and fees  

## How It Works✅ **Verify Requirements**: Confirm you have sufficient buying power  



### UI Layout### Workflow Progression

```1. **Phase 1 (Complete)**: Dry-run mode - export orders to JSON for offline review

┌─────────────────────┬─────────────────────┬─────────────────────┐2. **Phase 2 (Complete)**: Account retrieval - get encrypted account IDs

│   📤 ENTRY Order    │  📥 EXIT Order      │  🛑 STOP-LOSS       │3. **Phase 3 (Current)**: Order preview - POST to Schwab API and view response

├─────────────────────┼─────────────────────┼─────────────────────┤4. **Phase 4 (Future)**: Live trading - actual order execution

│ Order details...    │ Order details...    │ Order details...    │

│                     │                     │                     │## How To Use

│ ┌─────┬──────────┐  │ ┌─────┬──────────┐  │ ┌─────┬──────────┐  │

│ │  🔍 │    ⬇️    │  │ │  🔍 │    ⬇️    │  │ │  🔍 │    ⬇️    │  │### Prerequisites

│ │Prev.│ Download │  │ │Prev.│ Download │  │ │Prev.│ Download │  │1. **Schwab Account Retrieved** (Step 1)

│ └─────┴──────────┘  │ └─────┴──────────┘  │ └─────┴──────────┘  │   - Click "🔍 Retrieve Account Numbers" 

└─────────────────────┴─────────────────────┴─────────────────────┘   - Copy the encrypted `hashValue`

```   - Set it as `SCHWAB_ACCOUNT_ID` environment variable



### Preview Button Actions2. **Schwab Provider Active**

   - Set `OPTIONS_PROVIDER=schwab` in environment

#### Entry Order Preview   - Configure `SCHWAB_API_KEY` and `SCHWAB_APP_SECRET`

- Click **🔍 Preview** under entry order   - Authenticate with Schwab (token file created)

- Calls `trader.preview_order(entry_order)`

- Displays:### Steps to Preview an Order

  - Commission fees

  - Estimated credit (for CSP/CC/Collar)1. **Run a CSP scan** in strategy_lab.py

  - Buying power impact   - Adjust filters and click "🔍 Run CSP Scan"

  - Margin requirement   - Review scan results in data table

  - Full Schwab API response

2. **Select a contract** in Trade Execution panel

#### Exit Order Preview   - Choose from dropdown of scan results

- Click **🔍 Preview** under exit order   - Set number of contracts

- Calls `trader.preview_order(exit_order)`   - Set limit price (defaults to scan premium)

- Displays:   - Choose order duration (DAY or GTC)

  - Commission fees

  - Estimated cost to close position3. **Click "🔍 Preview Order with Schwab API"**

  - Buying power effect   - Order is validated first

  - Full Schwab API response   - POSTs to Schwab preview endpoint

   - Schwab returns preview response

#### Stop-Loss Order Preview

- Click **🔍 Preview** under stop-loss order4. **Review Schwab's preview response**

- Calls `trader.preview_order(stop_loss_order)`   - Commission amount

- Displays:   - Estimated credit/debit

  - Commission fees   - Buying power effect

  - Estimated cost at stop trigger   - Margin requirement

  - Buying power effect   - Any warnings from Schwab

  - Margin requirement   - Full JSON response for details

  - Full Schwab API response

5. **Optional: Export to JSON** (Step 2)

### Special Cases   - Click "📥 Generate Order File" for dry-run export

   - Download order JSON for offline review

#### Collar Strategy

Collar has **2 exit orders** (call and put):## Technical Details

- **🔍 Preview Call** - Preview call exit order

- **🔍 Preview Put** - Preview put exit order### Implementation

- **🔍 Preview** (stop-loss) - Preview stop-loss on call- **Method**: `SchwabTrader.preview_order(order, account_id)`

- **API Endpoint**: `POST /trader/v1/accounts/{accountHash}/previewOrder`

Both exit orders can be previewed independently.- **schwab-py**: Uses `client.preview_order(account_hash, order_spec)`

- **Response**: JSON with commission, costs, requirements, warnings

#### Iron Condor Strategy

Iron Condor has **4-leg orders**:### File Storage

- Entry: 4 legs (Buy Put, Sell Put, Sell Call, Buy Call)Preview responses are automatically saved to:

- Exit: 4 legs (reversed actions)```

- Stop-Loss: 4 legs (reversed actions)./trade_orders/order_preview_YYYYMMDD_HHMMSS.json

```

All three can be previewed as complete 4-leg spreads.

File contains:

## Preview API Response```json

{

### Successful Preview  "timestamp": "2025-01-29T21:45:00",

```json  "account_id": "406195DF...",

{  "order": { /* full order payload */ },

  "status": "preview_success",  "preview": { /* Schwab's preview response */ }

  "preview": {}

    "commission": 0.65,```

    "estimatedTotalAmount": 550.00,

    "buyingPowerEffect": -5500.00,### Error Handling

    "marginRequirement": 5500.00,If preview fails, error details are saved to:

    "warnings": []```

  },./trade_orders/order_preview_error_YYYYMMDD_HHMMSS.json

  "filepath": "./trade_orders/csp_TEST_251115P00550000_preview.json"```

}

```## UI Components



### Preview Metrics Displayed### Preview Button Location

1. **Commission**: Schwab's fee for the trade (typically $0.65 per contract)- **Tab**: Cash-Secured Puts (CSP)

2. **Estimated Total Amount**: - **Section**: Trade Execution (Test Mode) expander

   - Entry orders: Credit received (positive)- **Step**: Step 2 - Create Order

   - Exit orders: Cost to close (positive = debit)- **Position**: Left column (next to "Generate Order File")

3. **Buying Power Effect**: Impact on account buying power (negative = reduces BP)

4. **Margin Requirement**: Cash/margin needed to secure position### Preview Response Display

- Expandable section: "📊 Schwab Preview Response"

### Error Handling- Key metrics shown as st.metric() cards

If preview fails:- Full JSON response for detailed inspection

- Error message displayed with reason- File path for saved preview

- Order structure may be invalid

- API credentials may be missing## Code Structure

- Account may not be authorized for strategy

### providers/schwab_trading.py

## Requirements```python

def preview_order(

### Schwab API Setup    self,

1. **Environment Variables**:    order: Dict[str, Any],

   ```bash    account_id: Optional[str] = None

   export OPTIONS_PROVIDER=schwab) -> Dict[str, Any]:

   export SCHWAB_API_KEY=your_key    """Preview order with Schwab API"""

   export SCHWAB_APP_SECRET=your_secret    # Validates client and account_id

   ```    # Calls schwab client.preview_order()

    # Saves response to JSON file

2. **OAuth Authentication**:    # Returns formatted result

   - Must complete OAuth flow once```

   - Token stored in `schwab_token.json`

   - Auto-refreshes when expired### strategy_lab.py

```python

3. **Account Authorization**:# Preview button in Trade Execution panel

   - Account must be approved for options tradingif st.button("🔍 Preview Order with Schwab API"):

   - Level 2+ required for spreads (Iron Condor)    # Initialize trader (NOT dry_run mode)

   - Cash-secured puts may require specific approval    trader = SchwabTrader(dry_run=False, client=schwab_client)

    

### Preview vs. Submit    # Create order payload

- **Preview**: Validates order, shows costs, **does not place trade**    order = trader.create_cash_secured_put_order(...)

- **Submit**: Actually places the trade with broker    

- **Always preview before submitting** to avoid surprises    # Validate order first

    validation = trader.validate_order(order)

## Use Cases    

    # Call preview API

### Pre-Trade Validation    preview_result = trader.preview_order(order)

```    

1. Generate order files    # Display Schwab's response

2. Preview entry order → Check commission & BP```

3. If acceptable, download and submit via Schwab

4. Preview exit order → Verify it will work when needed## Security Considerations

5. Preview stop-loss → Ensure protection is in place

6. Download exit & stop-loss for post-fill submission### What Is Sent to Schwab

```- Order payload (symbol, strike, quantity, price, duration)

- Account hash (encrypted ID, not plain text account number)

### Commission Verification- OAuth token (for authentication)

```

Entry Preview:    $0.65 commission ✓### What Is NOT Sent

Exit Preview:     $0.65 commission ✓- API key or app secret (used for initial auth only)

Stop-Loss Preview: $0.65 commission ✓- Plain text account number

Total Round-Trip: $1.95 (entry + exit)- Any personal information beyond order details

```

### Local Storage

### Buying Power Planning- Preview responses saved to `./trade_orders/` directory

```- Directory is in `.gitignore` (not committed to git)

Entry BP Impact:     -$5,500 (margin locked)- Files contain order details and Schwab's response

Exit BP Release:     +$5,500 (when closed)- No sensitive credentials in files

Stop-Loss BP Impact: -$11,000 (if triggered at 2x loss)

```## Limitations



### Multi-Account Testing### What Preview Does NOT Do

```❌ Place actual trades  

# Test order in paper trading account❌ Reserve capital or positions  

Preview with account A → See dry-run results❌ Guarantee execution at preview price  

❌ Lock in commission rates  

# Execute in live account❌ Create working orders  

Submit to account B → Actual trade

```### Important Notes

⚠️ Preview is a **simulation** of what would happen  

## Testing⚠️ Actual execution may differ if market moves  

⚠️ Commission and fees are estimates  

### Order Structure Tests⚠️ Buying power can change between preview and execution  

Run validation tests:⚠️ Preview does not check for duplicate orders  

```bash

python3 test_order_preview.py## Next Steps

```

### After Successful Preview

**Test Coverage**:1. **Review all details carefully**

- ✅ CSP: Entry, profit exit, stop-loss (1-leg each)   - Check commission is acceptable

- ✅ CC: Entry, profit exit, stop-loss (1-leg each)   - Verify buying power is sufficient

- ✅ Iron Condor: Entry, exit, stop-loss (4-leg each)   - Read any warnings from Schwab

- ✅ Collar: Entry (2-leg), call/put exits, stop-loss   - Confirm order parameters are correct

- ✅ Order structure validity

- ✅ GTC duration for exits2. **Export to JSON** (optional)

- ✅ DAY duration for entries   - Use "Generate Order File" for offline record

   - Review order structure and metadata

### Live API Testing

1. Set up Schwab credentials3. **Future: Place Order** (not yet implemented)

2. Run Strategy Lab: `streamlit run strategy_lab.py`   - Once preview testing is complete

3. Generate orders for a test position   - Actual order submission will require user confirmation

4. Click preview buttons   - Will use preview response to show final details

5. Verify API responses

### Development Roadmap

## Benefits- ✅ Phase 1: Dry-run export to JSON

- ✅ Phase 2: Account number retrieval  

### Risk Management- ✅ Phase 3: Order preview with Schwab API (Current)

- **Validate before trading**: Catch errors before money is at risk- ⏭️ Phase 4: Live order placement (Future)

- **Verify calculations**: Ensure limit prices are correct

- **Check commissions**: Know exact costs upfront## Troubleshooting

- **Confirm BP availability**: Make sure account can handle position

### "Schwab client not available"

### Workflow Improvement**Solution**: Ensure Schwab provider is active

- **No more blind submissions**: See what Schwab will receive```bash

- **Faster corrections**: Fix issues before placing ordersexport OPTIONS_PROVIDER=schwab

- **Better planning**: Understand total cost of round-trip tradeexport SCHWAB_API_KEY=your_key

- **Educational**: Learn how Schwab sees your ordersexport SCHWAB_APP_SECRET=your_secret

```

### Professional Execution

- **Complete visibility**: All three orders previewed independently### "Account ID required"

- **Granular control**: Preview only what you need**Solution**: Retrieve account first (Step 1)

- **Documentation**: Each preview saved to file for records```bash

- **Confidence**: Trade knowing exactly what will happen# In UI: Click "Retrieve Account Numbers"

# Then set environment variable:

## Troubleshootingexport SCHWAB_ACCOUNT_ID=your_encrypted_hash

```

### "Schwab provider not active"

**Cause**: OPTIONS_PROVIDER not set to "schwab"### "Authentication failed"

**Fix**: **Solution**: Token may be expired

```bash```bash

export OPTIONS_PROVIDER=schwab# Delete token file to force re-authentication

```rm schwab_token.json

# Restart app and re-authenticate

### "Schwab client not available"```

**Cause**: OAuth not completed or token expired

**Fix**: ### "Order validation failed"

1. Delete `schwab_token.json`**Solution**: Check order parameters

2. Restart Strategy Lab- Verify symbol exists and is option-eligible

3. Complete OAuth flow in browser- Ensure strike price is valid

- Check quantity is positive integer

### "Preview failed: Invalid order"- Confirm limit price is reasonable

**Cause**: Order structure incorrect- Verify expiration date is valid

**Fix**: 

1. Check order details in expander## Example Preview Response

2. Verify strikes, expiration, quantity

3. Ensure account authorized for strategy type```json

{

### "Commission not shown"  "status": "preview_success",

**Cause**: Schwab API didn't return commission field  "preview": {

**Note**: Some preview responses don't include commission    "orderType": "LIMIT",

**Workaround**: Assume $0.65 per contract (standard rate)    "session": "NORMAL",

    "duration": "DAY",

### Preview very slow    "orderStrategyType": "SINGLE",

**Cause**: Schwab API can take 3-5 seconds    "commission": 0.65,

**Normal**: This is typical API response time    "estimatedTotalAmount": 125.00,

**Tip**: Be patient, don't click multiple times    "buyingPowerEffect": -2500.00,

    "marginRequirement": 2500.00,

## Limitations    "orderLegCollection": [

      {

### Current Constraints        "orderLegType": "OPTION",

1. **One preview at a time**: Can't preview multiple orders simultaneously        "instruction": "SELL_TO_OPEN",

2. **No batch preview**: Each order must be previewed individually        "quantity": 1,

3. **Schwab only**: Preview requires Schwab provider (not YFinance)        "instrument": {

4. **Live API required**: Dry-run mode doesn't call real preview API          "symbol": "TGT_011725P150",

5. **Manual submission**: Preview doesn't auto-submit orders          "assetType": "OPTION"

        }

### Future Enhancements      }

- [ ] **Batch preview**: Preview all 3 orders in one API call    ],

- [ ] **Comparison view**: Side-by-side preview of all orders    "warnings": []

- [ ] **Auto-validation**: Preview automatically before download  },

- [ ] **Preview caching**: Store recent previews to avoid re-calling API  "filepath": "./trade_orders/order_preview_20250129_214500.json",

- [ ] **OCO preview**: Preview One-Cancels-Other linked orders  "message": "Order preview saved to ./trade_orders/order_preview_20250129_214500.json"

- [ ] **Real-time updates**: Live preview as you adjust sliders}

```

## Related Features

## Support

### Download Buttons

After preview, use **⬇️ Download** to save order JSON for Schwab submission.For issues or questions:

1. Check error details in expandable section

### Order Generation2. Review saved preview files in `./trade_orders/`

Generate all 3 orders at once with **📥 Generate Order Files** button.3. Verify Schwab credentials and token validity

4. Consult Schwab API documentation

### Trade Execution5. Test with smaller quantities first

After preview and download, submit orders via:

- Schwab.com web interface## Disclaimer

- Schwab mobile app

- thinkorswim desktop platform⚠️ **IMPORTANT**: This preview feature is for testing purposes only. Always review:

- Order details carefully before actual execution

### Consistency Tests- Your risk tolerance and account size

Validate all 3 orders match with:- Market conditions and volatility

```bash- Schwab's terms of service and commission schedule

python3 test_trade_ticket_consistency.py

```Trading options involves risk of loss. This software is provided as-is without warranty. Use at your own risk.


## Best Practices

### Pre-Trade Checklist
1. ✅ Generate all 3 orders (entry, exit, stop-loss)
2. ✅ Preview entry order → Verify commission & BP
3. ✅ Preview exit order → Confirm profit target works
4. ✅ Preview stop-loss → Ensure risk protection valid
5. ✅ Download all 3 orders
6. ✅ Submit entry order first
7. ✅ Wait for fill
8. ✅ Submit exit & stop-loss immediately after fill

### Risk Management
- **Always preview stop-loss**: Ensure your protection is valid
- **Check BP for all orders**: Make sure you can afford max loss
- **Verify exit prices**: Ensure profit target is achievable
- **Review warnings**: Pay attention to Schwab's warnings

### Error Prevention
- **Preview before every trade**: Don't skip this step
- **Check symbol matches**: Ensure all 3 orders reference same contract
- **Verify quantities**: Confirm all orders trade same number
- **Validate expirations**: Make sure dates are correct

## Summary

The order preview feature provides **complete visibility** into all three order types before submission. By previewing entry, profit exit, and stop-loss orders independently, you can:

- **Validate** order structure and pricing
- **Verify** commissions and costs
- **Confirm** buying power requirements
- **Catch** errors before trading
- **Trade** with confidence

This completes the "set and forget" workflow with professional-grade order validation at every step.

---

**Last Updated**: October 30, 2025  
**Commit**: e3259ed  
**Tests**: 5/5 passing ✅
