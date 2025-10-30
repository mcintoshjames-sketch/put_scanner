# Best-Practice Fit Review & Improvement Suggestions

## Executive Summary

The `evaluate_fit()` function provides solid baseline checks for all 4 strategies (CSP, CC, COLLAR, IRON_CONDOR). This review identifies gaps and recommends enhancements to make the best-practice evaluation more robust and actionable.

---

## Current State Analysis

### Universal Checks (All Strategies)
✅ **Implemented:**
- Tenor sweet spot (DTE ranges)
- Liquidity (OI and bid-ask spread)
- Excess ROI vs T-bills

⚠️ **Missing:**
- Volume analysis (daily volume vs OI ratio)
- Implied volatility rank/percentile
- Market regime indicators (VIX level, trend)

### Strategy-Specific Checks

#### CSP (Cash-Secured Put)
✅ **Implemented:**
- Theta/Gamma ratio
- Delta target (-0.30 to -0.15)
- Sigma cushion
- OTM distance

⚠️ **Missing:**
- Win rate estimation (probability of profit)
- Assignment probability
- Earnings proximity check
- Support level analysis

#### CC (Covered Call)
✅ **Implemented:**
- Theta/Gamma ratio
- Delta target (0.20 to 0.35)
- Sigma cushion
- Ex-dividend assignment risk

⚠️ **Missing:**
- Upside capture analysis
- Cost basis protection check
- Earnings proximity check
- Resistance level analysis

#### COLLAR
✅ **Implemented:**
- Put/Call delta targets
- Dual sigma cushions
- Net credit/debit analysis

⚠️ **Missing:**
- Skew analysis (put vs call IV)
- Downside protection adequacy
- Opportunity cost vs outright long

#### IRON_CONDOR
✅ **Implemented:**
- Profit zone width
- Risk/reward ratio
- Balanced spreads

⚠️ **Missing:**
- Probability of max profit
- Wing distance analysis
- Skew positioning
- Short strike delta targets

---

## Recommended Improvements

### 1. Add Volume/Liquidity Ratio Check (All Strategies)
**Priority: HIGH**

```python
# Check volume-to-OI ratio for liquidity health
volume = float(_series_get(row, "Volume", float("nan")))
if volume == volume and oi > 0:
    vol_oi_ratio = volume / oi
    if vol_oi_ratio >= 0.5:
        checks.append(("Volume/OI ratio", "✅", f"{vol_oi_ratio:.2f} (healthy turnover)"))
    elif vol_oi_ratio >= 0.25:
        checks.append(("Volume/OI ratio", "⚠️", f"{vol_oi_ratio:.2f} (moderate turnover)"))
    else:
        checks.append(("Volume/OI ratio", "❌", f"{vol_oi_ratio:.2f} (low turnover, stale OI)"))
```

**Rationale:** OI alone doesn't guarantee liquidity. High OI with low volume may indicate stale positions.

---

### 2. Add Implied Volatility Rank (All Strategies)
**Priority: MEDIUM**

```python
# IV rank: where current IV sits relative to 52-week range
iv_rank = float(_series_get(row, "IVRank", float("nan")))
if iv_rank == iv_rank:
    if strategy in ("CSP", "CC", "IRON_CONDOR"):  # Premium selling
        if iv_rank >= 50:
            checks.append(("IV Rank", "✅", f"{iv_rank:.0f}th percentile (good for selling)"))
        elif iv_rank >= 30:
            checks.append(("IV Rank", "⚠️", f"{iv_rank:.0f}th percentile (acceptable)"))
        else:
            checks.append(("IV Rank", "❌", f"{iv_rank:.0f}th percentile (low IV for selling)"))
    else:  # COLLAR (buying protection)
        if iv_rank <= 30:
            checks.append(("IV Rank", "✅", f"{iv_rank:.0f}th percentile (cheap protection)"))
        else:
            checks.append(("IV Rank", "⚠️", f"{iv_rank:.0f}th percentile (expensive protection)"))
```

**Rationale:** Selling premium in high IV environments and buying protection in low IV environments improves edge.

---

### 3. Add Earnings Proximity Check (CSP, CC)
**Priority: HIGH**

```python
# Check if earnings announcement is within DTE window
days_to_earnings = int(_series_get(row, "DaysToEarnings", -1))
if days_to_earnings >= 0 and days_to_earnings <= days:
    checks.append(("Earnings risk", "⚠️", 
                  f"Earnings in {days_to_earnings} days (high vol event risk)"))
    flags["earnings_risk"] = True
elif days_to_earnings >= 0 and days_to_earnings <= days + 7:
    checks.append(("Earnings risk", "⚠️", 
                  f"Earnings shortly after expiry ({days_to_earnings} days)"))
else:
    checks.append(("Earnings risk", "✅", "No earnings within cycle"))
```

**Rationale:** Earnings create significant volatility risk. Traders should be explicitly warned.

