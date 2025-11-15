#!/usr/bin/env python3
"""
Schwab Authentication Helper
This script will guide you through the Schwab OAuth authentication process.
"""

import os
import sys
from datetime import datetime
from providers.schwab import SchwabClient, SchwabError
from providers import schwab_auth as schwab_auth_utils


def main():
    print("=" * 60)
    print("Schwab API Authentication")
    print("=" * 60)
    print()
    
    # Check credentials
    api_key = os.environ.get("SCHWAB_API_KEY")
    app_secret = os.environ.get("SCHWAB_APP_SECRET")
    callback_url = os.environ.get("SCHWAB_CALLBACK_URL", "https://127.0.0.1")
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
    print("1. A URL will be displayed below")
    print("2. Copy the URL and open it in your browser")
    print("3. Log in to your Schwab account")
    print("4. Authorize the application")
    print("5. You'll be redirected to a localhost URL")
    print("6. Copy the ENTIRE URL from your browser's address bar")
    print("7. Paste it back here when prompted")
    print()
    input("Press Enter to continue...")
    print()
    
    try:
        # Delete old token file if it exists
        if os.path.exists(token_path):
            import shutil
            backup_path = token_path + ".old"
            shutil.move(token_path, backup_path)
            print(f"📦 Backed up old token to: {backup_path}")
            print()
        
        # Manual OAuth flow with explicit URL display
        auth_url = schwab_auth_utils.build_authorization_url(api_key, callback_url)
        
        print("=" * 60)
        print("🌐 OPEN THIS URL IN YOUR BROWSER:")
        print("=" * 60)
        print()
        print(auth_url)
        print()
        print("=" * 60)
        print()
        
        # Get the callback URL from user
        print("After authorizing, you'll be redirected to a URL like:")
        print(f"{callback_url}/?code=XXXXXX&session=YYYYYY")
        print()
        callback_response = input("Paste the ENTIRE redirect URL here: ").strip()
        
        if not callback_response:
            print("❌ Error: No URL provided")
            sys.exit(1)
        
        # Parse the code from the callback URL
        try:
            auth_code = schwab_auth_utils.parse_auth_code(callback_response)
        except Exception as exc:
            print(f"❌ Error parsing authorization code: {exc}")
            sys.exit(1)

        print(f"✓ Got authorization code: {auth_code[:20]}...")
        print()

        print("🔄 Exchanging authorization code for tokens...")
        try:
            result = schwab_auth_utils.complete_manual_oauth(
                api_key=api_key,
                app_secret=app_secret,
                callback_url=callback_url,
                token_path=token_path,
                callback_response=callback_response,
            )
        except Exception as exc:
            print(f"❌ Token exchange failed: {exc}")
            sys.exit(1)

        token_file_data = result.get("token_data", {})
        print(f"✓ Token saved to: {result.get('token_path', token_path)}")
        if "backup_path" in result:
            print(f"  (Previous token backed up to {result['backup_path']})")
        print()
        
        # Wrap in SchwabClient for testing
        from providers.schwab import SchwabClient
        schwab_client = SchwabClient(
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
        
        # Check token expiration
        expires_at = token_file_data['token']['expires_at']
        expires_dt = datetime.fromtimestamp(expires_at)
        minutes_remaining = (expires_at - datetime.now().timestamp()) / 60
        
        print(f"✓ Token expires: {expires_dt.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"✓ Valid for: {minutes_remaining:.0f} minutes ({minutes_remaining/60:.1f} hours)")
        print()
        print("You can now use the Strategy Lab with Schwab data!")
        print()
        
        # Test the connection
        print("Testing connection by fetching a quote for SPY...")
        try:
            price = schwab_client.last_price("SPY")
            print(f"✅ SPY last price: ${price:.2f}")
            print()
            print("Schwab API is working correctly! 🎉")
        except Exception as e:
            print(f"⚠️  Warning: Could not fetch test quote: {e}")
            print("But authentication was successful.")
            print("The token should work for other API calls.")
        
    except KeyboardInterrupt:
        print()
        print("Authentication cancelled.")
        sys.exit(1)
    except Exception as e:
        print()
        print(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
