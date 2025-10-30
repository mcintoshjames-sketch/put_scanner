# Profit-Taking Exit Order Feature

## Overview
The Trade Execution tab now automatically generates **profit-taking exit orders** based on your runbook profit targets. This enables a true "set and forget" workflow where you can submit both entry and exit orders immediately after scanning.

## How It Works

### 1. **Select Your Trade**
- Choose strategy (CSP, CC, Collar, Iron Condor)
- Pick contract from scan results
- Set quantity and order parameters

### 2. **Set Profit Target**
When you click "📥 Generate Order Files", you'll see a slider to choose your profit capture percentage:
- **25%**: Conservative, quick profit-taking
- **50%**: Standard target (recommended by most runbooks)
- **75%**: Aggressive, capture most of max profit
- **90%**: Very aggressive, near-max profit

### 3. **Generate Both Orders**
The system creates:
- **Entry Order**: Opens your position (SELL TO OPEN)
- **Exit Order**: Automatically closes at profit target (BUY TO CLOSE)

Both orders are exported as JSON files ready for Schwab submission.

---

## Exit Order Logic by Strategy

### Cash-Secured Put (CSP)
**Entry:** SELL TO OPEN $550 PUT @ $5.50  
**Exit @ 50%:** BUY TO CLOSE when mark ≤ $2.75  
**Profit:** $275 per contract ($550 collateral = 50% ROI on this exit)

**Formula:** Exit Price = Entry Premium × (1 - Target%)

### Covered Call (CC)
**Entry:** SELL TO OPEN $575 CALL @ $3.20  
**Exit @ 75%:** BUY TO CLOSE when mark ≤ $0.80  
**Profit:** $240 per contract

**Formula:** Same as CSP

### Iron Condor (4-Leg)
**Entry:** NET CREDIT $2.50 (all 4 legs)  
**Exit @ 50%:** Close entire spread for NET DEBIT ≤ $1.25  
**Profit:** $125 per contract

**Exit closes all 4 legs:**
- SELL TO CLOSE: Long Put (540)
- BUY TO CLOSE: Short Put (545)
- BUY TO CLOSE: Short Call (575)
- SELL TO CLOSE: Long Call (580)

**Formula:** Exit Debit = Entry Credit × (1 - Target%)

### Collar (2-Leg)
**Entry:** SELL CALL $575 @ $3.00, BUY PUT $540 @ $1.50 (net $1.50 credit)  
**Exit:** Two separate orders
- BUY TO CLOSE: Call leg @ profit target
- SELL TO CLOSE: Put leg @ ~50% of cost

---

## Workflow: "Set and Forget"

### Step 1: Submit Entry Order
1. Download/copy entry order JSON
2. Submit via Schwab (web/mobile/thinkorswim)
3. **Wait for fill confirmation**

### Step 2: Submit Exit Order Immediately
1. Download/copy exit order JSON
2. Submit via Schwab with **GTC duration**
3. Order stays active until:
   - ✅ Filled at profit target
   - ❌ Manually canceled
   - ⏱️ Option expires

### Step 3: Monitor (Optional)
- Set calendar reminder at 7-10 DTE
- Check position occasionally
- Exit order will execute automatically if target hit

---

## GTC (Good Till Canceled) Duration

All exit orders default to **GTC** for maximum convenience:

**Benefits:**
- No need to re-enter order daily
- Automatically fills when market hits your target
- Survives overnight and weekends
- True "set it and forget it"

**Schwab Behavior:**
- Order stays active for up to 60 days (Schwab policy)
- You can cancel anytime via web/mobile
- Will auto-cancel if underlying expires

---

## Order Files Generated

### Entry Order
```
trade_orders/csp_SPY_20251030_123456.json
```
Contains:
- Order payload (ready for Schwab API)
- Strategy type and metadata
- Scanner data (IV, delta, ROI, etc.)
- Timestamp and account ID

### Exit Order
```
trade_orders/csp_exit_SPY_20251030_123457.json
```
Contains:
- Exit order payload (BUY TO CLOSE)
- Profit target percentage
- Entry premium and exit price
- Expected profit per contract
- Scanner data (for tracking)

Both files are saved to `./trade_orders/` directory.

---

## Safety Features

### Earnings Warning Integration
If earnings are within your warning window (default: 14 days), you'll see:
- ⚠️ Warning message before generating orders
- Earnings date in order metadata
- Reminder to consider IV crush risk

### Validation
All orders are validated before export:
- Required fields present
- Strikes and expirations valid
- Option symbols formatted correctly
- Quantities within reason

### Metadata Tracking
Every order includes:
- **Source**: `strategy_lab_[strategy]_scanner`
- **Scanner Data**: OTM%, ROI, IV, Greeks, OI, DTE
- **Profit Target**: Percentage and dollar amount
- **Entry/Exit Prices**: For reconciliation

---

## Example: CSP "Set and Forget"

### Scan Results
- **Ticker**: SPY
- **Strike**: $550
- **Premium**: $5.50
- **DTE**: 30 days
- **Strategy**: Cash-Secured Put

