# Portfolio Risk Management Testing Guide

## Test Suites

### 1. Unit Tests (Mock Data)
Fast tests using synthetic positions - no API required.

```bash
python test_portfolio.py
```

**What it tests:**
- Portfolio manager initialization
- Greeks aggregation logic
- Risk alert generation
- DataFrame formatting
- Singleton pattern
- Empty portfolio handling
- High-risk scenario detection

**Runtime:** < 5 seconds  
**Requirements:** None (no API needed)

---

### 2. Schwab Integration Tests
Real-world tests using live Schwab API and actual positions.

```bash
python test_schwab_integration.py
```

**What it tests:**
- Schwab API connectivity
- Real position retrieval
- Live market data integration
- Greeks calculation with real prices
- Data quality validation
- Portfolio metrics with actual positions

**Runtime:** 5-15 seconds (depends on API latency)  
**Requirements:**
- Valid Schwab API credentials in `config.py`
- Active Schwab account with positions
- Network connectivity

---

### 3. Quick Singleton Test
Minimal test to verify singleton pattern.

```bash
python test_singleton.py
```

**Runtime:** < 1 second

---

## Environment Variables

### For Schwab Integration Tests

```bash
# Require Schwab (fail if not available)
export REQUIRE_SCHWAB=true

# Minimum expected positions (fail if fewer)
export MIN_POSITIONS=5

# Run test
python test_schwab_integration.py
```

---

## Test Configuration

### Enable Schwab in Unit Tests

Edit `test_portfolio.py`:
```python
USE_MOCK_DATA = False  # Switch to real Schwab API
```

### Configure Schwab Provider

Edit `config.py`:
```python
PROVIDER = "schwab"  # Use Schwab as data provider
```

---

## Expected Test Output

### ✅ All Tests Passing

```
============================================================
Testing Portfolio Risk Management Phase 1.1
============================================================

1. Testing imports...
✅ portfolio_manager imports successful
✅ schwab_positions imports successful

2. Testing mock positions...
✅ Created 3 mock positions

3. Testing PortfolioManager...
✅ Loaded 3 positions

   Portfolio Metrics:
   - Total Delta: 100.90
   - Total Gamma: 0.0100
   - Total Vega: 0.25
   - Total Theta: -0.11
   ...

10. Testing high-risk scenarios...
✅ High-risk scenario generated 2 alerts

============================================================
✅ All Portfolio Risk Management tests passed!
============================================================
```

---

## Common Issues

### Issue: "cannot import name 'get_provider'"
**Solution:** Ensure `providers/` module exists and is properly configured

### Issue: "Schwab provider initialization failed"
**Solution:** 
1. Check Schwab credentials in `config.py`
2. Verify token is not expired: `python refresh_token.py`
3. Check network connectivity

### Issue: "No positions found in Schwab account"
**Solution:** This is normal if account is empty - tests will use mock data

### Issue: "Delta out of range" validation error
**Solution:** Check if option is very deep ITM/OTM, or if data is stale

---

## Continuous Integration

### GitHub Actions Example

```yaml
name: Portfolio Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.10'
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
      - name: Run unit tests
        run: python test_portfolio.py
      - name: Run Schwab integration tests
        run: python test_schwab_integration.py
        env:
          REQUIRE_SCHWAB: false  # Optional for CI
```

---

## Test Coverage

| Component | Unit Tests | Integration Tests |
|-----------|------------|-------------------|
| Position loading | ✅ | ✅ |
| Greeks calculation | ✅ | ✅ |
| Risk alerts | ✅ | ✅ |
| Portfolio metrics | ✅ | ✅ |
| Schwab API | ❌ | ✅ |
| Live market data | ❌ | ✅ |
| Data validation | ✅ | ✅ |
| Error handling | ✅ | ✅ |

---

## Performance Benchmarks

| Test Suite | Positions | Runtime | API Calls |
|------------|-----------|---------|-----------|
| Unit Tests | 3 (mock) | < 5s | 0 |
| Integration (empty) | 0 (real) | 5-10s | 1-2 |
| Integration (typical) | 10-20 (real) | 10-15s | 5-15 |
| Integration (large) | 50+ (real) | 15-30s | 20-50 |

---

## Next Steps After Testing

1. ✅ All tests pass → Ready for production
2. ⚠️  Some tests fail → Review logs and fix issues
3. 🔍 Data quality issues → Check Schwab API responses
4. 🚀 Deploy → Start Streamlit app: `streamlit run strategy_lab.py`

---

## Support

For issues with:
- **Unit tests**: Check `portfolio_manager.py` logic
- **Integration tests**: Verify Schwab API credentials and connectivity
- **Data quality**: Review `schwab_positions.py` parsing logic
- **Performance**: Check API rate limits and network latency
