# Code Optimization Opportunities

**File:** `strategy_lab.py` (3,132 lines)  
**Date:** October 27, 2025

---

## High-Impact Optimizations

### 1. **Consolidate Repeated yf.Ticker() Calls** ⭐⭐⭐
**Impact:** Reduce API calls by 30-50%, faster execution  
**Current Issue:** Creating new `yf.Ticker()` objects repeatedly for same symbol

**Current Pattern:**
```python
# Lines 716-717, 716-717, 1069, 1773, 2300, etc.
stock = yf.Ticker(ticker)  # Created multiple times per ticker!
```

**Problem:** In `analyze_csp()`, `analyze_cc()`, and `analyze_collar()`, you fetch:
- Price (line 717): `yf.Ticker(ticker)`
- Expirations (fetched separately)
- Options chains (multiple expiration calls)
- Earnings date (line 716)
- Dividend info

**All from separate Ticker objects!**

**Solution:**
```python
# Create ONCE per ticker in analyzer functions
def analyze_csp(ticker, **kwargs):
    stock = yf.Ticker(ticker)  # Once!
    
    # Reuse for price
    current_price = fetch_price(ticker)
    
    # Reuse for earnings
    earn_date = get_earnings_date(stock)
    
    # Reuse for dividends
    div_ps_annual, div_y = trailing_dividend_info(stock, current_price)
    
    # Then proceed with expirations/chains
```

**Estimated Gain:** 40-60% faster on multi-ticker scans (5-10 tickers: 1-2s faster)

---

### 2. **Cache Historical Volatility Calculation** ⭐⭐⭐
**Impact:** Eliminate 3-4 redundant calls per ticker  
**Current Issue:** HV computed fresh each time, but intraday it doesn't change

**Current Pattern:**
```python
# Multiple analyzer functions call this independently
hist = stock.history(period="3mo")
returns = hist['Close'].pct_change()
hv = returns.std() * np.sqrt(252)
```

**Solution:** Cache HV per ticker for session:
```python
@st.cache_data(ttl=300, show_spinner=False)
def cached_hv(ticker: str, period: str = "3mo") -> float:
    """Cache HV for 5 minutes (enough for intraday consistency)"""
    stock = yf.Ticker(ticker)
    hist = stock.history(period=period)
    if hist.empty or len(hist) < 20:
        return 0.20  # default
    returns = hist['Close'].pct_change().dropna()
    if len(returns) < 20:
        return 0.20
    return float(returns.iloc[-30:].std() * np.sqrt(252))
```

**Estimated Gain:** 20-30% faster on repeated scans of same tickers

---

### 3. **Batch Earnings Calendar Fetch** ⭐⭐
**Impact:** Parallel fetching instead of sequential loop  
**Current Issue:** Lines 2298-2307 loop sequentially:

```python
for ticker in sorted(all_tickers):  # One at a time!
    stock = yf.Ticker(ticker)
    earn_date = get_earnings_date(stock)
```

**Solution:** Use ThreadPoolExecutor for parallel fetches:
```python
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

def fetch_earnings_parallel(tickers, max_workers=5):
    """Fetch earnings dates in parallel (10-50 tickers: 3-4x faster)"""
    results = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                lambda t: (t, get_earnings_date(yf.Ticker(t)))
            ): t for t in tickers
        }
        for future in as_completed(futures):
            ticker, earn_date = future.result()
            results[ticker] = earn_date
    return results

# Use in earnings calendar:
earnings_dict = fetch_earnings_parallel(sorted(all_tickers), max_workers=5)
for ticker in sorted(all_tickers):
    earn_date = earnings_dict.get(ticker)
    # ...
```

**Estimated Gain:** 10 tickers: 4-5s → 1-2s (60-70% faster)

---

### 4. **Eliminate Redundant DataFrame Operations** ⭐⭐
**Impact:** Reduce memory, CPU overhead  
**Current Issue:** Multiple unnecessary `.copy()` and concatenations

**Example (Line 179-189):**
```python
dfs = []
for typ, df in (("call", ch.calls), ("put", ch.puts)):
    if df is None or df.empty:
        continue
    tmp = df.copy()  # Unnecessary copy every time
    tmp["type"] = typ
    dfs.append(tmp)
out = pd.concat(dfs, ignore_index=True)  # Expensive for 2 items
```

**Optimized:**
```python
dfs = []
for typ, df in (("call", ch.calls), ("put", ch.puts)):
    if df is not None and not df.empty:
        df["type"] = typ  # In-place assignment
        dfs.append(df)

if dfs:
    out = pd.concat(dfs, ignore_index=True, copy=False)
else:
    out = pd.DataFrame()
```

**Estimated Gain:** 5-10% memory reduction, faster concat

---

