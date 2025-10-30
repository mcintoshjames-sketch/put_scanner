# Credit Spreads Trading Guide

## Table of Contents
1. [Overview](#overview)
2. [Bull Put Spreads](#bull-put-spreads)
3. [Bear Call Spreads](#bear-call-spreads)
4. [When to Use Each Strategy](#when-to-use-each-strategy)
5. [Risk/Reward Profiles](#riskreward-profiles)
6. [Capital Efficiency](#capital-efficiency)
7. [Scanner Usage](#scanner-usage)
8. [Trade Management](#trade-management)
9. [Exit Strategies](#exit-strategies)
10. [Common Mistakes](#common-mistakes)
11. [Best Practices](#best-practices)

---

## Overview

Credit spreads are **defined-risk** options strategies that allow you to profit from directional or neutral market views while limiting your maximum loss. You collect a premium (credit) when opening the trade and keep it if the stock stays within a favorable range.

### Key Characteristics:
- ✅ **Defined Risk**: Maximum loss is known upfront
- ✅ **High Probability**: Can be structured with 60-80%+ probability of profit
- ✅ **Capital Efficient**: Requires less capital than naked options
- ✅ **Time Decay Friend**: Benefits from theta decay
- ⚠️ **Limited Profit**: Maximum gain is the credit received

---

## Bull Put Spreads

### What is it?
A **Bull Put Spread** is a credit spread used when you have a **bullish to neutral** view on a stock. You sell a put option at a higher strike and buy a put option at a lower strike.

### Structure:
```
Current Price: $580

Sell: 575 Put @ $5.00  ← Higher strike (short)
Buy:  570 Put @ $3.50  ← Lower strike (long protective)
─────────────────────────────
Net Credit: $1.50 per share ($150 per contract)
Spread Width: $5.00
Max Loss: $3.50 ($350 per contract)
Breakeven: $573.50
```

### When to Use:
- ✅ Bullish market outlook
- ✅ Expect stock to stay above the short strike
- ✅ Want to collect premium with defined risk
- ✅ High implied volatility (better premiums)

### Profit/Loss Zones:
| Stock Price at Expiration | Result |
|---------------------------|--------|
| Above $575 (short strike) | **Max Profit**: Keep full $150 credit |
| $573.50 - $575 | **Partial Profit**: Between $0 and $150 |
| $570 - $573.50 | **Partial Loss**: Between $0 and -$350 |
| Below $570 (long strike) | **Max Loss**: -$350 |

### Margin Requirement:
- **Capital Required**: $350 (spread width - credit)
- **Potential Return**: 43% ($150 profit / $350 capital)
- **Return if Annualized (30 days)**: 520%

---

## Bear Call Spreads

### What is it?
A **Bear Call Spread** is a credit spread used when you have a **bearish to neutral** view on a stock. You sell a call option at a lower strike and buy a call option at a higher strike.

### Structure:
```
Current Price: $580

Sell: 590 Call @ $2.50  ← Lower strike (short)
Buy:  595 Call @ $1.00  ← Higher strike (long protective)
─────────────────────────────
Net Credit: $1.50 per share ($150 per contract)
Spread Width: $5.00
Max Loss: $3.50 ($350 per contract)
Breakeven: $591.50
```

### When to Use:
- ✅ Bearish market outlook
- ✅ Expect stock to stay below the short strike
- ✅ Want to collect premium with defined risk
- ✅ High implied volatility (better premiums)

### Profit/Loss Zones:
| Stock Price at Expiration | Result |
|---------------------------|--------|
| Below $590 (short strike) | **Max Profit**: Keep full $150 credit |
| $590 - $591.50 | **Partial Profit**: Between $0 and $150 |
| $591.50 - $595 | **Partial Loss**: Between $0 and -$350 |
| Above $595 (long strike) | **Max Loss**: -$350 |

### Margin Requirement:
- **Capital Required**: $350 (spread width - credit)
- **Potential Return**: 43% ($150 profit / $350 capital)
- **Return if Annualized (30 days)**: 520%

---

## When to Use Each Strategy

### Bull Put Spread (Bullish)
**Best Market Conditions:**
- Stock is in an uptrend
- Support level nearby
- After a pullback in a bull market
- High IV after negative news that seems overblown

**Example Scenarios:**
- SPY at $580, strong support at $570
- NVDA pulled back 5% but fundamentals strong
- Market sell-off but you expect recovery

### Bear Call Spread (Bearish)
**Best Market Conditions:**
- Stock is in a downtrend
- Resistance level nearby
- After a rally in a bear market
- High IV after positive news that seems overdone

**Example Scenarios:**
- Stock at $580, strong resistance at $590
- Stock has rallied 10% and looks overbought
- Market euphoria but you expect correction

---

## Risk/Reward Profiles

### Comparison Table

| Metric | Bull Put Spread | Bear Call Spread | Cash-Secured Put | Covered Call |
|--------|----------------|------------------|------------------|--------------|
| **Directional Bias** | Bullish/Neutral | Bearish/Neutral | Bullish | Neutral |
| **Max Profit** | Credit Received | Credit Received | Credit Received | Credit + Cap Gains |
| **Max Loss** | Spread Width - Credit | Spread Width - Credit | Strike Price | Unlimited Downside |
| **Capital Required** | Low (spread width) | Low (spread width) | High (strike × 100) | High (stock price × 100) |
| **Probability of Profit** | 60-80% (typical) | 60-80% (typical) | 60-80% (typical) | 50-70% (typical) |
| **Best For** | Defined risk bulls | Defined risk bears | Cash-heavy accounts | Stock owners |

### Real Example Comparison
**SPY @ $580, 30 Days to Expiration**

| Strategy | Capital | Max Profit | Max Loss | ROI | Annualized ROI |
|----------|---------|------------|----------|-----|----------------|
| Bull Put Spread (575/570) | $350 | $150 | $350 | 43% | 520% |
| Bear Call Spread (590/595) | $350 | $150 | $350 | 43% | 520% |
| Cash-Secured Put (570) | $57,000 | $350 | $56,650 | 0.6% | 7.3% |
| Covered Call (590) | $58,000 | $1,350 | $56,650 | 2.3% | 28% |

**Key Insight**: Credit spreads offer similar profit potential with **99% less capital** than cash-secured puts!

---

## Capital Efficiency

### Why Credit Spreads Are Capital Efficient

1. **Defined Risk**: Only tie up the maximum loss amount
2. **High ROI**: 40-50% returns in 30-45 days are common
3. **Scalability**: Can run multiple spreads with same capital as 1 CSP
4. **Flexibility**: Easy to adjust or roll positions

### Example Portfolio
**$10,000 Account**

**Option 1: Cash-Secured Puts**
- Sell 1x SPY 570 Put
- Capital tied up: $57,000 (need margin or limited to 0 contracts)
- Max profit: $350
- ROI: 3.5% (if you could trade it)

**Option 2: Bull Put Spreads**
- Sell 28x SPY 575/570 Put Spreads
- Capital tied up: $9,800 ($350 × 28)
- Max profit: $4,200 ($150 × 28)
- ROI: 43%

**Result**: Credit spreads allow you to trade **28 times larger position size** with **12 times higher ROI**!

---

## Scanner Usage

### Step 1: Select Strategy
1. Open **Strategy Lab** app
2. In sidebar, select:
   - **Bull Put Spread** (bullish view), OR
   - **Bear Call Spread** (bearish view)

### Step 2: Configure Parameters
```
Ticker: SPY (or any stock)
Days Limit: 30-45 (sweet spot for theta decay)
Min OI: 100 (ensure liquidity)
Max Spread: 5-10 (narrower = less risk, wider = more credit)
Min IVR: 20% (higher IV = better premiums)
Min PoP: 70% (adjust based on risk tolerance)
```

### Step 3: Run Scan
1. Click **"Runall Scans"**
2. Scanner will analyze option chains and find opportunities
3. Results appear in dedicated tab (Bull Put or Bear Call)

### Step 4: Analyze Results
Scanner shows:
- **Sell Strike**: The short option strike
- **Buy Strike**: The long (protective) option strike
- **Net Credit**: Premium you'll receive
- **Spread Width**: Distance between strikes
- **Max Profit**: Credit × 100
- **Max Loss**: (Spread Width - Credit) × 100
- **Breakeven**: Price where P&L = $0
- **PoP (Probability of Profit)**: Based on delta
- **IV (Implied Volatility)**: Higher = better premiums
- **Score**: Composite ranking (higher = better)

### Step 5: Select Trade
1. Click on a row to select it
2. Review in **Overview tab** for full analysis
3. Use **Monte Carlo tab** for risk simulation
4. Place order via **Trade Ticket** or **Schwab Orders** tab

---

## Trade Management

### Entry Guidelines

**1. Choose the Right Time:**
- ✅ High IV environment (IVR > 20%)
- ✅ 30-45 days to expiration (optimal theta decay)
- ✅ After pullback (bull put) or rally (bear call)
- ✅ Away from earnings (unless intentional vol play)

**2. Strike Selection:**
- **Conservative**: 70-80% PoP (further OTM)
- **Moderate**: 65-75% PoP (balanced risk/reward)
- **Aggressive**: 60-70% PoP (higher premium, more risk)

**3. Position Sizing:**
- Never risk more than 2-5% of account per trade
- Example: $10,000 account, max $350 loss per trade
- This allows 1 trade per$350 of max loss

### During the Trade

**Monitor Daily:**
- Stock price relative to short strike
- Days to expiration (time decay working for you)
- IV changes (IV crush helps, IV expansion hurts)
- News events or earnings

**Red Flags:**
- Stock moving toward or through short strike
- Unusual volume or news
- Big move against you early in trade

**Green Lights:**
- Stock staying in profit zone
- Time passing (theta decay)
- IV dropping (vega benefit)
- Profit approaching 50-75% of max

---

## Exit Strategies

### Profit-Taking Exits

**50% Rule** (Recommended for most traders)
- When profit reaches 50% of max ($75 on $150 max)
- Close the spread for a $75 profit
- Frees up capital for next trade
- Reduces risk of reversal

**Example:**
- Opened: Sold for $1.50 credit
- Target: Close when spread costs ≤ $0.75
- Profit: $0.75 per share = $75 per contract

**75% Rule** (For aggressive profit-taking)
- When profit reaches 75% of max ($112.50 on $150 max)
- Close the spread for a $112.50 profit
- Very high win rate
- Requires patience

**Hold to Expiration** (For maximum profit)
- ✅ Only if stock is well away from short strike
- ⚠️ Risk of late assignment
- ⚠️ Gamma risk increases near expiration

### Loss Management Exits

**Stop-Loss at 2x Credit** (Recommended)
- If spread value reaches $3.00 (2× the $1.50 credit)
- Close for -$150 loss
- Prevents catastrophic losses
- Example: Opened at $1.50, close if it reaches $3.00

**Mechanical Stop at 21 DTE**
- If position is losing at 21 days
- Close and move on
- Avoids gamma risk

**Adjustment Strategies:**
1. **Roll Out**: Close current spread, open new spread further out in time
2. **Roll Down/Up**: Close and reopen at different strikes
3. **Convert**: Turn into iron condor or other spread

### Exit Priority Matrix

| Scenario | Action | Priority |
|----------|--------|----------|
| 50% profit reached | Close | ⭐⭐⭐ High |
| 75% profit reached | Close | ⭐⭐⭐ Very High |
| Loss = 2× credit | Close | ⭐⭐⭐ Critical |
| 7-0 DTE, in profit | Close or Let expire | ⭐⭐ Medium |
| 7-0 DTE, at risk | Close immediately | ⭐⭐⭐ Critical |
| Stock through short strike | Evaluate: Close or Roll | ⭐⭐ High |

---

## Common Mistakes

### 1. ❌ Trading Too Close to Current Price
**Problem**: High probability of getting tested
**Solution**: Sell strikes with 70%+ PoP (further OTM)

### 2. ❌ Over-Leveraging
**Problem**: One bad trade wipes out account
**Solution**: Never risk more than 2-5% per trade

### 3. ❌ Ignoring the Greeks
**Problem**: Don't understand why position is losing
**Solution**: Learn delta (directional), theta (time), vega (volatility)

### 4. ❌ Holding Through Earnings
**Problem**: IV crush and gap risk
**Solution**: Close before earnings or use defined strategy

### 5. ❌ Not Taking Profits
**Problem**: Giving back gains waiting for last $25
**Solution**: Take 50-75% profit and move on

### 6. ❌ Trading Low Volume Options
**Problem**: Wide bid-ask spreads, hard to exit
**Solution**: Stick to high liquidity (SPY, QQQ, AAPL, etc.)

### 7. ❌ No Trading Plan
**Problem**: Emotional decisions in heat of moment
**Solution**: Write down entry, exit, and stop-loss BEFORE entering

### 8. ❌ Ignoring Assignment Risk
**Problem**: Unexpected stock position or capital requirement
**Solution**: Close or roll positions before expiration if tested

---

## Best Practices

### Pre-Trade Checklist
- [ ] High IV environment (IVR > 20%)?
- [ ] 30-45 days to expiration?
- [ ] Adequate liquidity (OI > 100)?
- [ ] Strike selection matches risk tolerance?
- [ ] Position size appropriate (2-5% risk)?
- [ ] Exit plan defined (profit target + stop loss)?
- [ ] No earnings in next 7 days (unless planned)?

### During Trade Checklist
- [ ] Monitor daily (price, IV, time decay)
- [ ] Hit 50% profit? Consider closing
- [ ] Hit 75% profit? Strongly consider closing
- [ ] Loss approaching 2× credit? Close now
- [ ] 7 DTE and tested? Close or roll
- [ ] Unexpected news? Reassess position

### Post-Trade Checklist
- [ ] Journal the trade (entry, exit, P&L, notes)
- [ ] What went right?
- [ ] What went wrong?
- [ ] What would you do differently?
- [ ] Update trading plan based on learnings

### Risk Management Rules
1. **Max 5% of account at risk across all trades**
2. **Max 2% risk per single trade**
3. **Stop loss at 2× credit received**
4. **Take profits at 50-75% of max**
5. **Close at 7 DTE if tested**

### Winning Mindset
- ✅ Focus on process, not profits
- ✅ Small consistent wins > home runs
- ✅ Protect capital first, profit second
- ✅ Learn from every trade
- ✅ Stay disciplined with rules

---

## Comparison: Credit Spreads vs Other Strategies

### Credit Spreads vs Cash-Secured Puts

| Aspect | Credit Spreads | Cash-Secured Puts |
|--------|---------------|-------------------|
| **Capital Required** | Low ($300-500 typical) | High ($5,000-50,000) |
| **ROI** | 40-50% in 30-45 days | 1-3% in 30-45 days |
| **Max Loss** | Defined (spread - credit) | Strike price (huge) |
| **Flexibility** | Very high (easy to adjust) | Low (big positions) |
| **Assignment Risk** | Low (both legs protect) | High (can be assigned) |
| **Best For** | Smaller accounts, defined risk | Large accounts, want shares |

### Credit Spreads vs Iron Condors

| Aspect | Credit Spreads | Iron Condors |
|--------|----------------|--------------|
| **Directional Bias** | Yes (bullish or bearish) | No (neutral) |
| **Profit Zone** | One side | Both sides |
| **Capital Required** | Lower (one spread) | Higher (two spreads) |
| **Complexity** | Simple (2 legs) | More complex (4 legs) |
| **Best For** | Directional views | Range-bound stocks |

---

## Advanced Tips

### 1. Stack Your Odds
- Trade in direction of trend
- Use support/resistance levels
- Wait for high IV
- Sell 30-45 DTE

### 2. Portfolio Diversification
Don't put all eggs in one basket:
- Mix of bull put and bear call spreads
- Different underlyings (SPY, QQQ, individual stocks)
- Different expirations (weekly, monthly)

### 3. Adjustments
When tested (stock moves against you):

**Option A: Close**
- Simple, clean exit
- Take loss and move on

**Option B: Roll Out**
- Close current spread
- Open new spread same strikes, later expiration
- Collect more credit, buy more time

**Option C: Roll Up/Down**
- Close current spread
- Open new spread at different strikes
- Reduce loss or improve breakeven

**Option D: Convert to Iron Condor**
- Add opposite spread (call spread to bull put, put spread to bear call)
- Now profitable if stock stays in range
- Increases capital requirement

### 4. Earnings Plays (Advanced)
- Can sell credit spreads before earnings
- High IV = bigger premiums
- ⚠️ Risk: big gap move against you
- Strategy: Sell further OTM (lower PoP, but safer)

### 5. Weekly Options
- Faster theta decay
- More frequent trading opportunities
- Higher risk (less time to be right)
- Best for experienced traders

---

## Quick Reference Card

### Bull Put Spread (Bullish)
```
Structure: Sell higher put, buy lower put
When: Bullish/neutral outlook
Max Profit: Credit received
Max Loss: Spread width - credit
Breakeven: Short strike - credit
Sweet Spot: Stock above short strike at expiration
```

### Bear Call Spread (Bearish)
```
Structure: Sell lower call, buy higher call
When: Bearish/neutral outlook
Max Profit: Credit received
Max Loss: Spread width - credit
Breakeven: Short strike + credit
Sweet Spot: Stock below short strike at expiration
```

### Key Numbers
- **Days to Expiration**: 30-45 (optimal)
- **Probability of Profit**: 70%+ (conservative)
- **Position Size**: 2-5% risk per trade
- **Profit Target**: 50-75% of max profit
- **Stop Loss**: 2× credit received
- **Min Open Interest**: 100+
- **Ideal IV Rank**: 20%+

---

## Resources

### Tools in Strategy Lab
1. **Scanner**: Find optimal credit spread opportunities
2. **Overview Tab**: Detailed trade analysis with structure summary
3. **Monte Carlo Tab**: Risk simulation (50,000 paths)
4. **Trade Ticket**: Generate orders with one click
5. **Schwab Orders**: Direct broker integration
6. **Exit Orders**: Plan your exits
7. **Stop-Loss Orders**: Set protective stops

### Further Learning
- Options as a Strategic Investment (McMillan)
- Trading Options Greeks (Passarelli)
- The Option Trader's Hedge Fund (Lowell)
- TastyTrade (free options education)
- OptionAlpha (strategy backtests)

### Practice Tips
1. **Paper Trade First**: Test strategies without risk
2. **Start Small**: 1-2 contracts maximum
3. **Keep a Journal**: Track every trade
4. **Review Monthly**: Analyze what works
5. **Stay Disciplined**: Follow your rules

---

## FAQ

**Q: How much capital do I need to trade credit spreads?**
A: Minimum $2,000-5,000 to allow proper diversification. You can start with 1-2 spreads at ~$350 each.

**Q: What's the best probability of profit to target?**
A: 70-75% is a good balance. Higher PoP = lower premium, lower risk. Lower PoP = higher premium, higher risk.

**Q: Should I hold to expiration?**
A: Usually no. Taking 50-75% profit early reduces risk and frees capital. Only hold to expiration if well out of danger.

**Q: What if I get assigned?**
A: Rare with spreads (both legs protect). If short leg assigned, long leg protects you. Contact broker immediately.

**Q: Can I lose more than my max loss?**
A: No! That's the beauty of defined-risk spreads. Max loss is locked in at entry.

**Q: Which is better: bull put or bear call?**
A: Neither - depends on your market view. Bull put = bullish, bear call = bearish.

**Q: Do credit spreads work in any market?**
A: Best in neutral to trending markets. Difficult in fast, volatile markets. Wait for high IV.

**Q: How many spreads should I have open?**
A: Start with 2-5. Experienced traders may run 10-20. Never risk more than 5% total account.

---

**Happy Trading! Remember: Consistency and discipline beat home runs every time. 📈**
