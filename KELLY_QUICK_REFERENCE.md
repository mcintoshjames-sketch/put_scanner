# Kelly Criterion Quick Reference Guide

## What is Kelly Criterion?

The Kelly Criterion is a mathematical formula for optimal position sizing that maximizes long-term growth while managing risk. It calculates what percentage of your capital to allocate to each trade based on:
- **Win probability** - How likely you are to profit
- **Win/loss ratio** - How much you win vs lose
- **Your edge** - The expected value of the trade

## Why Use Fractional Kelly?

**Full Kelly** (100%) maximizes growth but has high volatility and ~20% risk of ruin.  
**Fractional Kelly** (25-50%) reduces volatility and risk while still capturing most of the growth benefit.

**Recommended**: Use **Quarter Kelly (0.25)** for safety - it provides 75% of Full Kelly growth with only 25% of the volatility.

---

## How to Use in Strategy Lab

### Step 1: Enable Kelly Sizing
In the sidebar under **💰 Position Sizing**:
1. Check ☑️ **Enable Kelly Criterion**
2. Set **Kelly Multiplier** (default 0.25 = Quarter Kelly)
3. Enter your **Portfolio Capital** (e.g., $50,000)

### Step 2: Run Your Scan
Run any strategy scan (CSP, CC, Iron Condor, etc.)

### Step 3: Review Kelly Columns
Look for the new columns in scan results:
- **Kelly%** - Recommended % of capital for this trade
- **KellySize** - Dollar amount to allocate

### Step 4: Interpret Results

**Example CSP Result:**
```
Ticker: AAPL
Premium: $150
Collateral: $17,000
Kelly%: 2.5%
KellySize: $1,250
```

**What this means:**
- Allocate $1,250 (2.5% of your $50k capital)
- Since collateral is $17,000, you can't afford a full contract
- Either **skip** this trade or **split** with other traders
- This is Kelly telling you the position size is too large for your capital

**Better Example:**
```
Ticker: SPY
Premium: $50
Collateral: $5,000
Kelly%: 2.0%
KellySize: $1,000
```
- Allocate $1,000 (2% of capital)
- Collateral $5,000 per contract
- You can afford 0.2 contracts (not enough)
- Kelly says this is appropriately sized but capital too small

**Ideal Example:**
```
Ticker: TSLA
Premium: $100
Collateral: $1,000
Kelly%: 5.0%
KellySize: $2,500
```
- Allocate $2,500 (5% of capital)
- Collateral $1,000 per contract
- Trade **2 contracts** ($2,000 total collateral)
- Remaining $500 for next opportunity

---

## Kelly Multiplier Settings

### 0.10 (1/10th Kelly) - Ultra Conservative
- **Risk of Ruin**: <1%
- **Growth**: Slowest
- **Use When**: Very risk-averse, learning, small capital base
- **Volatility**: Very low

### 0.25 (Quarter Kelly) - **RECOMMENDED**
- **Risk of Ruin**: ~2%
- **Growth**: 75% of Full Kelly
- **Use When**: Most situations, long-term growth
- **Volatility**: Low

### 0.33 (Third Kelly) - Moderate
- **Risk of Ruin**: ~5%
- **Growth**: 85% of Full Kelly
- **Use When**: Confident in edge, moderate risk tolerance
- **Volatility**: Moderate

### 0.50 (Half Kelly) - Aggressive
- **Risk of Ruin**: ~10%
- **Growth**: 90% of Full Kelly
- **Use When**: High conviction, high risk tolerance, strong track record
- **Volatility**: High

### Never Use > 0.50 (Full Kelly or more)
- **Risk of Ruin**: >20%
- **Volatility**: Extreme
- **Result**: High probability of significant drawdowns

---

## Understanding Kelly Results

### High Kelly% (>5%)
**Meaning**: Strong edge, attractive opportunity  
**Caution**: Still respect position limits (20% max per trade)  
**Action**: Consider this opportunity seriously