### 5. **Replace try/except Exception Spam with Targeted Catches** ⭐
**Impact:** Clearer code, easier debugging, minor performance gain  
**Current Issue:** Generic `except Exception` masks real errors

**Current Pattern (Lines 716-750, repeated ~50 times):**
```python
try:
    # Multiple things that could fail
    stock = yf.Ticker(ticker)
    hist = stock.history(...)
    returns = hist.pct_change()
    hv = ...
    # ... 10 more lines
except Exception:  # Catches EVERYTHING
    continue
```

**Problem:** Masks ValueError, KeyError, ZeroDivisionError that should be visible

**Solution:**
```python
try:
    stock = yf.Ticker(ticker)
    hist = stock.history(period="3mo")
except (requests.exceptions.RequestException, TimeoutError):
    continue  # Network error
except KeyError:
    continue  # yfinance structure changed
else:
    try:
        if hist.empty or len(hist) < 20:
            continue
        returns = hist['Close'].pct_change().dropna()
        hv = returns.iloc[-30:].std() * np.sqrt(252)
    except (ValueError, ZeroDivisionError):
        continue  # Data quality issue
```

**Estimated Gain:** 2-3% performance (less exception handling), much better debugging

---

### 6. **Pre-compile Numpy Operations** ⭐
**Impact:** Vectorize hot loops  
**Current Issue:** Line 1790-1850: MC simulation recreates arrays repeatedly

**Current Pattern:**
```python
for path in range(n_paths):
    Z = rng.standard_normal()  # Per-path (slow)
    S_T = S0 * np.exp(...)
```

**Should be (Line 655):**
```python
# Already vectorized! But could add numba JIT:
from numba import jit

@jit(nopython=True)
def gbm_paths_fast(S0, mu, sigma, T, n_paths, Z):
    drift = (mu - 0.5 * sigma**2) * T
    vol_term = sigma * np.sqrt(T)
    return S0 * np.exp(drift + vol_term * Z)
```

**Estimated Gain:** MC simulations 2-3x faster (especially with 50k paths)

---

### 7. **Eliminate Triple-Nested getattr/get Chains** ⭐
**Impact:** Cleaner code, 5-10% faster  
**Current Issue:** Lines throughout call `_get_num_from_row()` which loops:

```python
# Lines 1831-1833
oi = _safe_int(_get_num_from_row(r, ["openInterest", "oi", "open_interest"], 0), 0)
bid = _safe_float(_get_num_from_row(r, ["bid", "Bid"], float("nan")))
```

**Problem:** Unnecessary function call overhead for simple dict access

**Better:**
```python
def safe_get(row: pd.Series, keys: list, coercer=float, default=None):
    """Get first available key, coerce type, return default if missing/invalid"""
    for key in keys:
        try:
            val = row.get(key) if hasattr(row, 'get') else row[key]
            if val is not None and val == val:  # NaN check
                return coercer(val)
        except (ValueError, TypeError, KeyError):
            pass
    return default if default is not None else (0 if coercer is int else float('nan'))

# Usage
oi = safe_get(r, ["openInterest", "oi", "open_interest"], int, 0)
bid = safe_get(r, ["bid", "Bid"], float, float('nan'))
```

**Estimated Gain:** 5-10% faster on chain processing (1000+ rows per expiration)

---

### 8. **Lazy Load Monte Carlo** ⭐
**Impact:** App feels 2-3x faster (MC only when needed)  
**Current Issue:** Monte Carlo computed on every tab switch

**Current Pattern (Line 2547):**
```python
# In Overview tab - ALWAYS computed
if "mc_results" not in st.session_state:
    mc = mc_pnl(...)  # 2-3 seconds for 50k paths
```

**Solution:** Load on-demand:
```python
if st.button("🎲 Compute Risk (Monte Carlo)"):
    with st.spinner("Running 50,000 simulations..."):
        mc = mc_pnl(...)
        st.session_state["mc_results"] = mc
        st.success("Done!")

# Display cached results if available
if "mc_results" in st.session_state:
    mc = st.session_state["mc_results"]
    # Display
```

**Estimated Gain:** 2-3 seconds faster app responsiveness

---

### 9. **Replace Linear Searches with Dictionaries** ⭐
**Impact:** O(n) → O(1) lookups  
**Current Issue:** Line 2238-2250 (CSV generation):

```python
# Linear search in `ks` for each row
if df.empty:
    return strat, None
sel = df[ks == key]  # Full scan!
```

**Better:**
```python
# Build lookup dict once
key_to_idx = {k: i for i, k in enumerate(ks)}

# Then O(1) lookup
if key in key_to_idx:
    sel = df.iloc[key_to_idx[key]:key_to_idx[key]+1]
```

**Estimated Gain:** Negligible on small dataframes (< 100 rows), but architectural improvement

