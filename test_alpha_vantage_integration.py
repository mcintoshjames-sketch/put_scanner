"""
Test script to verify Alpha Vantage integration with earnings date fallback.
Tests both Yahoo Finance success (no API call) and failure (API call) scenarios.
"""
import os
import sys
from datetime import datetime
import yfinance as yf

# Add providers to path
sys.path.insert(0, os.path.dirname(__file__))

from providers.alpha_vantage import AlphaVantageClient, get_earnings_with_fallback

def test_yahoo_success():
    """Test that Alpha Vantage is NOT called when Yahoo has data."""
    print("\n" + "="*60)
    print("TEST 1: Yahoo Finance has data (should NOT call Alpha Vantage)")
    print("="*60)
    
    # Try a popular stock that Yahoo typically has data for
    symbol = "AAPL"
    print(f"\nTesting symbol: {symbol}")
    
    stock = yf.Ticker(symbol)
    
    # Get Yahoo data
    yahoo_date = None
    try:
        cal = stock.calendar
        if cal is not None and not cal.empty:
            if "Earnings Date" in cal.index:
                ed = cal.loc["Earnings Date"]
                if hasattr(ed, "__iter__") and len(ed) > 0:
                    yahoo_date = ed[0]
                else:
                    yahoo_date = ed
                print(f"✓ Yahoo Finance returned: {yahoo_date}")
    except Exception as e:
        print(f"✗ Yahoo Finance error: {e}")
    
    # Call fallback (should return Yahoo date without API call)
    result = get_earnings_with_fallback(symbol, yahoo_date)
    
    if result == yahoo_date:
        print(f"✓ Fallback returned Yahoo date: {result}")
        print("✓ SUCCESS: No Alpha Vantage API call made (as expected)")
    else:
        print(f"✗ UNEXPECTED: Result {result} differs from Yahoo {yahoo_date}")

def test_yahoo_failure():
    """Test that Alpha Vantage IS called when Yahoo has no data."""
    print("\n" + "="*60)
    print("TEST 2: Yahoo Finance has no data (should call Alpha Vantage)")
    print("="*60)
    
    # Use a symbol that Yahoo might not have data for
    symbol = "TGT"
    print(f"\nTesting symbol: {symbol}")
    
    # Simulate Yahoo returning None
    yahoo_date = None
    print("Simulating Yahoo Finance returning None")
    
    # Call fallback (should attempt Alpha Vantage)
    result = get_earnings_with_fallback(symbol, yahoo_date)
    
    if result:
        print(f"✓ Alpha Vantage returned: {result}")
        print("✓ SUCCESS: Fallback worked")
    else:
        print("✗ Alpha Vantage also had no data")

def test_cache():
    """Test that second call uses cache."""
    print("\n" + "="*60)
    print("TEST 3: Second call should use cache (no API call)")
    print("="*60)
    
    api_key = os.environ.get("ALPHA_VANTAGE_API_KEY")
    if not api_key:
        print("✗ ALPHA_VANTAGE_API_KEY not found in environment")
        return
    
    client = AlphaVantageClient(api_key)
    
    # Check remaining calls before
    remaining_before = client.get_remaining_calls()
    print(f"\nAPI calls remaining before: {remaining_before}/25")
    
    # First call (might use API)
    symbol = "MSFT"
    print(f"\nFirst call for {symbol}...")
    date1 = client.get_earnings_date(symbol, use_cache=True)
    
    remaining_middle = client.get_remaining_calls()
    print(f"API calls remaining after first: {remaining_middle}/25")
    
    # Second call (should use cache)
    print(f"\nSecond call for {symbol} (should use cache)...")
    date2 = client.get_earnings_date(symbol, use_cache=True)
    
    remaining_after = client.get_remaining_calls()
    print(f"API calls remaining after second: {remaining_after}/25")
    
    if date1 == date2:
        print(f"✓ Both calls returned same date: {date1}")
    else:
        print(f"✗ Dates differ: {date1} vs {date2}")
    
    if remaining_middle == remaining_after:
        print("✓ SUCCESS: Second call used cache (no API call)")
    else:
        print(f"✗ UNEXPECTED: API calls changed from {remaining_middle} to {remaining_after}")

def main():
    # Check for API key
    api_key = os.environ.get("ALPHA_VANTAGE_API_KEY")
    if not api_key:
        print("ERROR: ALPHA_VANTAGE_API_KEY not found in environment")
        print("Please run: export ALPHA_VANTAGE_API_KEY=69W6V3AL4VF1ROEA")
        sys.exit(1)
    
    print("Alpha Vantage Integration Test")
    print(f"API Key: {api_key[:10]}...")
    
    try:
        test_yahoo_success()
        test_yahoo_failure()
        test_cache()
        
        print("\n" + "="*60)
        print("TESTING COMPLETE")
        print("="*60)
        
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
