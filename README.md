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

   Note: `streamlit_app.py` is deprecated. Always use `strategy_lab.py`.

The app will open in your browser (default http://localhost:8501). Press Ctrl+C in the terminal to stop.

## Tips
- To use a different port or network host: `streamlit run strategy_lab.py --server.port 8502 --server.address 0.0.0.0`
- If you see missing package errors, ensure your virtual environment is activated (`source .venv/bin/activate`) and re-run `pip install -r requirements.txt`.
- yfinance data can be delayed and limited; the tool is for education only.

## Smoke test live trading (no real orders)

You can exercise the full order execution code path without contacting Schwab using the mock transport:

```bash
python smoke_test_trading.py
```

This will:
- Build a sample CSP order
- Preview via a mock endpoint (writes a preview JSON file in `trade_orders/`)
- Submit via a mock endpoint (writes an executed JSON file, extracts a fake orderId)

No live trades are sent. Use this to verify safety checks and payload shape.

## Optional: One-liner using pipx (no venv needed)

If you use pipx, you can run without creating a venv manually:

```zsh
pipx runpip streamlit install -r requirements.txt && pipx run streamlit run strategy_lab.py
```

