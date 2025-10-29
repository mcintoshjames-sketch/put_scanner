# providers/__init__.py — Provider factory and interface
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import List, Optional, Tuple
from datetime import date
import pandas as pd


class OptionsProvider(ABC):
    """Abstract base class for options data providers."""

    @abstractmethod
    def last_price(self, symbol: str) -> float:
        """Get the last trade price for a symbol."""
        pass

    @abstractmethod
    def expirations(self, symbol: str) -> List[str]:
        """Get list of expiration dates in YYYY-MM-DD format."""
        pass

    @abstractmethod
    def chain_snapshot_df(self, symbol: str, expiration: str) -> pd.DataFrame:
        """
        Get options chain for a specific expiration.
        
        Returns DataFrame with columns:
        - type: "put" or "call"
        - strike: strike price
        - bid, ask, lastPrice: prices
        - impliedVolatility: IV as decimal
        - openInterest: OI
        - mark: mid-point price
        """
        pass

    @abstractmethod
    def get_earnings_date(self, symbol: str) -> Optional[date]:
        """Get next earnings date (optional, may return None)."""
        pass

    @abstractmethod
    def get_technicals(self, symbol: str) -> Tuple[float, float, float]:
        """
        Get technical indicators.
        Returns: (sma200, year_low, year_high)
        """
        pass


def get_provider(provider_type: str | None = None) -> OptionsProvider:
    """
    Factory function to get the configured provider.
    
    Args:
        provider_type: "yfinance", "polygon", or "schwab"
                      If None, reads from config
    """
    if provider_type is None:
        from config import PROVIDER
        provider_type = PROVIDER

    provider_type = provider_type.lower()

    if provider_type == "yfinance":
        from providers.yfinance_provider import YFinanceProvider
        return YFinanceProvider()
    elif provider_type == "polygon":
        from providers.polygon_provider import PolygonProvider
        return PolygonProvider()
    elif provider_type == "schwab":
        from providers.schwab_provider import SchwabProvider
        return SchwabProvider()
    else:
        raise ValueError(
            f"Unknown provider: {provider_type}. "
            "Choose 'yfinance', 'polygon', or 'schwab'"
        )
