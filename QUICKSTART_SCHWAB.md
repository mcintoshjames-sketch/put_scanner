# Quick Start: Schwab API Integration

## TL;DR

Your put scanner now supports three data providers:
- **YFinance** (default, free, no setup)
- **Schwab API** (real-time, requires account)  ← NEW!
- **Polygon.io** (excellent data, paid)

## Using Schwab API in 3 Steps

### 1. Get Credentials
- Sign up: https://developer.schwab.com/
- Create app → Get API Key & App Secret

### 2. Set Environment Variables
```bash
export OPTIONS_PROVIDER=schwab
export SCHWAB_API_KEY=your_key
export SCHWAB_APP_SECRET=your_secret
```

### 3. Run (First Time = OAuth Login)
```bash
# Test it
python test_providers.py

# Use it
python app.py --tickers AAPL,MSFT
streamlit run streamlit_app.py
```

## Keep Using YFinance (No Change)

Nothing changes! YFinance is still the default:
```bash
python app.py --tickers AAPL,MSFT
streamlit run streamlit_app.py
```

## Files You Care About

- **SCHWAB_SETUP.md** - Full setup guide
- **SCHWAB_INTEGRATION.md** - Technical details
- **test_providers.py** - Test your setup
- **.env.example** - Configuration template

## What Changed

✅ Backward compatible - existing code works unchanged
✅ New provider pattern - easy to switch data sources
✅ Schwab API fully integrated
✅ All tests passing

## Need Help?

1. Read: **SCHWAB_SETUP.md**
2. Test: `python test_providers.py`
3. Issues: Check troubleshooting in SCHWAB_SETUP.md

That's it! 🚀
