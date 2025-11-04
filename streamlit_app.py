"""
Deprecated entry point for the app.

This file used to host a simplified scanner UI. The canonical entry point is now
strategy_lab.py.

How to run:
    streamlit run strategy_lab.py

This module intentionally stops immediately to avoid confusion.
"""

import sys

try:
    import streamlit as st
except Exception:
    sys.stderr.write(
        "streamlit_app.py is deprecated. Please run:\n\n  streamlit run strategy_lab.py\n\n"
    )
    raise SystemExit(0)

st.set_page_config(page_title="Deprecated: use strategy_lab.py", layout="centered")

st.title("This entry point is deprecated")
st.info("Please run the Strategy Lab with:")
st.code("streamlit run strategy_lab.py", language="bash")

st.stop()
