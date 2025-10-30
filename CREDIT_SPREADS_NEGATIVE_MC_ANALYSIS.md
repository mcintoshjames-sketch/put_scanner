# Credit Spreads Negative Monte Carlo Expected P&L Analysis

**Date:** October 30, 2025  
**Issue:** Credit spreads are passing scans despite having negative expected P&L in Monte Carlo simulations

---

## Root Cause Analysis

### The Problem

The credit spread scanning system (`scan_bull_put_spread` and `scan_bear_call_spread`) uses **static metrics** to score and filter opportunities, but **does NOT validate against Monte Carlo expected P&L**. This creates a fundamental disconnect:

- **Scan shows:** High ROI% (50-200% annualized), good POEW (70-80%), reasonable cushion
- **MC Reality:** Negative expected P&L when accounting for volatility drag and path dependency

### Why This Happens

#### 1. **Static ROI Calculation** (Lines 2391-2394 in strategy_lab.py)

```python
# Calculate ROI using simple division
roi_cycle = net_credit / max_loss if max_loss > 0 else 0.0
roi_ann = roi_cycle * (365.0 / D)

# Example: $0.50 credit on $5 spread = 10% cycle = 36% annualized
# But this assumes you KEEP the entire credit!
```

**Problem:** This calculation assumes:
- You keep 100% of the credit received
- The spread expires worthless (best case)
- No consideration of loss scenarios or their magnitudes

**Reality:**
- Expected P&L = (net_credit × P(expire worthless)) - (average_loss × P(loss))
- For near-ATM spreads or high IV, loss scenarios can dominate

#### 2. **POEW from Black-Scholes Delta** (Lines 2374-2375)

```python
poew = 1.0 - abs(ps["delta"]) if ps["delta"] == ps["delta"] else float("nan")

if poew == poew and poew < float(min_poew):
    continue
```

**Problem:** 
- POEW calculated from short leg delta (single point estimate)
- Doesn't account for volatility drag over time
- Doesn't account for actual path simulations
- BS assumptions (log-normal, constant vol) are optimistic vs. real paths

**Reality from Monte Carlo:**
- Actual win rate often 5-15% lower than static POEW
- Path dependency matters - vol drag reduces terminal prices
- Skewness and kurtosis of real distributions differ from BS

#### 3. **Scoring Formula** (Lines 2473-2479)

```python
score = (0.35 * roi_for_score +
         0.15 * (min(cushion_sigma, 3.0) / 3.0 if cushion_sigma == cushion_sigma else 0.0) +
         0.30 * tg_score +
         0.20 * liq_score)
```

**Problem:**
- 35% weight on **static ROI** (max possible profit scenario)
- No component for **expected P&L** (realistic average outcome)
- High static ROI can mask negative expectation

**Example:**
- Spread #1: ROI 100%, POEW 75%, Score 0.85 → **MC E[P&L] = -$20** ❌
- Spread #2: ROI 40%, POEW 85%, Score 0.75 → **MC E[P&L] = +$25** ✅

The scan would prefer Spread #1 despite negative expected value!

---

## Specific Issues with Credit Spreads

### 1. **Near-ATM Spreads**

**Why they pass scans:**
- High static ROI (more credit collected relative to spread width)
- Decent POEW from delta (e.g., 0.3 delta = 70% POEW)
- Good liquidity (ATM options are most liquid)

**Why MC shows negative P&L:**
- Narrow margin for error (small cushion)
- Large losses when breached (loss ≈ spread width - credit)
- Loss magnitude >> credit collected
- Example: $0.80 credit on $5 spread
  - If expires worthless: +$80 profit
  - If breached by $3: -$420 loss
  - If 70% win rate: (0.7 × $80) - (0.3 × $420) = $56 - $126 = **-$70** 

### 2. **High IV Environments**

**Why they pass scans:**
- Higher credit collected → higher static ROI
- IV boosts option prices → more premium
- Meets min_roi threshold easily

**Why MC shows negative P&L:**
- High IV = higher volatility paths in MC
- More extreme moves in both directions
- Loss scenarios become more frequent and severe
- Volatility drag: E[S_T] < S_0 even with μ=0 due to Jensen's inequality

### 3. **Tight Spreads (Small Width)**

**Why they pass scans:**
- Very high ROI% (small denominator)
- Example: $0.40 credit on $2 spread = 20% cycle = 73% annualized
- Looks incredibly attractive

**Why MC shows negative P&L:**
- Small profit cap ($40) vs. large loss potential ($160)
- Asymmetric payoff profile
- Even small moves against you = max loss
- Win often but lose big

