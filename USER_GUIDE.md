# Strategy Lab — Comprehensive User Guide

**Version:** 2.0  
**Last Updated:** October 27, 2025  
**Author:** Options Income Strategy Lab

---

## Table of Contents

1. [Overview](#overview)
2. [Getting Started](#getting-started)
3. [Financial Strategy Explained](#financial-strategy-explained)
7. [Troubleshooting](#troubleshooting)

---

## Overview

### What is Strategy Lab?
1. **Cash-Secured Puts (CSP)** - Generate income while waiting to buy stocks at a discount
2. **Covered Calls (CC)** - Generate income on stocks you already own

- **Conservative income traders** seeking 10-45 day positions
- **Theta harvesting enthusiasts** looking for the time-decay sweet spot (21-35 DTE)
- **Risk-aware investors** who want quantified probabilities and Greeks
- **Systematic traders** who prefer data-driven decision making

### Core Philosophy


1. **Risk Management First** - Never sacrifice safety for yield
2. **Time Decay Optimization** - Target the 21-35 DTE "sweet spot" where theta is highest relative to gamma
3. **Liquidity Matters** - Only trade options with sufficient open interest and tight bid-ask spreads

# Clone or download the repository
cd put_scanner

# Install dependencies
pip install streamlit pandas numpy yfinance polygon-api-client scipy

# Set your Polygon API key (optional, for enhanced data)
export POLYGON_API_KEY=your_api_key_here

# Run the app
streamlit run strategy_lab.py
```

### First Launch

1. The app will open in your browser at `http://localhost:8501`
2. You'll see the sidebar with **Global Settings**
3. Default parameters are optimized for 10-45 day positions
4. Start by using the **Pre-Screener** to find quality tickers

### Quick Start Workflow

```
1. Pre-Screener → Find quality tickers
2. CSP/CC/Collar Tab → Analyze specific strategy
3. Compare Tab → See all opportunities side-by-side
4. Overview Tab → Deep dive on selected position
5. Roll Analysis → Decide when to close vs. roll
```

---

## Financial Strategy Explained

### The Core Strategies

#### 1. Cash-Secured Put (CSP)

**What It Is:**
- You **sell (write) a put option** on a stock you'd be willing to own
- You collect **premium upfront**
- You must have **cash reserved** to buy 100 shares if assigned

**When to Use:**
- You're bullish or neutral on a stock
- You want to own the stock at a lower price (the strike)
- You want to generate income while waiting

**Example:**
```
Stock: AAPL trading at $180
Action: Sell 1 AAPL Nov 15 $170 PUT
Premium: $2.50 ($250)
Days: 21 DTE

Outcomes:
- Stock stays above $170 → Keep $250 premium (13.2% annualized return)
- Stock drops below $170 → Buy 100 shares at $170, effective cost $167.50
```

**Risk:**
- Maximum loss = Strike price - premium (if stock goes to $0)
- You're obligated to buy the stock if it drops below strike

**Profit Profile:**
- Maximum profit = Premium collected
- Breakeven = Strike - Premium
- Theta works FOR you (time decay earns money)

#### 2. Covered Call (CC)

**What It Is:**
- You **own 100 shares** of a stock
- You **sell a call option** against those shares
- You collect **premium upfront**
- You cap your upside at the strike price

**When to Use:**
- You own stock and think it will trade sideways or slightly up
- You want to generate extra income on holdings
- You're willing to sell at the strike price

**Example:**
```
Stock: MSFT trading at $380 (you own 100 shares)
Action: Sell 1 MSFT Nov 15 $390 CALL
Premium: $3.00 ($300)
Days: 21 DTE

Outcomes:
- Stock stays below $390 → Keep shares + $300 premium
- Stock goes above $390 → Sell shares at $390 + keep premium
  Total profit: ($390 - $380) + $3 = $13/share = $1,300
```

**Risk:**
- Opportunity cost: Stock could rally above strike
- Still lose money if stock drops significantly (but premium provides small cushion)

**Profit Profile:**
- Maximum profit = (Strike - Stock Price) + Premium
- Breakeven = Stock Price - Premium
- Theta works FOR you

#### 3. Collar

**What It Is:**
- You **own 100 shares** of a stock
- You **buy a protective put** (downside protection)
- You **sell a covered call** (finance the put)
- Creates a "collar" around your position

**When to Use:**
- You want to protect gains in a stock you own
- Earnings or volatile event approaching
- You want defined risk without paying for insurance

**Example:**
```
Stock: NVDA trading at $500 (you own 100 shares)
Action: 
  - Buy 1 NVDA Nov 15 $480 PUT (costs $5.00)
  - Sell 1 NVDA Nov 15 $520 CALL (collects $5.50)
Net Credit: $0.50 ($50)

Outcomes:
- Stock drops below $480 → Protected! Max loss = $20/share - $0.50 credit = $19.50
- Stock stays $480-$520 → Keep stock + $50 credit
- Stock goes above $520 → Sell at $520, profit = $20 + $0.50 = $20.50
```

**Risk:**
- Upside capped at call strike
- Still responsible for shares if assigned

**Profit Profile:**
- Maximum loss = Stock Price - Put Strike + Net Debit
- Maximum profit = Call Strike - Stock Price + Net Credit
- Theta mostly neutral (short call theta offsets long put theta)

---

### Key Concepts

#### Time Decay (Theta)

**What It Is:**
- Options lose value as expiration approaches
- This loss is called **theta** (measured in $/day)
- When you **sell** options, theta works FOR you

**The Sweet Spot:**
- **21-35 Days to Expiration (DTE)**
- Theta decay accelerates in this window
- Gamma risk still manageable
- Best risk/reward for income strategies

**Why Not Shorter?**
- <10 DTE: Gamma explodes (tiny moves = huge P&L swings)
- Too risky, hard to manage

**Why Not Longer?**
- >45 DTE: Theta too slow (you're "wasting time")
- Capital tied up for low daily returns

#### The Greeks

**Delta (Δ)**
- Rate of change in option price per $1 move in stock
- **Put delta:** -0.30 means option gains $0.30 if stock drops $1
- **Call delta:** +0.40 means option gains $0.40 if stock rises $1
- For income strategies, we target **low delta** (far OTM = safer)

**Gamma (Γ)**
- Rate of change of delta
- High gamma = delta changes rapidly as stock moves
- **Problem for income:** Position risk accelerates near expiration
- We want **low gamma** relative to theta

**Theta (Θ)**
- Daily time decay (usually negative for long options, positive for short)
- **CSP/CC:** Positive theta = you earn money every day
- Measured in dollars per day per contract

**Vega (ν)**
- Sensitivity to implied volatility (IV) changes
- **Short options:** Negative vega (you want IV to drop)
- High IV = collect more premium (but more risk)

#### Theta-to-Gamma Ratio

**Why It Matters:**
- **Theta/Gamma > 3.0:** Ultra-safe but tiny premium (inefficient)
- **Theta/Gamma 0.8-3.0:** Sweet spot (good income, manageable risk)
- **Theta/Gamma < 0.5:** Danger zone (gamma explosion risk)

**Interpretation:**
```
Theta = $5/day, Gamma = 0.03
Ratio = 5 / (100 × 0.03) = 1.67 ✅ Good!

Theta = $2/day, Gamma = 0.08
Ratio = 2 / (100 × 0.08) = 0.25 ❌ Too risky!
```

**Strategy Lab Optimization:**
- Scores positions with 0.8-3.0 ratio highest
- Penalizes extreme ratios (too risky or too conservative)

#### Cushion (Standard Deviations)

**What It Is:**
- Distance from current price to strike, measured in **standard deviations (σ)**
- Uses historical volatility to estimate likely price movement

**Example:**
```
Stock: $100
Strike: $90 (10% OTM)
30-day Historical Volatility: 20%

Expected 1σ move in 30 days = $100 × 0.20 × √(30/365) = $5.73
Cushion = ($100 - $90) / $5.73 = 1.75σ
```

**Interpretation:**
- **<0.5σ:** Very close to ITM, high risk
- **0.75-1.5σ:** Moderate cushion, sweet spot for income
- **>2.0σ:** Very safe, but premium will be small

**Default Settings:**
- Strategy Lab uses **0.75σ minimum** for short-term positions
- Allows higher risk for better yield in 21-35 DTE window

#### Probability of Expiring Worthless (POEW)

**What It Is:**
- Chance the option expires OTM (you keep full premium)
- Calculated using **delta** as probability proxy
- For CSP: POEW = 1 - |put delta|

**Example:**
```
AAPL $170 PUT, delta = -0.25
POEW = 1 - 0.25 = 0.75 = 75% chance of success
```

**Strategy:**
- **60-70% POEW:** Aggressive (higher yield, more risk)
- **70-80% POEW:** Balanced (sweet spot)
- **>80% POEW:** Conservative (safer, lower yield)

**Default:** Strategy Lab uses **60% minimum** for yield focus

---

## Tab-by-Tab Guide

### Tab 1: Cash-Secured Put (CSP)

**Purpose:** Find the best short put opportunities for income generation.

#### Workflow

1. **Enter Ticker(s)**
   - Single: `AAPL`
   - Multiple: `AAPL, MSFT, GOOGL`
   - Use Pre-Screener results

2. **Adjust Filters** (Sidebar)
   - **Min Days:** 10 (avoid ultra-short)
   - **Max Days:** 45 (avoid long duration)
   - **Min OTM%:** 8% (aggressiveness)
   - **Min ROI% (ann):** 20% (minimum acceptable return)
   - **Min Cushion (σ):** 0.75 (safety buffer)
   - **Min POEW:** 60% (probability of success)
   - **Min Open Interest:** 50 (liquidity)
   - **Max Spread%:** 10% (execution quality)

3. **Review Results**
   - Sorted by **Score** (composite of all factors)
   - Look for 21-35 DTE in green zone
   - Check Theta/Gamma ratio (0.8-3.0 ideal)

4. **Select a Row**
   - Click radio button to select
   - See detailed analysis in other tabs

#### Key Columns

- **Score:** Composite metric (35% ROI, 15% Cushion, 30% Theta/Gamma, 20% Liquidity)
- **OTM%:** How far below current price (higher = safer, lower yield)
- **ROI%_ann:** Annualized return on capital
- **CushionSigma:** Standard deviations of safety margin
- **POEW:** Probability of keeping full premium
- **Theta/Gamma:** Daily income vs. risk ratio
- **Spread%:** Bid-ask spread as % of mid (lower = better liquidity)

#### Best-Practice Fit

Visual indicators show if position meets quality standards:
- ✅ **Green:** Meets criterion
- ❌ **Red:** Fails criterion

**Criteria:**
1. Days in 21-45 range (sweet spot)
2. OTM% ≥ 8% (reasonable distance)
3. Theta/Gamma ≥ 0.8 (efficient income)
4. Cushion ≥ 0.75σ (adequate buffer)
5. POEW ≥ 60% (acceptable probability)
6. ROI ≥ 20% annualized (minimum yield)
7. Spread ≤ 10% (executable)

### Tab 2: Covered Call (CC)

**Purpose:** Generate income on stocks you own or plan to own.

#### Workflow

1. **Enter Ticker**
   - You must own (or plan to own) 100 shares

2. **Adjust Filters**
   - Similar to CSP, but focused on upside cap
   - **Min OTM%:** How much room for appreciation
   - Consider: Are you OK selling at this strike?

3. **Dividend Consideration**
   - Toggle "Include Dividend Yield" if stock pays dividends
   - Adds dividend to total return calculation

4. **Review & Select**
   - Balance premium vs. strike price
   - Don't get greedy—give stock room to breathe

#### Key Differences from CSP

- **Upside Cap:** You sell shares if called away
- **Dividend Risk:** Early assignment if dividend > time value
- **Stock Ownership:** Must own or buy 100 shares first

#### Strategy Tips

- **Neutral to slightly bullish:** Sell ATM or slightly OTM
- **Very bullish:** Sell further OTM (lower premium, more upside)
- **Defensive:** Sell ATM for maximum premium

### Tab 3: Collar

**Purpose:** Protect downside while financing with upside cap.

#### Workflow

1. **Enter Ticker**
   - Must own 100 shares

2. **Set Protection Level**
   - **Put Strike:** How much downside protection? (usually 5-10% below)
   - **Call Strike:** How much upside to give up? (usually 5-10% above)

3. **Analyze Net Cost**
   - **Zero-cost collar:** Put cost = Call premium
   - **Net credit collar:** Call premium > Put cost (preferred)
   - **Net debit collar:** Put cost > Call premium (paying for insurance)

4. **Evaluate Risk/Reward**
   - Max loss defined by put strike
   - Max gain defined by call strike
   - Review whether protection is worth the cap

#### Use Cases

- **Pre-Earnings:** Protect against surprise gap
- **Portfolio Protection:** Hedge during market uncertainty
- **Lock In Gains:** Protect profits on winning positions

### Tab 4: Compare Strategies

**Purpose:** See all three strategies side-by-side for the same ticker.

#### What It Shows

- CSP, CC, and Collar opportunities simultaneously
- Compare risk/reward profiles
- Identify best strategy for current market condition

#### Decision Framework

```
Bullish → CSP (collect premium, willing to own)
Neutral → CC (own stock, milk premium)
Uncertain → Collar (protect + generate income)
```

### Tab 5: Risk (Monte Carlo Simulation)

**Purpose:** Understand probability of loss using simulations.

#### How It Works

1. Simulates **50,000 price paths** using Geometric Brownian Motion
2. Uses implied volatility (or 20% default)
3. Calculates % of paths where you lose money

#### Interpreting Results

- **P(Loss) < 20%:** Conservative position
- **P(Loss) 20-35%:** Moderate risk (acceptable for income)
- **P(Loss) > 40%:** Aggressive, consider reducing size

**Chart:**
- Distribution of simulated outcomes at expiration
- Red line = Strike price (your decision point)

**Important:** This is a **simulation**, not a guarantee. Markets don't follow perfect GBM.

### Tab 6: Playbook (Trade Checklist)

**Purpose:** Pre-trade and post-trade checklists to avoid mistakes.

#### Pre-Trade Checklist

Before entering any trade, verify:

1. ✅ **Position fits account size** (don't over-allocate)
2. ✅ **Earnings date checked** (avoid surprise gaps)
3. ✅ **Greeks reviewed** (theta/gamma ratio acceptable)
4. ✅ **Liquidity confirmed** (tight spread, OI > 50)
5. ✅ **Max loss calculated** (assignment price clear)
6. ✅ **Exit plan defined** (profit target and stop loss)
7. ✅ **Margin/cash verified** (CSP requires full cash, CC requires shares)

#### Post-Trade Checklist

After entering:

1. ✅ **Order filled** (check execution price vs. limit)
2. ✅ **Position logged** (track entry details)
3. ✅ **Alerts set** (technical levels, profit targets)
4. ✅ **Calendar reminder** (check position at 50% profit, 7 DTE)

### Tab 7: Plan & Runbook

**Purpose:** Structured approach to position management.

#### Position Management Rules

**Entry:**
- Only trade 21-45 DTE (sweet spot)
- Max 5% of portfolio per position
- Only tickers with adequate liquidity

**Monitoring:**
- Check daily if <14 DTE
- Check weekly if >14 DTE
- React to earnings announcements immediately

**Exit Scenarios:**

1. **Normal Close (50-75% profit captured)**
   ```
   Entry: Sold for $2.50
   Current: Trading at $0.75
   Profit: ($2.50 - $0.75) / $2.50 = 70% ✅ Close
   ```

2. **Early Assignment (ITM)**
   - CSP: Stock drops below strike → Buy 100 shares
   - CC: Stock rises above strike → Sell 100 shares
   - Accept assignment if within strategy

3. **Roll Forward (extend duration)**
   - Current DTE < 10 and want to continue
   - Buy back current, sell next cycle
   - Must collect net credit

4. **Stop Loss (emergency exit)**
   - Stock moves against you dramatically
   - Premium doubles (100% loss on paper)
   - Consider closing or rolling to reduce loss

#### The 21-Day Rule

**Why 21-35 DTE is optimal:**

| DTE Range | Theta/Day | Gamma Risk | Verdict |
|-----------|-----------|------------|---------|
| 7-10      | High      | Very High  | ❌ Too risky |
| 21-35     | High      | Moderate   | ✅ Sweet spot |
| 45-60     | Moderate  | Low        | ⚠️ Inefficient |
| 60+       | Low       | Very Low   | ❌ Wasting time |

**Strategy:** Enter at 30-45 DTE, close at 50% profit or 14 DTE (whichever comes first).

### Tab 8: Stress Test

**Purpose:** See how position performs under extreme scenarios.

#### Scenarios Tested

1. **+5% Rally:** Stock jumps 5%
2. **-5% Drop:** Stock falls 5%
3. **+10% Rally:** Stock jumps 10%
4. **-10% Drop:** Stock falls 10%
5. **IV +50%:** Implied volatility spikes (fear)
6. **IV -50%:** Implied volatility collapses (calm)

#### Understanding Results

**CSP Example:**
```
Current P&L: +$150
After -10% drop: -$850
Conclusion: Can you handle $850 loss? If not, position too large.
```

**Use This To:**
- Size positions appropriately
- Understand tail risk
- Plan defensive actions

### Tab 9: Overview (Deep Dive)

**Purpose:** Complete analysis of selected position.

#### What It Shows

**Position Details:**
- All contract specifications
- Current Greeks
- Profit/loss scenarios

**Key Metrics:**
- Max profit, max loss, breakeven
- Theta/Gamma ratio
- Time value decay rate

**Profit Capture Targets:**
- **Exit: 50% profit = close when mark ≤ $X**
  - Early exit, high win rate
- **Exit: 75% profit = close when mark ≤ $Y**
  - Balanced, good capital efficiency

**Strategy:**
- Set price alerts at these levels
- Close when hit for consistent wins

**Best-Practice Summary:**
- Visual table showing all quality checks
- Quickly see if position meets standards

**Risk Insights:**
- Probability of loss (Monte Carlo)
- Standard deviation analysis
- Margin/cash requirement

### Tab 10: Roll Analysis

**Purpose:** Decide whether to close or roll expiring positions.

#### When to Use

- Position approaching expiration (< 14 DTE)
- Captured 50%+ profit but want to continue
- Want to extend duration vs. close & redeploy

#### Workflow

1. **Select Current Position**
   - Must have position selected from CSP/CC tab

2. **Set Roll Parameters**
   - **Target Min DTE:** Usually current DTE + 14
   - **Target Max DTE:** Usually current DTE + 30
   - **Same Strike:** Check for lower risk, uncheck for flexibility

3. **Click "Find Roll Candidates"**
   - App scans for next-cycle opportunities
   - Shows extended DTE options

4. **Review Comparison**
   - **Option 1: Close Now**
     - Profit realized immediately
     - Capital freed for redeployment
   - **Option 2: Roll Forward**
     - Additional credit collected
     - Time extension (stay in position)

5. **Decision Framework**

**Roll If:**
- Roll credit > $50 AND
- Extended DTE keeps you in 21-45 sweet spot AND
- Theta/Gamma stays > 0.8

**Close If:**
- Profit captured > 75% OR
- Current DTE < 10 days OR
- Roll credit < $30

**Consider Strike Adjustment:**
- Rolling UP (CSP): Less risk, less premium
- Rolling DOWN (CC): Less risk, less premium
- Rolling same strike: Maintain risk/reward

#### Example

```
Current Position:
AAPL $170 PUT, 7 DTE, Entry $2.50, Current $0.60
Profit Captured: 76%

Roll Option:
AAPL $170 PUT, 28 DTE, Premium $3.20
Roll Credit: $3.20 - $0.60 = $2.60

Decision:
✅ Roll! Collect $260, extend 21 days, stay in sweet spot
```

---

## Understanding the Metrics

### Score Calculation

**Formula:**
```
Score = 0.35 × ROI_norm 
      + 0.15 × Cushion_norm 
      + 0.30 × ThetaGamma_norm 
      + 0.20 × Liquidity_norm
```

**Components:**

1. **ROI Weight (35%):**
   - Annualized return on capital
   - Normalized to 0-1 scale

2. **Cushion Weight (15%):**
   - Standard deviations of safety
   - Reduced weight for short-term focus

3. **Theta/Gamma Weight (30%):**
   - Income efficiency vs. risk
   - **Highest weight** for 10-45 DTE strategy

4. **Liquidity Weight (20%):**
   - Based on spread % and open interest
   - Critical for entries and exits

**Why These Weights?**

- **Short-term focus:** Theta/Gamma is king (30%)
- **Income goal:** ROI still primary (35%)
- **Risk management:** Cushion prevents disasters (15%)
- **Execution quality:** Liquidity enables the strategy (20%)

### Quality Thresholds

**Default Minimums (Optimized for 10-45 DTE):**

| Metric | Minimum | Rationale |
|--------|---------|-----------|
| Days | 10 | Avoid gamma risk |
| Max Days | 45 | Stay in theta sweet spot |
| OTM% | 8% | Reasonable distance |
| ROI% (ann) | 20% | Worth the capital |
| Cushion (σ) | 0.75 | Adequate buffer |
| POEW | 60% | Acceptable probability |
| Theta/Gamma | 0.8 | Efficient income |
| Open Interest | 50 | Minimum liquidity |
| Spread% | 10% | Executable price |

**Adjust Based On:**
- Risk tolerance (higher cushion = safer)
- Yield needs (lower OTM% = more premium)
- Market conditions (increase POEW in volatile markets)

---

## Best Practices

### Position Sizing

**The 5% Rule:**
- Never allocate more than 5% of portfolio to one position
- CSP: Capital at risk = Strike × 100
- CC: Capital at risk = Stock value (100 shares)

**Example:**
```
Portfolio: $100,000
Max per position: $5,000
CSP Strike: $50
Max positions: 1 contract ($5,000 capital)
```

**Diversification:**
- Max 3-5 positions simultaneously
- Different sectors
- Different strategies (CSP + CC + Collar)

### Entry Timing

**Best Times:**
- **Monday/Tuesday:** Full week for theta decay
- **After IV spike:** Sell when premium inflated
- **Post-earnings:** After uncertainty resolved

**Avoid:**
- **Day before earnings:** Massive IV crush risk
- **Friday:** Wastes weekend theta
- **During news events:** Unpredictable gaps

### Exit Discipline

**The 50-75 Rule:**

1. **50% Profit Target:**
   - Close when captured half of max profit
   - High win rate
   - Frees capital quickly

2. **75% Profit Target:**
   - Close when captured 3/4 of max profit
   - Balanced approach
   - Slightly longer hold time

3. **Never Hold to Expiration:**
   - Assignment risk increases
   - Gamma explodes
   - Close or roll at 7 DTE

**Example:**
```
Entry: Sold PUT for $2.00
50% Target: Buy back at $1.00 or less
75% Target: Buy back at $0.50 or less
Max Hold: 7 DTE regardless of P&L
```

### Rolling Strategy

**When to Roll:**
- Profitable position you want to extend
- Losing position that needs time to recover
- 7-14 DTE on current contract

**How to Roll:**
1. Buy back current contract
2. Sell next-cycle contract (21-35 DTE out)
3. Must collect net credit
4. Can adjust strike if needed

**Roll for Credit, Not Hope:**
```
❌ Bad Roll: Pay $1.00 to extend losing position
✅ Good Roll: Collect $0.50 to extend profitable position
```

### Risk Management

**Stop Loss Rules:**

1. **Premium Doubles:** Close if option value 2× entry
   ```
   Entry: Sold for $2.00
   Current: $4.00
   Action: Close (-$200 loss)
   ```

2. **Delta > 0.70:** Position deep ITM, assignment likely
   ```
   CSP Delta: -0.75 (stock well below strike)
   Action: Close or roll down
   ```

3. **Major News:** Earnings miss, regulatory action, etc.
   ```
   News: FDA rejects drug approval
   Action: Close all positions immediately
   ```

**Never Average Down:**
- Don't sell more puts on a falling stock
- Don't add to losing positions
- Accept the loss and move on

### Capital Efficiency

**The Pyramid:**

```
Tier 1 (40% of capital): Ultra-safe CSPs
  - OTM% > 15%
  - POEW > 75%
  - Blue chips only

Tier 2 (40% of capital): Moderate CSPs/CCs
  - OTM% 8-15%
  - POEW 60-75%
  - Quality stocks

Tier 3 (20% of capital): Aggressive plays
  - OTM% 5-8%
  - POEW 55-65%
  - Higher beta stocks
```

**Rebalance Weekly:**
- Move profits from Tier 3 to Tier 1
- Maintain pyramid structure
- Never invert (don't be top-heavy in risk)

---

## Troubleshooting

### Common Issues

#### "No results found"

**Causes:**
1. Filters too restrictive
2. Ticker has no options
3. API connection issue

**Solutions:**
- Lower Min ROI%, Min POEW thresholds
- Check if ticker is optionable
- Verify Polygon API key

#### "Spread% very high"

**Meaning:**
- Bid-ask spread > 10% of mid price
- Poor liquidity

**Action:**
- Avoid the position
- Slippage will eat your profits
- Find more liquid ticker

#### "Days < 21, risky"

**Meaning:**
- Approaching gamma explosion zone
- Time decay accelerates but risk spikes

**Action:**
- Only trade if very experienced
- Consider closing at 50% profit
- Or roll to next cycle

#### "Theta/Gamma < 0.8"

**Meaning:**
- Premium too low for the gamma risk
- Inefficient position

**Action:**
- Move strike closer to money
- Find different ticker
- Wait for IV to increase

### Data Issues

#### Stale Prices

**Symptom:** Prices not updating

**Fix:**
```bash
# Clear cache
rm -rf ~/.yfinance
# Restart app
```

#### Missing Greeks

**Symptom:** Theta/Gamma show as 0.0

**Cause:** Insufficient data for Black-Scholes

**Fix:**
- Check if IV available
- Ensure DTE > 0
- Verify risk-free rate set

#### Wrong Expiration Dates

**Symptom:** Only weeklies or monthlies showing

**Cause:** yfinance limitations

**Workaround:**
- Use multiple tickers
- Manually adjust date range
- Consider Polygon API for better data

---

## Advanced Topics

### Implied Volatility (IV) Strategies

**IV Rank:**
- Where current IV stands vs. 52-week range
- High IV Rank (>50): Good time to SELL options
- Low IV Rank (<25): Poor time to sell (wait)

**IV Crush:**
- Post-earnings IV collapse
- Sell BEFORE earnings for high premium
- Exit AFTER earnings before crush

**Example:**
```
Before Earnings: IV = 60%, PUT premium = $3.50
After Earnings: IV = 30%, PUT premium = $1.50
Strategy: Sell 1-2 weeks before, close day after
```

### Delta-Neutral Strategies

**Advanced Collar:**
- Adjust strikes to target zero delta
- Stock gains = Call loss, Stock loss = Put gain
- Pure theta harvesting with hedged directional risk

**Iron Condor (Not in App):**
- Sell OTM put + OTM call
- Buy further OTM put + call for protection
- Collect premium from both sides

### Portfolio Margin

**Standard Margin:**
- CSP requires 100% cash
- CC requires 100 shares owned

**Portfolio Margin:**
- Reduced requirements for offsetting positions
- Collar uses less margin (protected downside)
- Check with broker for eligibility

### Tax Considerations

**Short-Term vs. Long-Term:**
- Options income = short-term capital gains
- Taxed at ordinary income rate
- No special treatment

**Wash Sale Rule:**
- Selling stock at loss + selling puts = potential wash sale
- 30-day window before/after
- Consult tax professional

**Assignment Impact:**
- CSP assignment: Establishes stock cost basis
- CC assignment: Closes stock position
- Track all transactions for tax reporting

### Mechanical/Systematic Approach

**Weekly Routine:**

**Monday AM:**
1. Run Pre-Screener
2. Identify 10-15 candidates
3. Filter for earnings safety

**Monday PM:**
4. Analyze top 5 in depth
5. Enter 2-3 positions (best scores)

**Wednesday:**
6. Check open positions
7. Adjust if needed (roll, close)

**Friday:**
8. Take 50%+ profits
9. Review week's performance
10. Plan next week

**Monthly:**
- Review strategy performance
- Adjust filters if needed
- Rebalance portfolio tiers

---

## Appendix

### Glossary

**Assignment:** Being forced to fulfill option obligation (buy/sell shares)

**ATM (At The Money):** Strike price = current stock price

**Black-Scholes:** Mathematical model for option pricing

**Break-Even:** Stock price where position neither profits nor loses

**Credit:** Money received (selling options)

**Cushion:** Safety buffer in standard deviations

**Debit:** Money paid (buying options)

**Delta:** Sensitivity to $1 stock move

**DTE (Days to Expiration):** Calendar days until option expires

**Extrinsic Value:** Time value portion of option premium

**Gamma:** Rate of delta change

**GBM (Geometric Brownian Motion):** Stochastic process for price simulation

**Greeks:** Mathematical measures of option sensitivities

**ITM (In The Money):** Option with intrinsic value

**Intrinsic Value:** Profit if exercised immediately

**IV (Implied Volatility):** Market's expectation of future volatility

**Liquidity:** Ease of entering/exiting at fair price

**OI (Open Interest):** Number of outstanding contracts

**OTM (Out of The Money):** Strike beyond current price

**Premium:** Price of the option

**POEW:** Probability of Expiring Worthless (for sellers, this is good)

**Spread:** Difference between bid and ask price

**Theta:** Time decay per day

**Vega:** Sensitivity to IV change

### Formula Reference

**Call Delta:**
```
Δ_call = e^(-q×T) × N(d₁)
```

**Put Delta:**
```
Δ_put = -e^(-q×T) × N(-d₁)
```

**Gamma:**
```
Γ = [e^(-q×T) × φ(d₁)] / (S × σ × √T)
```

**Call Theta (per day):**
```
Θ_call = [-S×φ(d₁)×σ×e^(-q×T) / (2×√T) - r×K×e^(-r×T)×N(d₂) + q×S×e^(-q×T)×N(d₁)] / 365
```

**Put Theta (per day):**
```
Θ_put = [-S×φ(d₁)×σ×e^(-q×T) / (2×√T) + r×K×e^(-r×T)×N(-d₂) - q×S×e^(-q×T)×N(-d₁)] / 365
```

**Where:**
- S = Stock price
- K = Strike price
- r = Risk-free rate
- q = Dividend yield
- σ = Volatility
- T = Time to expiration (years)
- N(x) = Cumulative normal distribution
- φ(x) = Standard normal density

**Expected Move (68% CI):**
```
Expected Move = Stock Price × IV × √(DTE / 365)
```

### Resources

**Learning:**
- [tastytrade](https://www.tastytrade.com) - Options education
- [CBOE Options Institute](https://www.cboe.com/education) - Comprehensive courses
- [r/thetagang](https://reddit.com/r/thetagang) - Community for income traders

**Data:**
- [yfinance](https://pypi.org/project/yfinance/) - Free market data
- [Polygon.io](https://polygon.io) - Premium options data
- [CBOE](https://www.cboe.com) - VIX and volatility metrics

**Tools:**
- This Strategy Lab - Income-focused analysis
- [OptionStrat](https://optionstrat.com) - Visual strategy builder
- [OptionAlpha](https://optionalpha.com) - Trade automation

**Books:**
- *Option Volatility and Pricing* by Sheldon Natenberg
- *Trading Options Greeks* by Dan Passarelli
- *The Option Trader's Hedge Fund* by Mark Sebastian

---

## Support & Feedback

**Issues/Bugs:**
- Check troubleshooting section first
- Review GitHub issues
- Submit detailed bug report with screenshots

**Feature Requests:**
- Open GitHub issue with "Feature Request" tag
- Describe use case and expected behavior

**Questions:**
- Review this guide thoroughly first
- Check FAQ section
- Reach out via GitHub discussions

---

**Disclaimer:** This tool is for educational and analytical purposes only. Options trading involves substantial risk and is not suitable for all investors. Past performance does not guarantee future results. Always do your own due diligence and consult with a financial advisor before making investment decisions. The authors are not responsible for any trading losses.

---

*Strategy Lab — Making Theta Harvesting Systematic*

**Version:** 2.0 | **Updated:** October 27, 2025
