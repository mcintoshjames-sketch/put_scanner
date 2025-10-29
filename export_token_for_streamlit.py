#!/usr/bin/env python3
"""
Export Schwab token in Streamlit secrets format.

Run this after authenticating locally:
1. python test_providers.py (authenticate with Schwab)
2. python export_token_for_streamlit.py (get secrets format)
3. Copy output to Streamlit Cloud secrets
"""

from providers.schwab_streamlit import export_token_for_streamlit

if __name__ == "__main__":
    export_token_for_streamlit()
