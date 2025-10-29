# Streamlit Community Cloud Deployment Guide

## Quick Deploy Steps

### 1. Push to GitHub
```bash
git add .
git commit -m "Prepare for Streamlit Community Cloud deployment"
git push origin main
```

### 2. Deploy on Streamlit Community Cloud

1. Go to [share.streamlit.io](https://share.streamlit.io)
2. Sign in with your GitHub account
3. Click **"New app"**
4. Fill in the deployment form:
   - **Repository:** `mcintoshjames-sketch/put_scanner`
   - **Branch:** `main`
   - **Main file path:** `strategy_lab.py`
5. Click **"Advanced settings"** (optional):
   - Python version: `3.11` (recommended)
6. Click **"Deploy!"**

### 3. Configure Secrets (Optional - for Polygon.io)

If you have a Polygon.io API key for better data quality:

1. Once deployed, click on your app settings (⚙️)
2. Select **"Secrets"** from the left sidebar
3. Add this content (replace with your actual key):
   ```toml
   POLYGON_API_KEY = "your_actual_polygon_api_key_here"
   ```
4. Click **"Save"**
5. Your app will automatically restart with the new secrets

**Note:** The app works perfectly fine without Polygon - it will use Yahoo Finance as a free fallback!

### 4. Share Your App

Your app will be live at: `https://[your-app-name].streamlit.app`

Share the link with anyone! 🚀

---

## Local Development

To run locally with secrets:

1. Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml`
2. Add your API keys to `.streamlit/secrets.toml`
3. Run: `streamlit run strategy_lab.py`

**Important:** Never commit `.streamlit/secrets.toml` to git!

---

## Troubleshooting

### Memory Issues (1 GB limit)
If you encounter memory errors with many tickers:
- Reduce the number of tickers scanned at once
- The app is optimized but 66 tickers may push limits
- Consider upgrading to paid tier for more resources

### App is slow to wake up
- Free tier apps sleep after 7 days of inactivity
- First request after sleep takes ~30 seconds to wake
- This is normal behavior for free tier

### Data quality issues
- Yahoo Finance data can be delayed or incomplete
- Add a Polygon.io API key in secrets for real-time data
- Free Polygon tier: 5 API calls/minute (sufficient for most scans)

---

## Features

✅ **Cash-Secured Puts** - Scan and rank CSP opportunities  
✅ **Covered Calls** - Find optimal CC positions  
✅ **Collars** - Analyze protective collar strategies  
✅ **Portfolio Builder** - Build multi-strategy portfolios  
✅ **Monte Carlo Risk** - Simulate position outcomes  
✅ **Parallel Processing** - Fast scans with ThreadPoolExecutor  
✅ **Advanced Filters** - ROI, OTM%, liquidity, spreads, and more  

---

## Tech Stack

- **Frontend:** Streamlit
- **Data:** Yahoo Finance (free) + Polygon.io (optional)
- **Analytics:** NumPy, Pandas, SciPy
- **Visualization:** Altair
- **Deployment:** Streamlit Community Cloud (free tier)

---

## License

Educational use only. Not financial advice. Always verify data and do your own research before trading.
