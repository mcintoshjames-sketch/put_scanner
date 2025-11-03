#!/usr/bin/env python3
"""
Refresh Schwab API token using schwab-py library.
"""
import json
import os
from datetime import datetime
from schwab import auth

# Prompt for credentials since they're not in .env
print("🔐 Schwab Token Refresh")
print("="*60)
print()
print("Your token needs to be refreshed. Please provide your Schwab API credentials.")
print("(These will NOT be saved - only used to refresh the token)")
print()

SCHWAB_APP_KEY = input("Enter your Schwab App Key: ").strip()
SCHWAB_SECRET = input("Enter your Schwab App Secret: ").strip()

if not SCHWAB_APP_KEY or not SCHWAB_SECRET:
    print("❌ Error: Both App Key and App Secret are required")
    exit(1)

# Load current token
with open('schwab_token.json', 'r') as f:
    token_data = json.load(f)

token_path = "schwab_token.json"

print()
print("🔄 Refreshing token...")
print(f"Token file: {token_path}")

try:
    # Load current token to check expiration
    with open(token_path, 'r') as f:
        token_data = json.load(f)
    
    expires_at = token_data['token']['expires_at']
    expires_dt = datetime.fromtimestamp(expires_at)
    print(f"Current token expires: {expires_dt.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Use schwab-py's auth to refresh from token file
    # This will automatically refresh the token if it's expired or about to expire
    print()
    print("Refreshing token using schwab-py...")
    client = auth.client_from_token_file(token_path, SCHWAB_APP_KEY, SCHWAB_SECRET)
    
    # Read the updated token file
    with open(token_path, 'r') as f:
        new_token_data = json.load(f)
    
    new_expires_at = new_token_data['token']['expires_at']
    new_expires_dt = datetime.fromtimestamp(new_expires_at)
    
    print()
    print("✅ Token refreshed successfully!")
    print(f"New token expires: {new_expires_dt.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Time until expiration: {(new_expires_at - datetime.now().timestamp()) / 60:.0f} minutes")
    
except FileNotFoundError:
    print(f"❌ Error: Token file not found: {token_path}")
    print("You may need to generate a new token using schwab-generate-token.py")
    
except Exception as e:
    print(f"❌ Error refreshing token: {e}")
    import traceback
    traceback.print_exc()
