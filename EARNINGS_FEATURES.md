# Earnings Date Checking Features

## Overview

Your Strategy Lab now has comprehensive earnings date protection to help you avoid the elevated risk associated with earnings announcements.

---

## How It Works

### 1. **Automatic Filtering (Already Built In)**

The app automatically **excludes positions** where the expiration date falls within your configured earnings window:

```python
# Default: ±5 days around earnings
if earn_date is not None and abs((earn_date - ed).days) <= int(earn_window):
    continue  # Skip this position
```

**What This Means:**
- If AAPL has earnings on Nov 2nd
- And you set earnings window to ±5 days
- Any expirations between Oct 28 - Nov 7 will be **automatically excluded**

### 2. **Configurable Window** (Sidebar)

Control the safety buffer with the slider:
```
Earnings window (± days, CSP/CC): 0 to 14 days (default: 5)
```

**Recommended Settings:**
- **Conservative:** 7-10 days (avoid week before/after)
- **Balanced:** 5 days (default, good for most traders)
- **Aggressive:** 3 days (minimum, only for experienced traders)
- **Disable:** 0 days (not recommended unless trading ETFs)

### 3. **Earnings Calendar Widget** (NEW!)

A dedicated earnings calendar appears after you run a scan, showing:

| Feature | Description |
|---------|-------------|
| **Ticker** | Stock symbol |
| **Earnings Date** | Next scheduled earnings announcement |
| **Days Away** | Days until earnings (negative = past) |
| **Status** | 🟢 Safe or 🔴 CAUTION |

**Status Indicators:**
- 🟢 **Safe:** Earnings beyond your configured window
- 🔴 **CAUTION:** Earnings within your configured window

**Note:** Positions marked CAUTION are already filtered out from results, but the calendar helps you see which tickers have upcoming earnings.

### 4. **DaysToEarnings Column** (NEW!)

Each strategy results table (CSP, CC) now includes a `DaysToEarnings` column:

**Values:**
- **Positive number:** Earnings in X days (future)
- **Negative number:** Earnings happened X days ago (past)
- **Blank/NaN:** Earnings date unknown or unavailable

**Example:**
```
Ticker | Days | DaysToEarnings | Interpretation
-------|------|----------------|---------------
AAPL   | 21   | 45             | Earnings in 45 days, safe
MSFT   | 30   | 8              | Earnings in 8 days, reviewed
GOOGL  | 25   | -3             | Earnings 3 days ago, safe now
TSLA   | 28   | NaN            | Unknown earnings date
```

### 5. **Visual Warnings** (NEW!)

When positions have earnings within 14 days (even if outside your filter window), you'll see:

```
⚠️ 3 position(s) have earnings within 14 days. Review 'DaysToEarnings' column.
```

This alerts you to upcoming events that might affect your positions.

---

## Data Source

**yfinance API:**
- Pulls earnings dates from Yahoo Finance
- Usually accurate but not guaranteed
- May be missing for some tickers (especially small caps)
- Updates daily

**Backup Verification:**
- Always verify earnings dates with your broker
- Check company investor relations page
- Use earnings calendars (Earnings Whispers, Nasdaq.com)

---

## Earnings Risk Explained

### Why Avoid Earnings?

1. **IV Crush**
   - Pre-earnings: IV spikes (premium inflated)
   - Post-earnings: IV collapses (premium deflates)
   - Bad for short options: You collect high premium but face gap risk

2. **Gap Risk**
   - Stock can gap 5-15% in minutes after earnings
   - Puts you deep ITM instantly
   - No time to adjust or close

3. **Unpredictable Movement**
   - Even "good" earnings can cause stock to drop
   - Guidance matters more than results
   - Options implied move often underestimates actual move

### When Earnings Might Be OK

**ETFs:**
- Diversified holdings dampen single-stock earnings impact
- Still check for major holdings (e.g., NVDA in QQQ)

**Far OTM Positions:**
- If strike is 20%+ OTM, earnings gap less likely to threaten
- Still risky, but manageable with proper sizing

**After Earnings (Within 1-2 days):**
- IV has crushed, premium is cheaper
- Known event is past
- Can be good entry opportunity

---

## Best Practices

### 1. **Check Calendar Before Entering**

Even though auto-filtering works, manually review:
```
1. Look at Earnings Calendar widget
2. Check DaysToEarnings column
3. Verify no earnings between entry and expiration
```

### 2. **Exit Before Earnings**

If you're holding a position and earnings approaches:
```
DaysToEarnings = 10 → Start planning exit
DaysToEarnings = 7  → Definitely exit or roll
DaysToEarnings = 3  → Emergency exit if still holding
```

### 3. **Use Earnings for Roll Timing**

**Scenario:**
- You're in AAPL $170 CSP, 14 DTE
- Earnings in 5 days
- Captured 60% profit

**Action:**
- Close for profit NOW
- Wait until day after earnings
- Re-enter with fresh 21-30 DTE position
- Collect post-earnings premium with IV crushed risk gone

