# Order Preview Feature

## Overview
The Order Preview feature allows you to test trade orders with Schwab API **without actually placing them**. This provides a safe intermediate step between dry-run (JSON export only) and live trading.

## What Is Order Preview?
Order preview POSTs your order to Schwab's `previewOrder` endpoint and returns detailed information about what would happen if the order were placed, including:

- **Estimated Commission & Fees**: Exact cost to execute the order
- **Order Value**: Total credit/debit amount
- **Buying Power Effect**: How the order impacts your account's buying power
- **Margin Requirements**: Collateral needed for the position
- **Warning Messages**: Any issues or concerns from Schwab
- **Order Confirmation Details**: Exactly how Schwab will process the order

## Why Use Order Preview?

### Safety Benefits
✅ **No Risk**: Preview doesn't place actual trades  
✅ **Real Data**: Get actual Schwab estimates (not simulated)  
✅ **Validate Orders**: Catch errors before risking capital  
✅ **Check Costs**: See exact commission and fees  
✅ **Verify Requirements**: Confirm you have sufficient buying power  

### Workflow Progression
1. **Phase 1 (Complete)**: Dry-run mode - export orders to JSON for offline review
2. **Phase 2 (Complete)**: Account retrieval - get encrypted account IDs
3. **Phase 3 (Current)**: Order preview - POST to Schwab API and view response
4. **Phase 4 (Future)**: Live trading - actual order execution

## How To Use

### Prerequisites
1. **Schwab Account Retrieved** (Step 1)
   - Click "🔍 Retrieve Account Numbers" 
   - Copy the encrypted `hashValue`
   - Set it as `SCHWAB_ACCOUNT_ID` environment variable

2. **Schwab Provider Active**
   - Set `OPTIONS_PROVIDER=schwab` in environment
   - Configure `SCHWAB_API_KEY` and `SCHWAB_APP_SECRET`
   - Authenticate with Schwab (token file created)

### Steps to Preview an Order

1. **Run a CSP scan** in strategy_lab.py
   - Adjust filters and click "🔍 Run CSP Scan"
   - Review scan results in data table

2. **Select a contract** in Trade Execution panel
   - Choose from dropdown of scan results
   - Set number of contracts
   - Set limit price (defaults to scan premium)
   - Choose order duration (DAY or GTC)

3. **Click "🔍 Preview Order with Schwab API"**
   - Order is validated first
   - POSTs to Schwab preview endpoint
   - Schwab returns preview response

4. **Review Schwab's preview response**
   - Commission amount
   - Estimated credit/debit
   - Buying power effect
   - Margin requirement
   - Any warnings from Schwab
   - Full JSON response for details

5. **Optional: Export to JSON** (Step 2)
   - Click "📥 Generate Order File" for dry-run export
   - Download order JSON for offline review

## Technical Details

### Implementation
- **Method**: `SchwabTrader.preview_order(order, account_id)`
- **API Endpoint**: `POST /trader/v1/accounts/{accountHash}/previewOrder`
- **schwab-py**: Uses `client.preview_order(account_hash, order_spec)`
- **Response**: JSON with commission, costs, requirements, warnings

### File Storage
Preview responses are automatically saved to:
```
./trade_orders/order_preview_YYYYMMDD_HHMMSS.json
```

File contains:
```json
{
  "timestamp": "2025-01-29T21:45:00",
  "account_id": "406195DF...",
  "order": { /* full order payload */ },
  "preview": { /* Schwab's preview response */ }
}
```

### Error Handling
If preview fails, error details are saved to:
```
./trade_orders/order_preview_error_YYYYMMDD_HHMMSS.json
```

## UI Components

### Preview Button Location
- **Tab**: Cash-Secured Puts (CSP)
- **Section**: Trade Execution (Test Mode) expander
- **Step**: Step 2 - Create Order
- **Position**: Left column (next to "Generate Order File")

### Preview Response Display
- Expandable section: "📊 Schwab Preview Response"
- Key metrics shown as st.metric() cards
- Full JSON response for detailed inspection
- File path for saved preview

## Code Structure

### providers/schwab_trading.py
```python
def preview_order(
    self,
    order: Dict[str, Any],
    account_id: Optional[str] = None
) -> Dict[str, Any]:
    """Preview order with Schwab API"""
    # Validates client and account_id
    # Calls schwab client.preview_order()
    # Saves response to JSON file
    # Returns formatted result
```

