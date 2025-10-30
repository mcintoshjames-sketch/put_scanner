# Feature Summary: Profit-Taking Exit Orders

## 🎯 What Was Added

The Trade Execution tab now **automatically generates profit-taking exit orders** alongside entry orders, enabling true "set and forget" trading based on runbook profit targets.

## 📋 Quick Start

1. **Run a scan** and select a contract
2. **Click "📥 Generate Order Files"**
3. **Choose profit target** (25%, 50%, 75%, or 90%)
4. **Download both orders:**
   - Entry order: Opens position
   - Exit order: Closes at profit target with GTC duration
5. **Submit to Schwab:**
   - Submit entry order first
   - After fill, submit exit order immediately
   - Exit order stays active until filled or canceled

## 💡 Key Features

### Automatic Exit Price Calculation
- **CSP/CC**: Exit price = Entry premium × (1 - target%)
  - Example: $5.50 premium @ 50% target → Exit at $2.75
- **Iron Condor**: Exit debit = Entry credit × (1 - target%)
  - Example: $2.50 credit @ 50% target → Close for $1.25 debit
- **Collar**: Separate exits for call (BTC) and put (STC) legs

### GTC Duration (Good Till Canceled)
- Exit orders automatically use GTC for convenience
- Stays active up to 60 days (Schwab policy)
- No need to re-enter daily
- True "set it and forget it"

### Complete Strategy Support
- ✅ Cash-Secured Put (CSP) - Single leg BUY TO CLOSE
- ✅ Covered Call (CC) - Single leg BUY TO CLOSE
- ✅ Collar - Two separate close orders
- ✅ Iron Condor - 4-leg NET DEBIT closing order

### Metadata Tracking
Every exit order includes:
- Profit target percentage
- Entry premium and exit price
- Expected profit per contract
- Scanner data (for tracking performance)

## 📊 Profit Target Guidelines

| Target | Use When | Strategy Fit |
|--------|----------|--------------|
| **25%** | High IV, earnings trades, short DTE | Quick profits before volatility changes |
| **50%** | Standard approach, most conditions | Balanced risk/reward (recommended) |
| **75%** | Low IV, strong conviction, theta acceleration | Capture more of max profit |
| **90%** | Very strong conviction, scalping | Near-max profit (or accept assignment) |

## 🔄 Workflow

### Traditional Approach (Before)
1. Open position
2. Manually monitor
3. Calculate profit target
4. Remember to close
5. Place exit order manually

**Problem:** Requires discipline, easy to forget, emotion-driven

### "Set and Forget" Approach (Now)
1. Generate both entry + exit orders
2. Submit entry → wait for fill
3. Submit exit immediately (GTC)
4. Walk away
5. Order executes automatically at target

**Result:** Disciplined, consistent, aligned with runbooks

## 📁 Files Generated

### Entry Order
```
trade_orders/csp_SPY_20251030_123456.json
```
- Standard entry order (SELL TO OPEN)
- Ready for Schwab submission

### Exit Order
```
trade_orders/csp_exit_SPY_20251030_123457.json
```
- Profit-taking order (BUY TO CLOSE)
- Includes profit target metadata
- GTC duration for automation

Both downloadable via Streamlit interface.

## ✅ Validation

Comprehensive test suite (`test_exit_orders.py`):
- ✅ 6/6 tests passing
- ✅ CSP, CC, Iron Condor exit orders
- ✅ Profit calculations (25%, 50%, 75%, 90%)
- ✅ Option symbol formatting
- ✅ GTC duration
- ✅ Order export and metadata

## 🚀 Benefits

1. **Disciplined Profit-Taking**: Exit at predetermined targets, not emotion
2. **Aligned with Runbooks**: Follows 50-75% profit capture guidelines
3. **Time Savings**: No manual exit order creation
4. **Reduced Risk**: GTC orders execute automatically if target hit
5. **Better Performance**: Consistent exit strategy across all trades
6. **Peace of Mind**: Set it and forget it, let the market work for you

## 📖 Documentation

See **EXIT_ORDER_FEATURE.md** for:
- Detailed workflow examples
- Order logic by strategy
- GTC duration explanation
- Troubleshooting guide
- Advanced tips and techniques

## 🎓 Example: CSP Trade

**Scan Results:**
- SPY $550 PUT @ $5.50 premium
- 30 DTE, 10% OTM

**Generate Orders (50% target):**
- Entry: SELL TO OPEN 1 contract @ $5.50
- Exit: BUY TO CLOSE 1 contract @ $2.75 (GTC)

**Submit to Schwab:**
1. Entry fills → Collect $550 premium
2. Exit order sits on books (GTC)

**Day 15:** SPY @ $570, put mark drops to $2.60
- Exit order fills automatically at $2.75
- **Profit: $275 in 15 days** (50% ROI in 2 weeks!)

**No monitoring required** - order executed automatically 🎯

## 🔧 Technical Implementation

**New Methods:**
- `create_iron_condor_exit_order()` - 4-leg closing order
- Enhanced order metadata tracking
- Profit target slider in UI
- Dual file generation (entry + exit)

**Updated Files:**
- `strategy_lab.py`: Exit order generation UI
- `providers/schwab_trading.py`: Iron Condor exit method
- `test_exit_orders.py`: Comprehensive test suite
- `EXIT_ORDER_FEATURE.md`: Full documentation

## 🎉 Impact

**Before:** Manual, inconsistent, emotion-driven exits  
**After:** Automated, disciplined, runbook-aligned exits

This feature brings professional-grade trade management to retail traders. 🚀
