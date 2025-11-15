# providers/schwab_provider.py — Schwab API adapter implementing OptionsProvider interface
from __future__ import annotations
from typing import List, Optional, Tuple
from datetime import date
import pandas as pd
from providers import OptionsProvider
from providers.schwab import SchwabClient, SchwabError


class SchwabProvider(OptionsProvider):
    """Schwab API provider for options data."""

    def __init__(self):
        """Initialize Schwab provider using environment variables for credentials."""
        try:
            self.client = SchwabClient()
        except SchwabError as e:
            raise RuntimeError(f"Failed to initialize Schwab provider: {e}")

    def last_price(self, symbol: str) -> float:
        """Get the last trade price for a symbol."""
        return self.client.last_price(symbol)

    def expirations(self, symbol: str) -> List[str]:
        """Get list of expiration dates in YYYY-MM-DD format."""
        return self.client.expirations(symbol)

    def chain_snapshot_df(self, symbol: str, expiration: str) -> pd.DataFrame:
        """
        Get options chain for a specific expiration.
        Returns both calls and puts (changed to support Iron Condor and other multi-leg strategies).
        """
        df = self.client.chain_snapshot_df(symbol, expiration)
        # Return both calls and puts (removed puts-only filter for Iron Condor support)
        return df

    def get_earnings_date(self, symbol: str) -> Optional[date]:
        """
        Schwab API doesn't provide earnings dates directly.
        Return None - caller should handle gracefully.
        """
        return None

    def get_technicals(self, symbol: str) -> Tuple[float, float, float]:
        """
        Schwab API doesn't provide historical data for technicals in the basic API.
        Return NaN values - caller should handle gracefully.
        
        For full implementation, you'd need to:
        1. Fetch historical price data via get_price_history()
        2. Calculate 200-day SMA
        3. Calculate 52-week high/low
        
        Returns: (sma200, year_low, year_high)
        """
        import math
        return (float("nan"), float("nan"), float("nan"))

    # Token management methods (delegate to underlying client)
    def get_token_info(self):
        """Get token status information from underlying Schwab client."""
        return self.client.get_token_info()

    def refresh_token(self):
        """Refresh the Schwab API token."""
        return self.client.refresh_token()

    def build_authorization_url(self, callback_url: str | None = None) -> str:
        """Generate the Schwab OAuth authorization URL."""
        return self.client.build_authorization_url(callback_url)

    def complete_manual_oauth(
        self,
        redirect_url: str,
        callback_url: str | None = None,
    ):
        """Exchange a redirect URL for fresh tokens via Schwab OAuth."""
        return self.client.complete_manual_oauth(
            redirect_url, callback_url
        )

    def reset_token_file(self):
        """Backup and remove the current token file to force re-authentication."""
        return self.client.reset_token_file()

    def build_authorization_url(self, callback_override: str | None = None) -> str:
        """Expose OAuth authorization URL builder for UI helpers."""
        return self.client.build_authorization_url(callback_override)

    def complete_manual_oauth(self, redirect_url: str, callback_override: str | None = None):
        """Run a manual OAuth exchange from a pasted redirect URL."""
        return self.client.complete_manual_oauth(redirect_url, callback_override)

    def reset_token_file(self):
        """Backup/remove the token file so a fresh OAuth run can occur."""
        return self.client.reset_token_file()