### 4. **Earnings Window Settings by Account Type**

| Account Type | Recommended Window | Rationale |
|--------------|-------------------|-----------|
| IRA/Retirement | 7-10 days | Max safety, no need for aggressive timing |
| Margin/Active | 5 days | Balanced, default setting |
| Small/Learning | 10-14 days | Learning mode, avoid surprises |
| Professional | 3-5 days | Experienced, can handle edge cases |

### 5. **Sector-Specific Considerations**

**Tech (AAPL, MSFT, GOOGL, META, NVDA):**
- ±7 days minimum (high volatility)
- Earnings often drive sector moves
- Consider pausing all tech positions during earnings season

**Financials (JPM, BAC, GS):**
- ±5 days usually sufficient
- Less dramatic moves
- Watch for Fed announcements (bigger impact)

**Utilities (XEL, NEE, SO):**
- ±3 days might be OK
- Lower volatility sector
- Earnings less impactful

**Biotechs/Small Cap:**
- ±10 days recommended
- Binary events (FDA approvals often with earnings)
- Avoid entirely if risk-averse

---

## Troubleshooting

### "Earnings date missing for ticker X"

**Causes:**
1. yfinance doesn't have data for this ticker
2. Company hasn't scheduled earnings yet
3. Recent IPO or delisting

**Solutions:**
- Manually check company's investor relations page
- Avoid the ticker if unsure
- Set earnings window to 0 (disable) for this specific scan (not recommended)

### "Earnings calendar shows past dates"

**Cause:** Data hasn't updated since last earnings

**Solution:**
- Check if `DaysToEarnings` is negative (past event)
- If so, position is safe
- Company may not have announced next date yet

### "All positions filtered out"

**Cause:** All expirations fall within earnings windows

**Solutions:**
1. Reduce earnings window from 5 to 3 days
2. Extend your `Max Days` to find expirations beyond earnings
3. Choose different tickers without near-term earnings
4. Use the Pre-Screener to find non-earnings tickers

---

## Example Workflow

### Scenario: Scanning AAPL for CSP opportunities

**Step 1: Run Scan**
```
Tickers: AAPL
Min Days: 10
Max Days: 45
Earnings Window: 5 days
```

**Step 2: Check Earnings Calendar**
```
Ticker | Earnings Date | Days Away | Status
-------|---------------|-----------|-------
AAPL   | 2025-11-15    | 19        | 🟢 Safe
```

**Step 3: Review Results**
```
All expirations shown are safe (earnings on Nov 15)
Best option: Nov 8 expiration (7 days before earnings)
```

**Step 4: Enter Position**
```
✅ SELL AAPL Nov 8 $170 PUT @$2.50
✅ Earnings on Nov 15 (7 days after expiration)
✅ Safe from earnings risk
```

**Step 5: Monitor**
```
Check DaysToEarnings column daily
If company moves earnings date, exit early
```

---

## Advanced: Earnings Plays (For Experienced Traders)

### Strategy 1: Sell Pre-Earnings, Close Same Day

**Setup:**
- Sell CSP 1-2 days before earnings
- High IV = collect big premium
- Close immediately after earnings announcement

**Risk:** If you can't close (gap down at open), you're stuck ITM

### Strategy 2: Buy Day After Earnings

**Setup:**
- Wait for earnings to pass
- IV crushed, premium cheap
- Sell CSP with 21-30 DTE

**Advantage:** Known event is behind you, cleaner risk

### Strategy 3: Collar Before Earnings

**Setup:**
- Own 100 shares
- Earnings approaching
- Sell OTM call, buy OTM put
- Defined risk for earnings

**Advantage:** Protected from gap, still collect premium

**Note:** These are ADVANCED strategies. Your app's default behavior (avoiding earnings) is the safest approach for most traders.

---

## Summary

✅ **Automatic Protection:** Positions within earnings window are filtered out

✅ **Visual Calendar:** See all upcoming earnings at a glance

✅ **DaysToEarnings Column:** Know exactly when earnings hit

✅ **Configurable:** Adjust window based on risk tolerance

✅ **Warnings:** Alerts for nearby earnings

**Default Behavior = Maximum Safety:** Your app protects you by default. You have to manually reduce the earnings window to increase risk.

---

## Quick Reference

| Feature | Location | Purpose |
|---------|----------|---------|
| Earnings Window Slider | Sidebar → Global Settings | Set safety buffer (±days) |
| Earnings Calendar | Main page (after scan) | View all upcoming earnings |
| DaysToEarnings Column | CSP/CC results tables | See days to earnings per position |
| Warning Alerts | Top of CSP/CC tabs | Alert for positions near earnings |
| Auto-Filtering | Background (automatic) | Removes risky expirations |

---

**Remember:** Earnings are the #1 cause of unexpected losses in options income strategies. Your app's built-in protection is your friend—use it!

---

*Last Updated: October 27, 2025*
