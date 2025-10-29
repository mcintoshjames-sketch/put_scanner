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
            token_data = dict(st.secrets["SCHWAB_TOKEN"])
            
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
        print("\n[SCHWAB_TOKEN]")
        for key, value in token_data.items():
            if isinstance(value, str):
                print(f'{key} = "{value}"')
            else:
                print(f'{key} = {value}')
        print("\n" + "="*60)
        print("\nDon't forget to also add:")
        print("OPTIONS_PROVIDER = \"schwab\"")
        print("SCHWAB_API_KEY = \"your_key\"")
        print("SCHWAB_APP_SECRET = \"your_secret\"")
        print("="*60 + "\n")
    except FileNotFoundError:
        print(f"Token file not found: {token_file_path}")
        print("Authenticate first by running: python test_providers.py")
    except Exception as e:
        print(f"Error reading token: {e}")


if __name__ == "__main__":
    # Run this to get the secrets format
    export_token_for_streamlit()
