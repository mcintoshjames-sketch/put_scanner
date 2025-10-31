# Live Trading Quick Reference

## ⚠️ CRITICAL SAFETY RULE

**NEVER EXECUTE AN ORDER WITHOUT PREVIEWING IT FIRST**

All live orders MUST be previewed within 30 minutes before execution.

---

## Quick Start (5 Steps)

### 1️⃣ Enable Live Trading
```
Sidebar → ⚡ LIVE TRADING → Toggle ON
```

### 2️⃣ Run Scanner & Select Trade
```
Configure strategy → Run scan → Pick trade
```

### 3️⃣ Preview Order
```
Set parameters → Click "Preview Order"
Review carefully: symbol, strike, exp, quantity, price
```

### 4️⃣ Execute Order (within 30 minutes)
```
Click "Execute Order" → Confirm
Order submitted to Schwab API
```

### 5️⃣ Verify Execution
```
Check Schwab account for order status
Review execution record in trade_orders/
```

---

## Safety Features

✅ **Preview Required** - Cannot execute without preview  
✅ **30-Minute Window** - Preview expires after 30 minutes  
✅ **One-Time Use** - Preview cleared after execution  
✅ **No Bypass** - Cannot override safety checks  

---

## Common Errors

### ❌ "SAFETY CHECK FAILED: Order must be previewed"
**Fix**: Click "Preview Order" first, then execute within 30 minutes

### ⏰ "Preview expired"
**Fix**: Click "Preview Order" again (30 minutes passed)

### 🔌 "Schwab API client required"
**Fix**: Configure Schwab credentials and restart app

### ❓ "Order validation failed"
**Fix**: Check error message, adjust parameters, preview again

---

## Before You Trade

✓ Test in DRY RUN mode first  
✓ Start with 1 contract  
✓ Use limit orders (not market)  
✓ Double-check symbol & expiration  
✓ Verify option type (PUT vs CALL)  
✓ Confirm action (SELL vs BUY)  
✓ Check account balance  
✓ Have exit plan ready  

---

## Workflow Diagram

```
┌─────────────────┐
│ 1. Preview      │ ← Always start here
│    Order        │   Order registered (30 min validity)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 2. Review       │ ← Check everything carefully
│    Details      │   Symbol, strike, exp, qty, price
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 3. Execute      │ ← Must confirm within 30 min
│    Order        │   Submitted to Schwab API
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 4. Verify       │ ← Check Schwab account
│    Success      │   Confirm order and price
└─────────────────┘
```

---

## Emergency Contacts

**Schwab Trading Support**: 1-800-435-4000  
**Account Issues**: Contact via Schwab website  
**App Issues**: Check error logs in trade_orders/

---

## File Locations

**Previews**: `trade_orders/order_preview_*.json`  
**Executions**: `trade_orders/order_executed_*.json`  
**Errors**: `trade_orders/order_error_*.json`

---

## Dry Run vs Live Mode

| Feature | Dry Run | Live |
|---------|---------|------|
| Orders executed | ❌ No | ✅ Yes |
| Preview required | ❌ No | ✅ Yes |
| Schwab API used | ⚠️ Preview only | ✅ Full |
| Account affected | ❌ No | ✅ Yes |
| Good for testing | ✅ Yes | ❌ No |

---

## Best Practices

🎯 **Always preview first** - Never skip this step  
📏 **Start small** - 1 contract until comfortable  
💰 **Use limits** - Never use market orders  
⏱️ **Don't rush** - Review preview thoroughly  
✅ **Verify execution** - Check Schwab account immediately  
📊 **Track performance** - Review execution records  
🛑 **Know your exit** - Have profit and loss targets  

---

## Legal Reminder

⚠️ **You are responsible for all trades**

- Trading involves substantial risk
- No guarantee of profit
- Losses can exceed premium
- Software provided "as is"
- Consult financial advisor

---

## Key Configuration

**Environment Variables**:
```bash
SCHWAB_APP_KEY="your_app_key"
SCHWAB_APP_SECRET="your_app_secret"
SCHWAB_ACCOUNT_HASH="your_account_hash"
```

**Or Streamlit Secrets** (`.streamlit/secrets.toml`):
```toml
[schwab]
app_key = "your_app_key"
app_secret = "your_app_secret"
account_hash = "your_account_hash"
```

---

## Testing Checklist

Before enabling live trading:

- [ ] Tested strategies in DRY RUN mode
- [ ] Understand each strategy completely
- [ ] Know position sizing rules
- [ ] Have profit/loss targets defined
- [ ] Account approved for options trading
- [ ] Schwab API credentials configured
- [ ] Completed OAuth authentication
- [ ] Verified token is active
- [ ] Read complete user guide
- [ ] Comfortable with safety features

---

## Support Resources

📖 **Full Guide**: `LIVE_TRADING_GUIDE.md`  
🔧 **Technical Details**: `LIVE_TRADING_IMPLEMENTATION_SUMMARY.md`  
🧪 **Test Suite**: `test_live_trading_safety.py`  
🏠 **Main App**: `strategy_lab.py`  
⚙️ **Trading Module**: `providers/schwab_trading.py`

---

## Quick Commands

### Test Safety Mechanism
```bash
python test_live_trading_safety.py
```

### Run App
```bash
streamlit run strategy_lab.py
```

### Check Logs
```bash
ls -la trade_orders/order_*.json
```

### View Execution Record
```bash
cat trade_orders/order_executed_*.json | jq
```

---

## Remember

🔴 **LIVE TRADING = REAL MONEY**

Every order in live mode affects your real Schwab account.  
Preview first, review carefully, execute confidently.

Happy trading! 📈

---

**Version**: 1.0.0  
**Last Updated**: October 31, 2025  
**Status**: Production Ready ✅