---

### 4. Add Probability of Profit (CSP, CC, IRON_CONDOR)
**Priority: MEDIUM**

```python
# Calculate probability of profit based on delta
if strategy == "CSP":
    pop = 1.0 - abs(pdelta) if pdelta == pdelta else float("nan")
elif strategy == "CC":
    pop = 1.0 - cdelta if cdelta == cdelta else float("nan")
elif strategy == "IRON_CONDOR":
    # Approximate POP for iron condor (more complex calculation needed)
    pop = float(_series_get(row, "ProbabilityOfProfit", float("nan")))

if pop == pop:
    if pop >= 0.70:
        checks.append(("Probability of profit", "✅", f"{pop*100:.0f}%"))
    elif pop >= 0.60:
        checks.append(("Probability of profit", "⚠️", f"{pop*100:.0f}% (prefer ≥70%)"))
    else:
        checks.append(("Probability of profit", "❌", f"{pop*100:.0f}% (too aggressive)"))
```

**Rationale:** Win rate context helps traders understand risk/reward trade-offs.

---

### 5. Add Wing Distance Check (IRON_CONDOR)
**Priority: HIGH**

```python
# Check if wings are far enough from short strikes
if all(x == x for x in [put_long_strike, put_short_strike, call_short_strike, call_long_strike]):
    put_wing_dist = put_short_strike - put_long_strike
    call_wing_dist = call_long_strike - call_short_strike
    
    # Calculate distance as % of short strike
    put_wing_pct = (put_wing_dist / put_short_strike) * 100
    call_wing_pct = (call_wing_dist / call_short_strike) * 100
    
    if min(put_wing_pct, call_wing_pct) >= 2.0:
        checks.append(("Wing distance", "✅", 
                      f"Put {put_wing_pct:.1f}%, Call {call_wing_pct:.1f}% (adequate buffer)"))
    elif min(put_wing_pct, call_wing_pct) >= 1.0:
        checks.append(("Wing distance", "⚠️", 
                      f"Put {put_wing_pct:.1f}%, Call {call_wing_pct:.1f}% (tight wings)"))
    else:
        checks.append(("Wing distance", "❌", 
                      f"Put {put_wing_pct:.1f}%, Call {call_wing_pct:.1f}% (very tight)"))
```

**Rationale:** Tighter wings increase max profit but reduce safety margin. Should be explicitly evaluated.

---

### 6. Add Short Strike Delta Check (IRON_CONDOR)
**Priority: MEDIUM**

```python
# Check delta of short strikes (should be ~0.15-0.20 on each side)
put_short_delta = float(_series_get(row, "PutShortDelta", float("nan")))
call_short_delta = float(_series_get(row, "CallShortDelta", float("nan")))

if put_short_delta == put_short_delta and call_short_delta == call_short_delta:
    put_in_range = -0.20 <= put_short_delta <= -0.15
    call_in_range = 0.15 <= call_short_delta <= 0.20
    
    if put_in_range and call_in_range:
        checks.append(("Short strike deltas", "✅", 
                      f"Put Δ {put_short_delta:.2f}, Call Δ {call_short_delta:.2f}"))
    else:
        checks.append(("Short strike deltas", "⚠️", 
                      f"Put Δ {put_short_delta:.2f}, Call Δ {call_short_delta:.2f} (prefer ±0.15-0.20)"))
```

**Rationale:** Target deltas help standardize Iron Condor strike selection for consistency.

---

### 7. Add Skew Analysis (IRON_CONDOR)
**Priority: MEDIUM**

```python
# Analyze put vs call IV skew
put_iv = float(_series_get(row, "PutIV", float("nan")))
call_iv = float(_series_get(row, "CallIV", float("nan")))

if put_iv == put_iv and call_iv == call_iv:
    skew = put_iv - call_iv
    if abs(skew) <= 2.0:
        checks.append(("IV skew", "✅", f"{skew:+.1f}% (balanced)"))
    elif abs(skew) <= 5.0:
        checks.append(("IV skew", "⚠️", f"{skew:+.1f}% (moderate skew)"))
    else:
        side = "put" if skew > 0 else "call"
        checks.append(("IV skew", "⚠️", f"{skew:+.1f}% (strong {side}-side skew)"))
```

**Rationale:** Asymmetric IV skew affects Iron Condor pricing and risk.

---

### 8. Add Cost Basis Check (CC)
**Priority: MEDIUM**

```python
# Check if covered call strike is above cost basis
cost_basis = float(_series_get(row, "CostBasis", float("nan")))
if cost_basis == cost_basis and K == K:
    if K >= cost_basis:
        profit_on_assignment = ((K - cost_basis) / cost_basis) * 100
        checks.append(("Strike vs cost basis", "✅", 
                      f"Strike ${K:.2f} > basis ${cost_basis:.2f} (+{profit_on_assignment:.1f}% if assigned)"))
    else:
        loss_on_assignment = ((K - cost_basis) / cost_basis) * 100
        checks.append(("Strike vs cost basis", "❌", 
                      f"Strike ${K:.2f} < basis ${cost_basis:.2f} ({loss_on_assignment:.1f}% loss if assigned)"))
```

