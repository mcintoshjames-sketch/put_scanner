# Schwab API Integration Summary

## What Was Done

I've successfully integrated the Schwab API into your put scanner using the `schwab-py` library. The integration uses a **provider pattern** that allows you to easily switch between different data sources (YFinance, Schwab, or Polygon) without changing your main code.

## Files Created/Modified

### New Files

1. **`providers/schwab.py`** - Low-level Schwab API client
   - Handles authentication (OAuth 2.0)
   - Makes API calls to Schwab
   - Parses responses into standardized format

2. **`providers/schwab_provider.py`** - Schwab provider wrapper
   - Implements the `OptionsProvider` interface
   - Adapts Schwab API to scanner's expected format
   - Note: Schwab doesn't provide earnings dates or full historical data in basic API

3. **`providers/yfinance_provider.py`** - YFinance provider wrapper
   - Maintains backward compatibility
   - Wraps existing yfinance functionality in the provider interface

4. **`config.py`** - Configuration file
   - Centralized provider selection
   - Environment variable management

5. **`SCHWAB_SETUP.md`** - Complete setup guide
   - Step-by-step OAuth setup instructions
   - Environment variable configuration
   - Troubleshooting tips
   - Provider comparison table

6. **`test_providers.py`** - Test script
   - Validates Schwab API integration
   - Tests all provider methods
   - Provides helpful diagnostics

### Modified Files

1. **`providers/__init__.py`**
   - Added `OptionsProvider` abstract base class
   - Added `get_provider()` factory function
   - Enables easy provider switching

2. **`app.py`**
   - Removed direct `yfinance` dependency
   - Now uses provider interface
   - Added `provider` parameter to `analyze_puts()`
   - More flexible and testable

3. **`requirements.txt`**
   - Added `schwab-py>=1.3.0`

## How to Use

### Quick Start with Schwab API

1. **Get Schwab API Credentials**
   ```bash
   # Sign up at https://developer.schwab.com/
   # Create an app to get:
   # - API Key (Client ID)
   # - App Secret (Client Secret)
   ```

2. **Set Environment Variables**
   ```bash
   export OPTIONS_PROVIDER=schwab
   export SCHWAB_API_KEY=your_api_key_here
   export SCHWAB_APP_SECRET=your_app_secret_here
   export SCHWAB_CALLBACK_URL=https://localhost
   export SCHWAB_TOKEN_PATH=./schwab_token.json
   ```

3. **First Run (OAuth Authentication)**
   ```bash
   python test_providers.py
   ```
   - Browser will open for Schwab login
   - Authorize the application
   - Copy redirect URL back to terminal
   - Token saved for future use

4. **Run the Scanner**
   ```bash
   # Command line
   python app.py --tickers AAPL,MSFT,NVDA
   
   # Streamlit app
   streamlit run strategy_lab.py
   ```

### Keep Using YFinance (Default)

No changes needed! The scanner defaults to YFinance:

```bash
# Explicitly set (or just don't set OPTIONS_PROVIDER)
export OPTIONS_PROVIDER=yfinance

python app.py --tickers AAPL,MSFT,NVDA
```

### Streamlit Cloud Deployment

1. Go to your Streamlit Cloud app settings
2. Add secrets:
   ```toml
   OPTIONS_PROVIDER = "schwab"
   SCHWAB_API_KEY = "your_key"
   SCHWAB_APP_SECRET = "your_secret"
   SCHWAB_CALLBACK_URL = "https://localhost"
   ```

3. **Important**: For OAuth in cloud environments, you'll need to:
   - Do initial authentication locally
   - Upload `schwab_token.json` securely, or
   - Use Streamlit secrets to store token data

## Architecture

### Provider Pattern

```
OptionsProvider (Abstract Base Class)
├── last_price(symbol) -> float
├── expirations(symbol) -> List[str]
├── chain_snapshot_df(symbol, exp) -> DataFrame
├── get_earnings_date(symbol) -> date|None
└── get_technicals(symbol) -> (sma200, low, high)

Implementations:
├── YFinanceProvider (free, 15-min delay)
├── SchwabProvider (real-time, requires account)
└── PolygonProvider (excellent data, paid plans)
```

