#!/bin/bash
# Secure startup script for Strategy Lab
# This script loads environment variables and starts the app

set -e  # Exit on error

# Load environment variables from .env file
if [ -f .env ]; then
    echo "Loading environment variables from .env..."
    export $(grep -v '^#' .env | grep -v '^$' | xargs)
    echo "✓ Environment variables loaded"
    echo "✓ Provider: $OPTIONS_PROVIDER"
else
    echo "ERROR: .env file not found!"
    exit 1
fi

# Verify critical variables are set
if [ "$OPTIONS_PROVIDER" = "schwab" ]; then
    if [ -z "$SCHWAB_API_KEY" ] || [ -z "$SCHWAB_APP_SECRET" ]; then
        echo "ERROR: Schwab credentials not found in .env file!"
        exit 1
    fi
    echo "✓ Schwab credentials verified"
fi

# Kill any existing streamlit processes
echo "Checking for existing Streamlit processes..."
pkill -f streamlit 2>/dev/null || true
sleep 1

# Start the app on port 8502
echo "Starting Strategy Lab..."
echo "Access the app at: http://localhost:8502"
echo "Press Ctrl+C to stop"
echo ""
streamlit run strategy_lab.py --server.port 8502
