# Live Trading Guide

## ⚠️ Critical Safety Information

**READ THIS COMPLETELY BEFORE ENABLING LIVE TRADING**

Live trading enables **real order execution** on your Schwab brokerage account. Orders placed in live mode are **legally binding** and will affect your real account balance.

---

## Overview

The options scanner now supports **live order execution** through the Schwab Trading API. This feature allows you to execute the orders you've scanned and analyzed directly from the app.

### Safety Mechanism

A **mandatory preview-before-execution** safety mechanism protects you from accidental trades:

1. **Preview Required**: Every order MUST be previewed before execution
2. **Time-Limited**: Previews expire after 30 minutes
3. **One-Time Use**: Preview is cleared after execution (cannot reuse)
4. **No Bypass**: Cannot override or skip the safety check

---

## How It Works

### Workflow

```
┌─────────────┐
│ 1. Preview  │  Order is sent to Schwab API for preview
│   Order     │  Order hash computed and registered
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ 2. Review   │  User reviews order details carefully
│   Details   │  Check: prices, quantities, expiration
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ 3. Execute  │  User confirms within 30 minutes
│   Order     │  Order submitted to Schwab API
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ 4. Confirm  │  Order ID returned
│   Success   │  Execution record saved
└─────────────┘
```

### Safety Layers

The system includes **four layers of safety checks**:

1. **Preview Validation**: Order must have been previewed
   - Hash-based tracking ensures exact order match
   - Prevents accidental execution of modified orders

2. **Time Validation**: Preview must not be expired
   - 30-minute expiration window
   - Forces fresh review if too much time passes

3. **Client Validation**: Schwab API client must be configured
   - Requires valid authentication
   - Checks for active session

4. **Structure Validation**: Order must be properly formed
   - Validates all required fields
   - Checks for API compliance

---

## Setup Instructions

### Prerequisites

1. **Schwab API Credentials**
   - App Key (Client ID)
   - App Secret
   - Redirect URI (for OAuth)

2. **Account Information**
   - Schwab account number
   - Account must be enabled for options trading

### Configuration

#### Option 1: Environment Variables

```bash
export SCHWAB_APP_KEY="your_app_key"
export SCHWAB_APP_SECRET="your_app_secret"
export SCHWAB_REDIRECT_URI="https://127.0.0.1:8182"
export SCHWAB_ACCOUNT_HASH="your_account_hash"
```

#### Option 2: Streamlit Secrets

Create `.streamlit/secrets.toml`:

```toml
[schwab]
app_key = "your_app_key"
app_secret = "your_app_secret"
redirect_uri = "https://127.0.0.1:8182"
account_hash = "your_account_hash"
```

### Authentication

1. First run will trigger OAuth flow
2. Browser window opens for Schwab login
3. Approve app access
4. Token saved to `schwab_token.json`
5. Token auto-refreshes (valid for 7 days)

---

## Using Live Trading

### Step 1: Enable Live Trading

1. Open **sidebar** in the app
2. Expand **"⚡ LIVE TRADING"** section
3. Toggle **"Enable Live Trading"** to ON
4. You'll see: 🔴 **LIVE TRADING ACTIVE**

⚠️ **Warning**: This enables real order execution!

### Step 2: Run Your Scanner

1. Configure your strategy (CSP, CC, Credit Spread, etc.)
2. Run the scanner as usual
3. Review results and select a trade

### Step 3: Preview the Order

1. Configure order parameters (contracts, price, duration)
2. Click **"Preview Order"** button
3. Review the preview carefully:
   - Symbol and option details
   - Action (SELL_TO_OPEN, BUY_TO_CLOSE, etc.)
   - Quantity and price
   - Estimated costs/credits
   - Commission and fees

### Step 4: Execute the Order

1. If preview looks correct, click **"Execute Order"**
2. Order is submitted to Schwab API
3. Order ID is returned on success
4. Execution record saved to file

### Step 5: Verify Execution

1. Check your Schwab account for the order
2. Review execution price and status
3. Check saved execution record in `trade_orders/`

---

## Order Tracking

### Preview Records

Previews are saved to: `trade_orders/order_preview_{timestamp}.json`

```json
{
  "order_hash": "a8b5b1a72ed4e4d2",
  "preview_timestamp": "2025-10-31T14:30:00",
  "order": { ... },
  "preview_response": { ... }
}
```

### Execution Records

Executions are saved to: `trade_orders/order_executed_{timestamp}.json`