### Medium Kelly% (2-5%)
**Meaning**: Good opportunity with reasonable edge  
**Action**: Standard allocation, good trade candidate

### Low Kelly% (0.5-2%)
**Meaning**: Marginal edge or small expected value  
**Action**: Consider but may not be worth trading costs

### Zero Kelly% (0%)
**Meaning**: Negative expectation or insufficient edge  
**Action**: **Do not trade** - expected value is negative

---

## Strategy-Specific Notes

### Cash-Secured Puts (CSP)
- **Base Win Rate**: 70%
- **Kelly Typical**: 2-4%
- **Watch For**: High collateral relative to capital
- **Tip**: Look for strikes with collateral <5% of capital

### Covered Calls (CC)
- **Base Win Rate**: 75% (highest)
- **Kelly Typical**: 1-3%
- **Watch For**: Stock already owned (capital efficiency)
- **Tip**: Kelly assumes you're buying stock + selling call

### Iron Condor
- **Base Win Rate**: 65%
- **Kelly Typical**: 2-6%
- **Advantage**: Lower capital requirement (defined risk)
- **Tip**: Can trade multiple contracts due to lower capital needs

### Bull Put / Bear Call Spreads
- **Base Win Rate**: 68%
- **Kelly Typical**: 3-7%
- **Advantage**: 5-10x more capital efficient than CSP/CC
- **Tip**: Kelly loves spreads - defined risk + good win rates

---

## Batch Allocation Strategy

Kelly includes a **50% total allocation cap** to prevent over-concentration.

**Example Portfolio:**
- Capital: $50,000
- Max Kelly Allocation: $25,000 (50%)

**Opportunities:**
1. AAPL CSP: Kelly $1,250 ✅
2. SPY IC: Kelly $800 ✅
3. MSFT CC: Kelly $900 ✅
4. TSLA Spread: Kelly $1,000 ✅
5. ... continue until $25,000 allocated

**Result**: Diversified across multiple uncorrelated positions while respecting Kelly sizing for each

---

## Common Mistakes to Avoid

### ❌ Mistake 1: Ignoring Kelly = 0
**Wrong**: "I'll trade it anyway, the ROI looks good"  
**Right**: Kelly = 0 means negative expectation - skip it

### ❌ Mistake 2: Using Full Kelly
**Wrong**: Kelly multiplier = 1.0  
**Right**: Use 0.25 (quarter Kelly) for safety

### ❌ Mistake 3: Exceeding Kelly Size
**Wrong**: Kelly says $1,000 but I'll do $5,000  
**Right**: Stick to Kelly - it's optimal for your capital and edge

### ❌ Mistake 4: Rounding Up Contracts
**Wrong**: Kelly says 0.7 contracts so I'll do 1  
**Right**: If you can't afford the next contract, skip the trade

### ❌ Mistake 5: Ignoring Total Allocation
**Wrong**: Keep adding positions until 100% allocated  
**Right**: Stop at 50% total Kelly allocation for diversification

---

## When Kelly Doesn't Apply

### Don't Use Kelly For:
1. **Hedging Positions** - Not about edge, about protection
2. **Adjustments** - Rolling/adjusting existing trades
3. **Covered Calls on Owned Stock** - Already have capital deployed
4. **Dividend Capture** - Different risk/reward profile
5. **Speculative Plays** - Win probabilities too uncertain

### Use Fixed Sizing Instead:
- **Hedges**: 1-2% of portfolio value per hedge
- **Adjustments**: Same size as original position
- **Covered Calls**: Based on stock position size
- **Speculative**: 0.5-1% of capital (if at all)

---

## Monitoring Kelly Performance

### Track These Metrics:
1. **Actual vs Recommended**: Are you following Kelly?
2. **Win Rate by Strategy**: Does reality match Kelly's assumptions?
3. **Avg Win/Loss**: Are your actual ratios close to Kelly's estimates?
4. **Total Allocation**: Are you respecting the 50% cap?

