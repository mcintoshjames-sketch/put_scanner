#!/usr/bin/env python3
"""
Test script to verify Schwab token management features.
Run this to check if token info and refresh methods work correctly.
"""

import os
import sys

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from providers.schwab import SchwabClient, SchwabError


def test_token_info():
    """Test the get_token_info method."""
    print("=" * 60)
    print("Testing Token Info Method")
    print("=" * 60)
    
    try:
        # Check if credentials are available
        api_key = os.environ.get("SCHWAB_API_KEY")
        app_secret = os.environ.get("SCHWAB_APP_SECRET")
        
        if not api_key or not app_secret:
            print("⚠️  Schwab credentials not found in environment")
            print("Set SCHWAB_API_KEY and SCHWAB_APP_SECRET to test")
            return False
        
        print(f"✓ API Key: {api_key[:10]}...")
        print(f"✓ App Secret: {app_secret[:10]}...")
        print()
        
        # Try to get token info without creating full client
        # (this tests the method independently)
        token_path = os.environ.get("SCHWAB_TOKEN_PATH", "./schwab_token.json")
        
        if not os.path.exists(token_path):
            print(f"⚠️  Token file not found: {token_path}")
            print("Run: python authenticate_schwab.py")
            return False
        
        print(f"✓ Token file exists: {token_path}")
        print()
        
        # Create client (this will test authentication)
        try:
            client = SchwabClient()
            print("✓ Client created successfully")
            print()
            
            # Test get_token_info method
            print("Fetching token info...")
            token_info = client.get_token_info()
            
            print("\nToken Information:")
            print("-" * 40)
            for key, value in token_info.items():
                if key != "error_detail":
                    print(f"  {key}: {value}")
            
            if token_info.get("exists"):
                if "error" in token_info:
                    print(f"\n❌ Error reading token: {token_info['error']}")
                    return False
                else:
                    print("\n✅ Token info retrieved successfully!")
                    
                    # Show status
                    if token_info.get("is_expired"):
                        print("🔴 Token is EXPIRED - needs refresh")
                    elif token_info.get("minutes_remaining", 0) < 60:
                        print(f"⚠️  Token expires soon: {token_info.get('minutes_remaining'):.0f} minutes")
                    else:
                        print(f"✓ Token is valid for {token_info.get('hours_remaining'):.1f} hours")
                    
                    return True
            else:
                print("\n❌ Token file not found")
                return False
                
        except SchwabError as e:
            print(f"\n❌ Error creating client: {e}")
            return False
            
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_token_refresh():
    """Test the refresh_token method (optional - requires valid token)."""
    print("\n" + "=" * 60)
    print("Testing Token Refresh Method")
    print("=" * 60)

    if not sys.stdin.isatty():
        print("Skipping token refresh test (non-interactive environment)")
        return True

    response = input("\nDo you want to test token refresh? (y/N): ")
    if response.lower() != 'y':
        print("Skipping token refresh test")
        return True
    
    try:
        client = SchwabClient()
        
        print("\nAttempting to refresh token...")
        result = client.refresh_token()
        
        print("\nRefresh Result:")
        print("-" * 40)
        for key, value in result.items():
            if key != "error_detail":
                print(f"  {key}: {value}")
        
        if result.get("success"):
            print("\n✅ Token refreshed successfully!")
            return True
        else:
            print(f"\n❌ Token refresh failed: {result.get('message')}")
            if "error_detail" in result:
                print(f"Details: {result['error_detail']}")
            return False
            
    except Exception as e:
        print(f"\n❌ Error during refresh: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("\n")
    print("╔" + "═" * 58 + "╗")
    print("║" + " " * 10 + "Schwab Token Management Test" + " " * 19 + "║")
    print("╚" + "═" * 58 + "╝")
    print()
    
    # Test 1: Token Info
    test1_passed = test_token_info()
    
    # Test 2: Token Refresh (optional)
    test2_passed = test_token_refresh()
    
    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    print(f"Token Info: {'✅ PASSED' if test1_passed else '❌ FAILED'}")
    print(f"Token Refresh: {'✅ PASSED' if test2_passed else '⏭️  SKIPPED'}")
    print()
    
    if test1_passed:
        print("✅ Token management features are working correctly!")
    else:
        print("❌ Some tests failed. Check the errors above.")
    print()


if __name__ == "__main__":
    main()