### Data Flow

```
strategy_lab.py
   ↓
app.py::analyze_puts()
   ↓
get_provider(provider_type)
   ↓
├→ YFinanceProvider → yfinance library
├→ SchwabProvider → schwab-py → Schwab API
└→ PolygonProvider → Polygon API
```

## Key Differences: YFinance vs Schwab

| Feature | YFinance | Schwab API |
|---------|----------|------------|
| **Cost** | Free | Free (with account) |
| **Data Delay** | 15 minutes | Real-time |
| **Rate Limits** | Soft limits | 120 req/min |
| **Authentication** | None | OAuth 2.0 |
| **Data Quality** | Good | Excellent |
| **Greeks** | Limited | Full (delta, gamma, theta, vega) |
| **Historical Data** | Full | Limited in basic API |
| **Earnings Dates** | Yes | No* |
| **Setup Complexity** | None | Medium |

*Schwab API doesn't provide earnings dates directly. Scanner will skip earnings filtering when using Schwab.

## Testing

Run the test script to verify your setup:

```bash
# Test Schwab provider
export OPTIONS_PROVIDER=schwab
python test_providers.py

# Test YFinance provider
export OPTIONS_PROVIDER=yfinance
python test_providers.py
```

## Troubleshooting

### "Missing Schwab credentials"
- Verify environment variables are set correctly
- Check for typos in variable names

### "Failed to authenticate"
- Ensure callback URL matches developer portal
- Check API key and secret are correct
- Delete `schwab_token.json` and re-authenticate

### "Token expired"
- schwab-py should auto-refresh, but if not:
- Delete `schwab_token.json`
- Re-run authentication

### "No earnings date warnings"
- Expected with Schwab API
- Earnings filtering will be skipped
- Consider using a separate earnings calendar API if needed

### "Rate limit exceeded"
- Schwab: 120 requests/minute
- Reduce number of tickers
- Add delays between scans

## Security Best Practices

1. **Never commit credentials to git**
   ```bash
   echo "schwab_token.json" >> .gitignore
   echo ".env" >> .gitignore
   ```

2. **Use environment variables**
   - Not hardcoded in files
   - Different values per environment

3. **Protect your token file**
   ```bash
   chmod 600 schwab_token.json
   ```

4. **Rotate credentials regularly**
   - Regenerate API keys periodically
   - Revoke old keys in developer portal

## Next Steps

1. **Read SCHWAB_SETUP.md** for detailed setup instructions
2. **Run test_providers.py** to validate your setup
3. **Update your deployment** with new environment variables
4. **Monitor rate limits** when scanning many tickers
5. **Consider caching** to reduce API calls

## Support Resources

- **schwab-py documentation**: https://github.com/alexgolec/schwab-py
- **Schwab Developer Portal**: https://developer.schwab.com/
- **Schwab API docs**: https://developer.schwab.com/products/trader-api--individual

## Future Enhancements

Potential improvements for the Schwab integration:

1. **Historical Data**: Implement `get_technicals()` using Schwab's price history endpoint
2. **Earnings Dates**: Integrate third-party earnings calendar API
3. **Caching Layer**: Reduce API calls by caching recent data
4. **Batch Requests**: Optimize multiple ticker scans
5. **Error Recovery**: Better handling of rate limits and transient errors
6. **Token Management**: Automated token refresh and storage

## Migration Checklist

- [x] Create Schwab API client
- [x] Implement provider interface
- [x] Update app.py to use providers
- [x] Add configuration management
- [x] Create setup documentation
- [x] Add test script
- [x] Update requirements.txt
- [ ] Test OAuth flow
- [ ] Test with real Schwab credentials
- [ ] Deploy to Streamlit Cloud
- [ ] Monitor API usage and performance
