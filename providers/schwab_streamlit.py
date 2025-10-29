# providers/schwab_streamlit.py — Streamlit Cloud helper for Schwab tokens
"""
Helper for using Schwab API on Streamlit Cloud.
Loads token from Streamlit secrets instead of local file.
"""
import os
import json
import streamlit as st
from schwab import auth, client


def get_schwab_client_from_streamlit_secrets():
    """
    Create Schwab client using tokens from Streamlit secrets.
    
    In Streamlit Cloud secrets, add:
    [SCHWAB_TOKEN]
    access_token = "..."
    refresh_token = "..."
    token_type = "Bearer"
    expires_in = 1800
    expires_at = 1234567890.123
    """
    try:
        api_key = st.secrets.get("SCHWAB_API_KEY")
        app_secret = st.secrets.get("SCHWAB_APP_SECRET")
        
        if not api_key or not app_secret:
            raise ValueError("SCHWAB_API_KEY and SCHWAB_APP_SECRET must be in secrets")
        
        # Check if token is in secrets
        if "SCHWAB_TOKEN" in st.secrets:
            token_dict = dict(st.secrets["SCHWAB_TOKEN"])
            
            # Create token structure expected by schwab-py
            # It expects: {"creation_timestamp": ..., "token": {...}}
            token_data = {
                "creation_timestamp": token_dict.get("creation_timestamp", 0),
                "token": {
                    "access_token": token_dict.get("access_token"),
                    "refresh_token": token_dict.get("refresh_token"),
                    "token_type": token_dict.get("token_type", "Bearer"),
                    "expires_in": token_dict.get("expires_in", 1800),
                    "expires_at": token_dict.get("expires_at", 0),
                    "scope": token_dict.get("scope", "api")
                }
            }
            
            # Create a temporary token file
            token_path = "/tmp/schwab_token.json"
            with open(token_path, "w") as f:
                json.dump(token_data, f)
            
            # Create client from token file
            c = auth.client_from_token_file(token_path, api_key, app_secret)
            return c
        else:
            raise ValueError(
                "SCHWAB_TOKEN not found in secrets. "
                "Authenticate locally first and add token to secrets."
            )
    except Exception as e:
        raise RuntimeError(f"Failed to create Schwab client from secrets: {e}")


def export_token_for_streamlit(token_file_path: str = "./schwab_token.json"):
    """
    Read local token file and print in Streamlit secrets format.
    Run this locally after authenticating.
    """
    try:
        with open(token_file_path, "r") as f:
            token_data = json.load(f)
        
        print("\n" + "="*60)
        print("Add this to your Streamlit Cloud secrets:")
        print("="*60)
        print("\nOPTIONS_PROVIDER = \"schwab\"")
        print("SCHWAB_API_KEY = \"your_key\"")
        print("SCHWAB_APP_SECRET = \"your_secret\"")
        print("SCHWAB_CALLBACK_URL = \"https://localhost\"")
        print("\n[SCHWAB_TOKEN]")
        
        # Handle nested token structure from schwab-py
        if "token" in token_data and isinstance(token_data["token"], dict):
            # Extract token fields
            token_dict = token_data["token"]
            for key in ["access_token", "refresh_token", "token_type", "expires_in", "expires_at", "scope"]:
                if key in token_dict:
                    value = token_dict[key]
                    if isinstance(value, str):
                        print(f'{key} = "{value}"')
                    else:
                        print(f'{key} = {value}')
            
            # Add creation timestamp if present
            if "creation_timestamp" in token_data:
                print(f'creation_timestamp = {token_data["creation_timestamp"]}')
        else:
            # Flat structure
            for key, value in token_data.items():
                if isinstance(value, str):
                    print(f'{key} = "{value}"')
                else:
                    print(f'{key} = {value}')
        
        print("\n" + "="*60)
        print("\n✓ Copy the above to Streamlit Cloud → Settings → Secrets")
        print("="*60 + "\n")
    except FileNotFoundError:
        print(f"Token file not found: {token_file_path}")
        print("Authenticate first by running: python test_providers.py")
    except Exception as e:
        print(f"Error reading token: {e}")


if __name__ == "__main__":
    # Run this to get the secrets format
    export_token_for_streamlit()
