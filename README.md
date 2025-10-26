# Put Scanner / Strategy Lab

This is a Streamlit app for scanning cash-secured put, covered call, and collar opportunities and analyzing risk.

## Quick start (macOS, zsh)

1) Ensure Python 3.10+ is available:

   ```zsh
   python3 --version
   ```

2) Create a virtual environment and activate it:

   ```zsh
   cd /Users/jamesmcintosh/Desktop/put_scanner
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3) Install dependencies:

   ```zsh
   pip install -U pip
   pip install -r requirements.txt
   ```

4) Run the Strategy Lab app:

   ```zsh
   streamlit run strategy_lab.py
   ```

   Or run the simpler scanner:

   ```zsh
   streamlit run streamlit_app.py
   ```

The app will open in your browser (default http://localhost:8501). Press Ctrl+C in the terminal to stop.

## Tips
- To use a different port or network host: `streamlit run strategy_lab.py --server.port 8502 --server.address 0.0.0.0`
- If you see missing package errors, ensure your virtual environment is activated (`source .venv/bin/activate`) and re-run `pip install -r requirements.txt`.
- yfinance data can be delayed and limited; the tool is for education only.

## Optional: One-liner using pipx (no venv needed)

If you use pipx, you can run without creating a venv manually:

```zsh
pipx runpip streamlit install -r requirements.txt && pipx run streamlit run strategy_lab.py
```

