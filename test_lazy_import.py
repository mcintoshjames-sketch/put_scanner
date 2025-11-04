#!/usr/bin/env python3
"""Test that analyzer functions can actually call their lazy imports"""

import sys
sys.path.insert(0, '/workspaces/put_scanner')

from strategy_analysis import prescreen_tickers

print("Testing prescreen_tickers with lazy import...")
try:
    # This should trigger the lazy import of strategy_lab inside prescreen_tickers
    result = prescreen_tickers(['AAPL'], min_price=100, max_price=300)
    print(f"✅ prescreen_tickers executed successfully!")
    print(f"   Result type: {type(result)}")
    print(f"   Result shape: {result.shape if hasattr(result, 'shape') else 'N/A'}")
except SystemExit as e:
    print(f"⚠️  SystemExit caught: {e}")
    print(f"   This means the guard is working but blocking function execution")
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