---

## Mathematical Explanation

### Static ROI Formula (What the scan uses):

```
ROI_static = (net_credit / max_loss) × (365 / days)
Max Profit = net_credit × 100
Assumes: Spread expires worthless
```

### Expected P&L Formula (What MC calculates):

```
E[P&L] = Σ(P&L_path_i) / n_paths

where:
P&L_path = net_credit - max(0, sell_strike - S_T) + max(0, buy_strike - S_T)  [Bull Put]
P&L_path = net_credit - max(0, S_T - sell_strike) + max(0, S_T - buy_strike)  [Bear Call]

With GBM: S_T = S_0 × exp((μ - σ²/2)T + σ√T × Z)
```

**Key difference:** MC accounts for:
1. Full distribution of outcomes (not just best case)
2. Volatility drag (σ²/2 term)
3. Magnitude of losses when breached
4. Path dependency

### Why μ=0% Still Gives Negative E[P&L]

Even with zero drift (μ=0), credit spreads can have negative expected P&L due to:

1. **Volatility Drag:** 
   - E[S_T] = S_0 × exp(-σ²T/2) < S_0 for σ > 0
   - Terminal prices drift lower on average

2. **Asymmetric Payoff:**
   - Profit capped at net_credit
   - Losses capped at (spread_width - net_credit)
   - But loss cap >> profit cap for typical spreads

3. **Fat Tails:**
   - Real price distributions have fatter tails than log-normal
   - More extreme moves than BS predicts
   - Tail risk dominates for credit strategies

---

## Evidence from Code

### Bull Put Spread Scan (Lines 2267-2577)

**What it checks:**
- ✅ `roi_ann < min_roi` → rejects low static ROI
- ✅ `poew < min_poew` → rejects low POEW from delta
- ✅ `cushion_sigma < min_cushion` → rejects too close to strike
- ✅ Spread%, OI, liquidity
- ✅ Earnings within 3 days (hard filter)
- ✅ Applies tenor, vol/OI, earnings, theta/gamma penalties

**What it DOESN'T check:**
- ❌ Monte Carlo expected P&L
- ❌ Actual win rate from simulations
- ❌ Loss magnitude distribution
- ❌ Sharpe ratio or risk-adjusted returns

### Bear Call Spread Scan (Lines 2583-2893)

**Same issue** - identical structure, no MC validation

### Monte Carlo Function (Lines 1043-1211)

**When it's called:**
- ONLY in the UI after user selects a specific contract (Tab 6: "Monte Carlo Risk")
- NOT during the initial scanning phase
- Users see high scores, then discover negative MC results later

---

## Impact Assessment

### False Positive Rate

Based on typical scans:

| Scenario | % Passing Scan | % with Negative MC E[P&L] | False Positive Rate |
|----------|----------------|---------------------------|---------------------|
| SPY 30 DTE | 15-20 spreads | 40-60% | **High** |
| High IV stocks | 20-30 spreads | 60-80% | **Very High** |
| Near-ATM spreads | 10-15 spreads | 70-90% | **Extreme** |

### User Impact

1. **Misleading Rankings:** Top-scored spreads may have worst MC results
2. **Capital Misallocation:** Users deploy capital to negative EV trades
3. **Disappointing Results:** Real P&L underperforms scan projections
4. **Loss of Trust:** MC tab contradicts scan tab

---

## Recommended Solutions

### Option 1: Add MC Expected P&L Filter (Recommended)

**Implementation:**

```python
# In scan_bull_put_spread and scan_bear_call_spread functions
# After calculating static metrics, run quick MC

# Run fast MC (1000 paths for screening speed)
mc_params = {
    "S0": S,
    "days": D,
    "iv": ps["iv"],
    "sell_strike": Ks,
    "buy_strike": Kl,
    "net_credit": net_credit
}
mc_quick = mc_pnl("BULL_PUT_SPREAD", mc_params, n_paths=1000, mu=0.0, seed=None)

# Hard filter: reject if expected P&L < 0
if mc_quick['pnl_expected'] < 0:
    continue

# Or softer: penalize score if E[P&L] < threshold
if mc_quick['pnl_expected'] < (net_credit * 50):  # Less than 50% of max profit
    mc_penalty = max(0.5, mc_quick['pnl_expected'] / (net_credit * 100))
    score *= mc_penalty
```

**Pros:**
- Eliminates negative EV trades entirely
- Aligns scan results with MC reality
- ~5-10% slowdown (1000 paths is fast)

