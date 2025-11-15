#!/bin/bash
# Restart Streamlit to pick up code changes

echo "Stopping Streamlit..."
pkill -f "streamlit run strategy_lab.py"

echo "Waiting for process to terminate..."
sleep 2

echo "Starting Streamlit..."
cd /workspaces/put_scanner
source .venv/bin/activate
streamlit run strategy_lab.py &

echo "Streamlit restarted. Check the app at the URL shown above."