```json
{
  "order_id": "123456789",
  "execution_timestamp": "2025-10-31T14:35:00",
  "order": { ... },
  "response": { ... },
  "metadata": { ... }
}
```

### Error Records

Errors are saved to: `trade_orders/order_error_{timestamp}.json`

```json
{
  "error": "Order validation failed: ...",
  "timestamp": "2025-10-31T14:40:00",
  "order": { ... }
}
```

---

## Safety Features in Detail

### Order Hashing

Orders are tracked using a **SHA256 hash** of their contents:

**Hashed Fields**:
- Order type (LIMIT, MARKET, etc.)
- Duration (DAY, GTC, etc.)
- Session (NORMAL, etc.)
- Price and stop price
- All legs (action, symbol, quantity, strike, expiration)

**Why Hashing?**
- Ensures exact order match between preview and execution
- Prevents modified orders from being executed without re-preview
- Survives across method calls and serialization

### Preview Expiration

Previews expire after **30 minutes** to:
- Prevent execution with stale market data
- Force fresh review of current conditions
- Reduce risk of executing outdated orders

### Preview Clearing

After successful execution, the preview is **automatically cleared**:
- Prevents accidental duplicate execution
- Forces new preview for subsequent orders
- Maintains audit trail integrity

### Dry Run Bypass

The safety mechanism **only applies to live trading**:
- `dry_run=True`: No safety checks (always safe)
- `dry_run=False`: Full safety enforcement
- Easy testing without consequences

---

## Error Handling

### Common Errors

#### "SAFETY CHECK FAILED: Order must be previewed"

**Cause**: Attempting to execute without preview

**Solution**:
1. Click "Preview Order" first
2. Review the preview
3. Click "Execute Order" within 30 minutes

#### "Preview expired"

**Cause**: More than 30 minutes since preview

**Solution**:
1. Click "Preview Order" again
2. Review updated market conditions
3. Execute within 30 minutes

#### "Schwab API client required"

**Cause**: Live trading enabled but client not configured

**Solution**:
1. Configure Schwab API credentials
2. Restart the app
3. Complete OAuth authentication

#### "Order validation failed"

**Cause**: Order structure doesn't meet Schwab requirements

**Solution**:
1. Check error message for specific issue
2. Adjust order parameters
3. Preview and execute again

### Network Issues

If execution fails due to network error:

1. **Check Schwab account** - order may have been placed
2. **Check execution records** - may be saved despite error
3. **Do NOT retry** immediately - could result in duplicate order
4. **Verify order status** on Schwab website first

---

## Best Practices

### Before Enabling Live Trading

- [ ] Test thoroughly in DRY RUN mode
- [ ] Understand the strategy completely
- [ ] Know your risk tolerance
- [ ] Have sufficient account balance
- [ ] Verify account is enabled for options

### When Using Live Trading

- [ ] Start with small position sizes
- [ ] Always preview before executing
- [ ] Double-check symbol and expiration
- [ ] Verify option type (CALL vs PUT)
- [ ] Confirm action (SELL_TO_OPEN vs BUY_TO_CLOSE)
- [ ] Review limit prices against current market
- [ ] Check account balance before execution

### After Execution

- [ ] Verify order on Schwab account
- [ ] Review execution price
- [ ] Check for partial fills
- [ ] Monitor position throughout life
- [ ] Have exit plan ready

---

## Testing Recommendations

### Unit Testing

```python
# Test safety mechanism
from providers.schwab_trading import SchwabTrader

trader = SchwabTrader(dry_run=False, client=None)
order = trader.create_cash_secured_put_order(...)

# Should fail (no preview)
try:
    trader.submit_order(order)
except RuntimeError as e:
    assert "SAFETY CHECK FAILED" in str(e)

# Should succeed
trader._register_preview(order)
# (Would fail at client check, but safety check passes)
```

### Integration Testing

Use **Schwab sandbox/paper trading** if available:
1. Configure sandbox credentials
2. Enable live trading
3. Test full workflow with fake money
4. Verify orders appear in sandbox account

### Production Testing

When ready for real money:
1. Start with **smallest position** (1 contract)
2. Test with **low-risk trade** (far OTM put)
3. Use **limit orders** (never market orders)
4. Verify execution **immediately**
5. Scale up only after success

---

## Troubleshooting

### Token Expired

**Symptom**: "Authentication failed" or "Token invalid"

**Solution**:
```bash
# Delete old token
rm schwab_token.json

# Restart app - will re-authenticate
streamlit run strategy_lab.py
```

