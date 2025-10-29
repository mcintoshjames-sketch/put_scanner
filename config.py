# config.py — Provider configuration
import os

# Provider selection: "yfinance", "polygon", or "schwab"
PROVIDER = os.environ.get("OPTIONS_PROVIDER", "yfinance").lower()

# Provider-specific settings
POLYGON_API_KEY = os.environ.get("POLYGON_API_KEY")
SCHWAB_API_KEY = os.environ.get("SCHWAB_API_KEY")
SCHWAB_APP_SECRET = os.environ.get("SCHWAB_APP_SECRET")
SCHWAB_CALLBACK_URL = os.environ.get("SCHWAB_CALLBACK_URL", "https://localhost")
SCHWAB_TOKEN_PATH = os.environ.get("SCHWAB_TOKEN_PATH", "./schwab_token.json")