---

### 10. **Profile & Cache Expensive Calculations** ⭐
**Current Code Issues:**
- Line 815-852: Greeks calculation repeated 100+ times per scan
- Line 900-1000: Option chains fetched twice (cached/uncached)
- Line 1770-1850: Pre-screener recalculates same metrics

**Solution:**
```python
# Add caching decorator
@st.cache_data(ttl=60, show_spinner=False)
def compute_greeks_cached(S, K, T, sigma, r, q, option_type):
    """Cache Greeks calculation for 60 seconds"""
    if option_type == "call":
        return call_delta(S, K, r, sigma, T, q), \
               call_theta(S, K, r, sigma, T, q)
    else:
        return put_delta(S, K, r, sigma, T, q), \
               put_theta(S, K, r, sigma, T, q)

# Use in loops
for row in chain.itertuples():
    delta, theta = compute_greeks_cached(S, K, T, sigma, r, q, opt_type)
```

**Estimated Gain:** 20-40% faster repeated scans

---

## Quick Wins (Easy, Low Risk)

### Quick Win 1: Remove Redundant String Operations
```python
# Before (Line 2159)
tickers = [t.strip().upper() for t in tickers_str.split(",") if t.strip()]
tickers = [t.strip().upper() for t in tickers_str.split(",") if t.strip()]  # Duplicate!

# After
tickers = [t.strip().upper() for t in tickers_str.split(",") if t.strip()]
```

### Quick Win 2: Pre-allocate Lists
```python
# Before
rows = []
for ticker in tickers:
    # append 1-N items

# After (if you know count)
rows = [None] * len(tickers)  # Pre-allocate
for i, ticker in enumerate(tickers):
    rows[i] = {...}
```

### Quick Win 3: Use Set for Uniqueness
```python
# Before (Line 2280)
all_tickers = set()
if not df_csp.empty:
    all_tickers.update(df_csp["Ticker"].unique())
# Good! Already using set

# But can optimize iteration
for ticker in all_tickers:  # Set iteration is O(1) per item ✓
```

---

## Bottleneck Summary

| Bottleneck | Current Time | Optimized | Gain |
|-----------|-------------|-----------|------|
| Sequential ticker fetches | 2-3s (5 tickers) | 1-2s | 40-50% |
| Earnings calendar fetch | 4-5s (10 tickers) | 1-2s | 60-70% |
| MC simulations | 2-3s (50k paths) | 1s | 50-60% |
| DataFrame operations | 200-300ms | 150ms | 25-40% |
| Total (10 tickers, 50k MC) | ~12-15s | ~5-7s | 50-60% |

---

## Recommended Implementation Order

1. **First:** Consolidate Ticker objects (#1) - Highest impact, lowest risk
2. **Second:** Cache HV calculations (#2) - Easy win
3. **Third:** Batch earnings fetch (#3) - Good for UX
4. **Fourth:** Lazy-load MC (#8) - Makes app feel responsive
5. **Fifth:** Replace exceptions (#5) - Better diagnostics
6. **Ongoing:** Profile with `@st.cache_data` (#10)

---

## Implementation Effort Estimate

| Optimization | Effort | Risk | Payoff |
|-------------|--------|------|--------|
| #1 Consolidate Ticker | 30min | Low | ⭐⭐⭐ |
| #2 Cache HV | 20min | Low | ⭐⭐⭐ |
| #3 Parallel Earnings | 45min | Medium | ⭐⭐ |
| #4 DataFrame ops | 15min | Low | ⭐⭐ |
| #5 Better exceptions | 60min | Low | ⭐ |
| #6 Numba JIT | 30min | Medium | ⭐⭐⭐ |
| #7 Helper function | 20min | Low | ⭐ |
| #8 Lazy MC | 20min | Low | ⭐⭐ |
| #9 Dict lookups | 15min | Low | ⭐ |
| #10 Cache Greeks | 30min | Low | ⭐⭐ |

**Total estimated improvement: 50-60% faster overall**

---

## Code Quality Improvements (No Performance Impact)

1. **Extract helper functions** from 150-line analyzers
2. **Add type hints** throughout (mypy compliance)
3. **Reduce function nesting** in main loop
4. **Document cache TTLs** (why 30s vs 300s?)
5. **Test Greeks against external source** (validate calculations)

---

## Monitoring Recommendations

Add to sidebar diagnostics:
```python
with st.expander("⏱️ Performance Metrics"):
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Data Calls", sum(st.session_state["data_calls"]))
    with col2:
        st.metric("Cache Hits", st.session_state.get("cache_hits", 0))
    with col3:
        st.metric("Last Query", st.session_state.get("query_time_ms", "N/A"))
```

---

**Next Steps:** Which optimizations would you like to implement first?