### Adjust Kelly If:
- **Win rate much lower**: Reduce Kelly multiplier (e.g., 0.25 → 0.10)
- **Win rate much higher**: Could increase slightly (e.g., 0.25 → 0.33)
- **High volatility**: Reduce Kelly multiplier for smoother equity curve
- **Low volatility**: Could increase slightly but stay ≤0.33

---

## Kelly + Other Risk Metrics

### Kelly + VaR
- Kelly sizes positions based on edge
- VaR measures portfolio tail risk
- **Rule**: If Kelly allocation pushes VaR >5%, reduce position sizes

### Kelly + Greeks
- Kelly determines size
- Delta shows directional risk
- **Rule**: If total portfolio delta >±50 from Kelly positions, hedge

### Kelly + Concentration
- Kelly sizes each opportunity
- Concentration measures sector/ticker clustering
- **Rule**: Reduce Kelly if >40% in one sector even if Kelly says allocate more

---

## Quick Decision Tree

```
Start: New trading opportunity
│
├─ Run Kelly calculation
│  │
│  ├─ Kelly = 0%? 
│  │  └─ YES → Skip trade (negative expectation)
│  │
│  └─ Kelly > 0%?
│     └─ YES → Continue
│
├─ Check Kelly% vs Capital
│  │
│  ├─ Can afford 1+ contracts?
│  │  └─ NO → Skip (position too large for capital)
│  │
│  └─ YES → Continue
│
├─ Check Total Allocation
│  │
│  ├─ Would exceed 50% total?
│  │  └─ YES → Reduce size or skip
│  │
│  └─ NO → Continue
│
├─ Check Risk Metrics
│  │
│  ├─ Would increase VaR >5%?
│  │  └─ YES → Reduce size
│  │
│  └─ NO → Continue
│
└─ Execute Trade
   └─ Trade Kelly-recommended size
```

---

## FAQs

### Q: Why is my Kelly% so low?
**A**: Either your edge is small, win probability is low, or the win/loss ratio is unfavorable. Review the opportunity metrics.

### Q: Can I override Kelly and trade larger?
**A**: You can, but you're increasing risk without increasing expected return. Not recommended.

### Q: Should I always follow Kelly exactly?
**A**: Fractional Kelly (0.25) builds in safety. Following it consistently optimizes long-term growth.

### Q: What if Kelly says 0.3 contracts?
**A**: You can't trade fractional contracts. Round down to 0 (skip the trade) unless you can split with others.

### Q: How do I know if Kelly's assumptions are correct?
**A**: Track actual win rates vs Kelly's estimates. Adjust Kelly multiplier if reality diverges significantly.

### Q: Can I use Kelly for other strategies (butterflies, calendars)?
**A**: Kelly works best for binary outcome strategies (profit or loss). Complex strategies need different analysis.

---

## Resources

### Mathematical Background
- **Original Paper**: Kelly, J.L. (1956) "A New Interpretation of Information Rate"
- **Practical Guide**: Thorp, Edward (2008) "The Kelly Capital Growth Investment Criterion"

### Further Reading
- Fortune's Formula by William Poundstone
- Options as a Strategic Investment by Lawrence McMillan (Chapter on Position Sizing)
- The Options Institute: Risk Management

### Tool Support
- **Dashboard**: Portfolio Summary tab shows Kelly allocations
- **Batch Analysis**: Coming in future version
- **Historical Tracking**: Coming in future version

---

## Support

For questions or issues with Kelly sizing:
1. Check PHASE_1_3_KELLY_SUMMARY.md for technical details
2. Review test_kelly.py for example calculations
3. Refer to RISK_ENHANCEMENT_PLAN.md for implementation roadmap

---

**Remember**: Kelly Criterion is a guide, not a rule. Use your judgment, respect your risk tolerance, and always verify calculations before trading.