### Generate Orders (50% Profit Target)
```
✅ Entry Order:  SELL TO OPEN 1 SPY 2025-11-30 $550 PUT @ $5.50 LIMIT
✅ Exit Order:   BUY TO CLOSE 1 SPY 2025-11-30 $550 PUT @ $2.75 LIMIT GTC
```

### Submit to Schwab
1. **Entry**: Filled at $5.50 → Collected $550 premium
2. **Exit**: Submitted immediately with GTC
3. **Wait**: Order sits on Schwab's books waiting for $2.75

### Scenarios

**Scenario A: Price Stays OTM (Win)**
- Day 15: SPY @ $570, Put mark drops to $2.60
- Exit order fills automatically at $2.75
- **Profit**: $275 in 15 days (15% return in 2 weeks!)

**Scenario B: Price Moves Against You**
- Day 20: SPY @ $555, Put mark rises to $8.00
- Exit order doesn't fill (mark too high)
- You manually manage: roll or take assignment
- Exit order can be canceled anytime

**Scenario C: Price Rallies Hard (Big Win)**
- Day 5: SPY @ $580, Put mark drops to $1.50
- Exit order fills at $2.75 (limit price)
- **Profit**: $275 in 5 days (even better!)

---

## Advanced Tips

### Adjust Profit Targets by Strategy
- **CSP**: 50-75% is standard (time decay favors you)
- **CC**: 50% is common (protect shares from call away)
- **IC**: 50% is prudent (avoid letting winners turn to losers)
- **Collar**: 50-75% on call leg (protect downside remains)

### When to Use Different Targets

**25% Target:**
- High IV environments (lock in gains before IV crush)
- Earnings trades (get out quick)
- Short DTE (< 7 days)

**50% Target:**
- Standard approach (balances risk/reward)
- Most market conditions
- 21-45 DTE positions

**75% Target:**
- Low IV environments (capture more premium)
- Strong directional conviction
- When theta decay is accelerating (< 10 DTE)

**90% Target:**
- Very strong conviction
- Scalping strategies
- When assignment is desired (CSP on quality stocks)

### Multiple Exit Orders
You can manually create multiple exit orders at different levels:
- 50% @ $2.75 for 1 contract
- 75% @ $1.38 for 1 contract

This scales out of position for optimal P&L curve.

---

## Technical Details

### Option Symbol Format
Schwab uses OCC standard format:
```
[SYMBOL][YYMMDD][C/P][STRIKE*1000]
Example: SPY   251130P00550000
         ^^^   ^^^^^^ ^^^^^^^^^^^
         ticker expiry strike+type
```

### Order Types

**Entry Orders:**
- CSP/CC: `LIMIT` with `SELL_TO_OPEN`
- Collar: `NET_CREDIT` (2-leg combo)
- IC: `NET_CREDIT` (4-leg combo)

**Exit Orders:**
- CSP/CC: `LIMIT` with `BUY_TO_CLOSE`
- Collar: Two separate `LIMIT` orders (BTC call, STC put)
- IC: `NET_DEBIT` (4-leg combo closing order)

### Duration Options
- **DAY**: Expires end of trading day
- **GTC**: Good till canceled (up to 60 days)

Exit orders always default to **GTC** for convenience.

---

## Troubleshooting

### "Exit order not filling"
**Causes:**
- Bid/ask spread too wide (market moved)
- Volatility increased (option value up)
- Low liquidity (no counterparty at your price)

**Solutions:**
- Adjust limit price slightly (give up a few cents)
- Switch to market order for instant fill
- Cancel and re-enter at better price

### "Which file is which?"
**File naming:**
- `csp_SPY_[timestamp].json` = Entry order
- `csp_exit_SPY_[timestamp].json` = Exit order

Look for `_exit` in filename.

### "Can I preview exit orders in Schwab?"
Yes! The exit order JSON can be previewed via Schwab API just like entry orders.

### "What if I change my mind?"
Simply cancel the GTC exit order in Schwab and:
- Let position run longer
- Submit new exit order at different target
- Manage manually based on market conditions

---

## API Integration (Future)

Currently orders are exported to JSON files. Future enhancement will:
1. Preview both entry AND exit orders via Schwab API
2. Option to submit both orders together
3. Conditional orders (submit exit only after entry fills)

For now, manual submission gives you full control and review capability.

---

## Test Coverage

The feature includes comprehensive tests (`test_exit_orders.py`):

- ✅ CSP exit order generation
- ✅ CC exit order generation
- ✅ IC 4-leg exit order generation
- ✅ Profit target calculations (25%, 50%, 75%, 90%)
- ✅ Order export with metadata
- ✅ GTC duration validation
- ✅ Option symbol formatting
- ✅ JSON file structure

All 6/6 tests passing.

---

## Summary

**Before this feature:**
1. Scan → Generate entry order → Submit → Wait for fill
2. Manually calculate profit target
3. Manually create exit order later
4. Risk forgetting or miscalculating

**With this feature:**
1. Scan → Generate BOTH orders → Submit entry → Submit exit
2. Walk away and let GTC order capture profit automatically
3. True "set and forget" workflow
4. Consistent with runbook best practices

**Result:** More disciplined profit-taking, less manual work, better risk management. 🎯
