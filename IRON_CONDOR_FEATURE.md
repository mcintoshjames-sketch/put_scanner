# Iron Condor Strategy Implementation

## Overview
Added Iron Condor as the 4th strategy to the Options Income Strategy Lab, providing a neutral income-generating strategy with defined risk.

## Strategy Structure
**Iron Condor** = Sell OTM Put Spread + Sell OTM Call Spread
- **Sell Put** at strike Kps (short put)
- **Buy Put** at strike Kpl (long put, Kpl < Kps)
- **Sell Call** at strike Kcs (short call)  
- **Buy Call** at strike Kcl (long call, Kcl > Kcs)

## Key Features Implemented

### 1. Analyzer Function: `analyze_iron_condor()`
**Location**: `strategy_lab.py` lines ~1433-1713

**Parameters**:
- `min_days`, `days_limit`: Tenor range (30-45 DTE recommended)
- `min_oi`, `max_spread`: Liquidity filters (all 4 legs)
- `spread_width_put`, `spread_width_call`: Wing widths (default $5)
- `target_delta_short`: Target delta for short strikes (default 0.16 = 84% POEW)
- `min_roi`: Minimum annualized ROI on risk
- `min_cushion`: Minimum sigma cushion for both wings
- `earn_window`: Earnings avoidance window
- `risk_free`: Risk-free rate for Greeks
- `bill_yield`: T-bill yield for excess return comparison

**Screening Logic**:
1. **Find Short Put**: Target delta ~-0.16 (84% probability of expiring worthless)
2. **Find Short Call**: Target delta ~+0.16 (84% POEW)
3. **Find Long Puts**: Fixed width below short put (e.g., $5 lower)
4. **Find Long Call**: Fixed width above short call (e.g., $5 higher)
5. **Liquidity Check**: All 4 legs must meet OI and spread requirements
6. **Calculate Metrics**:
   - Net Credit = (Put Spread Credit) + (Call Spread Credit)
   - Max Loss = max(put_width, call_width) - net_credit
   - ROI = (net_credit / max_loss) × (365 / days)
   - Breakevens: Lower = Kps - credit, Upper = Kcs + credit
   - Cushions: Distance to strikes in standard deviations

**Scoring Formula** (optimized for neutral income):
```
Score = 0.40 × ROI_ann                  # High ROI (credit/risk ratio)
      + 0.30 × balance_score            # Symmetric wings (equal cushion)
      + 0.20 × cushion_score            # Sufficient distance from price
      + 0.10 × liquidity_score          # Tight spreads across all legs
```

**Returns DataFrame** with columns:
- Strategy, Ticker, Price, Exp, Days
- PutShortStrike, PutLongStrike, PutSpreadCredit, PutShortΔ
- CallShortStrike, CallLongStrike, CallSpreadCredit, CallShortΔ
- NetCredit, MaxLoss, Capital, ROI%_ann, ROI%_excess_bills
- BreakevenLower, BreakevenUpper, Range
- PutCushionσ, CallCushionσ, ProbMaxProfit
- PutSpread%, CallSpread%, PutShortOI, CallShortOI, IV, Score

### 2. Best Practices
**Location**: `strategy_lab.py` lines ~1732-1741

**Guidelines**:
- **Structure**: Sell OTM put spread + sell OTM call spread (neutral, defined risk)
- **Tenor**: 30-45 DTE for theta decay without gamma risk
- **Strikes**: Short strikes Δ ~±0.15-0.25 (84-75% POEW); wing width $5-10 or 5-10% OTM
- **Liquidity**: All 4 legs need OI ≥ 200, bid-ask ≤ 10%
- **Risk**: Max loss = wing width − net credit; target credit/max_loss ≥ 25-35%
- **Balance**: Symmetric wings (equal cushion) for neutral outlook
- **Exit**: Take profit at 50-75% of max credit; close if one side Δ > ~0.35
- **Avoid**: Earnings and high-IV events (gap risk through breakevens)