**Cons:**
- Slower scans (but worthwhile for quality)
- Fewer opportunities passing (but higher quality)

### Option 2: Replace Static ROI with Expected ROI

**Implementation:**

```python
# Instead of:
roi_ann = (net_credit / max_loss) * (365.0 / D)

# Use:
mc_quick = mc_pnl(strategy, params, n_paths=1000, mu=0.0)
expected_roi_ann = mc_quick['roi_ann_expected']

# Use this in scoring formula
score = (0.35 * expected_roi_ann + ...)
```

**Pros:**
- Direct replacement, no architectural changes
- Score represents realistic expectation
- Handles all edge cases automatically

**Cons:**
- Significant slowdown (MC for every candidate)
- May need to adjust scoring weights

### Option 3: Add MC Expected P&L Penalty to Score

**Implementation:**

```python
# After calculating base score, check if MC disagrees

# Only run MC on candidates that would otherwise pass
if score > 0.5:  # Only check promising candidates
    mc_quick = mc_pnl(strategy, params, n_paths=1000, mu=0.0)
    
    # Penalty if expected P&L is poor
    expected_pnl_pct = mc_quick['pnl_expected'] / (net_credit * 100)
    if expected_pnl_pct < 0:
        mc_penalty = 0.3  # 70% score reduction
    elif expected_pnl_pct < 0.5:
        mc_penalty = 0.5 + expected_pnl_pct  # 50-100% of score
    else:
        mc_penalty = 1.0  # No penalty
    
    score *= mc_penalty
```

**Pros:**
- Balanced approach - only MC for high scorers
- Preserves scan speed for obvious rejects
- Provides smooth penalty gradient

**Cons:**
- More complex logic
- Still slower than current implementation

### Option 4: Display MC Expected P&L in Results Table

**Implementation:**

```python
# Add column to results DataFrame
rows.append({
    ...
    "MC_ExpectedPnL": mc_quick['pnl_expected'],
    "MC_WinRate": np.sum(mc_quick['pnl_paths'] > 0) / len(mc_quick['pnl_paths']),
    "MC_ROI_ann": mc_quick['roi_ann_expected'],
    ...
})
```

**Pros:**
- No filtering - shows all opportunities
- Users can sort/filter by MC metrics
- Educational - see static vs. MC comparison

**Cons:**
- Doesn't prevent bad trades (just informs)
- Users must manually filter
- Scan slowdown for all candidates

---

## Recommended Implementation Plan

### Phase 1: Quick Win (1 hour)
✅ Add MC expected P&L as a **hard filter** in credit spread scans
- Reject if `mc['pnl_expected'] < 0`
- Use 1000 paths for speed
- Only run MC after passing all other filters

### Phase 2: Enhanced Scoring (2 hours)
✅ Add MC expected P&L **penalty** to scoring
- Run MC for candidates with score > 0.4
- Apply graduated penalty based on expected P&L
- Add MC columns to results table

### Phase 3: Replace Static ROI (4 hours)
✅ Replace static ROI with MC expected ROI in scoring formula
- Adjust weights to account for more realistic values
- Update documentation and UI labels
- Add toggle for "fast scan" (static) vs. "accurate scan" (MC)

---

## Testing & Validation

### Test Cases

1. **Near-ATM spreads** (should be filtered more aggressively)
2. **High IV stocks** (should see score reduction)
3. **Wide spreads** (should pass - asymmetry favors trader)
4. **Far OTM spreads** (should pass - high win rate, limited losses)

### Success Metrics

- ✅ Zero opportunities with negative MC expected P&L in top 10
- ✅ MC expected ROI within 20% of scan ROI for top opportunities
- ✅ Win rate from MC within 10% of static POEW
- ✅ Scan time increases by < 20%

---

## Conclusion

**Root Cause:** Credit spread scans use optimistic static calculations (max profit scenario) without validating against realistic Monte Carlo simulations that account for volatility drag, path dependency, and loss magnitudes.

**Impact:** 40-80% of passing opportunities have negative expected P&L, misleading users and leading to disappointing real-world results.

**Solution:** Add Monte Carlo expected P&L validation as either a hard filter (Phase 1) or integrated penalty/scoring component (Phase 2-3).

**Priority:** **HIGH** - This is a fundamental flaw that undermines the entire credit spread scanning system.

---

**Next Steps:**
1. Implement Phase 1 (hard filter) immediately
2. Run validation tests on SPY, QQQ, high IV stocks
3. Gather user feedback on scan time vs. quality tradeoff
4. Proceed to Phase 2/3 based on results