### strategy_lab.py
```python
# Preview button in Trade Execution panel
if st.button("🔍 Preview Order with Schwab API"):
    # Initialize trader (NOT dry_run mode)
    trader = SchwabTrader(dry_run=False, client=schwab_client)
    
    # Create order payload
    order = trader.create_cash_secured_put_order(...)
    
    # Validate order first
    validation = trader.validate_order(order)
    
    # Call preview API
    preview_result = trader.preview_order(order)
    
    # Display Schwab's response
```

## Security Considerations

### What Is Sent to Schwab
- Order payload (symbol, strike, quantity, price, duration)
- Account hash (encrypted ID, not plain text account number)
- OAuth token (for authentication)

### What Is NOT Sent
- API key or app secret (used for initial auth only)
- Plain text account number
- Any personal information beyond order details

### Local Storage
- Preview responses saved to `./trade_orders/` directory
- Directory is in `.gitignore` (not committed to git)
- Files contain order details and Schwab's response
- No sensitive credentials in files

## Limitations

### What Preview Does NOT Do
❌ Place actual trades  
❌ Reserve capital or positions  
❌ Guarantee execution at preview price  
❌ Lock in commission rates  
❌ Create working orders  

### Important Notes
⚠️ Preview is a **simulation** of what would happen  
⚠️ Actual execution may differ if market moves  
⚠️ Commission and fees are estimates  
⚠️ Buying power can change between preview and execution  
⚠️ Preview does not check for duplicate orders  

## Next Steps

### After Successful Preview
1. **Review all details carefully**
   - Check commission is acceptable
   - Verify buying power is sufficient
   - Read any warnings from Schwab
   - Confirm order parameters are correct

2. **Export to JSON** (optional)
   - Use "Generate Order File" for offline record
   - Review order structure and metadata

3. **Future: Place Order** (not yet implemented)
   - Once preview testing is complete
   - Actual order submission will require user confirmation
   - Will use preview response to show final details

### Development Roadmap
- ✅ Phase 1: Dry-run export to JSON
- ✅ Phase 2: Account number retrieval  
- ✅ Phase 3: Order preview with Schwab API (Current)
- ⏭️ Phase 4: Live order placement (Future)

## Troubleshooting

### "Schwab client not available"
**Solution**: Ensure Schwab provider is active
```bash
export OPTIONS_PROVIDER=schwab
export SCHWAB_API_KEY=your_key
export SCHWAB_APP_SECRET=your_secret
```

### "Account ID required"
**Solution**: Retrieve account first (Step 1)
```bash
# In UI: Click "Retrieve Account Numbers"
# Then set environment variable:
export SCHWAB_ACCOUNT_ID=your_encrypted_hash
```

### "Authentication failed"
**Solution**: Token may be expired
```bash
# Delete token file to force re-authentication
rm schwab_token.json
# Restart app and re-authenticate
```

### "Order validation failed"
**Solution**: Check order parameters
- Verify symbol exists and is option-eligible
- Ensure strike price is valid
- Check quantity is positive integer
- Confirm limit price is reasonable
- Verify expiration date is valid

## Example Preview Response

```json
{
  "status": "preview_success",
  "preview": {
    "orderType": "LIMIT",
    "session": "NORMAL",
    "duration": "DAY",
    "orderStrategyType": "SINGLE",
    "commission": 0.65,
    "estimatedTotalAmount": 125.00,
    "buyingPowerEffect": -2500.00,
    "marginRequirement": 2500.00,
    "orderLegCollection": [
      {
        "orderLegType": "OPTION",
        "instruction": "SELL_TO_OPEN",
        "quantity": 1,
        "instrument": {
          "symbol": "TGT_011725P150",
          "assetType": "OPTION"
        }
      }
    ],
    "warnings": []
  },
  "filepath": "./trade_orders/order_preview_20250129_214500.json",
  "message": "Order preview saved to ./trade_orders/order_preview_20250129_214500.json"
}
```

## Support

For issues or questions:
1. Check error details in expandable section
2. Review saved preview files in `./trade_orders/`
3. Verify Schwab credentials and token validity
4. Consult Schwab API documentation
5. Test with smaller quantities first

## Disclaimer

⚠️ **IMPORTANT**: This preview feature is for testing purposes only. Always review:
- Order details carefully before actual execution
- Your risk tolerance and account size
- Market conditions and volatility
- Schwab's terms of service and commission schedule

Trading options involves risk of loss. This software is provided as-is without warranty. Use at your own risk.
