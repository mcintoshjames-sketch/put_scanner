# Iron Condor Fix - Root Cause Analysis

## Problem
Iron Condor strategy was returning 0 results even with very loose screening parameters (min_oi=50, max_spread=25%, min_roi=5%).

## Root Cause
The `schwab_provider.py` file was filtering options chains to **puts only**:

```python
def chain_snapshot_df(self, symbol: str, expiration: str) -> pd.DataFrame:
    df = self.client.chain_snapshot_df(symbol, expiration)
    # Filter to puts only  ← THIS WAS THE PROBLEM
    if not df.empty:
        df = df[df["type"] == "put"].copy()
    return df
```

Since Iron Condor is a 4-leg strategy requiring both OTM puts AND OTM calls, filtering to puts only caused:
- ✅ Put spreads found correctly (107-191 candidates per expiration)
- ❌ Call spreads had 0 candidates (calls were filtered out)
- ❌ Result: 0 Iron Condors (needs both sides)

## Investigation Process

1. **Initial hypothesis**: `min_days` parameter issue
   - Fixed min_days default from 0 to 1
   - Fixed slider minimum from 0 to 1
   - **Result**: Still 0 Iron Condors found

2. **Debug logging added**:
   - Confirmed expirations in range exist (15, 22, 29, 36, 50 days)
   - Confirmed chains being fetched (5 expirations processed)
   - Discovered: `puts_sell=107-191, calls_sell=0`

3. **Chain inspection**:
   - Added logging to see chain contents
   - Found: `Fetched 146 options -> 146 puts, 0 calls`
   - **Root cause identified**: Schwab provider filtering to puts only

## Solution
Modified `providers/schwab_provider.py` to return both calls and puts:

```python
def chain_snapshot_df(self, symbol: str, expiration: str) -> pd.DataFrame:
    """Returns both calls and puts (supports Iron Condor and multi-leg strategies)."""
    df = self.client.chain_snapshot_df(symbol, expiration)
    return df  # No filtering - return full chain
```

## Verification
After fix, tested with SPY:
- ✅ Fetched chains: `292 options -> 146 puts, 146 calls`
- ✅ Found 3 Iron Condor opportunities:
  - 15 DTE: $665P/$705C, $1.21 credit, 777% ROI annualized
  - 29 DTE: $656P/$715C, $1.11 credit, 357% ROI annualized
  - 50 DTE: $645P/$730C, $1.03 credit, 190% ROI annualized

## Impact
This fix enables:
- ✅ Iron Condor strategy (primary benefit)
- ✅ Any future multi-leg strategies requiring calls (straddles, strangles, calendars, etc.)
- ✅ Call-based strategies (covered calls, long calls, etc.)

## Commits
- Initial implementation: `417f95a` (Iron Condor feature complete)
- Bug fix: `a561725` (Schwab provider returns both calls and puts)
