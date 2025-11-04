#!/usr/bin/env python3
"""
Schwab Authentication Helper
This script will guide you through the Schwab OAuth authentication process.
"""

import os
import sys
from providers.schwab import SchwabClient, SchwabError


def main():
    print("=" * 60)
    print("Schwab API Authentication")
    print("=" * 60)
    print()
    
    # Check credentials
    api_key = os.environ.get("SCHWAB_API_KEY")
    app_secret = os.environ.get("SCHWAB_APP_SECRET")
    callback_url = os.environ.get("SCHWAB_CALLBACK_URL", "https://localhost")
    token_path = os.environ.get("SCHWAB_TOKEN_PATH", "./schwab_token.json")
    
    if not api_key or not app_secret:
        print("❌ Error: Schwab credentials not found!")
        print()
        print("Please set the following environment variables:")
        print("  - SCHWAB_API_KEY")
        print("  - SCHWAB_APP_SECRET")
        print("  - SCHWAB_CALLBACK_URL (optional, defaults to https://localhost)")
        print()
        sys.exit(1)
    
    print(f"✓ API Key: {api_key[:10]}...")
    print(f"✓ App Secret: {app_secret[:10]}...")
    print(f"✓ Callback URL: {callback_url}")
    print(f"✓ Token will be saved to: {token_path}")
    print()
    
    # Check if token already exists
    if os.path.exists(token_path):
        print(f"⚠️  Token file already exists at: {token_path}")
        response = input("Do you want to re-authenticate? (y/N): ")
        if response.lower() != 'y':
            print("Keeping existing token. Exiting.")
            sys.exit(0)
        print()
    
    print("Starting OAuth authentication flow...")
    print()
    print("📋 Instructions:")
    print("1. A browser will open (or you'll get a URL)")
    print("2. Log in to your Schwab account")
    print("3. Authorize the application")
    print("4. You'll be redirected to a localhost URL")
    print("5. Copy the ENTIRE URL from your browser")
    print("6. Paste it back here when prompted")
    print()
    input("Press Enter to continue...")
    print()
    
    try:
        # This will trigger the OAuth flow
        client = SchwabClient(
            api_key=api_key,
            app_secret=app_secret,
            callback_url=callback_url,
            token_path=token_path
        )
        
        print()
        print("=" * 60)
        print("✅ Authentication successful!")
        print("=" * 60)
        print()
        print(f"Token saved to: {token_path}")
        print()
        print("You can now use the Strategy Lab with Schwab data!")
        print()
        
        # Test the connection
        print("Testing connection by fetching a quote for SPY...")
        try:
            price = client.last_price("SPY")
            print(f"✅ SPY last price: ${price:.2f}")
            print()
            print("Schwab API is working correctly! 🎉")
        except Exception as e:
            print(f"⚠️  Warning: Could not fetch test quote: {e}")
            print("But authentication was successful.")
        
    except SchwabError as e:
        print()
        print("=" * 60)
        print("❌ Authentication failed!")
        print("=" * 60)
        print()
        print(f"Error: {e}")
        print()
        print("Troubleshooting tips:")
        print("1. Make sure your API credentials are correct")
        print("2. Ensure your app is registered in Schwab Developer Portal")
        print("3. Check that the callback URL matches your app settings")
        print("4. Try logging out of Schwab and logging back in")
        print()
        sys.exit(1)
    except KeyboardInterrupt:
        print()
        print("Authentication cancelled.")
        sys.exit(1)
    except Exception as e:
        print()
        print(f"❌ Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
