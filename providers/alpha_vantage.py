# Alpha Vantage API for earnings data
# Used as fallback when Yahoo Finance doesn't have earnings dates
# API limit: 25 calls per day - use sparingly!

import os
import requests
from datetime import datetime, date
from typing import Optional, Dict
import json
from pathlib import Path


class AlphaVantageClient:
    """
    Alpha Vantage API client for earnings calendar data.
    
    IMPORTANT: API is rate-limited to 25 calls/day.
    Use only as fallback when Yahoo Finance data is unavailable.
    """
    
    def __init__(self, api_key: Optional[str] = None, cache_dir: str = "./earnings_cache"):
        """
        Initialize Alpha Vantage client.
        
        Args:
            api_key: Alpha Vantage API key (or use ALPHA_VANTAGE_API_KEY env var)
            cache_dir: Directory to cache earnings data to minimize API calls
        """
        self.api_key = api_key or os.environ.get("ALPHA_VANTAGE_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Alpha Vantage API key required. Set ALPHA_VANTAGE_API_KEY "
                "environment variable or pass api_key parameter."
            )
        
        self.base_url = "https://www.alphavantage.co/query"
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        
        # Track API calls to avoid hitting limit
        self.call_count_file = self.cache_dir / "api_call_count.json"
    
    def _load_call_count(self) -> Dict:
        """Load today's API call count from file."""
        if self.call_count_file.exists():
            try:
                with open(self.call_count_file, 'r') as f:
                    data = json.load(f)
                    # Reset count if it's a new day
                    if data.get('date') != str(date.today()):
                        return {'date': str(date.today()), 'count': 0}
                    return data
            except Exception:
                pass
        return {'date': str(date.today()), 'count': 0}
    
    def _save_call_count(self, count_data: Dict):
        """Save API call count to file."""
        try:
            with open(self.call_count_file, 'w') as f:
                json.dump(count_data, f)
        except Exception:
            pass
    
    def _increment_call_count(self) -> int:
        """Increment and return current API call count for today."""
        count_data = self._load_call_count()
        count_data['count'] += 1
        self._save_call_count(count_data)
        return count_data['count']
    
    def get_remaining_calls(self) -> int:
        """Get remaining API calls available today."""
        count_data = self._load_call_count()
        return max(0, 25 - count_data['count'])
    
    def _get_cache_path(self, symbol: str) -> Path:
        """Get cache file path for a symbol."""
        return self.cache_dir / f"{symbol.upper()}_earnings.json"
    
    def _load_from_cache(self, symbol: str) -> Optional[Dict]:
        """
        Load earnings data from cache if available and recent.
        Cache is valid for 24 hours.
        """
        cache_path = self._get_cache_path(symbol)
        if cache_path.exists():
            try:
                with open(cache_path, 'r') as f:
                    data = json.load(f)
                    # Check if cache is less than 24 hours old
                    cached_time = datetime.fromisoformat(data['cached_at'])
                    age_hours = (datetime.now() - cached_time).total_seconds() / 3600
                    if age_hours < 24:
                        return data
            except Exception:
                pass
        return None
    
    def _save_to_cache(self, symbol: str, data: Dict):
        """Save earnings data to cache."""
        cache_path = self._get_cache_path(symbol)
        try:
            cache_data = {
                'cached_at': datetime.now().isoformat(),
                'symbol': symbol.upper(),
                'data': data
            }
            with open(cache_path, 'w') as f:
                json.dump(cache_data, f, indent=2)
        except Exception:
            pass
    
    def get_earnings_date(self, symbol: str, use_cache: bool = True) -> Optional[date]:
        """
        Get next earnings date for a symbol.
        
        This method is designed to minimize API calls:
        1. Checks cache first (valid for 24 hours)
        2. Only calls API if cache miss and calls remaining
        3. Returns None if API limit reached
        
        Args:
            symbol: Stock ticker symbol
            use_cache: Whether to use cached data (default: True)
        
        Returns:
            Next earnings date or None if unavailable
        """
        symbol = symbol.upper()
        
        # Try cache first
        if use_cache:
            cached = self._load_from_cache(symbol)
            if cached is not None:
                # Cache hit - don't make API call
                earnings_date_str = cached.get('data', {}).get('earnings_date')
                if earnings_date_str and earnings_date_str != 'null':
                    print(f"💾 Using cached earnings date for {symbol}")
                    return datetime.strptime(earnings_date_str, '%Y-%m-%d').date()
                else:
                    # Cache says no earnings date (also a valid cache hit)
                    print(f"💾 Cache indicates no earnings date for {symbol}")
                    return None
        
        # Check if we have API calls remaining
        remaining = self.get_remaining_calls()
        if remaining <= 0:
            print(f"⚠️ Alpha Vantage API limit reached (25/day). Using cache only.")
            return None
        
        try:
            # Make API call
            params = {
                'function': 'EARNINGS_CALENDAR',
                'symbol': symbol,
                'apikey': self.api_key
            }
            
            response = requests.get(self.base_url, params=params, timeout=10)
            response.raise_for_status()
            
            # Increment call count
            call_count = self._increment_call_count()
            print(f"📊 Alpha Vantage API call {call_count}/25 for {symbol}")
            
            # Parse CSV response
            lines = response.text.strip().split('\n')
            if len(lines) < 2:
                # No data - cache this result too (as 'null')
                self._save_to_cache(symbol, {'earnings_date': 'null'})
                return None
            
            # Header: symbol,name,reportDate,fiscalDateEnding,estimate,currency
            # Find the first future earnings date
            today = date.today()
            for line in lines[1:]:  # Skip header
                try:
                    parts = line.split(',')
                    if len(parts) >= 3:
                        # Index 0: symbol, 1: name, 2: reportDate
                        report_date_str = parts[2].strip()
                        report_date = datetime.strptime(report_date_str, '%Y-%m-%d').date()
                        
                        if report_date >= today:
                            # Cache the result
                            self._save_to_cache(symbol, {'earnings_date': str(report_date)})
                            return report_date
                except Exception:
                    continue
            
            # No future earnings found, cache empty result
            self._save_to_cache(symbol, {'earnings_date': 'null'})
            return None
            
        except Exception as e:
            print(f"⚠️ Alpha Vantage error for {symbol}: {e}")
            return None


def get_earnings_with_fallback(symbol: str, yahoo_date: Optional[date] = None) -> Optional[date]:
    """
    Get earnings date with Yahoo Finance -> Alpha Vantage fallback.
    
    Only calls Alpha Vantage if Yahoo Finance returned None.
    This minimizes API usage.
    
    Args:
        symbol: Stock ticker
        yahoo_date: Earnings date from Yahoo Finance (or None if unavailable)
    
    Returns:
        Earnings date from Yahoo or Alpha Vantage, or None if unavailable
    """
    # If Yahoo has data, use it
    if yahoo_date is not None:
        return yahoo_date
    
    # Yahoo failed, try Alpha Vantage as fallback
    try:
        # Check if API key is configured
        api_key = os.environ.get("ALPHA_VANTAGE_API_KEY")
        if not api_key:
            return None
        
        client = AlphaVantageClient(api_key=api_key)
        
        # Only call if we have API calls remaining
        if client.get_remaining_calls() <= 0:
            return None
        
        return client.get_earnings_date(symbol, use_cache=True)
    
    except Exception:
        return None