**Rationale:** Selling calls below cost basis locks in losses if assigned. Critical for CC strategy.

---

### 9. Add Max Loss Sanity Check (All Strategies)
**Priority: HIGH**

```python
# Calculate max loss as % of account (assuming account size known)
account_size = float(st.session_state.get("account_size", 100000))
max_loss = calculate_max_loss(strategy, row)  # Strategy-specific calculation

if max_loss == max_loss:
    loss_pct = (max_loss / account_size) * 100
    if loss_pct <= 2.0:
        checks.append(("Position sizing", "✅", f"Max loss {loss_pct:.1f}% of account"))
    elif loss_pct <= 5.0:
        checks.append(("Position sizing", "⚠️", f"Max loss {loss_pct:.1f}% of account (consider 1-2%)"))
    else:
        checks.append(("Position sizing", "❌", f"Max loss {loss_pct:.1f}% of account (too large!)"))
        flags["position_too_large"] = True
```

**Rationale:** Position sizing is critical risk management. Should be evaluated against account size.

---

### 10. Add Market Regime Indicator (All Strategies)
**Priority: LOW**

```python
# Check VIX level to assess market regime
vix_level = float(st.session_state.get("current_vix", float("nan")))
if vix_level == vix_level:
    if vix_level <= 15:
        checks.append(("Market regime (VIX)", "⚠️", 
                      f"VIX {vix_level:.1f} (low vol environment, thin premiums)"))
    elif vix_level <= 25:
        checks.append(("Market regime (VIX)", "✅", 
                      f"VIX {vix_level:.1f} (moderate vol environment)"))
    else:
        checks.append(("Market regime (VIX)", "⚠️", 
                      f"VIX {vix_level:.1f} (high vol environment, elevated risk)"))
```

**Rationale:** Market regime context helps traders adjust expectations and risk parameters.

---

## Implementation Priority

### Phase 1 (Critical - Implement First)
1. ✅ Earnings proximity check (CSP, CC)
2. ✅ Volume/OI ratio (all strategies)
3. ✅ Max loss sanity check (all strategies)
4. ✅ Wing distance check (IRON_CONDOR)
5. ✅ Cost basis check (CC)

### Phase 2 (Important - Implement Soon)
1. ✅ Probability of profit (CSP, CC, IRON_CONDOR)
2. ✅ IV Rank (all strategies)
3. ✅ Short strike delta check (IRON_CONDOR)
4. ✅ Skew analysis (IRON_CONDOR)

### Phase 3 (Nice to Have - Future Enhancement)
1. ✅ Market regime indicator (all strategies)
2. ✅ Support/resistance proximity
3. ✅ Historical performance of similar setups
4. ✅ Correlation analysis (portfolio level)

---

## Data Requirements

To implement these improvements, we need to ensure the following data is available:

### Currently Missing:
- `Volume` - Daily option volume
- `IVRank` - 52-week IV percentile
- `DaysToEarnings` - Days until next earnings announcement
- `ProbabilityOfProfit` - Calculated POP
- `PutShortDelta`, `CallShortDelta` - Individual leg deltas for Iron Condor
- `PutIV`, `CallIV` - Individual leg IVs for skew analysis
- `CostBasis` - User's cost basis for CC (optional, user input)
- `current_vix` - Current VIX level (session state)
- `account_size` - User's account size (session state)

### Data Collection Strategy:
1. **Option chain data**: Add volume to existing option data collection
2. **IV metrics**: Calculate IV rank from historical IV data
3. **Earnings**: Integrate earnings calendar API (Alpha Vantage has this)
4. **User inputs**: Add settings panel for account size, cost basis
5. **Market data**: Fetch VIX from yfinance daily

---

## Testing Strategy

For each new check:
1. Create unit test with edge cases
2. Test with real market data
3. Validate thresholds against historical performance
4. Get user feedback on actionability
5. Iterate on thresholds and messaging

---

## Conclusion

The current `evaluate_fit()` implementation provides a solid foundation. The recommended improvements focus on:

1. **Risk awareness**: Earnings, position sizing, max loss checks
2. **Liquidity confidence**: Volume/OI ratio
3. **Strategy optimization**: IV rank, delta targets, skew
4. **Actionable insights**: Clear thresholds with status indicators

Implementing Phase 1 improvements will significantly enhance risk management. Phase 2 adds strategic optimization. Phase 3 provides advanced context for experienced traders.

**Estimated Development Effort:**
- Phase 1: 4-6 hours
- Phase 2: 3-4 hours  
- Phase 3: 2-3 hours
- Data integration: 4-6 hours

**Total: ~15-20 hours for complete implementation**