### 3. UI Integration

#### Sidebar Controls (lines ~2753-2770)
New section: **"Iron Condor"**
- Short Strike Target Δ (slider, default 0.16)
- Put Spread Width (input, default $5)
- Call Spread Width (input, default $5)
- Min ROI % annualized (input, default 15%)
- Min Cushion σ (input, default 0.5)

#### Tab 3: Iron Condor Results (lines ~3648-3669)
Displays screening results with:
- 4-leg structure details (all strikes, deltas, credits)
- Risk metrics (net credit, max loss, ROI)
- Breakeven range and probability metrics
- Cushion for both wings
- Liquidity metrics for all 4 legs

#### Tab 4: Compare (lines ~3681-3722)
Updated to include Iron Condor in strategy comparison table with proper key formatting:
- Key format: `{Ticker} | {Exp} | CS={CallShortStrike} | PS={PutShortStrike}`

#### Tab 6: Playbook (lines ~3979-3987)
Added Iron Condor to best practices display

### 4. Selection & Navigation
**Location**: `strategy_lab.py` lines ~3007-3105

Updated functions:
- **`_keys_for()`**: Builds unique keys for Iron Condor selection
- **`_get_selected_row()`**: Retrieves selected Iron Condor row for Risk/Runbook tabs
- **Strategy picker**: Dropdown now includes "IRON_CONDOR" option

### 5. Session State & Scanning
**Location**: `strategy_lab.py` lines ~2464, 2777-2904, 2924-2948

- **Initialization**: Added `df_iron_condor` to session state (line 2464)
- **`run_scans()` function**: Updated to scan Iron Condor in parallel (returns 4 dataframes)
- **Parameter passing**: Added `ic_*` parameters to opts dict
- **Results storage**: Saves `df_iron_condor` to session state
- **Success message**: Shows Iron Condor opportunity count

## Usage Example

### Scanning for Iron Condors
1. **Set Universe**: Enter tickers (e.g., "SPY, QQQ, AAPL")
2. **Configure Tenor**: Min 30 days, Max 45 days
3. **Set Iron Condor Parameters**:
   - Target Δ: 0.16 (84% POEW on each side)
   - Put/Call Width: $5 (narrower for ETFs, wider for volatile stocks)
   - Min ROI: 15% annualized (25-35% of max loss)
   - Min Cushion: 0.5σ (ensure price is away from strikes)
4. **Liquidity**: Min OI 200, Max Spread 10%
5. **Click "Scan Strategies"**

### Interpreting Results
**Key Metrics**:
- **NetCredit**: Total premium collected (higher is better)
- **MaxLoss**: Wing width − credit (defines capital at risk)
- **ROI%_ann**: (Credit / MaxLoss) × (365 / Days) × 100
- **PutCushionσ / CallCushionσ**: Distance in std devs (>1.0 = safer)
- **Range**: Breakeven upper − breakeven lower (wider = more forgiving)
- **ProbMaxProfit**: Approximate probability both spreads expire worthless
- **Balance**: Look for similar cushions on both sides (neutral strategy)

**Good Iron Condor Example**:
```
SPY | 2025-12-19 | CS=610 | PS=570
- Net Credit: $2.50
- Max Loss: $2.50 ($5 wing width - $2.50 credit)
- ROI: 100% (over 45 days = 811% annualized)
- Put Cushion: 1.5σ, Call Cushion: 1.4σ (balanced wings)
- Breakeven Range: $567.50 - $612.50 (wide margin)
- Liquidity: All legs OI > 500, spreads < 5%
```

## Technical Notes

### Scoring Rationale
Iron Condor scoring differs from directional strategies:
- **ROI Weight (40%)**: Credit/risk ratio is paramount for income strategies
- **Balance Weight (30%)**: Symmetric wings critical for neutral outlook
- **Cushion Weight (20%)**: Safety margin from both strikes
- **Liquidity Weight (10%)**: Lower than CSP/CC because 4 legs = more slippage risk