### Order Rejected by Schwab

**Possible Reasons**:
- Insufficient buying power
- Account not approved for options level
- Invalid option (doesn't exist)
- Order outside market hours
- Price too far from market

**Check**: Schwab account messages for specific reason

### Preview Not Registering

**Symptom**: "SAFETY CHECK FAILED" even after preview

**Possible Causes**:
- Order modified after preview (different hash)
- Preview expired (>30 minutes)
- Session state cleared (app restarted)

**Solution**: Preview again with current order

---

## Development Notes

### Code Structure

**Main Implementation**: `providers/schwab_trading.py`

**Key Methods**:
- `_compute_order_hash()`: Generate order hash
- `_register_preview()`: Register previewed order
- `_is_previewed()`: Check if order has valid preview
- `_clear_preview()`: Remove preview after execution
- `preview_order()`: Preview order via Schwab API
- `submit_order()`: Execute order with safety checks

**Safety Flow**:
```python
# Preview
order_hash = trader._register_preview(order)
# Cache: {hash: timestamp}

# Execute (within 30 min)
if trader._is_previewed(order):  # ✓ Valid
    result = schwab_client.place_order(acct_id, order)
    trader._clear_preview(order)  # Prevent reuse
else:
    raise RuntimeError("SAFETY CHECK FAILED")
```

### Configuration

**Preview Expiration**: Configurable via `_preview_expiry_minutes`

```python
# Default: 30 minutes
trader._preview_expiry_minutes = 30

# Adjust if needed (use with caution)
trader._preview_expiry_minutes = 60  # 1 hour
```

---

## FAQ

**Q: Can I bypass the preview requirement?**
A: No. The safety mechanism has no override. This is by design.

**Q: What happens if I modify the order after preview?**
A: The hash changes, so it's treated as a new order. Must preview again.

**Q: Can I preview multiple orders and execute later?**
A: Yes, but each must be executed within 30 minutes of its preview.

**Q: Does preview cost anything?**
A: No. Previews are free and don't affect your account.

**Q: What if I execute the same order twice?**
A: First execution clears the preview. Second attempt will be rejected.

**Q: Can I use live trading with paper money?**
A: If Schwab offers a sandbox/paper account, configure those credentials.

**Q: What's the minimum order size?**
A: Typically 1 contract. Check Schwab's requirements.

**Q: Are there API rate limits?**
A: Yes. Schwab has rate limits. The app doesn't batch-execute orders.

**Q: Can I cancel a live order after submission?**
A: Not from this app. Cancel via Schwab website or app.

**Q: Where can I see order history?**
A: Check `trade_orders/` directory for all preview/execution records.

---

## Support & Resources

### Schwab Resources
- **API Documentation**: [Schwab Developer Portal](https://developer.schwab.com)
- **Account Support**: 1-800-435-4000
- **Trading Support**: Contact via Schwab website

### App Support
- **Issues**: Check GitHub issues or create new
- **Questions**: Check documentation first
- **Bugs**: Report with detailed reproduction steps

### Emergency Contacts
- **Trading Issues**: Contact Schwab immediately
- **Account Issues**: Contact Schwab customer service
- **Technical Issues**: Check app logs and error files

---

## Legal Disclaimer

⚠️ **USE AT YOUR OWN RISK**

This software is provided "as is" without warranty of any kind. The authors are not responsible for:
- Financial losses from trades
- Bugs or errors in the software
- Market movements or volatility
- Order execution issues
- API failures or outages

**You are solely responsible for**:
- All trading decisions
- Position sizing and risk management
- Account monitoring and management
- Tax implications of trades
- Compliance with regulations

Options trading involves substantial risk and is not suitable for all investors. Consult a financial advisor before trading.

---

## Version History

### v1.0.0 (2025-10-31)
- ✅ Initial live trading implementation
- ✅ Preview-before-execution safety mechanism
- ✅ Order hashing and tracking
- ✅ 30-minute preview expiration
- ✅ Comprehensive error handling
- ✅ Audit trail (preview/execution/error files)
- ✅ UI toggle for live trading mode
- ✅ Integration with existing scanner

### Future Enhancements
- 🔄 Order status tracking
- 🔄 Partial fill handling
- 🔄 Position management
- 🔄 Portfolio view
- 🔄 P&L tracking
- 🔄 Batch order execution
- 🔄 Advanced order types (OCO, bracket)

---

**Remember**: Start small, test thoroughly, and never risk more than you can afford to lose.

Happy trading! 📈
