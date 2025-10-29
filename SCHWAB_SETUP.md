# Switching to Schwab API

This guide explains how to switch your put scanner from YFinance to the Schwab API using `schwab-py`.

## Prerequisites

1. **Schwab Developer Account**: Sign up at [Schwab Developer Portal](https://developer.schwab.com/)
2. **Create an App**: Register a new application to get:
   - API Key (Client ID)
   - App Secret (Client Secret)
   - Set callback URL (e.g., `https://localhost`)

## Installation

The required dependency `schwab-py` is already in `requirements.txt`. Install it:

```bash
pip install -r requirements.txt
```

## Configuration

### Option 1: Environment Variables (Recommended for Production)

Set these environment variables:

```bash
export OPTIONS_PROVIDER=schwab
export SCHWAB_API_KEY=your_api_key_here
export SCHWAB_APP_SECRET=your_app_secret_here
export SCHWAB_CALLBACK_URL=https://localhost
export SCHWAB_TOKEN_PATH=./schwab_token.json
```

For Streamlit Cloud, add these as secrets in your app settings.

### Option 2: Local Development

Create a `.env` file in the project root:

```bash
OPTIONS_PROVIDER=schwab
SCHWAB_API_KEY=your_api_key_here
SCHWAB_APP_SECRET=your_app_secret_here
SCHWAB_CALLBACK_URL=https://localhost
SCHWAB_TOKEN_PATH=./schwab_token.json
```

Then load it in your code:

```python
from dotenv import load_dotenv
load_dotenv()
```

## First-Time OAuth Setup

The first time you run with Schwab API, you'll need to complete OAuth authentication:

1. Run your application
2. schwab-py will open a browser window for Schwab login
3. Log in to your Schwab account
4. Authorize the application
5. You'll be redirected to your callback URL with an authorization code
6. Copy the full redirect URL and paste it back into the terminal
7. A token file will be saved at `SCHWAB_TOKEN_PATH` (default: `./schwab_token.json`)

**Important**: Keep your token file secure and add it to `.gitignore`!

```bash
echo "schwab_token.json" >> .gitignore
```

## Token Refresh

The schwab-py library automatically handles token refresh. Your access token will be refreshed when needed without requiring re-authentication.

## Running the Application

### Command Line

```bash
# Make sure environment variables are set
export OPTIONS_PROVIDER=schwab
export SCHWAB_API_KEY=your_key
export SCHWAB_APP_SECRET=your_secret

# Run the scanner
python app.py --tickers AAPL,MSFT,NVDA
```

### Streamlit App

```bash
# Set environment variables first
export OPTIONS_PROVIDER=schwab
export SCHWAB_API_KEY=your_key
export SCHWAB_APP_SECRET=your_secret

# Run Streamlit
streamlit run streamlit_app.py
```

## Switching Back to YFinance

To switch back to free YFinance data:

```bash
export OPTIONS_PROVIDER=yfinance
```

Or simply unset the variable (yfinance is the default):

```bash
unset OPTIONS_PROVIDER
```

## Provider Comparison

| Feature | YFinance | Schwab API |
|---------|----------|------------|
| Cost | Free | Free (with account) |
| Rate Limits | Soft limits | 120 requests/minute |
| Data Quality | Good | Excellent |
| Real-time | 15-min delay | Real-time |
| Options Chains | Yes | Yes |
| Greeks | Limited | Full |
| Historical Data | Yes | Yes |
| Earnings Dates | Yes | No* |
| Authentication | None | OAuth 2.0 |

*Note: Schwab API doesn't provide earnings dates directly. The scanner will skip earnings filtering when using Schwab.

## Streamlit Cloud Deployment

Since Streamlit apps can't handle OAuth callbacks directly, use this approach:

### Step 1: Set Callback URL in Schwab Developer Portal

```
Callback URL: https://localhost
```

### Step 2: Authenticate Locally

```bash
# On your local machine
export OPTIONS_PROVIDER=schwab
export SCHWAB_API_KEY="your_app_key"
export SCHWAB_APP_SECRET="your_secret"
export SCHWAB_CALLBACK_URL="https://localhost"

# Authenticate (creates schwab_token.json)
python test_providers.py
```

### Step 3: Export Token for Streamlit

```bash
# Generate Streamlit secrets format
python export_token_for_streamlit.py
```

This will output something like:

```toml
[SCHWAB_TOKEN]
access_token = "your_access_token"
refresh_token = "your_refresh_token"
token_type = "Bearer"
expires_in = 1800
expires_at = 1234567890.123
```

### Step 4: Add to Streamlit Cloud Secrets

1. Go to your Streamlit app: https://putscanner-htcyyzfgrd4mj3qgj3uzbr1.streamlit.app/
2. Click Settings → Secrets
3. Add all credentials:

```toml
OPTIONS_PROVIDER = "schwab"
SCHWAB_API_KEY = "your_app_key"
SCHWAB_APP_SECRET = "your_secret"
SCHWAB_CALLBACK_URL = "https://localhost"

[SCHWAB_TOKEN]
access_token = "your_access_token_here"
refresh_token = "your_refresh_token_here"
token_type = "Bearer"
expires_in = 1800
expires_at = 1234567890.123
```

4. Save and restart your app

### Token Refresh

The refresh token is valid for 7 days. The app will automatically refresh your access token. If the refresh token expires, repeat steps 2-4.

## Troubleshooting

### "Failed to authenticate"

- Verify your API key and secret are correct
- Check that your callback URL matches what's registered in the developer portal
- Ensure the token file path is writable

### "Token expired"

- Delete `schwab_token.json` and re-authenticate
- Check that your app is still active in the Schwab developer portal

### "Rate limit exceeded"

- Schwab allows 120 requests per minute
- Reduce the number of tickers scanned at once
- Add delays between requests if needed

### "No earnings date" warnings

- This is expected with Schwab API
- Earnings date filtering will be skipped
- Consider using a third-party earnings calendar API if needed

## Advanced: Using Polygon.io

The scanner also supports Polygon.io as a data provider:

```bash
export OPTIONS_PROVIDER=polygon
export POLYGON_API_KEY=your_polygon_key
```

Polygon offers excellent data quality with generous rate limits on paid plans.

## Code Structure

The scanner uses a provider pattern for flexibility:

```
providers/
├── __init__.py           # Provider factory
├── yfinance_provider.py  # YFinance wrapper
├── schwab.py             # Schwab API client
├── schwab_provider.py    # Schwab wrapper
└── polygon.py            # Polygon API client
```

To add a new provider, implement the `OptionsProvider` interface in `providers/__init__.py`.

## Support

For issues with:
- **schwab-py library**: Visit [schwab-py GitHub](https://github.com/alexgolec/schwab-py)
- **Schwab API**: Check [Schwab Developer docs](https://developer.schwab.com/products/trader-api--individual)
- **This scanner**: Open an issue in this repository
