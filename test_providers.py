#!/usr/bin/env python3
"""
Test script to verify Schwab API integration.
Make sure you have set the required environment variables before running:

export OPTIONS_PROVIDER=schwab
export SCHWAB_API_KEY=your_key
export SCHWAB_APP_SECRET=your_secret
export SCHWAB_CALLBACK_URL=https://localhost
export SCHWAB_TOKEN_PATH=./schwab_token.json
"""

import os
import sys

def test_schwab_provider():
    """Test Schwab provider initialization and basic operations."""
    print("=" * 60)
    print("Testing Schwab API Integration")
    print("=" * 60)
    
    # Check environment variables
    print("\n1. Checking environment variables...")
    required_vars = ["SCHWAB_API_KEY", "SCHWAB_APP_SECRET"]
    missing = []
    for var in required_vars:
        value = os.environ.get(var)
        if value:
            print(f"   ✓ {var}: {'*' * 10} (set)")
        else:
            print(f"   ✗ {var}: Not set")
            missing.append(var)
    
    if missing:
        print(f"\n❌ Missing required environment variables: {', '.join(missing)}")
        print("\nPlease set them and try again:")
        print("  export SCHWAB_API_KEY=your_key")
        print("  export SCHWAB_APP_SECRET=your_secret")
        return False
    
    # Try to import and initialize provider
    print("\n2. Importing provider...")
    try:
        from providers import get_provider
        print("   ✓ Provider module imported successfully")
    except ImportError as e:
        print(f"   ✗ Failed to import provider: {e}")
        return False
    
    # Initialize Schwab provider
    print("\n3. Initializing Schwab provider...")
    print("   (This may open a browser for OAuth authentication on first run)")
    try:
        provider = get_provider("schwab")
        print("   ✓ Schwab provider initialized successfully")
    except Exception as e:
        print(f"   ✗ Failed to initialize Schwab provider: {e}")
        return False
    
    # Test getting a stock price
    print("\n4. Testing last_price() for AAPL...")
    try:
        price = provider.last_price("AAPL")
        print(f"   ✓ AAPL price: ${price:.2f}")
    except Exception as e:
        print(f"   ✗ Failed to get price: {e}")
        return False
    
    # Test getting expirations
    print("\n5. Testing expirations() for AAPL...")
    try:
        expirations = provider.expirations("AAPL")
        if expirations:
            print(f"   ✓ Found {len(expirations)} expirations")
            print(f"   First 5: {expirations[:5]}")
        else:
            print("   ⚠ No expirations found (this might be expected)")
    except Exception as e:
        print(f"   ✗ Failed to get expirations: {e}")
        return False
    
    # Test getting option chain
    if expirations:
        print(f"\n6. Testing chain_snapshot_df() for AAPL {expirations[0]}...")
        try:
            df = provider.chain_snapshot_df("AAPL", expirations[0])
            print(f"   ✓ Got option chain with {len(df)} contracts")
            if not df.empty:
                print(f"   Columns: {list(df.columns)}")
                print(f"\n   Sample data (first 3 rows):")
                print(df.head(3).to_string(index=False))
        except Exception as e:
            print(f"   ✗ Failed to get option chain: {e}")
            return False
    
    print("\n" + "=" * 60)
    print("✓ All tests passed!")
    print("=" * 60)
    print("\nYour Schwab API integration is working correctly.")
    print("You can now run the put scanner with:")
    print("  export OPTIONS_PROVIDER=schwab")
    print("  python app.py --tickers AAPL,MSFT")
    print("  # or")
    print("  streamlit run streamlit_app.py")
    return True


def test_yfinance_provider():
    """Test that YFinance provider still works (for comparison)."""
    print("\n" + "=" * 60)
    print("Testing YFinance Provider (for comparison)")
    print("=" * 60)
    
    try:
        from providers import get_provider
        provider = get_provider("yfinance")
        
        print("\n1. Testing last_price() for AAPL...")
        price = provider.last_price("AAPL")
        print(f"   ✓ AAPL price: ${price:.2f}")
        
        print("\n2. Testing expirations() for AAPL...")
        expirations = provider.expirations("AAPL")
        print(f"   ✓ Found {len(expirations)} expirations")
        
        if expirations:
            print(f"\n3. Testing chain_snapshot_df() for AAPL {expirations[0]}...")
            df = provider.chain_snapshot_df("AAPL", expirations[0])
            print(f"   ✓ Got option chain with {len(df)} contracts")
        
        print("\n✓ YFinance provider working correctly")
        return True
    except Exception as e:
        print(f"\n✗ YFinance provider test failed: {e}")
        return False


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("PUT SCANNER - PROVIDER TEST SUITE")
    print("=" * 60)
    
    # Check which provider to test
    provider_type = os.environ.get("OPTIONS_PROVIDER", "yfinance").lower()
    
    if provider_type == "schwab":
        success = test_schwab_provider()
    elif provider_type == "yfinance":
        success = test_yfinance_provider()
    else:
        print(f"\nUnknown provider: {provider_type}")
        print("Set OPTIONS_PROVIDER to 'schwab' or 'yfinance'")
        success = False
    
    # Also offer to test the other provider
    if success and provider_type == "schwab":
        print("\nWould you like to test YFinance provider too? (y/n): ", end="")
        try:
            if input().lower() == 'y':
                test_yfinance_provider()
        except (KeyboardInterrupt, EOFError):
            pass
    
    sys.exit(0 if success else 1)