### Delta Targeting
- **0.16 delta ≈ 84% POEW** (probability of expiring worthless)
- Both short strikes target same delta magnitude for balanced wings
- Long strikes fixed width away (simple, predictable risk)

### Wing Width Considerations
- **ETFs (SPY, QQQ)**: $5 wings typical, price-to-strike ratio matters
- **High-price stocks**: $10-15 wings may be needed
- **Volatile stocks**: Wider wings reduce gamma risk but lower ROI

### Risk Management
- Max loss is **known and capped** = wing width − credit
- **Breakeven protection**: ±(credit) from short strikes
- **Assignment risk**: Low if kept to expiration with wide cushions
- **Early close**: Exit at 50-75% profit or if one wing delta > 0.35

## Integration with Existing Features

### Monte Carlo Tab
Iron Condor **not yet integrated** with Monte Carlo simulation (complex 4-leg P&L).
Future enhancement would require:
- GBM terminal price simulation
- 4-leg payoff function: max(0, Kps - ST) - max(0, Kpl - ST) - max(0, ST - Kcs) + max(0, ST - Kcl) + credit
- P&L distribution and expected value calculation

### Plan & Runbook Tab
Iron Condor selection supported via `_get_selected_row()`.
Future enhancement: Iron Condor-specific order preview and risk analysis.

### Stress Test Tab
Will use selected Iron Condor if available.
Shows P&L at various price points between breakevens.

## Files Modified

1. **strategy_lab.py**:
   - Added `analyze_iron_condor()` function (~280 lines)
   - Updated `best_practices()` for Iron Condor guidelines
   - Added sidebar controls for Iron Condor scanning
   - Updated `run_scans()` to include Iron Condor
   - Added Iron Condor tab to UI
   - Updated Compare tab integration
   - Updated Playbook tab
   - Updated session state initialization
   - Updated strategy selection and navigation functions
   - Updated all tab indices (5-9 → 6-10)

## Testing Recommendations

1. **Scan ETFs first** (SPY, QQQ, IWM) - highest liquidity, tightest spreads
2. **Check balance**: PutCushionσ should be close to CallCushionσ
3. **Verify liquidity**: All 4 legs show good OI and tight spreads
4. **Validate strikes**: Short strikes should be OTM with deltas ~±0.16
5. **ROI sanity check**: 15-40% annualized is realistic; >100% may be too risky
6. **Compare to alternatives**: Use Compare tab to see Iron Condor vs CSP/CC/Collar

## Known Limitations

1. **No Monte Carlo support yet**: Complex 4-leg payoff not yet simulated
2. **No order preview**: Schwab integration for 4-leg order not implemented
3. **Fixed wing widths**: Dynamic wing optimization not available
4. **No volatility skew adjustment**: Uses average IV for both sides
5. **Simplified POEW**: Uses Black-Scholes; ignores skew/kurtosis

## Future Enhancements

1. **Monte Carlo**: Add 4-leg P&L simulation with GBM
2. **Dynamic wing selection**: Optimize wing widths based on liquidity/risk
3. **Skew analysis**: Display put/call IV skew, adjust scoring
4. **Adjustment suggestions**: Recommend rolls when wings threatened
5. **Order preview**: Schwab 4-leg order builder integration
6. **Greeks dashboard**: Display position-level delta, gamma, theta, vega
7. **Iron Butterfly variant**: Add related strategy with ATM short strikes

## Conclusion

The Iron Condor strategy adds a powerful neutral income-generation tool to the lab. It's ideal for:
- **Range-bound markets**: Profit when price stays between breakevens
- **High-IV environments**: Collect more premium without taking directional risk
- **Defined risk tolerance**: Know max loss upfront
- **Balanced portfolios**: Combine with directional CSP/CC for diversification

The implementation follows the same patterns as existing strategies (CSP, CC, Collar) for consistency and maintainability.
