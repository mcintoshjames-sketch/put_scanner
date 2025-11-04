# Schwab API adapter for Strategy Lab
# Uses schwab-py library for authentication and API access

from __future__ import annotations
import os
import pandas as pd
from typing import List, Optional
from datetime import datetime, date
import schwab
from schwab import auth, client


class SchwabError(Exception):
    pass


class SchwabClient:
    """
    Wrapper for Schwab API using schwab-py library.
    Provides:
      - last trade price (equity)
      - expirations (option chain dates)
      - chain snapshots (calls+puts) with greeks/IV/OI
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        app_secret: Optional[str] = None,
        callback_url: Optional[str] = None,
        token_path: Optional[str] = None,
    ):
        """
        Initialize Schwab client.
        
        Args:
            api_key: Schwab API key (or use SCHWAB_API_KEY env var)
            app_secret: Schwab app secret (or use SCHWAB_APP_SECRET env var)
            callback_url: OAuth callback URL (or use SCHWAB_CALLBACK_URL env var)
            token_path: Path to store tokens (default: ./schwab_token.json)
        """
        self.api_key = api_key or os.environ.get("SCHWAB_API_KEY")
        self.app_secret = app_secret or os.environ.get("SCHWAB_APP_SECRET")
        self.callback_url = callback_url or os.environ.get(
            "SCHWAB_CALLBACK_URL", "https://127.0.0.1"
        )
        self.token_path = token_path or os.environ.get(
            "SCHWAB_TOKEN_PATH", "./schwab_token.json"
        )

        if not self.api_key or not self.app_secret:
            raise SchwabError(
                "Missing Schwab credentials. Set SCHWAB_API_KEY and SCHWAB_APP_SECRET "
                "environment variables or pass them to constructor."
            )

        try:
            # Authenticate and create client
            self.client = self._get_authenticated_client()
        except Exception as e:
            raise SchwabError(f"Failed to authenticate with Schwab API: {e}")

    def _get_authenticated_client(self) -> client.Client:
        """Get authenticated Schwab client using token or OAuth flow."""
        try:
            # Try Streamlit secrets first (for Streamlit Cloud deployment)
            try:
                import streamlit as st
                if hasattr(st, 'secrets') and "SCHWAB_TOKEN" in st.secrets:
                    from providers.schwab_streamlit import get_schwab_client_from_streamlit_secrets
                    return get_schwab_client_from_streamlit_secrets()
            except (ImportError, Exception):
                pass  # Not in Streamlit environment or secrets not configured
            
            # Try to use existing token file
            if os.path.exists(self.token_path):
                c = auth.client_from_token_file(
                    self.token_path, self.api_key, self.app_secret
                )
            else:
                # Need to do OAuth flow
                c = auth.client_from_manual_flow(
                    self.api_key, self.app_secret, self.callback_url, self.token_path
                )
            return c
        except Exception as e:
            raise SchwabError(f"Authentication failed: {e}")

    # ---------- Public methods used by Strategy Lab ----------

    def last_price(self, symbol: str) -> float:
        """
        Return the last trade price for the given symbol.
        Falls back to previous close if last trade unavailable.
        """
        try:
            response = self.client.get_quote(symbol.upper())
            response.raise_for_status()
            data = response.json()
            
            # Schwab quote response structure
            quote_data = data.get(symbol.upper(), {})
            if not quote_data:
                raise SchwabError(f"No quote data for {symbol}")
            
            # Try quote.lastPrice (most recent trade)
            quote = quote_data.get("quote", {})
            last = quote.get("lastPrice")
            if last is not None and last > 0:
                return float(last)
            
            # Fall back to quote.closePrice
            close = quote.get("closePrice")
            if close is not None and close > 0:
                return float(close)
            
            # Try regular market price
            regular = quote_data.get("regular", {})
            regular_last = regular.get("regularMarketLastPrice")
            if regular_last is not None and regular_last > 0:
                return float(regular_last)
            
            # Try extended hours
            extended = quote_data.get("extended", {})
            ext_last = extended.get("lastPrice")
            if ext_last is not None and ext_last > 0:
                return float(ext_last)
            
            raise SchwabError(f"No price data available for {symbol}")
        except Exception as e:
            raise SchwabError(f"Failed to get price for {symbol}: {e}")

    def expirations(self, symbol: str) -> List[str]:
        """
        List option expiration dates for the underlying symbol.
        Returns dates in YYYY-MM-DD format.
        """
        try:
            response = self.client.get_option_chain(
                symbol.upper(),
                contract_type=client.Client.Options.ContractType.ALL,
            )
            response.raise_for_status()
            data = response.json()
            
            expirations = set()
            
            # Extract expirations from callExpDateMap and putExpDateMap
            call_map = data.get("callExpDateMap", {})
            put_map = data.get("putExpDateMap", {})
            
            for exp_date in call_map.keys():
                # Format: "2025-01-17:30" -> extract date part
                date_str = exp_date.split(":")[0]
                expirations.add(date_str)
            
            for exp_date in put_map.keys():
                date_str = exp_date.split(":")[0]
                expirations.add(date_str)
            
            return sorted(list(expirations))
        except Exception as e:
            raise SchwabError(f"Failed to get expirations for {symbol}: {e}")

    def chain_snapshot_df(self, symbol: str, expiration: str) -> pd.DataFrame:
        """
        Return a DataFrame for puts at the given expiration.
        
        Returns DataFrame with columns matching the expected format:
        - type: "put" or "call"
        - strike: strike price
        - bid: bid price
        - ask: ask price
        - lastPrice: last trade price
        - impliedVolatility: IV as decimal (e.g., 0.25 for 25%)
        - openInterest: open interest
        - mark: mid-point between bid/ask
        - delta, gamma, theta, vega: greeks
        - volume: daily volume
        """
        try:
            response = self.client.get_option_chain(
                symbol.upper(),
                contract_type=client.Client.Options.ContractType.ALL,
                from_date=datetime.strptime(expiration, "%Y-%m-%d"),
                to_date=datetime.strptime(expiration, "%Y-%m-%d"),
            )
            response.raise_for_status()
            data = response.json()
            
            rows = []
            
            # Process puts
            put_map = data.get("putExpDateMap", {})
            for exp_key, strike_map in put_map.items():
                exp_date = exp_key.split(":")[0]
                if exp_date != expiration:
                    continue
                    
                for strike_key, contracts in strike_map.items():
                    for contract in contracts:
                        rows.append(self._parse_contract(contract, "put", symbol))
            
            # Process calls
            call_map = data.get("callExpDateMap", {})
            for exp_key, strike_map in call_map.items():
                exp_date = exp_key.split(":")[0]
                if exp_date != expiration:
                    continue
                    
                for strike_key, contracts in strike_map.items():
                    for contract in contracts:
                        rows.append(self._parse_contract(contract, "call", symbol))
            
            df = pd.DataFrame(rows)
            
            # Normalize types
            if not df.empty:
                df["type"] = df["type"].astype(str).str.lower()
                
                # Calculate mark if not present
                if "mark" in df.columns:
                    mask = df["mark"].isna()
                    df.loc[mask, "mark"] = (df.loc[mask, "bid"] + df.loc[mask, "ask"]) / 2.0
            
            return df
        except Exception as e:
            raise SchwabError(f"Failed to get option chain for {symbol} on {expiration}: {e}")

    def _parse_contract(self, contract: dict, contract_type: str, symbol: str) -> dict:
        """Parse a single contract from Schwab API response."""
        bid = contract.get("bid", 0.0)
        ask = contract.get("ask", 0.0)
        last = contract.get("last", 0.0)
        
        # Calculate mark
        mark = None
        if bid and ask and bid > 0 and ask > 0:
            mark = (bid + ask) / 2.0
        elif last and last > 0:
            mark = last
        
        return {
            "symbol": symbol,
            "type": contract_type,
            "expiration": contract.get("expirationDate", "")[:10],
            "strike": float(contract.get("strikePrice", 0.0)),
            "bid": float(bid) if bid else 0.0,
            "ask": float(ask) if ask else 0.0,
            "last": float(last) if last else 0.0,
            "lastPrice": float(last) if last else 0.0,
            "openInterest": int(contract.get("openInterest", 0)),
            "impliedVolatility": float(contract.get("volatility", 0.0)) / 100.0,  # Convert from % to decimal
            "delta": float(contract.get("delta", 0.0)),
            "gamma": float(contract.get("gamma", 0.0)),
            "theta": float(contract.get("theta", 0.0)),
            "vega": float(contract.get("vega", 0.0)),
            "volume": int(contract.get("totalVolume", 0)),
            "mark": mark,
        }
