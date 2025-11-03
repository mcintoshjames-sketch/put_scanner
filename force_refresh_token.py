#!/usr/bin/env python3
"""
Force refresh Schwab access token using the refresh token.
"""
import json
import os
import requests
from datetime import datetime

# Get credentials (these are safe to use - they're your app credentials, not passwords)
SCHWAB_APP_KEY = "6BfiBC8PtJAEq9orfCzUaOA9GKGGMCRa5cRyNqH6ZnYDTH7t"
SCHWAB_SECRET = "jDt6jZ3QFkMkjmKPGoXn0g8SasymLZb6LUvW9HCVnGjAcwzX"

token_path = "schwab_token.json"

print("🔄 Force Refreshing Schwab Access Token")
print("="*60)

try:
    # Load current token
    with open(token_path, 'r') as f:
        token_data = json.load(f)
    
    refresh_token = token_data['token']['refresh_token']
    expires_at = token_data['token']['expires_at']
    expires_dt = datetime.fromtimestamp(expires_at)
    
    print(f"Current access token expires: {expires_dt.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Time remaining: {(expires_at - datetime.now().timestamp()) / 60:.0f} minutes")
    print()
    
    # Make OAuth token refresh request
    token_url = "https://api.schwabapi.com/v1/oauth/token"
    
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token
    }
    
    print("Making refresh request to Schwab API...")
    response = requests.post(
        token_url,
        data=data,
        auth=(SCHWAB_APP_KEY, SCHWAB_SECRET),
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    
    if response.status_code == 200:
        new_tokens = response.json()
        
        # Update token data
        now_ts = int(datetime.now().timestamp())
        token_data['creation_timestamp'] = now_ts
        token_data['token']['access_token'] = new_tokens['access_token']
        token_data['token']['expires_in'] = new_tokens['expires_in']
        token_data['token']['expires_at'] = now_ts + new_tokens['expires_in']
        token_data['token']['token_type'] = new_tokens.get('token_type', 'Bearer')
        token_data['token']['scope'] = new_tokens.get('scope', 'api')
        
        # Update refresh token if provided (sometimes it's renewed)
        if 'refresh_token' in new_tokens:
            token_data['token']['refresh_token'] = new_tokens['refresh_token']
            print("✓ Refresh token was also renewed")
        
        if 'id_token' in new_tokens:
            token_data['token']['id_token'] = new_tokens['id_token']
        
        # Save updated token
        with open(token_path, 'w') as f:
            json.dump(token_data, f, indent=2)
        
        new_expires_dt = datetime.fromtimestamp(token_data['token']['expires_at'])
        
        print()
        print("✅ Access token refreshed successfully!")
        print(f"New token expires: {new_expires_dt.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Time until expiration: {new_tokens['expires_in'] / 60:.0f} minutes")
        print()
        print("Your token has been refreshed and saved to schwab_token.json")
        
    else:
        print(f"❌ Error: {response.status_code}")
        print(f"Response: {response.text}")
        
        if response.status_code == 400:
            print()
            print("The refresh token may have expired (they last 7 days).")
            print("You'll need to re-authenticate using: schwab-generate-token.py")
        
except FileNotFoundError:
    print(f"❌ Error: Token file not found: {token_path}")
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
