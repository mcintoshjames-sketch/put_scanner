# providers/yfinance_provider.py — YFinance adapter implementing OptionsProvider interface
from __future__ import annotations
from typing import List, Optional, Tuple
from datetime import date
import pandas as pd
import yfinance as yf
from datetime import datetime
from providers import OptionsProvider


class YFinanceProvider(OptionsProvider):
    """YFinance provider for options data (default, free)."""

    def __init__(self):
        """Initialize YFinance provider."""
        pass

    def last_price(self, symbol: str) -> float:
        """Get the last trade price for a symbol."""
        stock = yf.Ticker(symbol)
        try:
            return float(stock.history(period="1d")["Close"].iloc[-1])
        except Exception as e:
            raise RuntimeError(f"Failed to get price for {symbol}: {e}")

    def expirations(self, symbol: str) -> List[str]:
        """Get list of expiration dates in YYYY-MM-DD format."""
        stock = yf.Ticker(symbol)
        try:
            expirations = list(stock.options or [])
            return expirations
        except Exception as e:
            raise RuntimeError(f"Failed to get expirations for {symbol}: {e}")

    def chain_snapshot_df(self, symbol: str, expiration: str) -> pd.DataFrame:
        """
        Get options chain for a specific expiration.
        Returns only puts for put scanner compatibility.
        """
        stock = yf.Ticker(symbol)
        try:
            opt_chain = stock.option_chain(expiration)
            df = opt_chain.puts
            
            # Normalize column names to match expected format
            if not df.empty:
                # Add type column
                df["type"] = "put"
                
                # Ensure we have the expected columns
                # YFinance already has: strike, bid, ask, lastPrice, impliedVolatility, openInterest
                
                # Calculate mark if not present
                if "mark" not in df.columns:
                    df["mark"] = (df["bid"] + df["ask"]) / 2.0
                    # Use last price if bid/ask not available
                    mask = df["mark"].isna() | (df["mark"] == 0)
                    df.loc[mask, "mark"] = df.loc[mask, "lastPrice"]
                
            return df
        except Exception as e:
            raise RuntimeError(f"Failed to get option chain for {symbol} on {expiration}: {e}")

    def get_earnings_date(self, symbol: str) -> Optional[date]:
        """Get next earnings date."""
        stock = yf.Ticker(symbol)
        try:
            cal = stock.calendar
            if cal is not None:
                # Handle different return types from yfinance
                if isinstance(cal, pd.DataFrame):
                    if not cal.empty:
                        if "Earnings Date" in cal.index:
                            ed = cal.loc["Earnings Date"]
                            if hasattr(ed, "__iter__"):
                                try:
                                    return pd.to_datetime(ed[0]).date()
                                except Exception:
                                    ts = pd.to_datetime(ed)
                                    return ts.date() if hasattr(ts, 'date') else None
                        if "Earnings Date" in cal.columns:
                            ed = cal["Earnings Date"].iloc[0]
                            if hasattr(ed, "__iter__"):
                                return pd.to_datetime(ed[0]).date()
                            return pd.to_datetime(ed).date()
                elif isinstance(cal, dict):
                    # Sometimes yfinance returns a dict
                    if "Earnings Date" in cal:
                        ed = cal["Earnings Date"]
                        if hasattr(ed, "__iter__") and not isinstance(ed, str):
                            return pd.to_datetime(ed[0]).date()
                        return pd.to_datetime(ed).date()
        except Exception:
            pass
        return None

    def get_technicals(self, symbol: str) -> Tuple[float, float, float]:
        """
        Get technical indicators: 200-DMA and 52-week low/high.
        Returns: (sma200, year_low, year_high)
        """
        stock = yf.Ticker(symbol)
        try:
            hist = stock.history(period="1y", auto_adjust=False)
            if hist.empty:
                return (float("nan"), float("nan"), float("nan"))
            close = hist["Close"]
            sma200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else float("nan")
            year_low = float(close.min())
            year_high = float(close.max())
            return (sma200, year_low, year_high)
        except Exception:
            return (float("nan"), float("nan"), float("nan"))
